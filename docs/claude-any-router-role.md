# Claude Any Router Role

Last updated: 2026-06-09

## Purpose

Claude Any router is an Anthropic-compatible local gateway used by Claude Code when the selected provider is not Claude Native.

Its primary job is to let Claude Code keep speaking the API shape it expects while Claude Any connects that session to another model provider.

Claude Native mode is different: Claude Code talks to Anthropic directly and Claude Any should not replace Claude Code's native behavior. In that mode, Claude Any may prepare launch configuration, MCP configuration, or development-channel flags, but the model traffic is owned by Claude Code unless the user explicitly selects routed mode.

## Core Responsibilities

- Expose Claude Code-compatible endpoints:
  - `/v1/messages`
  - `/v1/models`
  - `/health`

- Route non-native providers:
  - Ollama / Ollama Cloud
  - DeepSeek
  - OpenCode
  - vLLM
  - LM Studio
  - other compatible providers configured by the user

- Translate provider protocols:
  - Convert provider responses into Anthropic-style message blocks.
  - Normalize streaming events.
  - Preserve tool-use and tool-result ordering expected by Claude Code.
  - Adapt OpenAI-compatible and Ollama-style tool calls when needed.

- Manage model options:
  - Context window
  - Reserved context
  - Max output tokens
  - Timeout and stream idle timeout
  - Provider-specific presets and auto-detected model metadata

- Handle provider reliability concerns:
  - Timeout handling
  - Retry handling
  - Rate-limit metadata logging
  - Empty or malformed upstream responses
  - Provider-specific compatibility quirks without hardcoding product-specific workflows

- Support Claude Any features that require routing:
  - Advisor model calls
  - Web chat provider bridge
  - Router diagnostics
  - Request and tool-call logging

## MCP and Channel Scope

Claude Any should not hardcode behavior for a specific MCP server or product.

For MCP servers, Claude Any's role is limited to generic launch and compatibility support:

- Generate or pass through MCP configuration for Claude Code.
- Proxy stdio MCP servers when needed.
- Detect channel-capable MCP servers and add the appropriate Claude Code development-channel launch flags.
- Avoid implementing product-specific message semantics such as "DM", "task", "poll", or "room" handling.

When Claude Code native development channels are enabled, channel event interpretation belongs to Claude Code and the MCP server tools. Claude Any may provide generic fallback or diagnostics, but it must not become a product-specific MCP client.

## Router Lifetime

When Claude Any starts Claude Code through the router, the router is part of that Claude Any-launched session.

Expected behavior:

- Start the router before launching Claude Code when routed mode needs it.
- Keep the router alive while the Claude Any-launched Claude Code process is alive.
- Stop the managed router when that Claude Code process exits.
- Avoid killing routers that belong to another working directory, config identity, user, or session.
- If a stale router blocks the intended port for the same config identity, replace it safely.

## Design Boundaries

Claude Any should remain a generic compatibility layer.

It should not:

- Hardcode AI-Net or any other specific MCP product behavior.
- Interpret business semantics of external channel messages.
- Depend on room names, actor names, or application-specific message types.
- Override Claude Native behavior unless routed mode is explicitly selected.

It should:

- Preserve Claude Code's expected API contract.
- Keep provider adaptation generic and metadata-driven.
- Log enough evidence for diagnosis.
- Prefer configuration, provider metadata, and protocol capabilities over hardcoded assumptions.
