# Responsible Disclosure Draft

## Summary

When Claude Code is run through a local Anthropic-compatible proxy, the proxy can
forward the streaming response body while dropping Anthropic response headers.
Claude Code appears to use those headers for quota/rate-limit/account-status
state, so routed mode may show incorrect usage/quota behavior even though the
upstream `/v1/messages` request was processed.

## Observed Behavior

- Native Claude Code receives response headers from Anthropic.
- Routed Claude Code receives only proxy-generated headers.
- SSE `usage` events can still be present in the response body.
- Client-visible quota/rate-limit state may therefore diverge from server state.

## Local POC

The attached `claude-free/run_claude_any_routed_poc.py` starts:

- a mock Anthropic-compatible streaming upstream;
- a real `claude-any` router configured in isolated `anthropic routed` mode;
- a direct `/v1/messages` probe against that real router;
- optionally, the real `claude` CLI pointed at the isolated routed setup.

The POC demonstrates that the real `claude-any anthropic routed` path can
preserve SSE `usage` events while dropping client-visible quota/rate-limit
headers. With `--execute-claude`, the evidence directory also contains
`claude.stdout.txt` showing that a real Claude Code process successfully
completed against the isolated routed setup.

Expected generated evidence:

- `timeline.log` shows the mock upstream emitting Anthropic-like headers.
- `timeline.log` shows the real routed client response lacks those headers.
- `evidence.json` asserts `router_probe_saw_usage_events=true`.
- `evidence.json` asserts `router_probe_lost_anthropic_quota_headers=true`.
- `evidence.json` asserts `router_probe_lost_request_id=true`.
- `claude.stdout.txt` contains `POC_OK` when `--execute-claude` is used.

## Security Impact

This is not presented as proof of server-side billing bypass. The concrete
impact is client-side accounting/quota visibility risk in routed mode. If Claude
Code relies on response headers to surface or enforce OAuth subscriber quota
state, a compatible proxy should know which headers must be preserved.

## Request

Please confirm which response headers and SSE events Claude Code requires for
accurate quota/rate-limit/usage state when `ANTHROPIC_BASE_URL` points to a local
Anthropic-compatible proxy.

Relevant header families observed in local code analysis:

- `anthropic-ratelimit-unified-*`
- `retry-after`
- `request-id` / `x-request-id`

## Suggested Compatibility Guidance

Document a safe response-header forwarding set for local proxies:

- forward request IDs;
- forward Anthropic rate-limit/quota headers;
- forward `retry-after`;
- do not forward hop-by-hop headers such as `connection`, `transfer-encoding`,
  `content-length`, `content-encoding`, `keep-alive`, or `upgrade`.
