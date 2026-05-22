# claude-any handoff

Date: 2026-05-22
Stable release: `@oneciel-ai/claude-any@0.1.99`
Nightly release: `@oneciel-ai/claude-any@0.1.99-nightly.20260522-1706`
Current branch: `nightly`
Current pushed commit: `0853688` (`Probe SSE MCP servers for the channel capability too`)

## Current state

`claude-any` is a Claude Code provider/router wrapper with MCP proxy support, channel message delivery, provider selection, and npm-based distribution.

The latest production path is:

- Default channel delivery is `native`.
- `stdin` delivery remains available as a fallback/manual option.
- Native channel delivery exposes the router MCP bridge at `/ca/mcp/sse` and `/ca/mcp/messages`.
- MCP notification events are persisted into `chat-messages.jsonl`.
- Native clients receive channel messages through `notifications/claude/channel` with metadata preserved as much as the MCP schema allows.
- `stdin` fallback injects a compact wake prompt into Claude Code when channel messages arrive.

The published stable npm version `0.1.99` includes the automatic MCP channel capability probing work through timeout/error classification. The current `nightly` branch adds the MCP channel server guide cleanup and SSE MCP server probing refinements.

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

### Nightly after 0.1.99

The `nightly` branch currently contains additional unreleased/staged work:

- Split npm publishing into stable `latest` and pre-release `nightly` channels.
- Added and then simplified an MCP channel-capable server author guide.
- Reframed the guide to point at Anthropic's MCP spec rather than maintaining a duplicated local protocol reference.
- Extended channel probing so SSE MCP servers are probed for channel capability too.

## Channel delivery modes

### Native

Native is the preferred delivery mode.

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

Stdin is a fallback.

Use this when native MCP delivery is unavailable or when explicitly testing prompt injection behavior.

Stdin channel flow:

1. External MCP server sends a notification.
2. Router stores a normalized message in `chat-messages.jsonl`.
3. Router watches the chat message file.
4. Router writes `Ctrl-U`, the compact wake prompt, and submit bytes to Claude Code's PTY.
5. Submit bytes are selected by explicit env override, platform default, or observed user input.

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
grep -n "mcp_proxy_notification\|channel_mcp_\|channel_stdin_proxy\|web_fetch_disabled" ~/.config/claude-any/router.log | tail -120
```

Check configured MCP proxy server files:

```bash
find ~/.config/claude-any/mcp-proxy-servers -maxdepth 1 -type f -print -exec sed -n '1,120p' {} \;
```

Force channel delivery mode:

```bash
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

- Router is still listening on `127.0.0.1:8799`.
- `/ca/mcp/sse` returns `200`.
- `/ca/mcp/messages?session=...` returns `200`.
- Router log has `channel_mcp_session_started` followed by `channel_mcp_initialized`.

Repeated 30 second `ConnectionResetError` closes can be normal client reconnect behavior, but a persistent `failed` state in `/mcp` means the client did not complete MCP initialization.

## Release process

Current release path uses GitHub Actions and two npm dist-tags.

Local npm auth may not work. Prefer:

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

## Known local workspace notes

The following local untracked directories have appeared during npm registry verification and should not be treated as source changes:

```text
.npm-view-cache-1/
.npm-view-cache-2/
.npm-view-cache-3/
```

Leave them alone unless doing deliberate workspace cleanup.

## Next recommended checks

1. Test native channel delivery with `ai-net` enabled and verify a real DM appears through MCP, not stdin injection.
2. Test stdin fallback explicitly with `claude-any channel-delivery stdin`.
3. Capture logs for one successful native notification and one successful stdin fallback notification.
4. If native `/mcp` still reports `claude-any-router failed`, inspect the MCP initialize/request response pair around `/ca/mcp/sse` and `/ca/mcp/messages`.
5. If stdin still parks text in the input area, test explicit `CLAUDE_ANY_CHANNEL_WAKE_ENTER=crlf` and compare logs with observed `channel_stdin_proxy_enter_observed`.
