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

    def test_exit_plan_permission_is_auto_allowed_when_bypass_permissions_is_active(self):
        proc = self.run_guard(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "ExitPlanMode",
                "tool_input": {"plan": "Implement the requested fix."},
            },
            {
                "CLAUDE_ANY_PROVIDER": "ollama-cloud",
                "CLAUDE_ANY_BYPASS_PERMISSIONS": "1",
            },
        )

        payload = json.loads(proc.stdout)
        output = payload["hookSpecificOutput"]
        self.assertEqual("PermissionRequest", output["hookEventName"])
        self.assertEqual("allow", output["decision"]["behavior"])
        self.assertEqual({"plan": "Implement the requested fix."}, output["decision"]["updatedInput"])

    def test_exit_plan_permission_accepts_camel_case_hook_fields(self):
        proc = self.run_guard(
            {
                "hook_event_name": "PermissionRequest",
                "toolName": "ExitPlanMode",
                "toolInput": {"plan": "Leave plan mode."},
            },
            {
                "CLAUDE_ANY_PROVIDER": "deepseek",
                "CLAUDE_ANY_BYPASS_PERMISSIONS": "true",
            },
        )

        payload = json.loads(proc.stdout)
        self.assertEqual("allow", payload["hookSpecificOutput"]["decision"]["behavior"])
        self.assertEqual({"plan": "Leave plan mode."}, payload["hookSpecificOutput"]["decision"]["updatedInput"])

    def test_exit_plan_permission_is_observed_without_bypass_permissions(self):
        proc = self.run_guard(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "ExitPlanMode",
                "tool_input": {"plan": "Implement the requested fix."},
            },
            {"CLAUDE_ANY_PROVIDER": "ollama-cloud"},
        )

        self.assertEqual("", proc.stdout.strip())
        self.assertEqual("", proc.stderr.strip())

    def test_non_plan_permission_is_not_auto_allowed_by_bypass_permissions(self):
        proc = self.run_guard(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {"command": "echo hello"},
            },
            {
                "CLAUDE_ANY_PROVIDER": "ollama-cloud",
                "CLAUDE_ANY_BYPASS_PERMISSIONS": "1",
            },
        )

        self.assertEqual("", proc.stdout.strip())
        self.assertEqual("", proc.stderr.strip())


if __name__ == "__main__":
    unittest.main()
