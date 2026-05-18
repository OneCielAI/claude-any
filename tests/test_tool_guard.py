import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "claude-any-tool-guard.py"


class ToolGuardTests(unittest.TestCase):
    def run_guard(self, event: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("CLAUDE_ANY_PROVIDER", None)
            env["HOME"] = tmp
            env["USERPROFILE"] = tmp
            if env_extra:
                env.update(env_extra)
            return subprocess.run(
                [sys.executable, str(GUARD)],
                input=json.dumps(event),
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

    def test_guard_is_silent_for_native_worktree_hook(self):
        proc = self.run_guard({"hook_event_name": "WorktreeCreate", "cwd": "/tmp/project"})

        self.assertEqual("", proc.stdout.strip())
        self.assertEqual("", proc.stderr.strip())

    def test_guard_handles_worktree_hook_for_claude_any_provider(self):
        proc = self.run_guard(
            {"hook_event_name": "WorktreeCreate", "cwd": "/tmp/project"},
            {"CLAUDE_ANY_PROVIDER": "ollama-cloud"},
        )

        payload = json.loads(proc.stdout)
        self.assertEqual("/tmp/project", payload["hookSpecificOutput"]["worktreePath"])


if __name__ == "__main__":
    unittest.main()
