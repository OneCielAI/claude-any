import json
import os
import tempfile
import unittest
from contextlib import ExitStack
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

    def test_channel_delivery_mode_supports_native_bridge(self):
        cfg = {"claude_code": {"channel_delivery": "native"}}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_ANY_CHANNEL_DELIVERY", None)
            self.assertEqual("native", claude_any.channel_delivery_mode(cfg))
            self.assertTrue(claude_any.should_use_native_channel_bridge(True, cfg, []))
            self.assertFalse(claude_any.should_use_channel_stdin_proxy(True, [], cfg))

    def test_prelaunch_menu_rows_show_channel_delivery(self):
        cfg = {"language": "en", "current_provider": "ollama-cloud", "claude_code": {"channel_delivery": "native"}}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_ANY_CHANNEL_DELIVERY", None)
            rows = claude_any.main_menu_rows(cfg, "ollama-cloud", {"current_model": "m", "advisor_model": ""}, "en")
            self.assertIn("7. Channel delivery  [native]", rows)
            delivery_rows, delivery_values = claude_any.channel_delivery_panel_rows(cfg)
            self.assertEqual(["stdin", "native", "back"], delivery_values)
            self.assertTrue(any(row.startswith("* native") for row in delivery_rows))

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

    def test_mcp_proxy_config_wraps_stdio_server(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcp_config = root / "mcp.json"
            proxy_config = root / "mcp-proxy.json"
            mcp_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "ai-net": {"command": "node", "args": ["server.js"], "env": {"TOKEN": "x"}},
                            "remote": {"type": "sse", "url": "http://example.test/sse"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(claude_any, "CONFIG_DIR", root), mock.patch.object(claude_any, "MCP_PROXY_CONFIG", proxy_config):
                written = claude_any.write_mcp_proxy_config(["--mcp-config", str(mcp_config)], cwd=root, home=root)

            self.assertEqual(proxy_config, written)
            data = json.loads(proxy_config.read_text(encoding="utf-8"))
            wrapped = data["mcpServers"]["ai-net"]
            self.assertEqual(claude_any.sys.executable, wrapped["command"])
            self.assertIn("mcp-proxy", wrapped["args"])
            self.assertIn("--server-name", wrapped["args"])
            self.assertIn("ai-net", wrapped["args"])
            self.assertEqual("sse", data["mcpServers"]["remote"]["type"])
            server_config_path = Path(wrapped["args"][wrapped["args"].index("--server-config") + 1])
            saved_server = json.loads(server_config_path.read_text(encoding="utf-8"))
            self.assertEqual("node", saved_server["command"])

    def test_strip_mcp_config_passthrough_removes_all_values(self):
        args = claude_any.strip_mcp_config_passthrough(["--mcp-config", "a.json", "b.json", "-p", "hello"])
        self.assertEqual(["-p", "hello"], args)

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
            mock.patch.object(claude_any, "write_mcp_proxy_config", return_value=None),
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
            mock.patch.object(claude_any, "write_mcp_proxy_config", return_value=None) as proxy_config,
            mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy", return_value=0) as proxy,
        ):
            rc = claude_any.launch_claude([])

        self.assertEqual(0, rc)
        auto_start.assert_called_once_with([])
        proxy_config.assert_called_once()
        launch_cmd = proxy.call_args.args[0]
        self.assertNotIn("--dangerously-load-development-channels", launch_cmd)

    def test_launch_without_external_channels_uses_generated_mcp_proxy_config(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False}}
        with tempfile.TemporaryDirectory() as td:
            proxy_path = Path(td) / "mcp-proxy.json"
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0))
                stack.enter_context(mock.patch.object(claude_any, "load_config", return_value=cfg))
                stack.enter_context(mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {})))
                stack.enter_context(mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]))
                stack.enter_context(mock.patch.object(claude_any, "native_anthropic_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "ollama_native_compat_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "cleanup_managed_services_for_provider"))
                stack.enter_context(mock.patch.object(claude_any, "start_router_if_needed"))
                stack.enter_context(mock.patch.object(claude_any, "auto_start_sse_channels_from_mcp_configs", return_value=[]))
                stack.enter_context(mock.patch.object(claude_any, "env_vars", return_value={"CLAUDE_ANY_MODEL_ALIAS": "claude-any-test"}))
                stack.enter_context(mock.patch.object(claude_any, "install_claude_any_slash_commands"))
                stack.enter_context(mock.patch.object(claude_any, "install_tool_guard_hooks"))
                stack.enter_context(mock.patch.object(claude_any, "install_claude_any_statusline"))
                stack.enter_context(mock.patch.object(claude_any, "find_executable", return_value="claude"))
                stack.enter_context(mock.patch.object(claude_any, "run_claude_update_check"))
                stack.enter_context(mock.patch.object(claude_any, "should_attach_web_search", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "should_append_compat_prompt", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "write_mcp_proxy_config", return_value=proxy_path))
                proxy = stack.enter_context(mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy", return_value=0))
                rc = claude_any.launch_claude(["--mcp-config", "original.json", "-p", "hello"])

        self.assertEqual(0, rc)
        launch_cmd = proxy.call_args.args[0]
        self.assertIn("--mcp-config", launch_cmd)
        self.assertIn(str(proxy_path), launch_cmd)
        self.assertNotIn("original.json", launch_cmd)
        self.assertIn("-p", launch_cmd)

    def test_launch_with_native_channel_bridge_uses_router_mcp_not_pty(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False, "channel_delivery": "native"}}
        with tempfile.TemporaryDirectory() as td:
            channel_path = Path(td) / "channel-mcp.json"
            proxy_path = Path(td) / "mcp-proxy.json"
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0))
                stack.enter_context(mock.patch.object(claude_any, "load_config", return_value=cfg))
                stack.enter_context(mock.patch.object(claude_any, "get_current_provider", return_value=("ollama-cloud", {})))
                stack.enter_context(mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]))
                stack.enter_context(mock.patch.object(claude_any, "native_anthropic_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "ollama_native_compat_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "cleanup_managed_services_for_provider"))
                stack.enter_context(mock.patch.object(claude_any, "start_router_if_needed"))
                stack.enter_context(mock.patch.object(claude_any, "auto_start_sse_channels_from_mcp_configs", return_value=[]))
                stack.enter_context(mock.patch.object(claude_any, "env_vars", return_value={"CLAUDE_ANY_MODEL_ALIAS": "claude-any-test", "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1"}))
                stack.enter_context(mock.patch.object(claude_any, "install_claude_any_slash_commands"))
                stack.enter_context(mock.patch.object(claude_any, "install_tool_guard_hooks"))
                stack.enter_context(mock.patch.object(claude_any, "install_claude_any_statusline"))
                stack.enter_context(mock.patch.object(claude_any, "find_executable", return_value="claude"))
                stack.enter_context(mock.patch.object(claude_any, "run_claude_update_check"))
                stack.enter_context(mock.patch.object(claude_any, "should_attach_web_search", return_value=False))
                stack.enter_context(mock.patch.object(claude_any, "should_append_compat_prompt", return_value=False))
                write_channel = stack.enter_context(mock.patch.object(claude_any, "write_channel_mcp_config", return_value=channel_path))
                write_proxy = stack.enter_context(mock.patch.object(claude_any, "write_mcp_proxy_config", return_value=proxy_path))
                proxy = stack.enter_context(mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy", return_value=0))
                call = stack.enter_context(mock.patch.object(claude_any.subprocess, "call", return_value=0))
                rc = claude_any.launch_claude(["--mcp-config", "original.json"])

        self.assertEqual(0, rc)
        write_channel.assert_called_once()
        extra_paths = write_proxy.call_args.kwargs["extra_config_paths"]
        self.assertIn(channel_path, extra_paths)
        proxy.assert_not_called()
        launch_cmd = call.call_args.args[0]
        self.assertIn("--mcp-config", launch_cmd)
        self.assertIn(str(proxy_path), launch_cmd)
        self.assertNotIn("original.json", launch_cmd)
        launch_env = call.call_args.kwargs["env"]
        self.assertNotIn("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", launch_env)

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
