import unittest
from unittest import mock

import claude_any


class InboundBetaFlagTests(unittest.TestCase):
    def test_beta_true_detected(self):
        self.assertTrue(claude_any.inbound_query_has_beta_flag("/v1/messages?beta=true"))

    def test_beta_one_detected(self):
        self.assertTrue(claude_any.inbound_query_has_beta_flag("/v1/messages?beta=1"))

    def test_beta_among_other_params(self):
        self.assertTrue(
            claude_any.inbound_query_has_beta_flag("/v1/messages?foo=bar&beta=true&x=2")
        )

    def test_no_query_is_false(self):
        self.assertFalse(claude_any.inbound_query_has_beta_flag("/v1/messages"))

    def test_beta_false_is_false(self):
        self.assertFalse(claude_any.inbound_query_has_beta_flag("/v1/messages?beta=false"))

    def test_unrelated_param_is_false(self):
        self.assertFalse(claude_any.inbound_query_has_beta_flag("/v1/messages?other=true"))


class UpstreamMessagesQueryTests(unittest.TestCase):
    def test_inbound_beta_propagated(self):
        self.assertEqual(
            "beta=true",
            claude_any.upstream_messages_query({}, "/v1/messages?beta=true"),
        )

    def test_no_query_yields_empty(self):
        self.assertEqual("", claude_any.upstream_messages_query({}, "/v1/messages"))

    def test_force_query_overrides_and_wins(self):
        pcfg = {"force_query_string": "beta=true&foo=bar"}
        self.assertEqual(
            "beta=true&foo=bar",
            claude_any.upstream_messages_query(pcfg, "/v1/messages"),
        )

    def test_force_query_used_even_without_inbound_query(self):
        pcfg = {"force_query_string": "beta=true"}
        self.assertEqual(
            "beta=true",
            claude_any.upstream_messages_query(pcfg, "/v1/messages"),
        )

    def test_force_query_leading_question_mark_stripped(self):
        pcfg = {"force_query_string": "?beta=1"}
        self.assertEqual("beta=1", claude_any.upstream_messages_query(pcfg, "/v1/messages"))


class ForceQueryProviderOptionTests(unittest.TestCase):
    def test_set_force_query_string(self):
        pcfg = {}
        claude_any.apply_provider_option("anthropic", pcfg, "force_query_string=beta=true")
        self.assertEqual("beta=true", pcfg["force_query_string"])

    def test_alias_force_query_and_leading_question_mark(self):
        pcfg = {}
        claude_any.apply_provider_option("anthropic", pcfg, "force_query=?beta=true&x=2")
        self.assertEqual("beta=true&x=2", pcfg["force_query_string"])

    def test_empty_value_clears(self):
        pcfg = {"force_query_string": "beta=true"}
        claude_any.apply_provider_option("anthropic", pcfg, "force_query_string=")
        self.assertNotIn("force_query_string", pcfg)

    def test_unset_clears(self):
        pcfg = {"force_query_string": "beta=true"}
        claude_any.apply_provider_option("anthropic", pcfg, "unset:force_query_string")
        self.assertNotIn("force_query_string", pcfg)

    def test_status_shows_force_query(self):
        pcfg = {"route_through_router": True, "force_query_string": "beta=true"}
        status = claude_any.provider_options_status("anthropic", pcfg)
        self.assertIn("force_query=beta=true", status)

    def test_status_omits_force_query_when_unset(self):
        pcfg = {"route_through_router": True}
        status = claude_any.provider_options_status("anthropic", pcfg)
        self.assertNotIn("force_query", status)


class ForceQueryMenuTests(unittest.TestCase):
    def test_option_appears_in_anthropic_menu(self):
        rows, values = claude_any.llm_option_panel_rows(
            "anthropic", {"route_through_router": True}
        )
        self.assertIn("force_query_string", values)

    def test_ip_family_appears_only_for_routed_anthropic_menu(self):
        _rows, native_values = claude_any.llm_option_panel_rows(
            "anthropic", {"route_through_router": False}
        )
        routed_rows, routed_values = claude_any.llm_option_panel_rows(
            "anthropic", {"route_through_router": True}
        )

        self.assertNotIn("ip_family", native_values)
        self.assertIn("ip_family", routed_values)
        self.assertIn("auto", routed_rows[routed_values.index("ip_family")])

    def test_prompt_default_reflects_current_value(self):
        self.assertEqual(
            "",
            claude_any.llm_option_prompt_default("anthropic", {}, "force_query_string"),
        )
        self.assertEqual(
            "beta=true",
            claude_any.llm_option_prompt_default(
                "anthropic", {"force_query_string": "beta=true"}, "force_query_string"
            ),
        )

    def _run_menu_set(self, pcfg, value):
        cfg = {"providers": {"anthropic": pcfg}, "current_provider": "anthropic"}
        with mock.patch.object(claude_any, "load_config", lambda: cfg), \
             mock.patch.object(claude_any, "save_config", lambda c: None), \
             mock.patch.object(claude_any, "clear_model_cache", lambda: None):
            claude_any.set_llm_option_config("anthropic", "force_query_string", value)
        return pcfg

    def test_menu_set_stores_value(self):
        pcfg = {"route_through_router": True}
        self._run_menu_set(pcfg, "beta=true")
        self.assertEqual("beta=true", pcfg.get("force_query_string"))

    def test_menu_set_multi_param(self):
        pcfg = {"route_through_router": True}
        self._run_menu_set(pcfg, "beta=true&foo=1")
        self.assertEqual("beta=true&foo=1", pcfg.get("force_query_string"))

    def test_menu_unset_clears_value(self):
        pcfg = {"route_through_router": True, "force_query_string": "beta=true"}
        self._run_menu_set(pcfg, "unset")
        self.assertNotIn("force_query_string", pcfg)


if __name__ == "__main__":
    unittest.main()
