# No `-p` Channel Handling Research

Date: 2026-05-25
Branch: `codex/nightly-no-p-channel-research`

## Context

`0.1.100` made AI-Net/SSE channel notifications actionable by letting claude-any
spawn a hidden Claude Code print-mode process:

```text
claude --dangerously-skip-permissions --model ... --mcp-config ... -p "[claude-any channel inbox] ..."
```

That path can call MCP tools and reply to agents, but it is the wrong surface for
automatic notification handling:

- It is a separate Claude Code process from the visible interactive session.
- Its stdout is captured by claude-any, not by the current Claude Code UI.
- A background `-p` invocation can be billed or governed separately from the
  user's interactive session.

User-invoked `claude-any ... -p` pass-through should remain supported. The
restriction is only on claude-any launching hidden `-p` work for channel events.

## Previous claude-any path

The old automatic direct-channel path lived in `claude_any.py`:

- `_channel_direct_llm_http_response()` can call `/v1/messages`, but it does not
  run a complete tool-use loop by itself.
- `_channel_direct_terminal_notice()` writes a best-effort notice to the
  terminal, but this is diagnostic output, not a reliable transcript surface.
- `body_with_pending_channel_messages()` injects pending channel messages into
  normal routed requests, which is useful but is not enough for immediate
  autonomous handling.

The observed failure is therefore expected: Sarah's DM can be processed and a
reply can be sent, while the active Robert UI never receives a clean summary of
what happened.

## Claude Code Source Observations

The local Claude Code source snapshot under `.tmp-claude-code-cli-leaked/src`
shows three relevant patterns.

### `/advisor`

Files:

- `commands/advisor.ts`
- `components/messages/AdvisorMessage.tsx`
- `query.ts`

`/advisor` is not a separate headless subprocess. It mutates the current
application state (`advisorModel`) and renders advisor result blocks inside the
current message transcript. This confirms the desired UX shape: model side
activity must be represented as blocks/messages in the active session, not as
captured output from another CLI process.

`/advisor` itself is not a direct integration point for claude-any channel
delivery.

### Bridge inbound messages

Files:

- `bridge/inboundMessages.ts`
- `bridge/bridgeMessaging.ts`
- `hooks/useReplBridge.tsx`
- `utils/messageQueueManager.ts`
- `utils/handlePromptSubmit.ts`
- `utils/processUserInput/processUserInput.ts`
- `screens/REPL.tsx`

Claude Code's bridge path accepts inbound `SDKMessage` objects whose type is
`user`, extracts `content` and `uuid`, deduplicates echos/replays, and then
queues the message into the active REPL:

```text
incoming user SDKMessage
  -> handleIngressMessage(...)
  -> useReplBridge.handleInboundMessage(...)
  -> enqueue({ value, mode: "prompt", uuid, skipSlashCommands: true, bridgeOrigin: true })
  -> handlePromptSubmit(...)
  -> processUserInput(...)
  -> onQuery(...)
```

Two details matter:

- The message is queued into the existing session, so rendering and tool-result
  follow-up happen in the active UI.
- Slash command handling is constrained for bridge-origin input, which is a
  reasonable prompt-injection defense.

This is the clean architecture, but it appears tied to Claude Code's internal
bridge/remote-control stack rather than a stable public local API that
claude-any can call from outside the process.

### Team agent messaging

Files:

- `tools/TeamCreateTool/TeamCreateTool.ts`
- `tools/SendMessageTool/SendMessageTool.ts`
- `utils/teammateMailbox.ts`
- `hooks/useInboxPoller.ts`
- `screens/REPL.tsx`
- `utils/attachments.ts`
- `cli/print.ts`
- `tasks/InProcessTeammateTask/InProcessTeammateTask.tsx`
- `utils/teammateContext.ts`

Team agents communicate through per-agent mailbox files:

```text
~/.claude/teams/{team_name}/inboxes/{agent_name}.json
```

`SendMessageTool` writes mailbox entries. In interactive mode,
`useInboxPoller()` polls the mailbox, formats unread messages as
`<teammate-message ...>`, and submits them to the active REPL only when it is
safe to do so. If the session is busy or a dialog is open, messages are queued in
app state and delivered later. Messages are marked read only after they are
delivered or durably queued.

`cli/print.ts` contains a separate headless loop for `-p` mode. That contrast is
important: interactive Claude Code and print mode do not share the same UI
delivery mechanics. Copying print-mode behavior into claude-any is exactly what
creates the invisible-summary problem.

## Implications For claude-any

For routed non-native providers, claude-any should not require Claude Code's
experimental `--channels`/development-channel path. The incoming AI-Net/SSE
events already arrive at claude-any; the routed provider path should handle them
through claude-any's own LLM/tool loop and then make the result visible to the
interactive session.

The product surface should be:

1. Receive and persist the channel notification.
2. Let a routed LLM turn decide what to do.
3. Execute approved MCP/tool calls and feed `tool_result` blocks back to that
   same LLM turn.
4. Persist the final summary/action log.
5. Inject that summary into the next visible interactive request, or deliver it
   through a future stable active-REPL queue if Claude Code exposes one.

Terminal notices can stay as diagnostics, but they must not be the only way the
user learns what happened.

## Recommended Next Implementation

This branch implements the no-hidden-`-p` direction:

1. Hidden `claude -p` is removed from automatic channel notification handling.
   Explicit user pass-through remains untouched.

2. Automatic handling now uses a router-owned direct handler:

   ```text
   channel notification
     -> build channel prompt
     -> call selected provider through claude-any's router adapter
     -> if tool_use: execute MCP/tool call
     -> append tool_result to the same provider conversation
     -> repeat until end_turn
     -> persist final summary
   ```

3. Direct channel handling has a minimal MCP tool-result loop. It discovers
   tools from the initialized source SSE MCP server, exposes them to the LLM as
   Anthropic tools, executes selected tools with MCP `tools/call`, and sends
   `tool_result` blocks back to the same LLM conversation before asking for the
   final response.

4. MCP JSON-RPC responses arriving on the SSE stream are stored as RPC results
   and are not appended as chat/channel notifications. This prevents `tools/list`
   and `tools/call` responses from being mistaken for Sarah/Robert messages.

5. Durable visibility state is stored in:

   ```text
   ~/.config/claude-any/channel-llm-summary-queue.jsonl
   ~/.config/claude-any/channel-llm-summary-cursor.json
   ```

   Each entry should include channel, message id, source agent, prompt summary,
   tool calls, tool results, final response text, and whether it has been shown
   in the interactive session.

6. Normal routed requests now call `body_with_pending_channel_summaries()` after
   pending channel-message injection, so completed direct-handling summaries that
   have not yet been shown are injected into the visible session.
   This lets the active Claude Code session print a visible summary on the next
   user/model turn even though the autonomous work happened in claude-any.

7. Explicit logs make failures diagnosable:

   - `channel_llm_direct_router_request`
   - `channel_sse_mcp_rpc_response`
   - `channel_llm_tool_call`
   - `channel_llm_tool_result_forwarded`
   - `channel_llm_summary_queued`
   - `channel_llm_summary_injected`
   - `channel_llm_direct_response`

8. Tests prove automatic channel notifications use the router-owned path, round
   trip MCP `tool_result` blocks to the same LLM turn, store SSE JSON-RPC
   responses without chat append, and inject durable summaries into the next
   routed request.

## Follow-up Surface: Router Web Chat

The no-hidden-`-p` direction also benefits from a first-party browser surface.
The router now serves `/ca/web/chat`, which posts a standalone text-only browser
conversation to the same `/v1/messages` route as Claude Code. This gives
operators a local provider test chat without relying on Claude Code's
experimental `--channels` flags, but it is not an attachment to an existing
Claude Code terminal transcript or tool executor. Claude Code tools, MCP tools,
shell, and filesystem access are unavailable in this UI. External exposure
remains user-managed; Claude Any documents Cloudflare MCP as an optional setup aid but does not create
tunnels, Tailscale routes, DNS records, or public hostnames.

Anthropic remains direct Claude Native by default. When an operator needs the
router-owned web chat, channel handling, or observability for Anthropic itself,
the Anthropic `route_through_router` option can be enabled with an Anthropic API
key.

## Open Question

The only way to get immediate, first-class UI display without waiting for the
next routed request is to enqueue into the active Claude Code REPL, like
`useReplBridge()` and `useInboxPoller()` do. The inspected source shows the
right internal mechanics, but not a stable public local API for doing this from
an external wrapper. Until such an API exists, durable summary injection into
the next routed request is the safer product path.
