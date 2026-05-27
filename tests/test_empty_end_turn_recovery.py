import unittest

import claude_any


def body_with_tools(user_text: str, tool_names: list[str]) -> dict:
    return {
        "model": "claude-any-ollama-cloud-deepseek-v4-flash[1m]",
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        "tools": [{"name": name, "input_schema": {"type": "object"}} for name in tool_names],
    }


class EmptyEndTurnRecoveryTests(unittest.TestCase):
    def test_empty_resume_turn_synthesizes_tasklist(self):
        body = body_with_tools("phase 2 개발진행", ["TaskList", "Read", "Edit"])
        body["messages"].insert(
            0,
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "I will continue the Phase 2 implementation."}],
            },
        )
        data = {
            "message": {"content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 197561,
            "eval_count": 29,
        }

        message = claude_any.ollama_chat_to_anthropic(data, "deepseek-v4-flash", source_body=body)

        self.assertEqual("tool_use", message["stop_reason"])
        self.assertEqual("TaskList", message["content"][0]["name"])
        self.assertEqual("tool_use", message["content"][0]["type"])

    def test_empty_turn_without_tasklist_returns_visible_notice(self):
        body = body_with_tools("phase 2 개발진행", ["Read", "Edit"])
        data = {
            "message": {"content": ""},
            "done": True,
            "done_reason": "stop",
            "eval_count": 29,
        }

        message = claude_any.ollama_chat_to_anthropic(data, "deepseek-v4-flash", source_body=body)

        text_blocks = [block for block in message["content"] if block.get("type") == "text"]
        self.assertTrue(text_blocks)
        self.assertIn("empty end_turn", text_blocks[0]["text"])
        self.assertEqual("end_turn", message["stop_reason"])

    def test_empty_plain_chat_does_not_synthesize_tasklist(self):
        body = body_with_tools("hi", ["TaskList", "Read"])
        data = {
            "message": {"content": ""},
            "done": True,
            "done_reason": "stop",
            "eval_count": 1,
        }

        message = claude_any.ollama_chat_to_anthropic(data, "deepseek-v4-flash", source_body=body)

        self.assertEqual("end_turn", message["stop_reason"])
        self.assertEqual("text", message["content"][0]["type"])
        self.assertIn("empty end_turn", message["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
