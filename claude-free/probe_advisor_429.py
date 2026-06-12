#!/usr/bin/env python3
"""Reproduce the /advisor rate_limit_error in anthropic routed mode.

Replicates claude-any's advisor upstream request shape against
api.anthropic.com with the local Claude Code OAuth token, A/B-testing:
  (1) presence of the ?beta=true query (advisor_endpoint omits it today)
  (2) system prompt shape (claude-any Advisor prompt vs Claude Code identity)

Prints status + error body per probe. Never prints the token.
"""
import json
import time
import urllib.error
import urllib.request

token = json.load(open("/home/frank/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

ADVISOR_PROMPT = (
    "You are claude-any Advisor, a stronger reviewer model. Review the current task state and provide "
    "concise guidance: the main blocker, the next concrete action, and a validation step."
)
CLAUDE_CODE_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."
BASE = "https://api.anthropic.com/v1/messages"
BETA_HEADER = "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14"


def probe(name: str, url: str, system_text: str, model: str = "claude-sonnet-4-6") -> None:
    body = {
        "model": model,
        "max_tokens": 16,
        "system": [{"type": "text", "text": system_text}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Reply with exactly: OK"}]}],
    }
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "authorization": f"Bearer {token}",
        "anthropic-beta": BETA_HEADER,
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            text = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict))
            print(f"{name}: HTTP {resp.status} OK text={text!r}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        print(
            f"{name}: HTTP {e.code} body={raw[:400]} "
            f"retry-after={e.headers.get('retry-after')} "
            f"x-ratelimit-reset={e.headers.get('anthropic-ratelimit-requests-reset')}"
        )
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {e}")
    time.sleep(3)


probe("A advisor-sys no-query  ", BASE, ADVISOR_PROMPT)
probe("B advisor-sys beta=true ", BASE + "?beta=true", ADVISOR_PROMPT)
probe("C cc-sys      no-query  ", BASE, CLAUDE_CODE_PROMPT)
probe("D cc-sys      beta=true ", BASE + "?beta=true", CLAUDE_CODE_PROMPT)
