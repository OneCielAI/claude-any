import unittest
from unittest import mock

import claude_any


class LMStudioProviderTests(unittest.TestCase):
    def test_provider_is_registered_with_local_defaults(self):
        for alias in ("lm-studio", "lmstudio", "lm"):
            self.assertEqual("lm-studio", claude_any.PROVIDER_ALIASES[alias])
        self.assertEqual("LM Studio", claude_any.PROVIDER_LABELS["lm-studio"])
        pcfg = claude_any.DEFAULT_CONFIG["providers"]["lm-studio"]
        self.assertEqual("http://127.0.0.1:1234/v1", pcfg["base_url"])
        self.assertEqual("local-model", pcfg["current_model"])
        self.assertFalse(claude_any.provider_native_compat_enabled("lm-studio", pcfg))

    def test_default_base_url_points_to_lm_studio_openai_api(self):
        self.assertEqual("http://127.0.0.1:1234/v1", claude_any.default_base_url("lm-studio"))
        self.assertEqual(
            "http://127.0.0.1:1234/v1/chat/completions",
            claude_any.join_url(claude_any.default_base_url("lm-studio"), "/v1/chat/completions"),
        )
        self.assertEqual(
            "http://127.0.0.1:1234/v1/models",
            claude_any.join_url(claude_any.default_base_url("lm-studio"), "/v1/models"),
        )

    def test_headers_do_not_send_dummy_auth_for_local_server(self):
        headers = claude_any.provider_headers("lm-studio", {"api_key": ""})
        self.assertNotIn("authorization", headers)
        self.assertNotIn("x-api-key", headers)

        keyed = claude_any.provider_headers("lm-studio", {"api_key": "lm-key"})
        self.assertEqual("Bearer lm-key", keyed["authorization"])
        self.assertEqual("lm-key", keyed["x-api-key"])

    def test_openai_compatible_request_for_lm_studio(self):
        body = {
            "model": "claude-any-lm-studio-local-model",
            "max_tokens": 1234,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }
        pcfg = {"context_window": 32768, "temperature": 0.2, "top_p": 0.9}

        request = claude_any.openai_compatible_chat_request("lm-studio", "local-model", body, pcfg, stream=False)

        self.assertEqual("local-model", request["model"])
        self.assertFalse(request["stream"])
        self.assertEqual(1234, request["max_tokens"])
        self.assertEqual(0.2, request["temperature"])
        self.assertEqual(0.9, request["top_p"])
        self.assertTrue(any(message.get("role") == "user" for message in request["messages"]))

    def test_lm_studio_routes_through_openai_compatible_forwarder(self):
        cfg = {
            "current_provider": "lm-studio",
            "providers": {"lm-studio": dict(claude_any.DEFAULT_CONFIG["providers"]["lm-studio"])},
            "router_debug_message_preview_chars": 0,
        }
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
            mock.patch.object(claude_any, "maybe_handle_advisor_request", return_value=False),
            mock.patch.object(claude_any, "dump_request_for_trace"),
            mock.patch.object(claude_any, "forward_openai_compatible_chat") as forward,
        ):
            handler.do_POST()

        forward.assert_called_once()
        self.assertIs(forward.call_args.args[0], handler)
        self.assertEqual("lm-studio", forward.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
