import unittest
from io import BytesIO

import claude_any


def body_with_tools(user_text: str, tool_names: list[str]) -> dict:
    return {
        "model": "claude-any-ollama-cloud-deepseek-v4-flash[1m]",
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        "tools": [{"name": name, "input_schema": {"type": "object"}} for name in tool_names],
    }


class EmptyEndTurnRecoveryTests(unittest.TestCase):
    def test_empty_resume_turn_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "Edit"])
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
        body = body_with_tools("continue implementation", ["Read", "Edit"])
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

    def test_choice_question_in_plan_mode_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "ExitPlanMode"])
        body["messages"].append(
            {
                "role": "user",
                "content": [],
                "attachment": {"type": "plan_mode", "filePath": "/tmp/plan.md"},
            }
        )
        data = {
            "message": {
                "content": (
                    "Which implementation part should I start now? "
                    "Or should I proceed with every in-scope part?"
                )
            },
            "done": True,
            "done_reason": "stop",
            "eval_count": 40,
        }

        message = claude_any.ollama_chat_to_anthropic(data, "deepseek-v4-flash", source_body=body)

        self.assertEqual("tool_use", message["stop_reason"])
        self.assertEqual("text", message["content"][0]["type"])
        self.assertEqual("TaskList", message["content"][-1]["name"])

    def test_native_json_choice_question_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "ExitPlanMode"])
        body["messages"].append(
            {
                "role": "user",
                "content": [],
                "attachment": {"type": "plan_mode", "filePath": "/tmp/plan.md"},
            }
        )
        message = {
            "id": "msg_native",
            "type": "message",
            "role": "assistant",
            "model": "deepseek-v4-flash",
            "content": [{"type": "text", "text": "Which part should I implement first?"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

        patched = claude_any.append_synthetic_tasklist_to_message(message, "deepseek-v4-flash", body, "test")

        self.assertEqual("tool_use", patched["stop_reason"])
        self.assertEqual("TaskList", patched["content"][-1]["name"])

    def test_native_stream_choice_question_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "ExitPlanMode"])
        body["messages"].append(
            {
                "role": "user",
                "content": [],
                "attachment": {"type": "plan_mode", "filePath": "/tmp/plan.md"},
            }
        )

        class Handler:
            def __init__(self):
                self.wfile = BytesIO()

        handler = Handler()
        events = [
            'event: message_start\ndata: {"type":"message_start","message":{"content":[]}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Which part should I implement first?"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        lines = []
        for event in events:
            lines.extend(f"{line}\n".encode("utf-8") for line in event.splitlines())
        claude_any._rebatch_anthropic_sse_text(
            handler,
            lines,
            "deepseek-v4-flash",
            word_chunking=False,
            source_body=body,
        )
        output = handler.wfile.getvalue().decode("utf-8")

        self.assertIn("toolu_anthropic_choice_", output)
        self.assertIn('"name": "TaskList"', output)
        self.assertIn('"stop_reason": "tool_use"', output)

    def test_native_stream_hidden_only_response_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "Edit"])
        body["messages"].append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "I will continue the implementation."}],
            }
        )

        class Handler:
            def __init__(self):
                self.wfile = BytesIO()

        handler = Handler()
        events = [
            'event: message_start\ndata: {"type":"message_start","message":{"content":[]}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"private reasoning"}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        lines = []
        for event in events:
            lines.extend(f"{line}\n".encode("utf-8") for line in event.splitlines())
        claude_any._rebatch_anthropic_sse_text(
            handler,
            lines,
            "deepseek-v4-flash",
            word_chunking=False,
            source_body=body,
            preserve_thinking=False,
            provider="deepseek",
            normalize_tool_use=True,
        )
        output = handler.wfile.getvalue().decode("utf-8")

        self.assertNotIn("private reasoning", output)
        self.assertNotIn("thinking_delta", output)
        self.assertIn('"name": "TaskList"', output)
        self.assertIn('"stop_reason": "tool_use"', output)

    def test_native_stream_dropped_tool_use_still_recovers_hidden_only_response(self):
        body = body_with_tools("continue implementation", ["TaskList", "EnterPlanMode", "Read"])
        body["messages"].append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_enter_plan",
                        "name": "EnterPlanMode",
                        "input": {},
                    }
                ],
            }
        )
        body["messages"].append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_enter_plan",
                        "content": "entered plan mode",
                    }
                ],
            }
        )

        class Handler:
            def __init__(self):
                self.wfile = BytesIO()

        handler = Handler()
        events = [
            'event: message_start\ndata: {"type":"message_start","message":{"content":[]}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"private reasoning"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_repeat_plan","name":"EnterPlanMode","input":{}}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{}"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":1}\n\n',
            'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"tool_use","stop_sequence":null},"usage":{"output_tokens":1}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        lines = []
        for event in events:
            lines.extend(f"{line}\n".encode("utf-8") for line in event.splitlines())
        claude_any._rebatch_anthropic_sse_text(
            handler,
            lines,
            "deepseek-v4-flash",
            word_chunking=False,
            source_body=body,
            preserve_thinking=False,
            provider="deepseek",
            normalize_tool_use=True,
        )
        output = handler.wfile.getvalue().decode("utf-8")

        self.assertNotIn("private reasoning", output)
        self.assertNotIn("toolu_repeat_plan", output)
        self.assertIn('"name": "TaskList"', output)
        self.assertIn('"stop_reason": "tool_use"', output)

    def test_native_stream_hidden_only_after_tool_result_synthesizes_tasklist(self):
        body = body_with_tools("continue implementation", ["TaskList", "Read", "Bash"])
        body["messages"].append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_health",
                        "name": "Bash",
                        "input": {"command": "check health"},
                    }
                ],
            }
        )
        body["messages"].append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_health",
                        "content": "healthy",
                    }
                ],
            }
        )

        class Handler:
            def __init__(self):
                self.wfile = BytesIO()

        handler = Handler()
        events = [
            'event: message_start\ndata: {"type":"message_start","message":{"content":[]}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"private reasoning"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        lines = []
        for event in events:
            lines.extend(f"{line}\n".encode("utf-8") for line in event.splitlines())
        claude_any._rebatch_anthropic_sse_text(
            handler,
            lines,
            "deepseek-v4-flash",
            word_chunking=False,
            source_body=body,
            preserve_thinking=False,
            provider="deepseek",
            normalize_tool_use=True,
        )
        output = handler.wfile.getvalue().decode("utf-8")

        self.assertNotIn("private reasoning", output)
        self.assertIn('"name": "TaskList"', output)
        self.assertIn('"stop_reason": "tool_use"', output)

    def test_native_stream_hidden_only_response_without_tasklist_shows_notice(self):
        body = body_with_tools("continue implementation", ["Read", "Edit"])

        class Handler:
            def __init__(self):
                self.wfile = BytesIO()

        handler = Handler()
        events = [
            'event: message_start\ndata: {"type":"message_start","message":{"content":[]}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"private reasoning"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        lines = []
        for event in events:
            lines.extend(f"{line}\n".encode("utf-8") for line in event.splitlines())
        claude_any._rebatch_anthropic_sse_text(
            handler,
            lines,
            "deepseek-v4-flash",
            word_chunking=False,
            source_body=body,
            preserve_thinking=False,
            provider="deepseek",
        )
        output = handler.wfile.getvalue().decode("utf-8")

        self.assertIn("empty end_turn", output)
        self.assertIn('"stop_reason": "end_turn"', output)


if __name__ == "__main__":
    unittest.main()
