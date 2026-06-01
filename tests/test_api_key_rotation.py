import copy
import unittest

import claude_any


class ApiKeyRotationTests(unittest.TestCase):
    def setUp(self):
        with claude_any._API_KEY_ROTATION_LOCK:
            claude_any._API_KEY_ROTATION_CURSOR.clear()

    def deepseek_pcfg(self, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["deepseek"])
        pcfg.update(overrides)
        return pcfg

    def test_parse_api_key_list_filters_placeholders_and_dedupes(self):
        keys = claude_any.parse_api_key_list("sk-a, dummy\nsk-b;sk-a\nnot-used")

        self.assertEqual(["sk-a", "sk-b"], keys)

    def test_provider_headers_round_robin_multiple_keys(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])

        first = claude_any.provider_headers("deepseek", pcfg)
        second = claude_any.provider_headers("deepseek", pcfg)
        third = claude_any.provider_headers("deepseek", pcfg)

        self.assertEqual("Bearer sk-one", first["authorization"])
        self.assertEqual("Bearer sk-two", second["authorization"])
        self.assertEqual("Bearer sk-one", third["authorization"])

    def test_model_list_headers_use_primary_key_without_advancing_rotation(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])

        model_headers = claude_any.provider_model_list_headers("deepseek", pcfg)
        request_headers = claude_any.provider_headers("deepseek", pcfg)

        self.assertEqual("Bearer sk-one", model_headers["authorization"])
        self.assertEqual("Bearer sk-one", request_headers["authorization"])

    def test_env_vars_use_primary_key_for_router_auth_token(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])
        cfg = {"current_provider": "deepseek", "providers": {"deepseek": pcfg}}

        env = claude_any.env_vars(cfg)

        self.assertEqual("sk-one", env["ANTHROPIC_AUTH_TOKEN"])

    def test_launch_readiness_accepts_api_keys_list(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])
        cfg = {"current_provider": "deepseek", "providers": {"deepseek": pcfg}}

        errors = claude_any.launch_readiness_errors(cfg)

        self.assertFalse(any("DeepSeek.com requires" in err for err in errors))

    def test_api_key_status_reports_round_robin(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])

        status = claude_any.api_key_status_line("deepseek", pcfg)

        self.assertIn("2 keys, round-robin", status)


if __name__ == "__main__":
    unittest.main()
