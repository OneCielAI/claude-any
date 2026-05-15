import unittest

import claude_any


class ReviewCommandPassthroughTests(unittest.TestCase):
    def test_review_and_slash_command_tools_are_not_blocked(self):
        blocked = claude_any.resolve_blocked_tools("ollama-cloud", {})

        self.assertNotIn("SlashCommand", blocked)
        self.assertNotIn("review", blocked)
        self.assertNotIn("Review", blocked)

    def test_filter_preserves_slash_command_tool_for_non_anthropic_provider(self):
        body = {
            "tools": [
                {
                    "name": "SlashCommand",
                    "description": "Run a custom slash command",
                    "input_schema": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                    },
                },
                {
                    "name": "Read",
                    "description": "Read a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {"file_path": {"type": "string"}},
                    },
                },
                {
                    "name": "EnterWorktree",
                    "description": "Internal Claude Code worktree tool",
                    "input_schema": {"type": "object", "properties": {}},
                },
            ]
        }

        filtered = claude_any.filter_blocked_tools("ollama-cloud", {}, body)
        names = [tool["name"] for tool in filtered["tools"]]

        self.assertIn("SlashCommand", names)
        self.assertIn("Read", names)
        self.assertNotIn("EnterWorktree", names)

    def test_slash_command_tool_schema_is_forwarded_to_ollama(self):
        tools = [
            {
                "name": "SlashCommand",
                "description": "Run a custom slash command",
                "input_schema": {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"},
                        "arguments": {"type": "string"},
                    },
                },
            }
        ]

        converted = claude_any.anthropic_tools_to_ollama(tools)

        self.assertEqual("SlashCommand", converted[0]["function"]["name"])
        self.assertEqual(["command"], converted[0]["function"]["parameters"]["required"])


if __name__ == "__main__":
    unittest.main()
