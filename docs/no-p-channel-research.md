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

## Current claude-any path

The automatic direct-channel path currently lives in `claude_any.py`:

- `_channel_direct_llm_cli_response()` shells out to Claude Code and appends
  `-p` to the command.
- `_channel_direct_llm_http_response()` can call `/v1/messages`, but it does not
  yet run a complete tool-use loop.
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

1. Disable hidden `claude -p` for automatic channel notifications.
   Keep explicit user pass-through untouched.

2. Replace `_channel_direct_llm_cli_response()` in the automatic path with a
   router-owned direct handler:

   ```text
   channel notification
     -> build channel prompt
     -> call selected provider through claude-any's router adapter
     -> if tool_use: execute MCP/tool call
     -> append tool_result to the same provider conversation
     -> repeat until end_turn
     -> persist final summary
   ```

3. Add a minimal MCP tool-result loop for direct channel handling. At minimum,
   it must support the AI-Net tools needed for DM workflows:

   - `get_messages`
   - `send_dm`
   - `send_message`
   - `ack_notifications`
   - `wait_for_notifications` only when explicitly bounded

4. Add durable visibility state, for example:

   ```text
   ~/.config/claude-any/channel-results.jsonl
   ~/.config/claude-any/channel-visible-queue.jsonl
   ```

   Each entry should include channel, message id, source agent, prompt summary,
   tool calls, tool results, final response text, and whether it has been shown
   in the interactive session.

5. Extend `body_with_pending_channel_messages()` so normal routed requests also
   include completed direct-handling summaries that have not yet been shown.
   This lets the active Claude Code session print a visible summary on the next
   user/model turn even though the autonomous work happened in claude-any.

6. Add explicit logs so failures are diagnosable:

   - `channel_llm_direct_router_request`
   - `channel_llm_tool_call`
   - `channel_llm_tool_result_forwarded`
   - `channel_llm_direct_router_response`
   - `channel_llm_summary_queued`
   - `channel_llm_summary_injected`

7. Add tests that prove automatic channel notifications do not spawn `claude -p`.
   The test should patch subprocess execution and fail if the internal automatic
   path appends `-p`.

## Open Question

The only way to get immediate, first-class UI display without waiting for the
next routed request is to enqueue into the active Claude Code REPL, like
`useReplBridge()` and `useInboxPoller()` do. The inspected source shows the
right internal mechanics, but not a stable public local API for doing this from
an external wrapper. Until such an API exists, durable summary injection into
the next routed request is the safer product path.
