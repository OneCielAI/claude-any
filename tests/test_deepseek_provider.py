import copy
import unittest
from contextlib import ExitStack
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

    def test_env_vars_route_deepseek_through_claude_any_router(self):
        cfg = self.deepseek_cfg(api_key="sk-deepseek-test")
        pcfg = cfg["providers"]["deepseek"]
        env = claude_any.env_vars(cfg)
        self.assertEqual("deepseek", env["CLAUDE_ANY_PROVIDER"])
        self.assertEqual(claude_any.ROUTER_BASE, env["ANTHROPIC_BASE_URL"])
        self.assertEqual("not-used", env["ANTHROPIC_AUTH_TOKEN"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("sk-deepseek-test", env.values())
        expected_model = claude_any.claude_code_context_model_alias("deepseek", pcfg, claude_any.current_alias(cfg))
        self.assertEqual(expected_model, env["ANTHROPIC_MODEL"])
        self.assertEqual(expected_model, env["ANTHROPIC_DEFAULT_OPUS_MODEL"])
        self.assertEqual(expected_model, env["ANTHROPIC_DEFAULT_SONNET_MODEL"])
        self.assertEqual(expected_model, env["ANTHROPIC_DEFAULT_HAIKU_MODEL"])
        self.assertEqual(expected_model, env["CLAUDE_CODE_SUBAGENT_MODEL"])
        self.assertEqual("8192", env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"])

    def test_launch_removes_inherited_anthropic_api_key_for_deepseek(self):
        cfg = self.deepseek_cfg(api_key="sk-deepseek-test")
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(
                "os.environ",
                {"PATH": "/usr/local/bin", "ANTHROPIC_API_KEY": "sk-ant-old"},
                clear=True,
            ))
            stack.enter_context(mock.patch.object(claude_any, "run_prelaunch_menu", return_value=0))
            stack.enter_context(mock.patch.object(claude_any, "load_config", return_value=cfg))
            stack.enter_context(mock.patch.object(claude_any, "launch_readiness_errors", return_value=[]))
            stack.enter_context(mock.patch.object(claude_any, "start_router_if_needed"))
            stack.enter_context(mock.patch.object(claude_any, "cleanup_managed_services_for_provider"))
            stack.enter_context(mock.patch.object(claude_any, "find_executable", return_value="/usr/local/bin/claude"))
            stack.enter_context(mock.patch.object(claude_any, "run_claude_update_check"))
            stack.enter_context(mock.patch.object(claude_any, "install_claude_any_slash_commands"))
            stack.enter_context(mock.patch.object(claude_any, "install_tool_guard_hooks"))
            stack.enter_context(mock.patch.object(claude_any, "install_claude_any_statusline"))
            stack.enter_context(mock.patch.object(claude_any, "should_attach_web_search", return_value=False))
            stack.enter_context(mock.patch.object(claude_any, "should_append_compat_prompt", return_value=False))
            stack.enter_context(mock.patch.object(claude_any, "ensure_channel_llm_delivery_cursor_initialized"))
            stack.enter_context(mock.patch.object(claude_any, "ensure_channel_probe_cache_for_launch", return_value=False))
            stack.enter_context(mock.patch.object(claude_any, "cached_channel_capable_server_names", return_value=["claude-any-router"]))
            stack.enter_context(mock.patch.object(claude_any, "cached_channel_source_paths_for_specs", return_value=[]))
            stack.enter_context(mock.patch.object(claude_any, "read_channel_probe_cache", return_value={"probed_at": 1700000000}))
            stack.enter_context(mock.patch.object(claude_any, "write_channel_mcp_config", return_value="channel-mcp.json"))
            stack.enter_context(mock.patch.object(claude_any, "write_mcp_proxy_config", return_value=None))
            stack.enter_context(mock.patch.object(claude_any, "auto_start_sse_channels_from_mcp_configs", return_value=[]))
            stack.enter_context(mock.patch.object(claude_any, "subprocess_call_with_channel_wake_proxy", return_value=0))
            call = stack.enter_context(mock.patch.object(claude_any.subprocess, "call", return_value=0))
            rc = claude_any.launch_claude([], update_check=False, self_update_check=False)

        self.assertEqual(0, rc)
        launch_env = call.call_args.kwargs["env"]
        self.assertEqual(claude_any.ROUTER_BASE, launch_env["ANTHROPIC_BASE_URL"])
        self.assertEqual("not-used", launch_env["ANTHROPIC_AUTH_TOKEN"])
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
