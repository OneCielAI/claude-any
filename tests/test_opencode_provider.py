import copy
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


if __name__ == "__main__":
    unittest.main()
