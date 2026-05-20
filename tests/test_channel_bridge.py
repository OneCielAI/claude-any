import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import unittest
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
        self.assertEqual(payload["meta"]["mcp_method"], "notifications/claude/channel")
        self.assertEqual(payload["meta"]["sse_json"]["params"]["meta"]["room_id"], "room_phase1sim")

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
        self.assertEqual(payload["meta"]["mcp_method"], "notifications/message")
        self.assertEqual(payload["meta"]["sse_json"]["params"]["data"]["type"], "message.created")

    def test_sse_payload_preserves_event_id_and_redacts_sensitive_metadata(self):
        payload = claude_any._sse_payload_to_chat_payload(
            '{"method":"notifications/message","params":{"data":{"room_id":"room_phase1sim","cursor":"123-0","api_key":"secret-value","payload":{"message":{"content":"hello with metadata"}}}}}',
            "message",
            {"name": "ai-net", "channel": "default"},
            event_id="evt-42",
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        meta = payload["meta"]
        self.assertEqual("evt-42", meta["sse_id"])
        self.assertEqual("123-0", meta["cursor"])
        self.assertEqual("[redacted]", meta["sse_json"]["params"]["data"]["api_key"])

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

    def test_start_channel_sse_connection_receives_stream_message(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    b'id: evt-1\n'
                    b'event: message\n'
                    b'data: {"method":"notifications/message","params":{"content":"hello over sse","room_id":"room_phase1sim"}}\n\n'
                )
                self.wfile.flush()
                time.sleep(0.05)

        original_connections = dict(claude_any._CHANNEL_SSE_CONNECTIONS)
        old_next = claude_any._CHAT_NEXT_ID
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chat_log = root / "chat-messages.jsonl"
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/events"
                with (
                    mock.patch.object(claude_any, "CONFIG_DIR", root),
                    mock.patch.object(claude_any, "CHAT_MESSAGES_PATH", chat_log),
                    mock.patch.object(claude_any, "_CHAT_NEXT_ID", None),
                ):
                    claude_any.start_channel_sse_connection(
                        {
                            "name": "unit-sse",
                            "url": url,
                            "channel": "unit",
                            "retry_seconds": 60,
                            "read_timeout_seconds": 5,
                        }
                    )
                    deadline = time.time() + 2
                    while time.time() < deadline:
                        if chat_log.exists() and "hello over sse" in chat_log.read_text(encoding="utf-8"):
                            break
                        time.sleep(0.02)
                    self.assertTrue(chat_log.exists())
                    text = chat_log.read_text(encoding="utf-8")
                    self.assertIn("hello over sse", text)
                    self.assertIn("evt-1", text)
                    claude_any.stop_channel_sse_connection("unit-sse")
            finally:
                server.shutdown()
                server.server_close()
                claude_any._CHANNEL_SSE_CONNECTIONS.clear()
                claude_any._CHANNEL_SSE_CONNECTIONS.update(original_connections)
                claude_any._CHAT_NEXT_ID = old_next

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
        self.assertIn("metadata=", prompt)
        self.assertIn("room_phase1sim", prompt)
        self.assertNotIn("\n", prompt)

    def test_channel_wake_enter_bytes_can_be_overridden(self):
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_WAKE_ENTER": "cr"}):
            self.assertTrue(claude_any._channel_wake_input_bytes("wake").endswith(b"\r"))
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_WAKE_ENTER": "crlf"}):
            self.assertTrue(claude_any._channel_wake_input_bytes("wake").endswith(b"\r\n"))

    def test_channel_enter_bytes_from_user_input_tracks_observed_submit_key(self):
        self.assertEqual(b"\n", claude_any._channel_enter_bytes_from_user_input(b"\n"))
        self.assertEqual(b"\r", claude_any._channel_enter_bytes_from_user_input(b"\r"))
        self.assertEqual(b"\r\n", claude_any._channel_enter_bytes_from_user_input(b"hello\r\n"))
        self.assertIsNone(claude_any._channel_enter_bytes_from_user_input(b"abc"))

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
        self.assertTrue(write_all.call_args.args[1].endswith(b"\n"))

        with (
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "_write_fd_all") as write_all_cr,
            mock.patch.object(claude_any, "router_log"),
        ):
            claude_any._inject_pending_channel_messages(99, 1, b"\r")
        self.assertTrue(write_all_cr.call_args.args[1].endswith(b"\r"))

    def test_inject_pending_channel_messages_batches_and_ignores_connection_noise(self):
        messages = [
            {"id": 1, "channel": "ai-net", "sender_id": "ai-net", "message": "ai-net.ws.connected", "meta": {}},
            {"id": 2, "channel": "ai-net", "sender_id": "robert", "message": "hello Sarah", "meta": {"room_id": "ai-net"}},
            {"id": 3, "channel": "ai-net", "sender_id": "samuel", "message": "status please", "meta": {"room_id": "ai-net"}},
        ]
        with (
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "_write_fd_all") as write_all,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            last_id = claude_any._inject_pending_channel_messages(99, 0)
        self.assertEqual(3, last_id)
        payload = write_all.call_args.args[1]
        self.assertIn(b"external channel messages", payload)
        self.assertIn(b"hello Sarah", payload)
        self.assertIn(b"status please", payload)
        self.assertNotIn(b"ai-net.ws.connected", payload)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_stdin_proxy_skipped_noise" in item for item in log_messages))
        self.assertTrue(any("channel_stdin_proxy_injected" in item and "message_ids=2,3" in item and "enter=lf" in item for item in log_messages))

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
        self.assertEqual("7", notification["params"]["meta"]["claude_any_message_id"])

    def test_router_channel_mcp_notification_stringifies_meta_for_native_schema(self):
        notification = claude_any._channel_mcp_notification(
            {
                "id": 8,
                "channel": "room",
                "sender_id": "agent",
                "thread_id": "root",
                "message": "native wake",
                "kind": "message",
                "meta": {"room_id": "room", "mcp_json": {"method": "notifications/message"}, "count": 3},
            }
        )
        meta = notification["params"]["meta"]
        self.assertTrue(all(isinstance(key, str) and isinstance(value, str) for key, value in meta.items()))
        self.assertEqual("8", meta["claude_any_message_id"])
        self.assertEqual("3", meta["count"])
        self.assertIn("notifications/message", meta["mcp_json"])
        self.assertIn("mcp_json", meta["claude_any_meta_json"])

    def test_channel_mcp_capabilities_declare_native_channel(self):
        capabilities = claude_any._channel_mcp_capabilities()
        self.assertIn("tools", capabilities)
        self.assertIn("claude/channel", capabilities["experimental"])

    def test_channel_mcp_sse_headers_keep_connection_alive(self):
        class FakeHandler:
            def __init__(self):
                self.status = None
                self.headers = []
                self.ended = False

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers.append((name.lower(), value))

            def end_headers(self):
                self.ended = True

        handler = FakeHandler()
        claude_any._send_channel_mcp_sse_headers(handler)
        headers = dict(handler.headers)
        self.assertEqual(200, handler.status)
        self.assertEqual("text/event-stream", headers["content-type"])
        self.assertEqual("keep-alive", headers["connection"])
        self.assertEqual("no", headers["x-accel-buffering"])
        self.assertTrue(handler.ended)

    def test_channel_mcp_rpc_responses_are_queued_for_sse(self):
        session = "session-rpc"
        with claude_any._CHANNEL_MCP_LOCK:
            original = dict(claude_any._CHANNEL_MCP_SESSIONS)
            claude_any._CHANNEL_MCP_SESSIONS.clear()
            claude_any._CHANNEL_MCP_SESSIONS[session] = {"outbox": []}
        try:
            response = claude_any._channel_mcp_initialize_response(1, "2025-11-25")
            self.assertTrue(claude_any._channel_mcp_enqueue(session, response))
            outbox = claude_any._channel_mcp_take_outbox(session)
            self.assertEqual([response], outbox)
            self.assertEqual([], claude_any._channel_mcp_take_outbox(session))
            self.assertEqual("claude-any-router", outbox[0]["result"]["serverInfo"]["name"])
            self.assertIn("claude/channel", outbox[0]["result"]["capabilities"]["experimental"])
        finally:
            with claude_any._CHANNEL_MCP_LOCK:
                claude_any._CHANNEL_MCP_SESSIONS.clear()
                claude_any._CHANNEL_MCP_SESSIONS.update(original)

    def test_channel_mcp_enqueue_rejects_missing_session(self):
        self.assertFalse(claude_any._channel_mcp_enqueue("missing-session", {"jsonrpc": "2.0"}))

    def test_channel_mcp_notifications_ignore_transport_noise(self):
        messages = [
            {"id": 1, "channel": "ai-net", "sender_id": "ai-net", "message": "ai-net.ws.connected", "meta": {}},
            {"id": 2, "channel": "ai-net", "sender_id": "robert", "message": "hello Sarah", "meta": {"room_id": "ai-net"}},
        ]
        with mock.patch.object(claude_any, "router_log") as router_log:
            last_id, events = claude_any._channel_mcp_notifications_for_messages(messages, "session-1")
        self.assertEqual(2, last_id)
        self.assertEqual(1, len(events))
        self.assertEqual(2, events[0][0])
        self.assertIn("hello Sarah", events[0][1]["params"]["content"])
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_mcp_skipped_noise" in item and "transport_connected" in item for item in log_messages))
        self.assertTrue(any("channel_mcp_notification_sent" in item and "message_id=2" in item for item in log_messages))

    def test_channel_mcp_cursor_initializes_at_current_tail(self):
        with tempfile.TemporaryDirectory(prefix="ca-channel-cursor-") as td:
            root = Path(td)
            cursor_path = root / "cursor.json"
            with (
                mock.patch.object(claude_any, "CONFIG_DIR", root),
                mock.patch.object(claude_any, "CHANNEL_MCP_CURSOR_PATH", cursor_path),
                mock.patch.object(claude_any, "_CHANNEL_MCP_CURSOR_LAST_ID", None),
                mock.patch.object(claude_any, "_chat_init_next_id", return_value=42),
            ):
                last_id = claude_any._channel_mcp_ensure_cursor_initialized()
                self.assertEqual(41, last_id)
                self.assertEqual({"last_id": 41}, json.loads(cursor_path.read_text(encoding="utf-8")))

    def test_channel_mcp_cursor_persists_across_reconnects(self):
        with tempfile.TemporaryDirectory(prefix="ca-channel-cursor-") as td:
            root = Path(td)
            cursor_path = root / "cursor.json"
            cursor_path.write_text('{"last_id":9}\n', encoding="utf-8")
            with (
                mock.patch.object(claude_any, "CONFIG_DIR", root),
                mock.patch.object(claude_any, "CHANNEL_MCP_CURSOR_PATH", cursor_path),
                mock.patch.object(claude_any, "_CHANNEL_MCP_CURSOR_LAST_ID", None),
            ):
                self.assertEqual(9, claude_any._channel_mcp_ensure_cursor_initialized())
                claude_any._channel_mcp_update_cursor(12)
                self.assertEqual(12, claude_any._channel_mcp_ensure_cursor_initialized())
                self.assertEqual({"last_id": 12}, json.loads(cursor_path.read_text(encoding="utf-8")))

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
        self.assertEqual("wake from server", payload["meta"]["mcp_json"]["params"]["data"]["payload"]["message"]["content"])

    def test_mcp_proxy_observer_deduplicates_generic_and_native_channel_notifications(self):
        generic = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"content": "hello team", "room_id": "room_phase1sim", "sender_id": "robert", "thread_id": "root"},
        }
        native = {
            "jsonrpc": "2.0",
            "method": "notifications/claude/channel",
            "params": {"content": "hello team", "room_id": "room_phase1sim", "sender_id": "robert", "thread_id": "root"},
        }
        claude_any._MCP_NOTIFICATION_DEDUP_RECENT.clear()
        try:
            with (
                mock.patch.object(claude_any, "append_chat_message", return_value={"id": 21}) as append,
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                claude_any._mcp_proxy_observe_json_message("ai-net", generic)
                claude_any._mcp_proxy_observe_json_message("ai-net", native)
            append.assert_called_once()
            log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
            self.assertTrue(any("mcp_proxy_notification_skipped_duplicate" in item for item in log_messages))
        finally:
            claude_any._MCP_NOTIFICATION_DEDUP_RECENT.clear()

    def test_mcp_proxy_observer_allows_repeated_same_method_notifications(self):
        message = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"content": "repeatable alert", "room_id": "room_phase1sim", "sender_id": "robert"},
        }
        claude_any._MCP_NOTIFICATION_DEDUP_RECENT.clear()
        try:
            with mock.patch.object(claude_any, "append_chat_message", return_value={"id": 22}) as append:
                claude_any._mcp_proxy_observe_json_message("ai-net", message)
                claude_any._mcp_proxy_observe_json_message("ai-net", message)
            self.assertEqual(2, append.call_count)
        finally:
            claude_any._MCP_NOTIFICATION_DEDUP_RECENT.clear()

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
            with (
                mock.patch.object(claude_any, "CHANNEL_MCP_CONFIG", path),
                mock.patch.object(claude_any, "_channel_mcp_ensure_cursor_initialized", return_value=0),
            ):
                written = claude_any.write_channel_mcp_config()
            data = __import__("json").loads(written.read_text(encoding="utf-8"))
        self.assertEqual("sse", data["mcpServers"]["claude-any-router"]["type"])
        self.assertTrue(data["mcpServers"]["claude-any-router"]["url"].endswith("/ca/mcp/sse"))


if __name__ == "__main__":
    unittest.main()
