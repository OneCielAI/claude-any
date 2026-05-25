import copy
import unittest
from unittest import mock

import claude_any


class DeepSeekProviderTests(unittest.TestCase):
    def deepseek_cfg(self, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["deepseek"])
        pcfg.update(overrides)
        return {
            "current_provider": "deepseek",
            "providers": {
                "deepseek": pcfg,
            },
        }

    def test_provider_is_registered(self):
        self.assertEqual("deepseek", claude_any.PROVIDER_ALIASES["deepseek"])
        self.assertEqual("deepseek", claude_any.PROVIDER_ALIASES["deepseek.com"])
        self.assertEqual("DeepSeek.com", claude_any.PROVIDER_LABELS["deepseek"])
        self.assertEqual("https://api.deepseek.com/anthropic", claude_any.default_base_url("deepseek"))

    def test_default_config_matches_deepseek_claude_code_docs(self):
        pcfg = claude_any.DEFAULT_CONFIG["providers"]["deepseek"]
        self.assertEqual("https://api.deepseek.com/anthropic", pcfg["base_url"])
        self.assertEqual("deepseek-v4-pro[1m]", pcfg["current_model"])
        self.assertEqual("deepseek-v4-flash", pcfg["haiku_model"])
        self.assertEqual("deepseek-v4-flash", pcfg["subagent_model"])
        self.assertEqual("max", pcfg["effort_level"])
        self.assertTrue(pcfg["native_compat"])

    def test_env_vars_use_deepseek_anthropic_endpoint(self):
        env = claude_any.env_vars(self.deepseek_cfg(api_key="sk-deepseek-test"))
        self.assertEqual("deepseek", env["CLAUDE_ANY_PROVIDER"])
        self.assertEqual("https://api.deepseek.com/anthropic", env["ANTHROPIC_BASE_URL"])
        self.assertEqual("sk-deepseek-test", env["ANTHROPIC_AUTH_TOKEN"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual("deepseek-v4-pro[1m]", env["ANTHROPIC_MODEL"])
        self.assertEqual("deepseek-v4-pro[1m]", env["ANTHROPIC_DEFAULT_OPUS_MODEL"])
        self.assertEqual("deepseek-v4-pro[1m]", env["ANTHROPIC_DEFAULT_SONNET_MODEL"])
        self.assertEqual("deepseek-v4-flash", env["ANTHROPIC_DEFAULT_HAIKU_MODEL"])
        self.assertEqual("deepseek-v4-flash", env["CLAUDE_CODE_SUBAGENT_MODEL"])
        self.assertEqual("max", env["CLAUDE_CODE_EFFORT_LEVEL"])
        self.assertEqual("8192", env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"])

    def test_launch_removes_inherited_anthropic_api_key_for_deepseek(self):
        cfg = self.deepseek_cfg(api_key="sk-deepseek-test")
        with (
            mock.patch.dict(
                "os.environ",
                {"PATH": "/usr/local/bin", "ANTHROPIC_API_KEY": "sk-ant-old"},
                clear=True,
            ),
            mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0),
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]),
            mock.patch.object(claude_any, "cleanup_managed_services_for_provider"),
            mock.patch.object(claude_any, "find_executable", return_value="/usr/local/bin/claude"),
            mock.patch.object(claude_any, "run_claude_update_check"),
            mock.patch.object(claude_any, "install_claude_any_slash_commands"),
            mock.patch.object(claude_any, "install_tool_guard_hooks"),
            mock.patch.object(claude_any, "install_claude_any_statusline"),
            mock.patch.object(claude_any, "should_attach_web_search", return_value=False),
            mock.patch.object(claude_any.subprocess, "call", return_value=0) as call,
        ):
            rc = claude_any.launch_claude([], update_check=False, self_update_check=False)

        self.assertEqual(0, rc)
        launch_env = call.call_args.kwargs["env"]
        self.assertEqual("sk-deepseek-test", launch_env["ANTHROPIC_AUTH_TOKEN"])
        self.assertNotIn("ANTHROPIC_API_KEY", launch_env)

    def test_deepseek_base_status_does_not_probe_model_list(self):
        cfg = self.deepseek_cfg(api_key="sk-deepseek-test")
        pcfg = cfg["providers"]["deepseek"]
        with mock.patch("urllib.request.urlopen") as urlopen:
            status = claude_any.base_url_status_line("deepseek", pcfg)
        urlopen.assert_not_called()
        self.assertIn("DeepSeek Anthropic API configured", status)

    def test_launch_requires_deepseek_api_key(self):
        errors = claude_any.launch_readiness_errors(self.deepseek_cfg(api_key=""))
        self.assertTrue(any("DeepSeek.com requires" in err for err in errors))
        self.assertTrue(claude_any.launch_blockers_require_api_key(errors))

    def test_base_url_blocker_does_not_open_api_key_setup(self):
        errors = ["Launch blocked: Base URL unreachable."]
        self.assertFalse(claude_any.launch_blockers_require_api_key(errors))

    def test_model_list_uses_documented_deepseek_models_without_network(self):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["deepseek"])
        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "write_model_list_cache") as write_cache,
            mock.patch.object(claude_any, "http_json") as http_json,
        ):
            models = claude_any.upstream_model_ids("deepseek", pcfg)
        http_json.assert_not_called()
        self.assertIn("deepseek-v4-pro[1m]", models)
        self.assertIn("deepseek-v4-flash", models)
        write_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
