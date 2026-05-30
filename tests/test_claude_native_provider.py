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
import tempfile
import io
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

import claude_any


class ProviderLabelTests(unittest.TestCase):
    def test_label_is_claude_native(self):
        self.assertEqual("Claude Native", claude_any.PROVIDER_LABELS["anthropic"])

    def test_aliases_route_to_anthropic(self):
        for alias in ("anthropic", "claude", "claude-native", "native", "claude-code"):
            self.assertEqual("anthropic", claude_any.PROVIDER_ALIASES[alias])

    def test_provider_menu_exposes_native_and_routed_anthropic_choices(self):
        cfg = {
            "current_provider": "anthropic",
            "providers": {
                "anthropic": {
                    "base_url": "https://api.anthropic.com",
                    "api_key": "",
                    "route_through_router": False,
                },
            },
        }

        rows, values = claude_any.provider_panel_rows(cfg)

        self.assertIn(claude_any.ANTHROPIC_NATIVE_PROVIDER_CHOICE, values)
        self.assertIn(claude_any.ANTHROPIC_ROUTED_PROVIDER_CHOICE, values)
        self.assertTrue(any("Claude Native" in row and row.startswith("*") for row in rows))
        self.assertTrue(any("Anthropic routed" in row and "Claude Code auth" in row for row in rows))

    def test_provider_menu_marks_routed_anthropic_choice(self):
        cfg = {
            "current_provider": "anthropic",
            "providers": {
                "anthropic": {
                    "base_url": "https://api.anthropic.com",
                    "api_key": "sk-ant-real",
                    "route_through_router": True,
                },
            },
        }

        rows, _ = claude_any.provider_panel_rows(cfg)

        self.assertTrue(any("Anthropic routed" in row and row.startswith("*") for row in rows))
        self.assertTrue(any("Claude Native" in row and row.startswith(" ") for row in rows))
        self.assertEqual(
            claude_any.ANTHROPIC_ROUTED_PROVIDER_CHOICE,
            claude_any.current_provider_panel_choice("anthropic", cfg["providers"]["anthropic"]),
        )

    def test_main_menu_provider_label_reflects_anthropic_route_mode(self):
        cfg = {"language": "en"}
        native = {"route_through_router": False, "advisor_model": "", "current_model": "claude-opus-4-7"}
        routed = {"route_through_router": True, "advisor_model": "", "current_model": "claude-opus-4-7"}

        self.assertIn("Provider  [Claude Native]", claude_any.main_menu_rows(cfg, "anthropic", native, "en")[1])
        self.assertIn("Provider  [Anthropic routed]", claude_any.main_menu_rows(cfg, "anthropic", routed, "en")[1])

    def test_provider_choice_toggles_anthropic_routing(self):
        cfg = {
            "current_provider": "anthropic",
            "providers": {
                "anthropic": {
                    "base_url": "https://api.anthropic.com",
                    "api_key": "",
                    "route_through_router": False,
                },
            },
        }
        saved: dict[str, object] = {}

        def fake_save_config(next_cfg):
            saved.clear()
            saved.update(next_cfg)

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config", side_effect=fake_save_config),
            mock.patch.object(claude_any, "clear_model_cache"),
        ):
            lines = claude_any.set_provider_choice_config(claude_any.ANTHROPIC_ROUTED_PROVIDER_CHOICE)

        self.assertEqual("anthropic", saved["current_provider"])
        self.assertTrue(saved["providers"]["anthropic"]["route_through_router"])
        self.assertTrue(any("Claude Code OAuth/API auth headers" in line for line in lines))

    def test_plain_anthropic_provider_selection_resets_to_native(self):
        cfg = {
            "current_provider": "opencode",
            "providers": {
                "anthropic": {
                    "base_url": "https://api.anthropic.com",
                    "api_key": "",
                    "route_through_router": True,
                },
                "opencode": {},
            },
        }
        saved: dict[str, object] = {}

        def fake_save_config(next_cfg):
            saved.clear()
            saved.update(next_cfg)

        with (
            mock.patch.object(claude_any, "load_config", return_value=cfg),
            mock.patch.object(claude_any, "save_config", side_effect=fake_save_config),
            mock.patch.object(claude_any, "clear_model_cache"),
        ):
            lines = claude_any.set_provider_config("anthropic")

        self.assertEqual("anthropic", saved["current_provider"])
        self.assertFalse(saved["providers"]["anthropic"]["route_through_router"])
        self.assertIn("mode: anthropic-native", lines)


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

    def test_routed_anthropic_env_uses_claude_any_router(self):
        env = claude_any.env_vars(self._cfg(api_key="sk-ant-real", route_through_router=True))

        self.assertEqual("anthropic", env.get("CLAUDE_ANY_PROVIDER"))
        self.assertEqual(claude_any.ROUTER_BASE, env.get("ANTHROPIC_BASE_URL"))
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertEqual("claude-any-anthropic-claude-sonnet-4-7", env.get("ANTHROPIC_MODEL"))
        self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_routed_anthropic_reports_router_mode(self):
        pcfg = self._cfg(route_through_router=True)["providers"]["anthropic"]

        self.assertEqual("anthropic-routed", claude_any.provider_mode_label("anthropic", pcfg))
        self.assertFalse(claude_any.direct_native_anthropic_enabled("anthropic", pcfg))

    def test_routed_anthropic_without_api_key_can_launch_for_oauth_header_pass_through(self):
        with mock.patch.object(claude_any, "base_url_status_line", return_value="Base URL: model list reachable"):
            errors = claude_any.launch_readiness_errors(self._cfg(route_through_router=True, api_key=""))

        self.assertEqual([], errors)

    def test_routed_anthropic_provider_headers_use_inbound_oauth_when_no_api_key(self):
        headers = claude_any.provider_headers(
            "anthropic",
            {"api_key": ""},
            {"authorization": "Bearer oauth-token", "anthropic-beta": "tools-2026"},
        )

        self.assertEqual("Bearer oauth-token", headers["authorization"])
        self.assertEqual("tools-2026", headers["anthropic-beta"])
        self.assertNotIn("x-api-key", headers)

    def test_routed_anthropic_provider_headers_prefer_configured_api_key(self):
        headers = claude_any.provider_headers(
            "anthropic",
            {"api_key": "sk-ant-real"},
            {"authorization": "Bearer oauth-token"},
        )

        self.assertEqual("sk-ant-real", headers["x-api-key"])
        self.assertNotIn("authorization", headers)

    def test_routed_anthropic_advisor_request_uses_messages_api(self):
        pcfg = {
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "advisor_model": "claude-opus-4-8",
            "route_through_router": True,
            "max_output_tokens": 4096,
        }
        body = {
            "system": "You are in Claude Code.",
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "CLAUDE_ANY_ADVISOR_CALL\nFocus: plan"}]},
                {"role": "system", "content": [{"type": "text", "text": "Runtime state from Claude Code."}]},
                {"role": "assistant", "content": [{"type": "text", "text": "I will inspect files."}]},
            ],
            "tools": [{"name": "Bash"}],
            "tool_choice": {"type": "auto"},
        }

        self.assertTrue(claude_any.advisor_provider_supported("anthropic"))
        self.assertEqual("https://api.anthropic.com/v1/messages", claude_any.advisor_endpoint("anthropic", pcfg))
        req = claude_any.advisor_request("anthropic", "claude-opus-4-8", body, pcfg)

        self.assertEqual("claude-opus-4-8", req["model"])
        self.assertEqual(False, req["stream"])
        self.assertNotIn("tools", req)
        self.assertNotIn("tool_choice", req)
        self.assertEqual(["user", "assistant", "user"], [message["role"] for message in req["messages"]])
        self.assertIn("Advisor focus", claude_any.anthropic_content_to_text(req["messages"][-1]["content"]))
        self.assertIn("claude-any Advisor", claude_any.anthropic_content_to_text(req["system"]))
        self.assertIn("Original session system context", claude_any.anthropic_content_to_text(req["system"]))
        self.assertIn("Runtime state from Claude Code.", claude_any.anthropic_content_to_text(req["system"]))

    def test_routed_anthropic_advisor_call_forwards_oauth_headers(self):
        pcfg = {
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "advisor_model": "claude-opus-4-8",
            "route_through_router": True,
            "max_output_tokens": 4096,
        }
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "CLAUDE_ANY_ADVISOR_CALL"}]}],
        }

        with mock.patch.object(
            claude_any,
            "post_json_with_rate_retry",
            return_value={"content": [{"type": "text", "text": "advisor ok"}]},
        ) as post:
            text = claude_any.call_advisor_text(
                "anthropic",
                pcfg,
                body,
                inbound_headers={"authorization": "Bearer oauth-token", "anthropic-beta": "tools-2026"},
            )

        self.assertEqual("advisor ok", text)
        args = post.call_args.args
        self.assertEqual("https://api.anthropic.com/v1/messages", args[0])
        self.assertEqual("Bearer oauth-token", args[2]["authorization"])
        self.assertEqual("tools-2026", args[2]["anthropic-beta"])

    def test_interactive_advisor_call_can_skip_rate_limit_wait_and_retry(self):
        pcfg = {
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "advisor_model": "claude-opus-4-8",
            "route_through_router": True,
            "max_output_tokens": 4096,
        }
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "CLAUDE_ANY_ADVISOR_CALL"}]}],
        }

        with (
            mock.patch.object(claude_any, "apply_router_rate_limit") as apply_rate_limit,
            mock.patch.object(claude_any, "post_json_with_rate_retry", side_effect=RuntimeError("rate limited")) as post,
        ):
            with self.assertRaises(RuntimeError):
                claude_any.call_advisor_text(
                    "anthropic",
                    pcfg,
                    body,
                    inbound_headers={"authorization": "Bearer oauth-token"},
                    allow_rate_limit_wait=False,
                    retry_rate_limits=False,
                    raise_errors=True,
                )

        apply_rate_limit.assert_not_called()
        self.assertFalse(post.call_args.kwargs["retry_rate_limits"])

    def test_post_json_can_fail_fast_on_429_without_retry_sleep(self):
        error = urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":{"message":"rate limit"}}'),
        )

        with (
            mock.patch("urllib.request.urlopen", side_effect=error) as urlopen,
            mock.patch.object(claude_any, "learn_router_rate_limit_headers"),
            mock.patch.object(claude_any, "write_router_activity"),
            mock.patch.object(claude_any, "router_log"),
            mock.patch("time.sleep") as sleep,
        ):
            with self.assertRaises(RuntimeError):
                claude_any.post_json_with_rate_retry(
                    "https://api.anthropic.com/v1/messages",
                    {"model": "claude-opus-4-8", "messages": []},
                    {},
                    30.0,
                    "anthropic",
                    {"gateway_retries": 2},
                    "claude-opus-4-8",
                    retry_rate_limits=False,
                )

        self.assertEqual(1, urlopen.call_count)
        sleep.assert_not_called()

    def test_direct_native_anthropic_does_not_require_api_key_or_base_url(self):
        errors = claude_any.launch_readiness_errors(self._cfg(base_url="", api_key="", route_through_router=False))

        self.assertEqual([], errors)


class NativeSlashCommandContractTests(unittest.TestCase):
    def test_native_mode_removes_claude_any_slash_commands(self):
        with tempfile.TemporaryDirectory() as td:
            commands_dir = Path(td) / "commands"
            commands_dir.mkdir()
            advisor = commands_dir / "advisor.md"
            router_debug = commands_dir / "router-debug.md"
            advisor.write_text(claude_any.ADVISOR_SLASH_COMMAND, encoding="utf-8")
            router_debug.write_text(claude_any.ROUTER_DEBUG_SLASH_COMMAND, encoding="utf-8")

            with mock.patch.object(claude_any, "CLAUDE_COMMANDS_DIR", commands_dir):
                claude_any.disable_claude_any_slash_commands_for_native()

            self.assertFalse(advisor.exists())
            self.assertFalse(router_debug.exists())

    def test_non_native_install_restores_router_backed_slash_commands(self):
        with tempfile.TemporaryDirectory() as td:
            commands_dir = Path(td) / "commands"
            commands_dir.mkdir()
            advisor = commands_dir / "advisor.md"
            advisor.write_text(claude_any.ADVISOR_SLASH_COMMAND, encoding="utf-8")

            with mock.patch.object(claude_any, "CLAUDE_COMMANDS_DIR", commands_dir):
                claude_any.disable_claude_any_slash_commands_for_native()
                self.assertFalse(advisor.exists())
                claude_any.install_claude_any_slash_commands()

            self.assertIn("CLAUDE_ANY_ADVISOR_CALL", advisor.read_text(encoding="utf-8"))

    def test_native_mode_preserves_user_custom_advisor_command(self):
        custom = "---\ndescription: My advisor\n---\n\nCustom user command\n"
        with tempfile.TemporaryDirectory() as td:
            commands_dir = Path(td) / "commands"
            commands_dir.mkdir()
            advisor = commands_dir / "advisor.md"
            advisor.write_text(custom, encoding="utf-8")

            with mock.patch.object(claude_any, "CLAUDE_COMMANDS_DIR", commands_dir):
                claude_any.disable_claude_any_slash_commands_for_native()

            self.assertEqual(custom, advisor.read_text(encoding="utf-8"))

    def test_non_native_install_preserves_user_custom_advisor_command(self):
        custom = "---\ndescription: My advisor\n---\n\nCustom user command\n"
        with tempfile.TemporaryDirectory() as td:
            commands_dir = Path(td) / "commands"
            commands_dir.mkdir()
            advisor = commands_dir / "advisor.md"
            advisor.write_text(custom, encoding="utf-8")

            with mock.patch.object(claude_any, "CLAUDE_COMMANDS_DIR", commands_dir):
                claude_any.install_claude_any_slash_commands()

            self.assertEqual(custom, advisor.read_text(encoding="utf-8"))


class NativeModelListTests(unittest.TestCase):
    def test_public_docs_parser_extracts_current_claude_models_without_footnotes(self):
        html = """
        Claude API ID
        <span>claude-opus-4-8</span><span>claude-sonnet-4-6</span>
        <span>claude-haiku-4-5-20251001</span>
        Claude API alias
        <span>claude-haiku-4-5</span>
        AWS Bedrock ID <span>anthropic.claude-opus-4-8</span>
        Vertex AI ID <span>claude-haiku-4-5@20251001</span>
        footnote artifact <span>claude-opus-4-1-2</span>
        """

        ids = claude_any.anthropic_model_ids_from_docs_text(html)

        self.assertEqual(
            ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-haiku-4-5"],
            ids,
        )

    def test_public_docs_parser_includes_latest_aliases(self):
        html = """
        <code>claude-3-7-sonnet-latest</code>
        <code>claude-3-5-haiku-latest</code>
        <code>claude-sonnet-4-6-latest</code>
        """

        ids = claude_any.anthropic_model_ids_from_docs_text(html)

        self.assertEqual(
            ["claude-3-7-sonnet-latest", "claude-3-5-haiku-latest", "claude-sonnet-4-6-latest"],
            ids,
        )

    def test_native_refresh_bypasses_model_cache_and_uses_public_docs_without_api_key(self):
        pcfg = {"base_url": "https://api.anthropic.com", "api_key": "", "current_model": "claude-sonnet-4-6"}

        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=["claude-old-cache"]),
            mock.patch.object(claude_any, "http_json", side_effect=RuntimeError("missing api key")),
            mock.patch.object(claude_any, "fetch_anthropic_public_model_ids", return_value=["claude-opus-4-8", "claude-sonnet-4-6"]) as docs,
            mock.patch.object(claude_any, "write_model_list_cache") as write,
        ):
            self.assertEqual(["claude-old-cache"], claude_any.upstream_model_ids("anthropic", pcfg))
            refreshed = claude_any.upstream_model_ids("anthropic", pcfg, force_refresh=True)

        self.assertEqual(["claude-opus-4-8", "claude-sonnet-4-6"], refreshed)
        docs.assert_called_once()
        write.assert_called_once_with("anthropic", pcfg, ["claude-opus-4-8", "claude-sonnet-4-6"])

    def test_native_refresh_prefers_public_docs_over_api_key_model_list(self):
        pcfg = {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-real", "current_model": "claude-sonnet-4-6"}

        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "fetch_anthropic_public_model_ids", return_value=["claude-opus-4-8", "claude-sonnet-4-6"]),
            mock.patch.object(claude_any, "http_json", return_value={"data": [{"id": "claude-old-api"}]}) as http_json,
            mock.patch.object(claude_any, "write_model_list_cache"),
        ):
            refreshed = claude_any.upstream_model_ids("anthropic", pcfg, force_refresh=True)

        self.assertEqual(["claude-opus-4-8", "claude-sonnet-4-6"], refreshed)
        http_json.assert_not_called()

    def test_native_model_registry_persists_provider_model_list(self):
        pcfg = {"base_url": "https://api.anthropic.com", "api_key": "", "current_model": "claude-sonnet-4-6"}

        with tempfile.TemporaryDirectory() as td:
            cache_path = Path(td) / "model-list-cache.json"
            registry_path = Path(td) / "model-registry.json"
            with (
                mock.patch.object(claude_any, "MODEL_LIST_CACHE_PATH", cache_path),
                mock.patch.object(claude_any, "MODEL_REGISTRY_PATH", registry_path),
            ):
                claude_any.write_model_registry("anthropic", pcfg, ["claude-opus-4-8", "claude-haiku-4-5"], "anthropic-docs")
                cached = claude_any.read_model_list_cache("anthropic", pcfg)
                registry = claude_any.read_model_registry("anthropic", pcfg)

        self.assertEqual(["claude-opus-4-8", "claude-haiku-4-5"], cached)
        self.assertIsNotNone(registry)
        assert registry is not None
        self.assertEqual("anthropic-docs", registry["source"])
        recommendations = registry["recommendations"]
        self.assertEqual("balanced", recommendations["claude-opus-4-8"]["recommended_preset"])
        self.assertEqual(4096, recommendations["claude-opus-4-8"]["parameters"]["max_output_tokens"])
        self.assertEqual(1048576, recommendations["claude-opus-4-8"]["limits"]["context_window"])
        self.assertEqual(128000, recommendations["claude-opus-4-8"]["limits"]["max_output_tokens"])
        self.assertEqual("high", recommendations["claude-opus-4-8"]["runtime"]["claude_code_default_effort"])
        self.assertEqual("xhigh", recommendations["claude-opus-4-8"]["runtime"]["claude_code_max_effort"])
        self.assertEqual("adaptive", recommendations["claude-opus-4-8"]["runtime"]["thinking_mode"])
        self.assertTrue(recommendations["claude-opus-4-8"]["runtime"]["fast_mode"]["available"])
        self.assertIn("temperature", recommendations["claude-opus-4-8"]["runtime"]["unsupported_sampling_parameters"])
        self.assertEqual("fast", recommendations["claude-haiku-4-5"]["recommended_preset"])
        self.assertEqual(2048, recommendations["claude-haiku-4-5"]["parameters"]["max_output_tokens"])
        self.assertEqual(200000, recommendations["claude-haiku-4-5"]["limits"]["context_window"])

    def test_anthropic_docs_registry_survives_api_key_state_changes(self):
        pcfg_with_key = {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-real", "current_model": "claude-sonnet-4-6"}
        pcfg_without_key = {"base_url": "https://api.anthropic.com", "api_key": "", "current_model": "claude-sonnet-4-6"}

        with tempfile.TemporaryDirectory() as td:
            cache_path = Path(td) / "model-list-cache.json"
            registry_path = Path(td) / "model-registry.json"
            with (
                mock.patch.object(claude_any, "MODEL_LIST_CACHE_PATH", cache_path),
                mock.patch.object(claude_any, "MODEL_REGISTRY_PATH", registry_path),
            ):
                claude_any.write_model_registry(
                    "anthropic",
                    pcfg_with_key,
                    ["claude-opus-4-8", "claude-sonnet-4-6"],
                    "anthropic-docs",
                )
                cached = claude_any.read_model_list_cache("anthropic", pcfg_without_key)

        self.assertEqual(["claude-opus-4-8", "claude-sonnet-4-6"], cached)

    def test_native_model_panel_force_refresh_shows_latest_public_models(self):
        pcfg = {"base_url": "https://api.anthropic.com", "api_key": "", "current_model": "claude-sonnet-4-6"}

        with (
            mock.patch.object(claude_any, "read_model_list_cache", return_value=None),
            mock.patch.object(claude_any, "http_json", side_effect=RuntimeError("missing api key")),
            mock.patch.object(claude_any, "fetch_anthropic_public_model_ids", return_value=["claude-opus-4-8", "claude-sonnet-4-6"]),
            mock.patch.object(claude_any, "write_model_list_cache"),
        ):
            rows, values = claude_any.model_panel_rows("anthropic", pcfg, fetch=True, force_refresh=True)

        self.assertIn("claude-opus-4-8", values)
        self.assertTrue(any("claude-opus-4-8" in row for row in rows))


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

    def test_stop_router_processes_uses_posix_port_fallback(self):
        with (
            mock.patch.object(claude_any.os, "name", "posix"),
            mock.patch.object(claude_any, "terminate_pid_file", return_value=False) as pid_file,
            mock.patch.object(claude_any, "terminate_matching_processes", return_value=False) as match,
            mock.patch.object(claude_any, "terminate_posix_port", return_value=True) as port,
        ):
            result = claude_any.stop_router_processes(quiet=True)

        self.assertTrue(result)
        pid_file.assert_called_once()
        self.assertEqual(2, match.call_count)
        port.assert_called_once_with(claude_any.ROUTER_PORT, "claude-any router", quiet=True)

    def test_posix_pids_on_port_parses_ss_listener_pid(self):
        class FakeProcess:
            stdout = 'LISTEN 0 4096 127.0.0.1:8799 0.0.0.0:* users:(("python",pid=4321,fd=4))'
            stderr = ""

        def fake_which(name):
            return f"/usr/bin/{name}" if name == "ss" else None

        with (
            mock.patch.object(claude_any.os, "name", "posix"),
            mock.patch.object(claude_any, "linux_procfs_pids_on_port", return_value=[]),
            mock.patch.object(claude_any.shutil, "which", side_effect=fake_which),
            mock.patch.object(claude_any.subprocess, "run", return_value=FakeProcess()),
            mock.patch.object(claude_any.os, "getpid", return_value=100),
            mock.patch.object(claude_any.os, "getppid", return_value=101),
        ):
            self.assertEqual([4321], claude_any.posix_pids_on_port(8799))

    def test_posix_pids_on_port_uses_procfs_fallback_without_tools(self):
        with (
            mock.patch.object(claude_any.os, "name", "posix"),
            mock.patch.object(claude_any, "linux_procfs_pids_on_port", return_value=[5555]),
            mock.patch.object(claude_any.shutil, "which", return_value=None),
            mock.patch.object(claude_any.os, "getpid", return_value=100),
            mock.patch.object(claude_any.os, "getppid", return_value=101),
        ):
            self.assertEqual([5555], claude_any.posix_pids_on_port(8799))

    def test_terminate_router_health_pid_uses_health_pid(self):
        with mock.patch.object(claude_any, "terminate_pid", return_value=True) as terminate:
            result = claude_any.terminate_router_health_pid({"pid": 2468}, quiet=True)

        self.assertTrue(result)
        terminate.assert_called_once_with(2468, "claude-any router", quiet=True)

    def test_ensure_router_port_available_for_spawn_clears_empty_port(self):
        with (
            mock.patch.object(claude_any, "terminate_router_health_pid", return_value=False),
            mock.patch.object(claude_any, "stop_router_processes", return_value=False) as stop,
            mock.patch.object(claude_any, "router_health", return_value=None),
            mock.patch.object(claude_any, "router_port_listener_pids", return_value=[]),
            mock.patch.object(claude_any, "router_log"),
        ):
            claude_any.ensure_router_port_available_for_spawn("test", None, max_wait_seconds=0.2)

        stop.assert_called()

    def test_ensure_router_port_available_for_spawn_reports_remaining_pids(self):
        with (
            mock.patch.object(claude_any, "terminate_router_health_pid", return_value=False),
            mock.patch.object(claude_any, "stop_router_processes", return_value=False),
            mock.patch.object(claude_any, "router_health", return_value={"version": "old", "source_fingerprint": "abc", "pid": 777}),
            mock.patch.object(claude_any, "router_port_listener_pids", return_value=[777]),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                claude_any.ensure_router_port_available_for_spawn("test", {"pid": 777}, max_wait_seconds=0.2)

        self.assertIn("listener_pids=[777]", str(ctx.exception))
        self.assertIn("version=old", str(ctx.exception))


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

    def test_routed_anthropic_respects_managed_services_toggle(self):
        cfg = {"cleanup": {"managed_services_on_launch": False}}
        pcfg = {"route_through_router": True}
        with (
            mock.patch.object(claude_any, "stop_router_processes") as stop,
            mock.patch.object(claude_any, "stop_router_with_guarantee") as guarantee,
            mock.patch.object(claude_any, "stop_ncp_proxy"),
        ):
            claude_any.cleanup_managed_services_for_provider("anthropic", pcfg, cfg, quiet=True)

        stop.assert_not_called()
        guarantee.assert_not_called()


if __name__ == "__main__":
    unittest.main()
