import copy
import io
import unittest
from unittest import mock

import claude_any


class OpenCodeProviderTests(unittest.TestCase):
    def opencode_cfg(self, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["opencode"])
        pcfg.update(overrides)
        return {
            "current_provider": "opencode",
            "providers": {
                "opencode": pcfg,
            },
        }

    def opencode_go_cfg(self, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["opencode-go"])
        pcfg.update(overrides)
        return {
            "current_provider": "opencode-go",
            "providers": {
                "opencode-go": pcfg,
            },
        }

    def test_provider_is_registered(self):
        self.assertEqual("opencode", claude_any.PROVIDER_ALIASES["opencode"])
        self.assertEqual("opencode", claude_any.PROVIDER_ALIASES["opencode.ai"])
        self.assertEqual("opencode", claude_any.PROVIDER_ALIASES["zen"])
        self.assertEqual("opencode-go", claude_any.PROVIDER_ALIASES["opencode-go"])
        self.assertEqual("opencode-go", claude_any.PROVIDER_ALIASES["opencode.go"])
        self.assertEqual("OpenCode Zen", claude_any.PROVIDER_LABELS["opencode"])
        self.assertEqual("OpenCode Go", claude_any.PROVIDER_LABELS["opencode-go"])
        self.assertEqual("https://opencode.ai/zen", claude_any.default_base_url("opencode"))
        self.assertEqual("https://opencode.ai/zen/go", claude_any.default_base_url("opencode-go"))

    def test_default_config_matches_zen_docs(self):
        pcfg = claude_any.DEFAULT_CONFIG["providers"]["opencode"]
        self.assertEqual("https://opencode.ai/zen", pcfg["base_url"])
        self.assertEqual("claude-sonnet-4-6", pcfg["current_model"])
        self.assertEqual("claude-haiku-4-5", pcfg["haiku_model"])
        self.assertEqual("claude-sonnet-4-6", pcfg["subagent_model"])
        self.assertTrue(pcfg["native_compat"])

    def test_go_default_config_matches_go_docs(self):
        pcfg = claude_any.DEFAULT_CONFIG["providers"]["opencode-go"]
        self.assertEqual("https://opencode.ai/zen/go", pcfg["base_url"])
        self.assertEqual("qwen3.6-plus", pcfg["current_model"])
        self.assertEqual("qwen3.5-plus", pcfg["haiku_model"])
        self.assertEqual("qwen3.6-plus", pcfg["subagent_model"])
        self.assertTrue(pcfg["native_compat"])

    def test_env_vars_route_opencode_through_claude_any_router(self):
        cfg = self.opencode_cfg(api_key="sk-opencode-test")
        pcfg = cfg["providers"]["opencode"]
        env = claude_any.env_vars(cfg)
        self.assertEqual("opencode", env["CLAUDE_ANY_PROVIDER"])
        self.assertEqual(claude_any.ROUTER_BASE, env["ANTHROPIC_BASE_URL"])
        self.assertEqual("sk-opencode-test", env["ANTHROPIC_AUTH_TOKEN"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        expected_model = claude_any.claude_code_context_model_alias("opencode", pcfg, claude_any.current_alias(cfg))
        self.assertEqual(expected_model, env["ANTHROPIC_MODEL"])

    def test_workflow_env_advertises_inferred_claude_capabilities(self):
        cfg = self.opencode_cfg(
            api_key="sk-opencode-test",
            current_model="claude-opus-4-8",
            workflows_enabled=True,
        )
        pcfg = cfg["providers"]["opencode"]

        env = claude_any.env_vars(cfg)

        self.assertNotIn("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", env)
        self.assertEqual(env["ANTHROPIC_MODEL"], env["ANTHROPIC_CUSTOM_MODEL_OPTION"])
        caps = env["ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES"].split(",")
        self.assertIn("effort", caps)
        self.assertIn("xhigh_effort", caps)
        self.assertIn("max_effort", caps)
        self.assertIn("adaptive_thinking", caps)
        self.assertEqual(
            env["ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES"],
            env["ANTHROPIC_DEFAULT_OPUS_MODEL_SUPPORTED_CAPABILITIES"],
        )

    def test_configured_capabilities_override_inference(self):
        cfg = self.opencode_cfg(
            api_key="sk-opencode-test",
            current_model="custom-model",
            claude_code_supported_capabilities=["effort", "max_effort", "unknown"],
        )

        env = claude_any.env_vars(cfg)

        self.assertEqual("effort,max_effort", env["ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES"])

    def test_ultracode_launch_requires_xhigh_capability(self):
        cfg = self.opencode_cfg(
            api_key="sk-opencode-test",
            current_model="deepseek-v4-flash-free",
            ultracode_enabled=True,
        )
        with mock.patch.object(claude_any, "base_url_status_line", return_value="Base URL: OK"):
            errors = claude_any.launch_readiness_errors(cfg)

        self.assertTrue(any("ultracode requires" in error for error in errors))

    def test_ultracode_runtime_settings(self):
        pcfg = self.opencode_cfg(ultracode_enabled=True)["providers"]["opencode"]

        self.assertEqual({"ultracode": True}, claude_any.claude_code_runtime_settings("opencode", pcfg))

    def test_ultracode_runtime_settings_args_are_appended(self):
        pcfg = self.opencode_cfg(ultracode_enabled=True)["providers"]["opencode"]
        extra_args: list[str] = []

        claude_any.append_claude_code_runtime_settings_args(extra_args, [], "opencode", pcfg)

        self.assertEqual(["--settings", '{"ultracode":true}'], extra_args)

    def test_env_vars_route_opencode_go_through_claude_any_router(self):
        cfg = self.opencode_go_cfg(api_key="sk-opencode-test")
        pcfg = cfg["providers"]["opencode-go"]
        env = claude_any.env_vars(cfg)
        self.assertEqual("opencode-go", env["CLAUDE_ANY_PROVIDER"])
        self.assertEqual(claude_any.ROUTER_BASE, env["ANTHROPIC_BASE_URL"])
        self.assertEqual("sk-opencode-test", env["ANTHROPIC_AUTH_TOKEN"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        expected_model = claude_any.claude_code_context_model_alias("opencode-go", pcfg, claude_any.current_alias(cfg))
        self.assertEqual(expected_model, env["ANTHROPIC_MODEL"])

    def test_launch_requires_opencode_api_key(self):
        errors = claude_any.launch_readiness_errors(self.opencode_cfg(api_key=""))
        self.assertTrue(any("OpenCode Zen requires" in err for err in errors))
        self.assertTrue(claude_any.launch_blockers_require_api_key(errors))

    def test_launch_requires_opencode_go_api_key(self):
        errors = claude_any.launch_readiness_errors(self.opencode_go_cfg(api_key=""))
        self.assertTrue(any("OpenCode Go requires" in err for err in errors))
        self.assertTrue(claude_any.launch_blockers_require_api_key(errors))

    def test_model_list_reads_zen_v1_models(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        response = {
            "object": "list",
            "data": [
                {"id": "claude-sonnet-4-6"},
                {"id": "glm-5.1"},
                {"id": "gpt-5.1"},
            ],
        }
        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "write_model_list_cache") as write_cache,
            mock.patch.object(claude_any, "http_json", return_value=response) as http_json,
        ):
            models = claude_any.upstream_model_ids("opencode", pcfg)
        http_json.assert_called_once()
        url = http_json.call_args.args[0]
        self.assertEqual("https://opencode.ai/zen/v1/models", url)
        headers = http_json.call_args.kwargs["headers"]
        self.assertEqual("Bearer sk-opencode-test", headers["authorization"])
        self.assertEqual(f"claude-any/{claude_any.VERSION}", headers["user-agent"])
        self.assertIn("claude-sonnet-4-6", models)
        self.assertIn("glm-5.1", models)
        self.assertIn("gpt-5.1", models)
        write_cache.assert_called_once()

    def test_go_model_list_reads_go_v1_models(self):
        pcfg = self.opencode_go_cfg(api_key="sk-opencode-test")["providers"]["opencode-go"]
        response = {
            "object": "list",
            "data": [
                {"id": "qwen3.6-plus"},
                {"id": "glm-5.1"},
                {"id": "deepseek-v4-pro"},
            ],
        }
        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "write_model_list_cache") as write_cache,
            mock.patch.object(claude_any, "http_json", return_value=response) as http_json,
        ):
            models = claude_any.upstream_model_ids("opencode-go", pcfg)
        http_json.assert_called_once()
        url = http_json.call_args.args[0]
        self.assertEqual("https://opencode.ai/zen/go/v1/models", url)
        headers = http_json.call_args.kwargs["headers"]
        self.assertEqual("Bearer sk-opencode-test", headers["authorization"])
        self.assertEqual(f"claude-any/{claude_any.VERSION}", headers["user-agent"])
        self.assertIn("qwen3.6-plus", models)
        self.assertIn("glm-5.1", models)
        self.assertIn("deepseek-v4-pro", models)
        write_cache.assert_called_once()

    def test_zen_advisor_panel_does_not_inject_global_deepseek_recommendation(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        with mock.patch.object(
            claude_any,
            "upstream_model_ids",
            return_value=["claude-sonnet-4-6", "deepseek-v4-flash-free", "glm-5.1"],
        ):
            rows, values = claude_any.advisor_model_panel_rows("opencode", pcfg)

        self.assertNotIn("deepseek-v4-pro", values)
        self.assertFalse(any("deepseek-v4-pro" in row for row in rows))
        self.assertIn("deepseek-v4-flash-free", values)
        self.assertIn("__refresh_models__", values)

    def test_model_panel_keeps_refresh_action_after_fetch(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        with mock.patch.object(claude_any, "upstream_model_ids", return_value=["claude-sonnet-4-6"]):
            rows, values = claude_any.model_panel_rows("opencode", pcfg, fetch=True, force_refresh=True)

        self.assertEqual("__refresh_models__", values[0])
        self.assertTrue(any("Refresh provider model list" in row for row in rows))

    def test_advisor_panel_can_force_refresh_provider_models(self):
        pcfg = self.opencode_go_cfg(api_key="sk-opencode-test")["providers"]["opencode-go"]
        with mock.patch.object(claude_any, "upstream_model_ids", return_value=["deepseek-v4-pro"]) as upstream:
            rows, values = claude_any.advisor_model_panel_rows(
                "opencode-go",
                pcfg,
                fetch=True,
                force_refresh=True,
            )

        upstream.assert_called_once_with("opencode-go", pcfg, force_refresh=True)
        self.assertIn("__refresh_models__", values)
        self.assertIn("deepseek-v4-pro", values)
        self.assertTrue(any("Refresh provider model list" in row for row in rows))

    def test_advisor_panel_keeps_preconfigured_custom_advisor_visible(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test", advisor_model="custom-advisor")["providers"]["opencode"]
        with mock.patch.object(claude_any, "upstream_model_ids", return_value=["claude-sonnet-4-6"]):
            rows, values = claude_any.advisor_model_panel_rows("opencode", pcfg)

        self.assertIn("custom-advisor", values)
        self.assertTrue(any("custom-advisor" in row for row in rows))

    def test_model_list_falls_back_to_config_when_zen_unreachable(self):
        pcfg = self.opencode_cfg(
            current_model="glm-5.1",
            custom_models=["claude-sonnet-4-6", "glm-5.1"],
        )["providers"]["opencode"]
        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "write_model_list_cache") as write_cache,
            mock.patch.object(claude_any, "http_json", side_effect=TimeoutError("offline")),
        ):
            models = claude_any.upstream_model_ids("opencode", pcfg)
        self.assertEqual(["claude-sonnet-4-6", "glm-5.1"], models)
        write_cache.assert_called_once()

    def test_provider_headers_include_opencode_api_key(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        headers = claude_any.provider_headers("opencode", pcfg)
        self.assertEqual("Bearer sk-opencode-test", headers["authorization"])
        self.assertEqual("sk-opencode-test", headers["x-api-key"])
        self.assertEqual("2023-06-01", headers["anthropic-version"])
        self.assertEqual(f"claude-any/{claude_any.VERSION}", headers["user-agent"])

    def test_provider_headers_include_opencode_go_api_key(self):
        pcfg = self.opencode_go_cfg(api_key="sk-opencode-test")["providers"]["opencode-go"]
        headers = claude_any.provider_headers("opencode-go", pcfg)
        self.assertEqual("Bearer sk-opencode-test", headers["authorization"])
        self.assertEqual("sk-opencode-test", headers["x-api-key"])
        self.assertEqual("2023-06-01", headers["anthropic-version"])
        self.assertEqual(f"claude-any/{claude_any.VERSION}", headers["user-agent"])

    def test_zen_endpoint_family_mapping(self):
        self.assertEqual("anthropic-messages", claude_any.opencode_zen_endpoint_kind("claude-sonnet-4-6"))
        self.assertEqual("anthropic-messages", claude_any.opencode_zen_endpoint_kind("qwen3.6-plus"))
        self.assertEqual("openai-chat", claude_any.opencode_zen_endpoint_kind("glm-5.1"))
        self.assertEqual("openai-responses", claude_any.opencode_zen_endpoint_kind("gpt-5.1"))
        self.assertEqual("google-generative", claude_any.opencode_zen_endpoint_kind("gemini-3.1-pro"))
        self.assertEqual("anthropic-messages", claude_any.opencode_zen_endpoint_kind("new-custom-model"))

    def test_go_endpoint_family_mapping(self):
        self.assertEqual("anthropic-messages", claude_any.opencode_go_endpoint_kind("qwen3.6-plus"))
        self.assertEqual("anthropic-messages", claude_any.opencode_go_endpoint_kind("minimax-m2.7"))
        self.assertEqual("openai-chat", claude_any.opencode_go_endpoint_kind("glm-5.1"))
        self.assertEqual("openai-chat", claude_any.opencode_go_endpoint_kind("kimi-k2.6"))
        self.assertEqual("openai-chat", claude_any.opencode_go_endpoint_kind("deepseek-v4-pro"))
        self.assertEqual("openai-chat", claude_any.opencode_go_endpoint_kind("mimo-v2.5-pro"))
        self.assertEqual("anthropic-messages", claude_any.opencode_go_endpoint_kind("new-custom-model"))

    def test_native_compat_depends_on_zen_endpoint_family(self):
        claude_cfg = self.opencode_cfg(current_model="claude-sonnet-4-6")["providers"]["opencode"]
        glm_cfg = self.opencode_cfg(current_model="glm-5.1")["providers"]["opencode"]
        self.assertTrue(claude_any.provider_native_compat_enabled("opencode", claude_cfg))
        self.assertFalse(claude_any.provider_native_compat_enabled("opencode", glm_cfg))

    def test_endpoint_override_takes_precedence_over_fallback(self):
        pcfg = self.opencode_go_cfg(
            current_model="glm-5.1",
            model_endpoints={"glm-5.1": "messages"},
        )["providers"]["opencode-go"]
        self.assertEqual("anthropic-messages", claude_any.opencode_endpoint_kind("opencode-go", "glm-5.1", pcfg))
        self.assertTrue(claude_any.provider_native_compat_enabled("opencode-go", pcfg))

    def test_provider_option_sets_endpoint_override(self):
        pcfg = self.opencode_go_cfg()["providers"]["opencode-go"]
        claude_any.apply_provider_option("opencode-go", pcfg, "endpoint:custom-model=chat")
        self.assertEqual("openai-chat", pcfg["model_endpoints"]["custom-model"])
        self.assertEqual("openai-chat", claude_any.opencode_endpoint_kind("opencode-go", "custom-model", pcfg))
        claude_any.apply_provider_option("opencode-go", pcfg, "unset:endpoint:custom-model")
        self.assertNotIn("custom-model", pcfg["model_endpoints"])

    def test_go_native_compat_depends_on_endpoint_family(self):
        qwen_cfg = self.opencode_go_cfg(current_model="qwen3.6-plus")["providers"]["opencode-go"]
        glm_cfg = self.opencode_go_cfg(current_model="glm-5.1")["providers"]["opencode-go"]
        self.assertTrue(claude_any.provider_native_compat_enabled("opencode-go", qwen_cfg))
        self.assertFalse(claude_any.provider_native_compat_enabled("opencode-go", glm_cfg))

    def test_model_object_reports_zen_endpoint_metadata(self):
        obj = claude_any.model_object("opencode", "gpt-5.1")
        self.assertEqual("openai-responses", obj["claude_any"]["opencode_endpoint"])
        self.assertFalse(obj["claude_any"]["router_supported"])

    def test_go_model_object_reports_endpoint_metadata(self):
        obj = claude_any.model_object("opencode-go", "glm-5.1")
        self.assertEqual("openai-chat", obj["claude_any"]["opencode_endpoint"])
        self.assertTrue(obj["claude_any"]["router_supported"])

    def test_zen_deepseek_chat_omits_forced_tool_choice(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        body = claude_any.compatibility_tool_request("deepseek-v4-flash-free")

        request = claude_any.openai_compatible_chat_request(
            "opencode",
            "deepseek-v4-flash-free",
            body,
            pcfg,
            stream=False,
        )

        self.assertIn("tools", request)
        self.assertNotIn("tool_choice", request)

    def test_go_deepseek_chat_omits_forced_tool_choice(self):
        pcfg = self.opencode_go_cfg(api_key="sk-opencode-test")["providers"]["opencode-go"]
        body = claude_any.compatibility_tool_request("deepseek-v4-pro")

        request = claude_any.openai_compatible_chat_request(
            "opencode-go",
            "deepseek-v4-pro",
            body,
            pcfg,
            stream=False,
        )

        self.assertIn("tools", request)
        self.assertNotIn("tool_choice", request)

    def test_non_deepseek_chat_preserves_forced_tool_choice(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test")["providers"]["opencode"]
        body = claude_any.compatibility_tool_request("glm-5.1")

        request = claude_any.openai_compatible_chat_request(
            "opencode",
            "glm-5.1",
            body,
            pcfg,
            stream=False,
        )

        self.assertEqual(
            {"type": "function", "function": {"name": claude_any.COMPAT_TOOL_NAME}},
            request.get("tool_choice"),
        )

    def test_zen_deepseek_roundtrips_reasoning_content(self):
        pcfg = self.opencode_cfg(
            api_key="sk-opencode-test",
            current_model="deepseek-v4-flash-free",
        )["providers"]["opencode"]
        data = {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "private chain",
                        "content": "visible answer",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "Bash", "arguments": "{\"command\":\"echo hi\"}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        message = claude_any.openai_chat_to_anthropic(data, "deepseek-v4-flash-free")
        self.assertEqual("thinking", message["content"][0]["type"])
        self.assertEqual("private chain", message["content"][0]["thinking"])

        body = {
            "model": "claude-any-opencode-deepseek-v4-flash-free",
            "thinking": {"type": "enabled"},
            "messages": [{"role": "assistant", "content": message["content"]}],
        }
        normalized = claude_any.normalize_thinking_for_non_anthropic_provider("opencode", pcfg, body)
        self.assertNotIn("thinking", normalized)
        self.assertEqual("thinking", normalized["messages"][0]["content"][0]["type"])

        converted = claude_any.anthropic_messages_to_openai(normalized)
        assistant = [item for item in converted if item.get("role") == "assistant"][-1]
        self.assertEqual("private chain", assistant["reasoning_content"])
        self.assertEqual("visible answer", assistant["content"])
        self.assertEqual("Bash", assistant["tool_calls"][0]["function"]["name"])

    def test_zen_deepseek_backfills_empty_reasoning_for_legacy_history(self):
        pcfg = self.opencode_cfg(
            api_key="sk-opencode-test",
            current_model="deepseek-v4-flash-free",
        )["providers"]["opencode"]
        body = {
            "model": "claude-any-opencode-deepseek-v4-flash-free",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "legacy answer"},
                        {"type": "tool_use", "id": "call_1", "name": "Read", "input": {"file_path": "a.txt"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "call_1", "content": "ok"},
                    ],
                },
            ],
            "tools": [
                {
                    "name": "Read",
                    "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}},
                }
            ],
        }

        request = claude_any.openai_compatible_chat_request(
            "opencode",
            "deepseek-v4-flash-free",
            body,
            pcfg,
            stream=False,
        )

        assistant = [item for item in request["messages"] if item.get("role") == "assistant"][-1]
        self.assertIn("reasoning_content", assistant)
        self.assertEqual("", assistant["reasoning_content"])
        self.assertEqual("legacy answer", assistant["content"])

    def test_non_deepseek_openai_chat_still_strips_anthropic_thinking(self):
        pcfg = self.opencode_cfg(api_key="sk-opencode-test", current_model="glm-5.1")["providers"]["opencode"]
        body = {
            "model": "claude-any-opencode-glm-5-1",
            "thinking": {"type": "enabled"},
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "private", "signature": "sig"},
                        {"type": "text", "text": "visible"},
                    ],
                }
            ],
        }

        normalized = claude_any.normalize_thinking_for_non_anthropic_provider("opencode", pcfg, body)

        self.assertNotIn("thinking", normalized)
        self.assertEqual([{"type": "text", "text": "visible"}], normalized["messages"][0]["content"])

    def test_zen_deepseek_stream_emits_reasoning_block(self):
        class FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()

        def sse(payload):
            return f"data: {claude_any.json.dumps(payload, ensure_ascii=False)}\n\n".encode()

        chunks = [
            sse({"choices": [{"delta": {"reasoning_content": "private "}}]}),
            sse({"choices": [{"delta": {"reasoning_content": "chain"}}]}),
            sse({"choices": [{"delta": {"content": "visible"}}]}),
            sse({"choices": [{"finish_reason": "stop", "delta": {}}], "usage": {"completion_tokens": 4}}),
            b"data: [DONE]\n\n",
        ]
        handler = FakeHandler()

        ok = claude_any.stream_openai_chat_to_anthropic_sse(
            handler,
            io.BytesIO(b"".join(chunks)),
            "deepseek-v4-flash-free",
            "opencode",
            source_body={"messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertTrue(ok)
        output = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('"type": "thinking"', output)
        self.assertIn('"type": "thinking_delta"', output)
        self.assertIn("private ", output)
        self.assertIn("chain", output)
        self.assertIn('"type": "signature_delta"', output)
        self.assertIn('"type": "text_delta"', output)
        self.assertIn("visible", output)


if __name__ == "__main__":
    unittest.main()
