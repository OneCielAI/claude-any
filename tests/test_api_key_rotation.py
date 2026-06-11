import copy
import io
import unittest
from unittest import mock
import urllib.error

import claude_any


class ApiKeyRotationTests(unittest.TestCase):
    def setUp(self):
        with claude_any._API_KEY_ROTATION_LOCK:
            claude_any._API_KEY_ROTATION_CURSOR.clear()

    def deepseek_pcfg(self, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["deepseek"])
        pcfg.update(overrides)
        return pcfg

    def provider_pcfg(self, provider, **overrides):
        pcfg = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"][provider])
        pcfg.update(overrides)
        return pcfg

    def test_parse_api_key_list_filters_placeholders_and_dedupes(self):
        keys = claude_any.parse_api_key_list("sk-a, dummy\nsk-b;sk-a\nnot-used")

        self.assertEqual(["sk-a", "sk-b"], keys)

    def test_parse_api_key_list_repairs_soft_wrapped_comma_fields(self):
        keys = claude_any.parse_api_key_list(
            "sk-one,sk-two,sk-or\n  -v1-wrapped,sk-four"
        )

        self.assertEqual(["sk-one", "sk-two", "sk-or-v1-wrapped", "sk-four"], keys)

    def test_parse_api_key_list_keeps_newline_separator_without_commas(self):
        keys = claude_any.parse_api_key_list("sk-one\nsk-two\nsk-three")

        self.assertEqual(["sk-one", "sk-two", "sk-three"], keys)

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
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-secret-one", "sk-secret-two"])

        status = claude_any.api_key_status_line("deepseek", pcfg)

        self.assertIn("2 keys, round-robin", status)
        self.assertIn(f"primary {claude_any.mask_secret('sk-secret-one')}", status)
        self.assertIn("fp", status)

    def test_stored_api_key_mask_includes_primary_fingerprint(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-secret-one", "sk-secret-two"])

        status = claude_any.stored_api_key_mask("deepseek", pcfg)

        self.assertIn("2 keys", status)
        self.assertIn(f"primary {claude_any.mask_secret('sk-secret-one')}", status)
        self.assertIn(claude_any.secret_fingerprint("sk-secret-one"), status)

    def test_store_api_key_input_detects_multiple_keys(self):
        cfg = {
            "providers": {
                "deepseek": self.deepseek_pcfg(api_key="", api_keys=[]),
            }
        }
        saved = {}

        def fake_save_config(value):
            saved.update(copy.deepcopy(value))

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config", side_effect=fake_save_config),
            mock.patch.object(claude_any, "clear_model_cache"),
        ):
            messages = claude_any.store_api_key_input_config("deepseek", "sk-one,sk-two")

        pcfg = saved["providers"]["deepseek"]
        self.assertEqual("sk-one", pcfg["api_key"])
        self.assertEqual(["sk-one", "sk-two"], pcfg["api_keys"])
        self.assertIn("Round-robin: enabled", "\n".join(messages))

    def test_compatibility_api_key_probe_tests_each_configured_key(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-one", "sk-two"])
        calls = []

        def fake_post_json(url, body, headers=None, timeout=60.0, **kwargs):
            calls.append((url, body, headers or {}, timeout, kwargs))
            return {"content": [{"type": "text", "text": "OK"}]}

        with mock.patch.object(claude_any, "post_json", side_effect=fake_post_json):
            lines = claude_any.run_compatibility_api_key_probes(
                "deepseek",
                pcfg,
                "claude-any-deepseek-deepseek-v4-pro[1m]",
                claude_any.compatibility_text_request("claude-any-deepseek-deepseek-v4-pro[1m]"),
                3.0,
            )

        self.assertEqual(2, len(calls))
        self.assertEqual("Bearer sk-one", calls[0][2]["authorization"])
        self.assertEqual("Bearer sk-two", calls[1][2]["authorization"])
        self.assertTrue(calls[0][0].endswith("/v1/messages"))
        self.assertEqual("deepseek", calls[0][4]["provider"])
        self.assertEqual("deepseek", calls[1][4]["provider"])
        self.assertIn("API key 1/2", "\n".join(lines))
        self.assertIn("API key 2/2", "\n".join(lines))

    def test_compatibility_api_key_probe_skips_single_key(self):
        pcfg = self.deepseek_pcfg(api_key="sk-one", api_keys=[])

        with mock.patch.object(claude_any, "post_json") as post_json:
            lines = claude_any.run_compatibility_api_key_probes(
                "deepseek",
                pcfg,
                "claude-any-deepseek-deepseek-v4-pro[1m]",
                claude_any.compatibility_text_request("claude-any-deepseek-deepseek-v4-pro[1m]"),
                3.0,
            )

        self.assertEqual([], lines)
        post_json.assert_not_called()

    def test_compatibility_api_key_probe_failure_masks_key(self):
        pcfg = self.deepseek_pcfg(api_key="", api_keys=["sk-secret-one", "sk-secret-two"])
        error = urllib.error.HTTPError(
            "https://api.deepseek.com/anthropic/v1/messages",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":{"message":"invalid key"}}'),
        )

        with mock.patch.object(claude_any, "post_json", side_effect=error):
            with self.assertRaises(claude_any.CompatibilityApiKeyProbeError) as caught:
                claude_any.run_compatibility_api_key_probes(
                    "deepseek",
                    pcfg,
                    "claude-any-deepseek-deepseek-v4-pro[1m]",
                    claude_any.compatibility_text_request("claude-any-deepseek-deepseek-v4-pro[1m]"),
                    3.0,
                )

        self.assertEqual(401, caught.exception.code)
        self.assertIn("invalid key", str(caught.exception))
        self.assertNotIn("sk-secret-one", str(caught.exception))

    def test_compatibility_http_error_message_preserves_type_and_retry_after(self):
        error = urllib.error.HTTPError(
            "https://opencode.ai/zen/v1/chat/completions",
            429,
            "Too Many Requests",
            {"Retry-After": "63478"},
            io.BytesIO(
                b'{"type":"error","error":{"type":"FreeUsageLimitError",'
                b'"message":"Rate limit exceeded. Please try again later."},"metadata":{}}'
            ),
        )

        message = claude_any.compatibility_http_error_message(error)

        self.assertIn("FreeUsageLimitError", message)
        self.assertIn("Rate limit exceeded. Please try again later.", message)
        self.assertIn("Retry-After:", message)
        self.assertIn("17h", message)
        self.assertIn("63478s", message)

    def test_upstream_429_long_retry_after_fails_fast_instead_of_timing_out(self):
        pcfg = self.provider_pcfg("opencode", api_key="sk-one", current_model="deepseek-v4-flash-free")
        error = urllib.error.HTTPError(
            "https://opencode.ai/zen/v1/chat/completions",
            429,
            "Too Many Requests",
            {"Retry-After": "3600"},
            io.BytesIO(
                b'{"type":"error","error":{"type":"FreeUsageLimitError",'
                b'"message":"Rate limit exceeded. Please try again later."},"metadata":{}}'
            ),
        )

        with (
            mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=error),
            mock.patch.object(claude_any, "write_router_activity"),
            mock.patch.object(claude_any, "learn_router_rate_limit_headers"),
            mock.patch.object(claude_any.time, "sleep") as sleep,
        ):
            with self.assertRaises(RuntimeError) as caught:
                claude_any.post_json_with_rate_retry(
                    "https://opencode.ai/zen/v1/chat/completions",
                    {"model": "deepseek-v4-flash-free", "messages": []},
                    {},
                    30.0,
                    "opencode",
                    pcfg,
                    "deepseek-v4-flash-free",
                )

        self.assertIn("FreeUsageLimitError", str(caught.exception))
        self.assertIn("Retry-After", str(caught.exception))
        sleep.assert_not_called()

    def test_stream_429_can_disable_rate_limit_retry_for_compatibility_tests(self):
        pcfg = self.provider_pcfg("opencode", api_key="sk-one", current_model="deepseek-v4-flash-free")
        error = urllib.error.HTTPError(
            "https://opencode.ai/zen/v1/chat/completions",
            429,
            "Too Many Requests",
            {"Retry-After": "300"},
            io.BytesIO(
                b'{"type":"error","error":{"type":"FreeUsageLimitError",'
                b'"message":"Rate limit exceeded. Please try again later."},"metadata":{}}'
            ),
        )

        with (
            mock.patch.object(claude_any.urllib.request, "urlopen", side_effect=error) as urlopen,
            mock.patch.object(claude_any, "write_router_activity"),
            mock.patch.object(claude_any, "learn_router_rate_limit_headers"),
            mock.patch.object(claude_any.time, "sleep") as sleep,
        ):
            with self.assertRaises(RuntimeError) as caught:
                claude_any.open_openai_stream_with_rate_retry(
                    "https://opencode.ai/zen/v1/chat/completions",
                    {"model": "deepseek-v4-flash-free", "messages": [], "stream": True},
                    {},
                    120.0,
                    "opencode",
                    pcfg,
                    "deepseek-v4-flash-free",
                    retry_rate_limits=False,
                )

        self.assertEqual(1, urlopen.call_count)
        self.assertIn("FreeUsageLimitError", str(caught.exception))
        sleep.assert_not_called()

    def test_compatibility_api_key_probe_uses_provider_specific_routes(self):
        cases = [
            ("ollama-cloud", "glm-5.1", "/api/chat"),
            ("self-hosted-nim", "model", "/v1/messages"),
            ("opencode", "claude-sonnet-4-6", "/v1/messages"),
            ("opencode", "deepseek-v4-flash-free", "/v1/chat/completions"),
            ("opencode-go", "qwen3.6-plus", "/v1/messages"),
            ("opencode-go", "deepseek-v4-pro", "/v1/chat/completions"),
        ]

        for provider, model, expected_suffix in cases:
            with self.subTest(provider=provider, model=model):
                pcfg = self.provider_pcfg(provider, api_key="", api_keys=["sk-one", "sk-two"], current_model=model)
                calls = []

                def fake_post_json(url, body, headers=None, timeout=60.0, **kwargs):
                    calls.append((url, body, headers or {}, timeout, kwargs))
                    return {"content": [{"type": "text", "text": "OK"}]}

                with mock.patch.object(claude_any, "post_json", side_effect=fake_post_json):
                    claude_any.run_compatibility_api_key_probes(
                        provider,
                        pcfg,
                        model,
                        claude_any.compatibility_text_request(model),
                        3.0,
                    )

                self.assertEqual(2, len(calls))
                self.assertTrue(calls[0][0].endswith(expected_suffix), calls[0][0])
                self.assertTrue(calls[1][0].endswith(expected_suffix), calls[1][0])
                self.assertEqual("Bearer sk-one", calls[0][2]["authorization"])
                self.assertEqual("Bearer sk-two", calls[1][2]["authorization"])
                self.assertEqual(provider, calls[0][4]["provider"])
                self.assertEqual(provider, calls[1][4]["provider"])


if __name__ == "__main__":
    unittest.main()
