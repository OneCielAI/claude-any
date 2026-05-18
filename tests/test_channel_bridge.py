import unittest
import tempfile
from pathlib import Path
from unittest import mock

import claude_any


class ChannelBridgeTests(unittest.TestCase):
    def test_parse_channel_args_accepts_sse_command(self):
        command, options = claude_any.parse_channel_bridge_args("sse")
        self.assertEqual(command, "sse")
        self.assertEqual(options, {})

    def test_parse_channel_send_quoted_message(self):
        command, options = claude_any.parse_channel_bridge_args('send channel=default to=all message="hello agents"')
        self.assertEqual(command, "send")
        self.assertEqual(options["channel"], "default")
        self.assertEqual(options["to"], "all")
        self.assertEqual(options["message"], "hello agents")

    def test_sse_payload_maps_mcp_notification_to_chat_payload(self):
        payload = claude_any._sse_payload_to_chat_payload(
            '{"method":"notifications/claude/channel","params":{"content":"hello","meta":{"room_id":"room_phase1sim","thread_id":"root"}}}',
            "message",
            {"name": "ai-net", "channel": "default", "sender_id": "ai-net", "recipient": "claude"},
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["kind"], "channel")
        self.assertEqual(payload["channel"], "default")
        self.assertEqual(payload["sender_id"], "ai-net")
        self.assertEqual(payload["recipients"], "claude")
        self.assertEqual(payload["thread_id"], "root")
        self.assertEqual(payload["meta"]["room_id"], "room_phase1sim")

    def test_sse_payload_ignores_done_marker(self):
        self.assertIsNone(claude_any._sse_payload_to_chat_payload("[DONE]", "message", {"name": "x"}))

    def test_sse_payload_ignores_mcp_endpoint_event(self):
        self.assertIsNone(claude_any._sse_payload_to_chat_payload("/messages?session=abc", "endpoint", {"name": "x"}))

    def test_sse_payload_honors_event_filter(self):
        payload = claude_any._sse_payload_to_chat_payload(
            '{"method":"notifications/message","params":{"content":"visible"}}',
            "message",
            {"name": "ai-net", "event_filter": ["notifications/message"]},
        )
        self.assertIsNotNone(payload)
        hidden = claude_any._sse_payload_to_chat_payload(
            '{"method":"tools/list","params":{"content":"hidden"}}',
            "message",
            {"name": "ai-net", "event_filter": ["notifications/message"]},
        )
        self.assertIsNone(hidden)

    def test_sse_payload_maps_nested_ai_net_event(self):
        payload = claude_any._sse_payload_to_chat_payload(
            '{"method":"notifications/message","params":{"data":{"type":"message.created","room_id":"room_phase1sim","payload":{"message":{"content":"hello from ai-net"},"sender_id":"agent_a"}}}}',
            "message",
            {"name": "ai-net", "channel": "default", "sender_id": "ai-net", "recipient": "claude", "event_filter": ["notifications/message"]},
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["message"], "hello from ai-net")
        self.assertEqual(payload["sender_id"], "agent_a")
        self.assertEqual(payload["meta"]["room_id"], "room_phase1sim")

    def test_read_channel_matches_room_id_alias(self):
        messages = [
            {"id": 1, "channel": "default", "recipients": ["all"], "sender_id": "agent", "message": "hello", "meta": {"room_id": "room_phase1sim"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chat-messages.jsonl"
            path.write_text("\n".join(__import__("json").dumps(item) for item in messages), encoding="utf-8")
            with mock.patch.object(claude_any, "CHAT_MESSAGES_PATH", path):
                found = claude_any.read_chat_messages(0, "room_phase1sim", None, 10)
        self.assertEqual(1, len(found))
        self.assertEqual("hello", found[0]["message"])

    def test_mcp_endpoint_event_initializes_sse_session(self):
        name = "unit-mcp"
        original = dict(claude_any._CHANNEL_SSE_CONNECTIONS)
        try:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS[name] = {
                "name": name,
                "url": "http://example.test/sse",
                "headers": {"Authorization": "Bearer test"},
                "running": True,
                "mcp_enabled": True,
                "mcp_initialized": False,
                "mcp_protocol_version": "2024-11-05",
                "mcp_timeout_seconds": 20.0,
            }
            with mock.patch.object(claude_any, "_mcp_sse_post_json", return_value={"ok": True}) as post:
                claude_any._channel_sse_dispatch(name, "endpoint", ["/messages?session=abc"])
            state = claude_any._CHANNEL_SSE_CONNECTIONS[name]
            self.assertEqual("http://example.test/messages?session=abc", state["mcp_endpoint"])
            self.assertTrue(state["mcp_initialized"])
            self.assertEqual(2, post.call_count)
            self.assertEqual("initialize", post.call_args_list[0].args[2]["method"])
            self.assertEqual("notifications/initialized", post.call_args_list[1].args[2]["method"])
        finally:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS.update(original)


if __name__ == "__main__":
    unittest.main()
