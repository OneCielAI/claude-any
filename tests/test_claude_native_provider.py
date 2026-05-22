"""Tests for the Claude Native provider mode contract:
- PROVIDER_LABELS exposes the "Claude Native" label.
- PROVIDER_ALIASES accepts claude-native / native / claude-code synonyms.
- env_vars() for native mode injects only the minimal marker (and
  ANTHROPIC_API_KEY when stored), so all Anthropic backend, model, advisor,
  output-token, auto-compact and similar settings revert to Claude Code's
  own defaults.
- stop_router_with_guarantee() polls router_up() and raises if the router
  can't be brought down.
- cleanup_managed_services_for_provider() always kills the router for native,
  even when the cleanup.managed_services_on_launch config gate is off.
"""
import unittest
from unittest import mock

import claude_any


class ProviderLabelTests(unittest.TestCase):
    def test_label_is_claude_native(self):
        self.assertEqual("Claude Native", claude_any.PROVIDER_LABELS["anthropic"])

    def test_aliases_route_to_anthropic(self):
        for alias in ("anthropic", "claude", "claude-native", "native", "claude-code"):
            self.assertEqual("anthropic", claude_any.PROVIDER_ALIASES[alias])


class NativeEnvContractTests(unittest.TestCase):
    def _cfg(self, **provider_overrides):
        base = {
            "current_provider": "anthropic",
            "providers": {
                "anthropic": {
                    "api_key": "",
                    "advisor_model": "deepseek-v4-pro",
                    "current_model": "claude-sonnet-4-7",
                    "max_output_tokens": 8192,
                    **provider_overrides,
                },
            },
        }
        return base

    def test_native_env_omits_claude_any_specific_overrides(self):
        # With advisor/model/output-tokens all set in the saved provider
        # config, the native-mode env MUST NOT propagate any of them — the
        # user explicitly chose Claude Native to revert to Anthropic defaults.
        env = claude_any.env_vars(self._cfg())
        self.assertEqual("anthropic", env.get("CLAUDE_ANY_PROVIDER"))
        for forbidden in (
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_SUBAGENT_MODEL",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
            "CLAUDE_CODE_DISABLE_TERMINAL_TITLE",
            "CLAUDE_CODE_ATTRIBUTION_HEADER",
            "CLAUDE_ANY_ADVISOR_MODEL",
            "CLAUDE_ANY_MODEL_ALIAS",
        ):
            self.assertNotIn(forbidden, env, msg=f"native env must not set {forbidden}")

    def test_native_env_includes_api_key_only_when_stored(self):
        # No stored key → ANTHROPIC_API_KEY absent (Claude Code's OAuth wins).
        env = claude_any.env_vars(self._cfg(api_key=""))
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        # Stored key → ANTHROPIC_API_KEY exposed.
        env_with_key = claude_any.env_vars(self._cfg(api_key="sk-ant-real"))
        self.assertEqual("sk-ant-real", env_with_key.get("ANTHROPIC_API_KEY"))


class StopRouterGuaranteeTests(unittest.TestCase):
    def test_returns_false_when_router_already_down(self):
        with (
            mock.patch.object(claude_any, "router_up", return_value=False),
            mock.patch.object(claude_any, "stop_router_processes") as stop,
            mock.patch.object(claude_any, "router_log"),
        ):
            result = claude_any.stop_router_with_guarantee("test", max_wait_seconds=0.5)
        self.assertFalse(result)
        stop.assert_not_called()

    def test_returns_true_when_kill_brings_router_down(self):
        states = iter([True, False])  # alive at first, dead after stop
        def fake_up():
            try:
                return next(states)
            except StopIteration:
                return False

        with (
            mock.patch.object(claude_any, "router_up", side_effect=fake_up),
            mock.patch.object(claude_any, "stop_router_processes") as stop,
            mock.patch.object(claude_any, "router_log"),
        ):
            result = claude_any.stop_router_with_guarantee("test", max_wait_seconds=1.0)
        self.assertTrue(result)
        stop.assert_called_once()

    def test_raises_when_router_stays_up_past_deadline(self):
        # router_up always returns True → guarantee should give up and raise.
        with (
            mock.patch.object(claude_any, "router_up", return_value=True),
            mock.patch.object(claude_any, "stop_router_processes"),
            mock.patch.object(claude_any, "router_log"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                claude_any.stop_router_with_guarantee("native_anthropic_launch", max_wait_seconds=0.3)
        self.assertIn("native_anthropic_launch", str(ctx.exception))
        self.assertIn("router", str(ctx.exception).lower())


class CleanupNativeAlwaysKillsTests(unittest.TestCase):
    def test_native_bypasses_managed_services_toggle(self):
        # Even when the user turned off managed_services_on_launch, native
        # mode must still kill the router. This is the hard guarantee the
        # provider was added to deliver.
        cfg = {"cleanup": {"managed_services_on_launch": False}}
        with (
            mock.patch.object(claude_any, "native_anthropic_enabled", return_value=True),
            mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "stop_router_with_guarantee", return_value=True) as kill,
            mock.patch.object(claude_any, "stop_ncp_proxy"),
        ):
            claude_any.cleanup_managed_services_for_provider("anthropic", {}, cfg, quiet=True)
        kill.assert_called_once()
        called_reason = kill.call_args.args[0] if kill.call_args.args else kill.call_args.kwargs.get("reason", "")
        self.assertIn("native", called_reason.lower())

    def test_non_native_respects_managed_services_toggle(self):
        # When the gate is off, non-native providers should NOT kill the
        # router (preserves the existing opt-out behavior).
        cfg = {"cleanup": {"managed_services_on_launch": False}}
        with (
            mock.patch.object(claude_any, "native_anthropic_enabled", return_value=False),
            mock.patch.object(claude_any, "ollama_native_compat_enabled", return_value=True),
            mock.patch.object(claude_any, "provider_native_compat_enabled", return_value=False),
            mock.patch.object(claude_any, "stop_router_processes") as stop,
            mock.patch.object(claude_any, "stop_router_with_guarantee") as guarantee,
            mock.patch.object(claude_any, "stop_ncp_proxy"),
        ):
            claude_any.cleanup_managed_services_for_provider("ollama", {}, cfg, quiet=True)
        stop.assert_not_called()
        guarantee.assert_not_called()


if __name__ == "__main__":
    unittest.main()
