# claude-free POC

This folder is a local proof-of-concept for a billing/quota visibility hypothesis.

It does **not** call Anthropic, does **not** attempt to bypass billing, and does
not include any exploit path. The purpose is to show a proxy compatibility issue:

> If an Anthropic-compatible router forwards the SSE body but strips Anthropic
> response headers, Claude Code can still receive token `usage` events while
> losing client-visible quota/rate-limit/account-status signals.

## Hypothesis

Claude Code appears to consume billing/quota-related signals from two places:

1. SSE body events such as `message_start.usage` and `message_delta.usage`.
2. Response headers such as `anthropic-ratelimit-unified-*`, `retry-after`,
   and request IDs.

The current routed proxy path can preserve the SSE body while dropping the
headers. That would not prove server-side billing is bypassed. It only proves
that the client may fail to observe quota/rate-limit state in routed mode.

## Run

```powershell
python .\claude-free\run_poc.py
```

Expected result:

- `direct` receives the mock quota headers.
- `strip` receives the SSE usage body but does not receive quota headers.
- `forward` receives both the SSE usage body and the quota headers.

The script writes a JSON evidence file under:

```text
claude-free/evidence/latest-run.json
```

It also writes a human-readable status-line/header trace:

```text
claude-free/evidence/latest-run.log
```

The log records:

- mock upstream status line and emitted quota headers;
- strip proxy's upstream-observed headers and downstream-sent headers;
- forward proxy's upstream-observed headers and downstream-sent headers;
- client-observed status line, headers, and SSE usage-event count.

## Real claude-any Anthropic Routed POC

For report evidence, use the routed POC. It starts:

1. a local Anthropic-compatible mock upstream;
2. a real `claude-any` router in isolated `anthropic routed` mode;
3. a direct router probe;
4. optionally, the real `claude` CLI pointed at that isolated router.

Router-only proof:

```powershell
python .\claude-free\run_claude_any_routed_poc.py
```

Full proof including a real Claude Code invocation:

```powershell
python .\claude-free\run_claude_any_routed_poc.py --execute-claude
```

This still does not call Anthropic. The real Claude Code process talks to the
local `claude-any` router, and the router talks to the local mock upstream. The
mock upstream emits Anthropic-like `usage` SSE events and
`anthropic-ratelimit-unified-*` headers.

Each run writes a dedicated evidence directory:

```text
claude-free/evidence/anthropic-routed-YYYYMMDD-HHMMSS/
```

Important files:

- `timeline.log` - human-readable status-line and header timeline.
- `evidence.json` - machine-readable assertions.
- `claude.stdout.txt` - real Claude Code output when `--execute-claude` is used.
- `claude-debug.log` - Claude Code debug log when `--execute-claude` is used.
- `router.log` - real claude-any router log copied from the isolated config.
- `claude-any-config/requests.jsonl` - routed request dump if present.

The expected evidence shape is:

- mock upstream emits `request-id`, `x-request-id`, `retry-after`, and
  `anthropic-ratelimit-unified-*`;
- actual `claude-any anthropic routed` response observed by the probe keeps SSE
  usage events;
- that same downstream response lacks the Anthropic quota/rate-limit/request-id
  headers;
- real `claude -p` can be run against this isolated local routed setup and
  returns `POC_OK`.

## Windows Interactive Usage Probe

For billing/usage evidence, an interactive Claude Code session is stronger than
`claude -p` because it lets you capture `/usage` before, during, and after the
load.

Prepare a Windows evidence folder and generated prompts:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\claude-free\prepare_windows_interactive_usage_probe.ps1 `
  -Model claude-sonnet-4-5 `
  -TargetTotalTokens 1000000 `
  -TokensPerCall 50000
```

The preparation step does not call Anthropic. It writes a new evidence directory
under:

```text
claude-free/evidence/real-load-YYYYMMDD-HHMMSS/
```

Open `WINDOWS_INTERACTIVE_STEPS.md` in that directory. The generated helpers are:

- `launch-claude-any-routed.ps1` - launches interactive Claude Code through
  `claude-any` Anthropic routed mode with an isolated evidence config directory.
- `copy-prompt.ps1` - copies `call-NNN.txt` to the Windows clipboard for manual
  paste into Claude Code.
- `submit-prompt-continue.ps1` - submits `call-NNN.txt` through `claude -c -p`
  without clipboard paste, while using the same routed claude-any evidence
  config and saving stdout/stderr/debug evidence.
- `resume-routed-claude.ps1` - reopens the latest Claude Code conversation
  through the same routed evidence environment so `/usage` can be captured after
  a file-submitted prompt.
- `collect-logs.ps1` - copies claude-any router logs and request/response traces
  into the evidence folder.
- `usage-checkpoints.md` - table for `/usage` screenshots before and after each
  load prompt.

Recommended proof flow:

1. Run `launch-claude-any-routed.ps1`.
2. In Claude Code, run `/usage` and capture `usage-before.png`.
3. In another PowerShell window, run `copy-prompt.ps1 -Index 1`.
4. Paste into Claude Code, wait for completion, run `/usage`, and capture
   `usage-after-call-001.png`.
5. Repeat until the usage delta is clear.
6. Run `collect-logs.ps1`.

If a prompt is too large for reliable terminal paste, keep the routed router
running and use:

```powershell
.\submit-prompt-continue.ps1 -Index 1
```

Then return to Claude Code and run `/usage` for the visible quota screenshot.
If the original interactive window is not attached to the latest conversation,
run `.\resume-routed-claude.ps1` and capture `/usage` there.

The prompt set can target about 1M estimated input tokens, so stop early if the
usage/billing evidence is already conclusive.

## Evidence Value

This POC is useful for a responsible report because it avoids real credentials
and isolates the behavior:

- upstream emitted quota headers;
- proxy mode `strip` removed them;
- the client still saw normal-looking SSE usage events;
- proxy mode `forward` restored the missing client-visible signals.

## What This Does Not Prove

This POC does not prove that Anthropic server-side billing is skipped. Server-side
billing should be determined by Anthropic when `/v1/messages` is processed. To
prove or disprove server-side billing, Anthropic-side request/accounting logs or
official OAuth usage API results are required.
