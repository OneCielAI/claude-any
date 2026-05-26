import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import unittest
import tempfile
import urllib.parse
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
        self.assertEqual(payload["channel"], "room_phase1sim")
        self.assertEqual(payload["sender_id"], "ai-net")
        self.assertEqual(payload["recipients"], "claude")
        self.assertEqual(payload["thread_id"], "root")
        self.assertEqual(payload["visibility"], "user")
        self.assertIn("llm", payload["delivery"])
        self.assertEqual(payload["meta"]["room_id"], "room_phase1sim")
        self.assertEqual(payload["meta"]["mcp_method"], "notifications/claude/channel")
        self.assertEqual(payload["meta"]["sse_json"]["params"]["meta"]["room_id"], "room_phase1sim")

    def test_sse_payload_ignores_done_marker(self):
        self.assertIsNone(claude_any._sse_payload_to_chat_payload("[DONE]", "message", {"name": "x"}))

    def test_sse_payload_ignores_jsonrpc_control_messages(self):
        self.assertIsNone(
            claude_any._sse_payload_to_chat_payload(
                '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
                "message",
                {"name": "x"},
            )
        )

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
        self.assertEqual(payload["channel"], "room_phase1sim")
        self.assertEqual(payload["meta"]["room_id"], "room_phase1sim")
        self.assertEqual(payload["meta"]["mcp_method"], "notifications/message")
        self.assertEqual(payload["meta"]["sse_json"]["params"]["data"]["type"], "message.created")

    def test_sse_payload_prefers_nested_message_over_generic_notification_content(self):
        payload = claude_any._sse_payload_to_chat_payload(
            json.dumps(
                {
                    "method": "notifications/message",
                    "params": {
                        "content": "New message from Sarah",
                        "data": {
                            "type": "message.created",
                            "room_id": "room_4pyr8vvwm2cd",
                            "payload": {
                                "message": {"content": "Robert 리드님, 매크로 분석 보고서입니다."},
                                "sender_id": "agent_n3wy9gfjmcil",
                            },
                        },
                    },
                },
                ensure_ascii=False,
            ),
            "message",
            {"name": "mcp-ai-net-sse", "channel": "ai-net-sse", "event_filter": ["notifications/message"]},
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual("Robert 리드님, 매크로 분석 보고서입니다.", payload["message"])
        self.assertEqual("agent_n3wy9gfjmcil", payload["sender_id"])
        self.assertEqual("room_4pyr8vvwm2cd", payload["channel"])

    def test_sse_payload_maps_direct_ai_net_chat_object(self):
        payload = claude_any._sse_payload_to_chat_payload(
            json.dumps(
                {
                    "id": 4,
                    "channel": "ai-net",
                    "sender_id": "Sarah",
                    "recipients": ["Robert"],
                    "thread_id": "dm-sarah-robert",
                    "message": "Robert님, DM 확인 부탁드립니다.",
                    "kind": "message",
                    "meta": {
                        "room_id": "dm_robert_sarah",
                        "recipient_id": "Robert",
                    },
                },
                ensure_ascii=False,
            ),
            "message",
            {"name": "mcp-ai-net-sse", "channel": "ai-net-sse", "sender_id": "ai-net-sse", "recipient": "all"},
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual("Robert님, DM 확인 부탁드립니다.", payload["message"])
        self.assertEqual("ai-net", payload["channel"])
        self.assertEqual("Sarah", payload["sender_id"])
        self.assertEqual(["Robert"], payload["recipients"])
        self.assertEqual("dm-sarah-robert", payload["thread_id"])
        self.assertEqual("dm_robert_sarah", payload["meta"]["room_id"])

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

    def test_mcp_endpoint_event_reinitializes_changed_sse_session(self):
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
                "mcp_initialized": True,
                "mcp_endpoint": "http://example.test/messages?session=old",
                "mcp_rpc_results": {"old": {"result": {}}},
                "mcp_protocol_version": "2024-11-05",
                "mcp_timeout_seconds": 20.0,
            }
            with (
                mock.patch.object(claude_any, "_mcp_sse_post_json", return_value={"ok": True}) as post,
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                claude_any._channel_sse_dispatch(name, "endpoint", ["/messages?session=new"])
            state = claude_any._CHANNEL_SSE_CONNECTIONS[name]
            self.assertEqual("http://example.test/messages?session=new", state["mcp_endpoint"])
            self.assertTrue(state["mcp_initialized"])
            self.assertEqual({}, state["mcp_rpc_results"])
            self.assertEqual(2, post.call_count)
            log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
            self.assertTrue(any("channel_sse_mcp_reinitializing" in item for item in log_messages))
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

    def test_sse_reconnect_sends_last_event_id(self):
        seen_headers = []
        second_seen = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                seen_headers.append(self.headers.get("Last-Event-ID"))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if len(seen_headers) == 1:
                    self.wfile.write(
                        b'id: evt-1\n'
                        b'event: message\n'
                        b'data: {"method":"notifications/message","params":{"content":"first"}}\n\n'
                    )
                    self.wfile.flush()
                    return
                second_seen.set()
                self.wfile.write(b': keepalive\n\n')
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
                    mock.patch.object(claude_any, "schedule_channel_direct_llm_delivery"),
                ):
                    claude_any.start_channel_sse_connection(
                        {
                            "name": "unit-sse-resume",
                            "url": url,
                            "channel": "unit",
                            "retry_seconds": 1,
                            "read_timeout_seconds": 5,
                        }
                    )
                    self.assertTrue(second_seen.wait(3))
                    self.assertGreaterEqual(len(seen_headers), 2)
                    self.assertIsNone(seen_headers[0])
                    self.assertEqual("evt-1", seen_headers[1])
                    claude_any.stop_channel_sse_connection("unit-sse-resume")
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
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(claude_any, "_channel_platform_default_enter_bytes", return_value=b"\r\n"),
        ):
            self.assertTrue(claude_any._channel_wake_input_bytes("wake").endswith(b"\r\n"))
            self.assertEqual(b"\r\n", claude_any._channel_wake_enter_bytes("auto"))
            self.assertEqual(b"\r\n", claude_any._channel_wake_enter_bytes("unknown"))
            self.assertEqual(b"\n", claude_any._channel_wake_enter_bytes("lf"))
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_WAKE_ENTER": "cr"}):
            self.assertTrue(claude_any._channel_wake_input_bytes("wake").endswith(b"\r"))
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_WAKE_ENTER": "crlf"}):
            self.assertTrue(claude_any._channel_wake_input_bytes("wake").endswith(b"\r\n"))

    def test_channel_platform_default_enter_bytes_is_submit_safe(self):
        self.assertEqual(b"\r\n", claude_any._channel_platform_default_enter_bytes("linux", "posix"))
        self.assertEqual(b"\r\n", claude_any._channel_platform_default_enter_bytes("darwin", "posix"))
        self.assertEqual(b"\r\n", claude_any._channel_platform_default_enter_bytes("win32", "nt"))
        self.assertEqual(b"\r\n", claude_any._channel_platform_default_enter_bytes("msys", "posix"))

    def test_channel_enter_bytes_from_user_input_tracks_observed_submit_key(self):
        self.assertEqual(b"\n", claude_any._channel_enter_bytes_from_user_input(b"\n"))
        self.assertEqual(b"\r", claude_any._channel_enter_bytes_from_user_input(b"\r"))
        self.assertEqual(b"\r\n", claude_any._channel_enter_bytes_from_user_input(b"hello\r\n"))
        self.assertIsNone(claude_any._channel_enter_bytes_from_user_input(b"abc"))

    def test_channel_synthetic_enter_normalizes_bare_cr_to_crlf(self):
        self.assertEqual(b"\r\n", claude_any._channel_synthetic_enter_bytes_from_user_input(b"\r"))
        self.assertEqual(b"\n", claude_any._channel_synthetic_enter_bytes_from_user_input(b"\n"))
        self.assertEqual(b"\r\n", claude_any._channel_synthetic_enter_bytes_from_user_input(b"hello\r\n"))

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
            mock.patch.object(claude_any, "_channel_platform_default_enter_bytes", return_value=b"\r\n"),
            mock.patch.object(claude_any, "_write_fd_all") as write_all,
            mock.patch.object(claude_any, "router_log"),
        ):
            last_id = claude_any._inject_pending_channel_messages(99, 1)
        self.assertEqual(2, last_id)
        self.assertIn(b"wake up", write_all.call_args.args[1])
        self.assertTrue(write_all.call_args.args[1].startswith(b"\x15"))
        self.assertTrue(write_all.call_args.args[1].endswith(b"\r\n"))

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
            mock.patch.object(claude_any, "_channel_platform_default_enter_bytes", return_value=b"\r\n"),
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
        self.assertTrue(any("channel_stdin_proxy_injected" in item and "message_ids=2,3" in item and "enter=crlf" in item for item in log_messages))

    def test_body_with_pending_channel_messages_injects_llm_context(self):
        body = {"messages": [{"role": "user", "content": "continue"}], "stream": True}
        messages = [
            {"id": 2, "channel": "ai-net", "sender_id": "ai-net", "message": "ai-net.sse.connected", "meta": {}},
            {"id": 3, "channel": "room", "sender_id": "sarah", "message": "Robert, can you check this?", "meta": {"room_id": "room"}},
            {
                "id": 4,
                "channel": "ai-net-sse",
                "sender_id": "ai-net-sse",
                "message": "SSE MCP initialized",
                "meta": {"transport": "sse", "event": "initialized"},
            },
        ]
        with (
            mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
            mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=1),
            mock.patch.object(claude_any, "_channel_llm_write_cursor_locked") as write_cursor,
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            out = claude_any.body_with_pending_channel_messages(body)

        self.assertIsNot(out, body)
        self.assertEqual(2, len(out["messages"]))
        injected = out["messages"][-1]["content"][0]["text"]
        self.assertIn("channel inbox", injected)
        self.assertIn("incoming channel message for the current agent", injected)
        self.assertIn("<< 메시지 >>", injected)
        self.assertIn("실제 업무 메시지", injected)
        self.assertIn("외부 채널/MCP 메시지", injected)
        self.assertIn("로컬 사용자 승인 없이 같은 채널/DM에 답장", injected)
        self.assertIn("답장 여부를 묻고 멈추지 마세요", injected)
        self.assertIn("미래 행동을 약속하는 말만 남기고 턴을 끝내지 마세요", injected)
        self.assertIn("같은 턴에서 필요한 조사/도구 호출/채널 보고까지 수행", injected)
        self.assertIn("실제 결제/투자 실행", injected)
        self.assertIn("Robert, can you check this?", injected)
        self.assertNotIn("ai-net.sse.connected", injected)
        self.assertNotIn("SSE MCP initialized", injected)
        write_cursor.assert_called_with(4)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_injected" in item and "message_ids=3" in item for item in log_messages))
        self.assertTrue(any("channel_llm_inject_skipped" in item and "initialized" in item for item in log_messages))

    def test_ensure_channel_llm_delivery_cursor_preserves_existing_cursor(self):
        with tempfile.TemporaryDirectory() as td:
            cursor_path = Path(td) / "channel-llm-cursor.json"
            cursor_path.write_text('{"last_id":3}\n', encoding="utf-8")
            original_cursor = claude_any._CHANNEL_LLM_CURSOR_LAST_ID
            try:
                claude_any._CHANNEL_LLM_CURSOR_LAST_ID = None
                with (
                    mock.patch.object(claude_any, "CHANNEL_LLM_CURSOR_PATH", cursor_path),
                    mock.patch.object(claude_any, "_chat_init_next_id", return_value=10),
                ):
                    self.assertEqual(3, claude_any.ensure_channel_llm_delivery_cursor_initialized())
            finally:
                claude_any._CHANNEL_LLM_CURSOR_LAST_ID = original_cursor

    def test_body_with_pending_channel_messages_keeps_ai_net_write_tools(self):
        body = {
            "messages": [{"role": "user", "content": "continue"}],
            "stream": True,
            "tools": [
                {"name": "mcp__ai-net-sse__send_dm"},
                {"name": "mcp__ai-net-sse__send_message"},
                {"name": "mcp__ai-net-sse__get_messages"},
                {"name": "mcp__duckduckgo__search"},
            ],
            "tool_choice": {"type": "tool", "name": "mcp__ai-net-sse__send_dm"},
        }
        messages = [
            {"id": 3, "channel": "room", "sender_id": "sarah", "message": "Robert, please read this", "meta": {"room_id": "room"}}
        ]
        with (
            mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
            mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=1),
            mock.patch.object(claude_any, "_channel_llm_write_cursor_locked"),
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            out = claude_any.body_with_pending_channel_messages(body)

        tool_names = [tool.get("name") for tool in out["tools"]]
        self.assertIn("mcp__ai-net-sse__send_dm", tool_names)
        self.assertIn("mcp__ai-net-sse__send_message", tool_names)
        self.assertIn("mcp__ai-net-sse__get_messages", tool_names)
        self.assertIn("mcp__duckduckgo__search", tool_names)
        self.assertEqual({"type": "tool", "name": "mcp__ai-net-sse__send_dm"}, out["tool_choice"])
        self.assertTrue(out["metadata"]["claude_any_channel_injected"])
        self.assertEqual("3", out["metadata"]["claude_any_channel_message_ids"])
        injected = out["messages"][-1]["content"][0]["text"]
        self.assertIn("자율 처리 턴", injected)
        self.assertIn("필요한 읽기/쓰기 도구를 호출", injected)
        self.assertIn("tool_result", injected)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_injected" in item and "message_ids=3" in item for item in log_messages))

    def test_channel_llm_prompt_treats_ai_net_dm_as_agent_task(self):
        prompt = claude_any.format_channel_llm_batch_prompt(
            [
                {
                    "id": 110,
                    "channel": "room_4pyr8vvwm2cd",
                    "sender_id": "agent_2i7ibhkysdk1",
                    "recipients": ["agent_n3wy9gfjmcil"],
                    "message": "Sarah, 추가 매크로 분석 보고서를 보내주세요.",
                    "meta": {"room_id": "room_4pyr8vvwm2cd", "sender": "Robert", "recipient": "Sarah"},
                }
            ]
        )
        self.assertIn("현재 Claude Code 세션의 에이전트에게 도착한 실제 업무 메시지", prompt)
        self.assertIn("외부 채널/MCP 메시지", prompt)
        self.assertIn("DM/업무 지시/상태 확인/컨텍스트 요청", prompt)
        self.assertIn("로컬 사용자 승인 없이 같은 채널/DM에 답장", prompt)
        self.assertIn("답장 여부를 묻고 멈추지 마세요", prompt)
        self.assertIn("진행하겠습니다", prompt)
        self.assertIn("같은 턴에서 필요한 조사/도구 호출/채널 보고까지 수행", prompt)
        self.assertIn("단순 온보딩/인사/중복 테스트 메시지", prompt)
        self.assertIn("Sarah, 추가 매크로 분석 보고서를 보내주세요.", prompt)
        self.assertIn('to=["agent_n3wy9gfjmcil"]', prompt)

    def test_channel_tool_result_context_is_injected_for_remembered_tool_use(self):
        claude_any._CHANNEL_LLM_TOOL_CONTEXT.clear()
        source_body = {
            "metadata": {
                "claude_any_channel_injected": True,
                "claude_any_channel_message_ids": "110",
            },
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "[claude-any channel inbox]\n<< room >> 에서 SSE 메시지가 도착했습니다.\n<< 발신자 >> Sarah\n<< 메시지 >> Robert 리드님, 준비 완료입니다.",
                        }
                    ],
                }
            ],
        }
        assistant_message = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_channel_1",
                    "name": "mcp__ai-net-sse__send_dm",
                    "input": {"to_agent_id": "agent_sarah", "content": "확인했습니다."},
                }
            ],
        }
        with mock.patch.object(claude_any, "router_log") as router_log:
            claude_any.remember_channel_injected_tool_uses(source_body, assistant_message)
            followup_body = {
                "messages": [
                    assistant_message,
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_channel_1",
                                "content": "DM sent",
                            }
                        ],
                    },
                ],
            }
            out = claude_any.body_with_channel_tool_result_context(followup_body)

        self.assertIsNot(out, followup_body)
        self.assertTrue(out["metadata"]["claude_any_channel_tool_result_followup"])
        injected = out["messages"][-1]["content"][0]["text"]
        self.assertIn("channel tool_result follow-up", injected)
        self.assertIn("toolu_channel_1", injected)
        self.assertIn("mcp__ai-net-sse__send_dm", injected)
        self.assertIn("Sarah", injected)
        self.assertIn("Robert 리드님, 준비 완료입니다.", injected)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_tool_context_stored" in item and "toolu_channel_1" in item for item in log_messages))
        self.assertTrue(any("channel_llm_tool_result_context_injected" in item and "toolu_channel_1" in item for item in log_messages))

    def test_summarize_messages_for_trace_includes_tool_result_blocks(self):
        summary = claude_any.summarize_messages_for_trace(
            [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_trace_1",
                            "name": "mcp__ai-net-sse__send_dm",
                            "input": {"content": "hello"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_trace_1",
                            "content": "sent",
                        }
                    ],
                },
            ]
        )

        self.assertEqual("tool_use", summary[0]["content"][0]["type"])
        self.assertEqual("toolu_trace_1", summary[0]["content"][0]["id"])
        self.assertEqual("tool_result", summary[1]["content"][0]["type"])
        self.assertEqual("toolu_trace_1", summary[1]["content"][0]["tool_use_id"])
        self.assertEqual("sent", summary[1]["content"][0]["content"])

    def test_body_with_pending_channel_messages_skips_direct_router_requests(self):
        body = {"metadata": {"claude_any_channel_direct": True}, "messages": []}
        with mock.patch.object(claude_any, "load_config") as load_config:
            out = claude_any.body_with_pending_channel_messages(body)
        self.assertIs(out, body)
        load_config.assert_not_called()

    def test_body_with_pending_channel_summaries_injects_direct_processing_result(self):
        original_cursor = claude_any._CHANNEL_LLM_SUMMARY_CURSOR_LAST_ID
        cursor_payload = None
        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "channel-llm-summary-queue.jsonl"
            cursor_path = Path(td) / "channel-llm-summary-cursor.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "message_id": 12,
                        "channel": "room_4pyr8vvwm2cd",
                        "sender": "Sarah",
                        "stop_reason": "end_turn",
                        "tool_turns": 1,
                        "incoming": "Robert 리드님, 보고드립니다.",
                        "summary": "Sarah에게 업무를 배정했고 DM 전송 결과를 확인했습니다.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                claude_any._CHANNEL_LLM_SUMMARY_CURSOR_LAST_ID = None
                with (
                    mock.patch.object(claude_any, "CHANNEL_LLM_SUMMARY_QUEUE_PATH", queue_path),
                    mock.patch.object(claude_any, "CHANNEL_LLM_SUMMARY_CURSOR_PATH", cursor_path),
                    mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_DELIVERY": "llm"}),
                    mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                    mock.patch.object(claude_any, "router_log") as router_log,
                ):
                    out = claude_any.body_with_pending_channel_summaries(
                        {"messages": [{"role": "user", "content": "continue"}]}
                    )
                    cursor_payload = json.loads(cursor_path.read_text(encoding="utf-8"))
            finally:
                claude_any._CHANNEL_LLM_SUMMARY_CURSOR_LAST_ID = original_cursor

        self.assertEqual(2, len(out["messages"]))
        injected = out["messages"][-1]["content"][0]["text"]
        self.assertIn("channel direct handling summaries", injected)
        self.assertIn("message_id=12", injected)
        self.assertIn("Sarah에게 업무를 배정", injected)
        self.assertTrue(out["metadata"]["claude_any_channel_summary_injected"])
        self.assertEqual("12", out["metadata"]["claude_any_channel_summary_message_ids"])
        self.assertEqual({"last_id": 12}, cursor_payload)
        self.assertTrue(any("channel_llm_summary_injected" in str(call.args[1]) for call in router_log.call_args_list))

    def test_body_with_pending_channel_messages_skips_persisted_direct_pending_messages(self):
        body = {"messages": [{"role": "user", "content": "continue"}], "stream": True}
        messages = [
            {
                "id": 3,
                "channel": "room",
                "sender_id": "sarah",
                "message": "direct marked before scheduling",
                "meta": {"room_id": "room", "llm_direct_pending": True},
            }
        ]
        with (
            mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
            mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=1),
            mock.patch.object(claude_any, "_channel_llm_write_cursor_locked") as write_cursor,
            mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            out = claude_any.body_with_pending_channel_messages(body)

        self.assertIs(out, body)
        write_cursor.assert_called_with(3)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("llm_direct_pending" in item for item in log_messages))

    def test_body_with_pending_channel_messages_skips_direct_delivered_messages(self):
        body = {"messages": [{"role": "user", "content": "continue"}], "stream": True}
        messages = [{"id": 3, "channel": "room", "sender_id": "sarah", "message": "already sent", "meta": {"room_id": "room"}}]
        claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()
        claude_any._CHANNEL_LLM_DIRECT_DELIVERED.add(3)
        try:
            with (
                mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=1),
                mock.patch.object(claude_any, "_channel_llm_write_cursor_locked") as write_cursor,
                mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                out = claude_any.body_with_pending_channel_messages(body)
        finally:
            claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()
        self.assertIs(out, body)
        write_cursor.assert_called_with(3)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("llm_direct_delivered" in item for item in log_messages))

    def test_body_with_pending_channel_messages_skips_direct_inflight_messages(self):
        body = {"messages": [{"role": "user", "content": "continue"}], "stream": True}
        messages = [{"id": 3, "channel": "room", "sender_id": "sarah", "message": "direct running", "meta": {"room_id": "room"}}]
        claude_any._CHANNEL_LLM_DIRECT_INFLIGHT.clear()
        claude_any._CHANNEL_LLM_DIRECT_INFLIGHT.add(3)
        try:
            with (
                mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=1),
                mock.patch.object(claude_any, "_channel_llm_write_cursor_locked") as write_cursor,
                mock.patch.object(claude_any, "read_chat_messages", return_value=messages),
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                out = claude_any.body_with_pending_channel_messages(body)
        finally:
            claude_any._CHANNEL_LLM_DIRECT_INFLIGHT.clear()
        self.assertIs(out, body)
        write_cursor.assert_called_with(3)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("llm_direct_inflight" in item for item in log_messages))

    def test_channel_sse_dispatch_marks_direct_pending_and_schedules_background_delivery(self):
        captured: list[dict[str, object]] = []
        original_connections = dict(claude_any._CHANNEL_SSE_CONNECTIONS)

        def fake_append(payload):
            captured.append(payload)
            saved = dict(payload)
            saved["id"] = 7
            return saved

        try:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS["mcp-ai-net-sse"] = {
                "name": "mcp-ai-net-sse",
                "channel": "room_4pyr8vvwm2cd",
            }
            payload = {
                "channel": "room_4pyr8vvwm2cd",
                "sender_id": "sarah",
                "message": "새 이벤트",
                "kind": "message",
                "meta": {"room_id": "room_4pyr8vvwm2cd"},
                "visibility": "user",
                "delivery": ["llm"],
            }
            with (
                mock.patch.object(claude_any, "_sse_payload_to_chat_payload", return_value=payload),
                mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                mock.patch.object(claude_any, "append_chat_message", side_effect=fake_append),
                mock.patch.object(claude_any, "schedule_channel_direct_llm_delivery") as schedule,
                mock.patch.object(claude_any, "router_log"),
            ):
                claude_any._channel_sse_dispatch("mcp-ai-net-sse", "message", ["{}"])
        finally:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS.update(original_connections)

        self.assertEqual(1, len(captured))
        self.assertTrue(captured[0]["meta"]["llm_direct_pending"])
        self.assertEqual(["llm"], captured[0]["delivery"])
        schedule.assert_called_once()
        self.assertEqual(7, schedule.call_args.args[0]["id"])
        self.assertTrue(schedule.call_args.args[0]["meta"]["llm_direct_pending"])

    def test_channel_sse_dispatch_ignores_native_router_self_echo(self):
        original_connections = dict(claude_any._CHANNEL_SSE_CONNECTIONS)
        try:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS["mcp-claude-any-router"] = {
                "name": "mcp-claude-any-router",
                "channel": "room_4pyr8vvwm2cd",
            }
            with (
                mock.patch.object(claude_any, "_sse_payload_to_chat_payload") as parse_payload,
                mock.patch.object(claude_any, "append_chat_message") as append,
                mock.patch.object(claude_any, "schedule_channel_direct_llm_delivery") as schedule,
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                claude_any._channel_sse_dispatch(
                    "mcp-claude-any-router",
                    "message",
                    ['{"method":"notifications/claude/channel","params":{"recipients":["all"]}}'],
                )
        finally:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS.update(original_connections)

        parse_payload.assert_not_called()
        append.assert_not_called()
        schedule.assert_not_called()
        self.assertTrue(any("native_router_self_echo" in str(call.args[1]) for call in router_log.call_args_list))

    def test_channel_sse_dispatch_stores_mcp_rpc_response_without_chat_append(self):
        original_connections = dict(claude_any._CHANNEL_SSE_CONNECTIONS)
        try:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS["mcp-ai-net-sse"] = {
                "name": "mcp-ai-net-sse",
                "mcp_rpc_results": {},
            }
            with (
                mock.patch.object(claude_any, "_sse_payload_to_chat_payload") as parse_payload,
                mock.patch.object(claude_any, "append_chat_message") as append,
                mock.patch.object(claude_any, "schedule_channel_direct_llm_delivery") as schedule,
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                claude_any._channel_sse_dispatch(
                    "mcp-ai-net-sse",
                    "message",
                    [json.dumps({"jsonrpc": "2.0", "id": 123, "result": {"ok": True}})],
                )
                state = claude_any._CHANNEL_SSE_CONNECTIONS["mcp-ai-net-sse"]
                stored = state["mcp_rpc_results"]["123"]
        finally:
            claude_any._CHANNEL_SSE_CONNECTIONS.clear()
            claude_any._CHANNEL_SSE_CONNECTIONS.update(original_connections)

        self.assertEqual({"ok": True}, stored["result"])
        parse_payload.assert_not_called()
        append.assert_not_called()
        schedule.assert_not_called()
        self.assertTrue(any("channel_sse_mcp_rpc_response" in str(call.args[1]) for call in router_log.call_args_list))

    def test_channel_string_list_decodes_json_array_strings(self):
        self.assertEqual(["all"], claude_any._as_string_list('["all"]'))
        self.assertEqual(["Robert", "Sarah"], claude_any._as_string_list(['["Robert"]', "Sarah"]))

    def test_channel_llm_skip_reason_rejects_internal_and_router_self_echo(self):
        self.assertEqual("recipient_internal", claude_any._channel_llm_message_skip_reason({"message": "x", "recipients": "internal"}))
        self.assertEqual(
            "native_router_self_echo",
            claude_any._channel_llm_message_skip_reason(
                {"message": "x", "sender_id": "mcp-claude-any-router", "meta": {"sse_source": "mcp-claude-any-router"}}
            ),
        )

    def test_channel_direct_llm_worker_uses_router_without_hidden_print_mode(self):
        message = {
            "id": 9,
            "channel": "room_4pyr8vvwm2cd",
            "sender_id": "ai-net",
            "message": "새 이벤트",
            "meta": {"room_id": "room_4pyr8vvwm2cd"},
        }
        claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()
        try:
            with (
                mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {"request_timeout_ms": 300000})),
                mock.patch.object(claude_any, "current_alias", return_value="claude-any-ollama-cloud-test"),
                mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=0),
                mock.patch.object(claude_any, "_channel_llm_write_cursor_locked"),
                mock.patch.object(
                    claude_any,
                    "_channel_direct_llm_router_response",
                    return_value=("분석 완료", "end_turn", 1),
                ) as router_response,
                mock.patch.object(claude_any, "_channel_direct_append_summary") as append_summary,
                mock.patch.object(claude_any, "append_chat_message") as append,
                mock.patch.object(claude_any, "router_log"),
            ):
                claude_any._channel_direct_llm_worker(message)
        finally:
            claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()

        router_response.assert_called_once()
        args = router_response.call_args.args
        self.assertEqual(9, args[0])
        prompt = args[1]
        self.assertIn("<< room_4pyr8vvwm2cd >> incoming channel message for the current agent", prompt)
        self.assertIn("자율 처리 턴", prompt)
        self.assertIn("로컬 사용자 승인 없이 같은 채널/DM에 답장", prompt)
        self.assertIn("답장 여부를 묻고 멈추지 마세요", prompt)
        self.assertIn("미래 행동을 약속하는 말만 남기고 턴을 끝내지 마세요", prompt)
        self.assertIn("범위를 작게 유지", prompt)
        self.assertIn("새 방 생성", prompt)
        self.assertIn("Let me send", prompt)
        self.assertIn("새 이벤트", prompt)
        append_summary.assert_called_once_with(message, "분석 완료", "end_turn", tool_turns=1)
        append.assert_not_called()

    def test_channel_direct_deferred_action_detector_matches_future_promises(self):
        self.assertTrue(
            claude_any._channel_direct_text_is_deferred_action(
                "Now I have the full context. Let me send her a proper DM response now."
            )
        )
        self.assertTrue(claude_any._channel_direct_text_is_deferred_action("Sarah에게 결과를 보고하겠습니다."))
        self.assertFalse(claude_any._channel_direct_text_is_deferred_action("Sarah에게 답장 완료했습니다."))
        self.assertFalse(claude_any._channel_direct_text_is_deferred_action("Sarah에게 회신했습니다."))

    def test_channel_direct_router_response_round_trips_mcp_tool_result_to_llm(self):
        calls: list[dict[str, object]] = []

        def fake_http(_message_id, body, _provider, _pcfg, _model):
            calls.append(json.loads(json.dumps(body, ensure_ascii=False)))
            if len(calls) == 1:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_direct_1",
                            "name": "mcp__ai-net-sse__send_dm",
                            "input": {"to_agent_id": "agent_sarah", "content": "확인했습니다."},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            return {"content": [{"type": "text", "text": "Sarah에게 회신했습니다."}], "stop_reason": "end_turn"}

        with (
            mock.patch.object(claude_any, "_channel_direct_tool_schemas", return_value=[{"name": "mcp__ai-net-sse__send_dm"}]),
            mock.patch.object(claude_any, "_channel_direct_llm_http_message", side_effect=fake_http),
            mock.patch.object(claude_any, "_channel_direct_execute_tool", return_value=("DM sent", False)) as execute_tool,
        ):
            text, stop_reason, tool_turns = claude_any._channel_direct_llm_router_response(
                14,
                "수신 메시지를 처리하세요",
                {"id": 14, "meta": {"sse_source": "mcp-ai-net-sse"}},
                "deepseek",
                {"request_timeout_ms": 300000},
                "deepseek-v4-pro",
            )

        self.assertEqual("Sarah에게 회신했습니다.", text)
        self.assertEqual("end_turn", stop_reason)
        self.assertEqual(1, tool_turns)
        execute_tool.assert_called_once()
        self.assertEqual(2, len(calls))
        second_messages = calls[1]["messages"]
        self.assertEqual("assistant", second_messages[-2]["role"])
        self.assertEqual("user", second_messages[-1]["role"])
        tool_result = second_messages[-1]["content"][0]
        self.assertEqual("tool_result", tool_result["type"])
        self.assertEqual("toolu_direct_1", tool_result["tool_use_id"])
        self.assertEqual("DM sent", tool_result["content"])

    def test_channel_direct_router_response_retries_deferred_action_text(self):
        calls: list[dict[str, object]] = []

        def fake_http(_message_id, body, _provider, _pcfg, _model):
            calls.append(json.loads(json.dumps(body, ensure_ascii=False)))
            if len(calls) == 1:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Now I have the full context. Let me send her a proper DM response now.",
                        }
                    ],
                    "stop_reason": "end_turn",
                }
            if len(calls) == 2:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_direct_retry_1",
                            "name": "mcp__ai-net-sse__send_dm",
                            "input": {"to_agent_id": "agent_sarah", "content": "현재 상황입니다."},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            return {"content": [{"type": "text", "text": "Sarah에게 현재 상황을 DM으로 회신했습니다."}], "stop_reason": "end_turn"}

        with (
            mock.patch.object(claude_any, "_channel_direct_tool_schemas", return_value=[{"name": "mcp__ai-net-sse__send_dm"}]),
            mock.patch.object(claude_any, "_channel_direct_llm_http_message", side_effect=fake_http),
            mock.patch.object(claude_any, "_channel_direct_execute_tool", return_value=("DM sent", False)) as execute_tool,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            text, stop_reason, tool_turns = claude_any._channel_direct_llm_router_response(
                15,
                "수신 메시지를 처리하세요",
                {"id": 15, "meta": {"sse_source": "mcp-ai-net-sse"}},
                "deepseek",
                {"request_timeout_ms": 300000},
                "deepseek-v4-pro",
            )

        self.assertEqual("Sarah에게 현재 상황을 DM으로 회신했습니다.", text)
        self.assertEqual("end_turn", stop_reason)
        self.assertEqual(1, tool_turns)
        execute_tool.assert_called_once()
        self.assertEqual(3, len(calls))
        retry_prompt = calls[1]["messages"][-1]["content"][0]["text"]
        self.assertIn("[claude-any channel action required]", retry_prompt)
        self.assertIn("Let me send", retry_prompt)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_deferred_action_retry" in item for item in log_messages))

    def test_channel_direct_router_response_retries_deferred_action_after_sixth_turn(self):
        calls: list[dict[str, object]] = []

        def fake_http(_message_id, body, _provider, _pcfg, _model):
            calls.append(json.loads(json.dumps(body, ensure_ascii=False)))
            if len(calls) <= 5:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": f"toolu_many_{len(calls)}",
                            "name": "mcp__ai-net-sse__get_messages",
                            "input": {"room_id": "room_dm_4wcekxw4yse", "limit": 5},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            if len(calls) == 6:
                return {
                    "content": [{"type": "text", "text": "All members invited. Now let me reply to Sarah's DM."}],
                    "stop_reason": "end_turn",
                }
            if len(calls) == 7:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_after_retry",
                            "name": "mcp__ai-net-sse__send_dm",
                            "input": {"to_agent_id": "agent_sarah", "content": "현재 상황입니다."},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            return {"content": [{"type": "text", "text": "Sarah에게 현재 상황을 DM으로 회신했습니다."}], "stop_reason": "end_turn"}

        with (
            mock.patch.object(
                claude_any,
                "_channel_direct_tool_schemas",
                return_value=[{"name": "mcp__ai-net-sse__get_messages"}, {"name": "mcp__ai-net-sse__send_dm"}],
            ),
            mock.patch.object(claude_any, "_channel_direct_llm_http_message", side_effect=fake_http),
            mock.patch.object(claude_any, "_channel_direct_execute_tool", return_value=("ok", False)) as execute_tool,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            text, stop_reason, tool_turns = claude_any._channel_direct_llm_router_response(
                18,
                "수신 메시지를 처리하세요",
                {"id": 18, "channel": "room_dm_4wcekxw4yse", "meta": {"sse_source": "mcp-ai-net-sse"}},
                "deepseek",
                {"request_timeout_ms": 300000},
                "deepseek-v4-pro",
            )

        self.assertEqual("Sarah에게 현재 상황을 DM으로 회신했습니다.", text)
        self.assertEqual("end_turn", stop_reason)
        self.assertEqual(6, tool_turns)
        self.assertEqual(6, execute_tool.call_count)
        self.assertEqual(8, len(calls))
        retry_prompt = calls[6]["messages"][-1]["content"][0]["text"]
        self.assertIn("[claude-any channel action required]", retry_prompt)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_deferred_action_retry" in item for item in log_messages))

    def test_channel_direct_router_response_replaces_deferred_text_at_max_turns(self):
        calls: list[dict[str, object]] = []

        def fake_http(_message_id, body, _provider, _pcfg, _model):
            calls.append(json.loads(json.dumps(body, ensure_ascii=False)))
            return {
                "content": [{"type": "text", "text": "All three members invited. Now let me send the group room announcement."}],
                "stop_reason": "end_turn",
            }

        with (
            mock.patch.object(claude_any, "_CHANNEL_DIRECT_MAX_ROUTER_TURNS", 1),
            mock.patch.object(claude_any, "_channel_direct_tool_schemas", return_value=[{"name": "mcp__ai-net-sse__send_dm"}]),
            mock.patch.object(claude_any, "_channel_direct_llm_http_message", side_effect=fake_http),
            mock.patch.object(claude_any, "router_log"),
        ):
            text, stop_reason, tool_turns = claude_any._channel_direct_llm_router_response(
                19,
                "수신 메시지를 처리하세요",
                {"id": 19, "channel": "room_dm_4wcekxw4yse", "message": "New message from Sarah"},
                "deepseek",
                {"request_timeout_ms": 300000},
                "deepseek-v4-pro",
            )

        self.assertEqual("max_tool_turns", stop_reason)
        self.assertEqual(0, tool_turns)
        self.assertIn("도구 호출 한도", text)
        self.assertIn("실제 처리 완료로 표시하지 않았습니다", text)
        self.assertIn("Now let me send", text)

    def test_channel_direct_tool_schemas_filters_workflow_tools(self):
        response = {
            "result": {
                "tools": [
                    {"name": "get_messages", "inputSchema": {"type": "object"}},
                    {"name": "send_dm", "inputSchema": {"type": "object"}},
                    {"name": "send_message", "inputSchema": {"type": "object"}},
                    {"name": "list_rooms", "inputSchema": {"type": "object"}},
                    {"name": "create_room", "inputSchema": {"type": "object"}},
                    {"name": "add_room_member", "inputSchema": {"type": "object"}},
                    {"name": "assign_task", "inputSchema": {"type": "object"}},
                    {"name": "wait_for_notifications", "inputSchema": {"type": "object"}},
                ]
            }
        }
        with (
            mock.patch.object(claude_any, "_channel_direct_source_state_name", return_value="mcp-ai-net-sse"),
            mock.patch.object(claude_any, "_channel_sse_public_mcp_name", return_value="ai-net-sse"),
            mock.patch.object(claude_any, "_channel_sse_rpc_request", return_value=response),
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            tools = claude_any._channel_direct_tool_schemas({"id": 20})

        names = {tool["name"] for tool in tools}
        self.assertIn("mcp__ai-net-sse__get_messages", names)
        self.assertIn("mcp__ai-net-sse__send_dm", names)
        self.assertIn("mcp__ai-net-sse__send_message", names)
        self.assertIn("mcp__ai-net-sse__list_rooms", names)
        self.assertNotIn("mcp__ai-net-sse__create_room", names)
        self.assertNotIn("mcp__ai-net-sse__add_room_member", names)
        self.assertNotIn("mcp__ai-net-sse__assign_task", names)
        self.assertNotIn("mcp__ai-net-sse__wait_for_notifications", names)
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("filtered=4" in item for item in log_messages))

    def test_channel_direct_execute_tool_blocks_workflow_tools(self):
        with (
            mock.patch.object(claude_any, "_channel_sse_state_name_for_mcp_server", return_value="mcp-ai-net-sse"),
            mock.patch.object(claude_any, "_channel_sse_rpc_request") as rpc_request,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            text, is_error = claude_any._channel_direct_execute_tool(
                {
                    "id": "toolu_blocked",
                    "name": "mcp__ai-net-sse__create_room",
                    "input": {"name": "new room"},
                }
            )

        self.assertTrue(is_error)
        self.assertIn("not allowed", text)
        rpc_request.assert_not_called()
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_tool_blocked" in item for item in log_messages))

    def test_channel_direct_router_response_without_tools_returns_blocker(self):
        with (
            mock.patch.object(claude_any, "_channel_direct_tool_schemas", return_value=[]),
            mock.patch.object(claude_any, "_channel_direct_llm_http_message") as http_message,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            text, stop_reason, tool_turns = claude_any._channel_direct_llm_router_response(
                16,
                "수신 메시지를 처리하세요",
                {
                    "id": 16,
                    "channel": "room_dm_4wcekxw4yse",
                    "message": "New message from Sarah",
                    "meta": {"sse_source": "mcp-ai-net-sse", "room_id": "room_dm_4wcekxw4yse"},
                },
                "deepseek",
                {"request_timeout_ms": 300000},
                "deepseek-v4-pro",
            )

        self.assertIn("MCP 도구 목록을 가져오지 못했습니다", text)
        self.assertIn("없는 도구를 가정한 텍스트 명령은 실행하지 않았습니다", text)
        self.assertIn("room_dm_4wcekxw4yse", text)
        self.assertEqual("no_tools", stop_reason)
        self.assertEqual(0, tool_turns)
        http_message.assert_not_called()
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_no_tools" in item for item in log_messages))

    def test_channel_direct_worker_does_not_enqueue_no_tools_summary(self):
        message = {
            "id": 17,
            "channel": "room_dm_4wcekxw4yse",
            "sender_id": "ai-net",
            "message": "New message from Sarah",
            "meta": {"room_id": "room_dm_4wcekxw4yse"},
        }
        claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()
        try:
            with (
                mock.patch.object(claude_any, "load_config", return_value={"claude_code": {"channel_delivery": "llm"}}),
                mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {"request_timeout_ms": 300000})),
                mock.patch.object(claude_any, "current_alias", return_value="claude-any-ollama-cloud-test"),
                mock.patch.object(claude_any, "_channel_llm_read_cursor_locked", return_value=0),
                mock.patch.object(claude_any, "_channel_llm_write_cursor_locked"),
                mock.patch.object(
                    claude_any,
                    "_channel_direct_llm_router_response",
                    return_value=("MCP tools unavailable", "no_tools", 0),
                ),
                mock.patch.object(claude_any, "_channel_direct_append_summary") as append_summary,
                mock.patch.object(claude_any, "_channel_direct_terminal_notice"),
                mock.patch.object(claude_any, "router_log") as router_log,
            ):
                claude_any._channel_direct_llm_worker(message)
        finally:
            claude_any._CHANNEL_LLM_DIRECT_DELIVERED.clear()

        append_summary.assert_not_called()
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("channel_llm_summary_skipped" in item and "reason=no_tools" in item for item in log_messages))

    def test_channel_direct_terminal_notice_prints_when_stdout_is_tty(self):
        class FakeStdout:
            def __init__(self):
                self.text = ""

            def isatty(self):
                return True

            def write(self, text):
                self.text += text

            def flush(self):
                pass

        fake_stdout = FakeStdout()
        message = {
            "id": 12,
            "channel": "room_dm",
            "sender_id": "ai-net-sse",
            "meta": {"author_name": "Sarah"},
        }

        with mock.patch.object(claude_any.sys, "stdout", fake_stdout):
            claude_any._channel_direct_terminal_notice(message, "처리 요약", "cli")

        self.assertIn("message_id=12", fake_stdout.text)
        self.assertIn("from=Sarah", fake_stdout.text)
        self.assertIn("처리 요약", fake_stdout.text)

    def test_router_channel_mcp_notification_wraps_chat_message(self):
        notification = claude_any._channel_mcp_notification(
            {
                "id": 7,
                "channel": "room_phase1sim",
                "sender_id": "robert",
                "thread_id": "root",
                "message": "hello Sarah",
                "recipients": ["sarah"],
                "meta": {"room_id": "room_phase1sim"},
            }
        )
        self.assertEqual("notifications/claude/channel", notification["method"])
        self.assertIn("hello Sarah", notification["params"]["content"])
        self.assertEqual("hello Sarah", notification["params"]["message"])
        self.assertEqual("hello Sarah", notification["params"]["text"])
        self.assertEqual("room_phase1sim", notification["params"]["channel"])
        self.assertEqual("room_phase1sim", notification["params"]["room_id"])
        self.assertEqual("robert", notification["params"]["sender_id"])
        self.assertEqual(["sarah"], notification["params"]["recipients"])
        self.assertEqual("7", notification["params"]["meta"]["claude_any_message_id"])
        self.assertEqual('["sarah"]', notification["params"]["meta"]["recipients"])

    def test_router_channel_mcp_notification_normalizes_json_string_recipients(self):
        notification = claude_any._channel_mcp_notification(
            {
                "id": 9,
                "channel": "room",
                "sender_id": "robert",
                "message": "hello",
                "recipients": '["sarah"]',
                "meta": {"room_id": "room"},
            }
        )
        self.assertEqual(["sarah"], notification["params"]["recipients"])
        self.assertEqual('["sarah"]', notification["params"]["meta"]["recipients"])

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
            self.assertEqual("2024-11-05", outbox[0]["result"]["protocolVersion"])
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
        self.assertTrue(any("channel_mcp_notification_prepared" in item and "message_id=2" in item for item in log_messages))

    def test_channel_mcp_notifications_skip_internal_messages(self):
        messages = [
            {
                "id": 15,
                "channel": "room",
                "sender_id": "claude-any-llm",
                "recipients": ["internal"],
                "message": "old internal response",
                "visibility": "user",
                "delivery": ["native"],
                "meta": {"room_id": "room"},
            },
            {
                "id": 16,
                "channel": "room",
                "sender_id": "ai-net",
                "recipients": ["all"],
                "message": "new external message",
                "visibility": "user",
                "delivery": ["native", "llm"],
                "meta": {"room_id": "room"},
            },
        ]
        with mock.patch.object(claude_any, "router_log") as router_log:
            last_id, events = claude_any._channel_mcp_notifications_for_messages(messages, "session-1")
        self.assertEqual(16, last_id)
        self.assertEqual(1, len(events))
        self.assertEqual(16, events[0][0])
        self.assertEqual(["all"], events[0][1]["params"]["recipients"])
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("recipient_internal" in item and "message_id=15" in item for item in log_messages))

    def test_channel_mcp_notifications_skip_llm_only_inputs(self):
        messages = [
            {
                "id": 106,
                "channel": "room",
                "sender_id": "ai-net",
                "recipients": ["all"],
                "message": "inbound event",
                "visibility": "user",
                "delivery": ["llm"],
                "meta": {"room_id": "room"},
            },
            {
                "id": 107,
                "channel": "room",
                "sender_id": "claude-any-llm",
                "recipients": ["all"],
                "message": "direct response",
                "visibility": "user",
                "delivery": ["native"],
                "kind": "channel_llm_response",
                "meta": {"room_id": "room", "source_message_id": 106, "llm_direct_delivered": True},
            },
        ]
        with mock.patch.object(claude_any, "router_log") as router_log:
            last_id, events = claude_any._channel_mcp_notifications_for_messages(messages, "session-1")
        self.assertEqual(107, last_id)
        self.assertEqual(1, len(events))
        self.assertEqual(107, events[0][0])
        self.assertEqual("channel_llm_response", events[0][1]["params"]["kind"])
        log_messages = [str(call.args[1]) for call in router_log.call_args_list if len(call.args) > 1]
        self.assertTrue(any("delivery_not_native" in item and "message_id=106" in item for item in log_messages))

    def test_channel_mcp_session_start_prefers_client_last_event_id_for_replay(self):
        class Handler:
            path = "/ca/mcp/sse"
            headers = {"Last-Event-ID": "10"}

        with (
            mock.patch.object(claude_any, "_channel_mcp_ensure_cursor_initialized", return_value=12),
            mock.patch.object(claude_any, "_channel_mcp_update_cursor") as update_cursor,
            mock.patch.object(claude_any, "router_log") as router_log,
        ):
            last_id = claude_any._channel_mcp_session_start_last_id(Handler())
        self.assertEqual(10, last_id)
        update_cursor.assert_not_called()
        self.assertTrue(any("channel_mcp_resume" in str(call.args[1]) and "client_last_id=10" in str(call.args[1]) for call in router_log.call_args_list))

    def test_channel_mcp_session_start_advances_cursor_from_client_ack(self):
        class Handler:
            path = "/ca/mcp/sse?lastEventId=15"
            headers = {}

        with (
            mock.patch.object(claude_any, "_channel_mcp_ensure_cursor_initialized", return_value=12),
            mock.patch.object(claude_any, "_channel_mcp_update_cursor") as update_cursor,
        ):
            last_id = claude_any._channel_mcp_session_start_last_id(Handler())
        self.assertEqual(15, last_id)
        update_cursor.assert_called_once_with(15)

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

    def test_mcp_proxy_subcommand_bridges_jsonl_stdio_server(self):
        with tempfile.TemporaryDirectory(prefix="ca-mcp-jsonl-test-") as td:
            root = Path(td)
            server = root / "fake_jsonl_server.py"
            server.write_text(
                textwrap.dedent(
                    r'''
                    import json
                    import sys

                    line = sys.stdin.buffer.readline()
                    if line:
                        request = json.loads(line.decode("utf-8"))
                        print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": {"protocolVersion": "2024-11-05", "capabilities": {}}}), flush=True)
                        print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {"content": "wake from jsonl subprocess"}}), flush=True)
                    '''
                ),
                encoding="utf-8",
            )
            config = root / "server.json"
            config.write_text(
                json.dumps({"command": sys.executable, "args": [str(server)], "claude_any_stdio": "jsonl"}),
                encoding="utf-8",
            )
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
                    "fake-jsonl",
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
            self.assertNotIn(b"Content-Length:", proc.stderr)
            chat_log = root / "config" / "chat-messages.jsonl"
            self.assertTrue(chat_log.exists())
            self.assertIn("wake from jsonl subprocess", chat_log.read_text(encoding="utf-8"))

    def test_channel_mcp_config_points_to_router_sse(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "channel-mcp.json"
            with (
                mock.patch.object(claude_any, "CONFIG_DIR", Path(td)),
                mock.patch.object(claude_any, "CHANNEL_MCP_CONFIG", path),
                mock.patch.object(claude_any, "_channel_mcp_ensure_cursor_initialized", return_value=0),
            ):
                written = claude_any.write_channel_mcp_config()
            data = __import__("json").loads(written.read_text(encoding="utf-8"))
        self.assertEqual("sse", data["mcpServers"]["claude-any-router"]["type"])
        self.assertTrue(data["mcpServers"]["claude-any-router"]["url"].endswith("/ca/mcp/sse"))

    def test_channel_mcp_endpoint_uses_legacy_session_id_param(self):
        session = "session-123"
        endpoint = f"/ca/mcp/messages?sessionId={session}"
        params = urllib.parse.parse_qs(urllib.parse.urlparse(endpoint).query)
        self.assertEqual(session, params["sessionId"][0])


if __name__ == "__main__":
    unittest.main()
