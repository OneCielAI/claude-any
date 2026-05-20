import json
import os
import subprocess
import sys
import textwrap
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

    def test_channel_wake_prompt_contains_routing_context(self):
        prompt = claude_any.format_channel_wake_prompt(
            {
                "id": 9,
                "channel": "room_phase1sim",
                "sender_id": "robert",
                "thread_id": "root",
                "message": "please review the latest update",
                "meta": {"room_id": "room_phase1sim"},
            }
        )
        self.assertIn("claude-any external channel message", prompt)
        self.assertIn("from=robert", prompt)
        self.assertIn("id=9", prompt)
        self.assertIn("please review the latest update", prompt)
        self.assertNotIn("\n", prompt)

    def test_inject_pending_channel_messages_writes_prompt_to_child_stdin(self):
        messages = [
            {
                "id": 2,
                "channel": "room",
                "sender_id": "agent",
                "message": "wake up",
                "meta": {},
            }
        ]
        with (
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "_write_fd_all") as write_all,
            mock.patch.object(claude_any, "router_log"),
        ):
            last_id = claude_any._inject_pending_channel_messages(99, 1)
        self.assertEqual(2, last_id)
        self.assertIn(b"wake up", write_all.call_args.args[1])
        self.assertTrue(write_all.call_args.args[1].startswith(b"\x15"))
        self.assertTrue(write_all.call_args.args[1].endswith(b"\r"))

    def test_inject_pending_channel_messages_batches_and_ignores_connection_noise(self):
        messages = [
            {"id": 1, "channel": "ai-net", "sender_id": "ai-net", "message": "ai-net.ws.connected", "meta": {}},
            {"id": 2, "channel": "ai-net", "sender_id": "robert", "message": "hello Sarah", "meta": {"room_id": "ai-net"}},
            {"id": 3, "channel": "ai-net", "sender_id": "samuel", "message": "status please", "meta": {"room_id": "ai-net"}},
        ]
        with (
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "_write_fd_all") as write_all,
            mock.patch.object(claude_any, "router_log"),
        ):
            last_id = claude_any._inject_pending_channel_messages(99, 0)
        self.assertEqual(3, last_id)
        payload = write_all.call_args.args[1]
        self.assertIn(b"external channel messages", payload)
        self.assertIn(b"hello Sarah", payload)
        self.assertIn(b"status please", payload)
        self.assertNotIn(b"ai-net.ws.connected", payload)

    def test_router_channel_mcp_notification_wraps_chat_message(self):
        notification = claude_any._channel_mcp_notification(
            {
                "id": 7,
                "channel": "room_phase1sim",
                "sender_id": "robert",
                "thread_id": "root",
                "message": "hello Sarah",
                "meta": {"room_id": "room_phase1sim"},
            }
        )
        self.assertEqual("notifications/claude/channel", notification["method"])
        self.assertIn("hello Sarah", notification["params"]["content"])
        self.assertEqual(7, notification["params"]["meta"]["claude_any_message_id"])

    def test_mcp_proxy_notification_maps_to_chat_payload(self):
        payload = claude_any._mcp_proxy_notification_payload(
            "ai-net",
            {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {
                    "data": {
                        "room_id": "room_phase1sim",
                        "payload": {"message": {"content": "wake from server"}},
                        "sender_id": "robert",
                    }
                },
            },
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual("wake from server", payload["message"])
        self.assertEqual("robert", payload["sender_id"])
        self.assertEqual("room_phase1sim", payload["channel"])
        self.assertEqual("notifications/message", payload["meta"]["mcp_method"])

    def test_mcp_proxy_observer_reads_content_length_framed_notification(self):
        body = __import__("json").dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {
                    "data": {
                        "room_id": "room_phase1sim",
                        "payload": {"message": {"content": "wake from framed mcp"}},
                        "sender_id": "robert",
                    }
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        with mock.patch.object(claude_any, "append_chat_message", return_value={"id": 11}) as append:
            observer = claude_any._McpStdoutObserver("ai-net")
            observer.feed(frame[:10])
            observer.feed(frame[10:])
        append.assert_called_once()
        payload = append.call_args.args[0]
        self.assertEqual("wake from framed mcp", payload["message"])
        self.assertEqual("robert", payload["sender_id"])
        self.assertEqual("room_phase1sim", payload["channel"])

    def test_mcp_proxy_observer_accepts_content_type_before_length(self):
        body = b'{"jsonrpc":"2.0","method":"notifications/message","params":{"content":"typed frame"}}'
        frame = b"Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        with mock.patch.object(claude_any, "append_chat_message", return_value={"id": 13}) as append:
            observer = claude_any._McpStdoutObserver("generic")
            observer.feed(frame)
        append.assert_called_once()
        self.assertEqual("typed frame", append.call_args.args[0]["message"])

    def test_mcp_proxy_observer_reads_jsonl_notification(self):
        line = (
            __import__("json").dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {"content": "wake from json line", "room_id": "room"},
                }
            )
            + "\n"
        ).encode("utf-8")
        with mock.patch.object(claude_any, "append_chat_message", return_value={"id": 12}) as append:
            observer = claude_any._McpStdoutObserver("generic")
            observer.feed(line)
        append.assert_called_once()
        self.assertEqual("wake from json line", append.call_args.args[0]["message"])

    def test_mcp_proxy_subcommand_round_trips_stdio_frame(self):
        with tempfile.TemporaryDirectory(prefix="ca-mcp-test-") as td:
            root = Path(td)
            server = root / "fake_server.py"
            server.write_text(
                textwrap.dedent(
                    r'''
                    import json
                    import sys

                    def read_frame():
                        header = b""
                        while b"\r\n\r\n" not in header:
                            chunk = sys.stdin.buffer.read(1)
                            if not chunk:
                                return None
                            header += chunk
                        length = 0
                        for line in header.decode("ascii", "replace").split("\r\n"):
                            if line.lower().startswith("content-length:"):
                                length = int(line.split(":", 1)[1].strip())
                        return sys.stdin.buffer.read(length)

                    def write_frame(payload):
                        body = json.dumps(payload).encode("utf-8")
                        sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
                        sys.stdout.buffer.flush()

                    frame = read_frame()
                    if frame:
                        request = json.loads(frame.decode("utf-8"))
                        write_frame({"jsonrpc": "2.0", "id": request.get("id"), "result": {"protocolVersion": "2024-11-05", "capabilities": {}}})
                        write_frame({"jsonrpc": "2.0", "method": "notifications/message", "params": {"content": "wake from subprocess"}})
                    '''
                ),
                encoding="utf-8",
            )
            config = root / "server.json"
            config.write_text(json.dumps({"command": sys.executable, "args": [str(server)]}), encoding="utf-8")
            request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            body = json.dumps(request).encode("utf-8")
            input_frame = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
            env = os.environ.copy()
            env["CLAUDE_ANY_CONFIG_DIR"] = str(root / "config")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(claude_any.__file__).resolve()),
                    "mcp-proxy",
                    "--server-name",
                    "fake",
                    "--server-config",
                    str(config),
                ],
                input=input_frame,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=5,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr.decode("utf-8", errors="replace"))
            self.assertIn(b"Content-Length:", proc.stdout)
            self.assertIn(b'"id": 1', proc.stdout)
            chat_log = root / "config" / "chat-messages.jsonl"
            self.assertTrue(chat_log.exists())
            self.assertIn("wake from subprocess", chat_log.read_text(encoding="utf-8"))

    def test_channel_mcp_config_points_to_router_sse(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "channel-mcp.json"
            with mock.patch.object(claude_any, "CHANNEL_MCP_CONFIG", path):
                written = claude_any.write_channel_mcp_config()
            data = __import__("json").loads(written.read_text(encoding="utf-8"))
        self.assertEqual("sse", data["mcpServers"]["claude-any-router"]["type"])
        self.assertTrue(data["mcpServers"]["claude-any-router"]["url"].endswith("/ca/mcp/sse"))


if __name__ == "__main__":
    unittest.main()
