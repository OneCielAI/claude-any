import unittest

import claude_any


class RateLimitDefaultTests(unittest.TestCase):
    def test_hosted_rate_limit_defaults_are_off(self):
        for provider in ("ollama", "ollama-cloud", "lm-studio", "nvidia-hosted", "self-hosted-nim"):
            with self.subTest(provider=provider):
                pcfg = claude_any.DEFAULT_CONFIG["providers"][provider]
                self.assertEqual(0, pcfg.get("rate_limit_rpm"))
                self.assertFalse(pcfg.get("rate_limit_status"))
                self.assertEqual(0, claude_any.router_rate_limit_configured_rpm(provider, pcfg))

    def test_missing_rate_limit_is_not_implicitly_40_rpm(self):
        self.assertIsNone(claude_any.router_rate_limit_configured_rpm("ollama-cloud", {}))
        self.assertIsNone(claude_any.router_rate_limit_rpm("ollama-cloud", {}))

    def test_migration_flips_old_default_rate_limits_off(self):
        cfg = {
            "migrations": {},
            "providers": {
                "ollama": {"rate_limit_rpm": 40, "rate_limit_status": True},
                "ollama-cloud": {"rate_limit_rpm": "40", "rate_limit_status": True},
                "nvidia-hosted": {"rate_limit_rpm": 40, "rate_limit_status": True},
                "self-hosted-nim": {"rate_limit_rpm": 40, "rate_limit_status": True},
                "lm-studio": {"rate_limit_rpm": 0, "rate_limit_status": True},
            },
        }

        claude_any.apply_config_migrations(cfg)

        for provider in ("ollama", "ollama-cloud", "nvidia-hosted", "self-hosted-nim", "lm-studio"):
            with self.subTest(provider=provider):
                self.assertEqual(0, int(cfg["providers"][provider]["rate_limit_rpm"]))
                self.assertFalse(cfg["providers"][provider]["rate_limit_status"])
        self.assertTrue(cfg["migrations"]["rate_limit_defaults_off_20260526"])

    def test_migration_preserves_explicit_non_default_rate_limit(self):
        cfg = {
            "migrations": {},
            "providers": {
                "ollama-cloud": {"rate_limit_rpm": 8, "rate_limit_status": True},
            },
        }

        claude_any.apply_config_migrations(cfg)

        self.assertEqual(8, cfg["providers"]["ollama-cloud"]["rate_limit_rpm"])
        self.assertTrue(cfg["providers"]["ollama-cloud"]["rate_limit_status"])


if __name__ == "__main__":
    unittest.main()
