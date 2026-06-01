import io
import unittest
from pathlib import Path
from unittest import mock

import claude_any


class InstallDiagnosticsTests(unittest.TestCase):
    def test_package_root_from_installed_path(self):
        root = Path("/usr/local/lib/node_modules/@oneciel-ai/claude-any")
        launcher = root / "npm-bin" / "claude-any.js"

        self.assertEqual(root.resolve(strict=False), claude_any.package_root_from_installed_path(launcher))

    def test_warns_when_newer_install_is_shadowed(self):
        rows = [
            {
                "launcher": "/usr/local/bin/claude-any",
                "resolved": "/usr/local/lib/node_modules/@oneciel-ai/claude-any/npm-bin/claude-any.js",
                "package_root": "/usr/local/lib/node_modules/@oneciel-ai/claude-any",
                "version": "0.1.104-nightly.20260531-070027.bb412de",
            },
            {
                "launcher": "/home/user/.local/bin/claude-any",
                "resolved": "/home/user/.local/lib/node_modules/@oneciel-ai/claude-any/npm-bin/claude-any.js",
                "package_root": "/home/user/.local/lib/node_modules/@oneciel-ai/claude-any",
                "version": "0.1.104-nightly.20260601-012855.916d3dc",
            },
        ]
        stderr = io.StringIO()

        with mock.patch.object(claude_any, "claude_any_install_diagnostics", return_value=rows), mock.patch.object(
            claude_any, "current_npm_package_root", return_value=Path(rows[0]["package_root"])
        ), mock.patch.object(claude_any.sys.stdin, "isatty", return_value=True), mock.patch.object(
            claude_any.sys.stdout, "isatty", return_value=True
        ), mock.patch.object(
            claude_any.sys, "stderr", stderr
        ):
            claude_any.warn_if_multiple_claude_any_installs()

        text = stderr.getvalue()
        self.assertIn("multiple claude-any npm installs", text)
        self.assertIn("/usr/local/bin/claude-any", text)
        self.assertIn("/home/user/.local/bin/claude-any", text)
        self.assertIn("0.1.104-nightly.20260601-012855.916d3dc", text)


if __name__ == "__main__":
    unittest.main()
