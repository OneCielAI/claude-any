# Claude Any Manual

<p align="center">
  <img src="../logo-small.png" alt="Claude Any logo" width="220">
</p>

Claude Any is a pre-launch configuration layer for Claude Code. It lets you
choose a provider, model, base URL, API key, and provider options before Claude
Code starts, while passing normal Claude Code arguments through unchanged.

Credits: One Ciel LLC

Current version: `0.1.34`

## Install

Requirements:

- Python 3.10+
- Claude Code installed as `claude`
- Node/npm (used for the install shim and optional MCP web tooling)

**Install from the npm registry (recommended):**

```sh
npm install -g @oneciel-ai/claude-any
claude-any
```

**Upgrade:**

```sh
npm update -g @oneciel-ai/claude-any
claude-any version
```

**Uninstall:**

```sh
npm uninstall -g @oneciel-ai/claude-any
```

### Alternative install paths

Install directly from the GitHub repository:

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

POSIX source install:

```sh
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
./install.sh
claude-any
```

Windows PowerShell source install:

```powershell
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
.\install.ps1
claude-any
```

### Releasing (maintainers)

The `Publish to npm` workflow publishes to the registry whenever a new GitHub
Release is published. It reads the `NPM_TOKEN` repository secret, which must
hold a granular npm access token for `@oneciel-ai/claude-any` with
*Bypass 2FA for publishing* enabled.

Release flow:

1. Bump `version` in `package.json` and `VERSION` in `claude_any.py`.
2. Add a Changelog entry.
3. `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
4. `gh release create vX.Y.Z --title "..." --notes "..."` — triggers the workflow.


macOS has not been fully tested by the maintainer yet. The project uses
portable Python and shell wrappers, so it is expected to work; please report
issues if you find them.

## Interactive Menu

Run:

```sh
claude-any
```

The menu appears before Claude Code starts. Use arrow keys to move and Enter to
edit or select:

- Language: English, Korean, Japanese, Chinese.
- Provider: Anthropic, Ollama, Ollama Cloud, vLLM, NVIDIA hosted, self-hosted NIM.
- API key: enter only when the selected provider needs one.
- Base URL: provider-aware default or custom endpoint.
- Model: provider model picker when available, custom input otherwise.
- Options: provider-specific generation, timeout, and preset settings.
- Compatibility test: checks a plain text response, a required `tool_use`, and
  a `tool_result` follow-up before launching Claude Code.
- Launch Claude Code: starts Claude Code with the selected configuration.

The lower status area shows connection checks, API-key state, provider notes,
and compatibility-test results.
For vLLM and self-hosted NIM, the compatibility test also reads `/v1/models`
when available and prints the runtime `max_model_len` next to Claude Any's
configured `context_window` and `max_output_tokens`.
If the runtime model reports one context size but Claude Any is configured for
another, the test output shows both values so you can fix either the server
startup flags or the client preset.

### LLM Option Presets

Open `LLM options`, then select `Apply preset` to apply a provider-aware preset
without editing every parameter manually. Claude Any currently includes:

- Balanced Claude Code: stable 4K-output default for normal Claude Code use.
- Coding deterministic: lower randomness for edits, scripts, and code review.
- Fast short tasks: shorter output and timeout for quick background jobs.
- Long context 65K: 65K context target with a 4K output reserve.
- Large output/report: 8K output for summaries and reports.
- Reasoning model: longer timeout and reasoning-friendly sampling.

The recommended preset is chosen from the current provider and model name. For
example, `coder` models prefer the coding preset, `r1`/`thinking` models prefer
the reasoning preset, and vLLM/NIM models configured for 65K context prefer the
long-context preset. For vLLM native mode, the server must still be launched
with a matching `--max-model-len`; Claude Any cannot raise the server-side
context limit from the client.

## Provider Setup

### Anthropic

Anthropic uses native Claude Code behavior. You can either log in through
Claude Code or use an Anthropic API key.

- Claude Code docs: https://docs.anthropic.com/en/docs/claude-code
- Claude Console API keys: https://console.anthropic.com/settings/keys

### Ollama

Local Ollama normally does not need an API key. Use a local base URL such as:

```text
http://127.0.0.1:11434
```

Ollama also provides Anthropic Messages API compatibility for tools such as
Claude Code. If you use `:cloud` models through a local Ollama host, sign in on
that Ollama host:

```sh
ollama signin
```

Links:

- Ollama Anthropic compatibility: https://docs.ollama.com/api/anthropic-compatibility
- Ollama authentication: https://docs.ollama.com/api/authentication

### Ollama Cloud

Ollama Cloud is for direct calls to `https://ollama.com/api`. It requires an
Ollama API key. Cloud model names must end in `:cloud`.

Links:

- Ollama Cloud: https://ollama.com/cloud
- Ollama API keys: https://ollama.com/settings/keys
- Ollama sign in: https://ollama.com/signin

### vLLM

Use a vLLM server that exposes the Anthropic Messages API used by Claude Code.
The base URL should be the server root, for example:

```text
http://127.0.0.1:8000
```

Claude Any and Claude Code will call `/v1/messages` under that base URL. Use an
API key only if your vLLM server is configured to require one.

For Claude Code, vLLM tool calling must be started with a parser that matches
the model family. A server can answer text requests and still fail Claude Code
if `--tool-call-parser` is wrong. For Qwen3-Coder, use `qwen3_xml`:

```sh
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3-coder-30b \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

Hermes-style models and some older Qwen tool templates may use `hermes`
instead, but do not assume `hermes` is correct for every Qwen model. Run
`claude-any test` after changing the parser; the test now checks text,
`tool_use`, and `tool_result`.

Links:

- vLLM Claude Code integration: https://docs.vllm.ai/en/latest/serving/integrations/claude_code/
- vLLM tool calling: https://docs.vllm.ai/en/stable/features/tool_calling/
- vLLM GitHub: https://github.com/vllm-project/vllm

### NVIDIA Hosted NIM

NVIDIA hosted models are available through NVIDIA API Catalog. Claude Any uses a
compatibility route for hosted models and requires an NVIDIA API key.

Links:

- NVIDIA API Catalog: https://build.nvidia.com/
- API Catalog quickstart: https://docs.api.nvidia.com/nim/docs/api-quickstart

### Self-Hosted NVIDIA NIM

Self-hosted NIM for LLMs can expose an Anthropic-compatible `/v1/messages`
endpoint. Use the NIM host base URL, not the OpenAI chat-completions URL.

Links:

- Claude Code with NIM: https://docs.nvidia.com/nim/large-language-models/latest/ai-assistant-integrations/claude-code.html
- NIM for LLMs getting started: https://docs.nvidia.com/nim/large-language-models/1.14.0/getting-started.html
- NGC personal keys: https://org.ngc.nvidia.com/setup/personal-keys

## Headless Usage

Claude Any options use the `--ca-*` prefix so they do not collide with Claude
Code flags. All other arguments pass through to Claude Code.

Headless mode is for launching Claude Code directly without opening the
pre-launch menu. It is useful for SSH sessions, scripts, scheduled jobs,
CI-like automation, and remote servers. Any `--ca-*` option updates Claude
Any's saved configuration first, skips the menu, starts the required
router services, then immediately executes Claude Code with the remaining
arguments.

Basic pattern:

```sh
claude-any --ca-provider PROVIDER --ca-model MODEL [claude-code args...]
```

Configuration precedence is deterministic:

1. Saved user choices from the interactive menu.
2. OS environment variables such as `CLAUDE_ANY_PROVIDER`.
3. Values loaded from `--ca-env-file .env.claude-any`.
4. CLI `--ca-*` parameters.
5. If `--ca-menu` is present, the final choice made in the interactive menu.

That lets automation provide defaults while still allowing a human operator to
make the final choice when needed.

Direct Claude Code launch examples:

```sh
# Open an interactive Claude Code session immediately with the saved model.
claude-any --ca-provider ollama-cloud --ca-model glm-5.1

# Run one non-interactive Claude Code prompt and print text output.
claude-any \
  --ca-provider ollama-cloud \
  --ca-model glm-5.1 \
  --ca-api-key-env OLLAMA_API_KEY \
  --ca-no-update-check \
  -p "Reply with OK only." \
  --output-format text

# Use the current saved Claude Any provider/model and pass args straight to Claude Code.
claude-any --ca-no-update-check -p "Summarize the current project." --output-format text
```

In these examples, `claude-any` is not just configuring settings. It starts
Claude Code in the same command. The `--ca-*` flags are consumed by Claude Any;
the prompt flags such as `-p` and `--output-format` are passed through to
Claude Code.

Provider setup examples:

```sh
# Local Ollama
claude-any \
  --ca-provider ollama \
  --ca-base-url http://127.0.0.1:11434 \
  --ca-model qwen3-coder \
  --ca-no-update-check \
  -p "Reply with OK only." --output-format text

# Ollama Cloud, reading the key from an environment variable
export OLLAMA_API_KEY="..."
claude-any \
  --ca-provider ollama-cloud \
  --ca-api-key-env OLLAMA_API_KEY \
  --ca-model glm-5.1 \
  -p "Summarize this repository." --output-format text

# vLLM Anthropic-compatible endpoint
claude-any \
  --ca-provider vllm \
  --ca-base-url http://127.0.0.1:8000 \
  --ca-model my-model \
  --ca-context-window 65536 \
  --ca-max-output-tokens 4096

# NVIDIA hosted API Catalog through the local Claude Any router
export NVIDIA_API_KEY="..."
claude-any \
  --ca-provider nvidia-hosted \
  --ca-api-key-env NVIDIA_API_KEY \
  --ca-model moonshotai/kimi-k2.6 \
  --ca-request-timeout-ms 300000

# Self-hosted NIM Anthropic-compatible endpoint
claude-any \
  --ca-provider self-hosted-nim \
  --ca-base-url http://127.0.0.1:8000 \
  --ca-model model \
  --ca-api-key not-used
```

Full headless configuration with flags:

```sh
claude-any \
  --ca-language en \
  --ca-provider nvidia-hosted \
  --ca-base-url https://integrate.api.nvidia.com/v1 \
  --ca-model z-ai/glm-4.7 \
  --ca-advisor-model deepseek-ai/deepseek-v4-pro \
  --ca-api-key-env NVIDIA_API_KEY \
  --ca-max-output-tokens 4096 \
  --ca-context-window 65536 \
  --ca-request-timeout-ms 300000 \
  --ca-rate-limit-rpm 40 \
  --ca-rate-limit-status on \
  --ca-stream on \
  --ca-stream-word-chunking off \
  --ca-web-search \
  --ca-web-fetch \
  --ca-enable-skills \
  --ca-no-update-check \
  -p "Reply with OK only." \
  --output-format text
```

Full headless configuration with environment variables:

```sh
export CLAUDE_ANY_SKIP_MENU=1
export CLAUDE_ANY_LANGUAGE=en
export CLAUDE_ANY_PROVIDER=nvidia-hosted
export CLAUDE_ANY_BASE_URL=https://integrate.api.nvidia.com/v1
export CLAUDE_ANY_MODEL=z-ai/glm-4.7
export CLAUDE_ANY_ADVISOR_MODEL=deepseek-ai/deepseek-v4-pro
export CLAUDE_ANY_API_KEY_ENV=NVIDIA_API_KEY
export CLAUDE_ANY_MAX_OUTPUT_TOKENS=4096
export CLAUDE_ANY_CONTEXT_WINDOW=65536
export CLAUDE_ANY_REQUEST_TIMEOUT_MS=300000
export CLAUDE_ANY_RATE_LIMIT_RPM=40
export CLAUDE_ANY_RATE_LIMIT_STATUS=on
export CLAUDE_ANY_STREAM=on
export CLAUDE_ANY_STREAM_WORD_CHUNKING=off
export CLAUDE_ANY_WEB_SEARCH=on
export CLAUDE_ANY_WEB_FETCH=on
export CLAUDE_ANY_DISABLE_SKILLS=off
export CLAUDE_ANY_UPDATE_CHECK=off
claude-any -p "Reply with OK only." --output-format text
```

The same values can be stored in a dotenv-style file and loaded explicitly:

```dotenv
CLAUDE_ANY_SKIP_MENU=1
CLAUDE_ANY_LANGUAGE=en
CLAUDE_ANY_PROVIDER=nvidia-hosted
CLAUDE_ANY_BASE_URL=https://integrate.api.nvidia.com/v1
CLAUDE_ANY_MODEL=z-ai/glm-4.7
CLAUDE_ANY_ADVISOR_MODEL=deepseek-ai/deepseek-v4-pro
CLAUDE_ANY_API_KEY_ENV=NVIDIA_API_KEY
CLAUDE_ANY_MAX_OUTPUT_TOKENS=4096
CLAUDE_ANY_CONTEXT_WINDOW=65536
CLAUDE_ANY_REQUEST_TIMEOUT_MS=300000
CLAUDE_ANY_RATE_LIMIT_RPM=40
CLAUDE_ANY_RATE_LIMIT_STATUS=on
CLAUDE_ANY_STREAM=on
CLAUDE_ANY_STREAM_WORD_CHUNKING=off
CLAUDE_ANY_WEB_SEARCH=on
CLAUDE_ANY_WEB_FETCH=on
CLAUDE_ANY_DISABLE_SKILLS=off
CLAUDE_ANY_UPDATE_CHECK=off
```

```sh
claude-any --ca-env-file .env.claude-any -p "Reply with OK only." --output-format text
```

To let `.env` or CLI values prefill the menu while the user makes the final
choice, add `--ca-menu`:

```sh
claude-any --ca-env-file .env.claude-any --ca-model z-ai/glm-4.7 --ca-menu
```

Passing Claude Code arguments:

```sh
# Everything not recognized as --ca-* is passed through to Claude Code.
claude-any --ca-provider ollama-cloud -p "Write a short status report." --output-format text

# Use -- when you want to visually separate Claude Any setup from Claude args.
claude-any --ca-provider ollama-cloud --ca-model glm-5.1 -- -p "Reply OK" --output-format text
```

Compatibility tests without the menu:

```sh
# Auto mode: fast default. NVIDIA hosted uses a text-only quick test.
claude-any test 60 auto

# Smoke mode: text response plus required tool_use.
claude-any test 120 smoke

# Full mode: text, tool_use, and tool_result round trip.
claude-any test 180 full
```

Service cleanup and status:

```sh
claude-any status
claude-any stop
```

Common Claude Any setup flags:

| Flag | Purpose |
| --- | --- |
| `--ca-env-file PATH` | Load `CLAUDE_ANY_*` values from a dotenv-style file. |
| `--ca-menu` | Apply env/flag values, then open the interactive menu for the final user choice. |
| `--ca-language en|ko|ja|zh` | Set display language. |
| `--ca-provider PROVIDER` | Set provider and skip the menu for this launch. |
| `--ca-model MODEL` | Set the current provider model. |
| `--ca-advisor-model MODEL` | Set the Advisor model; use `off` to disable it. |
| `--ca-base-url URL` | Set the current provider base URL. |
| `--ca-api-key KEY` | Store the current provider API key directly. Prefer env vars for scripts. |
| `--ca-api-key-env ENVVAR` | Store the current provider API key from an environment variable. |
| `--ca-set-api-key PROVIDER KEY` | Store a key for a specific provider. |
| `--ca-set-api-key-env PROVIDER ENVVAR` | Store a provider key from an environment variable. |
| `--ca-max-output-tokens VALUE` | Set provider output-token cap. |
| `--ca-context-window VALUE` | Set provider/router context-window cap where supported. |
| `--ca-request-timeout-ms VALUE` | Set upstream request timeout in milliseconds. |
| `--ca-rate-limit-rpm VALUE` | Set provider RPM limit; `0` disables throttling but keeps usage display. |
| `--ca-rate-limit-status on|off` | Show or hide RPM/rate-limit status in the Claude Code statusline. |
| `--ca-stream on|off` | Enable or disable streaming through the router. |
| `--ca-stream-word-chunking on|off` | Split streamed text into smaller word-like chunks when enabled. |
| `--ca-ollama-num-ctx VALUE` | Set Ollama `num_ctx`. |
| `--ca-ollama-ctx-range MIN MAX` | Set Ollama auto context range. |
| `--ca-ollama-option KEY=VALUE` | Set an Ollama option such as `temperature=0.3`. |
| `--ca-web-search` / `--ca-no-web-search` | Force-enable or disable web-search MCP for this launch. |
| `--ca-web-fetch` / `--ca-no-web-fetch` | Enable or disable fetch MCP for web page content. |
| `--ca-disable-skills` / `--ca-enable-skills` | Control Claude Code skills for this launch. |
| `--ca-no-update-check` | Skip the Claude Code update check. |
| `--ca-status` | Print status and exit. |
| `--ca-stop` | Stop managed router services and exit. |

Notes for automation:

- `--ca-api-key-env` avoids putting secrets directly in shell history.
- `--ca-api-key` and `--ca-set-api-key` are available for direct key passing,
  but prefer the environment-variable forms in shared scripts and terminals.
- `claude-any stop` is safe to run before scripted tests to remove stale
  router/proxy processes.
- Use `claude-any test 60 auto` for a quick readiness check and reserve
  `claude-any test 180 full` for deeper provider validation.
- Headless flags persist in `~/.config/claude-any/config.json`, so the next
  interactive launch starts from the same provider/model settings.

## Router Chat and Plan Artifacts

Claude Code Plan mode uses internal Claude Code tools and UI state. Claude Any
keeps `EnterPlanMode` available for non-Anthropic providers and handles the
Plan-mode transition in the router when the upstream model does not reliably
select that internal tool. If Claude Code forces `tool_choice=EnterPlanMode`,
the router returns a valid Anthropic `tool_use` locally. If a long
implementation request receives only a short or empty non-actionable text
response, the router promotes that response to `EnterPlanMode` using
language-agnostic structure checks. Other unsupported Claude Code self-tools
are still removed before forwarding requests to non-Anthropic providers.

For troubleshooting, write `TRACE` to `~/.config/claude-any/log-level`; the
router then records redacted request and response summaries in:

- `~/.config/claude-any/requests.jsonl`
- `~/.config/claude-any/responses.jsonl`

The router also exposes a provider-neutral control plane for headless sub
agents. It is intentionally separate from `/v1/messages` so it does not change
Claude Code's API traffic.

Endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/ca/chat/health` | `GET` | Check chat service availability. |
| `/ca/chat/messages` | `POST` | Send a message. |
| `/ca/chat/messages?after=N` | `GET` | Poll messages after the last seen id. |
| `/ca/chat/wait?after=N&timeout=60` | `GET` | Long-poll until messages arrive or timeout. |
| `/ca/chat/stream?after=N&timeout=300` | `GET` | Server-sent event stream for agents that must wait for replies. |
| `/ca/chat/files` | `POST` | Upload a text/base64 file and optionally announce it to a channel. |
| `/ca/chat/files/NAME` | `GET` | Fetch an uploaded file. |
| `/ca/plan/artifacts` | `POST` | Create and serve a plan artifact file. |
| `/ca/plan/artifacts` | `GET` | List plan artifacts. |
| `/ca/plan/artifacts/NAME` | `GET` | Fetch a plan artifact. |

Message shape:

```json
{
  "channel": "agents",
  "sender_id": "codex",
  "recipients": ["kimi", "qwen"],
  "thread_id": "task-123",
  "parent_id": 42,
  "message": "I need the current test failure output."
}
```

The response includes a monotonically increasing `id`. Store that id and pass
it back as `after=N` to receive only new messages.

Headless examples:

```sh
# Send a direct message.
curl -s http://127.0.0.1:8799/ca/chat/messages \
  -H 'content-type: application/json' \
  -d '{"channel":"agents","sender_id":"codex","recipients":["kimi"],"message":"Please inspect the failing test."}'

# Poll for updates addressed to kimi.
curl -s 'http://127.0.0.1:8799/ca/chat/messages?channel=agents&recipient=kimi&after=0'

# Wait on SSE until a response arrives.
curl -N 'http://127.0.0.1:8799/ca/chat/stream?channel=agents&recipient=codex&after=10&timeout=300'

# Create a plan artifact that other agents can fetch by URL.
curl -s http://127.0.0.1:8799/ca/plan/artifacts \
  -H 'content-type: application/json' \
  -d '{"title":"handoff","name":"handoff.md","content":"# Plan\n- reproduce\n- patch\n- verify"}'
```

Artifacts are stored under `~/.config/claude-any/plan-artifacts/`; chat
messages are stored in `~/.config/claude-any/chat-messages.jsonl`.

## Recommended Uses

Claude Any is a good fit for slower background work where steady throughput
matters more than instant interaction:

- Docker host maintenance and cleanup.
- Windows, Linux, and remote server administration.
- Finding unused files and turning cleanup into repeatable scripts.
- Periodic security checklists and configuration review.
- Log review for failed sign-in attempts, exposed services, suspicious access,
  and other intrusion indicators.
- Noisy Windows Event Log review, including possible virus, ransomware,
  brute-force, and remote-access intrusion attempts.
- Drafting operational reports from command output and logs.
- Turning requests like "install PostgreSQL in a Docker container" or "analyze
  today's Docker logs and email me a report" into commands, scripts, scheduled
  jobs, and summaries.

### Tiered Supervision Pattern

A practical operating pattern is to combine models by cost and capability:

- Small or cheaper models watch logs, detect possible issues, and prepare first
  summaries.
- A larger model reviews the findings, writes policy, decides priority, and
  plans the response.
- Small models then execute routine commands, cleanup, reporting, or scheduled
  checks under the larger model's supervision.

It is not a replacement for dedicated monitoring, EDR, SIEM, or security
products. It is useful as an operator assistant that can inspect logs, propose
scripts, summarize findings, and produce readable reports while preserving
premium Claude/Codex tokens for harder work.
Used this way, Claude Any can become a free or low-cost system security watcher
for routine checks and summaries.

## Web Search

Non-native providers may not have Claude Code's remote web-search capability.
Claude Any can wire separate MCP tools for DuckDuckGo search and URL fetch so
agents can still perform web research through explicit tools.

## Service Lifecycle

Claude Any starts provider helpers on demand rather than keeping every helper
alive permanently.

- `claude-any stop` stops managed Claude Any router processes.
- When launching Claude Code, Claude Any starts only the services required by
  the selected provider.
- Ollama and Ollama Cloud router mode use the Claude Any router on
  `127.0.0.1:8799`.
- NVIDIA hosted router mode uses the Claude Any router on `127.0.0.1:8799`;
  hosted API Catalog models do not require a separate NVIDIA proxy.
- For clean provider-switch testing, run `claude-any stop`, select the provider,
  then launch or test. This avoids stale router port ownership from old sessions.

## Development Story

Claude Any started because long Claude Code sessions can run out of premium
tokens even on a high plan. The intent is to keep work moving while waiting for
the next token window: slower but usable providers can handle summaries,
research, journals, simple code, and delegated background tasks.

During development, Anthropic-compatible Messages endpoints proved to be the
cleanest integration path for Claude Code. Ollama, vLLM, and NIM can expose
those routes. Generic OpenAI-compatible chat endpoints were not selected as the
primary route because tool-call translation was less stable around parameters,
tool results, repeated calls, retries, and model selection.

The vLLM work also showed that a successful text response is not enough for
Claude Code. The selected model and server need compatible tool-call formatting.
In particular, Qwen3-Coder should use vLLM's `qwen3_xml` tool parser. Claude Any
therefore expanded its compatibility test to cover text, `tool_use`, and
`tool_result` phases.

Local Qwen 3.6 27B Q4 runs were tested through Ollama and vLLM on RTX 5090 and
MSI GB10-class hardware. They worked, but the speed belongs in a different
category from native Claude Code or Codex. For this hybrid workflow, some
hosted/cloud models from NVIDIA NIM and Ollama Cloud were more practical than
expected.

## Demo Assets

Demo images, GIF, and MP4 are generated from a script:

```sh
python scripts/make_demo_assets.py
```

Generated files live in `docs/assets/`.

## Next Stage TODO

- **True NVIDIA hosted upstream streaming**: the current NVIDIA hosted router
  path opens an SSE stream back to Claude Code, but calls NVIDIA hosted
  `/v1/chat/completions` with `stream:false` and emits the converted Anthropic
  response only after the upstream request completes. Implement an OpenAI
  streaming parser for NVIDIA hosted so text deltas are forwarded to Claude Code
  as they arrive.
- **Safe streamed tool-call conversion**: when enabling NVIDIA upstream
  streaming, accumulate OpenAI `tool_calls` / function-call chunks until each
  tool input JSON object is complete, then emit valid Anthropic
  `content_block_start`, `input_json_delta`, and `content_block_stop` events.
  Text deltas can stream immediately; tool-use blocks must preserve Claude
  Code's strict content-block ordering and indexes.
- **Streaming diagnostics**: add router debug logs or a compatibility subtest
  that distinguishes "Claude Code SSE is open" from "upstream provider is truly
  streaming" so long NVIDIA hosted waits are easier to explain.

## Troubleshooting

- If the first request says a model does not exist, re-open the menu and select
  a model that the current provider actually serves.
- If Ollama Cloud returns authentication errors, check `OLLAMA_API_KEY` or use
  the API key menu.
- If local Ollama cloud models fail, run `ollama signin` on the Ollama host.
- If vLLM or NIM returns model `404`, map Claude Code's model aliases to the
  served model name or select the custom model entry.
- If vLLM tool calls fail, verify both model support and the vLLM
  `--tool-call-parser`/chat-template combination. Qwen3-Coder should start with
  `--enable-auto-tool-choice --tool-call-parser qwen3_xml`.
- If Claude Code update checks fail due to disk space, clean local caches or
  skip the check with `--ca-no-update-check`.

## Security Checklist

- Do not commit `~/.config/claude-any/`.
- Do not commit API keys, tokens, screenshots containing secrets, or router logs.
- Prefer environment variables for keys in automation.
- Revoke and rotate any key that was pasted into chat, logs, or issue reports.
