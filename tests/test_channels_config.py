import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import claude_any


class ChannelConfigTests(unittest.TestCase):
    def test_saved_channels_do_not_inject_native_channel_flag(self):
        cfg = {
            "claude_code": {
                "channels": ["plugin:telegram@claude-plugins-official", "server:ai-net"],
                "development_channels": False,
            }
        }
        self.assertEqual([], claude_any.claude_channel_args(cfg, []))
        self.assertFalse(claude_any.claude_channels_requested(cfg, []))

    def test_channel_passthrough_converts_channels_to_native_loading(self):
        args = claude_any.normalize_channel_passthrough(["--channels", "server:ai-net", "-p", "hello"])
        self.assertEqual(args, ["--dangerously-load-development-channels", "server:ai-net", "-p", "hello"])

    def test_channel_passthrough_leaves_development_loading_alone(self):
        args = claude_any.normalize_channel_passthrough(["--dangerously-load-development-channels", "server:ai-net"])
        self.assertEqual(args, ["--dangerously-load-development-channels", "server:ai-net"])

    def test_channels_requested_detects_external_native_passthrough(self):
        cfg = {"claude_code": {"channels": [], "development_channels": False}}
        self.assertTrue(claude_any.claude_channels_requested(cfg, ["--dangerously-load-development-channels", "server:ai-net"]))
        self.assertTrue(claude_any.claude_channels_requested(cfg, ["--channels", "plugin:fakechat@claude-plugins-official"]))

    def test_auto_discovers_mcp_servers_from_project_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "work"
            project.mkdir()
            claude_json = root / ".claude.json"
            claude_json.write_text(
                json.dumps({"projects": {str(project): {"mcpServers": {"ai-net": {"command": "node"}}}}}),
                encoding="utf-8",
            )
            specs = claude_any.auto_discovered_mcp_channel_specs([], cwd=project, home=root)
        self.assertEqual(["server:ai-net"], specs)

    def test_auto_starts_sse_servers_from_mcp_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcp_config = root / "mcp.json"
            mcp_config.write_text(
                json.dumps({"mcpServers": {"ai-net": {"type": "sse", "url": "http://example.test/sse"}}}),
                encoding="utf-8",
            )
            with mock.patch.object(claude_any, "start_channel_sse_connection", return_value={"name": "mcp-ai-net"}) as start:
                started = claude_any.auto_start_sse_channels_from_mcp_configs(["--mcp-config", str(mcp_config)], cwd=root, home=root)
        self.assertEqual([{"name": "mcp-ai-net"}], started)
        self.assertEqual("mcp-ai-net", start.call_args.args[0]["name"])
        self.assertEqual("http://example.test/sse", start.call_args.args[0]["url"])

    def test_launch_with_external_channels_defers_to_claude_native(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False}}
        with (
            mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0),
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {})),
            mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]),
            mock.patch.object(claude_any, "native_anthropic_enabled", return_value=False),
            mock.patch.object(claude_any, "ollama_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "cleanup_managed_services_for_provider"),
            mock.patch.object(claude_any, "start_router_if_needed"),
            mock.patch.object(
                claude_any,
                "env_vars",
                return_value={
                    "CLAUDE_ANY_MODEL_ALIAS": "claude-any-test",
                    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
                },
            ),
            mock.patch.object(claude_any, "install_claude_any_slash_commands"),
            mock.patch.object(claude_any, "install_tool_guard_hooks"),
            mock.patch.object(claude_any, "install_claude_any_statusline"),
            mock.patch.object(claude_any, "find_executable", return_value="claude"),
            mock.patch.object(claude_any, "run_claude_update_check"),
            mock.patch.object(claude_any, "should_attach_web_search", return_value=False),
            mock.patch.object(claude_any, "should_append_compat_prompt", return_value=False),
            mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy") as proxy,
            mock.patch.object(claude_any.subprocess, "call", return_value=0) as call,
        ):
            rc = claude_any.launch_claude(["--channels", "server:ai-net"])

        self.assertEqual(0, rc)
        proxy.assert_not_called()
        launch_cmd = call.call_args.args[0]
        self.assertIn("--dangerously-load-development-channels", launch_cmd)
        self.assertNotIn("--channels", launch_cmd)
        launch_env = call.call_args.kwargs["env"]
        self.assertNotIn("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", launch_env)

    def test_launch_without_external_channels_uses_stdin_proxy(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False}}
        with (
            mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0),
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {})),
            mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]),
            mock.patch.object(claude_any, "native_anthropic_enabled", return_value=False),
            mock.patch.object(claude_any, "ollama_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "cleanup_managed_services_for_provider"),
            mock.patch.object(claude_any, "start_router_if_needed"),
            mock.patch.object(claude_any, "auto_start_sse_channels_from_mcp_configs", return_value=[]) as auto_start,
            mock.patch.object(claude_any, "env_vars", return_value={"CLAUDE_ANY_MODEL_ALIAS": "claude-any-test"}),
            mock.patch.object(claude_any, "install_claude_any_slash_commands"),
            mock.patch.object(claude_any, "install_tool_guard_hooks"),
            mock.patch.object(claude_any, "install_claude_any_statusline"),
            mock.patch.object(claude_any, "find_executable", return_value="claude"),
            mock.patch.object(claude_any, "run_claude_update_check"),
            mock.patch.object(claude_any, "should_attach_web_search", return_value=False),
            mock.patch.object(claude_any, "should_append_compat_prompt", return_value=False),
            mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy", return_value=0) as proxy,
        ):
            rc = claude_any.launch_claude([])

        self.assertEqual(0, rc)
        auto_start.assert_called_once_with([])
        launch_cmd = proxy.call_args.args[0]
        self.assertNotIn("--dangerously-load-development-channels", launch_cmd)

    def test_channels_command_toggles_official_plugin(self):
        cfg = {
            "claude_code": {
                "channels": [],
                "development_channels": False,
            },
            "providers": {},
        }
        with mock.patch.object(claude_any, "load_config", return_value=cfg), mock.patch.object(claude_any, "save_config"):
            lines = claude_any.add_channel_spec("plugin:discord@claude-plugins-official")
        self.assertIn("plugin:discord@claude-plugins-official", cfg["claude_code"]["channels"])
        self.assertTrue(lines[0].startswith("Channel added"))

    def test_channels_command_rejects_untagged_spec(self):
        cfg = {
            "claude_code": {
                "channels": [],
                "development_channels": False,
            },
            "providers": {},
        }
        with mock.patch.object(claude_any, "load_config", return_value=cfg), mock.patch.object(claude_any, "save_config") as save:
            lines = claude_any.add_channel_spec("ainet")
        self.assertEqual(["Channel spec must start with plugin: or server:."], lines)
        self.assertEqual([], cfg["claude_code"]["channels"])
        save.assert_not_called()

    def test_development_channel_alias_adds_channel_without_persisting_obsolete_toggle(self):
        cfg = {
            "claude_code": {
                "channels": [],
                "development_channels": False,
            },
            "providers": {},
        }
        with mock.patch.object(claude_any, "load_config", return_value=cfg), mock.patch.object(claude_any, "save_config"):
            claude_any.add_channel_spec("plugin:ainet@local", development=True)
        self.assertEqual(["plugin:ainet@local"], cfg["claude_code"]["channels"])
        self.assertFalse(cfg["claude_code"]["development_channels"])


if __name__ == "__main__":
    unittest.main()
