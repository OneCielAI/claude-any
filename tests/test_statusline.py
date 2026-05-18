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


if __name__ == "__main__":
    unittest.main()
