import unittest

import claude_any


class RecommendedTimeoutTests(unittest.TestCase):
    def test_context_size_maps_to_timeout(self):
        self.assertEqual(300000, claude_any.recommended_timeout_ms_for_context(None))
        self.assertEqual(300000, claude_any.recommended_timeout_ms_for_context(1048576))
        self.assertEqual(180000, claude_any.recommended_timeout_ms_for_context(524288))
        self.assertEqual(120000, claude_any.recommended_timeout_ms_for_context(262144))
        self.assertEqual(120000, claude_any.recommended_timeout_ms_for_context(65536))

    def test_ollama_large_model_applies_five_minute_timeout(self):
        pcfg = {"current_model": "deepseek-v4-flash", "num_ctx": "auto", "num_ctx_max": 1048576}

        messages = claude_any.apply_recommended_timeout_for_model_context("ollama-cloud", pcfg)

        self.assertEqual(300000, pcfg["request_timeout_ms"])
        self.assertEqual(300000, pcfg["stream_idle_timeout_ms"])
        self.assertTrue(any("300000" in message for message in messages))

    def test_half_million_context_applies_three_minute_timeout(self):
        pcfg = {"current_model": "custom-large", "context_window": 524288}

        claude_any.apply_recommended_timeout_for_model_context("vllm", pcfg)

        self.assertEqual(180000, pcfg["request_timeout_ms"])
        self.assertEqual(180000, pcfg["stream_idle_timeout_ms"])

    def test_quarter_million_context_applies_two_minute_timeout(self):
        pcfg = {"current_model": "kimi-k2.6", "num_ctx": "auto", "num_ctx_max": 262144}

        claude_any.apply_recommended_timeout_for_model_context("ollama-cloud", pcfg)

        self.assertEqual(120000, pcfg["request_timeout_ms"])
        self.assertEqual(120000, pcfg["stream_idle_timeout_ms"])

    def test_unknown_model_change_falls_back_to_five_minutes(self):
        pcfg = {"current_model": "unknown-private-model", "num_ctx": "auto", "num_ctx_max": 262144}

        claude_any.apply_recommended_timeout_for_model_context("ollama-cloud", pcfg, use_context_fallback=False)

        self.assertEqual(300000, pcfg["request_timeout_ms"])
        self.assertEqual(300000, pcfg["stream_idle_timeout_ms"])

    def test_explicit_context_change_still_uses_context_recommendation(self):
        pcfg = {"current_model": "unknown-private-model", "num_ctx": "auto", "num_ctx_max": 262144}

        claude_any.apply_recommended_timeout_for_model_context("ollama-cloud", pcfg, use_context_fallback=True)

        self.assertEqual(120000, pcfg["request_timeout_ms"])
        self.assertEqual(120000, pcfg["stream_idle_timeout_ms"])


if __name__ == "__main__":
    unittest.main()
