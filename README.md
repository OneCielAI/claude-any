# Claude Any

<p align="center">
  <img src="logo.png" alt="Claude Any logo" width="360">
</p>

![Claude Any: full Claude Code experience with free or low-cost LLMs](claude-any-adv.png)

| English | [한국어](docs/README.ko.md) | [日本語](docs/README.ja.md) | [中文](docs/README.zh.md) |
| --- | --- | --- | --- |

[![npm version](https://img.shields.io/npm/v/@oneciel-ai/claude-any?logo=npm&label=npm)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![npm downloads](https://img.shields.io/npm/dm/@oneciel-ai/claude-any?logo=npm&label=downloads)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> ## 🚀 Use the full Claude Code experience with free or low-cost LLMs
>
> - **Free** — [NVIDIA hosted NIM](https://build.nvidia.com/) (qwen3-coder-480b, gpt-oss, and friends) through the API Catalog.
> - **Low-cost** — [Ollama Cloud](https://ollama.com/cloud) and [Fireworks.ai](https://fireworks.ai/) for GLM, Qwen, DeepSeek, Kimi, and other open-weight models at a fraction of frontier-model pricing.
> - **Free + local** — [Ollama](https://ollama.com/), [LM Studio](https://lmstudio.ai/), or [vLLM](https://github.com/vllm-project/vllm) on your own GPU, fully offline.
> - **Plan Mode + Advisor ready** — Claude Any preserves Claude Code Plan Mode on non-Anthropic providers and adds an optional long-context Advisor model for review.
> - **Local browser chat** — the router serves `/ca/web/chat`, a local browser UI that talks to the selected provider through the same `/v1/messages` path Claude Code uses.
> - **Smooth free-model pacing** — Claude Code spends time reading files and running tools, and Claude Any uses that natural gap for RPM pacing so NVIDIA hosted free models feel usable even with strict per-minute limits.
>
> Provider, model, base URL, API key, streaming behavior, and LLM options are all selected from a console menu **before** Claude Code starts. Claude Code itself runs untouched with all of its native tooling, slash commands, and workflows.

## Today's Top 3 Benefits

### 2026-06-17

1. **Channel backlog control** — routed sessions now install `/channel-clear`.
   Use `/channel-clear status` to inspect pending external channel work, or
   `/channel-clear` to discard already queued bridge backlog without replaying
   it into the model. New events arriving after the clear point are still
   delivered normally.
2. **Live LLM preset commands** — routed sessions can switch or restore runtime
   LLM presets from Claude Code with `/llm-options`, `/llm-restore`, and the
   generated `/llm-*` preset commands.
3. **Channel stale replay diagnostics** — channel cursors, summary cursors, and
   direct-worker queues are now surfaced together so operators can distinguish
   new MCP delivery from stale local bridge backlog.

### 2026-06-12

1. **Fireworks.ai provider** — Fireworks is now a first-class
   Anthropic-compatible routed provider. Claude Any defaults to
   `https://api.fireworks.ai/inference` for `/v1/messages`, reads live model
   metadata from `https://api.fireworks.ai/v1/accounts/{account_id}/models`,
   and caches `contextLength`, tool/vision support, and
   `baseModelDetails.parameterCount` for LLM option presets.
2. **Provider metadata stays account-aware** — Fireworks model discovery supports
   `account_id` and `model_api_base_url` provider options, so public
   `accounts/fireworks/...` models and account-scoped custom models can share
   the same runtime path without hardcoded model-size guesses.
3. **Fireworks headless setup** — Fireworks can be provisioned through the same
   `--ca-provider`, `--ca-model`, `--ca-api-key-env`, and
   `--ca-provider-option` flags as the other routed providers.

### 2026-06-11

1. **OpenRouter provider** — [OpenRouter](https://openrouter.ai/) is a first-class
   OpenAI-compatible provider with full feature parity (model discovery,
   provider-options, status, help), defaulting to the free
   `nvidia/nemotron-3-ultra-550b-a55b:free` model.
2. **Per-key cooldown for multi-key rotation** — when one key in a multi-key pool
   hits a 429, Claude Any rests it until its rate limit resets (from
   `X-RateLimit-Reset`/`Retry-After`) and keeps serving from the remaining keys,
   then rejoins it automatically. Ideal for OpenRouter `:free` per-key limits.
3. **Faithful Anthropic native behavior** — routed Anthropic no longer overrides
   Claude Code's native per-model output cap (e.g. Fable 5 keeps its 64k default
   instead of a forced 4096), `/model` switching reaches the chosen model instead
   of collapsing to the menu model, and the `?beta=true` flag is forwarded so
   long-context (1M) requests are billed correctly. Claude native and Anthropic
   routed sessions now follow Claude Code's built-in `/advisor` flow (model
   picker + advisor server tool) end to end: Claude Any no longer installs its
   own `/advisor` command, intercepts advisor traffic, or strips the advisor
   server tool for the Anthropic provider.

### 2026-06-05

1. **Windows-aware install paths** — Claude Any now uses `%APPDATA%\claude-any`
   for its default config on Windows, installs helper/statusline scripts under
   `%LOCALAPPDATA%\claude-any\bin`, and searches Windows npm shims such as
   `%APPDATA%\npm` when launching `claude`.
2. **DeepSeek V4 thinking compatibility** — DeepSeek.com V4 requests keep tools
   available but remove forced `tool_choice` before upstream calls and
   compatibility tests, matching DeepSeek's official V4 thinking-mode agent
   compatibility guidance.
3. **More reliable install diagnostics** — multiple-install checks now reuse the
   same OS-aware executable search paths, so Windows and mixed npm-prefix
   machines report the launcher that will actually run.

### 2026-06-03

1. **Router lifecycle isolation** — Claude Any now distinguishes routers it
   manages from routers owned by another config directory or active session. It
   replaces stale same-config routers only when they are idle, and managed
   routers shut down after their Claude Code child exits.
2. **OpenAI/vLLM compatibility repairs** — long compacted routed sessions keep
   required tool-result messages with assistant tool calls, vLLM endpoint
   routing distinguishes OpenAI-compatible and Anthropic-compatible servers, and
   128K context presets stay visible instead of collapsing back to 65K.
3. **Cleaner ultracode, advisor, and channel behavior** — ultracode is gated by
   verified model capabilities, `/advisor` remains an explicit user action, and
   external-channel digests stay local so internal `tool_result` or background
   summary text is not posted back into AI-Net-style rooms.

### 2026-05-28

1. **Non-native Claude Code workflow prep** — routed providers can opt in to Claude Code dynamic workflows with `workflows_enabled`, which removes Claude Any's experimental-beta disable env for that launch.
2. **Ultracode capability guard** — `ultracode_enabled` launches Claude Code with the ultracode session setting only when the selected model advertises `xhigh_effort`; unverified DeepSeek/OpenCode/local models are not over-claimed.
3. **Model capability overrides** — `claude_code_supported_capabilities=effort,xhigh_effort,...` lets operators declare verified Claude Code capabilities per provider/model, while known Claude Opus/Sonnet model IDs are inferred automatically.

### 2026-05-25

1. **DeepSeek.com provider path** — DeepSeek's Anthropic-compatible Claude Code endpoint is available as a first-class provider with model presets and API-key launch checks.
2. **Safer shared-host router lifecycle** — routed sessions now use a stable per-user router port by default and stale same-user routers are cleaned up before launch, avoiding cross-user session bleed on shared machines.
3. **Router browser chat and optional Anthropic routing** — `/ca/web/chat` gives the local router a modern browser chat surface, and Anthropic can optionally be routed through Claude Any when you need router-owned SSE, channel, or observability features instead of direct Claude Native behavior.

### 2026-05-18

1. **Realtime channel bridge for external agents** — Claude Any now exposes `/ca/channel/*` endpoints and an SSE connector so systems like AI-Net can push live agent messages into Claude Code sessions.
2. **Advisor feedback is visible and actionable** — Advisor reviews can be surfaced in the Claude Code transcript and fed back into the executor model before plan approval or risky continuation points.
3. **Better non-Anthropic workflow parity** — Cron-style task scheduling, channel polling, and router-native coordination commands are modeled more closely to Claude Code's native behavior for Ollama, Ollama Cloud, NVIDIA hosted, vLLM, and NIM.

### 2026-05-15

1. **Router management is now navigable** — the built-in router home page is split into top-menu sections for Overview, LLM Settings, Events, and Endpoints instead of crowding everything into one long screen.
2. **Safer remote debug exposure** — router external access is off by default, requires an explicit confirmed toggle, can be switched with `/router-debug`, restarts the router to apply the bind address, and shows `debug external` in the Claude Code status line when enabled.
3. **Operator-grade observability and live settings** — the router now exposes structured event views plus live LLM setting controls, making long Claude Code sessions easier to monitor, tune, and debug without editing config files by hand.

### 2026-05-14

1. **Plan Mode loop recovery is semantic, not hard-coded** — unchanged `Read` results are now converted with the previous authoritative observation and current Plan Mode state, so Claude Code can move to `ExitPlanMode` or the next real step instead of rereading the same slice.
2. **Remote test router mode is easier to expose** — set `CLAUDE_ANY_ROUTER_BIND_HOST=0.0.0.0` when you intentionally want to test the router from another machine, while Claude Code still talks to the safe local client base.
3. **Cleaner router transcripts for third-party models** — attachment-only metadata, historical no-op tool results, and orphan tool results are normalized before reaching Ollama, Ollama Cloud, NVIDIA hosted, vLLM, or NIM.

### 2026-05-13

1. **Plan Mode works on non-Anthropic models** — Claude Any keeps Claude Code's Plan Mode usable even when the upstream provider is NVIDIA hosted, Ollama Cloud, local Ollama, vLLM, or NIM.
2. **Advisor review with a bigger model** — pick a long-context Advisor Model at launch, then use `/advisor` inside Claude Code to review the current task, blockers, and next concrete action.
3. **Free-model RPM limits feel smoother** — router-side RPM pacing uses the natural time spent reading files and running tools, so NVIDIA hosted free models can stay within per-minute limits with less visible waiting.

### Demo

![NVIDIA hosted NIM driving Claude Code (deepseek-4-flash)](docs/assets/claude-any-nvidia-nim.gif)

NVIDIA hosted NIM (deepseek-4-flash) driving Claude Code through the claude-any router. &nbsp;[full mp4 ⤓](https://github.com/OneCielAI/claude-any/raw/main/demo/claude-any-nvidia-nim.mp4)

![Ollama Cloud streamed through the claude-any router (glm-5.1)](docs/assets/claude-any-ollama-cloud.gif)

Ollama Cloud (glm-5.1) streamed through the claude-any router with SSE word-boundary chunking enabled. &nbsp;[full mp4 ⤓](https://github.com/OneCielAI/claude-any/raw/main/demo/claude-any-ollama-cloud.mp4)

---

Claude Any is a provider selector and compatibility launcher for Claude Code.
It lets you choose Anthropic, Ollama, Ollama Cloud, DeepSeek.com, OpenCode Zen,
OpenCode Go, OpenRouter, LM Studio,
vLLM, NVIDIA hosted models, or self-hosted NIM before Claude Code starts, then
passes normal Claude Code arguments through unchanged.

Credits: One Ciel LLC

Current version: `0.1.106`

## Why This Exists

Claude Any started from a practical need: even on the highest Claude Code plan,
long sessions can run out of available tokens or become blocked while waiting
for the next quota window. The goal is not to replace Claude Code, but to keep
work moving. Slower but usable providers such as NVIDIA NIM, Ollama Cloud,
LM Studio, vLLM, and local Ollama can act as hybrid third-party agents for summaries,
research, journaling, simple coding tasks, and delegated background work.

Another design goal is to keep as much of Claude Code's native experience as
possible. When a provider exposes an Anthropic-compatible endpoint, Claude Any
prefers that path so Claude Code tooling, permissions, model selection, and
workflow behavior remain close to the original. For capabilities that remote
providers cannot supply directly, such as web search, Claude Any adds separate
MCP-based tooling.

The pre-launch menu is console-first. Provider, model, base URL, API key, and
options are meant to be easy to review and change before Claude Code starts,
including over SSH.

macOS has not been fully tested by the maintainer yet, but Claude Any uses
portable Python and shell wrappers. If you hit a macOS issue, please report it.

- D. Yun

## Install

[![npm version](https://img.shields.io/npm/v/@oneciel-ai/claude-any.svg)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![npm downloads](https://img.shields.io/npm/dm/@oneciel-ai/claude-any.svg)](https://www.npmjs.com/package/@oneciel-ai/claude-any)

Requirements:

- Python 3.10+
- Claude Code installed and available as `claude`
- Node/npm (used for the install shim and optional MCP web tooling)

**Install from the npm registry (recommended):**

```sh
npm install -g @oneciel-ai/claude-any
```

```sh
claude-any
```

### Nightly channel

Pre-release builds are published from the `nightly` branch with the
`nightly` npm dist-tag. Use them if you want the latest fixes before the
next stable release; expect occasional churn.

```sh
npm install -g @oneciel-ai/claude-any@nightly
```

To go back to stable:

```sh
npm install -g @oneciel-ai/claude-any@latest
```

Nightly version numbers follow `X.Y.Z-nightly.YYYYMMDD-HHmmss.SHORTSHA` (UTC).
Maintainers publish nightlies by pushing to the `nightly` branch; GitHub
Actions handles npm publishing with the repository `NPM_TOKEN`. Do not run
`npm publish` from a local checkout.

## Run Claude Code Headlessly

Use headless mode when a script, SSH session, CI job, or parent agent needs to
launch Claude Code directly without opening the pre-launch menu. `claude-any`
consumes `--ca-*` options, starts the required local router, and passes the
remaining arguments to Claude Code.

```sh
claude-any --ca-provider nvidia-hosted --ca-model z-ai/glm-4.7
```

```sh
claude-any --ca-provider ollama-cloud --ca-model glm-5.1
```

```sh
claude-any --ca-provider ollama --ca-base-url http://127.0.0.1:11434 --ca-model qwen3-coder
```

Apply settings only, without launching Claude Code:

```sh
claude-any --ca-provider ollama-cloud --ca-model deepseek-v4-flash --ca-context-window 1048576 --ca-request-timeout-ms 300000 --ca-no-launch
```

New routed providers can also be configured entirely with `--ca-*` flags. For
DeepSeek.com:

```sh
claude-any --ca-provider deepseek --ca-base-url https://api.deepseek.com/anthropic --ca-model deepseek-v4-pro --ca-api-key-env DEEPSEEK_API_KEY --ca-no-launch
```

For OpenCode Zen:

```sh
claude-any --ca-provider opencode --ca-base-url https://opencode.ai/zen --ca-model claude-sonnet-4-6 --ca-api-key-env OPENCODE_ZEN_API_KEY --ca-no-launch
```

For OpenCode Go:

```sh
claude-any --ca-provider opencode-go --ca-base-url https://opencode.ai/zen/go --ca-model qwen3.6-plus --ca-api-key-env OPENCODE_GO_API_KEY --ca-provider-option endpoint:custom-model=chat --ca-no-launch
```

For [Kimi.com Code](https://www.kimi.com/code/docs/third-party-tools/other-coding-agents.html):

```sh
claude-any --ca-provider kimi --ca-base-url https://api.kimi.com/coding --ca-model kimi-for-coding --ca-api-key-env KIMI_API_KEY --ca-no-launch
```

Kimi K2.7 Code is exposed through the documented `kimi-for-coding` model ID.
Claude Any keeps the upstream Anthropic thinking/tool round trip intact and
applies Kimi's documented 256K context window and 32K output defaults.
Claude Any does not reuse Kimi Code CLI's own login/OAuth state; use a Kimi
Code API key directly or via `KIMI_API_KEY` / `KIMI_API_KEYS`.

For [OpenRouter](https://openrouter.ai/) (OpenAI-compatible; access to hundreds of
models through one key). The default model is the free
`nvidia/nemotron-3-ultra-550b-a55b:free`; pick any slug from OpenRouter's catalog:

```sh
claude-any --ca-provider openrouter --ca-model nvidia/nemotron-3-ultra-550b-a55b:free --ca-api-key-env OPENROUTER_API_KEY --ca-no-launch
```

OpenRouter free (`:free`) models are rate-limited per key (e.g. 20 requests/min),
so this is a natural fit for multi-key round-robin (below): store several keys and
Claude Any spreads requests across them and rests any key that hits a 429 until
its rate limit resets.

For [Fireworks.ai](https://fireworks.ai/) (Anthropic-compatible `/v1/messages`;
model metadata comes from the account-scoped Fireworks model API):

```sh
claude-any --ca-provider fireworks --ca-base-url https://api.fireworks.ai/inference --ca-model accounts/fireworks/models/kimi-k2p5 --ca-api-key-env FIREWORKS_API_KEY --ca-provider-option account_id=fireworks --ca-no-launch
```

`--ca-provider-option KEY=VALUE` applies a provider option to the current
provider; use `--ca-set-provider-option PROVIDER KEY=VALUE` when a script needs
to configure a provider other than the current one. OpenCode endpoint overrides
use `endpoint:<model-id>=messages|chat|responses|gemini`. Fireworks model-list
overrides use `account_id=<account>` and
`model_api_base_url=https://api.fireworks.ai`.

Apply the recommended LLM options for the saved provider/model, then exit:

```sh
claude-any --ca-auto-llm-options --ca-no-launch
```

Apply the recommended LLM options for a specific model name, then exit:

```sh
claude-any --ca-provider ollama-cloud --ca-auto-llm-options deepseek-v4-flash --ca-no-launch
```

```sh
claude-any --ca-env-file .env.claude-any --ca-no-launch
```

This is useful for remote provisioning, CI setup, base image preparation, or a
parent agent that wants to configure Claude Any once and launch Claude Code in a
separate step. Without `--ca-no-launch`, Claude Any applies the settings and
then launches Claude Code as usual.

Run one non-interactive Claude Code prompt:

```sh
claude-any --ca-provider nvidia-hosted --ca-model z-ai/glm-4.7 --ca-no-update-check -p "Reply with OK only." --output-format text
```

Use the saved provider/model and only skip the menu:

```sh
CLAUDE_ANY_SKIP_MENU=1 claude-any -p "Summarize this repository." --output-format text
```

Configure every launch option with flags:

```sh
claude-any --ca-provider nvidia-hosted --ca-base-url https://integrate.api.nvidia.com/v1 --ca-model z-ai/glm-4.7 --ca-advisor-model deepseek-ai/deepseek-v4-pro --ca-api-key-env NVIDIA_API_KEY --ca-max-output-tokens 4096 --ca-context-window 65536 --ca-request-timeout-ms 120000 --ca-rate-limit-rpm 0 --ca-rate-limit-status off --ca-no-update-check -p "Reply with OK only." --output-format text
```

Full Ollama Cloud 1M-context setup with flags:

```sh
claude-any --ca-provider ollama-cloud --ca-base-url https://ollama.com --ca-model deepseek-v4-flash --ca-advisor-model deepseek-v4-pro --ca-api-key-env OLLAMA_API_KEY --ca-context-window 1048576 --ca-max-output-tokens 8192 --ca-request-timeout-ms 300000 --ca-stream on --ca-stream-word-chunking off --ca-rate-limit-rpm 0 --ca-rate-limit-status off -p "Create an implementation plan." --output-format text
```

The same setup can let Claude Any choose the model's recommended LLM options:

```sh
claude-any --ca-provider ollama-cloud --ca-base-url https://ollama.com --ca-auto-llm-options deepseek-v4-flash --ca-advisor-model deepseek-v4-pro --ca-api-key-env OLLAMA_API_KEY --ca-stream on --ca-rate-limit-status off -p "Create an implementation plan." --output-format text
```

Full local Ollama setup with flags:

```sh
claude-any --ca-provider ollama --ca-base-url http://127.0.0.1:11434 --ca-model qwen3-coder --ca-ollama-num-ctx auto --ca-ollama-ctx-range 65536 262144 --ca-request-timeout-ms 180000 --ca-stream on --ca-no-update-check -p "Inspect the current project and summarize risks." --output-format text
```

Full NVIDIA hosted setup with rate-limit management:

```sh
claude-any --ca-provider nvidia-hosted --ca-base-url https://integrate.api.nvidia.com/v1 --ca-model z-ai/glm-4.7 --ca-advisor-model deepseek-ai/deepseek-v4-pro --ca-api-key-env NVIDIA_API_KEY --ca-context-window 65536 --ca-max-output-tokens 4096 --ca-request-timeout-ms 180000 --ca-stream on --ca-rate-limit-rpm 0 --ca-rate-limit-status off -p "Review this repository and list next actions." --output-format text
```

Or put the same values in environment variables:

```sh
export CLAUDE_ANY_SKIP_MENU=1
export CLAUDE_ANY_PROVIDER=nvidia-hosted
export CLAUDE_ANY_BASE_URL=https://integrate.api.nvidia.com/v1
export CLAUDE_ANY_MODEL=z-ai/glm-4.7
export CLAUDE_ANY_ADVISOR_MODEL=deepseek-ai/deepseek-v4-pro
export CLAUDE_ANY_API_KEY_ENV=NVIDIA_API_KEY
export CLAUDE_ANY_MAX_OUTPUT_TOKENS=4096
export CLAUDE_ANY_CONTEXT_WINDOW=65536
export CLAUDE_ANY_REQUEST_TIMEOUT_MS=120000
export CLAUDE_ANY_RATE_LIMIT_RPM=0
export CLAUDE_ANY_RATE_LIMIT_STATUS=off
claude-any -p "Reply with OK only." --output-format text
```

For `.env` driven runs, save the same `CLAUDE_ANY_*` values in a file:

```dotenv
CLAUDE_ANY_SKIP_MENU=1
CLAUDE_ANY_PROVIDER=ollama-cloud
CLAUDE_ANY_BASE_URL=https://ollama.com
CLAUDE_ANY_MODEL=deepseek-v4-flash
CLAUDE_ANY_ADVISOR_MODEL=deepseek-v4-pro
CLAUDE_ANY_API_KEY_ENV=OLLAMA_API_KEY
CLAUDE_ANY_CONTEXT_WINDOW=1048576
CLAUDE_ANY_MAX_OUTPUT_TOKENS=8192
CLAUDE_ANY_REQUEST_TIMEOUT_MS=300000
CLAUDE_ANY_STREAM=on
CLAUDE_ANY_STREAM_WORD_CHUNKING=off
CLAUDE_ANY_RATE_LIMIT_RPM=0
CLAUDE_ANY_RATE_LIMIT_STATUS=off
CLAUDE_ANY_WEB_SEARCH=on
CLAUDE_ANY_WEB_FETCH=on
CLAUDE_ANY_SELF_UPDATE_CHECK=off
CLAUDE_ANY_UPDATE_CHECK=off
```

Then apply and launch:

```sh
claude-any --ca-env-file .env.claude-any -p "Reply with OK only." --output-format text
```

Or apply only and exit:

```sh
claude-any --ca-env-file .env.claude-any --ca-no-launch
```

You can also use a CLI flag to override one `.env` value for a single run:

```sh
claude-any --ca-env-file .env.claude-any --ca-model glm-5.1 -p "Use the overridden model for this run." --output-format text
```

Override order is deterministic: saved user choices from the menu are the
baseline, OS environment variables override them, `--ca-env-file` values
override the OS environment, CLI `--ca-*` parameters override the env file, and
`--ca-menu` lets the final interactive menu choice override everything.

Quietly upgrade Claude Any and Claude Code, then exit without launching Claude:

```sh
claude-any --ca-upgrade-and-exit
```

Headless coverage checklist: provider, base URL, model, Advisor model, API key
or API-key environment variable, multi-key round-robin, max output, context window, request timeout,
RPM limit, RPM status display, streaming, web search, web fetch, Claude skills,
update check, language, Ollama context/options, and normal Claude Code
passthrough arguments are all configurable without opening the menu. API keys
can be passed directly with `--ca-api-key`, but `--ca-api-key-env` is safer for
scripts because the secret does not appear in shell history. To remove stored
credentials, use the launch-menu `Clear stored API key(s)` action or run
`claude-any set-api-key PROVIDER clear`.

For high-token routed sessions such as ultracode, or for rate-limited free models
like OpenRouter `:free`, store multiple keys for the same provider and Claude Any
will rotate them per upstream request:

```sh
export OPENROUTER_API_KEYS="KEY1,KEY2,KEY3,KEY4"
claude-any --ca-provider openrouter --ca-api-keys-env OPENROUTER_API_KEYS --ca-no-launch
# or directly: claude-any set-api-keys openrouter KEY1,KEY2,KEY3,KEY4
```

Rotation is round-robin **with per-key cooldown**: if one key returns a 429, that
key rests until its rate limit resets — Claude Any reads the reset time from the
response (`X-RateLimit-Reset`, falling back to `Retry-After`), skips the resting
key, and keeps serving from the remaining keys; the key automatically rejoins the
rotation once its cooldown expires. A key that exhausts a daily quota rests until
the quota refreshes rather than retrying every hour.

This distributes provider quota/rate usage across keys; it does not reduce the
task's actual token consumption. The menu also accepts comma/newline-separated
keys in the API-key input paths and shows a masked primary key plus a short
fingerprint so you can confirm which key set is actually active without exposing
the secret.

More examples are in [Headless Examples](#headless-examples) and
[the full manual](docs/manual.md#headless-usage).

**Upgrade:**

```sh
npm update -g @oneciel-ai/claude-any
```

```sh
claude-any version
```

**Uninstall:**

```sh
npm uninstall -g @oneciel-ai/claude-any
```

### Alternative install paths

Install directly from the GitHub repository (useful for testing unreleased
commits between npm publishes):

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
```

```sh
claude-any
```

POSIX source install:

```sh
git clone https://github.com/OneCielAI/claude-any.git
```

```sh
cd claude-any
```

```sh
./install.sh
```

```sh
claude-any
```

Windows PowerShell source install:

```powershell
git clone https://github.com/OneCielAI/claude-any.git
```

```powershell
cd claude-any
```

```powershell
.\install.ps1
```

```powershell
claude-any
```

### Releasing (maintainers)

The npm registry version is published automatically by the
[`Publish to npm`](.github/workflows/npm-publish.yml) workflow when `main`
or `nightly` is pushed. The workflow needs an `NPM_TOKEN` repository secret
containing a granular access token for `@oneciel-ai/claude-any` with
*Bypass 2FA for publishing* enabled.

Do not run `npm publish` from a local checkout. Local npm auth can be
different from the GitHub Actions token and may report `E401`/`E404` even
when the branch-push workflow publishes successfully.

Release flow:

1. Nightly work: commit to `nightly` and run `git push origin nightly`.
2. Stable release: bump `package.json` and `claude_any.py` to the target stable
   version when needed, merge `nightly` to `main`, and run `git push origin main`.
3. Verify the `Publish to npm` workflow succeeded.
4. For stable releases, create the matching GitHub Release after npm publish.


![Claude Any menu](docs/assets/claude-any-main.en.png)

## Demo

![Claude Any demo](docs/assets/claude-any-demo.en.gif)

The demo sequence now shows provider selection, Base URL entry, model selection,
LLM options, and the compatibility test. The compatibility test checks a plain
text response, a required `tool_use`, and a `tool_result` follow-up before the
launcher recommends starting Claude Code. When multiple API keys are configured
for the selected provider, the test also sends a lightweight text probe with
each key so a dead key is caught before launch instead of during round-robin use.

Additional current screenshots:

| Provider | Base URL | Model | LLM options | Compatibility |
| --- | --- | --- | --- | --- |
| ![Provider](docs/assets/claude-any-provider.en.png) | ![Base URL](docs/assets/claude-any-base-url.en.png) | ![Model](docs/assets/claude-any-model.en.png) | ![Options](docs/assets/claude-any-options.en.png) | ![Test](docs/assets/claude-any-test.en.png) |

See the [full manual](docs/manual.md) for provider setup, headless flags, and
troubleshooting. A downloadable demo video is available at
[docs/assets/claude-any-demo.mp4](docs/assets/claude-any-demo.mp4).

## Development Story

Claude Any was built through real integration tests: provider switching, model
discovery, API-key entry, compatibility tests, web-search tooling, timeout
handling, and native Claude Code behavior. The main lesson was that
Anthropic-compatible Messages endpoints are the cleanest integration path when a
provider supports them. Ollama, LM Studio, vLLM, and NIM can expose
Anthropic-compatible routes that preserve more of Claude Code's tooling model
than a generic OpenAI-compatible chat route.

Local inference was also tested with Qwen 3.6 27B Q4 through Ollama and vLLM on
RTX 5090 and MSI GB10-class hardware. It worked, but the speed should not be
judged against native Claude Code or Codex. In practice, some hosted/cloud
choices such as NVIDIA NIM and Ollama Cloud felt more useful for this hybrid
workflow than expected.

OpenAI-compatible endpoints were deliberately kept out of the primary path for
Claude Code use. In testing, tool-call translation through generic OpenAI chat
compatibility was more brittle around tool parameters, tool results, repeated
calls, retries, and model selection.

The most recent vLLM finding is that server-side tool-call parsing must match
the model family. For Claude Code, a vLLM server can be reachable and still fail
if `--tool-call-parser` is wrong. In particular, Qwen3-Coder should be served
with `--enable-auto-tool-choice --tool-call-parser qwen3_xml`; Hermes is for
Hermes-style models and some older Qwen tool templates. Claude Any now surfaces
this in the compatibility test instead of treating a simple text response as
enough.

## Recommended Uses

Claude Any is most useful where speed is less important than keeping background
work moving. Good fits include Docker host maintenance, Windows or Linux system
administration, cleanup scripts for unused files, periodic security checklists,
log review, Windows Event Log review, intrusion-attempt triage, and report
drafting.

It is not a replacement for dedicated security products, but it can help
administrators turn routine checks into repeatable scripts and readable reports.
It is useful for summarizing possible virus, ransomware, brute-force, or
remote-access intrusion attempts. In that sense, Claude Any can help you build a
free or low-cost system security watcher for routine checks, alerts, and
human-readable summaries.

For example, it can help turn requests such as "install PostgreSQL in a Docker
container" or "analyze today's Docker logs and email me a report" into concrete
commands, scripts, scheduled jobs, and summaries.

A practical pattern is tiered supervision: use smaller or cheaper models to
watch logs and detect possible issues, use a larger model to review findings,
write policy, and plan the response, then let smaller models execute routine
steps under that larger model's supervision.

## Features

- Pre-launch provider picker with English, Korean, Japanese, and Chinese UI.
- Provider-aware model list and custom model entry.
- API key entry outside the Claude Code chat input.
- LLM option presets for context window, output tokens, timeout, sampling, and
  native compatibility.
- Runtime LLM preset slash commands in routed sessions: `/llm-options` lists
  the active settings, `/llm-<preset>` applies a preset from the Claude Code
  slash menu, and `/llm-restore` returns to the options captured before the
  first live change. Direct Claude Native mode keeps Claude Code untouched and
  does not install these router commands.
- Compatibility test before launch, including text response, tool use, and
  tool-result round trip checks.
- Runtime context reporting for vLLM/NIM when `/v1/models` exposes
  `max_model_len`.
- Ollama model-context catalog: `claude-any ollama-catalog` downloads
  `https://ollama.com/api/tags` and Ollama library tag pages, then caches real
  context windows such as 256K Kimi and 1M DeepSeek models for preset filtering
  and status display.
- Console-first pre-launch menu for SSH and terminal workflows.
- Native paths where providers expose Claude/Anthropic-compatible endpoints.
- Router mode for providers that need request/response adaptation.
- DuckDuckGo and fetch MCP wiring for non-native providers.
- Headless setup flags such as `--ca-provider`, `--ca-model`, `--ca-base-url`,
  `--ca-api-key-env`, `--ca-provider-option`, `--ca-ollama-option`, and
  `--ca-max-output-tokens`.
- Claude Code Plan Mode support on router-backed non-Anthropic providers,
  including local handling for `EnterPlanMode` and plan artifacts.
- Optional `/advisor` slash command on non-Anthropic providers that routes the
  current task state to a selected Advisor Model, useful for long-context
  review and next-step checks. Claude native and Anthropic routed sessions use
  Claude Code's built-in `/advisor` (run `/advisor` in the session to pick its
  model); Claude Any passes that flow through untouched.
- Optional Claude Code `statusLine` integration for router RPM usage and wait
  time in the bottom status area instead of polluting the chat transcript.
- Router-side RPM control for NVIDIA hosted, self-hosted NIM, Ollama, and
  Ollama Cloud. The default is off (`rate_limit_rpm=0` and
  `rate_limit_status=off`); set a positive RPM and enable status display when
  you want router pacing telemetry.
- Soft pacing subtracts time already spent reading files, running commands, and
  waiting for tool results. In real coding sessions, those tool-call gaps absorb
  much of the RPM spacing naturally, so providers such as NVIDIA hosted NIM can
  stay within free-model limits without making every Claude Code turn feel
  rate-limited.
- Streaming proxy for Ollama/Ollama Cloud router path — tokens are delivered
  to Claude Code as they arrive instead of waiting for the full response.
- Per-provider `stream` on/off toggle and `stream_word_chunking` option to
  batch text deltas at word boundaries, mitigating SSE fragmentation that can
  break tool-call / JSON parsing in long streamed responses.
- LLM options menu shows the meaning of the highlighted row at the bottom of
  the panel in the selected language (English, Korean, Japanese, Chinese), and
  boolean rows (`Stream`, `Stream word chunking`, `Native compatibility`,
  `Think`) toggle in place when you press Enter — no input prompt.
- Tool guard hook coverage extended to the full Claude Code hook surface,
  including `WorktreeCreate` / `WorktreeRemove`, so non-git working directories
  no longer fail Agent isolation with
  `Cannot create agent worktree: not in a git repository...`.
- Config file caching — settings are read from disk once and reused until the
  file changes, reducing per-request overhead in the router.
- Router control-plane endpoints for headless agent coordination:
  `/ca/chat/messages`, `/ca/chat/wait`, `/ca/chat/stream`, `/ca/chat/files`,
  and `/ca/plan/artifacts`.

## Changelog

### 0.1.108

- **Z.AI GLM provider**: added first-class Z.AI support using the official
  Anthropic-compatible base `https://api.z.ai/api/anthropic`, including
  `glm-5.2[1m]` defaults, `[1m]` model suffix preservation, long-context
  presets, and Claude Code family-model environment mapping.
- **Z.AI managed MCP**: when Z.AI is active, Claude Any can generate the
  provider MCP config for vision, search, reader, and zread servers using the
  configured Z.AI API key; switching away from Z.AI removes the generated
  provider-specific MCP file.
- **Runtime provider architecture contracts**: added architecture helpers,
  documentation, and tests that make provider-specific behavior easier to find
  and keep isolated as Claude Any prepares for future non-Claude runtimes.
- **Streamable MCP notification hardening**: improved reconnect and
  notification delivery behavior for routed/non-native channel handling while
  preserving Claude Native behavior.
- **Statusline and Ollama handling fixes**: corrected context-limit display
  after preset changes and improved Ollama compatibility-test handling around
  provider rate-limit responses.

### 0.1.107

- **Fireworks.ai provider**: added first-class Fireworks support using the
  Anthropic-compatible inference base `https://api.fireworks.ai/inference` and
  the documented account-scoped model API
  `/v1/accounts/{account_id}/models` for model discovery.
- **Fireworks model metadata**: model refresh now stores Fireworks
  `contextLength`, `supportsTools`, `supportsImageInput`, and
  `baseModelDetails.parameterCount`, so context presets and model-size display
  are based on provider metadata instead of guessed IDs.
- **Fireworks provisioning flags**: `--ca-provider fireworks`,
  `FIREWORKS_API_KEY`/`FIREWORKS_API_KEYS`, and provider options
  `account_id` / `model_api_base_url` are available for scripted setup.

### 0.1.106

- **MCP notification wait guard**: routed streams now cap MCP
  `wait_for_notifications` / `wait_for_response`-style tool calls in every
  provider conversion path, including Anthropic-compatible SSE passthrough.
  Empty wait-tool inputs also receive a short timeout. This prevents long
  polling tool calls from occupying Claude Code while mailbox/SSE notifications
  pile up behind them.
- **Mailbox delivery hardening**: chat mailbox writes now rescan the persisted
  JSONL tail under an inter-process file lock before assigning the next id, so
  concurrent MCP writers cannot reuse the same local message id.
- **Stable notification de-duplication**: MCP notification observers now
  de-duplicate repeated delivery of the same stable event id
  (`stream_id`, `message_id`, `assignment_id`, `poll_id`, and similar generic
  metadata) across multiple MCP writer names without hard-coding any product.

### 0.1.105

- **Router lifecycle isolation**: routed launches now track managed router
  ownership with the current Claude Any config directory and owner process,
  replace only idle same-config routers on the same port, refuse foreign-config
  routers instead of killing unrelated sessions, and ask managed routers to stop
  after their Claude Code child exits. npm `postinstall` also performs a
  best-effort managed-router cleanup so upgrades do not leave stale local
  bridges attached to old code.
- **Routed transcript repair for OpenAI-compatible providers**: compacted or
  truncated contexts that still contain an assistant `tool_calls` message are
  repaired before upstream forwarding by preserving the required matching tool
  messages. This avoids DeepSeek/OpenAI-compatible errors such as
  `insufficient tool messages following tool_calls message` after long routed
  coding sessions.
- **vLLM and local Anthropic-compatible routing fixes**: vLLM endpoint detection
  now distinguishes OpenAI-compatible `/v1` URLs from Anthropic-compatible
  Messages endpoints, normalizes system messages for Anthropic-style vLLM
  servers, shows model context metadata in the model picker when available, and
  adds visible 128K presets instead of forcing every long-context choice back to
  65K.
- **Claude Code capability and ultracode guards**: workflow/ultracode launch
  options now use explicit model capability metadata. Claude family IDs exposed
  through routed gateways can infer supported capabilities, while unverified
  OpenCode/DeepSeek/local IDs no longer advertise `xhigh_effort` unless the user
  sets a provider capability override.
- **Advisor routing hardening**: routed sessions strip Claude Code's autonomous
  server-side advisor tool from normal turns so `/advisor` remains an explicit
  user action. Advisor model aliases are resolved through the selected provider,
  preventing routed advisor requests from sending Claude Any alias names as raw
  upstream model IDs.
- **Upstream request identity and install diagnostics**: routed provider calls
  send a Claude Code oriented user-agent header by default, and startup now warns
  when another `claude-any` executable shadows the active npm install. Self
  updates target the npm prefix that owns the running executable instead of a
  different global install.
- **External channel summary cleanup**: AI-Net-style channel digest summaries are
  kept as local status notices and simplified to point users back to the MCP
  system for details. Internal `tool_result`, background-summary, and
  no-reply markers are suppressed from outbound external-channel messages.
- **Provider API-key round-robin**: routed providers now support multiple stored
  API keys per provider (`api_keys`) while preserving the existing single
  `api_key` config. `--ca-api-keys`, `--ca-api-keys-env`,
  `--ca-set-api-keys`, and `set-api-keys` configure comma-, semicolon-, or
  newline-separated key lists. Upstream provider requests rotate through the
  keys in-process, which is useful for high-token ultracode sessions that need
  quota/rate distribution across keys. Compatibility tests now probe every
  configured key independently before the normal text/tool/tool-result checks.
  API-key status lines include the masked primary key and a short SHA-256
  fingerprint, and single-key entry/clipboard/env paths auto-detect multiple
  pasted keys to avoid silently overwriting a round-robin set.
- **Rate-limit error surfacing**: routed upstream 429 responses with a
  `Retry-After` longer than the current request timeout now fail fast and report
  the provider's real error type/message plus `Retry-After`, instead of sleeping
  until Claude Code surfaces the situation as a generic timeout.
- **Compatibility-test rate-limit diagnostics**: compatibility-test requests now
  mark themselves for the local router, and router-backed OpenAI-compatible
  paths skip rate-limit retry sleeps for those probes. A provider-side 429 should
  show as the provider's rate-limit error instead of leaving the menu stuck and
  later reporting a generic timeout.
- **Claude native model registry refresh**: Anthropic native model refresh now
  prefers the official Claude model documentation before falling back to API
  model-list endpoints, stores the refreshed list in a provider-scoped
  `model-registry.json`, and records per-model recommended presets plus
  conservative CLI parameters separately from provider hard limits and runtime
  hints. The refreshed registry includes the May 28 Claude Code / Claude model
  update: Claude Code `2.1.154`, Claude Opus 4.8 (`claude-opus-4-8`), Opus 4.8
  1M context metadata, the current Opus 4.8 128K output limit, Claude Code's
  default `high` effort, `xhigh` support, adaptive thinking, and fast-mode
  availability.
- **Session web chat file transfer**: `/ca/web/chat` now supports browser file
  attachments through `/ca/channel/files`, stores uploads in the local chat file
  store, and includes downloadable router URLs in the active session message.
  The built-in `claude-any-router` MCP server also exposes `send_file`, so
  Claude Code can send local files or inline content back to the same browser
  session without leaving the active Claude Code tool/MCP context.
- **OpenCode Zen and Go providers**: added first-class `opencode` and
  `opencode-go` providers for `https://opencode.ai/zen` and
  `https://opencode.ai/zen/go`. The model picker reads the live `/v1/models`
  catalog for each plan; Anthropic-compatible OpenCode models are routed
  through `/v1/messages`, and chat-compatible OpenCode models are routed
  through `/v1/chat/completions`. Zen models that require provider-specific
  Responses or Gemini endpoints are listed with metadata but are not routed yet.
  Because OpenCode's model catalog currently returns IDs without endpoint or
  AI SDK package metadata, Claude Any displays the inferred endpoint family in
  the model picker, prefers Anthropic-compatible `/v1/messages` for unknown
  OpenCode model IDs, and supports per-model overrides with
  `claude-anyctl provider-options opencode-go endpoint:<model-id>=messages|chat|responses|gemini`
  or the headless
  `--ca-provider-option endpoint:<model-id>=messages|chat|responses|gemini`
  flag.

### 0.1.101

- **DeepSeek.com Claude Code auth hotfix**: routed DeepSeek launches now pass
  the configured DeepSeek API key through `ANTHROPIC_AUTH_TOKEN` while leaving
  `ANTHROPIC_API_KEY` unset, matching DeepSeek's Claude Code integration path
  and avoiding Claude Code governor 401 failures after a successful
  `claude-any test`.

### 0.1.100

- **DeepSeek.com provider**: added a first-class `deepseek` provider for
  `https://api.deepseek.com/anthropic`, including aliases, defaults, model
  presets, and launch-time API-key guidance.
- **No API-key menu dead end**: when a provider launch is blocked by a missing
  key, the launcher opens the API-key menu path instead of forcing the user to
  restart navigation manually.
- **Nightly publish reliability**: nightly versions now include seconds and
  the short commit SHA so repeated same-minute pushes produce installable npm
  artifacts.
- **Router cleanup and shared-host isolation**: claude-any clears stale
  same-user router processes before spawning, uses `/proc`/port fallbacks on
  Linux, and defaults routed providers to a stable per-user port instead of a
  single global `8799`.
- **Channel delivery simplification**: non-native routed sessions use the LLM
  channel path instead of asking users to pick between native/SSE/stdio channel
  modes in the launch menu.
- **AI-Net/SSE direct handling without hidden `-p`**: channel notifications
  trigger immediate router-owned LLM handling, execute MCP tools over the
  initialized SSE connection, feed `tool_result` blocks back to the same LLM
  conversation, queue visible summaries for the next routed request, and keep
  best-effort terminal notices as diagnostics.
- **RPM limits default off**: hosted/local router providers now default to
  `rate_limit_rpm=0` and `rate_limit_status=off`; existing old default 40 RPM
  configs are migrated to off unless the user selected a non-default value.

### 0.1.71

- **MCP SSE channel initialization**: the channel bridge now handles MCP
  `endpoint` events by sending `initialize` and `notifications/initialized`,
  so AI-Net style push notifications can start flowing into Claude Any.
- **Channel SSE diagnostics**: connector status now reports the MCP endpoint,
  initialization state, and last MCP initialization error.

### 0.1.70

- **Linux menu debug log fix**: key-debug logging now writes under the user's
  Claude Any config directory instead of global `/tmp`, avoiding permission
  crashes on locked-down Linux systems.
- **Best-effort key logging**: menu input no longer fails if the optional
  key-debug log cannot be written.

### 0.1.69

- **Realtime channel bridge**: added `/ca/channel/messages`, `/ca/channel/wait`,
  `/ca/channel/stream`, `/ca/channel/notify`, and runtime SSE connector controls
  so external systems can deliver live messages into Claude Any.
- **`/channel` slash command**: Claude Code can inspect bridge status, poll,
  wait, send messages, and check SSE connector state without leaving the session.
- **Advisor and coordination parity**: Advisor feedback is summarized back into
  the visible transcript/executor flow, while channel and Cron-compatible tool
  schemas make third-party model sessions behave closer to native Claude Code.

### 0.1.68

- **Tabbed router management page**: the router root page now has top-menu
  sections for Overview, LLM Settings, Events, and Endpoints, keeping remote
  management usable as more controls are added.
- **Safe `/router-debug` toggle**: external router exposure is off by default,
  requires an explicit confirmed setting, can be toggled inside Claude Code
  with `/router-debug`, and automatically restarts the router so the bind
  address changes immediately.
- **Main-branch npm automation**: pushing or merging to `main` now triggers the
  npm publish workflow, but the workflow first checks whether the package
  version already exists on npm and skips duplicate publishes.

### 0.1.67

- **Fast prelaunch navigation**: arrow-key redraws no longer call the router
  `/health` endpoint just to render the `mode:` label, avoiding per-keystroke
  delays when the router is stopped or slow.
- **Lower-latency paste handling**: portable raw input prompts drain pasted
  bursts and flush once per batch instead of once per character.

### 0.1.66

- **TUI input fix for tmux/zsh**: portable menu prompts now handle visible text,
  paste, Backspace/Delete, and Ctrl-U directly in raw terminal mode instead of
  depending on fragile terminal echo restoration.
- **Issue-linked release flow**: npm publishing can now be triggered
  automatically by pushing a `v*` tag, in addition to GitHub releases and manual
  workflow dispatch.

### 0.1.65

- **Plan Mode unchanged-Read loop recovery**: router conversion now preserves the
  previous successful `Read` result for unchanged/no-op reads, exposes the
  current Plan Mode state to third-party models, and avoids arbitrary retry
  thresholds.
- **Cleaner third-party transcripts**: attachment-only metadata, historical
  no-op tool results, and orphan tool results are normalized before reaching
  Ollama, Ollama Cloud, NVIDIA hosted, vLLM, or NIM.
- **Remote router test binding**: `CLAUDE_ANY_ROUTER_BIND_HOST=0.0.0.0` can be
  used for intentional remote testing while Claude Code keeps using the local
  client base URL.

### 0.1.64

- **Model-aware native auto-compact**: claude-any now injects
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` at launch using the selected provider/model
  context window, including the cached Ollama/Ollama Cloud model catalog. Smaller
  custom models now let Claude Code's native auto-compact trigger against their
  real context budget instead of falling back to Claude Code's generic 200K
  assumption.

### 0.1.63

- **Plan Mode stop guard**: when a non-Anthropic model is already in Plan Mode
  and stops after a short acknowledgement without a tool call, the Stop hook
  now returns structured JSON feedback so Claude Code continues with a
  plan-mode-safe tool instead of leaking text into the prompt box.
- **Guard-feedback filtering**: claude-any filters its own plan-guard marker
  from router history for all roles, preventing Stop hook recovery messages from
  being sent back to upstream models.
- **Safer retry budget**: the Stop guard retry counter now resets once a real
  tool call is attempted, while `SubagentStop` events are kept observational.

### 0.1.62

- **Ollama context catalog**: added `claude-any ollama-catalog`, which downloads
  Ollama's model list and library tag pages, strips suffixes such as `:cloud`
  and `:latest`, and caches per-model context windows under
  `~/.config/claude-any/ollama-model-catalog.json`.
- **Context-aware presets**: the pre-launch menu now uses the selected model's
  known context capacity to hide impossible presets and expose 1M-context
  presets only for models that can actually use them.
- **Native Claude Code compacting preserved**: removed the
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` override so Claude Code's own compact
  behavior stays in control instead of being capped too early by claude-any.
- **Live context/status accounting**: the statusline prefers Claude Code's
  current session context-window telemetry when available, while router mode
  continues to report upstream request tokens, retries, RPM usage, and errors.
- **Advisor and plan-mode hardening**: kept Advisor review support, stale
  `ExitPlanMode` recovery, queued-command handling, and broader Claude Code hook
  coverage for agent/task/team workflows on non-Anthropic providers.

### 0.1.50

- **Dynamic timeout help**: the LLM options panel now describes
  `request_timeout_ms` using the currently selected value instead of always
  showing a hard-coded timeout example.

### 0.1.49

- **Streaming buffer fix**: Ollama/OpenAI-compatible streams now flush any
  briefly held plan-detection text as soon as normal text streaming resumes,
  instead of replaying it at the end of the response.
- **Plan mode guard**: `ExitPlanMode` tool calls are dropped when Claude Code is
  no longer in plan mode, avoiding the “You are not in plan mode” dead end.

### 0.1.48

- **Unreachable model list fix**: when a provider model endpoint cannot be
  reached, the model picker no longer repopulates stale `current_model` or
  `custom_models` entries from config as if they came from the new endpoint.

### 0.1.47

- **Base URL model reset**: changing a provider Base URL now clears stale
  custom/current model entries and refreshes model caches, so the model picker
  cannot keep showing models from the previous endpoint.

### 0.1.46

- **Cleaner stream options**: the LLM options menu now hides `Stream word
  chunking` whenever `Stream` is off, since chunking only applies to streamed
  responses.

### 0.1.45

- **Interactive npm self-update check**: npm-installed `claude-any` now checks
  the npm registry before launch. If a newer version exists, it asks whether to
  run `npm update -g @oneciel-ai/claude-any`, then restarts into the updated
  version. Non-interactive/headless runs are not interrupted.

### 0.1.44

- **Statusline split**: turning Rate Limit status off now hides only RPM,
  server-limit, and wait counters. Upstream progress, retry, error, and token
  diagnostics remain visible.

### 0.1.43

- **429 backoff retry**: upstream `429 Too Many Requests` responses are now
  handled as retry/backoff events across all retry attempts instead of leaking
  the raw upstream error after the first backoff.

### 0.1.42

- **Live stream progress**: the statusline now updates streamed upstream output
  progress with formatted input/output token estimates and chunk counts.

### 0.1.41

- **Statusline formatting**: upstream token counts now use thousands separators
  and a space before `tok`, for example `27,501 tok`.

### 0.1.40

- **RPM 0 is preserved**: setting `rate_limit_rpm=0` now stores an explicit
  unmanaged router mode instead of falling back to the provider default.
  Claude Any still shows recent 60-second request usage when enabled, but it
  does not claim the upstream provider is unlimited.

### 0.1.39

- **Menu input fixes**: restores terminal line/echo mode before text or number
  prompts, so typed numeric values are visible in the prelaunch UI.
- **Safer numeric validation**: invalid numeric option input now shows an
  inline message instead of crashing the menu.
- **Preset visibility**: applied presets report the effective context, reserve,
  output, and timeout values.

### 0.1.38

- **User-selected context windows**: removes the NVIDIA hosted 32K safety cap.
  The router now uses the context window selected in LLM options or headless
  configuration, with model-aware fallback only when no value is configured.
- **NVIDIA presets updated**: NVIDIA hosted presets now start at 65K and scale
  up to 256K for large-output/reasoning workflows.

### 0.1.37

- **Pseudo tool-call recovery**: the NVIDIA/OpenAI-compatible stream path now
  suppresses `<|tool_calls_section_begin|>...` pseudo tool-call text and
  converts it back into Claude `tool_use` blocks when possible.
- **Streaming defaults**: provider streaming defaults to on; NVIDIA hosted
  remains forced to the streaming upstream path for stability.

### 0.1.36

- **NVIDIA upstream streaming**: NVIDIA hosted router calls now use upstream
  `stream=true`, so long responses can flow as chunks instead of waiting for a
  full non-streaming completion.
- **Stream retry diagnostics**: streamed NVIDIA calls keep the same retry and
  request-size activity status used by the statusline.

### 0.1.35

- **NVIDIA router context guard**: NVIDIA hosted now defaults to a 32K router
  context window and LLM presets may tune that cap, reducing timeout-prone
  payload growth in long Claude Code sessions.
- **Upstream activity status**: the router records current request, retry,
  success, and error state with estimated token/byte size so the statusline can
  distinguish active upstream waits from idle sessions.

### 0.1.34

- **Complete headless configuration path**: add `--ca-env-file`,
  environment-variable mapping, Advisor model, rate-limit, streaming, language,
  and web-fetch headless controls.
- **Documented override order**: saved menu choices < OS environment <
  `.env` file < CLI parameters < final interactive menu choice via `--ca-menu`.

### 0.1.33

- **Logo branding in every README**: add the Claude Any logo at the top of the
  English, Korean, Japanese, and Chinese README files.
- **npm image assets included**: package `logo.png`, `logo-small.png`, and
  `claude-any-adv.png` so the npm README renders the same branding as GitHub.

### 0.1.32

- **NVIDIA preset menu fix**: LLM presets no longer try to apply the unsupported
  `native` option for NVIDIA hosted, so selecting Long context / Large output
  presets stays inside the menu instead of exiting.

### 0.1.31

- **2-minute default upstream timeout**: existing saved longer bundled defaults are migrated to 120000 ms so gateway stalls fail faster.
- **Localized gateway retries**: 502/503/504 and socket timeout responses are
  retried automatically, with retry progress shown in the selected UI language.

### 0.1.30

- **Headless launch docs moved up**: README now shows copy-ready examples for
  launching Claude Code directly with `--ca-provider`, `--ca-model`, `-p`, and
  `CLAUDE_ANY_SKIP_MENU=1` immediately after install.
- **NVIDIA hosted wording cleanup**: provider and lifecycle docs now describe
  NVIDIA hosted as using the Claude Any local router, with no separate hosted
  API Catalog proxy requirement.

### 0.1.29

- **NVIDIA compatibility test fix**: `claude-any test` now restarts the local
  router before router-mode tests, so upgraded installs do not accidentally use
  an old long-running router that still expects `nvd-claude-proxy`.
- **Clear NVIDIA router wording**: menu status now describes NVIDIA hosted as
  using the local claude-any router instead of the retired local proxy path.

### 0.1.28

- **Plan Mode + Advisor headline**: document Claude Any's Plan Mode support for
  router-backed non-Anthropic providers and the `/advisor` slash command backed
  by a selected long-context Advisor Model.
- **Status-line RPM telemetry**: Claude Any can show router RPM usage and the
  latest wait time in the bottom status area when `rate_limit_status=on`,
  keeping rate-limit telemetry out of the chat transcript.
- **Soft RPM pacing for free hosted models**: NVIDIA hosted, self-hosted NIM,
  Ollama, and Ollama Cloud can use router-side RPM pacing. The pacing subtracts
  time already spent in file reads, command execution, and tool-result waits, so
  normal coding tool-call gaps naturally absorb much of the RPM spacing.
- **Unlimited usage display**: `rate_limit_rpm=0` disables throttling; enable
  `rate_limit_status=on` only when you want the last-60-seconds request rate.

### 0.1.27

- **Plan mode support for non-Anthropic providers**: the router now keeps
  `EnterPlanMode` available and supports Claude Code Plan mode even when the
  upstream model does not reliably choose that internal tool. Forced
  `tool_choice=EnterPlanMode` is answered locally with a valid Anthropic
  `tool_use`, and long implementation requests that receive only a short or
  empty non-actionable text response are promoted to `EnterPlanMode` using
  language-agnostic structure checks.
- **Plan-mode self-tool handling**: unsupported Claude Code self-tools are
  still stripped for non-Anthropic providers, but Plan-mode tools are handled
  separately so planning can work instead of being disabled.

### 0.1.25

- **Plan-mode diagnostics**: set `~/.config/claude-any/log-level` to `TRACE`
  to capture redacted request and response summaries in `requests.jsonl` /
  `responses.jsonl`.
- **Headless agent chat service**: the router exposes a small HTTP control
  plane for sub coding agents. Agents can post messages, poll updates after
  the last seen message id, or wait on an SSE stream when they do not have
  their own loop.
- **Plan artifact serving**: agents can create plan files through the router
  and share stable local URLs, matching Claude Code's file/artifact-oriented
  Plan-mode workflow without copying Anthropic's internal implementation.

### 0.1.24

- **First public npm release** under the correct scope: `@oneciel-ai/claude-any`. Earlier 0.1.x versions were never published to the registry; this is the version that is actually installable via `npm install -g @oneciel-ai/claude-any`.

### 0.1.23

- **Stream toggle**: each non-Anthropic provider now has a `stream_enabled`
  knob in the LLM options menu, in `claude-anyctl ollama-options` /
  `provider-options`, and in headless flags. When off, the router forces
  `stream:false` upstream and returns the full response to Claude Code — a
  workaround when streaming fragmentation breaks tool-call or JSON parsing.
- **Word-boundary streaming**: new `stream_word_chunking` option buffers SSE
  text deltas to whitespace/word boundaries before flushing. Implemented for
  both the Ollama router path and the native pass-through path (vLLM, NVIDIA
  hosted, self-hosted NIM). Tool deltas and non-text SSE events pass through
  unchanged.
- **All-hooks tool guard**: `install_tool_guard_hooks` now registers the full
  set of Claude Code hook events (PreToolUse, PostToolUse, PostToolUseFailure,
  PostToolBatch, PermissionRequest, PermissionDenied, SessionStart/End, Setup,
  UserPromptSubmit/Expansion, Stop, StopFailure, InstructionsLoaded,
  ConfigChange, CwdChanged, Notification, SubagentStart/Stop, TeammateIdle,
  TaskCreated, TaskCompleted, PreCompact, PostCompact, WorktreeCreate,
  WorktreeRemove, Elicitation, ElicitationResult). The WorktreeCreate handler
  emits `worktreePath = base_path` so Agent isolation works in non-git
  directories.
- **Windows hook compatibility**: `shell_command_string` now emits forward
  slashes and POSIX quoting on Windows so Claude Code's sh-based hook runner
  doesn't strip backslashes from paths like `C:\Users\...`.
- **LLM options UX**: per-row description footer rendered in the user's
  selected language, and boolean toggles (`Stream`, `Stream word chunking`,
  `Native compatibility`, `Think`) flip on Enter without a prompt.

### 0.1.22

- **Headless manual expansion**: expand the manual with practical headless setup, launch, testing, passthrough, and cleanup examples for automation and remote-server use.

### 0.1.21

- **Service lifecycle documentation**: clarify that Claude Any starts only the router/proxy services required for the selected provider at launch time, and `claude-any stop` is the explicit cleanup command.

### 0.1.20

- **NVIDIA hosted quick test**: `auto` mode now uses a text-only quick test for NVIDIA hosted providers, avoiding slow or flaky tool_use requests during menu checks. Use `smoke` for text + tool_use, or `full` for the full text/tool_use/tool_result round trip.
- **Menu test timeout**: the terminal menu now runs `claude-any test 60 auto`, which keeps the pre-launch test responsive for hosted models.

### 0.1.19

- **Faster compatibility tests**: `claude-any test` now supports `auto`, `smoke`, and `full` modes.
- **Menu default speedup**: the terminal menu runs `claude-any test 120 auto`, so NVIDIA hosted compatibility checks finish faster while full validation remains available with `claude-any test 180 full`.

### 0.1.18

- **NVIDIA hosted transient diagnostics**: compatibility tests now identify `RemoteDisconnected`, connection resets, and 502/503/504 responses from NVIDIA hosted backends as transient upstream/API Catalog failures.
- **NVIDIA proxy cleanup**: `claude-any stop` now also matches `nvd-claude-proxy` executable processes so stale proxy sessions are cleaned up reliably.

### 0.1.17

- **Menu compatibility-test timeout**: the terminal menu now runs compatibility tests with an explicit 180 s timeout and stops the child process if it exceeds the menu hard limit, so slow hosted models cannot leave the menu appearing indefinitely pending.

### 0.1.16

- **NVIDIA hosted proxy startup fix**: detect and launch an installed `nvd-claude-proxy`/`ncp` executable before falling back to `python -m nvd_claude_proxy.main`. This supports uv-tool installs where the proxy is available as a command but not importable from Claude Any's Python interpreter.

### 0.1.15

- **Ollama/Ollama Cloud tool-call streaming fix**: emit streamed tool calls using sequential Anthropic SSE content block indexes and `input_json_delta` payloads. This prevents Claude Code from rejecting malformed streamed tool-use blocks with `Invalid tool parameters`.
- **Tool guard auto-install**: non-Anthropic launches now merge the Claude Any tool guard into `~/.claude/settings.json` so generated tool inputs can be normalized before execution.
- **Tool-call diagnostics**: router-side tool calls are logged to `~/.config/claude-any/tool-calls.jsonl`, and Claude Code hook inputs are logged to `~/.claude/claude-any-tool-guard/tool-events.jsonl` for precise debugging.
- **Tool input normalization**: the guard now maps common aliases such as `path` to `file_path`, `cmd` to `command`, and `query` to `pattern`, and returns explicit guidance when required fields are missing.

### 0.1.14

- **SSH/terminal arrow-key compatibility**: rewrote `read_menu_key()` with a proper ANSI escape sequence parser and moved raw terminal setup into `portable_select()` so the terminal stays in raw mode for the entire menu loop. This prevents escape sequences from leaking to the screen when `ECHO` is restored between keystrokes. Arrow keys, Home, and End now work reliably in SSH sessions.
- **Test timeout**: default compatibility test timeout increased from 60 s to 120 s for slower cloud providers.
- **Ollama Cloud compatibility test fix**: added `"stream": false` to compatibility test requests so the router fetches a single JSON response from Ollama Cloud instead of SSE streaming, which was causing `post_json` to timeout while collecting all chunks.

### 0.1.13

- **Ollama streaming proxy**: The router now streams Ollama and Ollama Cloud
  responses through to Claude Code in real time using Anthropic SSE format,
  instead of buffering the entire response before delivery.
- **Config caching**: `load_config()` now caches the configuration file in
  memory and only re-reads from disk when the file modification time changes.
  This eliminates repeated file I/O and JSON parsing on every router request.
- **Token estimation caching**: `estimate_tokens()` now accepts an optional
  cache dict to avoid redundant `json.dumps()` calls within a single request.
  `ollama_chat_request` and `cap_output_tokens_for_context` share the same
  cache when computing context window sizing.

### 0.1.12

- Refresh docs and demo assets.

### 0.1.11

- Validate tool call compatibility.

### 0.1.10

- Show runtime context in tests.

### 0.1.9

- Cap presets to server context.

### 0.1.8

- Localize LLM presets.

## Provider Notes

| Provider | Mode | Notes |
| --- | --- | --- |
| Anthropic | Native Claude Code by default, optional router | Uses Claude login or Anthropic API key in direct native mode. The model picker uses `/v1/models` with an API key and falls back to Anthropic's public Models overview for direct Claude Native sessions without one. Enable `route_through_router` when you explicitly want Anthropic requests to pass through the Claude Any router; routed mode requires an Anthropic API key. |
| Ollama | Native when available, router otherwise | Local Ollama normally needs no API key. Cloud models through local Ollama require `ollama signin` on the Ollama host. |
| Ollama Cloud | Router | Calls `https://ollama.com/api`; requires an Ollama API key. |
| DeepSeek.com | Router | Calls `https://api.deepseek.com/anthropic`; requires a DeepSeek API key. Claude Any passes that key as `ANTHROPIC_AUTH_TOKEN` and keeps `ANTHROPIC_API_KEY` unset to avoid Claude Code auth conflicts. |
| OpenCode Zen | Router | Calls `https://opencode.ai/zen`; requires an OpenCode Zen API key. The model picker reads `/v1/models`; Claude/Qwen Zen models use `/v1/messages`, documented chat-compatible Zen models use `/v1/chat/completions`, and unknown model IDs default to `/v1/messages` unless overridden. |
| OpenCode Go | Router | Calls `https://opencode.ai/zen/go`; requires an OpenCode Go API key. The model picker reads `/v1/models`; Qwen/MiniMax Go models use `/v1/messages`, documented GLM/Kimi/DeepSeek/MiMo Go models use `/v1/chat/completions`, and unknown model IDs default to `/v1/messages` unless overridden. |
| Kimi.com | Router | Calls `https://api.kimi.com/coding`; requires a Kimi Code API key. The model picker reads `/v1/models`; `kimi-for-coding` is treated as a 256K-context, 32K-output Anthropic-compatible coding model with thinking preserved. |
| vLLM | Native Anthropic-compatible endpoint | Use a vLLM endpoint that exposes Anthropic-compatible `/v1/messages`; match `--tool-call-parser` to the model family. |
| NVIDIA hosted | Router | Uses the NVIDIA hosted API Catalog through the Claude Any local router. |
| self-hosted NIM | Native Anthropic-compatible endpoint | Use the self-hosted NIM Anthropic-compatible endpoint. |

## Service Lifecycle

Claude Any does not keep every possible backend helper running all the time. The
normal lifecycle is:

- Before launch, managed router processes can be stopped with
  `claude-any stop`.
- When `claude-any` starts Claude Code, it starts only the services required by
  the selected provider.
- Routed providers use the Claude Any router on a stable per-user local port.
  `CLAUDE_ANY_ROUTER_PORT` wins when set; otherwise POSIX systems default to
  `8799 + (uid % 1000)`. This prevents users on the same host from accidentally
  sharing one stale router.
- Ollama Cloud, DeepSeek.com, NVIDIA hosted, and other router-backed providers
  use that local router; hosted API Catalog models do not require a separate
  NVIDIA proxy.
- Run `claude-any stop` before a fresh provider-switch test if an old router is
  still bound to the local port. Current launches also try to clear stale
  same-user router processes automatically.

### Channel Automation Note

Routed, non-Claude-Native sessions deliver external channel messages through
the LLM channel path. The 0.1.100 implementation can process AI-Net/SSE
notifications automatically and can call MCP tools while doing so. Direct
channel handling currently surfaces summaries through best-effort terminal
notices and follow-up context; a future nightly must avoid spawning an internal
`claude -p` process for automatic channel handling so background notifications
do not create a separate Claude Code billing path. User-initiated `-p`
commands remain ordinary Claude Code pass-through arguments.

This keeps Claude Code pointed at one stable Claude Any entry point while still
letting provider-specific helpers start on demand.

For Qwen3-Coder on vLLM, start the server with a matching tool parser:

```sh
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3-coder-30b \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

## Provider Links

- Ollama Cloud: [cloud overview](https://ollama.com/cloud), [API key settings](https://ollama.com/settings/keys), [authentication docs](https://docs.ollama.com/api/authentication).
- Ollama local Anthropic compatibility: [Ollama Anthropic API docs](https://docs.ollama.com/api/anthropic-compatibility).
- OpenCode Zen: [Zen docs](https://opencode.ai/docs/ko/zen), [model catalog](https://opencode.ai/zen/v1/models).
- OpenCode Go: [Go docs](https://opencode.ai/docs/ko/go/), [model catalog](https://opencode.ai/zen/go/v1/models).
- Kimi.com Code: [Claude Code integration](https://www.kimi.com/code/docs/third-party-tools/other-coding-agents.html), [Kimi Code config](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/config-files.html).
- vLLM: [Claude Code integration](https://docs.vllm.ai/en/latest/serving/integrations/claude_code/), [tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/), [project GitHub](https://github.com/vllm-project/vllm).
- NVIDIA hosted NIM: [NVIDIA API Catalog](https://build.nvidia.com/), [API Catalog quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart).
- Self-hosted NVIDIA NIM: [Claude Code with NIM](https://docs.nvidia.com/nim/large-language-models/latest/ai-assistant-integrations/claude-code.html), [NIM for LLMs getting started](https://docs.nvidia.com/nim/large-language-models/1.14.0/getting-started.html), [NGC personal keys](https://org.ngc.nvidia.com/setup/personal-keys).
- Cloudflare MCP for user-managed external access: [Cloudflare API MCP](https://github.com/cloudflare/mcp), [Cloudflare MCP servers](https://developers.cloudflare.com/agents/model-context-protocol/mcp-servers-for-cloudflare/), [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/setup/).

## Headless Examples

Headless commands skip the pre-launch menu and launch Claude Code immediately.
Claude Any consumes `--ca-*` setup flags, starts the required router
services, then passes the remaining arguments to Claude Code.

```sh
claude-any --ca-provider ollama-cloud --ca-model glm-5.1
claude-any --ca-provider ollama --ca-base-url http://127.0.0.1:11434 --ca-model qwen3-coder
claude-any --ca-provider ollama-cloud --ca-api-key-env OLLAMA_API_KEY --ca-model qwen3-coder:480b:cloud
claude-any --ca-provider vllm --ca-base-url http://127.0.0.1:8000 --ca-model Qwen/Qwen3-Coder
claude-any --ca-no-update-check -p "Reply with OK only." --output-format text
```

All other arguments are passed through to Claude Code.

## Headless Agent Chat

When the claude-any router is running, sub agents can coordinate through local
HTTP endpoints without opening the menu:

```sh
# Send a message to a channel.
curl -s http://127.0.0.1:8799/ca/chat/messages \
  -H 'content-type: application/json' \
  -d '{"channel":"agents","sender_id":"codex","recipients":["kimi"],"message":"Need logs after id 42"}'

# Poll updates after the last message id.
curl -s 'http://127.0.0.1:8799/ca/chat/messages?channel=agents&recipient=kimi&after=42'

# Wait on a stream until messages arrive.
curl -N 'http://127.0.0.1:8799/ca/chat/stream?channel=agents&recipient=kimi&after=42&timeout=300'

# Publish a plan file and get a served URL.
curl -s http://127.0.0.1:8799/ca/plan/artifacts \
  -H 'content-type: application/json' \
  -d '{"title":"handoff","name":"handoff.md","content":"# Plan\n- step 1"}'
```

## Local Browser Chat

When the Claude Any router is running, open:

```text
http://127.0.0.1:8799/ca/web/chat
```

The page is a local, Teams-style chat surface that posts browser messages into
`/ca/channel/messages`; the active Claude Code session consumes those messages
through the Claude Any channel bridge with its normal tools and MCP servers.
The composer also supports file attachments. Files are uploaded to
`/ca/channel/files`, stored under the local chat file store, and included in
the web-chat message as downloadable router URLs so the active session can fetch
or inspect them with its usual tools. The reverse direction is available through
the built-in `claude-any-router` MCP server: Claude Code can call `send_file`
with a local `path` or inline `content`, and the router publishes the stored
file back to the browser session as a web-visible attachment.

The page does not create tunnels, public DNS names, Cloudflare zones, or
Tailscale routes. If the selected provider is Anthropic and you want this page
or other router features to handle Anthropic traffic, enable the Anthropic
`route_through_router` LLM option and set an Anthropic API key.

## External Web Access

Claude Any intentionally keeps external network publishing outside the core
launcher. The built-in router and web chat surface bind to a local per-user
port by default, so multiple Claude Any instances on one host do not fight over
public DNS names, tunnels, or tailnet policy.

If you want browser access from outside the machine, use a user-managed reverse
proxy or tunnel in front of the local Claude Any web/chat port. Cloudflare is
the preferred documented path because it can be configured outside Claude Any
without giving the launcher long-lived zone-wide credentials.

Recommended Cloudflare MCP-assisted flow:

1. Start Claude Any locally and note the web/chat URL or router base printed by
   `claude-any status`.
2. Connect an MCP client to Cloudflare's official API MCP server:
   `https://mcp.cloudflare.com/mcp`.
3. Authorize Cloudflare with only the account/zone permissions you are willing
   to grant.
4. Ask the MCP client to create or update a Cloudflare Tunnel/public hostname
   that forwards to the local Claude Any service.
5. Keep the hostname unique per Claude Any instance and avoid overwriting
   existing DNS or tunnel routes.

Claude Any does not create Cloudflare tunnels automatically today, and Tailscale
Funnel/Serve automation is intentionally not included. Users who prefer
Tailscale, nginx, Caddy, SSH forwarding, or another gateway can still place that
tool in front of the local web/chat port themselves.

## Security

Do not commit runtime configuration or API keys. Claude Any stores local runtime
configuration under `~/.config/claude-any/`. NVIDIA hosted credentials used by
the optional proxy are stored under `~/.config/nvd-claude-proxy/`.

This repository should contain source, documentation, and demo assets only.

## Development

```sh
python -m py_compile claude_any.py claude-any-menu.py claude-any-tool-guard.py
python -m ruff check .
python scripts/make_demo_assets.py
```

## License

MIT. See [LICENSE](LICENSE).
