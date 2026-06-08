import unittest
from unittest import mock

import claude_any


class OllamaProviderOptionTests(unittest.TestCase):
    def test_generic_context_window_maps_to_ollama_num_ctx(self):
        pcfg = {"num_ctx": "auto", "num_ctx_min": 32768, "num_ctx_max": 131072}

        claude_any.apply_provider_option("ollama-cloud", pcfg, "context_window=1048576")

        self.assertEqual(1048576, pcfg["context_window"])
        self.assertEqual("auto", pcfg["num_ctx"])
        self.assertEqual(1048576, pcfg["num_ctx_max"])
        self.assertEqual(65536, pcfg["num_ctx_min"])

    def test_generic_max_output_tokens_maps_to_ollama_num_predict(self):
        pcfg = {"ollama_options": {}}

        claude_any.apply_provider_option("ollama-cloud", pcfg, "max_output_tokens=8192")

        self.assertEqual(8192, pcfg["max_output_tokens"])
        self.assertEqual(8192, pcfg["ollama_options"]["num_predict"])

    def test_generic_sampling_options_stay_in_ollama_options(self):
        pcfg = {"ollama_options": {}}

        claude_any.apply_provider_option("ollama-cloud", pcfg, "temperature=0.7")
        claude_any.apply_provider_option("ollama-cloud", pcfg, "top_p=0.9")

        self.assertEqual(0.7, pcfg["ollama_options"]["temperature"])
        self.assertEqual(0.9, pcfg["ollama_options"]["top_p"])

    def test_ollama_provider_options_status_shows_effective_context(self):
        pcfg = {
            "num_ctx": "auto",
            "num_ctx_min": 65536,
            "num_ctx_max": 1048576,
            "ollama_options": {"num_predict": 8192},
            "rate_limit_rpm": 0,
        }

        status = claude_any.provider_options_status("ollama-cloud", pcfg)

        self.assertIn("num_ctx=auto (65536-1048576)", status)
        self.assertIn("ollama_options=num_predict=8192", status)

    def test_unset_generic_ollama_aliases_clears_effective_options(self):
        pcfg = {
            "context_window": 1048576,
            "max_output_tokens": 8192,
            "num_ctx": "auto",
            "num_ctx_max": 1048576,
            "ollama_options": {"num_predict": 8192},
        }

        claude_any.apply_provider_option("ollama-cloud", pcfg, "unset:context_window")
        claude_any.apply_provider_option("ollama-cloud", pcfg, "unset:max_output_tokens")

        self.assertNotIn("context_window", pcfg)
        self.assertNotIn("num_ctx_max", pcfg)
        self.assertNotIn("max_output_tokens", pcfg)
        self.assertNotIn("num_predict", pcfg["ollama_options"])

    def test_ollama_output_cap_uses_runtime_context(self):
        pcfg = {
            "current_model": "gemma4:12b",
            "ollama_options": {"num_predict": 8192},
            "max_output_tokens": 8192,
        }

        with mock.patch.object(
            claude_any,
            "ollama_runtime_info",
            return_value={"runtime_model": "gemma4:12b", "loaded_context_len": 65536},
        ):
            messages = claude_any.apply_ollama_runtime_output_guard("ollama", pcfg)

        self.assertEqual(4096, pcfg["ollama_options"]["num_predict"])
        self.assertEqual(4096, pcfg["max_output_tokens"])
        self.assertTrue(any("runtime context 64K" in message for message in messages))

    def test_ollama_output_cap_keeps_128k_runtime_at_8k(self):
        pcfg = {
            "current_model": "large-model",
            "ollama_options": {"num_predict": 8192},
            "max_output_tokens": 8192,
        }

        with mock.patch.object(
            claude_any,
            "ollama_runtime_info",
            return_value={"runtime_model": "large-model", "loaded_context_len": 131072},
        ):
            messages = claude_any.apply_ollama_runtime_output_guard("ollama", pcfg)

        self.assertEqual(8192, pcfg["ollama_options"]["num_predict"])
        self.assertEqual(8192, pcfg["max_output_tokens"])
        self.assertEqual([], messages)


if __name__ == "__main__":
    unittest.main()
