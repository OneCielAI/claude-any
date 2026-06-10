import unittest

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


if __name__ == "__main__":
    unittest.main()
