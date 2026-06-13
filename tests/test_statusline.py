import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import claude_any


class StatuslineTests(unittest.TestCase):
    def run_statusline(self, env_extra: dict[str, str] | None = None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "statusline.py"
            script.write_text(claude_any.STATUSLINE_SCRIPT, encoding="utf-8")
            env = os.environ.copy()
            env.pop("CLAUDE_ANY_PROVIDER", None)
            env.pop("CLAUDE_ANY_MODEL_ALIAS", None)
            env.pop("CLAUDE_ANY_STATUSLINE_FORCE", None)
            env.update({
                "CLAUDE_ANY_CONFIG_DIR": tmp,
                "CLAUDE_ANY_STATUSLINE_ANSI": "0",
            })
            if env_extra:
                env.update(env_extra)
            session = {
                "model": {"display_name": "claude-sonnet-4-6"},
                "workspace": {"current_dir": tmp},
            }
            proc = subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(session),
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            return proc.stdout.strip()

    def test_statusline_is_silent_for_native_claude_session(self):
        self.assertEqual("", self.run_statusline())

    def test_statusline_outputs_for_claude_any_session(self):
        out = self.run_statusline({"CLAUDE_ANY_PROVIDER": "ollama-cloud", "CLAUDE_ANY_MODEL_ALIAS": "claude-any-test"})

        self.assertIn("[claude-sonnet-4-6]", out)

    def test_statusline_shows_pending_channel_queue_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "statusline.py"
            script.write_text(claude_any.STATUSLINE_SCRIPT, encoding="utf-8")
            config_dir = Path(tmp)
            (config_dir / "channel-llm-cursor.json").write_text('{"last_id":1}\n', encoding="utf-8")
            messages = [
                {"id": 1, "channel": "room", "sender_id": "a", "message": "old"},
                {"id": 2, "channel": "room", "sender_id": "a", "message": "new 1"},
                {"id": 3, "channel": "room", "sender_id": "b", "message": "new 2"},
                {"id": 4, "channel": "sys", "sender_id": "sys", "message": "sys.sse.connected"},
            ]
            (config_dir / "chat-messages.jsonl").write_text(
                "\n".join(json.dumps(item) for item in messages) + "\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_ANY_CONFIG_DIR": tmp,
                    "CLAUDE_ANY_STATUSLINE_ANSI": "0",
                    "CLAUDE_ANY_PROVIDER": "ollama-cloud",
                    "CLAUDE_ANY_MODEL_ALIAS": "claude-any-test",
                }
            )
            session = {
                "model": {"display_name": "claude-any-test"},
                "workspace": {"current_dir": tmp},
            }
            proc = subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(session),
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

        self.assertIn("channel queue 2", proc.stdout)


if __name__ == "__main__":
    unittest.main()
