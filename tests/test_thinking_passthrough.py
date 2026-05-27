import unittest

import claude_any


class ThinkingPassthroughTests(unittest.TestCase):
    def test_defer_plan_mode_synthesis_when_native_provider_requests_thinking(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "tool_choice": {"type": "tool", "name": "EnterPlanMode"},
            "tools": [{"name": "EnterPlanMode", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "plan"}]}],
        }

        self.assertTrue(
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

    def test_keep_initial_thinking_request_without_tool_continuation(self):
        body = {
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }

        out = claude_any.normalize_thinking_for_non_anthropic_native_provider(
            "self-hosted-nim",
            {"native_compat": True},
            body,
        )

        self.assertIs(out, body)
        self.assertIn("thinking", out)

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
