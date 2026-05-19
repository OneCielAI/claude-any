import unittest
from unittest import mock

import claude_any


class ChannelConfigTests(unittest.TestCase):
    def test_channel_args_are_injected_for_saved_channels(self):
        cfg = {
            "claude_code": {
                "channels": ["plugin:telegram@claude-plugins-official", "plugin:ainet@local"],
                "development_channels": True,
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
