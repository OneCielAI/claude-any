import unittest

import claude_any


class ToolNameCanonicalizationTests(unittest.TestCase):
    def test_matches_mcp_server_hyphen_underscore_drift_when_unique(self):
        available = {
            "mcp__ai-net-http__list_assignments",
            "mcp__other-server__list_assignments",
        }

        self.assertEqual(
            "mcp__ai-net-http__list_assignments",
            claude_any._match_available_tool_name("mcp__ai-net_http__list_assignments", available),
        )
        self.assertEqual(
            "mcp__ai-net-http__list_assignments",
            claude_any._match_available_tool_name("mcp__ai_net_http__list_assignments", available),
        )

    def test_does_not_match_ambiguous_mcp_server_normalization(self):
        available = {
            "mcp__ab__get_messages",
            "mcp__a-b__get_messages",
        }

        self.assertIsNone(
            claude_any._match_available_tool_name("mcp__a_b__get_messages", available)
        )

    def test_does_not_normalize_mcp_tool_segment(self):
        available = {"mcp__ai-net-http__get_messages"}

        self.assertIsNone(
            claude_any._match_available_tool_name("mcp__ai-net_http__get-messages", available)
        )

    def test_ollama_nonstream_emits_available_mcp_tool_name(self):
        source_body = {
            "model": "claude-any-ollama-gemma4-12b",
            "tools": [
                {
                    "name": "mcp__ai-net-http__list_assignments",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
            "messages": [{"role": "user", "content": "check assignments"}],
        }
        data = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "mcp__ai-net_http__list_assignments",
                            "arguments": "{}",
                        }
                    }
                ],
            }
        }

        out = claude_any.ollama_chat_to_anthropic(data, "gemma4:12b", source_body)

        self.assertEqual("tool_use", out["stop_reason"])
        self.assertEqual("mcp__ai-net-http__list_assignments", out["content"][0]["name"])


if __name__ == "__main__":
    unittest.main()
