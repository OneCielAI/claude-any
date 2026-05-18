import unittest
from unittest.mock import patch

import claude_any


class RouterDebugTests(unittest.TestCase):
    def test_router_debug_defaults_to_local_bind(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(claude_any.router_debug_external_access_enabled({}))
            self.assertEqual("127.0.0.1", claude_any.router_bind_host({}))

    def test_router_debug_enables_external_bind(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = {"router_debug_external_access": True, "router_debug_external_access_confirmed": True}

            self.assertTrue(claude_any.router_debug_external_access_enabled(cfg))
            self.assertEqual("0.0.0.0", claude_any.router_bind_host(cfg))

    def test_unconfirmed_router_debug_true_is_treated_as_off(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = {"router_debug_external_access": True}

            self.assertFalse(claude_any.router_debug_external_access_enabled(cfg))
            self.assertEqual("127.0.0.1", claude_any.router_bind_host(cfg))

    def test_bind_host_environment_still_overrides_debug_setting(self):
        with patch.dict("os.environ", {"CLAUDE_ANY_ROUTER_BIND_HOST": "192.0.2.10"}, clear=True):
            self.assertEqual("192.0.2.10", claude_any.router_bind_host({"router_debug_external_access": False}))

    def test_router_debug_slash_value_parsing(self):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "CLAUDE_ANY_ROUTER_DEBUG_ACCESS\n\nValue: on"}],
                }
            ]
        }

        self.assertTrue(claude_any.is_router_debug_request(body))
        self.assertEqual("on", claude_any.router_debug_value_from_body(body))

    def test_router_debug_slash_without_argument_toggles(self):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "CLAUDE_ANY_ROUTER_DEBUG_ACCESS\n\nValue: "}],
                }
            ]
        }

        self.assertEqual("toggle", claude_any.router_debug_value_from_body(body))

    def test_router_event_message_preview_defaults_to_off(self):
        body = {"messages": [{"role": "user", "content": "secret prompt"}]}

        self.assertEqual({}, claude_any.router_event_message_preview(body, {"router_debug_message_preview_chars": 0}))

    def test_router_event_message_preview_truncates_latest_user_text(self):
        body = {"messages": [{"role": "user", "content": "hello\nworld side question"}]}

        preview = claude_any.router_event_message_preview(body, {"router_debug_message_preview_chars": 11})

        self.assertEqual(11, preview["message_preview_chars"])
        self.assertEqual("hello world", preview["message_preview"])
        self.assertTrue(preview["message_preview_truncated"])


if __name__ == "__main__":
    unittest.main()
