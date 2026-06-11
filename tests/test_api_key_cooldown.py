import copy
import email.message
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import claude_any


def _headers(**fields):
    msg = email.message.Message()
    for k, v in fields.items():
        msg[k] = str(v)
    return msg


class RateLimitResetSecondsTests(unittest.TestCase):
    def test_millisecond_epoch(self):
        now = time.time()
        self.assertAlmostEqual(
            30.0, claude_any.rate_limit_reset_seconds(str(int((now + 30) * 1000))), delta=2.0
        )

    def test_millisecond_epoch_near_term(self):
        now = time.time()
        self.assertAlmostEqual(
            5.0, claude_any.rate_limit_reset_seconds(str(int((now + 5) * 1000))), delta=2.0
        )

    def test_seconds_epoch(self):
        now = time.time()
        self.assertAlmostEqual(
            90.0, claude_any.rate_limit_reset_seconds(str(int(now + 90))), delta=2.0
        )

    def test_relative_seconds(self):
        self.assertEqual(45.0, claude_any.rate_limit_reset_seconds("45"))

    def test_past_reset_is_zero(self):
        now = time.time()
        self.assertEqual(0.0, claude_any.rate_limit_reset_seconds(str(int((now - 10) * 1000))))


class ApiKeyCooldownTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        self._patch = mock.patch.object(claude_any, "RATE_LIMIT_STATE_PATH", Path(self._tmp.name))
        self._patch.start()
        with claude_any._API_KEY_ROTATION_LOCK:
            claude_any._API_KEY_ROTATION_CURSOR.clear()

    def tearDown(self):
        self._patch.stop()
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def pcfg(self, **overrides):
        p = copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"]["openrouter"])
        p.update(overrides)
        return p

    def test_cooldown_from_x_ratelimit_reset_ms(self):
        now = time.time()
        rest = claude_any.register_api_key_cooldown(
            "openrouter", self.pcfg(), "sk-k1",
            _headers(**{"X-RateLimit-Reset": str(int((now + 45) * 1000)), "X-RateLimit-Remaining": "0"}),
        )
        self.assertAlmostEqual(45.0, rest, delta=2.0)
        until = claude_any.api_key_cooldown_until("openrouter", self.pcfg(), "sk-k1")
        self.assertAlmostEqual(45.0, until - now, delta=2.0)

    def test_cooldown_from_retry_after(self):
        rest = claude_any.register_api_key_cooldown(
            "openrouter", self.pcfg(), "sk-k1", _headers(**{"Retry-After": "20"})
        )
        self.assertEqual(20.0, rest)

    def test_cooldown_default_when_no_headers(self):
        rest = claude_any.register_api_key_cooldown("openrouter", self.pcfg(), "sk-k1", _headers())
        self.assertEqual(claude_any.API_KEY_COOLDOWN_DEFAULT_SECONDS, rest)

    def test_cooldown_clamped_to_ceiling(self):
        rest = claude_any.register_api_key_cooldown(
            "openrouter", self.pcfg(), "sk-k1", _headers(**{"Retry-After": "9999999"})
        )
        self.assertEqual(claude_any.API_KEY_COOLDOWN_MAX_SECONDS, rest)

    def test_cooldown_covers_daily_quota_reset(self):
        # An RPD limit resets up to ~24h away; the ceiling must allow that.
        now = time.time()
        rest = claude_any.register_api_key_cooldown(
            "openrouter", self.pcfg(), "sk-k1",
            _headers(**{"X-RateLimit-Reset": str(int((now + 80000) * 1000))}),
        )
        self.assertAlmostEqual(80000.0, rest, delta=5.0)

    def test_select_skips_cooled_key(self):
        pcfg = self.pcfg(api_key="", api_keys=["sk-k1", "sk-k2", "sk-k3"])
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k1", _headers(**{"Retry-After": "300"}))
        selected = {claude_any.select_provider_api_key("openrouter", pcfg) for _ in range(6)}
        self.assertNotIn("sk-k1", selected)
        self.assertEqual({"sk-k2", "sk-k3"}, selected)

    def test_select_resumes_after_expiry(self):
        pcfg = self.pcfg(api_key="", api_keys=["sk-k1", "sk-k2"])
        # cooldown in the past (already expired)
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k1", _headers(**{"Retry-After": "1"}))
        time.sleep(1.1)
        selected = {claude_any.select_provider_api_key("openrouter", pcfg) for _ in range(4)}
        self.assertIn("sk-k1", selected)

    def test_all_cooling_uses_soonest(self):
        pcfg = self.pcfg(api_key="", api_keys=["sk-k1", "sk-k2", "sk-k3"])
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k1", _headers(**{"Retry-After": "300"}))
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k2", _headers(**{"Retry-After": "10"}))
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k3", _headers(**{"Retry-After": "500"}))
        self.assertEqual("sk-k2", claude_any.select_provider_api_key("openrouter", pcfg))

    def test_single_key_ignores_cooldown(self):
        pcfg = self.pcfg(api_key="sk-only")
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-only", _headers(**{"Retry-After": "300"}))
        self.assertEqual("sk-only", claude_any.select_provider_api_key("openrouter", pcfg))

    def test_primary_api_key_unaffected_by_cooldown(self):
        pcfg = self.pcfg(api_key="", api_keys=["sk-k1", "sk-k2"])
        claude_any.register_api_key_cooldown("openrouter", pcfg, "sk-k1", _headers(**{"Retry-After": "300"}))
        self.assertEqual("sk-k1", claude_any.provider_primary_api_key("openrouter", pcfg))

    def test_key_from_request_headers(self):
        self.assertEqual("sk-x", claude_any.key_from_request_headers({"x-api-key": "sk-x"}))
        self.assertEqual("sk-y", claude_any.key_from_request_headers({"authorization": "Bearer sk-y"}))


if __name__ == "__main__":
    unittest.main()
