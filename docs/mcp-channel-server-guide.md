# Making Your MCP Server Discoverable as a Claude Code Channel

If you want your MCP server to be picked up as a **Claude Code channel**
— so Claude Code can route inbound messages and external events into a
running session through your server — there is only one thing to do:

> **Follow the official Anthropic Claude Code Channels spec.**

Authoritative references:

- Channels reference (the contract — capability key, notification
  method, example server, transport):
  <https://code.claude.com/docs/en/channels-reference>
- MCP overview (server lifecycle inside Claude Code):
  <https://code.claude.com/docs/en/mcp>
- MCP protocol (stdio wire format — Content-Length framing):
  <https://modelcontextprotocol.io>
- Official channel implementations (Telegram, Discord, iMessage,
  fakechat) to copy from:
  <https://github.com/anthropics/claude-plugins-official/tree/main/external_plugins>

claude-any imposes **no extra requirements** on top of that contract.
If Claude Code accepts your server as a channel, claude-any will too;
if it doesn't, claude-any can't either. Anything below this line is
optional debugging info from the claude-any side — it is not a spec.

## Verify against Claude Code directly

The canonical end-to-end check, with no claude-any in the picture:

```sh
# Register your server in ~/.claude.json or a project .mcp.json,
# then start Claude Code with it loaded as a development channel.
claude --dangerously-load-development-channels server:<your-name>

# Inside the session
/mcp
```

If `/mcp` shows your server as connected and channel notifications you
emit show up as `<channel source="<your-name>" ...>` blocks in the
session, you are done.

If Claude Code reports `--dangerously-load-development-channels ignored
(server:<your-name>)` or `/mcp` shows your server as failed, the
problem is between your server and Claude Code, not between your server
and claude-any. The session debug log Claude Code points you at —
`~/.claude/debug/<session-id>.txt` — contains the stderr trace that
explains it. Fix it there first.

## Optional: claude-any-side diagnostics

These notes are only useful if a user is running your server through
claude-any and asks for help interpreting claude-any's pre-launch menu.
None of these are requirements your server has to satisfy.

When claude-any does its own MCP `initialize` round-trip to decide
which configured stdio servers should be listed under "Auto-detected
channel-capable", it can mark your server with one of these reasons.
Each one maps to a real underlying bug, not to a claude-any quirk:

| claude-any reason | what it usually means about your server | where to look |
| --- | --- | --- |
| `capable` | All good. | — |
| `no_experimental_claude_channel` | Your server replied to `initialize` with a valid MCP response, but `result.capabilities.experimental['claude/channel']` was absent. | The Anthropic Channels reference (Server options) explains the exact key. |
| `timeout` | Either your startup is genuinely long, or your stdio transport is bare newline-delimited JSON instead of MCP's required Content-Length framing — in which case Claude Code itself won't talk to you either. | Confirm you're using the official SDK's `StdioServerTransport` (or another implementation that produces Content-Length headers per the MCP stdio transport spec). |
| `exited_without_response` | Your server died before responding to `initialize`. | Run your server manually with `echo` piping a Content-Length-framed initialize message, or just check the stderr that claude-any captures and logs. |
| `spawn_failed:<exc>` | The OS could not start your command at all. | Wrong path, missing executable, missing permissions. |

The set of failure modes above mirrors what plain Claude Code would
also experience; claude-any just surfaces it earlier in a menu instead
of waiting for you to hit `/mcp` in a live session.

## A note about JSON-RPC notification methods

Claude Code listens for `notifications/claude/channel` specifically — a
spec-defined method name. Generic `notifications/message` (sometimes
used informally for "log this somewhere") is **not** the channel
notification method. If your server emits `notifications/message` for
inbound chat events, Claude Code will not route them into the session
as channel content. The Channels reference (Notification format) has
the exact shape.

That's it. If you got this far the answer to "what does claude-any
require of my server?" is: nothing on top of the Anthropic-defined
spec.
