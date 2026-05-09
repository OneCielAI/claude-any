# Claude Any Manual

Claude Any is a pre-launch configuration layer for Claude Code. It lets you
choose a provider, model, base URL, API key, and provider options before Claude
Code starts, while passing normal Claude Code arguments through unchanged.

Credits: One Ciel LLC

Current version: `0.1.7`

## Install

Requirements:

- Python 3.10+
- Claude Code installed as `claude`
- Node/npm only if you enable optional MCP web tooling

Current install from GitHub:

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

Source install:

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

Registry install, after the first npm publish:

```sh
npm install -g @onecielai/claude-any
claude-any
```

Upgrade:

```sh
# GitHub install, current recommended path
npm install -g https://github.com/OneCielAI/claude-any.git --force
claude-any version
```

To make `npm update -g @onecielai/claude-any` work, the package must be
published to the public npm registry under the same package name:

```sh
npm login
npm publish --access public
npm install -g @onecielai/claude-any
npm update -g @onecielai/claude-any
```

For automated publishing, create an npm automation token, save it as the
repository secret `NPM_TOKEN`, then publish a GitHub Release or run the
`Publish to npm` workflow manually.

Versioning uses SemVer. For future releases, bump `version` in `package.json`,
create a matching Git tag such as `v0.1.1`, and publish a GitHub Release to
trigger the npm publish workflow. After registry publication, the normal
registry upgrade command will be:

```sh
npm update -g @onecielai/claude-any
```


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
- Compatibility test: makes a small request before launching Claude Code.
- Launch Claude Code: starts Claude Code with the selected configuration.

The lower status area shows connection checks, API-key state, provider notes,
and compatibility-test results.

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

Links:

- vLLM Claude Code integration: https://docs.vllm.ai/en/latest/serving/integrations/claude_code/
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

Examples:

```sh
claude-any --ca-provider ollama --ca-base-url http://127.0.0.1:11434 --ca-model qwen3-coder
claude-any --ca-provider ollama-cloud --ca-api-key-env OLLAMA_API_KEY --ca-model qwen3-coder:480b:cloud
claude-any --ca-provider vllm --ca-base-url http://127.0.0.1:8000 --ca-model my-model
claude-any --ca-max-output-tokens 4096 -p "Reply with OK only." --output-format text
```

Common Claude Any flags:

- `--ca-provider`
- `--ca-model`
- `--ca-base-url`
- `--ca-api-key`
- `--ca-api-key-env`
- `--ca-max-output-tokens`
- `--ca-timeout-ms`
- `--ca-ollama-option`
- `--ca-no-update-check`

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

## Troubleshooting

- If the first request says a model does not exist, re-open the menu and select
  a model that the current provider actually serves.
- If Ollama Cloud returns authentication errors, check `OLLAMA_API_KEY` or use
  the API key menu.
- If local Ollama cloud models fail, run `ollama signin` on the Ollama host.
- If vLLM or NIM returns model `404`, map Claude Code's model aliases to the
  served model name or select the custom model entry.
- If tool calls fail, verify that the selected model supports tool use.
- If Claude Code update checks fail due to disk space, clean local caches or
  skip the check with `--ca-no-update-check`.

## Security Checklist

- Do not commit `~/.config/claude-any/`.
- Do not commit API keys, tokens, screenshots containing secrets, or router logs.
- Prefer environment variables for keys in automation.
- Revoke and rotate any key that was pasted into chat, logs, or issue reports.
