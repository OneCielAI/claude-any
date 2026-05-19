import unittest
from unittest.mock import patch

import claude_any


class HeadlessUpdateCheckTests(unittest.TestCase):
    def test_print_mode_disables_update_prompts(self):
        patches = [
            patch("claude_any.run_prelaunch_menu", return_value=0),
            patch("claude_any.load_config", return_value={}),
            patch("claude_any.get_current_provider", return_value=("anthropic", {})),
            patch("claude_any.launch_readiness_errors", return_value=[]),
            patch("claude_any.native_anthropic_enabled", return_value=True),
            patch("claude_any.ollama_native_compat_enabled", return_value=False),
            patch("claude_any.provider_native_compat_enabled", return_value=False),
            patch("claude_any.cleanup_managed_services_for_provider"),
            patch("claude_any.env_vars", return_value={}),
            patch("claude_any.find_executable", return_value="claude"),
            patch("claude_any.should_attach_web_search", return_value=False),
            patch("claude_any.should_append_compat_prompt", return_value=False),
            patch("claude_any.subprocess.call", return_value=0),
        ]
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8],
            patches[9],
            patches[10],
            patches[11],
            patches[12],
            patch("claude_any.run_claude_any_update_check") as self_update,
            patch("claude_any.run_claude_update_check") as claude_update,
        ):
            rc = claude_any.launch_claude(["-p", "hello"])

        self.assertEqual(0, rc)
        self_update.assert_called_once_with(enabled=False)
        claude_update.assert_called_once_with("claude", enabled=False)

    def test_print_long_option_is_noninteractive(self):
        self.assertTrue(claude_any.has_noninteractive_claude_args(["--print", "hello"]))
        self.assertTrue(claude_any.has_noninteractive_claude_args(["--print=hello"]))

    def test_quiet_upgrade_flag_updates_and_exits(self):
        with (
            patch("claude_any.run_quiet_upgrade_and_exit", return_value=0) as upgrade,
            patch("claude_any.launch_claude") as launch,
        ):
            rc = claude_any.run_cli(["--ca-upgrade-and-exit"])

        self.assertEqual(0, rc)
        upgrade.assert_called_once_with()
        launch.assert_not_called()

    def test_quiet_upgrade_runs_both_updaters(self):
        with (
            patch("claude_any.quiet_upgrade_claude_any", return_value=0) as any_update,
            patch("claude_any.quiet_upgrade_claude_code", return_value=0) as claude_update,
        ):
            rc = claude_any.run_quiet_upgrade_and_exit()

        self.assertEqual(0, rc)
        any_update.assert_called_once_with()
        claude_update.assert_called_once_with()

    def test_quiet_upgrade_reports_failure_when_any_updater_fails(self):
        with (
            patch("claude_any.quiet_upgrade_claude_any", return_value=0),
            patch("claude_any.quiet_upgrade_claude_code", return_value=1),
        ):
            self.assertEqual(1, claude_any.run_quiet_upgrade_and_exit())

    def test_self_update_uses_install_latest_not_update(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": ""})()
        with (
            patch("claude_any.running_from_npm_package", return_value=True),
            patch("claude_any.sys.stdin.isatty", return_value=True),
            patch("claude_any.sys.stdout.isatty", return_value=True),
            patch("claude_any.find_executable", return_value="npm"),
            patch("claude_any.npm_latest_package_version", return_value="999.0.0"),
            patch("claude_any.version_newer", return_value=True),
            patch("builtins.input", return_value="y"),
            patch("claude_any.subprocess.run", return_value=completed) as run,
            patch("claude_any.os.execv", side_effect=RuntimeError("stop")),
            patch("builtins.print"),
        ):
            claude_any.run_claude_any_update_check()

        self.assertEqual(
            ["npm", "install", "-g", "@oneciel-ai/claude-any@latest"],
            run.call_args.args[0],
        )

    def test_configure_only_applies_setup_without_launching(self):
        with (
            patch("claude_any.apply_headless_env_config", return_value=(False, None, None, None, False)),
            patch("claude_any.cmd_provider") as provider,
            patch("claude_any.cmd_model") as model,
            patch("claude_any.launch_claude") as launch,
        ):
            rc = claude_any.run_cli(["--ca-provider", "ollama-cloud", "--ca-model", "deepseek-v4-flash", "--ca-no-launch"])

        self.assertEqual(0, rc)
        provider.assert_called_once()
        model.assert_called_once()
        launch.assert_not_called()

    def test_configure_only_aliases_are_recognized(self):
        for flag in ("--ca-configure-only", "--ca-setup-only"):
            with self.subTest(flag=flag):
                with (
                    patch("claude_any.apply_headless_env_config", return_value=(False, None, None, None, False)),
                    patch("claude_any.launch_claude") as launch,
                ):
                    rc = claude_any.run_cli([flag])

                self.assertEqual(0, rc)
                launch.assert_not_called()

    def test_auto_llm_options_uses_saved_model_when_no_model_is_given(self):
        with (
            patch("claude_any.apply_headless_env_config", return_value=(False, None, None, None, False)),
            patch("claude_any.apply_auto_llm_options_config", return_value=["ok"]) as auto_llm,
            patch("claude_any.launch_claude") as launch,
            patch("builtins.print"),
        ):
            rc = claude_any.run_cli(["--ca-auto-llm-options", "--ca-no-launch"])

        self.assertEqual(0, rc)
        auto_llm.assert_called_once_with(None)
        launch.assert_not_called()

    def test_auto_llm_options_accepts_model_argument(self):
        with (
            patch("claude_any.apply_headless_env_config", return_value=(False, None, None, None, False)),
            patch("claude_any.apply_auto_llm_options_config", return_value=["ok"]) as auto_llm,
            patch("claude_any.launch_claude") as launch,
            patch("builtins.print"),
        ):
            rc = claude_any.run_cli(["--ca-auto-llm-options", "deepseek-v4-flash", "--ca-no-launch"])

        self.assertEqual(0, rc)
        auto_llm.assert_called_once_with("deepseek-v4-flash")
        launch.assert_not_called()

    def test_auto_llm_options_equals_form_accepts_model_argument(self):
        with (
            patch("claude_any.apply_headless_env_config", return_value=(False, None, None, None, False)),
            patch("claude_any.apply_auto_llm_options_config", return_value=["ok"]) as auto_llm,
            patch("claude_any.launch_claude") as launch,
            patch("builtins.print"),
        ):
            rc = claude_any.run_cli(["--ca-auto-llm-options=deepseek-v4-pro", "--ca-no-launch"])

        self.assertEqual(0, rc)
        auto_llm.assert_called_once_with("deepseek-v4-pro")
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
