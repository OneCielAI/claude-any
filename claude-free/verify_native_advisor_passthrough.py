#!/usr/bin/env python3
"""Live DoD verification: Claude Code native advisor flow passes through the
patched claude-any router in Anthropic routed mode.

Sends a /v1/messages request shaped like a native-advisor session turn
(advisor_20260301 server tool in tools, Claude Code identity system, OAuth
auth) to an isolated patched router and checks the upstream accepts it.
The router log must NOT contain the "stripped autonomous advisor server
tool" line.
"""
import json
import sys
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
token = json.load(open("/home/frank/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

body = {
    "model": "claude-haiku-4-5",
    "max_tokens": 32,
    "stream": False,
    "system": [
        {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."},
    ],
    "tools": [
        {"name": "Bash", "description": "run a shell command", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}},
        {"type": "advisor_20260301", "name": "advisor", "model": "claude-sonnet-4-6"},
    ],
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "Reply with exactly: OK"}]},
    ],
}
headers = {
    "content-type": "application/json",
    "anthropic-version": "2023-06-01",
    "authorization": f"Bearer {token}",
    "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,advisor-tool-2026-03-01",
}
url = f"http://127.0.0.1:{PORT}/v1/messages?beta=true"
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict))
        print(f"RESULT: HTTP {resp.status} stop_reason={data.get('stop_reason')} text={text!r}")
except urllib.error.HTTPError as e:
    raw = e.read().decode("utf-8", errors="ignore")
    print(f"RESULT: HTTP {e.code} body={raw[:400]}")
    sys.exit(1)
