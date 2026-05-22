# Building an MCP Server That Works as a Claude Code Channel

This is a development guide for **MCP server authors** who want their
server to be discovered by [claude-any](https://www.npmjs.com/package/@oneciel-ai/claude-any)
and surfaced under `--dangerously-load-development-channels` so Claude
Code can route channel notifications through it.

Audience: someone who already runs an MCP server over stdio and wants
Claude Code to treat it as a channel transport. If you have not built
an MCP server before, start at <https://modelcontextprotocol.io>.

claude-any probes your server with a real MCP `initialize` request, looks
at the response's `capabilities.experimental['claude/channel']`, and only
then offers it as a `server:NAME` channel in the pre-launch menu. If your
server is not picked up, follow this guide to make it conformant; in
return, claude-any will not need a per-server workaround.

## 1. Use the MCP-standard stdio framing

MCP defines stdio transport as **JSON-RPC 2.0 messages prefixed with an
LSP-style `Content-Length` header**, not bare newline-delimited JSON.
Every message a server emits and every message it consumes must look
like:

```
Content-Length: <byte length of JSON body>\r\n
\r\n
<JSON body>
```

Concretely the bytes on the wire for an `initialize` response look like:

```
Content-Length: 152\r\n
\r\n
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"experimental":{"claude/channel":{}}},"serverInfo":{"name":"my-server","version":"1.0.0"}}}
```

If you use the official `@modelcontextprotocol/sdk` `StdioServerTransport`
class you get this framing for free — do not replace the transport with
a hand-rolled `process.stdin.on('line', ...)` reader. Bare line-delimited
JSON ("JSONL") is **not** the MCP stdio wire format and will cause
clients (including Claude Code and the claude-any probe) to silently
ignore your responses.

How to tell whether you are speaking framed stdio:

1. Send any message and capture the raw bytes you put on stdout.
2. The first bytes must be the ASCII letters `Content-Length:`.
3. The body that follows the `\r\n\r\n` separator must be exactly the
   number of bytes given in the header (no trailing newline).

If you see your server emitting a line like
`{"method":"notifications/message","params":{...}}\n` with no
`Content-Length:` prefix, you are in JSONL mode and need to switch.

## 2. Declare the channel capability in the initialize response

A channel-capable server announces itself during the standard MCP
handshake by including `claude/channel` under `capabilities.experimental`.
A minimal response looks like:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "experimental": {
        "claude/channel": {}
      }
    },
    "serverInfo": {
      "name": "my-server",
      "version": "1.0.0"
    }
  }
}
```

Notes:

- The value can be `{}` today. Future revisions may add fields; an empty
  object is forward-compatible.
- Omitting `experimental` entirely, or including `experimental` without
  `claude/channel`, marks your server as not channel-capable. claude-any
  will list it under "Detected but not channel-capable" in the menu.
- The probe expects `protocolVersion: "2024-11-05"`. If your server only
  speaks a newer protocol, the probe accepts whatever the server returns
  as long as `result` is present and the capability is declared.

## 3. Emit channel notifications using the `notifications/claude/channel` method

When you have a message to deliver into Claude Code, send a JSON-RPC
**notification** (no `id` field) on stdout with the framed encoding:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/claude/channel",
  "params": {
    "content": "[room_id] sender: text body",
    "meta": {
      "channel": "room_id",
      "sender_id": "sender",
      "thread_id": "optional",
      "message_id": "optional"
    }
  }
}
```

`params.content` is what Claude Code will read; `params.meta` is the
structured form that claude-any preserves. Both come through to the
Claude Code session over `/ca/mcp/sse`.

Do **not** use the generic `notifications/message` method for channel
delivery — that is a different transport-level log channel. claude-any
will accept `notifications/message` as a fallback for compatibility but
real channel notifications should be `notifications/claude/channel`.

## 4. How claude-any probes your server

Useful to know so you can reproduce exactly what claude-any does:

1. Spawn your server with the command/args/env you declared in the user's
   MCP config (e.g. `~/.mcp.json`, `~/.claude/settings.json`, or
   `~/.claude.json`).
2. Write a single framed `initialize` request to stdin.
3. Wait up to **15 seconds** (configurable via the user's
   `CLAUDE_ANY_CHANNEL_PROBE_TIMEOUT_SECONDS` env var) for a framed
   response with the same id.
4. Inspect `result.capabilities.experimental['claude/channel']`. Anything
   that is not `null` and not `false` counts as capable.
5. Close stdin and terminate the child.

The probe captures up to 4KB of your stderr; anything you log there will
end up in the user's `~/.config/claude-any/router.log` under a
`channel_probe_stderr server=<name>` line, which makes it the right
place to print fatal startup errors but the wrong place to dump a
verbose info-level log.

## 5. Diagnosing common failure reasons

When claude-any reports your server as not channel-capable, look at the
`reason` field on the relevant menu row, or run:

```sh
claude-any channels detect
```

| reason | meaning | typical fix |
| --- | --- | --- |
| `capable` | All good. | — |
| `no_experimental_claude_channel` | Server responded with a valid framed initialize result but `capabilities.experimental['claude/channel']` was missing. | Add the capability to your initialize result. See section 2. |
| `timeout` | Process is still running but never produced a framed initialize response within the timeout. | Either your startup is genuinely longer than the timeout (rare — users can raise `CLAUDE_ANY_CHANNEL_PROBE_TIMEOUT_SECONDS`), or your transport is JSONL instead of framed. See section 1. |
| `exited_without_response` | Process died before responding. | Look at the `stderr` preview claude-any logged. Usually a missing env var, missing dependency, or runtime error during init. |
| `spawn_failed:<exception>` | The OS could not even start your command. | Wrong `command` path, missing executable, missing permissions. |
| `not_stdio` / `no_command` | The MCP server entry has no `command`, or the user declared it as a non-stdio transport (e.g. `type: "sse"`). | Probing non-stdio servers is not implemented; users can still wire those manually. |

If you cannot reproduce locally, ask the user to share two log lines:

```sh
grep "channel_probe_result server=<your-name>" ~/.config/claude-any/router.log | tail -1
grep "channel_probe_stderr server=<your-name>" ~/.config/claude-any/router.log | tail -1
```

The first line tells you which reason fired and how many bytes of stdout
were read; the second includes up to 500 characters of your stderr.

## 6. Minimal example (TypeScript, `@modelcontextprotocol/sdk`)

```ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server(
  { name: "my-channel-server", version: "1.0.0" },
  {
    capabilities: {
      // The presence of experimental.claude/channel is what claude-any
      // looks for during the channel probe.
      experimental: { "claude/channel": {} },
    },
  }
);

// Wherever your server learns about an inbound message it wants to
// surface inside the Claude Code session:
async function notifyChannel(content: string, meta: Record<string, unknown> = {}) {
  await server.notification({
    method: "notifications/claude/channel",
    params: { content, meta },
  });
}

// StdioServerTransport produces the required Content-Length framing.
// Do not write to stdout yourself.
await server.connect(new StdioServerTransport());
```

If you ship a hand-rolled stdio server in another language, the
equivalent contract is: write `Content-Length: <N>\r\n\r\n<JSON>` to
stdout for every message, and read the same shape from stdin.

## 7. Local verification

Once you've adopted the changes above, the fastest end-to-end check is:

```sh
# Make sure your MCP server is registered in one of the standard places
# (project .mcp.json, ~/.mcp.json, or ~/.claude.json mcpServers section).

npm i -g @oneciel-ai/claude-any@nightly
claude-any channels detect
```

You should see your server name appear under `capable` with no stderr
preview attached and a non-zero `bytes` value. If you do, claude-any
will offer it under `[Auto-detected channel-capable]` in the pre-launch
menu and pass `--dangerously-load-development-channels server:<name>`
into Claude Code on launch.
