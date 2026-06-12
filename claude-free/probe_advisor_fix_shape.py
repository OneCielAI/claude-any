#!/usr/bin/env python3
"""Verify the planned advisor system-block fix shape passes the OAuth gate.

E: [cc-identity, advisor-prompt] — identity first, advisor instruction second
F: [cc-identity, advisor-prompt, original-session-context, extra-context]
   — the full shape anthropic_system_with_advisor would emit after the fix
"""
import json
import time
import urllib.error
import urllib.request

token = json.load(open("/home/frank/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

CC = "You are Claude Code, Anthropic's official CLI for Claude."
ADVISOR_PROMPT = (
    "You are claude-any Advisor, a stronger reviewer model. Review the current task state and provide "
    "concise guidance: the main blocker, the next concrete action, and a validation step."
)
BASE = "https://api.anthropic.com/v1/messages?beta=true"
BETA_HEADER = "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14"


def probe(name: str, system_blocks: list) -> None:
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 16,
        "system": system_blocks,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Reply with exactly: OK"}]}],
    }
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "authorization": f"Bearer {token}",
        "anthropic-beta": BETA_HEADER,
    }
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            text = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict))
            print(f"{name}: HTTP {resp.status} OK text={text!r}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        print(f"{name}: HTTP {e.code} body={raw[:300]}")
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {e}")
    time.sleep(3)


probe("E identity+advisor        ", [
    {"type": "text", "text": CC},
    {"type": "text", "text": ADVISOR_PROMPT},
])
probe("F identity+advisor+context", [
    {"type": "text", "text": CC},
    {"type": "text", "text": ADVISOR_PROMPT},
    {"type": "text", "text": "Original session system context:\nYou are a helpful coding agent working in a git repo."},
    {"type": "text", "text": "Additional system context from message history:\ngit status output here."},
])
