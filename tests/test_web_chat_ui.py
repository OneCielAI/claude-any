import copy
import unittest

import claude_any


class WebChatUiTests(unittest.TestCase):
    def _cfg(self, provider: str = "ollama-cloud"):
        return {
            "current_provider": provider,
            "providers": {
                provider: copy.deepcopy(claude_any.DEFAULT_CONFIG["providers"][provider]),
            },
        }

    def test_router_home_links_browser_web_chat(self):
        cfg = self._cfg()
        provider, pcfg = claude_any.get_current_provider(cfg)

        html = claude_any.render_router_home_html(cfg, provider, pcfg)

        self.assertIn("/ca/web/chat", html)
        self.assertIn("Standalone browser chat", html)

    def test_web_chat_posts_to_router_messages_endpoint(self):
        cfg = self._cfg()
        provider, pcfg = claude_any.get_current_provider(cfg)
        model = claude_any.current_alias(cfg)

        html = claude_any.render_web_chat_html(cfg, provider, pcfg)

        self.assertIn("Provider Web Chat", html)
        self.assertIn("/v1/messages", html)
        self.assertIn("not attached to an existing Claude Code terminal session", html)
        self.assertIn("standalone browser conversation", html)
        self.assertIn("text/event-stream", html)
        self.assertIn(model, html)
        self.assertIn(".bubble", html)
        self.assertIn("bubble.className = 'bubble'", html)

    def test_web_chat_reports_anthropic_routed_mode(self):
        cfg = self._cfg("anthropic")
        pcfg = cfg["providers"]["anthropic"]
        pcfg["api_key"] = "sk-ant-real"
        pcfg["route_through_router"] = True

        html = claude_any.render_web_chat_html(cfg, "anthropic", pcfg)

        self.assertIn("anthropic-routed", html)
        self.assertIn("API key: set (Anthropic routed)", html)


if __name__ == "__main__":
    unittest.main()
