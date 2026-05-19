import unittest
from unittest import mock

import claude_any


class ChannelConfigTests(unittest.TestCase):
    def test_channel_args_are_injected_for_saved_channels(self):
        cfg = {
            "claude_code": {
                "channels": ["plugin:telegram@claude-plugins-official", "plugin:ainet@local"],
                "development_channels": False,
            }
        }
        args = claude_any.claude_channel_args(cfg, [])
        self.assertEqual(
            args,
            [
                "--dangerously-load-development-channels",
                "plugin:telegram@claude-plugins-official",
                "plugin:ainet@local",
            ],
        )

    def test_channel_passthrough_converts_channels_to_wake_capable_loading(self):
        args = claude_any.normalize_channel_passthrough(["--channels", "server:ai-net", "-p", "hello"])
        self.assertEqual(args, ["--dangerously-load-development-channels", "server:ai-net", "-p", "hello"])

    def test_channel_passthrough_leaves_development_loading_alone(self):
        args = claude_any.normalize_channel_passthrough(["--dangerously-load-development-channels", "server:ai-net"])
        self.assertEqual(args, ["--dangerously-load-development-channels", "server:ai-net"])

    def test_channel_args_do_not_override_native_passthrough(self):
        cfg = {
            "claude_code": {
                "channels": ["plugin:telegram@claude-plugins-official"],
                "development_channels": True,
            }
        }
        self.assertEqual([], claude_any.claude_channel_args(cfg, ["--channels", "plugin:discord@claude-plugins-official"]))

    def test_channel_args_do_not_override_native_development_passthrough(self):
        cfg = {
            "claude_code": {
                "channels": ["plugin:telegram@claude-plugins-official"],
                "development_channels": True,
            }
        }
        self.assertEqual(
            [],
            claude_any.claude_channel_args(
                cfg,
                ["--dangerously-load-development-channels", "plugin:custom@local"],
            ),
        )

    def test_channels_requested_detects_native_passthrough(self):
        cfg = {"claude_code": {"channels": [], "development_channels": False}}
        self.assertTrue(claude_any.claude_channels_requested(cfg, ["--dangerously-load-development-channels", "server:ai-net"]))
        self.assertTrue(claude_any.claude_channels_requested(cfg, ["--channels", "plugin:fakechat@claude-plugins-official"]))

    def test_channels_requested_detects_saved_channels(self):
        cfg = {"claude_code": {"channels": ["server:ai-net"], "development_channels": True}}
        self.assertTrue(claude_any.claude_channels_requested(cfg, []))

    def test_channels_requested_ignores_empty_or_untagged_saved_channels(self):
        cfg = {"claude_code": {"channels": ["ai-net"], "development_channels": True}}
        self.assertFalse(claude_any.claude_channels_requested(cfg, []))

    def test_launch_with_channels_does_not_disable_experimental_betas(self):
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
            mock.patch.object(claude_any.subprocess, "call", return_value=0) as call,
        ):
            rc = claude_any.launch_claude(["--channels", "server:ai-net"])

        self.assertEqual(0, rc)
        launch_cmd = call.call_args.args[0]
        self.assertIn("--dangerously-load-development-channels", launch_cmd)
        self.assertNotIn("--channels", launch_cmd)
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

    def test_development_channel_enables_development_flag(self):
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
        self.assertTrue(cfg["claude_code"]["development_channels"])


if __name__ == "__main__":
    unittest.main()
