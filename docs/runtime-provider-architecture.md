# Runtime and Provider Architecture

Claude Any currently implements Claude Code as the only runtime.  The codebase
should still be shaped so future Codex or Agy runtimes can be added without
threading new conditionals through provider, protocol, MCP, and channel code.

This document defines the maintenance boundaries used by
`claude_any_support.architecture`.

## Vocabulary

- **Runtime**: the local/interactive coding client being launched.
  - Current implementation: Claude Code.
  - Future placeholders: Codex, Agy.
- **Provider**: the upstream LLM service.
  - Examples: Anthropic, Ollama Cloud, vLLM, Kimi, OpenCode, OpenRouter,
    Fireworks.
- **Protocol**: the HTTP message format spoken to the provider.
  - Examples: Anthropic Messages, OpenAI Chat Completions, OpenAI Responses.
- **Tool dialect**: the tool names and schemas expected by a runtime.
  - Example: Claude Code tools such as `Bash`, `Read`, `Edit`, `TaskList`.
- **Channel bridge**: external event delivery into the active runtime session.

## Required Separation

Provider code must not know how to launch Claude Code.  Runtime code must not
know how a provider rotates keys or parses rate-limit headers.

Use these ownership rules:

- Runtime adapters own executable discovery, launch arguments, runtime-specific
  environment variables, status line integration, slash commands, and runtime
  MCP config paths.
- Provider adapters own base URLs, auth headers, model lists, context metadata,
  rate-limit parsing, key rotation, and provider-specific HTTP behavior.
- Protocol adapters own request/response conversion and streaming event shapes.
- Tool dialects own runtime tool names, schema repair, and blocked-tool policy.
- Channel bridge code owns queueing, dedupe, staleness, and wake behavior.

## Current Refactor Target

Do not implement Codex or Agy yet.  First make the Claude Code path live behind
runtime/provider/protocol/tool contracts while preserving behavior.

Safe order:

1. Add contracts and tests.
2. Wrap the existing Claude launch path with a `ClaudeRuntimeAdapter`.
3. Move MCP config discovery/generation behind the runtime adapter.
4. Move Claude Code tool names and plan-mode behavior behind a Claude tool
   dialect.
5. Move upstream provider behavior into provider adapters.
6. Only then add another runtime.

## Compatibility Rules

Each migration step must keep these stable:

- Existing CLI commands and flags.
- Existing config file format.
- Existing npm package bins.
- Existing Claude Code launch command for equivalent settings.
- Existing router HTTP API.
- Existing channel queue semantics unless the change explicitly targets them.

## AI Maintenance Notes

Every module should say what it owns and what it does not own.  This helps AI
agents find the right file instead of making local fixes in unrelated areas.

Examples:

- `runtime/claude.py`: do not add provider rate-limit logic here.
- `providers/opencode.py`: do not add Claude Code launch flags here.
- `channels/queue.py`: do not call provider HTTP APIs here.
- `protocol/openai.py`: do not decide terminal wake behavior here.
