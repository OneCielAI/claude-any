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
        self.assertIn("active Claude Code session", html)

    def test_web_chat_posts_to_channel_bridge_and_streams_replies(self):
        cfg = self._cfg()
        provider, pcfg = claude_any.get_current_provider(cfg)
        model = claude_any.current_alias(cfg)

        html = claude_any.render_web_chat_html(cfg, provider, pcfg)

        self.assertIn("Session Web Chat", html)
        self.assertIn("/ca/channel/messages", html)
        self.assertIn("/ca/channel/stream", html)
        self.assertIn("active Claude Code session", html)
        self.assertIn("configured tools and MCP servers remain available", html)
        self.assertIn("claude-any-router send_message tool", html)
        self.assertIn("delivery: ['llm', 'native']", html)
        self.assertNotIn("TEXT_ONLY_SYSTEM_PROMPT", html)
        self.assertNotIn("system: TEXT_ONLY_SYSTEM_PROMPT", html)
        self.assertIn(model, html)
        self.assertIn(".bubble", html)
        self.assertIn("bubble.className = 'bubble'", html)
        self.assertIn("function renderMarkdown(text)", html)
        self.assertIn("function renderMarkdownTable(lines, startIndex)", html)
        self.assertIn(".markdown table", html)
        self.assertIn("bubble.innerHTML = renderMarkdown(text)", html)
        self.assertIn("bubble.textContent = text", html)

    def test_web_chat_markdown_renderer_sanitizes_and_supports_tables(self):
        cfg = self._cfg()
        provider, pcfg = claude_any.get_current_provider(cfg)

        html = claude_any.render_web_chat_html(cfg, provider, pcfg)

        self.assertIn("escapeHtml(value)", html)
        self.assertIn("safeHref(value)", html)
        self.assertIn("isMarkdownTableDelimiter(line)", html)
        self.assertIn("<table>", html)
        self.assertIn("<thead><tr>", html)
        self.assertIn("<tbody>", html)
        self.assertIn("rel=\"noopener noreferrer\"", html)
        self.assertNotIn("marked.min.js", html)
        self.assertNotIn("cdn.jsdelivr", html)

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
