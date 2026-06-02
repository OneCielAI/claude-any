import unittest
from unittest import mock

import claude_any


class VllmProviderTests(unittest.TestCase):
    def test_vllm_native_base_url_strips_v1_suffix(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["base_url"] = "http://vllm.local:8000/v1"

        self.assertEqual("http://vllm.local:8000", claude_any.native_anthropic_base_url("vllm", pcfg))

    def test_vllm_native_false_routes_through_openai_compatible_forwarder(self):
        cfg = {
            "current_provider": "vllm",
            "providers": {"vllm": dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])},
            "router_debug_message_preview_chars": 0,
        }
        cfg["providers"]["vllm"]["native_compat"] = False
        handler = object.__new__(claude_any.RouterHandler)
        handler.path = "/v1/messages"
        handler.headers = {"content-length": "2"}
        handler.rfile = mock.Mock()
        handler.rfile.read.return_value = b"{}"

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "reject_external_router_request", return_value=False),
            mock.patch.object(claude_any, "handle_llm_config_post", return_value=False),
            mock.patch.object(claude_any, "handle_channel_mcp_post", return_value=False),
            mock.patch.object(claude_any, "handle_chat_post", return_value=False),
            mock.patch.object(claude_any, "handle_plan_post", return_value=False),
            mock.patch.object(claude_any, "maybe_handle_plan_mode_tool_choice", return_value=False),
            mock.patch.object(claude_any, "filter_blocked_tools", side_effect=lambda _p, _c, b: b),
            mock.patch.object(claude_any, "write_context_usage"),
            mock.patch.object(claude_any, "maybe_handle_router_debug_request", return_value=False),
            mock.patch.object(claude_any, "body_with_pending_channel_messages", side_effect=lambda b: b),
            mock.patch.object(claude_any, "dump_request_for_trace"),
            mock.patch.object(claude_any, "forward_openai_compatible_chat") as forward,
        ):
            handler.do_POST()

        forward.assert_called_once()
        self.assertEqual("vllm", forward.call_args.args[1])

    def test_vllm_compatibility_probe_native_false_uses_chat_completions(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["base_url"] = "http://vllm.local:8000/v1"
        pcfg["native_compat"] = False

        url, req_body, _headers = claude_any.compatibility_api_key_probe_request(
            "vllm",
            pcfg,
            "test-model",
            {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
        )

        self.assertEqual("http://vllm.local:8000/v1/chat/completions", url)
        self.assertEqual("test-model", req_body["model"])

    def test_set_base_url_autodetects_openai_only_endpoint(self):
        cfg = {
            "current_provider": "vllm",
            "providers": {"vllm": dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])},
        }

        def route_exists(url, _headers, timeout=1.5):
            if url.endswith("/v1/messages"):
                return False
            if url.endswith("/v1/chat/completions"):
                return True
            return None

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config") as save,
            mock.patch.object(claude_any, "clear_model_cache"),
            mock.patch.object(claude_any, "endpoint_route_exists", side_effect=route_exists),
        ):
            lines = claude_any.set_base_url_config("vllm", "http://vllm.local:8000/v1")

        self.assertFalse(cfg["providers"]["vllm"]["native_compat"])
        self.assertTrue(any("Native compatibility disabled" in line for line in lines))
        save.assert_called_once()

    def test_set_base_url_keeps_anthropic_default_when_detection_is_inconclusive(self):
        cfg = {
            "current_provider": "vllm",
            "providers": {"vllm": dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])},
        }
        cfg["providers"]["vllm"]["native_compat"] = False

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config"),
            mock.patch.object(claude_any, "clear_model_cache"),
            mock.patch.object(claude_any, "endpoint_route_exists", return_value=None),
        ):
            lines = claude_any.set_base_url_config("vllm", "http://vllm.local:9000")

        self.assertTrue(cfg["providers"]["vllm"]["native_compat"])
        self.assertTrue(any("Anthropic default" in line for line in lines))

    def test_long_context_128k_preset_configures_vllm_range(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])

        lines = claude_any.apply_llm_preset_to_provider("vllm", pcfg, "long-context-128k", "en")

        self.assertEqual(131072, pcfg["context_window"])
        self.assertEqual(8192, pcfg["context_reserve_tokens"])
        self.assertEqual(8192, pcfg["max_output_tokens"])
        self.assertEqual("long-context-128k", pcfg["llm_preset"])
        self.assertTrue(any("Long context 128K" in line for line in lines))

    def test_long_context_128k_preset_is_visible_even_when_capacity_lower(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["max_model_len"] = 65536

        rows, values = claude_any.llm_preset_panel_rows("vllm", pcfg, "en")

        self.assertIn("long-context-128k", values)
        row = rows[values.index("long-context-128k")]
        self.assertIn("Long context 128K", row)
        self.assertIn("requires 128K", row)
        self.assertIn("server", row)

    def test_stored_preset_status_is_preserved_even_when_capacity_lower(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["llm_preset"] = "long-context-128k"
        pcfg["max_model_len"] = 65536

        self.assertEqual("long-context-128k", claude_any.applied_preset_id("vllm", pcfg))

    def test_qwen36_35b_does_not_inherit_27b_65k_hint(self):
        self.assertIsNone(claude_any.model_context_hint_from_model_id("qwen36-35b-a3b-mtp-nvfp4"))

    def test_vllm_runtime_context_limit_overrides_model_hint(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["current_model"] = "qwen36-35b-a3b-mtp-nvfp4"

        with mock.patch.object(claude_any, "upstream_model_context_limit", return_value=131072):
            self.assertEqual(131072, claude_any.provider_model_context_capacity("vllm", pcfg))
            claude_any.apply_llm_preset_to_provider("vllm", pcfg, "long-context-128k", "en")

        self.assertEqual(131072, pcfg["context_window"])

    def test_vllm_saved_max_model_len_overrides_model_hint_when_runtime_unavailable(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["vllm"])
        pcfg["current_model"] = "qwen36-35b-a3b-mtp-nvfp4"
        pcfg["max_model_len"] = 131072

        with mock.patch.object(claude_any, "upstream_model_context_limit", return_value=None):
            self.assertEqual(131072, claude_any.provider_model_context_capacity("vllm", pcfg))
            claude_any.apply_llm_preset_to_provider("vllm", pcfg, "long-context-128k", "en")

        self.assertEqual(131072, pcfg["context_window"])

    def test_long_context_128k_preset_configures_ollama_range(self):
        pcfg = dict(claude_any.DEFAULT_CONFIG["providers"]["ollama-cloud"])

        lines = claude_any.apply_llm_preset_to_provider(
            "ollama-cloud",
            pcfg,
            "long-context-128k",
            "en",
            sync_ollama_context=False,
        )

        self.assertEqual("auto", pcfg["num_ctx"])
        self.assertEqual(65536, pcfg["num_ctx_min"])
        self.assertEqual(131072, pcfg["num_ctx_max"])
        self.assertEqual(8192, pcfg["ollama_options"]["num_predict"])
        self.assertEqual("long-context-128k", pcfg["llm_preset"])
        self.assertTrue(any("Long context 128K" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
