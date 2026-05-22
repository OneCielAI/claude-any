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

    def test_channel_delivery_mode_defaults_to_native_bridge(self):
        cfg = {"claude_code": {}}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_ANY_CHANNEL_DELIVERY", None)
            self.assertEqual("native", claude_any.channel_delivery_mode(cfg))
            self.assertTrue(claude_any.should_use_native_channel_bridge(True, cfg, []))
            self.assertFalse(claude_any.should_use_channel_stdin_proxy(True, [], cfg))

    def test_channel_delivery_migration_moves_old_default_to_native(self):
        cfg = {"migrations": {}, "claude_code": {"channel_delivery": "stdin"}, "providers": {}}
        claude_any.apply_config_migrations(cfg)
        self.assertEqual("native", cfg["claude_code"]["channel_delivery"])
        self.assertTrue(cfg["migrations"]["default_channel_delivery_native_20260520"])

    def test_prelaunch_menu_rows_show_channel_delivery(self):
        cfg = {"language": "en", "current_provider": "ollama-cloud", "claude_code": {"channel_delivery": "native"}}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_ANY_CHANNEL_DELIVERY", None)
            rows = claude_any.main_menu_rows(cfg, "ollama-cloud", {"current_model": "m", "advisor_model": ""}, "en")
            self.assertIn("7. Channel delivery  [native]", rows)
            delivery_rows, delivery_values = claude_any.channel_delivery_panel_rows(cfg)
            self.assertEqual(["native", "stdin", "back"], delivery_values)
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

    def test_web_fetch_mcp_config_marks_jsonl_stdio(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "web-tools-mcp.json"
            with (
                mock.patch.object(claude_any, "CONFIG_DIR", root),
                mock.patch.object(claude_any, "WEB_TOOLS_MCP_CONFIG", path),
                mock.patch.object(claude_any, "find_executable", side_effect=lambda name: f"/bin/{name}"),
            ):
                written = claude_any.write_web_tools_mcp_config({"web_search": {"fetch_enabled": True}})
            self.assertEqual(path, written)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("jsonl", data["mcpServers"]["web_fetch"]["claude_any_stdio"])

    def test_web_fetch_mcp_config_falls_back_to_uv_tool_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "web-tools-mcp.json"

            def fake_find(name):
                return "/bin/uv" if name == "uv" else None

            with (
                mock.patch.object(claude_any, "CONFIG_DIR", root),
                mock.patch.object(claude_any, "WEB_TOOLS_MCP_CONFIG", path),
                mock.patch.object(claude_any, "find_executable", side_effect=fake_find),
            ):
                claude_any.write_web_tools_mcp_config({"web_search": {"fetch_enabled": True}})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("/bin/uv", data["mcpServers"]["web_fetch"]["command"])
            self.assertEqual(["tool", "run", "mcp-server-fetch"], data["mcpServers"]["web_fetch"]["args"])

    def test_web_fetch_mcp_config_skips_fetch_when_no_python_runner_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "web-tools-mcp.json"
            with (
                mock.patch.object(claude_any, "CONFIG_DIR", root),
                mock.patch.object(claude_any, "WEB_TOOLS_MCP_CONFIG", path),
                mock.patch.object(claude_any, "find_executable", return_value=None),
                mock.patch.object(claude_any.importlib.util, "find_spec", return_value=None),
                mock.patch.object(claude_any, "router_log") as log,
            ):
                claude_any.write_web_tools_mcp_config({"web_search": {"fetch_enabled": True}})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("web_fetch", data["mcpServers"])
            self.assertIn("duckduckgo", data["mcpServers"])
            self.assertTrue(any("web_fetch_disabled_missing_runner" in call.args[1] for call in log.call_args_list))

    def test_mcp_proxy_resolves_legacy_uvx_config_to_uv_tool_run(self):
        def fake_find(name):
            return "/bin/uv" if name == "uv" else None

        with mock.patch.object(claude_any, "find_executable", side_effect=fake_find):
            command, args = claude_any.resolve_mcp_server_process("uvx", ["mcp-server-fetch"])
        self.assertEqual("/bin/uv", command)
        self.assertEqual(["tool", "run", "mcp-server-fetch"], args)

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

    def test_launch_without_external_channels_uses_stdin_proxy_when_selected(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False, "channel_delivery": "stdin"}}
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

    def test_launch_without_external_channels_uses_generated_mcp_proxy_config_for_stdin(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False, "channel_delivery": "stdin"}}
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

    def test_launch_with_native_channel_bridge_uses_router_mcp_not_pty_by_default(self):
        cfg = {"providers": {}, "claude_code": {"channels": [], "development_channels": False}}
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


class PassthroughChannelImportTests(unittest.TestCase):
    def test_parse_extracts_channels_and_dangerously_loaded_specs(self):
        specs = claude_any.parse_passthrough_channel_specs([
            "--channels",
            "server:ai-net",
            "plugin:fakechat@claude-plugins-official",
            "-p",
            "hi",
            "--dangerously-load-development-channels",
            "server:other",
        ])
        self.assertEqual(
            [
                "server:ai-net",
                "plugin:fakechat@claude-plugins-official",
                "server:other",
            ],
            specs,
        )

    def test_parse_extracts_inline_equals_form(self):
        specs = claude_any.parse_passthrough_channel_specs([
            "--channels=server:ai-net",
            "--dangerously-load-development-channels=plugin:telegram@claude-plugins-official",
        ])
        self.assertEqual(
            ["server:ai-net", "plugin:telegram@claude-plugins-official"],
            specs,
        )

    def test_parse_skips_unrelated_args(self):
        self.assertEqual([], claude_any.parse_passthrough_channel_specs(["-p", "hi", "--model", "x"]))

    def test_parse_ignores_untagged_values(self):
        # A bare token after --channels that does not look like a channel spec
        # must not be misinterpreted as a spec.
        specs = claude_any.parse_passthrough_channel_specs(["--channels", "just-a-word"])
        self.assertEqual([], specs)

    def test_auto_import_adds_new_specs(self):
        cfg = {"claude_code": {"channels": []}, "providers": {}}
        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config") as save,
            mock.patch.object(claude_any, "invalidate_config_cache"),
            mock.patch.object(claude_any, "router_log"),
        ):
            added = claude_any.auto_import_passthrough_channels(["--channels", "server:ai-net"])
        self.assertEqual(["server:ai-net"], added)
        self.assertEqual(["server:ai-net"], cfg["claude_code"]["channels"])
        save.assert_called_once()

    def test_auto_import_skips_already_present_specs(self):
        cfg = {"claude_code": {"channels": ["server:ai-net"]}, "providers": {}}
        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config") as save,
            mock.patch.object(claude_any, "invalidate_config_cache"),
            mock.patch.object(claude_any, "router_log"),
        ):
            added = claude_any.auto_import_passthrough_channels(["--channels", "server:ai-net"])
        self.assertEqual([], added)
        save.assert_not_called()

    def test_auto_import_noop_for_empty_passthrough(self):
        with (
            mock.patch.object(claude_any, "load_config") as load,
            mock.patch.object(claude_any, "save_config") as save,
        ):
            self.assertEqual([], claude_any.auto_import_passthrough_channels([]))
        load.assert_not_called()
        save.assert_not_called()


class ChannelProbeCacheTests(unittest.TestCase):
    def _isolate_cache(self, stack, td):
        root = Path(td)
        stack.enter_context(mock.patch.object(claude_any, "CONFIG_DIR", root))
        stack.enter_context(mock.patch.object(claude_any, "CHANNEL_PROBE_CACHE_PATH", root / "channel-probe-cache.json"))
        stack.enter_context(mock.patch.object(claude_any, "router_log"))
        return root

    def test_cache_read_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            self._isolate_cache(stack, td)
            data = claude_any.read_channel_probe_cache()
        self.assertEqual([], data["servers"])
        self.assertEqual(0.0, data["probed_at"])

    def test_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            root = self._isolate_cache(stack, td)
            cache = {
                "version": 1,
                "probed_at": 1700000000.0,
                "servers": [
                    {"name": "ai-net", "capable": True, "transport": "stdio", "source_path": str(root / ".mcp.json")},
                ],
            }
            claude_any._write_channel_probe_cache(cache)
            data = claude_any.read_channel_probe_cache()
        self.assertEqual(1700000000.0, data["probed_at"])
        self.assertEqual("ai-net", data["servers"][0]["name"])

    def test_cached_capable_names_always_includes_router_self(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            self._isolate_cache(stack, td)
            # Empty cache → only built-in router.
            self.assertEqual(["claude-any-router"], claude_any.cached_channel_capable_server_names())

    def test_cached_capable_names_returns_capable_plus_router(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            self._isolate_cache(stack, td)
            claude_any._write_channel_probe_cache({
                "version": 1,
                "probed_at": 1700000000.0,
                "servers": [
                    {"name": "ai-net", "capable": True, "transport": "stdio"},
                    {"name": "boring", "capable": False, "transport": "stdio"},
                ],
            })
            names = claude_any.cached_channel_capable_server_names()
        self.assertIn("claude-any-router", names)
        self.assertIn("ai-net", names)
        self.assertNotIn("boring", names)

    def test_probe_records_include_router_self_and_skip_recursion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps({
                    "mcpServers": {
                        "ai-net": {"command": "node", "args": ["server.js"]},
                        "sse-only": {"type": "sse", "url": "http://example.test/sse"},
                    }
                }),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    claude_any,
                    "probe_stdio_mcp_for_channel_capability_detailed",
                    return_value={
                        "capable": True,
                        "reason": "capable",
                        "response_bytes": 256,
                        "response_received": True,
                        "elapsed_ms": 800,
                    },
                ) as stdio_probe,
                mock.patch.object(
                    claude_any,
                    "probe_sse_mcp_for_channel_capability_detailed",
                    return_value={
                        "capable": True,
                        "reason": "capable",
                        "response_bytes": 512,
                        "response_received": True,
                        "elapsed_ms": 400,
                    },
                ) as sse_probe,
            ):
                records = claude_any._probe_mcp_servers_to_records([str(mcp_config)], root)
        names = {r["name"] for r in records}
        self.assertIn("claude-any-router", names)
        self.assertIn("ai-net", names)
        self.assertIn("sse-only", names)
        # Non-router stdio server is probed via stdio, sse-only via SSE.
        self.assertEqual(1, stdio_probe.call_count)
        self.assertEqual(1, sse_probe.call_count)
        ai_net_record = next(r for r in records if r["name"] == "ai-net")
        self.assertTrue(ai_net_record["capable"])
        self.assertEqual("capable", ai_net_record["reason"])
        sse_record = next(r for r in records if r["name"] == "sse-only")
        self.assertTrue(sse_record["capable"])
        self.assertEqual("capable", sse_record["reason"])

    def test_refresh_writes_cache_with_capable_server(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            root = self._isolate_cache(stack, td)
            project = root / "work"
            project.mkdir()
            mcp_config = project / ".mcp.json"
            mcp_config.write_text(
                json.dumps({"mcpServers": {"ai-net": {"command": "node", "args": ["server.js"]}}}),
                encoding="utf-8",
            )
            stack.enter_context(
                mock.patch.object(
                    claude_any,
                    "probe_stdio_mcp_for_channel_capability_detailed",
                    return_value={
                        "capable": True,
                        "reason": "capable",
                        "response_bytes": 128,
                        "response_received": True,
                        "elapsed_ms": 500,
                    },
                )
            )
            result = claude_any.refresh_channel_probe_cache(cwd=project, home=root)
        self.assertGreater(result["probed_at"], 0)
        names = {r["name"] for r in result["servers"]}
        self.assertIn("claude-any-router", names)
        self.assertIn("ai-net", names)

    def test_panel_rows_show_auto_detected_section(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            self._isolate_cache(stack, td)
            claude_any._write_channel_probe_cache({
                "version": 1,
                "probed_at": 1700000000.0,
                "servers": [
                    {"name": "ai-net", "capable": True, "transport": "stdio"},
                    {"name": "boring", "capable": False, "transport": "stdio", "reason": "timeout"},
                ],
            })
            cfg = {"claude_code": {"channels": ["server:ai-net"]}}
            rows, values = claude_any.channel_panel_rows(cfg)
        self.assertIn("[Auto-detected channel-capable]", rows)
        self.assertIn("[Detected but not channel-capable]", rows)
        # ai-net should appear as a selected spec (* mark).
        self.assertTrue(any("server:ai-net" == v for v in values))
        ai_row = rows[values.index("server:ai-net")]
        self.assertTrue(ai_row.startswith("*"))
        # Headings and noop placeholders must not be selectable on Enter.
        first_selectable = claude_any._channel_panel_first_selectable(values)
        self.assertNotIn(values[first_selectable], ("__heading__", "__noop__"))
        # The Re-probe action must be present.
        self.assertIn("__reprobe__", values)
        # The reason from the detailed probe must surface to the user
        # (so they can see whether it was timeout vs missing capability).
        self.assertTrue(any("timeout" in row for row in rows))


class ChannelProbeDetailedReasonTests(unittest.TestCase):
    def test_default_timeout_can_be_overridden_via_env(self):
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_PROBE_TIMEOUT_SECONDS": "42"}, clear=False):
            self.assertEqual(42.0, claude_any.channel_probe_default_timeout())
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_PROBE_TIMEOUT_SECONDS": "garbage"}, clear=False):
            self.assertEqual(
                claude_any.CHANNEL_PROBE_DEFAULT_TIMEOUT_SECONDS,
                claude_any.channel_probe_default_timeout(),
            )
        with mock.patch.dict(os.environ, {"CLAUDE_ANY_CHANNEL_PROBE_TIMEOUT_SECONDS": "-1"}, clear=False):
            self.assertEqual(
                claude_any.CHANNEL_PROBE_DEFAULT_TIMEOUT_SECONDS,
                claude_any.channel_probe_default_timeout(),
            )

    def test_default_timeout_is_at_least_ten_seconds(self):
        # The default must be large enough for typical npx/tsx cold start;
        # users testing remote MCP servers complained that 3s was too short.
        self.assertGreaterEqual(claude_any.CHANNEL_PROBE_DEFAULT_TIMEOUT_SECONDS, 10.0)

    def test_records_carry_stderr_preview_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps({"mcpServers": {"crashy": {"command": "node", "args": ["server.js"]}}}),
                encoding="utf-8",
            )
            stderr_text = "ReferenceError: AINET_BASE_URL is not defined\n  at server.js:42"
            with mock.patch.object(
                claude_any,
                "probe_stdio_mcp_for_channel_capability_detailed",
                return_value={
                    "capable": False,
                    "reason": "exited_without_response",
                    "response_bytes": 0,
                    "response_received": False,
                    "exit_code": 1,
                    "stderr_bytes": len(stderr_text),
                    "stderr_preview": stderr_text,
                    "stdout_preview": "",
                    "elapsed_ms": 380,
                },
            ):
                records = claude_any._probe_mcp_servers_to_records([str(mcp_config)], root)
        crashy = next(r for r in records if r["name"] == "crashy")
        self.assertEqual("exited_without_response", crashy["reason"])
        self.assertEqual(1, crashy["exit_code"])
        self.assertIn("ReferenceError", crashy["stderr_preview"])

    def test_records_carry_detailed_reason_from_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps({"mcpServers": {"slow-net": {"command": "node", "args": ["server.js"]}}}),
                encoding="utf-8",
            )
            with mock.patch.object(
                claude_any,
                "probe_stdio_mcp_for_channel_capability_detailed",
                return_value={
                    "capable": False,
                    "reason": "timeout",
                    "response_bytes": 0,
                    "response_received": False,
                    "elapsed_ms": 15000,
                },
            ):
                records = claude_any._probe_mcp_servers_to_records([str(mcp_config)], root)
        slow = next(r for r in records if r["name"] == "slow-net")
        self.assertFalse(slow["capable"])
        self.assertEqual("timeout", slow["reason"])
        self.assertEqual(15000, slow["elapsed_ms"])
        self.assertFalse(slow["response_received"])


class _FakeSSEResponse:
    """Imitates the file-like object urlopen returns for SSE GETs."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)
        self._closed = False

    def read(self, _n: int = -1) -> bytes:
        if self._closed:
            return b""
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def close(self) -> None:
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _FakePostResponse:
    def read(self) -> bytes:
        return b""

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ChannelProbeSSETests(unittest.TestCase):
    def test_sse_event_parser_splits_messages_and_endpoint(self):
        events, leftover = claude_any._decode_sse_events(
            bytearray(
                b"event: endpoint\r\ndata: /messages?session=abc\r\n\r\n"
                b"data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n"
                b"data: incomplete"
            )
        )
        self.assertEqual(("endpoint", "/messages?session=abc"), events[0])
        self.assertEqual("message", events[1][0])
        self.assertIn("jsonrpc", events[1][1])
        # Trailing partial event stays in the buffer.
        self.assertIn(b"incomplete", bytes(leftover))

    def _build_sse_capable_response(self) -> _FakeSSEResponse:
        init_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"experimental": {"claude/channel": {}}},
                "serverInfo": {"name": "fake", "version": "0.0.1"},
            },
        })
        return _FakeSSEResponse([
            b"event: endpoint\ndata: /messages?session=xyz\n\n",
            f"data: {init_response}\n\n".encode("utf-8"),
        ])

    def _build_sse_no_capability_response(self) -> _FakeSSEResponse:
        init_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "serverInfo": {"name": "fake", "version": "0.0.1"},
            },
        })
        return _FakeSSEResponse([
            b"event: endpoint\ndata: /messages?session=xyz\n\n",
            f"data: {init_response}\n\n".encode("utf-8"),
        ])

    def test_sse_probe_reports_capable(self):
        get_resp = self._build_sse_capable_response()
        post_resp = _FakePostResponse()

        def fake_urlopen(req, timeout=None):
            method = getattr(req, "get_method", lambda: "GET")()
            return get_resp if method == "GET" else post_resp

        with mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=fake_urlopen):
            detail = claude_any.probe_sse_mcp_for_channel_capability_detailed(
                "fake-sse",
                {"type": "sse", "url": "http://example.test/sse"},
                timeout=3.0,
            )
        self.assertTrue(detail["capable"])
        self.assertEqual("capable", detail["reason"])
        self.assertTrue(detail["response_received"])

    def test_sse_probe_reports_no_capability_when_absent(self):
        get_resp = self._build_sse_no_capability_response()
        post_resp = _FakePostResponse()

        def fake_urlopen(req, timeout=None):
            method = getattr(req, "get_method", lambda: "GET")()
            return get_resp if method == "GET" else post_resp

        with mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=fake_urlopen):
            detail = claude_any.probe_sse_mcp_for_channel_capability_detailed(
                "fake-sse",
                {"type": "sse", "url": "http://example.test/sse"},
                timeout=3.0,
            )
        self.assertFalse(detail["capable"])
        self.assertEqual("no_experimental_claude_channel", detail["reason"])

    def test_sse_probe_times_out_when_no_endpoint_event(self):
        # SSE stream that emits a heartbeat comment but never an endpoint event.
        get_resp = _FakeSSEResponse([b": heartbeat\n\n"])

        def fake_urlopen(req, timeout=None):
            method = getattr(req, "get_method", lambda: "GET")()
            if method == "GET":
                return get_resp
            return _FakePostResponse()

        with mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=fake_urlopen):
            detail = claude_any.probe_sse_mcp_for_channel_capability_detailed(
                "fake-sse",
                {"type": "sse", "url": "http://example.test/sse"},
                timeout=0.3,
            )
        self.assertFalse(detail["capable"])
        self.assertEqual("timeout_no_endpoint_event", detail["reason"])

    def test_sse_probe_handles_open_failure(self):
        def fake_urlopen(req, timeout=None):
            raise __import__("urllib").error.URLError("connection refused")

        with mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=fake_urlopen):
            detail = claude_any.probe_sse_mcp_for_channel_capability_detailed(
                "fake-sse",
                {"type": "sse", "url": "http://example.test/sse"},
                timeout=2.0,
            )
        self.assertFalse(detail["capable"])
        self.assertTrue(detail["reason"].startswith("sse_open_failed:"))
        self.assertIn("connection refused", detail["stderr_preview"])

    def test_sse_probe_handles_no_url(self):
        detail = claude_any.probe_sse_mcp_for_channel_capability_detailed(
            "fake-sse",
            {"type": "sse"},
            timeout=2.0,
        )
        self.assertFalse(detail["capable"])
        self.assertEqual("no_url", detail["reason"])


if __name__ == "__main__":
    unittest.main()
