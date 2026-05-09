# Claude Any

| English | [한국어](docs/README.ko.md) | [日本語](docs/README.ja.md) | [中文](docs/README.zh.md) |
| --- | --- | --- | --- |

Claude Any is a provider selector and compatibility launcher for Claude Code.
It lets you choose Anthropic, Ollama, Ollama Cloud, vLLM, NVIDIA hosted models,
or self-hosted NIM before Claude Code starts, then passes normal Claude Code
arguments through unchanged.

Credits: One Ciel LLC

Current version: `0.1.5`

## Why This Exists

Claude Any started from a practical need: even on the highest Claude Code plan,
long sessions can run out of available tokens or become blocked while waiting
for the next quota window. The goal is not to replace Claude Code, but to keep
work moving. Slower but usable providers such as NVIDIA NIM, Ollama Cloud,
vLLM, and local Ollama can act as hybrid third-party agents for summaries,
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

Requirements:

- Python 3.10+
- Claude Code installed and available as `claude`
- Node/npm only if you enable MCP web tooling

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


![Claude Any menu](docs/assets/claude-any-main.en.png)

## Demo

![Claude Any demo](docs/assets/claude-any-demo.en.gif)

See the [full manual](docs/manual.md) for provider setup, headless flags, and
troubleshooting. A downloadable demo video is available at
[docs/assets/claude-any-demo.mp4](docs/assets/claude-any-demo.mp4).

## Development Story

Claude Any was built through real integration tests: provider switching, model
discovery, API-key entry, compatibility tests, web-search tooling, timeout
handling, and native Claude Code behavior. The main lesson was that
Anthropic-compatible Messages endpoints are the cleanest integration path when a
provider supports them. Ollama, vLLM, and NIM can expose Anthropic-compatible
routes that preserve more of Claude Code's tooling model than a generic
OpenAI-compatible chat route.

Local inference was also tested with Qwen 3.6 27B Q4 through Ollama and vLLM on
RTX 5090 and MSI GB10-class hardware. It worked, but the speed should not be
judged against native Claude Code or Codex. In practice, some hosted/cloud
choices such as NVIDIA NIM and Ollama Cloud felt more useful for this hybrid
workflow than expected.

OpenAI-compatible endpoints were deliberately kept out of the primary path for
Claude Code use. In testing, tool-call translation through generic OpenAI chat
compatibility was more brittle around tool parameters, tool results, repeated
calls, retries, and model selection.

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
- Compatibility test before launch.
- Console-first pre-launch menu for SSH and terminal workflows.
- Native paths where providers expose Claude/Anthropic-compatible endpoints.
- Router mode for providers that need request/response adaptation.
- DuckDuckGo and fetch MCP wiring for non-native providers.
- Headless setup flags such as `--ca-provider`, `--ca-model`, `--ca-base-url`,
  `--ca-api-key-env`, `--ca-ollama-option`, and `--ca-max-output-tokens`.

## Provider Notes

| Provider | Mode | Notes |
| --- | --- | --- |
| Anthropic | Native Claude Code | Uses Claude login or Anthropic API key. |
| Ollama | Native when available, router otherwise | Local Ollama normally needs no API key. Cloud models through local Ollama require `ollama signin` on the Ollama host. |
| Ollama Cloud | Router | Calls `https://ollama.com/api`; requires an Ollama API key. |
| vLLM | Native Anthropic-compatible endpoint | Use a vLLM endpoint that exposes Anthropic-compatible `/v1/messages`. |
| NVIDIA hosted | Router/proxy | Uses NVIDIA hosted API through the compatibility path. |
| self-hosted NIM | Native Anthropic-compatible endpoint | Use the self-hosted NIM Anthropic-compatible endpoint. |

## Provider Links

- Ollama Cloud: [cloud overview](https://ollama.com/cloud), [API key settings](https://ollama.com/settings/keys), [authentication docs](https://docs.ollama.com/api/authentication).
- Ollama local Anthropic compatibility: [Ollama Anthropic API docs](https://docs.ollama.com/api/anthropic-compatibility).
- vLLM: [Claude Code integration](https://docs.vllm.ai/en/latest/serving/integrations/claude_code/), [project GitHub](https://github.com/vllm-project/vllm).
- NVIDIA hosted NIM: [NVIDIA API Catalog](https://build.nvidia.com/), [API Catalog quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart).
- Self-hosted NVIDIA NIM: [Claude Code with NIM](https://docs.nvidia.com/nim/large-language-models/latest/ai-assistant-integrations/claude-code.html), [NIM for LLMs getting started](https://docs.nvidia.com/nim/large-language-models/1.14.0/getting-started.html), [NGC personal keys](https://org.ngc.nvidia.com/setup/personal-keys).

## Headless Examples

```sh
claude-any --ca-provider ollama --ca-base-url http://127.0.0.1:11434 --ca-model qwen3-coder
claude-any --ca-provider ollama-cloud --ca-api-key-env OLLAMA_API_KEY --ca-model qwen3-coder:480b:cloud
claude-any --ca-provider vllm --ca-base-url http://127.0.0.1:8000 --ca-model Qwen/Qwen3-Coder
claude-any --ca-no-update-check -p "Reply with OK only." --output-format text
```

All other arguments are passed through to Claude Code.

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
