# claude-any handoff

Date: 2026-05-25
Stable release being promoted: `@oneciel-ai/claude-any@0.1.101`
Latest tested nightly: `@oneciel-ai/claude-any@0.1.100-nightly.20260525-080725.2424094`
Current branch: `nightly`
Current pushed commit: `2424094` (`Show direct channel handling in terminal`)

## Current state

`claude-any` is a Claude Code provider/router wrapper with MCP proxy support, channel message delivery, provider selection, and npm-based distribution.

The latest production path is:

- `0.1.101` is a stable hotfix for routed DeepSeek.com Claude Code launches:
  it passes the configured DeepSeek API key through `ANTHROPIC_AUTH_TOKEN`
  while keeping `ANTHROPIC_API_KEY` unset, avoiding Claude Code governor 401
  failures after `claude-any test` succeeds.
- `0.1.100` promotes the current `nightly` line to stable.
- DeepSeek.com is a first-class routed provider using `https://api.deepseek.com/anthropic`.
- Non-Claude-Native providers route through claude-any; Claude Native suppresses routing env vars and stops the router before launch.
- Anthropic still defaults to direct Claude Native, but can opt into `route_through_router` when router-owned SSE/channel/web-chat/observability is required; routed Anthropic requires an Anthropic API key.
- Routed sessions default to a stable per-user router port (`CLAUDE_ANY_ROUTER_PORT`, otherwise `8799 + uid % 1000` on POSIX).
- Stale same-user routers are cleared by port/PID/procfs fallbacks before spawn.
- Channel delivery choices are hidden from normal routed-provider launch flow; routed sessions use the `llm` channel delivery path.
- MCP notification events are persisted into `chat-messages.jsonl`.
- AI-Net/SSE notifications can trigger immediate direct LLM handling, use MCP tools, and receive tool-result follow-up context.
- Direct channel handling no longer spawns hidden Claude Code `-p`; it uses the routed `/v1/messages` path, executes MCP tools over the initialized SSE connection, forwards `tool_result` blocks back to the same LLM turn, queues summaries durably, and injects those summaries into the next visible routed request.
- The router now has a local session chat UI at `/ca/web/chat`. It posts browser messages into `/ca/channel/messages`, the active Claude Code session consumes them through the channel bridge with its normal tools/MCP servers, and replies return through the built-in `claude-any-router` MCP `send_message` tool plus `/ca/channel/stream`. Browser-to-Claude file attachments go through `/ca/channel/files`, and Claude-to-browser file replies use the built-in `send_file` MCP tool.

The previous stable `0.1.99` included automatic MCP channel capability probing through timeout/error classification. `0.1.100` adds DeepSeek.com, shared-host router isolation, automatic API-key setup routing, unique nightly versions, router cleanup hardening, and LLM channel direct handling diagnostics.

## Current next-nightly work: remove internal `claude -p`

Do not continue the automatic channel-notification path by spawning a hidden
`claude -p` process. The previous 0.1.100 direct handler could run:

```text
claude --dangerously-skip-permissions --model ... --mcp-config ... -p "[claude-any channel inbox] ..."
```

That made AI-Net messages actionable because the headless Claude Code process
can use MCP tools, but it is the wrong long-term design:

- It is a separate Claude Code process from the user-visible interactive session.
- Its stdout is captured by claude-any, so "show the user a summary" is not guaranteed to appear in the visible Claude Code UI.
- Recent Anthropic billing/policy behavior can treat `-p` as a separate usage path, so automatic background channel handling must not create hidden `-p` calls.

Implemented direction for the next branch:

1. Reuse the existing routed `/v1/messages` path without invoking Claude Code `-p`.
2. Preserve MCP/tool ability with a controlled SSE MCP JSON-RPC client path and direct `tools/call` execution.
3. Store direct handling summaries in `channel-llm-summary-queue.jsonl` and inject them into the next interactive `/v1/messages` request so the visible Claude Code session summarizes what happened.
4. Keep terminal notices as diagnostic-only; do not rely on raw TTY writes as the product surface.
5. Keep user-initiated `claude-any ... -p` pass-through working. The ban is on internal automatic background `-p` launches for channel notifications.

Useful logs:

- `channel_sse_mcp_rpc_response`
- `channel_llm_direct_router_request`
- `channel_llm_tool_call`
- `channel_llm_tool_result_forwarded`
- `channel_llm_summary_queued`
- `channel_llm_summary_injected`
- `channel_llm_direct_response`

Detailed investigation notes are in `docs/no-p-channel-research.md`. The key
finding is that Claude Code's own bridge and team-agent paths queue inbound
messages into the active REPL; print mode has separate headless handling, so it
should not be used as the product path for automatic channel notifications.

## Recent release sequence

### 0.1.91

Added JSONL stdio framing support for `mcp-server-fetch`.

Reason: `web_fetch` was failing because the proxy expected one MCP stdio shape while `mcp-server-fetch` emitted another. The proxy now converts between Claude MCP Content-Length frames and JSONL where needed.

### 0.1.92

Made `web_fetch` runner resolution more robust.

Behavior:

- Prefer `uvx` when present.
- Fall back to `uv tool run`.
- Fall back to `python -m uv`.
- Fall back to `pipx run`.
- If no runner exists, skip `web_fetch` and log `web_fetch_disabled_missing_runner install=uvx_or_uv` instead of letting `/mcp` show a hard failure from missing `uvx`.

### 0.1.93

Changed native channel MCP SSE delivery to replay until client acknowledgment.

Important logs:

- `channel_mcp_session_started`
- `channel_mcp_resume`
- `channel_mcp_notification_prepared`
- `channel_mcp_notification_written`
- `channel_mcp_session_closed`

Reason: the router could receive an SSE/channel event, but Claude Code might reconnect before the event was actually consumed. The cursor now advances only after the client acknowledges through the MCP message flow, not merely after a socket write attempt.

### 0.1.94

Fixed stdin synthetic Enter handling for raw terminals.

Observed issue:

- Logs showed `channel_stdin_proxy_injected ... enter=cr`.
- The prompt text appeared in Claude Code's input area.
- It was not submitted.

Fix:

- Preserve observed user Enter behavior.
- Normalize bare `CR` to `CRLF` for synthetic injected submits.

### 0.1.95

Changed default channel delivery to `native`.

Behavior:

- `DEFAULT_CONFIG["claude_code"]["channel_delivery"]` is now `native`.
- Old default `stdin` configs are migrated to `native` through marker `default_channel_delivery_native_20260520`.
- The menu presents `native` before `stdin`.
- `normalize_channel_delivery` defaults empty, `auto`, and invalid values to `native`.

### 0.1.96

Added platform-aware submit sequence handling for `stdin` fallback.

Behavior:

- First synthetic stdin injection uses a platform-safe submit default.
- Current default submit bytes are `CRLF`.
- Explicit override remains available with `CLAUDE_ANY_CHANNEL_WAKE_ENTER=lf|cr|crlf`.
- Empty, `auto`, `default`, and `platform` mean platform default.
- If the user presses Enter during the session, stdin proxy observes that sequence and follows it.
- Bare observed `CR` is still normalized to `CRLF` for synthetic injection.

Important logs:

- `channel_stdin_proxy_enter_default enter=crlf os=... platform=...`
- `channel_stdin_proxy_enter_observed enter=...`
- `channel_stdin_proxy_injected ... enter=...`

### 0.1.97

Added automatic MCP channel capability detection for `--channels`.

Behavior:

- The router can inspect configured MCP servers for channel-capable tools/resources instead of requiring all channel wiring to be known ahead of time.
- Channel-capable servers can be surfaced to the Claude Code launch path automatically.
- This is the start of making native channel delivery less dependent on manual config.

### 0.1.98

Cached channel probe results and surfaced them in the menu.

Behavior:

- Probe results are stored with a cache version and timestamp.
- The pre-launch menu can show channel probe state and allow re-probing.
- Tests cover cache reads/writes and menu state.

### 0.1.99

Distinguished channel probe timeout from missing channel capability.

Behavior:

- Probe failures now preserve stderr/exit-code detail where available.
- Timeouts are reported differently from "server does not expose channel capability".
- This reduces false negatives when a server is slow or fails during startup.

### 0.1.100

The `nightly` branch currently contains the release candidate being promoted to stable:

- Split npm publishing into stable `latest` and pre-release `nightly` channels.
- Made nightly version numbers unique with UTC seconds and short SHA.
- Added and then simplified an MCP channel-capable server author guide.
- Reframed the guide to point at Anthropic's MCP spec rather than maintaining a duplicated local protocol reference.
- Extended channel probing so SSE MCP servers are probed for channel capability too.
- Changed the stdio channel probe default to MCP-spec newline-delimited JSON (`jsonl`/NDJSON). Legacy `Content-Length` framed probing is still available through `claude_any_stdio: "framed"` or equivalent aliases.
- Added Claude Native provider semantics: `anthropic` is now labeled `Claude Native`; aliases include `claude-native`, `native`, and `claude-code`; launches suppress claude-any routing/model/advisor env overrides and guarantee the router is stopped before Claude Code starts.
- Added DeepSeek.com routed provider semantics and defaults.
- Opened the API-key setup path automatically when DeepSeek or another key-required provider blocks launch.
- Routed non-native launches through claude-any instead of exposing native channel modes that cannot carry the planned `/llm` workflow.
- Hid channel delivery choices from the normal options menu because routed sessions should use `llm`.
- Fixed AI-Net DM channel handling and immediate SSE receipt processing.
- Added direct channel tool-result context preservation.
- Added best-effort terminal notice output for direct channel handling results.
- Added stale router cleanup by listening port, PID, and procfs fallback.
- Added per-user router MCP ports to avoid Robert/Sarah/worker sessions sharing one `127.0.0.1:8799` router on a shared host.

## Provider modes

### Claude Native

`anthropic` is intentionally presented as `Claude Native`.

Use this mode when the user wants Claude Code's own Anthropic/OAuth/default behavior, not claude-any routing.

Aliases:

- `anthropic`
- `claude`
- `claude-native`
- `native`
- `claude-code`

Claude Native contract:

- `env_vars()` only sets `CLAUDE_ANY_PROVIDER=anthropic` as an internal marker.
- If the user has a stored Anthropic API key, `ANTHROPIC_API_KEY` is passed through.
- If no stored key exists, no Anthropic auth env var is set; Claude Code's own OAuth/default credentials win.
- claude-any does not set `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `ANTHROPIC_AUTH_TOKEN`, advisor model, max output token, auto-compact, attribution, or model alias variables.
- Before launching Claude Code, claude-any must guarantee the local router is stopped so stale router state cannot intercept the native Claude Code session.

Important logs:

- `router_kill_guarantee reason=native_anthropic_launch state=already_down`
- `router_kill_guarantee reason=native_anthropic_launch state=killed elapsed_ms=...`
- `router_kill_guarantee reason=native_anthropic_launch state=still_up_after_...`

If the router remains alive after the shutdown deadline, launch aborts with a `RuntimeError`. This is deliberate.

### Routed Providers

Non-native providers still use claude-any's routing env and model aliases as before:

- `ollama`
- `ollama-cloud`
- `vllm`
- `nvidia-hosted`
- `self-hosted-nim`

## Channel delivery modes

### LLM

LLM delivery is the default routed-provider channel path for 0.1.100.

Use this when Claude Any, not Claude Native, is responsible for receiving
external channel/SSE notifications and deciding how the current agent should
respond.

LLM channel flow:

1. External MCP/SSE source sends `notifications/message` or `notifications/claude/channel`.
2. Router stores a normalized message in `chat-messages.jsonl`.
3. Router marks eligible messages for direct handling and records the channel cursor.
4. The current 0.1.100 implementation may invoke a background `claude -p` process with the MCP proxy config so tool calls can be made.
5. Tool calls from that background path store context with `channel_llm_tool_context_stored`; tool results are supplied through `channel_llm_tool_result_context_injected`.
6. The final response is logged as `channel_llm_direct_response` and a best-effort terminal notice is written.

Known limitation: step 4 must be removed in the next nightly. Do not rely on
internal `claude -p` for automatic channel handling going forward.

### Native

Native is retained for Claude Code's experimental MCP channel behavior but is
not the normal routed-provider path.

Use this when Claude Code can connect to the built-in `claude-any-router` MCP server.

Expected `/mcp` shape:

- `claude-any-router` connected
- `ai-net` connected when configured
- `duckduckgo` connected when configured
- `web_fetch` connected only when an available runner exists

Native channel flow:

1. External MCP server sends `notifications/message` or `notifications/claude/channel`.
2. Router stores a normalized message in `chat-messages.jsonl`.
3. Claude Code connects to `/ca/mcp/sse`.
4. Router sends channel notification events over SSE.
5. Router waits for MCP client acknowledgment before advancing the native channel cursor.

### Stdin

Stdin is a fallback/manual test path.

Use this when native MCP delivery is unavailable or when explicitly testing prompt injection behavior.

Stdin channel flow:

1. External MCP server sends a notification.
2. Router stores a normalized message in `chat-messages.jsonl`.
3. Router watches the chat message file.
4. Router writes `Ctrl-U`, the compact wake prompt, and submit bytes to Claude Code's PTY.
5. Submit bytes are selected by explicit env override, platform default, or observed user input.

## MCP channel capability probing

Channel probing detects whether configured MCP servers expose the experimental `claude/channel` capability.

Current behavior:

- Stdio probe default is `jsonl`/NDJSON, matching the MCP stdio wire format.
- `Content-Length` framed probing is treated as legacy opt-in.
- Configure framed probing per server with `claude_any_stdio: "framed"` or aliases such as `content-length` / `lsp`.
- Unknown or empty probe strategy values fall back to `jsonl`.
- SSE MCP servers are also probed for channel capability on `nightly`.
- Probe results are cached in `channel-probe-cache.json` and surfaced in the menu.

Relevant helpers:

- `_channel_probe_strategy_for`
- `_channel_probe_parse_jsonl_responses`
- `_channel_probe_parse_framed_responses`
- `probe_stdio_mcp_for_channel_capability_detailed`
- `CHANNEL_PROBE_CACHE_PATH`

Debug focus:

- If a spec-correct stdio server is missed, check whether it emits exactly one JSON object per line and no embedded newlines.
- If a legacy server is missed, add `claude_any_stdio: "framed"` to its MCP config entry.
- If probing times out, distinguish startup failure from missing capability; timeout and stderr/exit code are now preserved where available.

## Configuration

Main config path:

```text
~/.config/claude-any/config.json
```

MCP proxy server configs:

```text
~/.config/claude-any/mcp-proxy-servers/*.json
```

Router log:

```text
~/.config/claude-any/router.log
```

Channel message store:

```text
~/.config/claude-any/chat-messages.jsonl
```

Native channel cursor:

```text
~/.config/claude-any/channel-mcp-cursor.json
```

Channel probe cache:

```text
~/.config/claude-any/channel-probe-cache.json
```

Do not commit or paste real MCP API keys into docs or issues. Keep values such as `AINET_API_KEY` in local config or environment only.

## Useful commands

Check current package version:

```bash
npm view @oneciel-ai/claude-any version
```

Run all tests:

```bash
npm test
```

Run channel bridge tests only:

```bash
python -m unittest discover -s tests -p "test_channel_bridge.py"
```

Watch recent router channel logs:

```bash
grep -n "channel_sse_message_received\|channel_llm_direct\|channel_llm_tool\|channel_mcp_\|channel_stdin_proxy\|web_fetch_disabled" ~/.config/claude-any/router.log | tail -160
```

Check configured MCP proxy server files:

```bash
find ~/.config/claude-any/mcp-proxy-servers -maxdepth 1 -type f -print -exec sed -n '1,120p' {} \;
```

Force channel delivery mode:

```bash
claude-any channel-delivery llm
claude-any channel-delivery native
claude-any channel-delivery stdin
```

Override stdin synthetic submit bytes:

```bash
CLAUDE_ANY_CHANNEL_WAKE_ENTER=crlf claude-any
CLAUDE_ANY_CHANNEL_WAKE_ENTER=lf claude-any
CLAUDE_ANY_CHANNEL_WAKE_ENTER=cr claude-any
```

## Debug checklist

### LLM channel message is handled but not visible in Claude Code

Check:

- Router log has `channel_sse_message_received`.
- Router log has `channel_llm_direct_router_request`.
- If tools were needed, router log has `channel_llm_tool_call` and
  `channel_llm_tool_result_forwarded`.
- Router log has `channel_llm_summary_queued`.
- On the next routed interactive request, router log has
  `channel_llm_summary_injected`.
- Router log has `channel_llm_direct_response ... chars=N tool_turns=N`.
- The AI-Net room/DM contains the reply sent by the agent.

If the direct response exists but `channel_llm_summary_injected` does not, the
agent handled the notification but the user has not yet made a routed
interactive request where the queued summary can be shown. Terminal notices are
diagnostic only; the durable visible path is the summary queue injection.

### Native channel message is not visible in Claude Code

Check:

- `/mcp` shows `claude-any-router` connected.
- Router log has `channel_mcp_initialized`.
- Router log has `mcp_proxy_notification`.
- Router log has `channel_mcp_notification_prepared`.
- Router log has `channel_mcp_notification_written`.
- Router log cursor uses the expected `last_id`.
- `chat-messages.jsonl` contains the message.

If notifications are received but not displayed, compare:

- `Last-Event-ID` from reconnect logs.
- `channel-mcp-cursor.json`.
- The message id in `chat-messages.jsonl`.

The likely bug class is cursor advancement or MCP client acknowledgment timing.

### Stdin channel message appears in input but is not submitted

Check:

- Router log has `channel_stdin_proxy_enter_default`.
- Router log has `channel_stdin_proxy_injected`.
- The `enter=` label is `crlf`, `lf`, or `cr`.
- If needed, force `CLAUDE_ANY_CHANNEL_WAKE_ENTER=crlf`.

The current default should already be `crlf`.

### `/mcp` shows `web_fetch` failed

Check the router log for:

```text
web_fetch_disabled_missing_runner install=uvx_or_uv
mcp_proxy_start_failed server=web_fetch command=uvx
```

Install one of:

- `uvx`
- `uv`
- `pipx`

The desired behavior is that missing runners skip `web_fetch` cleanly rather than breaking other MCP servers.

### `/mcp` shows `claude-any-router` failed

Check:

- Router is listening on the expected local port. `CLAUDE_ANY_ROUTER_PORT`
  overrides the port; otherwise POSIX defaults to `8799 + (uid % 1000)`.
- `/ca/mcp/sse` returns `200`.
- `/ca/mcp/messages?session=...` returns `200`.
- Router log has `channel_mcp_session_started` followed by `channel_mcp_initialized`.

Repeated 30 second `ConnectionResetError` closes can be normal client reconnect behavior, but a persistent `failed` state in `/mcp` means the client did not complete MCP initialization.

### Claude Native still routes through claude-any

This should not happen on current `nightly`.

Check:

- Selected provider resolves to `anthropic`.
- Provider label is `Claude Native`.
- `claude-any env` does not print `ANTHROPIC_BASE_URL=http://127.0.0.1:PORT` for the per-user router port.
- Router log has a `router_kill_guarantee` entry during launch.
- `claude-any stop` fully stops the router if the guarantee reports `state=still_up...`.

The intended failure mode is to abort launch rather than accidentally route a native Claude Code session through claude-any.

### Channel-capable MCP server is not detected

Check:

- Server type is stdio/command or SSE and is reachable.
- Stdio server uses MCP-spec NDJSON by default.
- Legacy framed stdio servers explicitly set `claude_any_stdio: "framed"`.
- Probe cache is not stale; re-probe from the menu or remove `channel-probe-cache.json`.
- Probe detail records timeout vs missing capability vs process stderr/exit code.

## Release process

Current release path uses GitHub Actions and two npm dist-tags. The
`Publish to npm` workflow is triggered automatically by branch pushes to
`nightly` and `main`.

Do not run `npm publish` locally. Local npm auth can be missing or stale,
which produces misleading `E401`/`E404` results even though the branch-push
workflow publishes with the repository `NPM_TOKEN` secret.

For ongoing work:

1. Commit to `nightly`.
2. Push `nightly`.
3. Watch `CI`.
4. Watch `Publish to npm`.
5. Verify `@oneciel-ai/claude-any@nightly`.

For stable release promotion:

1. Open a PR from `nightly` to `main` using `.github/PULL_REQUEST_TEMPLATE/release.md`.
2. Bump `VERSION` in `claude_any.py` and `version` in `package.json` to the stable `X.Y.Z`.
3. Merge to `main`.
4. Watch `CI`.
5. Watch `Publish to npm`.
6. Verify `@oneciel-ai/claude-any@latest`.
7. Create a matching GitHub Release.
8. Fast-forward `nightly` to `main`.

Commands:

```bash
git status --short --branch
npm test
git add claude_any.py package.json tests docs
git commit -m "..."
git push origin nightly
gh run list --branch nightly --limit 8
gh run watch <run-id> --exit-status
npm view @oneciel-ai/claude-any version gitHead dist.tarball
npm view @oneciel-ai/claude-any@nightly version gitHead dist.tarball
```

Troubleshooting note from 2026-05-23: local `npm whoami` returned `E401`,
and local `npm publish --tag nightly` returned `E404`, while the
branch-push workflow successfully published
`@oneciel-ai/claude-any@0.1.100-nightly.20260523-2252` from commit
`1ce64abcf6e96f1313a9bb6641d37a52d7bae368`. Treat GitHub Actions as the
source of truth for npm publishing.

## Known local workspace notes

The following local untracked directories have appeared during npm registry verification and should not be treated as source changes:

```text
.npm-view-cache-1/
.npm-view-cache-2/
.npm-view-cache-3/
.npm-view-cache-4/
.npm-view-cache-5/
.npm-view-cache-6/
.npm-view-cache-7/
.npm-view-cache-8/
```

Leave them alone unless doing deliberate workspace cleanup.

## Next recommended checks

1. Test native channel delivery with `ai-net` enabled and verify a real DM appears through MCP, not stdin injection.
2. Test stdin fallback explicitly with `claude-any channel-delivery stdin`.
3. Capture logs for one successful native notification and one successful stdin fallback notification.
4. If native `/mcp` still reports `claude-any-router failed`, inspect the MCP initialize/request response pair around `/ca/mcp/sse` and `/ca/mcp/messages`.
5. If stdin still parks text in the input area, test explicit `CLAUDE_ANY_CHANNEL_WAKE_ENTER=crlf` and compare logs with observed `channel_stdin_proxy_enter_observed`.
6. Test `claude-any --ca-provider claude-native` from a shell with a stale router process running and confirm launch aborts or logs `router_kill_guarantee ... state=killed`.
7. Test a spec-correct stdio MCP server that only speaks NDJSON and confirm default channel probing detects `claude/channel`.
