import io
import unittest

import claude_any


class ThinkingPassthroughTests(unittest.TestCase):
    def test_do_not_defer_plan_mode_synthesis_for_non_anthropic_thinking(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "tool_choice": {"type": "tool", "name": "EnterPlanMode"},
            "tools": [{"name": "EnterPlanMode", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "plan"}]}],
        }

        self.assertFalse(
            claude_any.should_defer_forced_tool_choice_for_thinking(
                "vllm",
                {"native_compat": True},
                body,
                "EnterPlanMode",
            )
        )

    def test_do_not_defer_plan_mode_synthesis_without_thinking(self):
        body = {
            "tool_choice": {"type": "tool", "name": "EnterPlanMode"},
            "tools": [{"name": "EnterPlanMode", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "plan"}]}],
        }

        self.assertFalse(
            claude_any.should_defer_forced_tool_choice_for_thinking(
                "vllm",
                {"native_compat": True},
                body,
                "EnterPlanMode",
            )
        )

    def test_strip_thinking_for_claude_any_synthetic_tool_history(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_claude_any_EnterPlanMode_123",
                            "name": "EnterPlanMode",
                            "input": {},
                        }
                    ],
                }
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "vllm",
            {"native_compat": True},
            body,
        )

        self.assertIn("thinking", body)
        self.assertNotIn("thinking", out)

    def test_strip_thinking_for_tool_continuation_without_passback_blocks(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_real_123",
                            "name": "Read",
                            "input": {"file_path": "x"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_real_123",
                            "content": "file contents",
                        }
                    ],
                },
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "lm-studio",
            {"native_compat": True},
            body,
        )

        self.assertNotIn("thinking", out)
        self.assertEqual(2, claude_any.anthropic_tool_continuation_block_count(body))

    def test_strip_thinking_blocks_even_without_top_level_thinking_for_tool_continuation(self):
        body = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "hidden", "signature": "sig"},
                        {
                            "type": "tool_use",
                            "id": "toolu_real_123",
                            "name": "Read",
                            "input": {"file_path": "x"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_real_123",
                            "content": "file contents",
                        }
                    ],
                },
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "deepseek",
            {"native_compat": True},
            body,
        )

        self.assertIsNot(out, body)
        self.assertNotIn("thinking", out)
        self.assertEqual(0, claude_any.anthropic_thinking_block_count(out))
        self.assertEqual(1, claude_any.anthropic_thinking_block_count(body))

    def test_strip_initial_thinking_request_for_non_anthropic_native_provider(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "self-hosted-nim",
            {"native_compat": True},
            body,
        )

        self.assertIsNot(out, body)
        self.assertIn("thinking", body)
        self.assertNotIn("thinking", out)

    def test_strip_thinking_after_assistant_history_without_tool_continuation(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "continue implementation"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "I will continue implementation now."}]},
                {
                    "role": "user",
                    "content": [],
                    "attachment": {"type": "plan_mode", "filePath": "/tmp/plan.md"},
                },
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "deepseek",
            {"native_compat": True},
            body,
        )

        self.assertIsNot(out, body)
        self.assertIn("thinking", body)
        self.assertNotIn("thinking", out)

    def test_strip_thinking_blocks_for_real_tool_continuation(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "hidden", "signature": "sig"},
                        {
                            "type": "tool_use",
                            "id": "toolu_real_123",
                            "name": "Read",
                            "input": {"file_path": "x"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_real_123",
                            "content": "file contents",
                        }
                    ],
                }
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "vllm",
            {"native_compat": True},
            body,
        )

        self.assertIsNot(out, body)
        self.assertNotIn("thinking", out)
        self.assertEqual(0, claude_any.anthropic_thinking_block_count(out))
        self.assertEqual(1, claude_any.anthropic_thinking_block_count(body))

    def test_preserve_thinking_for_anthropic_native_history(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "hidden", "signature": "sig"},
                        {
                            "type": "tool_use",
                            "id": "toolu_real_123",
                            "name": "Read",
                            "input": {"file_path": "x"},
                        },
                    ],
                }
            ],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "anthropic",
            {"native_compat": True},
            body,
        )

        self.assertIs(out, body)
        self.assertIn("thinking", out)
        self.assertEqual(1, claude_any.anthropic_thinking_block_count(out))

    def test_strip_thinking_response_blocks_for_non_anthropic_provider(self):
        message = {
            "content": [
                {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
                {"type": "text", "text": "visible answer"},
            ],
            "stop_reason": "end_turn",
        }

        out = claude_any.normalize_response_thinking_for_non_anthropic_provider(
            "vllm",
            {"native_compat": True},
            message,
        )

        self.assertIsNot(out, message)
        self.assertEqual([{"type": "text", "text": "visible answer"}], out["content"])
        self.assertEqual(1, claude_any.anthropic_thinking_block_count({"messages": [{"role": "assistant", "content": message["content"]}]}))
        self.assertEqual(0, claude_any.anthropic_thinking_block_count({"messages": [{"role": "assistant", "content": out["content"]}]}))

    def test_preserve_thinking_response_blocks_for_anthropic_provider(self):
        message = {
            "content": [
                {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
                {"type": "text", "text": "visible answer"},
            ],
        }

        out = claude_any.normalize_response_thinking_for_non_anthropic_provider(
            "anthropic",
            {},
            message,
        )

        self.assertIs(out, message)
        self.assertEqual(2, len(out["content"]))

    def test_rebatch_suppresses_thinking_stream_blocks_for_non_anthropic_provider(self):
        class FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()

        def sse(event_name, payload):
            return f"event: {event_name}\ndata: {claude_any.json.dumps(payload, ensure_ascii=False)}\n\n".encode()

        chunks = [
            sse("message_start", {"type": "message_start", "message": {"id": "msg", "type": "message", "role": "assistant", "content": [], "model": "model"}}),
            sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "private reasoning"}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}}),
            sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}),
            sse("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "visible answer"}}),
            sse("content_block_stop", {"type": "content_block_stop", "index": 1}),
            sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 3}}),
            sse("message_stop", {"type": "message_stop"}),
        ]
        resp = io.BytesIO(b"".join(chunks))
        handler = FakeHandler()

        claude_any._rebatch_anthropic_sse_text(
            handler,
            resp,
            "model",
            word_chunking=False,
            preserve_thinking=False,
        )

        output = handler.wfile.getvalue().decode("utf-8")
        self.assertNotIn("thinking_delta", output)
        self.assertNotIn("private reasoning", output)
        self.assertIn("visible answer", output)
        self.assertIn('"index": 0', output)
        self.assertNotIn('"index": 1', output)

    def test_openai_conversion_does_not_leak_thinking_text(self):
        body = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
                        {"type": "text", "text": "visible answer"},
                    ],
                }
            ]
        }

        messages = claude_any.anthropic_messages_to_openai(body)

        assistant_messages = [message for message in messages if message.get("role") == "assistant"]
        self.assertTrue(assistant_messages)
        self.assertIn("visible answer", assistant_messages[-1]["content"])
        self.assertNotIn("private reasoning", assistant_messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
