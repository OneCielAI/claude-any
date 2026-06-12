#!/usr/bin/env python3
"""Live DoD verification: patched call_advisor_text against the real Anthropic API.

Runs the actual claude-any advisor code path (advisor_request ->
anthropic_system_with_advisor -> advisor_endpoint -> post_json_with_rate_retry)
in anthropic routed mode with the local Claude Code OAuth token.
Isolated via CLAUDE_ANY_CONFIG_DIR (set by the caller).
"""
import json
import sys

sys.path.insert(0, "/tmp/ca-fix")
import claude_any  # noqa: E402

token = json.load(open("/home/frank/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

pcfg = {
    "base_url": "https://api.anthropic.com",
    "api_key": "",
    "advisor_model": "claude-sonnet-4-6",
    "route_through_router": True,
    "force_query_string": "beta=true",
    "request_timeout_ms": 120000,
}
body = {
    "model": "claude-haiku-4-5",
    "system": [
        {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."},
        {"type": "text", "text": "Session instructions: the user is testing the /advisor feature end to end."},
    ],
    "messages": [
        {
            "role": "user",
            "content": [{
                "type": "text",
                "text": "CLAUDE_ANY_ADVISOR_CALL\nFocus: confirm you received this advisor request; start your reply with ADVISOR_FIX_OK.",
            }],
        },
    ],
}


class Headers(dict):
    def get(self, key, default=None):  # case-insensitive like http headers
        return super().get(str(key).lower(), default)


inbound = Headers({
    "authorization": f"Bearer {token}",
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14",
})

print("endpoint:", claude_any.advisor_endpoint("anthropic", pcfg))
sys_blocks = claude_any.advisor_request("anthropic", "claude-sonnet-4-6", body, pcfg)["system"]
print("system[0]:", sys_blocks[0]["text"][:60])
print("system[1]:", sys_blocks[1]["text"][:60])
try:
    text = claude_any.call_advisor_text(
        "anthropic",
        pcfg,
        body,
        inbound_headers=inbound,
        allow_rate_limit_wait=False,
        retry_rate_limits=False,
        raise_errors=True,
    )
    print("RESULT: SUCCESS")
    print("advisor text:", (text or "")[:500])
except Exception as exc:
    print(f"RESULT: FAILED {type(exc).__name__}: {exc}")
    sys.exit(1)
