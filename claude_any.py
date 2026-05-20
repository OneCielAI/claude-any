#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import html as html_lib
import importlib.util
import json
import math
import os
import re
import signal
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable

from claude_any_support.observability import EventBus, render_events_html
from claude_any_support.transcript_filter import (
    is_claude_code_transcript_event,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("CLAUDE_ANY_CONFIG_DIR") or (HOME / ".config" / "claude-any"))
CONFIG_PATH = CONFIG_DIR / "config.json"
LOG_PATH = CONFIG_DIR / "router.log"
LOG_LEVEL_PATH = CONFIG_DIR / "log-level"
REQUEST_DUMP_PATH = CONFIG_DIR / "requests.jsonl"
RESPONSE_DUMP_PATH = CONFIG_DIR / "responses.jsonl"
TOOL_CALL_LOG_PATH = CONFIG_DIR / "tool-calls.jsonl"
RATE_LIMIT_STATE_PATH = CONFIG_DIR / "rate-limit-state.json"
ROUTER_ACTIVITY_PATH = CONFIG_DIR / "router-activity.json"
CONTEXT_USAGE_PATH = CONFIG_DIR / "context-usage.json"
OLLAMA_MODEL_CATALOG_PATH = CONFIG_DIR / "ollama-model-catalog.json"
CHAT_MESSAGES_PATH = CONFIG_DIR / "chat-messages.jsonl"
CHAT_FILES_DIR = CONFIG_DIR / "chat-files"
MENU_KEY_DEBUG_PATH = CONFIG_DIR / "ca-key-debug.log"
PLAN_ARTIFACTS_DIR = CONFIG_DIR / "plan-artifacts"
PID_PATH = CONFIG_DIR / "router.pid"
MODEL_LIST_CACHE_PATH = CONFIG_DIR / "model-list-cache.json"
WEB_TOOLS_MCP_CONFIG = CONFIG_DIR / "web-tools-mcp.json"
DUCKDUCKGO_MCP_CONFIG = CONFIG_DIR / "duckduckgo-mcp.json"
CHANNEL_MCP_CONFIG = CONFIG_DIR / "channel-mcp.json"
CHANNEL_MCP_CURSOR_PATH = CONFIG_DIR / "channel-mcp-cursor.json"
MCP_PROXY_CONFIG = CONFIG_DIR / "mcp-proxy.json"
ROUTER_HOST = os.environ.get("CLAUDE_ANY_ROUTER_CLIENT_HOST", "127.0.0.1").strip() or "127.0.0.1"
ROUTER_PORT = 8799
ROUTER_BASE = f"http://{ROUTER_HOST}:{ROUTER_PORT}"
CLAUDE_GATEWAY_CACHE = HOME / ".claude" / "cache" / "gateway-models.json"
CLAUDE_SETTINGS_PATH = HOME / ".claude" / "settings.json"
CLAUDE_COMMANDS_DIR = HOME / ".claude" / "commands"
CLAUDE_ANY_STATUSLINE_PATH = HOME / ".local" / "bin" / "claude-any-statusline.py"
NCP_ENV = HOME / ".config" / "nvd-claude-proxy" / ".env"
NCP_LOG = HOME / ".config" / "nvd-claude-proxy" / "proxy.log"
MODEL_CACHE_TTL_SECONDS = 300
OLLAMA_MODEL_CATALOG_URL = "https://ollama.com/api/tags"
OLLAMA_MODEL_CATALOG_TTL_SECONDS = 24 * 60 * 60
NCP_PYPI_PACKAGE = "nvd-claude-proxy"

PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "ollama": "ollama",
    "ollama-cloud": "ollama-cloud",
    "cloud-ollama": "ollama-cloud",
    "vllm": "vllm",
    "vllm-local": "vllm",
    "nvidia": "nvidia-hosted",
    "nvidia-hosted": "nvidia-hosted",
    "hosted-nvidia": "nvidia-hosted",
    "nim": "self-hosted-nim",
    "self-hosted-nim": "self-hosted-nim",
    "self-nim": "self-hosted-nim",
}

PROVIDER_LABELS = {
    "anthropic": "Anthropic",
    "ollama": "Ollama",
    "ollama-cloud": "Ollama Cloud",
    "vllm": "vLLM",
    "nvidia-hosted": "Nvidia Hosted",
    "self-hosted-nim": "Self Hosted NIM",
}
OFFICIAL_CHANNEL_PLUGINS = {
    "telegram": "plugin:telegram@claude-plugins-official",
    "discord": "plugin:discord@claude-plugins-official",
    "imessage": "plugin:imessage@claude-plugins-official",
    "fakechat": "plugin:fakechat@claude-plugins-official",
}
APP_NAME = "Claude Any"
VERSION = "0.1.96"
CREDITS = "Credits: One Ciel LLC"

LOG_LEVELS = {"SILENT": 0, "ERROR": 1, "WARN": 2, "INFO": 3, "DEBUG": 4, "TRACE": 5}
LOG_LEVEL_NAMES = {v: k for k, v in LOG_LEVELS.items()}
LOG_LEVEL_DEFAULT = LOG_LEVELS["ERROR"]
ROUTER_LOG_MAX_BYTES = 1_000_000
REQUEST_DUMP_MAX_BYTES = 5_000_000
RESPONSE_DUMP_MAX_BYTES = 5_000_000
RESPONSE_DUMP_TEXT_LIMIT = 16_000
CHAT_MESSAGES_MAX_BYTES = 20_000_000
DEFAULT_REQUEST_TIMEOUT_MS = 300000
_LOG_LEVEL_CACHE: dict[str, Any] = {"value": None, "checked_at": 0.0, "file_mtime": 0.0}
_RATE_LIMIT_LOCK = threading.Lock()
_CHAT_CONDITION = threading.Condition()
_CHAT_NEXT_ID: int | None = None
_CHANNEL_SSE_LOCK = threading.Lock()
_CHANNEL_SSE_CONNECTIONS: dict[str, dict[str, Any]] = {}
_CHANNEL_MCP_LOCK = threading.Lock()
_CHANNEL_MCP_SESSIONS: dict[str, dict[str, Any]] = {}
_CHANNEL_MCP_CURSOR_LOCK = threading.Lock()
_CHANNEL_MCP_CURSOR_LAST_ID: int | None = None
_NATIVE_CHANNEL_NOTIFICATION_METHOD = "notifications/claude/channel"
_MCP_NOTIFICATION_DEDUP_TTL_SECONDS = 3.0
_MCP_NOTIFICATION_DEDUP_LOCK = threading.Lock()
_MCP_NOTIFICATION_DEDUP_RECENT: dict[str, tuple[str, float]] = {}
EVENT_BUS = EventBus()
ADVISOR_FEEDBACK_MARKER = "CLAUDE_ANY_ADVISOR_FEEDBACK"
PLAN_GUARD_MARKER = "[claude-any-plan-guard]"
TASK_UPDATE_STATUSES = {"pending", "in_progress", "completed", "deleted"}
TASK_UPDATE_STATUS_ALIASES = {
    "active": "in_progress",
    "assigned": "in_progress",
    "current": "in_progress",
    "doing": "in_progress",
    "inprogress": "in_progress",
    "in_progress": "in_progress",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "ongoing": "in_progress",
    "processing": "in_progress",
    "running": "in_progress",
    "started": "in_progress",
    "working": "in_progress",
    "complete": "completed",
    "completed": "completed",
    "done": "completed",
    "finished": "completed",
    "resolved": "completed",
    "success": "completed",
    "closed": "completed",
    "open": "pending",
    "pending": "pending",
    "queued": "pending",
    "todo": "pending",
    "to_do": "pending",
    "to-do": "pending",
    "waiting": "pending",
    "cancel": "deleted",
    "cancelled": "deleted",
    "canceled": "deleted",
    "delete": "deleted",
    "deleted": "deleted",
    "remove": "deleted",
    "removed": "deleted",
}

# Tools Claude Code injects into every model's tool list that misfire when called
# by non-Anthropic models. See docs/notes from anthropics/claude-code issues
# #25720, #29950 and Piebald-AI/claude-code-system-prompts for tool semantics.
PLAN_MODE_SELF_TOOLS: tuple[str, ...] = ("EnterPlanMode", "ExitPlanMode")
DEFAULT_BLOCKED_TOOLS_NON_ANTHROPIC: tuple[str, ...] = (
    "EnterWorktree",
    "ExitWorktree",
    "TeamCreate",
    "TeamDelete",
    "TeammateTool",
    "SendMessage",
    "SendMessageTool",
    "ScheduleWakeup",
    "RemoteTrigger",
    "PushNotification",
)
NON_ANTHROPIC_COMPAT_PROMPT = (
    "You are running inside Claude Code through a non-Anthropic model provider. "
    "Do not stop after announcing what you plan to do. When the user asks you to create, edit, or run code, "
    "immediately use the available Claude Code tools such as Write, Edit, Read, and Bash as appropriate, "
    "except while Claude Code is in Plan Mode. In Plan Mode, first explore/read as needed, write or update the plan file named "
    "by the plan_mode attachment, and only then call ExitPlanMode to request approval; do not call EnterPlanMode again. "
    "then report the concrete result. If you decide not to use tools, provide the complete requested code or answer in the same turn. "
    "Use skills only when the user's request clearly matches that skill; never invoke keybindings-help unless the user asks about keybindings. "
    "Keep final answers concise and do not expose hidden chain-of-thought. "
    "When calling Claude Code tools, use exactly the tool schema and do not invent extra fields. "
    "Bash: command (string), description (string), timeout (integer), run_in_background (boolean). "
    "Read: file_path (string), offset (integer), limit (integer). "
    "Write: file_path (string), content (string). "
    "Edit: file_path (string), old_string (string), new_string (string), replace_all (boolean). "
    "TaskList: no input. TaskUpdate: taskId (string), optional status enum exactly one of pending, in_progress, completed, deleted. "
    "CronCreate: cron (standard 5-field local-time cron string), prompt (string), optional recurring (boolean), optional durable (boolean). "
    "CronDelete: id (string returned by CronCreate). CronList: no input. "
    "Never write pseudo tool calls, partial JSON, or markdown code fences when a real Claude Code tool call is required."
)
LANGUAGES = {
    "en": "English",
    "ko": "한국어",
    "ja": "日本語",
    "zh": "中文",
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "glm-4.7": {"compat_max_tokens": 64, "thinking": True, "num_ctx_min": 32768, "num_ctx_max": 131072},
    "glm-5.1": {"compat_max_tokens": 64, "thinking": True, "num_ctx_min": 32768, "num_ctx_max": 131072},
    "glm-4.7:cloud": {"compat_max_tokens": 64, "thinking": True, "num_ctx_min": 32768, "num_ctx_max": 131072},
    "glm-5.1:cloud": {"compat_max_tokens": 64, "thinking": True, "num_ctx_min": 32768, "num_ctx_max": 131072},
    "qwen3-coder": {"compat_max_tokens": 16, "thinking": False, "num_ctx_min": 32768, "num_ctx_max": 65536},
    "qwen3-coder:30b": {"compat_max_tokens": 16, "thinking": False, "num_ctx_min": 32768, "num_ctx_max": 65536},
    "qwen3.6:27b": {"compat_max_tokens": 16, "thinking": False, "num_ctx_min": 32768, "num_ctx_max": 65536},
    "deepseek-r1": {"compat_max_tokens": 64, "thinking": True, "num_ctx_min": 32768, "num_ctx_max": 131072},
    "llama3.3:70b": {"compat_max_tokens": 16, "thinking": False, "num_ctx_min": 32768, "num_ctx_max": 131072},
}


def nvidia_hosted_context_default(model_id: str) -> int:
    model = model_id.lower()
    if "kimi-k2.6" in model or "kimi_k2.6" in model:
        return 262144
    if "deepseek" in model:
        return 131072
    if "glm" in model or "qwen" in model:
        return 65536
    return 65536


def model_preset(model_id: str) -> dict[str, Any]:
    """Return preset dict for a model ID, checking exact match then prefix match."""
    if model_id in MODEL_PRESETS:
        return MODEL_PRESETS[model_id]
    for key, value in MODEL_PRESETS.items():
        if model_id.startswith(key) or key.startswith(model_id.split(":")[0]):
            return value
    return {}


def compat_max_tokens_for_model(model_id: str) -> int:
    return model_preset(model_id).get("compat_max_tokens", 16)


def ollama_library_model_parts(model_id: str) -> tuple[str, str] | None:
    model = (model_id or "").strip()
    if not model:
        return None
    base, tag = (model.split(":", 1) + ["latest"])[:2] if ":" in model else (model, "latest")
    base = base.strip()
    tag = tag.strip() or "latest"
    # Ollama library pages are /library/<model>/tags. Skip custom namespaces
    # such as hf.co/... or registry paths that do not map cleanly to this URL.
    if "/" in base or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", base):
        return None
    return base, tag


def context_label_to_tokens(number: str, unit: str | None) -> int | None:
    try:
        value = float(number)
    except Exception:
        return None
    if value <= 0 or not math.isfinite(value):
        return None
    unit = (unit or "").strip().lower()
    multiplier = {"k": 1024, "m": 1024 * 1024, "g": 1024 * 1024 * 1024}.get(unit, 1)
    return int(round(value * multiplier))


def recommended_timeout_ms_for_context(context_tokens: int | None) -> int:
    """Return the default upstream wait timeout for a model/context size."""
    tokens = positive_int(context_tokens)
    if not tokens:
        return DEFAULT_REQUEST_TIMEOUT_MS
    if tokens and tokens >= 1024 * 1024:
        return 300000
    if tokens and tokens >= 512 * 1024:
        return 180000
    return 120000


def ollama_model_catalog_key(model_id: str) -> tuple[str, str, str] | None:
    parts = ollama_library_model_parts(model_id)
    if not parts:
        return None
    base, tag = parts
    return base.lower(), base, tag.lower()


def load_ollama_model_catalog() -> dict[str, Any]:
    try:
        data = json.loads(OLLAMA_MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_ollama_model_catalog(catalog: dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = OLLAMA_MODEL_CATALOG_PATH.with_name(f"{OLLAMA_MODEL_CATALOG_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(OLLAMA_MODEL_CATALOG_PATH)
    except Exception as exc:
        router_log("WARN", f"ollama catalog: failed to save cache: {exc}")


def ollama_catalog_is_stale(catalog: dict[str, Any], ttl_seconds: int = OLLAMA_MODEL_CATALOG_TTL_SECONDS) -> bool:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), dict):
        return True
    try:
        updated_at = float(catalog.get("updated_at") or 0)
    except Exception:
        updated_at = 0.0
    return updated_at <= 0 or time.time() - updated_at > ttl_seconds


def fetch_json_url(url: str, timeout: float = 12.0) -> Any:
    req = urllib.request.Request(url, headers={"user-agent": f"claude-any/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(5_000_000).decode("utf-8", errors="replace"))


def context_tokens_from_ollama_snippet(snippet: str, table_fallback: bool = True) -> int | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*([KMG])\s+context\s+window\b", snippet, re.IGNORECASE)
    if match:
        return context_label_to_tokens(match.group(1), match.group(2))
    if table_fallback:
        match = re.search(r">\s*(\d+(?:\.\d+)?)\s*([KM])\s*</p>", snippet, re.IGNORECASE)
        if match:
            return context_label_to_tokens(match.group(1), match.group(2))
    return None


def parse_ollama_library_context_map(page_html: str, base_model: str) -> dict[str, int]:
    text = html_lib.unescape(page_html or "")
    base = (base_model or "").strip()
    if not text or not base:
        return {}
    contexts: dict[str, int] = {}
    pattern = re.compile(r"(?<![A-Za-z0-9._/-])" + re.escape(base) + r":([A-Za-z0-9][A-Za-z0-9._-]*)", re.IGNORECASE)
    for match in pattern.finditer(text):
        tag = match.group(1).strip().lower()
        if not tag:
            continue
        snippet = text[max(0, match.start() - 700): match.end() + 3000]
        tokens = context_tokens_from_ollama_snippet(snippet)
        if tokens:
            contexts[tag] = max(contexts.get(tag, 0), tokens)

    if not contexts:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*([KMG])\s+context\s+window\b", text, re.IGNORECASE)
        tokens = context_label_to_tokens(match.group(1), match.group(2)) if match else None
        if tokens:
            contexts["latest"] = tokens
    return contexts


def fetch_ollama_library_context_map(base_model: str, timeout: float = 10.0) -> tuple[dict[str, int], str | None]:
    parts = ollama_library_model_parts(base_model)
    if not parts:
        return {}, None
    base, _ = parts
    urls = [
        f"https://ollama.com/library/{urllib.parse.quote(base, safe='')}/tags",
        f"https://ollama.com/library/{urllib.parse.quote(base, safe='')}",
    ]
    merged: dict[str, int] = {}
    source_url: str | None = None
    for url in urls:
        req = urllib.request.Request(url, headers={"user-agent": f"claude-any/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(3_000_000)
        except Exception:
            continue
        page_map = parse_ollama_library_context_map(raw.decode("utf-8", errors="replace"), base)
        for tag, tokens in page_map.items():
            merged[tag] = max(merged.get(tag, 0), tokens)
        if page_map and not source_url:
            source_url = url
    return merged, source_url


def refresh_ollama_model_catalog(include_contexts: bool = True, timeout: float = 10.0) -> dict[str, Any]:
    old_catalog = load_ollama_model_catalog()
    old_models = old_catalog.get("models") if isinstance(old_catalog.get("models"), dict) else {}
    data = fetch_json_url(OLLAMA_MODEL_CATALOG_URL, timeout=timeout)
    raw_models = data.get("models") if isinstance(data, dict) else None
    if raw_models is None and isinstance(data, dict):
        raw_models = data.get("data")
    if not isinstance(raw_models, list):
        raw_models = []

    models: dict[str, dict[str, Any]] = {}
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or item.get("id") or "").strip()
        parts = ollama_model_catalog_key(name)
        if not parts:
            continue
        key, base, tag = parts
        entry = models.setdefault(
            key,
            {
                "id": base,
                "models": [],
                "tags": [],
                "raw": [],
                "context_windows": {},
                "context_source": None,
            },
        )
        if name not in entry["models"]:
            entry["models"].append(name)
        if tag not in entry["tags"]:
            entry["tags"].append(tag)
        entry["raw"].append(item)

    if not include_contexts and isinstance(old_models, dict):
        for key, entry in models.items():
            old_entry = old_models.get(key)
            if not isinstance(old_entry, dict):
                continue
            old_windows = old_entry.get("context_windows")
            if isinstance(old_windows, dict) and old_windows:
                entry["context_windows"] = old_windows
                entry["context_window"] = positive_int(old_entry.get("context_window")) or max(
                    positive_int(v) or 0 for v in old_windows.values()
                )
                if isinstance(old_entry.get("recommended_timeout_ms_by_tag"), dict):
                    entry["recommended_timeout_ms_by_tag"] = old_entry["recommended_timeout_ms_by_tag"]
                if positive_int(old_entry.get("recommended_timeout_ms")):
                    entry["recommended_timeout_ms"] = positive_int(old_entry.get("recommended_timeout_ms"))
                entry["context_source"] = old_entry.get("context_source")

    if include_contexts:
        for key in sorted(models):
            entry = models[key]
            context_map, source = fetch_ollama_library_context_map(str(entry["id"]), timeout=timeout)
            if context_map:
                entry["context_windows"] = context_map
                entry["context_window"] = max(context_map.values())
                entry["recommended_timeout_ms_by_tag"] = {
                    tag: recommended_timeout_ms_for_context(tokens)
                    for tag, tokens in context_map.items()
                    if positive_int(tokens)
                }
                entry["recommended_timeout_ms"] = recommended_timeout_ms_for_context(entry["context_window"])
                entry["context_source"] = source

    catalog = {
        "schema": 1,
        "source": OLLAMA_MODEL_CATALOG_URL,
        "updated_at": time.time(),
        "model_count": len(raw_models),
        "base_model_count": len(models),
        "models": models,
    }
    save_ollama_model_catalog(catalog)
    return catalog


def ollama_catalog_context_for_model(model_id: str) -> tuple[int | None, str | None, str | None]:
    parts = ollama_model_catalog_key(model_id)
    if not parts:
        return None, None, None
    key, base, tag = parts
    catalog = load_ollama_model_catalog()
    entry = catalog.get("models", {}).get(key) if isinstance(catalog.get("models"), dict) else None
    if not isinstance(entry, dict):
        return None, None, None
    windows = entry.get("context_windows")
    source = str(entry.get("context_source") or catalog.get("source") or "")
    if isinstance(windows, dict):
        candidates = [tag]
        if tag in ("latest", ""):
            candidates.extend(["cloud", "latest"])
        candidates.extend(["cloud", "latest"])
        for candidate in candidates:
            value = positive_int(windows.get(candidate))
            if value:
                return value, f"{base}:{candidate}", source or None
    value = positive_int(entry.get("context_window"))
    if value:
        return value, base, source or None
    return None, None, None


def ollama_catalog_timeout_for_model(model_id: str) -> int | None:
    parts = ollama_model_catalog_key(model_id)
    if not parts:
        return None
    key, _, tag = parts
    catalog = load_ollama_model_catalog()
    entry = catalog.get("models", {}).get(key) if isinstance(catalog.get("models"), dict) else None
    if not isinstance(entry, dict):
        return None
    per_tag = entry.get("recommended_timeout_ms_by_tag")
    if isinstance(per_tag, dict):
        candidates = [tag]
        if tag in ("latest", ""):
            candidates.extend(["cloud", "latest"])
        candidates.extend(["cloud", "latest"])
        for candidate in candidates:
            value = positive_int(per_tag.get(candidate))
            if value:
                return value
    return positive_int(entry.get("recommended_timeout_ms"))


def update_ollama_catalog_context(model_id: str, limit: int, matched_model: str | None, source_url: str | None) -> None:
    parts = ollama_model_catalog_key(model_id)
    if not parts or not limit:
        return
    key, base, tag = parts
    catalog = load_ollama_model_catalog()
    if not isinstance(catalog.get("models"), dict):
        catalog = {
            "schema": 1,
            "source": OLLAMA_MODEL_CATALOG_URL,
            "updated_at": time.time(),
            "model_count": 0,
            "base_model_count": 0,
            "models": {},
        }
    entry = catalog["models"].setdefault(
        key,
        {"id": base, "models": [], "tags": [], "raw": [], "context_windows": {}, "context_source": None},
    )
    if model_id not in entry["models"]:
        entry["models"].append(model_id)
    tag_to_store = tag
    matched_parts = ollama_model_catalog_key(matched_model or "")
    if matched_parts:
        tag_to_store = matched_parts[2]
    entry.setdefault("tags", [])
    if tag_to_store not in entry["tags"]:
        entry["tags"].append(tag_to_store)
    windows = entry.setdefault("context_windows", {})
    if isinstance(windows, dict):
        windows[tag_to_store] = int(limit)
    recommended_by_tag = entry.setdefault("recommended_timeout_ms_by_tag", {})
    if isinstance(recommended_by_tag, dict):
        recommended_by_tag[tag_to_store] = recommended_timeout_ms_for_context(limit)
    entry["context_window"] = max([positive_int(v) or 0 for v in entry.get("context_windows", {}).values()] + [int(limit)])
    entry["recommended_timeout_ms"] = recommended_timeout_ms_for_context(positive_int(entry.get("context_window")))
    entry["context_source"] = source_url or entry.get("context_source")
    catalog["updated_at"] = time.time()
    catalog["base_model_count"] = len(catalog.get("models", {}))
    save_ollama_model_catalog(catalog)


def parse_ollama_library_context_limit(tags_html: str, full_model_id: str) -> int | None:
    text = html_lib.unescape(tags_html or "")
    target = (full_model_id or "").strip()
    if not text or not target:
        return None
    lower = text.lower()
    target_lower = target.lower()
    positions: list[int] = []
    start = 0
    while True:
        idx = lower.find(target_lower, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + len(target_lower)
    for idx in positions:
        snippet = text[max(0, idx - 500): idx + 2500]
        tokens = context_tokens_from_ollama_snippet(snippet)
        if tokens:
            return tokens
    return None


def fetch_ollama_library_context_limit(model_id: str, timeout: float = 6.0) -> tuple[int | None, str | None, str | None]:
    parts = ollama_library_model_parts(model_id)
    if not parts:
        return None, None, None
    base, tag = parts
    full_model = f"{base}:{tag}"
    context_map, url = fetch_ollama_library_context_map(base, timeout=timeout)
    limit = positive_int(context_map.get(tag.lower()))
    if not limit and tag == "latest":
        cloud_limit = positive_int(context_map.get("cloud"))
        if cloud_limit:
            return cloud_limit, f"{base}:cloud", url
    return limit, full_model, url


def ollama_context_model_matches(current_model: str, cached_model: str | None) -> bool:
    current = (current_model or "").strip().lower()
    cached = (cached_model or "").strip().lower()
    if not current or not cached:
        return False

    def aliases(value: str) -> set[str]:
        result = {value}
        if ":" not in value:
            result.add(f"{value}:latest")
            result.add(f"{value}:cloud")
        if value.endswith(":latest") or value.endswith(":cloud"):
            result.add(value.rsplit(":", 1)[0])
        return result

    return bool(aliases(current) & aliases(cached))


def sync_ollama_library_context_limit(provider: str, pcfg: dict[str, Any], model_id: str) -> list[str]:
    if provider not in ("ollama", "ollama-cloud"):
        return []
    catalog = load_ollama_model_catalog()
    if ollama_catalog_is_stale(catalog):
        try:
            catalog = refresh_ollama_model_catalog(include_contexts=False)
        except Exception as exc:
            router_log("WARN", f"ollama catalog: api refresh failed: {exc}")
    limit, matched_model, url = ollama_catalog_context_for_model(model_id)
    if not limit:
        limit, matched_model, url = fetch_ollama_library_context_limit(model_id)
        if limit:
            update_ollama_catalog_context(model_id, limit, matched_model, url)
    if not limit:
        hint = model_context_hint_from_model_id(model_id)
        if hint:
            limit = hint
            matched_model = normalize_model_id(provider, model_id)
        else:
            if not ollama_context_model_matches(model_id, str(pcfg.get("model_context_model") or "")):
                pcfg.pop("model_context_max", None)
                pcfg.pop("model_context_model", None)
            return []
    old_max = positive_int(pcfg.get("num_ctx_max"))
    pcfg["model_context_max"] = limit
    pcfg["model_context_model"] = matched_model
    pcfg["num_ctx_max"] = limit
    minimum = positive_int(pcfg.get("num_ctx_min"))
    if minimum and minimum > limit:
        pcfg["num_ctx_min"] = limit
    fixed_ctx = positive_int(pcfg.get("num_ctx"))
    if fixed_ctx and fixed_ctx > limit:
        pcfg["num_ctx"] = limit
    label = f"{limit:,}"
    if old_max and old_max == limit:
        return [f"Ollama library context verified: {matched_model} -> {label} tokens."]
    detail = f" from {url}" if url else ""
    return [f"Ollama library context detected: {matched_model} -> {label} tokens{detail}."]


# ---------------------------------------------------------------------------
# Tool schema registry and parameter validation
# ---------------------------------------------------------------------------

_TOOL_SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {}

_BUILTIN_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "Bash": {
        "required": ["command"],
        "properties": {
            "command": {"type": "string"},
            "description": {"type": "string"},
            "timeout": {"type": "integer"},
            "run_in_background": {"type": "boolean"},
        },
    },
    "Read": {
        "required": ["file_path"],
        "properties": {
            "file_path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
    },
    "Write": {
        "required": ["file_path", "content"],
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
        },
    },
    "Edit": {
        "required": ["file_path", "old_string", "new_string"],
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
    },
    "Glob": {
        "required": ["pattern"],
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
        },
    },
    "Grep": {
        "required": ["pattern"],
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "output_mode": {"type": "string"},
        },
    },
    "TaskList": {
        "required": [],
        "properties": {},
    },
    "TaskUpdate": {
        "required": ["taskId"],
        "properties": {
            "taskId": {"type": "string"},
            "subject": {"type": "string"},
            "description": {"type": "string"},
            "activeForm": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
            "owner": {"type": "string"},
            "addBlocks": {"type": "array"},
            "addBlockedBy": {"type": "array"},
            "metadata": {"type": "object"},
        },
    },
    "TaskCreate": {
        "required": ["subject", "description"],
        "properties": {
            "subject": {"type": "string"},
            "description": {"type": "string"},
        },
    },
    "TaskGet": {
        "required": ["taskId"],
        "properties": {
            "taskId": {"type": "string"},
        },
    },
    "TaskStop": {
        "required": ["task_id"],
        "properties": {
            "task_id": {"type": "string"},
        },
    },
    "CronCreate": {
        "required": ["cron", "prompt"],
        "properties": {
            "cron": {"type": "string"},
            "prompt": {"type": "string"},
            "recurring": {"type": "boolean"},
            "durable": {"type": "boolean"},
        },
    },
    "CronDelete": {
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
        },
    },
    "CronList": {
        "required": [],
        "properties": {},
    },
    "advisor": {
        "required": ["question"],
        "properties": {
            "question": {"type": "string"},
        },
    },
}


def _update_tool_schema_registry(tools: Any) -> None:
    """Cache tool schemas from incoming Anthropic requests."""
    if not isinstance(tools, list):
        return
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        _TOOL_SCHEMA_REGISTRY[name] = tool.get("input_schema") or {}


def _lookup_tool_schema(tool_name: str) -> dict[str, Any] | None:
    """Look up a tool schema by name, checking registry then builtins."""
    if tool_name in _TOOL_SCHEMA_REGISTRY:
        return _TOOL_SCHEMA_REGISTRY[tool_name]
    if tool_name in _BUILTIN_TOOL_SCHEMAS:
        return _BUILTIN_TOOL_SCHEMAS[tool_name]
    return None


def _fuzzy_match_tool_name(name: str) -> str | None:
    """Fuzzy match a tool name against known schemas (case-insensitive, prefix)."""
    low = name.lower()
    candidates = list(_TOOL_SCHEMA_REGISTRY.keys()) + list(_BUILTIN_TOOL_SCHEMAS.keys())
    # Exact match first
    for c in candidates:
        if c == name:
            return c
    # Case-insensitive
    for c in candidates:
        if c.lower() == low:
            return c
    # Prefix/substring match
    for c in candidates:
        if low in c.lower() or c.lower() in low:
            return c
    return None


def _coerce_value(value: Any, expected_type: str | None) -> Any:
    """Coerce a value to the expected JSON schema type."""
    if expected_type is None:
        return value
    if isinstance(value, bool) and expected_type == "boolean":
        return value
    if isinstance(value, (int, float)) and expected_type == "integer":
        return int(value)
    if isinstance(value, (int, float)) and expected_type == "number":
        return float(value)
    if isinstance(value, str) and expected_type == "string":
        return value
    if expected_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if value is None:
            return []
        return value
    if expected_type == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return value
    # Coerce string -> integer
    if isinstance(value, str) and expected_type in ("integer", "number"):
        try:
            return int(value) if expected_type == "integer" else float(value)
        except Exception:
            pass
    # Coerce string -> boolean
    if isinstance(value, str) and expected_type == "boolean":
        low = value.lower()
        if low in ("true", "yes", "on", "1"):
            return True
        if low in ("false", "no", "off", "0"):
            return False
    # Coerce int/float -> string
    if isinstance(value, (int, float)) and expected_type == "string":
        return str(value)
    # Coerce anything -> string as last resort
    if expected_type == "string" and value is not None:
        return str(value)
    return value


def normalize_task_update_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = re.sub(r"[\s\-]+", "_", text.lower())
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    if normalized in TASK_UPDATE_STATUSES:
        return normalized
    return TASK_UPDATE_STATUS_ALIASES.get(text.lower()) or TASK_UPDATE_STATUS_ALIASES.get(normalized)


def _default_for_missing_required(tool_name: str, field: str) -> Any:
    """Return a safe default for known required fields."""
    defaults: dict[str, dict[str, Any]] = {
        "Bash": {"command": "true", "timeout": 30000, "description": "", "run_in_background": False},
        "Read": {"offset": 0, "limit": 0},
        "Edit": {"replace_all": False},
        "Glob": {"path": "."},
        "Grep": {"output_mode": "content"},
        "TaskCreate": {"description": ""},
        "TaskStop": {},
    }
    return defaults.get(tool_name, {}).get(field)


def _is_empty_value(value: Any) -> bool:
    """Check if a value is effectively empty and should be defaulted."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _move_first_present(fixed: dict[str, Any], target: str, aliases: tuple[str, ...]) -> None:
    """Move the first non-empty alias value to the target field."""
    if target in fixed and not _is_empty_value(fixed.get(target)):
        return
    for alias in aliases:
        value = fixed.get(alias)
        if not _is_empty_value(value):
            fixed[target] = value
            break


def _validate_and_fix_tool_input(tool_name: str, input_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Validate tool_use input against schema and fix common errors:
      - fuzzy-match tool name
      - coerce types to match schema
      - add defaults for missing required fields
      - keep unknown fields (Claude Code may accept extra fields)
    """
    schema = _lookup_tool_schema(tool_name)
    matched_name = tool_name
    if schema is None:
        matched = _fuzzy_match_tool_name(tool_name)
        if matched:
            matched_name = matched
            schema = _lookup_tool_schema(matched)

    if schema is None:
        # No schema known: just ensure it's a dict and return
        return input_dict if isinstance(input_dict, dict) else {}

    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fixed: dict[str, Any] = {}

    for key, raw_value in input_dict.items():
        prop_schema = properties.get(key)
        if prop_schema is None:
            # Unknown field: keep it rather than dropping it.
            # Claude Code may accept fields not in our static registry.
            fixed[key] = raw_value
            continue
        expected_type = prop_schema.get("type") if isinstance(prop_schema, dict) else None
        fixed[key] = _coerce_value(raw_value, expected_type)

    if matched_name == "TaskUpdate":
        if "taskId" not in fixed or _is_empty_value(fixed.get("taskId")):
            for alias in ("task_id", "id"):
                value = fixed.get(alias)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
                    fixed["taskId"] = str(value)
                    break
        if "status" in fixed:
            status = normalize_task_update_status(fixed.get("status"))
            if status:
                fixed["status"] = status
        for alias in ("task_id", "id"):
            fixed.pop(alias, None)

    if matched_name == "CronCreate":
        _move_first_present(
            fixed,
            "cron",
            ("schedule", "cronExpression", "cron_expression", "expression", "interval", "time"),
        )
        _move_first_present(
            fixed,
            "prompt",
            ("message", "task", "instruction", "instructions", "command", "query"),
        )
        for key in ("cron", "prompt", "recurring", "durable"):
            prop_schema = properties.get(key)
            expected_type = prop_schema.get("type") if isinstance(prop_schema, dict) else None
            if key in fixed:
                fixed[key] = _coerce_value(fixed[key], expected_type)
        for alias in (
            "schedule",
            "cronExpression",
            "cron_expression",
            "expression",
            "interval",
            "time",
            "message",
            "task",
            "instruction",
            "instructions",
            "command",
            "query",
        ):
            fixed.pop(alias, None)

    if matched_name == "CronDelete":
        _move_first_present(fixed, "id", ("taskId", "task_id", "jobId", "job_id", "cronId", "cron_id"))
        if "id" in fixed:
            fixed["id"] = _coerce_value(fixed["id"], "string")
        for alias in ("taskId", "task_id", "jobId", "job_id", "cronId", "cron_id"):
            fixed.pop(alias, None)

    if matched_name == "CronList":
        fixed = {}

    # Fill in missing or empty required fields with defaults
    injected: list[str] = []
    for req in required:
        if req not in fixed or _is_empty_value(fixed.get(req)):
            default = _default_for_missing_required(matched_name, req)
            if default is not None:
                fixed[req] = default
            elif matched_name == "TaskUpdate" and req == "taskId":
                continue
            elif req not in fixed:
                # No known default: inject empty value matching expected type
                prop_schema = properties.get(req)
                expected_type = prop_schema.get("type") if isinstance(prop_schema, dict) else None
                if expected_type == "string":
                    fixed[req] = ""
                elif expected_type == "integer":
                    fixed[req] = 0
                elif expected_type == "number":
                    fixed[req] = 0.0
                elif expected_type == "boolean":
                    fixed[req] = False
                elif expected_type == "array":
                    fixed[req] = []
                elif expected_type == "object":
                    fixed[req] = {}
                else:
                    fixed[req] = ""
            injected.append(req)

    if injected:
        router_log("WARN", f"tool_guard: {matched_name}: injected missing required fields: {', '.join(injected)}")

    return fixed


UI_TEXT = {
    "en": {
        "language": "Language",
        "provider": "Provider",
        "api_key": "API key",
        "base_url": "Base URL",
        "model": "Model",
        "advisor_model": "Advisor Model",
        "test": "Test compatibility",
        "options": "LLM options",
        "channel_delivery": "Channel delivery",
        "log_level": "Log level",
        "presets": "LLM presets",
        "context_setup": "Context setup",
        "timeout_preset": "Timeout preset",
        "apply_preset": "Apply preset",
        "model_family": "Model family",
        "recommended_preset_is": "recommended preset is",
        "back": "Back",
        "launch": "Launch Claude Code",
        "quit": "Quit",
        "title": "claude-any pre-launch",
    },
    "ko": {
        "language": "언어",
        "provider": "프로바이더",
        "api_key": "API 키",
        "base_url": "Base URL",
        "model": "모델",
        "advisor_model": "Advisor Model",
        "test": "호환성 테스트",
        "options": "LLM 옵션",
        "channel_delivery": "채널 전달 방식",
        "log_level": "로그 레벨",
        "presets": "LLM 프리셋",
        "context_setup": "컨텍스트 설정",
        "timeout_preset": "타임아웃 프리셋",
        "apply_preset": "프리셋 적용",
        "model_family": "모델 계열",
        "recommended_preset_is": "추천 프리셋",
        "back": "뒤로",
        "launch": "Claude Code 실행",
        "quit": "종료",
        "title": "claude-any 실행 전 설정",
    },
    "ja": {
        "language": "言語",
        "provider": "プロバイダー",
        "api_key": "APIキー",
        "base_url": "Base URL",
        "model": "モデル",
        "advisor_model": "Advisor Model",
        "test": "互換性テスト",
        "options": "LLMオプション",
        "channel_delivery": "チャンネル配信方式",
        "log_level": "ログレベル",
        "presets": "LLMプリセット",
        "context_setup": "コンテキスト設定",
        "timeout_preset": "timeout プリセット",
        "apply_preset": "プリセットを適用",
        "model_family": "モデル系統",
        "recommended_preset_is": "推奨プリセット",
        "back": "戻る",
        "launch": "Claude Codeを起動",
        "quit": "終了",
        "title": "claude-any 起動前設定",
    },
    "zh": {
        "language": "语言",
        "provider": "提供商",
        "api_key": "API 密钥",
        "base_url": "Base URL",
        "model": "模型",
        "advisor_model": "Advisor Model",
        "test": "兼容性测试",
        "options": "LLM 选项",
        "channel_delivery": "频道投递方式",
        "log_level": "日志级别",
        "presets": "LLM 预设",
        "context_setup": "上下文设置",
        "timeout_preset": "Timeout 预设",
        "apply_preset": "应用预设",
        "model_family": "模型类型",
        "recommended_preset_is": "推荐预设",
        "back": "返回",
        "launch": "启动 Claude Code",
        "quit": "退出",
        "title": "claude-any 启动前设置",
    },
}


def ui_text(key: str, lang: str | None = None) -> str:
    lang = lang or load_config().get("language", "en")
    return UI_TEXT.get(lang, UI_TEXT["en"]).get(key, UI_TEXT["en"].get(key, key))


PROVIDER_NOTES = {
    "en": {
        "anthropic": [
            "Anthropic: uses Claude Code's native Anthropic connection.",
            "Set an Anthropic API key here, or run `claude /login` separately to use your Claude account login.",
        ],
        "ollama": [
            "Ollama: uses your local Ollama daemon; API key is normally not required.",
            "To use :cloud models through local Ollama, sign in on the Ollama host with `ollama signin`.",
        ],
        "ollama-cloud": [
            "Ollama Cloud: calls https://ollama.com/api directly; an Ollama API key is required.",
            "Use this when you want cloud models without relying on the local Ollama daemon's sign-in state.",
        ],
        "vllm": [
            "vLLM: enter the vLLM server root that implements the Anthropic Messages API.",
            "Do not enter an OpenAI-only chat completions endpoint; use a compatibility proxy for those servers.",
        ],
        "self-hosted-nim": [
            "Self-hosted NIM: enter the NIM server root that exposes Anthropic-compatible /v1/messages.",
            "This native path does not use the NVIDIA hosted API Catalog proxy.",
        ],
        "nvidia-hosted": [
            "NVIDIA hosted: uses NVIDIA API Catalog at https://integrate.api.nvidia.com/v1.",
            "Hosted API Catalog currently uses the claude-any router path; self-hosted NIM uses native Messages.",
        ],
    },
    "ko": {
        "anthropic": [
            "Anthropic: Claude Code의 기본 Anthropic 연결을 사용합니다.",
            "여기에 Anthropic API key를 넣거나, 별도로 `claude /login`을 실행해 Claude 계정 로그인을 사용하세요.",
        ],
        "ollama": [
            "Ollama: 로컬 Ollama 데몬을 사용합니다. 일반 로컬 모델은 API key가 필요 없습니다.",
            "로컬 Ollama로 :cloud 모델을 쓰려면 Ollama가 실행되는 호스트에서 `ollama signin`이 필요합니다.",
        ],
        "ollama-cloud": [
            "Ollama Cloud: https://ollama.com/api를 직접 호출합니다. Ollama API key가 필요합니다.",
            "로컬 Ollama 데몬의 로그인 상태와 무관하게 클라우드 모델을 쓰고 싶을 때 사용합니다.",
        ],
        "vllm": [
            "vLLM: Anthropic Messages API를 구현한 vLLM 서버 root를 넣으세요.",
            "OpenAI 전용 chat completions endpoint를 넣지 마세요. 그런 서버는 호환 프록시가 필요합니다.",
        ],
        "self-hosted-nim": [
            "Self-hosted NIM: Anthropic 호환 /v1/messages를 노출하는 NIM 서버 root를 넣으세요.",
            "이 native 경로는 NVIDIA hosted API Catalog 프록시를 사용하지 않습니다.",
        ],
        "nvidia-hosted": [
            "NVIDIA hosted: https://integrate.api.nvidia.com/v1 의 NVIDIA API Catalog를 사용합니다.",
            "Hosted API Catalog는 claude-any router 경로를 기본 사용합니다. self-hosted NIM은 native Messages를 사용합니다.",
        ],
    },
    "ja": {
        "anthropic": [
            "Anthropic: Claude CodeのネイティブAnthropic接続を使います。",
            "ここでAnthropic API keyを設定するか、別途`claude /login`を実行してClaudeアカウントログインを使ってください。",
        ],
        "ollama": [
            "Ollama: ローカルのOllama daemonを使います。通常のローカルモデルではAPI keyは不要です。",
            "ローカルOllama経由で:cloudモデルを使うには、Ollamaホストで`ollama signin`が必要です。",
        ],
        "ollama-cloud": [
            "Ollama Cloud: https://ollama.com/api を直接呼び出します。Ollama API keyが必要です。",
            "ローカルOllama daemonのサインイン状態に依存せずクラウドモデルを使う場合に選びます。",
        ],
        "vllm": [
            "vLLM: Anthropic Messages APIを実装したvLLMサーバーrootを入力してください。",
            "OpenAI専用chat completions endpointは入力しないでください。その場合は互換プロキシが必要です。",
        ],
        "self-hosted-nim": [
            "Self-hosted NIM: Anthropic互換/v1/messagesを公開するNIMサーバーrootを入力してください。",
            "このnative経路はNVIDIA hosted API Catalog proxyを使いません。",
        ],
        "nvidia-hosted": [
            "NVIDIA hosted: https://integrate.api.nvidia.com/v1 のNVIDIA API Catalogを使います。",
            "Hosted API Catalogはclaude-any router経路を既定で使います。self-hosted NIMはnative Messagesを使います。",
        ],
    },
    "zh": {
        "anthropic": [
            "Anthropic: 使用Claude Code原生Anthropic连接。",
            "可在此设置Anthropic API key，或另行运行`claude /login`使用Claude账号登录。",
        ],
        "ollama": [
            "Ollama: 使用本地Ollama daemon；普通本地模型通常不需要API key。",
            "若通过本地Ollama使用:cloud模型，需要在运行Ollama的主机上执行`ollama signin`。",
        ],
        "ollama-cloud": [
            "Ollama Cloud: 直接调用 https://ollama.com/api；需要Ollama API key。",
            "当你想不依赖本地Ollama daemon登录状态使用云端模型时选择它。",
        ],
        "vllm": [
            "vLLM: 请输入实现Anthropic Messages API的vLLM服务器root。",
            "不要输入仅OpenAI chat completions的端点；这类服务器需要兼容代理。",
        ],
        "self-hosted-nim": [
            "Self-hosted NIM: 请输入暴露 Anthropic-compatible /v1/messages 的 NIM 服务器 root。",
            "此 native 路径不使用 NVIDIA hosted API Catalog 代理。",
        ],
        "nvidia-hosted": [
            "NVIDIA hosted: 使用 https://integrate.api.nvidia.com/v1 的 NVIDIA API Catalog。",
            "Hosted API Catalog 默认使用 claude-any router 路径；self-hosted NIM 使用 native Messages。",
        ],
    },
}

DEFAULT_ADVISOR_MODELS: tuple[str, ...] = (
    "",
    "deepseek-v4-pro",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "glm-5.1",
)

DEFAULT_CONFIG: dict[str, Any] = {
    "current_provider": "nvidia-hosted",
    "language": "en",
    "migrations": {},
    "router_debug_external_access": False,
    "router_debug_external_access_confirmed": False,
    "router_debug_message_preview_chars": 0,
    "claude_code": {
        "compat_prompt_for_non_anthropic": True,
        "channels": [],
        "development_channels": False,
        "channel_delivery": "native",
    },
    "cleanup": {
        "managed_services_on_launch": True,
    },
    "web_search": {
        "auto_for_non_native": True,
        "provider": "duckduckgo",
        "package": "ddg-mcp-search",
        "fetch_enabled": True,
        "fetch_package": "mcp-server-fetch",
        "fetch_ignore_robots_txt": False,
        "fetch_user_agent": "",
    },
    "providers": {
        "anthropic": {
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "current_model": "claude-sonnet-4-6",
            "advisor_model": "",
            "custom_models": [],
        },
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "api_key": "ollama",
            "current_model": "qwen3-coder",
            "advisor_model": "",
            "custom_models": ["qwen3-coder"],
            "native_compat": True,
            "rate_limit_rpm": 40,
            "rate_limit_status": True,
            "num_ctx": "auto",
            "num_ctx_min": 32768,
            "num_ctx_max": 131072,
            "keep_alive": "5m",
            "think": False,
            "request_timeout_ms": DEFAULT_REQUEST_TIMEOUT_MS,
            "stream_enabled": True,
            "stream_word_chunking": False,
            "ollama_options": {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "num_predict": 4096,
            },
        },
        "ollama-cloud": {
            "base_url": "https://ollama.com",
            "api_key": "",
            "current_model": "glm-5.1",
            "advisor_model": "",
            "custom_models": ["glm-5.1"],
            "rate_limit_rpm": 40,
            "rate_limit_status": True,
            "num_ctx": "auto",
            "num_ctx_min": 32768,
            "num_ctx_max": 131072,
            "keep_alive": "5m",
            "think": False,
            "request_timeout_ms": DEFAULT_REQUEST_TIMEOUT_MS,
            "stream_enabled": True,
            "stream_word_chunking": False,
            "ollama_options": {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "num_predict": 4096,
            },
        },
        "vllm": {
            "base_url": "http://127.0.0.1:8000",
            "api_key": "dummy",
            "current_model": "my-model",
            "advisor_model": "",
            "custom_models": ["my-model"],
            "native_compat": True,
            "context_window": 32768,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "context_reserve_tokens": 1024,
            "request_timeout_ms": DEFAULT_REQUEST_TIMEOUT_MS,
            "stream_enabled": True,
            "stream_word_chunking": False,
        },
        "nvidia-hosted": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "not-used",
            "current_model": "qwen/qwen3-coder-480b-a35b-instruct",
            "advisor_model": "",
            "custom_models": [],
            "native_compat": False,
            "rate_limit_rpm": 40,
            "rate_limit_status": True,
            "context_window": 65536,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "request_timeout_ms": DEFAULT_REQUEST_TIMEOUT_MS,
            "stream_enabled": True,
            "stream_word_chunking": False,
        },
        "self-hosted-nim": {
            "base_url": "http://127.0.0.1:8000",
            "api_key": "not-used",
            "current_model": "model",
            "advisor_model": "",
            "custom_models": ["model"],
            "native_compat": True,
            "rate_limit_rpm": 40,
            "rate_limit_status": True,
            "context_window": 32768,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "context_reserve_tokens": 1024,
            "request_timeout_ms": DEFAULT_REQUEST_TIMEOUT_MS,
            "stream_enabled": True,
            "stream_word_chunking": False,
        },
    },
}


def deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(a))
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_config_migrations(cfg: dict[str, Any]) -> None:
    migrations = cfg.setdefault("migrations", {})
    if not isinstance(migrations, dict):
        migrations = {}
        cfg["migrations"] = migrations

    marker = "nvidia_hosted_router_default_20260509"
    if not migrations.get(marker):
        pcfg = cfg.get("providers", {}).get("nvidia-hosted", {})
        if isinstance(pcfg, dict) and bool(pcfg.get("native_compat", False)):
            pcfg["native_compat"] = False
        migrations[marker] = True

    marker = "default_timeout_5m_20260513"
    if not migrations.get(marker):
        # Historical marker kept for configs that have already recorded it.
        # Do not rewrite 10/30 minute values here anymore: those can now be
        # deliberate long-running timeout profiles.
        migrations[marker] = True

    marker = "default_timeout_2m_20260514"
    if not migrations.get(marker):
        # Historical marker only. The 2-minute default was too short for
        # 50k+ token hosted requests, so newer migrations no longer apply it.
        migrations[marker] = True

    marker = "default_timeout_restore_5m_20260515"
    if not migrations.get(marker):
        for pcfg in (cfg.get("providers") or {}).values():
            if not isinstance(pcfg, dict):
                continue
            if positive_int(pcfg.get("request_timeout_ms")) == 120000 and not pcfg.get("llm_preset"):
                pcfg["request_timeout_ms"] = DEFAULT_REQUEST_TIMEOUT_MS
                if "stream_idle_timeout_ms" not in pcfg:
                    pcfg["stream_idle_timeout_ms"] = DEFAULT_REQUEST_TIMEOUT_MS
        migrations[marker] = True

    marker = "nvidia_context_window_32k_20260513"
    if not migrations.get(marker):
        pcfg = cfg.get("providers", {}).get("nvidia-hosted", {})
        if isinstance(pcfg, dict) and not positive_int(pcfg.get("context_window")):
            pcfg["context_window"] = nvidia_hosted_context_default(str(pcfg.get("current_model") or ""))
        migrations[marker] = True

    marker = "nvidia_context_window_unforce_32k_20260513"
    if not migrations.get(marker):
        pcfg = cfg.get("providers", {}).get("nvidia-hosted", {})
        if isinstance(pcfg, dict) and positive_int(pcfg.get("context_window")) == 32768:
            pcfg["context_window"] = nvidia_hosted_context_default(str(pcfg.get("current_model") or ""))
        migrations[marker] = True

    marker = "stream_enabled_default_true_20260513"
    if not migrations.get(marker):
        for pcfg in (cfg.get("providers") or {}).values():
            if isinstance(pcfg, dict) and "stream_enabled" not in pcfg:
                pcfg["stream_enabled"] = True
        migrations[marker] = True

    marker = "default_channel_delivery_native_20260520"
    if not migrations.get(marker):
        ccfg = cfg.setdefault("claude_code", {})
        if not isinstance(ccfg, dict):
            ccfg = {}
            cfg["claude_code"] = ccfg
        if normalize_channel_delivery(ccfg.get("channel_delivery")) == "stdin":
            ccfg["channel_delivery"] = "native"
        migrations[marker] = True


_config_cache: dict[str, Any] | None = None
_config_cache_mtime: float = 0.0


def load_config() -> dict[str, Any]:
    global _config_cache, _config_cache_mtime
    try:
        mtime = CONFIG_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _config_cache is not None and mtime == _config_cache_mtime:
        return json.loads(json.dumps(_config_cache))
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except Exception:
            data = {}
    else:
        data = {}
    cfg = deep_merge(DEFAULT_CONFIG, data)
    apply_config_migrations(cfg)
    cloud = cfg["providers"].get("ollama-cloud", {})
    local_key = cfg["providers"].get("ollama", {}).get("api_key", "")
    if not cloud.get("api_key") and local_key and local_key not in ("ollama", "dummy", "not-used"):
        cloud["api_key"] = local_key
    for provider_name, pcfg in cfg.get("providers", {}).items():
        if isinstance(pcfg, dict):
            if pcfg.get("current_model"):
                pcfg["current_model"] = normalize_model_id(provider_name, str(pcfg["current_model"]))
            if isinstance(pcfg.get("custom_models"), list):
                pcfg["custom_models"] = [normalize_model_id(provider_name, str(mid)) for mid in pcfg["custom_models"] if str(mid).strip()]
    _config_cache = cfg
    _config_cache_mtime = mtime
    return cfg


def invalidate_config_cache() -> None:
    global _config_cache, _config_cache_mtime
    _config_cache = None
    _config_cache_mtime = 0.0


def save_config(cfg: dict[str, Any]) -> None:
    global _config_cache, _config_cache_mtime
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_PATH)
    _config_cache = cfg
    try:
        _config_cache_mtime = CONFIG_PATH.stat().st_mtime
    except OSError:
        _config_cache_mtime = 0.0


def clear_model_cache() -> None:
    invalidate_config_cache()
    try:
        CLAUDE_GATEWAY_CACHE.unlink()
    except FileNotFoundError:
        pass
    try:
        MODEL_LIST_CACHE_PATH.unlink()
    except FileNotFoundError:
        pass


def normalize_provider(name: str) -> str:
    key = name.strip().lower().replace("_", "-").replace(" ", "-")
    if key not in PROVIDER_ALIASES:
        raise SystemExit(f"Unknown provider: {name}\nKnown: {', '.join(PROVIDER_LABELS)}")
    return PROVIDER_ALIASES[key]


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-zA-Z0-9_.-]+", "-", s.lower())).strip("-") or "model"


def model_sort_key(model_id: str) -> tuple[str, str]:
    return (model_id.casefold(), model_id)


def sorted_model_ids(ids: list[str]) -> list[str]:
    return sorted(ids, key=model_sort_key)


def unique_model_ids(provider: str, ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        mid = normalize_model_id(provider, str(raw))
        if not mid:
            continue
        key = mid.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(mid)
    return out


def normalize_model_id(provider: str, model_id: str) -> str:
    model_id = strip_claude_context_suffix(model_id).strip()
    if provider == "ollama-cloud" and model_id.endswith(":cloud"):
        return model_id[:-6]
    return model_id


def strip_claude_context_suffix(model_id: str | None) -> str:
    text = str(model_id or "").strip()
    return re.sub(r"\[(?:1m)\]\s*$", "", text, flags=re.IGNORECASE)


def alias_for(provider: str, model_id: str) -> str:
    if provider == "nvidia-hosted" and model_id.startswith("claude-"):
        return model_id
    return f"claude-any-{provider}-{slug(model_id)}"


def unslug_provider_alias(provider: str, alias: str, model_map: dict[str, str]) -> str | None:
    alias = strip_claude_context_suffix(alias)
    if alias in model_map:
        return model_map[alias]
    prefix = f"claude-any-{provider}-"
    if alias.startswith(prefix):
        target_slug = alias[len(prefix):]
        for _, model_id in model_map.items():
            if slug(model_id) == target_slug:
                return model_id
    return None


def display_name(provider: str, model_id: str) -> str:
    label = PROVIDER_LABELS.get(provider, provider).replace("-", " ")
    cleaned = model_id
    if provider == "nvidia-hosted" and cleaned.startswith("claude-nvidia-"):
        cleaned = cleaned[len("claude-"):]
        return cleaned.replace("/", " ").replace("-", " ").replace("_", " ").title().replace("Nvidia", "Nvidia")
    cleaned = cleaned.replace("/", " ").replace("-", " ").replace("_", " ")
    return f"{label} {cleaned}".title().replace("Vllm", "vLLM").replace("Nvidia", "Nvidia")


def model_object(provider: str, model_id: str) -> dict[str, Any]:
    model_id = normalize_model_id(provider, model_id)
    alias = alias_for(provider, model_id)
    return {
        "id": alias,
        "type": "model",
        "display_name": display_name(provider, model_id),
        "created_at": 1700000000,
        "object": "model",
        "created": 1700000000,
        "owned_by": f"claude-any/{provider}",
        "claude_any": {"provider": provider, "upstream_model": model_id},
    }


def join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return base + path[3:]
    return base + path


def read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def meaningful_key_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text and text not in ("dummy", "not-used", "ollama"))


def env_bool(value: str | None, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    text = value.strip().lower()
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n"):
        return False
    return default


def load_dotenv_into_environ(path: Path, *, override: bool = True) -> None:
    for key, value in read_env_file(path).items():
        if override or key not in os.environ:
            os.environ[key] = value


def executable_candidates(name: str) -> list[str]:
    if os.name == "nt" and not Path(name).suffix:
        return [f"{name}.exe", f"{name}.cmd", f"{name}.bat", name]
    return [name]


def executable_extra_dirs() -> list[Path]:
    dirs = [HOME / ".local" / "bin"]
    for env_name in ("UV_INSTALL_DIR", "CARGO_HOME"):
        root = os.environ.get(env_name)
        if root:
            path = Path(root)
            dirs.append(path if path.name == "bin" else path / "bin")
    if os.name == "nt":
        pyver = f"Python{sys.version_info.major}{sys.version_info.minor}"
        for env_name in ("APPDATA", "LOCALAPPDATA"):
            root = os.environ.get(env_name)
            if root:
                dirs.append(Path(root) / "Python" / pyver / "Scripts")
        try:
            import site

            dirs.append(Path(site.getuserbase()) / "Scripts")
        except Exception:
            pass
        dirs.append(Path(sys.executable).resolve().parent / "Scripts")
    else:
        dirs.extend(
            [
                HOME / ".cargo" / "bin",
                HOME / ".npm-global" / "bin",
                HOME / ".bun" / "bin",
                Path(sys.executable).resolve().parent,
                Path("/usr/local/bin"),
                Path("/usr/bin"),
                Path("/bin"),
                Path("/opt/homebrew/bin"),
            ]
        )
    out: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        key = str(directory)
        if key and key not in seen:
            seen.add(key)
            out.append(directory)
    return out


def find_executable(name: str) -> str | None:
    for candidate in executable_candidates(name):
        found = shutil.which(candidate)
        if found:
            return found
    for directory in executable_extra_dirs():
        for candidate in executable_candidates(name):
            path = directory / candidate
            if path.exists():
                return str(path)
    return None


def resolve_executable_for_subprocess(command: str) -> str:
    command = str(command or "").strip()
    if not command:
        return command
    pathish = Path(command).is_absolute() or os.sep in command or bool(os.altsep and os.altsep in command)
    if pathish:
        return command
    return find_executable(command) or command


def resolve_mcp_server_process(command: str, args: list[str]) -> tuple[str, list[str]]:
    command = str(command or "").strip()
    resolved = resolve_executable_for_subprocess(command)
    name = Path(command).name.lower()
    if resolved == command and name in ("uvx", "uvx.exe", "uvx.cmd", "uvx.bat"):
        uv = find_executable("uv")
        if uv:
            return uv, ["tool", "run", *args]
        if importlib.util.find_spec("uv") is not None:
            return sys.executable, ["-m", "uv", "tool", "run", *args]
    return resolved, args


def shell_command_string(args: list[str]) -> str:
    if os.name == "nt":
        # Claude Code on Windows runs hook commands through sh/bash, which treats
        # backslashes in unquoted Windows paths as escape characters (so
        # "C:\Users\djlov" becomes "C:Usersdjlov"). Convert backslashes to
        # forward slashes for path-like args (Python and sh both accept them on
        # Windows) and use POSIX quoting.
        normalized: list[str] = []
        for arg in args:
            looks_like_path = "\\" in arg and (
                (len(arg) >= 2 and arg[1] == ":")
                or arg.startswith("\\\\")
                or arg.endswith((".py", ".exe", ".cmd", ".bat", ".ps1"))
            )
            if looks_like_path:
                arg = arg.replace("\\", "/")
            normalized.append(shlex.quote(arg))
        return " ".join(normalized)
    return " ".join(shlex.quote(arg) for arg in args)


def find_tool_guard_script() -> Path | None:
    candidates = [
        Path(__file__).resolve().with_name("claude-any-tool-guard.py"),
        HOME / ".local" / "bin" / "claude-any-tool-guard.py",
        HOME / ".local" / "bin" / "claude-any-tool-guard",
    ]
    found = find_executable("claude-any-tool-guard")
    if found:
        candidates.append(Path(found))
    found_py = find_executable("claude-any-tool-guard.py")
    if found_py:
        candidates.append(Path(found_py))
    for path in candidates:
        if path.exists():
            return path
    return None


def claude_any_tool_guard_command() -> str | None:
    script = find_tool_guard_script()
    if script is None:
        return None
    if script.suffix == ".py":
        return shell_command_string([sys.executable, str(script)])
    return shell_command_string([str(script)])


TOOL_GUARD_EVENTS_WITH_TOOL_MATCHER: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "PermissionDenied",
)

TOOL_GUARD_EVENTS_WITHOUT_MATCHER: tuple[str, ...] = (
    "PostToolBatch",
    "SessionStart",
    "SessionEnd",
    "Setup",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "Stop",
    "StopFailure",
    "InstructionsLoaded",
    "ConfigChange",
    "CwdChanged",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "PreCompact",
    "PostCompact",
    "WorktreeCreate",
    "WorktreeRemove",
    "Elicitation",
    "ElicitationResult",
)


def install_tool_guard_hooks() -> None:
    command = claude_any_tool_guard_command()
    if not command:
        print("Claude Any warning: tool guard hook was not installed; claude-any-tool-guard was not found.", flush=True)
        return

    if CLAUDE_SETTINGS_PATH.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(settings, dict):
                settings = {}
        except Exception as exc:
            print(f"Claude Any warning: could not read {CLAUDE_SETTINGS_PATH} ({type(exc).__name__}); tool guard hook was not installed.", flush=True)
            return
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        print(f"Claude Any warning: {CLAUDE_SETTINGS_PATH} has non-object hooks; tool guard hook was not installed.", flush=True)
        return

    changed = False
    all_events: tuple[tuple[str, bool], ...] = tuple(
        (event, True) for event in TOOL_GUARD_EVENTS_WITH_TOOL_MATCHER
    ) + tuple(
        (event, False) for event in TOOL_GUARD_EVENTS_WITHOUT_MATCHER
    )
    for event, with_matcher in all_events:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            print(f"Claude Any warning: {CLAUDE_SETTINGS_PATH} hooks.{event} is not a list; tool guard hook was not installed.", flush=True)
            return
        existing = False
        for group in groups:
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if isinstance(handler, dict) and "claude-any-tool-guard" in str(handler.get("command", "")):
                    existing = True
                    if handler.get("command") != command:
                        handler["command"] = command
                        changed = True
        if existing:
            continue
        group: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
        if with_matcher:
            group["matcher"] = "*"
        groups.append(group)
        changed = True

    if changed:
        CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CLAUDE_SETTINGS_PATH.with_name(f"{CLAUDE_SETTINGS_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(CLAUDE_SETTINGS_PATH)


STATUSLINE_SCRIPT = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("CLAUDE_ANY_CONFIG_DIR") or (HOME / ".config" / "claude-any"))
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = CONFIG_DIR / "rate-limit-state.json"
ACTIVITY_PATH = CONFIG_DIR / "router-activity.json"
CONTEXT_PATH = CONFIG_DIR / "context-usage.json"
PALETTE = (203, 209, 215, 221, 229, 187, 151, 116, 111, 147, 183, 219)


def load_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def color(text):
    if os.environ.get("CLAUDE_ANY_STATUSLINE_ANSI", "1").lower() in ("0", "false", "no"):
        return text
    phase = int(time.monotonic() * 8)
    out = []
    for i, ch in enumerate(text):
        if ch.isspace():
            out.append(ch)
        else:
            out.append(f"\033[1;38;5;{PALETTE[(phase + i) % len(PALETTE)]}m{ch}\033[0m")
    return "".join(out)


def gray(text):
    if os.environ.get("CLAUDE_ANY_STATUSLINE_ANSI", "1").lower() in ("0", "false", "no"):
        return text
    return f"\033[38;5;245m{text}\033[0m"


def token_text(value):
    try:
        return f"{int(value):,} tok"
    except Exception:
        return f"{value} tok"


def token_part(value, muted=False):
    text = token_text(value)
    return gray(text) if muted else color(text)


def context_status_text(context, provider, model):
    if not isinstance(context, dict):
        return ""
    if str(context.get("provider") or "") != str(provider or ""):
        return ""
    try:
        age = time.time() - float(context.get("updated_at") or 0)
    except Exception:
        age = 999999
    if age < 0 or age > 3600:
        return ""
    try:
        tokens = int(context.get("tokens") or 0)
    except Exception:
        tokens = 0
    if tokens <= 0:
        return ""
    try:
        limit = int(context.get("context_limit") or 0)
    except Exception:
        limit = 0
    if limit > 0:
        pct = (tokens / limit) * 100.0
        return f"ctx {tokens:,}/{limit:,} tok ({pct:.1f}%)"
    return f"ctx {tokens:,} tok"


def _as_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def session_context_status_text(session):
    if not isinstance(session, dict):
        return ""
    context_window = session.get("context_window")
    if not isinstance(context_window, dict):
        return ""
    usage = context_window.get("current_usage")
    if not isinstance(usage, dict):
        return ""
    tokens = (
        _as_int(usage.get("input_tokens"))
        + _as_int(usage.get("cache_creation_input_tokens"))
        + _as_int(usage.get("cache_read_input_tokens"))
    )
    if tokens <= 0:
        tokens = _as_int(context_window.get("total_input_tokens"))
    if tokens <= 0:
        return ""
    limit = _as_int(context_window.get("context_window_size"))
    pct = context_window.get("used_percentage")
    if limit > 0:
        try:
            pct_value = float(pct) if pct is not None else (tokens / limit) * 100.0
        except Exception:
            pct_value = (tokens / limit) * 100.0
        return f"ctx {tokens:,}/{limit:,} tok ({pct_value:.1f}%)"
    return f"ctx {tokens:,} tok"


def is_claude_any_session(session):
    if os.environ.get("CLAUDE_ANY_PROVIDER") or os.environ.get("CLAUDE_ANY_MODEL_ALIAS"):
        return True
    if os.environ.get("CLAUDE_ANY_STATUSLINE_FORCE", "").lower() in ("1", "true", "yes", "on"):
        return True
    model_name = ((session.get("model") or {}).get("display_name") if isinstance(session.get("model"), dict) else None) or ""
    return str(model_name).startswith("claude-any-")


def display_capacity(rpm):
    if rpm <= 1:
        return rpm
    reserve = 1 if rpm <= 20 else max(1, int((rpm * 0.05) + 0.999))
    return max(1, rpm - reserve)


def main():
    try:
        session = json.load(sys.stdin)
        if not isinstance(session, dict):
            session = {}
    except Exception:
        session = {}
    if not is_claude_any_session(session):
        return
    cfg = load_json(CONFIG_PATH, {})
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    provider = str(cfg.get("current_provider") or "")
    pcfg = providers.get(provider) if isinstance(providers.get(provider), dict) else {}
    router_debug_external = bool(cfg.get("router_debug_external_access", False))
    rpm_status = bool(pcfg.get("rate_limit_status", True))
    model = str(pcfg.get("current_model") or "")
    raw_rpm = pcfg.get("rate_limit_rpm")
    if raw_rpm is None and provider in ("nvidia-hosted", "self-hosted-nim", "ollama", "ollama-cloud"):
        raw_rpm = 40
    try:
        rpm = int(raw_rpm)
    except Exception:
        rpm = 40
    state = load_json(STATE_PATH, {})
    activity = load_json(ACTIVITY_PATH, {})
    context = load_json(CONTEXT_PATH, {})
    now = time.time()
    key = f"{provider}:__global__" if provider else ""
    entry = state.get(key) if key else None
    if not isinstance(entry, dict):
        legacy_key = f"{provider}:{model}" if provider and model else ""
        entry = state.get(legacy_key) if legacy_key else None
    if not isinstance(entry, dict):
        prefix = f"{provider}:"
        candidates = [(k, v) for k, v in state.items() if isinstance(k, str) and k.startswith(prefix) and isinstance(v, dict)]
        if not candidates:
            candidates = [(k, v) for k, v in state.items() if isinstance(v, dict)]
        if candidates:
            key, entry = max(candidates, key=lambda item: float(item[1].get("updated_at") or 0))
    timestamps = entry.get("timestamps") if isinstance(entry, dict) else []
    if isinstance(entry, dict):
        try:
            rpm = int(entry.get("rpm") or rpm)
        except Exception:
            pass
    try:
        last_wait = float(entry.get("last_wait") or 0.0) if isinstance(entry, dict) else 0.0
    except Exception:
        last_wait = 0.0
    try:
        penalty_until = float(entry.get("penalty_until") or 0.0) if isinstance(entry, dict) else 0.0
    except Exception:
        penalty_until = 0.0
    try:
        updated_at = float(entry.get("updated_at") or 0.0) if isinstance(entry, dict) else 0.0
    except Exception:
        updated_at = 0.0
    server_remaining = entry.get("server_remaining") if isinstance(entry, dict) else None
    server_reset_seconds = entry.get("server_reset_seconds") if isinstance(entry, dict) else None
    server_rpm = entry.get("server_rpm") if isinstance(entry, dict) else None
    used = len([ts for ts in (timestamps or []) if isinstance(ts, (int, float)) and 0.0 <= now - float(ts) < 60.0])
    model_name = ((session.get("model") or {}).get("display_name") if isinstance(session.get("model"), dict) else None) or model or "model"
    current_dir = ((session.get("workspace") or {}).get("current_dir") if isinstance(session.get("workspace"), dict) else None) or session.get("cwd") or ""
    dir_name = Path(current_dir).name if current_dir else ""
    left = f"[{model_name}]"
    if dir_name:
        left += f" {dir_name}"
    status_parts = []
    ctx_text = session_context_status_text(session) or context_status_text(context, provider, model)
    if ctx_text:
        status_parts.append(gray(ctx_text))
    if router_debug_external:
        status_parts.append(color("debug external"))
    if rpm_status:
        if rpm > 0:
            shown_limit = display_capacity(rpm)
            shown_used = min(used, shown_limit)
            rpm_text = f"RPM used: {shown_used}/{shown_limit}"
        else:
            rpm_text = f"RPM used: {used}/min (unmanaged)"
        if server_rpm or server_remaining is not None or server_reset_seconds is not None:
            parts = []
            if server_remaining is not None:
                parts.append(f"remaining {server_remaining}")
            if server_rpm:
                parts.append(f"limit {server_rpm}")
            try:
                if server_reset_seconds is not None and float(server_reset_seconds) > 0:
                    parts.append(f"reset {float(server_reset_seconds):.0f}s")
            except Exception:
                pass
            if parts:
                rpm_text += " | server " + ", ".join(parts)
        if penalty_until > now:
            rpm_text += f" | wait {max(0.0, penalty_until - now):.0f}s"
        elif last_wait >= 0.5 and 0.0 <= now - updated_at < 60.0:
            rpm_text += f" | wait {last_wait:.1f}s"
        status_parts.append(color(rpm_text))
    activity_text = ""
    if isinstance(activity, dict):
        try:
            age = now - float(activity.get("updated_at") or 0)
        except Exception:
            age = 999999
        if 0 <= age < 180:
            event = str(activity.get("event") or "")
            if event == "retry":
                activity_text = color(f"retry {activity.get('attempt')}/{activity.get('total')}")
                wait = activity.get("wait")
                try:
                    if rpm_status and wait is not None and float(wait) > 0:
                        activity_text += " " + color(f"wait {float(wait):.0f}s")
                except Exception:
                    pass
                tokens = activity.get("tokens")
                if tokens:
                    activity_text += " " + color("last input") + " " + token_part(tokens, muted=rpm_status)
            elif event == "request":
                tokens = activity.get("tokens")
                activity_text = color(f"upstream {age:.0f}s")
                if tokens:
                    activity_text += " " + token_part(tokens, muted=rpm_status)
                output_tokens = activity.get("output_tokens")
                if output_tokens:
                    activity_text += " " + color("->") + " " + token_part(output_tokens, muted=rpm_status)
                chunks = activity.get("chunks")
                if chunks:
                    try:
                        activity_text += " " + color(f"({int(chunks):,} chunks)")
                    except Exception:
                        activity_text += " " + color(f"({chunks} chunks)")
            elif event in ("success", "error"):
                activity_text = color(f"{event} {age:.0f}s")
    if activity_text:
        status_parts.append(activity_text)
    status_text = " | ".join(status_parts)
    if status_text:
        print(f"{left} | {status_text}")
    else:
        print(left)


if __name__ == "__main__":
    main()
'''


def install_claude_any_statusline() -> None:
    try:
        CLAUDE_ANY_STATUSLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CLAUDE_ANY_STATUSLINE_PATH.exists() or CLAUDE_ANY_STATUSLINE_PATH.read_text(encoding="utf-8") != STATUSLINE_SCRIPT:
            CLAUDE_ANY_STATUSLINE_PATH.write_text(STATUSLINE_SCRIPT, encoding="utf-8")
        try:
            os.chmod(CLAUDE_ANY_STATUSLINE_PATH, 0o700)
        except Exception:
            pass
        if CLAUDE_SETTINGS_PATH.exists():
            try:
                settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
                if not isinstance(settings, dict):
                    settings = {}
            except Exception as exc:
                print(f"Claude Any warning: could not read {CLAUDE_SETTINGS_PATH} ({type(exc).__name__}); status line was not installed.", flush=True)
                return
        else:
            settings = {}
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(CLAUDE_ANY_STATUSLINE_PATH))}"
        current = settings.get("statusLine")
        if isinstance(current, dict) and current.get("command") == command:
            return
        settings["statusLine"] = {
            "type": "command",
            "command": command,
            "padding": 0,
            "refreshInterval": 1000,
        }
        CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CLAUDE_SETTINGS_PATH.with_name(f"{CLAUDE_SETTINGS_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(CLAUDE_SETTINGS_PATH)
    except Exception as exc:
        print(f"Claude Any warning: could not install status line ({type(exc).__name__}: {exc}).", flush=True)


ADVISOR_SLASH_COMMAND = """---
description: Run the selected claude-any Advisor Model
argument-hint: [question or focus]
---

CLAUDE_ANY_ADVISOR_CALL

Focus: $ARGUMENTS

Use the Advisor Model selected in the claude-any launch menu. If the Advisor Model is off, explain how to enable it. Otherwise review the current conversation, tool history, and task state. Return concise guidance with the blocker, next concrete action, and validation step.
"""

ROUTER_DEBUG_SLASH_COMMAND = """---
description: Toggle claude-any router external debug access
argument-hint: [on|off|status]
---

CLAUDE_ANY_ROUTER_DEBUG_ACCESS

Value: $ARGUMENTS

Toggle claude-any router debug external access. With no argument, this toggles the current state. Use `on`, `off`, or `status` for explicit control.
"""

def install_claude_any_slash_commands() -> None:
    try:
        CLAUDE_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
        commands = {
            "advisor.md": ADVISOR_SLASH_COMMAND,
            "router-debug.md": ROUTER_DEBUG_SLASH_COMMAND,
        }
        stale_channel = CLAUDE_COMMANDS_DIR / "channel.md"
        if stale_channel.exists():
            try:
                stale_text = stale_channel.read_text(encoding="utf-8", errors="replace")
                if "CLAUDE_ANY_CHANNEL_BRIDGE" in stale_text or "claude-any channel bridge" in stale_text:
                    stale_channel.unlink()
            except Exception:
                pass
        for name, content in commands.items():
            path = CLAUDE_COMMANDS_DIR / name
            if path.exists() and path.read_text(encoding="utf-8") == content:
                continue
            path.write_text(content, encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
    except Exception as exc:
        print(f"Claude Any warning: could not install claude-any slash commands ({type(exc).__name__}: {exc}).", flush=True)


def http_json(url: str, headers: dict[str, str] | None = None, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def current_log_level() -> int:
    """Resolve effective log level. Priority: log-level file > env var > default.
    File mtime + 1s wall cache to keep overhead near zero on hot paths."""
    now = time.time()
    cache = _LOG_LEVEL_CACHE
    if cache["value"] is not None and (now - float(cache["checked_at"])) < 1.0:
        return int(cache["value"])
    level: int | None = None
    try:
        if LOG_LEVEL_PATH.exists():
            mtime = LOG_LEVEL_PATH.stat().st_mtime
            if cache["value"] is not None and mtime == cache["file_mtime"]:
                cache["checked_at"] = now
                return int(cache["value"])
            txt = LOG_LEVEL_PATH.read_text(encoding="utf-8").strip().upper()
            if txt in LOG_LEVELS:
                level = LOG_LEVELS[txt]
            elif txt.isdigit():
                level = max(0, min(5, int(txt)))
            cache["file_mtime"] = mtime
    except Exception:
        pass
    if level is None:
        env = os.environ.get("CLAUDE_ANY_LOG_LEVEL", "").strip().upper()
        if env in LOG_LEVELS:
            level = LOG_LEVELS[env]
        elif env.isdigit():
            level = max(0, min(5, int(env)))
    if level is None:
        level = LOG_LEVEL_DEFAULT
    cache["value"] = level
    cache["checked_at"] = now
    return level


def reset_log_level_cache() -> None:
    _LOG_LEVEL_CACHE.update({"value": None, "checked_at": 0.0, "file_mtime": 0.0})


def log_level_name(value: int | None = None) -> str:
    if value is None:
        value = current_log_level()
    return str(LOG_LEVEL_NAMES.get(int(value), value))


def log_level_source() -> str:
    if LOG_LEVEL_PATH.exists():
        return "file"
    if os.environ.get("CLAUDE_ANY_LOG_LEVEL", "").strip():
        return "env"
    return "default"


def log_level_status() -> str:
    return f"{log_level_name()} ({log_level_source()})"


def normalize_log_level(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("log level is empty")
    upper = raw.upper()
    aliases = {
        "OFF": "SILENT",
        "NONE": "SILENT",
        "QUIET": "SILENT",
        "WARNING": "WARN",
        "WARNINGS": "WARN",
    }
    upper = aliases.get(upper, upper)
    if upper in ("DEFAULT", "RESET", "UNSET", "AUTO"):
        return None
    if upper in LOG_LEVELS:
        return upper
    if upper.isdigit():
        numeric = max(0, min(5, int(upper)))
        return LOG_LEVEL_NAMES[numeric]
    raise ValueError(f"unknown log level: {value}")


def set_log_level_config(value: str) -> list[str]:
    try:
        level = normalize_log_level(value)
    except ValueError as exc:
        known = ", ".join(LOG_LEVELS)
        return [f"{exc}. Known levels: {known}, DEFAULT."]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if level is None:
        try:
            LOG_LEVEL_PATH.unlink()
        except FileNotFoundError:
            pass
        reset_log_level_cache()
        return [f"Log level reset to {log_level_status()}."]
    LOG_LEVEL_PATH.write_text(level + "\n", encoding="utf-8")
    try:
        os.chmod(LOG_LEVEL_PATH, 0o600)
    except Exception:
        pass
    reset_log_level_cache()
    return [f"Log level set to {level}."]


def router_log(level: str, message: str) -> None:
    """Append a line to router.log if the active level allows it.
    Rotates router.log when it exceeds ROUTER_LOG_MAX_BYTES."""
    threshold = LOG_LEVELS.get(level, 0)
    if threshold <= 0 or threshold > current_log_level():
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > ROUTER_LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("%s [%s] %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), level, message))
    except Exception:
        pass


def _truncate_for_dump(value: Any, max_len: int = 4000) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    except Exception:
        text = str(value)
    if len(text) > max_len:
        return text[:max_len] + f"...<truncated {len(text) - max_len} chars>"
    return value


def resolve_blocked_tools(provider: str, pcfg: dict[str, Any]) -> set[str]:
    """Return the set of tool names to strip from upstream requests.
    `pcfg['blocked_tools']` overrides: None/missing => default list, False/[] => disable, list => explicit set."""
    if provider == "anthropic":
        return set()
    override = pcfg.get("blocked_tools", None)
    if override is False:
        return set()
    if isinstance(override, list):
        return {str(name).strip() for name in override if str(name).strip()}
    return set(DEFAULT_BLOCKED_TOOLS_NON_ANTHROPIC)


def forced_tool_choice_name(body: dict[str, Any]) -> str | None:
    tool_choice = body.get("tool_choice") if isinstance(body.get("tool_choice"), dict) else None
    if not tool_choice:
        return None
    if tool_choice.get("type") != "tool":
        return None
    name = tool_choice.get("name")
    return name if isinstance(name, str) and name else None


def tool_names_in_body(body: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    tools = body.get("tools")
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            names.add(tool["name"])
    return names


def synthetic_tool_use_response(model: str, tool_name: str, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
    now = int(time.time() * 1000)
    return {
        "id": f"msg_claude_any_tool_{now}",
        "type": "message",
        "role": "assistant",
        "model": model or "claude-any-router",
        "content": [
            {
                "type": "tool_use",
                "id": f"toolu_claude_any_{tool_name}_{now}",
                "name": tool_name,
                "input": tool_input or {},
            }
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def has_tool(body: dict[str, Any], name: str) -> bool:
    return name in tool_names_in_body(body)


def _message_content_blocks(message: dict[str, Any]) -> list[Any]:
    content = message.get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def plan_mode_active(body: dict[str, Any]) -> bool:
    """Infer Claude Code Plan Mode from tool history and plan-mode attachments."""
    active = False
    tool_names_by_id: dict[str, str] = {}
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        attachment = message.get("attachment")
        if isinstance(attachment, dict):
            attachment_type = attachment.get("type")
            if attachment_type in {"plan_mode", "plan_mode_reentry"}:
                active = True
            elif attachment_type == "plan_mode_exit":
                active = False
        if message.get("role") == "assistant":
            for block in _message_content_blocks(message):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                name = str(block.get("name") or "")
                if tool_id and name:
                    tool_names_by_id[tool_id] = name
        elif message.get("role") == "user":
            for block in _message_content_blocks(message):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tool_use_id = str(block.get("tool_use_id") or "")
                    tool_name = tool_names_by_id.get(tool_use_id)
                    if tool_name == "EnterPlanMode":
                        active = True
                    elif tool_name == "ExitPlanMode":
                        active = False
                elif block.get("type") in {"plan_mode", "plan_mode_reentry"}:
                    active = True
                elif block.get("type") == "plan_mode_exit":
                    active = False
    return active


def has_plan_mode_exit(body: dict[str, Any]) -> bool:
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        attachment = message.get("attachment")
        if isinstance(attachment, dict) and attachment.get("type") == "plan_mode_exit":
            return True
        if message.get("role") != "assistant":
            continue
        for block in _message_content_blocks(message):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "ExitPlanMode":
                return True
    return False


def plan_mode_tool_name_for_emit(body: dict[str, Any], name: str, tool_input: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    active = plan_mode_active(body)
    if name == "EnterPlanMode" and active:
        router_log("WARN", "dropped repeated EnterPlanMode while plan mode is active")
        return None, tool_input
    if name == "ExitPlanMode" and not active:
        router_log("WARN", "dropped ExitPlanMode while plan mode is not active")
        return None, tool_input
    return name, tool_input


def is_guard_feedback_text(text: str) -> bool:
    stripped = (text or "").strip()
    return (
        stripped.startswith("Stop hook feedback:")
        or stripped.startswith("Claude Any plan guard:")
        or PLAN_GUARD_MARKER in stripped
    )


def latest_user_text(body: dict[str, Any]) -> str:
    for message in reversed(body.get("messages") or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        if message.get("isMeta") is True:
            continue
        content = message.get("content")
        if isinstance(content, str):
            if is_guard_feedback_text(content):
                continue
            return content
        if not isinstance(content, list):
            # Claude Code can inject user-role attachment records such as
            # plan_mode_exit. They are state metadata, not new user intent.
            continue
        # Claude Code sends tool_result blocks as user-role messages. Those are
        # not new user intent; treating them as prompts can repeatedly trigger
        # synthetic self-tools such as EnterPlanMode.
        text_blocks = [
            block for block in content
            if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text")
        ]
        text = anthropic_content_to_text(text_blocks)
        if not text or is_guard_feedback_text(text):
            continue
        return text
    return ""


def router_debug_message_preview_chars(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or load_config()
    env = os.environ.get("CLAUDE_ANY_ROUTER_MESSAGE_PREVIEW_CHARS", "").strip()
    if env:
        value = positive_int(env)
        return min(value or 0, 4000)
    value = positive_int(cfg.get("router_debug_message_preview_chars"))
    return min(value or 0, 4000)


def router_event_message_preview(body: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    limit = router_debug_message_preview_chars(cfg)
    if limit <= 0:
        return {}
    text = latest_user_text(body).strip()
    if not text:
        return {"message_preview_chars": limit, "message_preview": "", "message_preview_truncated": False}
    normalized = re.sub(r"\s+", " ", redact_sensitive_text(text))
    truncated = len(normalized) > limit
    return {
        "message_preview_chars": limit,
        "message_preview": normalized[:limit].rstrip(),
        "message_preview_truncated": truncated,
    }


def likely_implementation_planning_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) >= 120:
        return True
    # Multi-line prompts usually carry enough task structure that a one-line
    # "I'll make a plan" style response is not a useful final answer.
    non_empty_lines = [line for line in (text or "").splitlines() if line.strip()]
    if len(non_empty_lines) >= 3 and len(normalized) >= 80:
        return True
    return False


def non_actionable_short_response(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return True
    # Language-agnostic: for a long implementation request, a short single-line
    # text response with no tool call is not actionable. Do not inspect words.
    if len(normalized) <= 80 and "\n" not in (text or ""):
        return True
    if len(normalized) <= 160 and "\n" not in (text or "") and not re.search(r"[`{};/\\\\]|https?://", normalized):
        return True
    return False


def should_auto_enter_plan_mode(body: dict[str, Any], response_text: str, tool_calls: list[dict[str, Any]]) -> bool:
    if tool_calls:
        return False
    if not has_tool(body, "EnterPlanMode"):
        return False
    if plan_mode_active(body):
        return False
    if has_plan_mode_exit(body):
        return False
    if latest_tool_result_indicates_completed_work(body):
        return False
    if not non_actionable_short_response(response_text):
        return False
    return likely_implementation_planning_request(latest_user_text(body))


WORK_CONTINUATION_RESULT_TOOLS: frozenset[str] = frozenset(
    {
        "Bash",
        "Glob",
        "Grep",
        "LS",
        "Read",
        "Write",
        "Edit",
        "MultiEdit",
        "TaskCreate",
        "TaskList",
        "TaskUpdate",
        "TaskStop",
    }
)


WORK_COMPLETION_RESULT_TOOLS: frozenset[str] = frozenset(
    {
        "Write",
        "Edit",
        "MultiEdit",
        "TaskUpdate",
        "TaskStop",
    }
)


def bash_command_looks_mutating(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command or "").strip()
    if not normalized:
        return False
    return bool(
        re.search(
            r"(^|[;&|]\s*|\b)(rm|rmdir|mv|cp|mkdir|touch|chmod|chown|ln|install|git\s+(commit|push|pull|merge|rebase|checkout|switch|restore|reset|clean)|npm\s+(install|update|run|publish)|pnpm\s+(install|update|run|publish)|yarn\s+(install|add|run|publish)|python\d*\s+-m\s+pip\s+install|pip\d*\s+install|docker\s+(run|compose|build|up|down|rm|rmi)|kubectl\s+(apply|delete|create|replace|patch))\b",
            normalized,
        )
    )


def latest_user_tool_result_details(body: dict[str, Any]) -> list[dict[str, Any]]:
    tools_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    latest: list[dict[str, Any]] = []
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if message.get("role") == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                name = str(block.get("name") or "")
                tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                if tool_id and name:
                    tools_by_id[tool_id] = (name, tool_input)
        elif message.get("role") == "user" and isinstance(content, list):
            current: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                name, tool_input = tools_by_id.get(tool_use_id, ("tool", {}))
                current.append(
                    {
                        "name": name,
                        "input": tool_input,
                        "text": anthropic_content_to_text(block.get("content", "")),
                        "is_error": bool(block.get("is_error")),
                    }
                )
            if current:
                latest = current
    return latest


def latest_tool_result_indicates_completed_work(body: dict[str, Any]) -> bool:
    details = latest_user_tool_result_details(body)
    if not details:
        return False
    for item in details:
        if item.get("is_error"):
            continue
        name = str(item.get("name") or "")
        tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
        if name in WORK_COMPLETION_RESULT_TOOLS:
            return True
        if name == "Bash" and bash_command_looks_mutating(str(tool_input.get("command") or "")):
            return True
    return False


def latest_user_tool_result_names(body: dict[str, Any]) -> list[str]:
    tool_names_by_id: dict[str, str] = {}
    latest: list[str] = []
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if message.get("role") == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                name = str(block.get("name") or "")
                if tool_id and name:
                    tool_names_by_id[tool_id] = name
        elif message.get("role") == "user" and isinstance(content, list):
            current: list[str] = []
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                if tool_use_id:
                    current.append(tool_names_by_id.get(tool_use_id, "tool"))
            if current:
                latest = current
    return latest


def latest_user_tool_result_text(body: dict[str, Any]) -> str:
    latest = ""
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user" or not isinstance(message.get("content"), list):
            continue
        parts: list[str] = []
        for block in message.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            parts.append(anthropic_content_to_text(block.get("content", "")))
        if parts:
            latest = "\n".join(part for part in parts if part)
    return latest


def recent_synthetic_tasklist_count(body: dict[str, Any]) -> int:
    count = 0
    for message in reversed(body.get("messages") or []):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            break
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, list):
            continue
        found_keepalive = False
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") == "TaskList" and str(block.get("id") or "").startswith("toolu_ollama_keepalive_"):
                found_keepalive = True
        if found_keepalive:
            count += 1
    return count


def tasklist_result_has_active_work(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    if not normalized:
        return False
    # This parses Claude Code's task-list tool output, not user-facing prose.
    for label in ("in progress", "open", "pending"):
        for match in re.finditer(rf"\b(\d+)\s+{re.escape(label)}\b", normalized):
            if int(match.group(1)) > 0:
                return True
    return False


def latest_assistant_text(body: dict[str, Any]) -> str:
    for message in reversed(body.get("messages") or []):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        return anthropic_content_to_text(message.get("content"))
    return ""


def short_resume_prompt(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return False
    if len(normalized) > 32:
        return False
    # Language-agnostic: a very short imperative with no question or code-like
    # syntax after an unfinished assistant turn is a request to proceed.
    return not re.search(r"[?？`{};/\\\\]|https?://", normalized)


def should_keep_work_alive_with_tasklist(body: dict[str, Any], response_text: str, tool_calls: list[dict[str, Any]]) -> bool:
    if tool_calls:
        return False
    if not has_tool(body, "TaskList"):
        return False
    latest_names = latest_user_tool_result_names(body)
    if not latest_names:
        return False
    latest_result_text = latest_user_tool_result_text(body)
    if latest_names == ["TaskList"] and "No tasks found" in latest_result_text:
        return False
    if "TaskList" in latest_names:
        max_keepalive = 6 if tasklist_result_has_active_work(latest_result_text) else 2
        if recent_synthetic_tasklist_count(body) >= max_keepalive:
            return False
    if not any(name in WORK_CONTINUATION_RESULT_TOOLS for name in latest_names):
        return False
    if latest_tool_result_indicates_completed_work(body) and response_text.strip():
        return False
    return non_actionable_short_response(response_text)


def maybe_handle_plan_mode_tool_choice(handler: BaseHTTPRequestHandler, provider: str, body: dict[str, Any]) -> bool:
    """Support Claude Code's forced Plan-mode entry without relying on upstream model behavior."""
    if provider == "anthropic":
        return False
    name = forced_tool_choice_name(body)
    if name != "EnterPlanMode":
        return False
    # Claude Code may force this tool when the user uses /plan or toggles Plan mode.
    # Returning a valid tool_use locally is more reliable than asking arbitrary
    # OpenAI/Ollama-compatible backends to select an internal Claude Code tool.
    available = tool_names_in_body(body)
    if available and name not in available:
        return False
    emit_name = name
    tool_input: dict[str, Any] = {}
    if plan_mode_active(body):
        router_log("WARN", f"ignored forced {name} tool_choice because plan mode is already active")
        return False
    else:
        router_log("INFO", f"synthesized {name} tool_use for {provider} forced tool_choice")
    write_json(handler, synthetic_tool_use_response(str(body.get("model") or ""), emit_name, tool_input))
    return True


def filter_blocked_tools(provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Strip Claude-Code self-tools the upstream model shouldn't see (e.g. EnterPlanMode).
    Returns a (possibly new) body dict."""
    blocked = resolve_blocked_tools(provider, pcfg)
    if not blocked:
        return body
    tools = body.get("tools")
    tool_choice = body.get("tool_choice") if isinstance(body.get("tool_choice"), dict) else None
    tool_choice_name = tool_choice.get("name") if tool_choice else None
    must_drop_tool_choice = isinstance(tool_choice_name, str) and tool_choice_name in blocked
    if not isinstance(tools, list) or not tools:
        if not must_drop_tool_choice:
            return body
        new_body = dict(body)
        new_body.pop("tool_choice", None)
        router_log("WARN", f"removed blocked tool_choice for {provider}: {tool_choice_name}")
        return new_body
    kept: list[Any] = []
    dropped: list[str] = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if isinstance(name, str) and name in blocked:
            dropped.append(name)
            continue
        kept.append(tool)
    if not dropped:
        if not must_drop_tool_choice:
            return body
        new_body = dict(body)
        new_body.pop("tool_choice", None)
        router_log("WARN", f"removed blocked tool_choice for {provider}: {tool_choice_name}")
        return new_body
    router_log("INFO", f"filtered upstream tools for {provider}: {', '.join(sorted(set(dropped)))}")
    new_body = dict(body)
    new_body["tools"] = kept
    if must_drop_tool_choice:
        new_body.pop("tool_choice", None)
        router_log("WARN", f"removed blocked tool_choice for {provider}: {tool_choice_name}")
    return new_body


def dump_request_for_trace(provider: str, path: str, body: dict[str, Any]) -> None:
    """At TRACE level, append a redacted snapshot of an inbound /v1/messages body
    (tools list, system prompt summary, message count) to requests.jsonl.
    Used to capture tool definitions Claude Code injects (e.g. EnterPlanMode)."""
    if current_log_level() < LOG_LEVELS["TRACE"]:
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if REQUEST_DUMP_PATH.exists() and REQUEST_DUMP_PATH.stat().st_size > REQUEST_DUMP_MAX_BYTES:
            REQUEST_DUMP_PATH.replace(REQUEST_DUMP_PATH.with_suffix(".jsonl.1"))
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": provider,
            "path": path,
            "model": body.get("model"),
            "stream": body.get("stream"),
            "messages_count": len(body.get("messages") or []),
            "system": _truncate_for_dump(body.get("system")),
            "tools": body.get("tools"),
        }
        with REQUEST_DUMP_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def dump_response_for_trace(provider: str, model: str, text_so_far: str, tool_calls: list[dict[str, Any]], stop_reason: str | None, input_tokens: int, output_tokens: int, last_chunk: dict[str, Any] | None = None) -> None:
    """At TRACE level, append a per-response summary to responses.jsonl.
    Used to confirm what GLM-5.1 (and other upstream models) actually sent
    when the Claude Code session appears to stall."""
    if current_log_level() < LOG_LEVELS["TRACE"]:
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if RESPONSE_DUMP_PATH.exists() and RESPONSE_DUMP_PATH.stat().st_size > RESPONSE_DUMP_MAX_BYTES:
            RESPONSE_DUMP_PATH.replace(RESPONSE_DUMP_PATH.with_suffix(".jsonl.1"))
        text_truncated = text_so_far
        text_full_len = len(text_so_far)
        if text_full_len > RESPONSE_DUMP_TEXT_LIMIT:
            text_truncated = text_so_far[:RESPONSE_DUMP_TEXT_LIMIT] + f"...<truncated {text_full_len - RESPONSE_DUMP_TEXT_LIMIT} chars>"
        tool_summary: list[dict[str, Any]] = []
        for call in tool_calls:
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            tool_summary.append({
                "name": (fn or {}).get("name"),
                "arguments": (fn or {}).get("arguments"),
            })
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": provider,
            "model": model,
            "stop_reason": stop_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "text_full_len": text_full_len,
            "tool_call_count": len(tool_calls),
            "text": text_truncated,
            "tool_calls": tool_summary,
            "done_reason": (last_chunk or {}).get("done_reason"),
        }
        with RESPONSE_DUMP_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def append_tool_call_log(event: str, payload: dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if TOOL_CALL_LOG_PATH.exists() and TOOL_CALL_LOG_PATH.stat().st_size > 2_000_000:
            TOOL_CALL_LOG_PATH.replace(TOOL_CALL_LOG_PATH.with_suffix(".jsonl.1"))
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            **payload,
        }
        with TOOL_CALL_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def model_cache_key(provider: str, pcfg: dict[str, Any]) -> str:
    api_state = "key" if provider != "nvidia-hosted" and meaningful_key_value(pcfg.get("api_key")) else "nokey"
    if provider == "nvidia-hosted":
        api_state = "key" if meaningful_key_value(read_env_file(NCP_ENV).get("NVIDIA_API_KEY")) else "nokey"
    return json.dumps(
        {
            "provider": provider,
            "base_url": pcfg.get("base_url", ""),
            "api": api_state,
            "current": pcfg.get("current_model", ""),
            "custom": pcfg.get("custom_models", []),
            "schema": 3,
        },
        sort_keys=True,
    )


def read_model_list_cache(provider: str, pcfg: dict[str, Any]) -> list[str] | None:
    try:
        data = json.loads(MODEL_LIST_CACHE_PATH.read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("key") != model_cache_key(provider, pcfg):
        return None
    if time.time() - float(data.get("time", 0)) > MODEL_CACHE_TTL_SECONDS:
        return None
    models = data.get("models")
    if not isinstance(models, list):
        return None
    return unique_model_ids(provider, [str(mid) for mid in models if str(mid).strip()])


def write_model_list_cache(provider: str, pcfg: dict[str, Any], models: list[str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"time": time.time(), "key": model_cache_key(provider, pcfg), "models": models}
    try:
        MODEL_LIST_CACHE_PATH.write_text(json.dumps(data, indent=2) + "\n")
        os.chmod(MODEL_LIST_CACHE_PATH, 0o600)
    except Exception:
        pass


def model_ids_from_response(data: Any) -> list[str]:
    ids: list[str] = []
    candidates: Any
    if isinstance(data, dict):
        candidates = data.get("data")
        if candidates is None:
            candidates = data.get("models")
        if candidates is None:
            candidates = data.get("model")
    else:
        candidates = data
    if isinstance(candidates, str):
        candidates = [candidates]
    if not isinstance(candidates, list):
        return ids
    for item in candidates:
        if isinstance(item, str):
            mid = item
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name") or item.get("model")
        else:
            mid = None
        if mid and str(mid).strip():
            ids.append(str(mid).strip())
    return ids


def nvidia_hosted_list_headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    key = read_env_file(NCP_ENV).get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if key:
        headers["authorization"] = f"Bearer {key}"
        headers["x-api-key"] = key
    return headers


def provider_model_list_headers(provider: str, pcfg: dict[str, Any]) -> dict[str, str]:
    headers = {"content-type": "application/json"}
    key = pcfg.get("api_key")
    if provider == "anthropic" and key:
        headers["x-api-key"] = str(key)
    elif meaningful_key(str(key) if key is not None else None):
        headers["authorization"] = f"Bearer {key}"
        headers["x-api-key"] = str(key)
    return headers


def post_json(url: str, body: Any, headers: dict[str, str] | None = None, timeout: float = 60.0) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def router_rate_limit_configured_rpm(provider: str, pcfg: dict[str, Any]) -> int | None:
    raw = pcfg.get("rate_limit_rpm")
    if raw is None and provider in ("nvidia-hosted", "self-hosted-nim", "ollama", "ollama-cloud"):
        raw = 40
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().lower() in ("0", "false", "off", "disable", "disabled", "none", "unset"):
        return 0
    try:
        if int(raw) == 0:
            return 0
    except Exception:
        pass
    rpm = positive_int(raw)
    return rpm if rpm and rpm > 0 else None


def router_rate_limit_rpm(provider: str, pcfg: dict[str, Any]) -> int | None:
    rpm = router_rate_limit_configured_rpm(provider, pcfg)
    return rpm if rpm and rpm > 0 else None


def router_rate_limit_key(provider: str, pcfg: dict[str, Any], model: str | None = None) -> str:
    # Provider/account limits such as NVIDIA NIM RPM apply across models.
    return f"{provider}:__global__"


def router_rate_limit_state_entry(provider: str, pcfg: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    key = router_rate_limit_key(provider, pcfg, model)
    try:
        state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
        if not isinstance(state, dict):
            return {}
        entry = state.get(key)
        if isinstance(entry, dict):
            return entry
        legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
        entry = state.get(legacy_key)
        return entry if isinstance(entry, dict) else {}
    except Exception:
        return {}


def router_rate_limit_effective_rpm(provider: str, pcfg: dict[str, Any], model: str | None = None) -> int | None:
    configured = router_rate_limit_configured_rpm(provider, pcfg)
    if configured == 0:
        return 0
    entry = router_rate_limit_state_entry(provider, pcfg, model)
    try:
        server_rpm = int(entry.get("server_rpm") or 0)
        updated_at = float(entry.get("server_rpm_updated_at") or 0.0)
        if server_rpm > 0 and 0.0 <= time.time() - updated_at < 3600.0:
            return server_rpm
    except Exception:
        pass
    return configured


def router_rate_limit_capacity(rpm: int) -> int:
    if rpm <= 1:
        return 1
    reserve = 1 if rpm <= 20 else max(1, math.ceil(rpm * 0.05))
    return max(1, rpm - reserve)


def router_rate_limit_recent(timestamps: Any, now: float, window: float, *, include_future: bool) -> list[float]:
    recent: list[float] = []
    for ts in timestamps or []:
        if not isinstance(ts, (int, float)):
            continue
        value = float(ts)
        age = now - value
        if age < window and (include_future or age >= 0.0):
            recent.append(value)
    return sorted(recent)


def router_rate_limit_usage(provider: str, pcfg: dict[str, Any], model: str | None = None) -> tuple[int, int | None]:
    rpm = router_rate_limit_effective_rpm(provider, pcfg, model)
    if rpm is None:
        return 0, None
    if rpm == 0:
        return 0, 0
    key = router_rate_limit_key(provider, pcfg, model)
    now = time.time()
    try:
        state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
        entry = state.get(key) if isinstance(state, dict) else None
        if not isinstance(entry, dict):
            legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
            entry = state.get(legacy_key) if isinstance(state, dict) else None
        timestamps = entry.get("timestamps") if isinstance(entry, dict) else ([float(entry)] if isinstance(entry, (int, float)) else [])
    except Exception:
        timestamps = []
    used = len(router_rate_limit_recent(timestamps, now, 60.0, include_future=False))
    return used, rpm


def record_router_rate_usage(provider: str, pcfg: dict[str, Any], model: str | None, rpm: int | None) -> tuple[int, int | None]:
    if rpm is None:
        return 0, None
    key = router_rate_limit_key(provider, pcfg, model)
    window = 60.0
    with _RATE_LIMIT_LOCK:
        try:
            state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        now = time.time()
        entry = state.get(key)
        if not isinstance(entry, dict):
            legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
            entry = state.get(legacy_key)
        timestamps = entry.get("timestamps") if isinstance(entry, dict) else ([float(entry)] if isinstance(entry, (int, float)) else [])
        recent = router_rate_limit_recent(timestamps, now, window, include_future=True)
        recent.append(now)
        keep = max(int(rpm or 0), 240)
        existing_penalty = float(entry.get("penalty_until") or 0.0) if isinstance(entry, dict) else 0.0
        new_entry: dict[str, Any] = {"timestamps": recent[-keep:], "rpm": int(rpm or 0), "updated_at": now, "last_wait": 0.0}
        if existing_penalty > now:
            new_entry["penalty_until"] = existing_penalty
        state[key] = new_entry
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        RATE_LIMIT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
        return len(recent), rpm


def parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    try:
        seconds = float(text)
        return max(0.0, seconds)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(text)
        return max(0.0, dt.timestamp() - time.time())
    except Exception:
        return None


def first_header(headers: Any, names: list[str]) -> str | None:
    for name in names:
        try:
            value = headers.get(name)
        except Exception:
            value = None
        if value:
            return str(value)
    return None


def first_int_in_header(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def rate_limit_reset_seconds(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    try:
        numeric = float(text)
        if numeric > time.time() + 60.0:
            return max(0.0, numeric - time.time())
        return max(0.0, numeric)
    except Exception:
        return parse_retry_after_seconds(text)


def learn_router_rate_limit_headers(provider: str, pcfg: dict[str, Any], model: str | None, headers: Any) -> None:
    limit = first_int_in_header(first_header(headers, [
        "x-ratelimit-limit-requests",
        "x-rate-limit-limit-requests",
        "ratelimit-limit",
        "rate-limit-limit",
        "x-ratelimit-limit",
        "x-rate-limit-limit",
    ]))
    remaining = first_int_in_header(first_header(headers, [
        "x-ratelimit-remaining-requests",
        "x-rate-limit-remaining-requests",
        "ratelimit-remaining",
        "rate-limit-remaining",
        "x-ratelimit-remaining",
        "x-rate-limit-remaining",
    ]))
    reset = rate_limit_reset_seconds(first_header(headers, [
        "x-ratelimit-reset-requests",
        "x-rate-limit-reset-requests",
        "ratelimit-reset",
        "rate-limit-reset",
        "x-ratelimit-reset",
        "x-rate-limit-reset",
    ]))
    if limit is None and remaining is None and reset is None:
        return
    configured = router_rate_limit_configured_rpm(provider, pcfg)
    rpm = limit if limit and limit > 0 else configured
    if rpm is None:
        rpm = 0
    key = router_rate_limit_key(provider, pcfg, model)
    with _RATE_LIMIT_LOCK:
        try:
            state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        now = time.time()
        entry = state.get(key)
        if not isinstance(entry, dict):
            legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
            entry = state.get(legacy_key)
        timestamps = entry.get("timestamps") if isinstance(entry, dict) else []
        recent = router_rate_limit_recent(timestamps, now, 60.0, include_future=True)
        penalty_until = float(entry.get("penalty_until") or 0.0) if isinstance(entry, dict) else 0.0
        if remaining == 0 and reset and reset > 0:
            penalty_until = max(penalty_until, now + reset)
        new_entry: dict[str, Any] = {
            "timestamps": recent[-max(int(rpm or 0), 240):],
            "rpm": int(rpm or 0),
            "updated_at": now,
            "last_wait": float(entry.get("last_wait") or 0.0) if isinstance(entry, dict) else 0.0,
            "server_remaining": remaining,
            "server_reset_seconds": reset,
        }
        if limit and limit > 0:
            new_entry["server_rpm"] = int(limit)
            new_entry["server_rpm_updated_at"] = now
        elif isinstance(entry, dict) and entry.get("server_rpm"):
            new_entry["server_rpm"] = entry.get("server_rpm")
            new_entry["server_rpm_updated_at"] = entry.get("server_rpm_updated_at")
        if penalty_until > now:
            new_entry["penalty_until"] = penalty_until
        state[key] = new_entry
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        RATE_LIMIT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
    router_log("INFO", f"rate_limit_headers provider={provider} model={model or ''} limit={limit} remaining={remaining} reset={reset}")


def register_router_rate_limit_backoff(provider: str, pcfg: dict[str, Any], model: str | None, retry_after: str | None = None) -> float:
    rpm = router_rate_limit_effective_rpm(provider, pcfg, model)
    fallback = 60.0 / float(rpm) if rpm and rpm > 0 else 15.0
    wait = parse_retry_after_seconds(retry_after)
    if wait is None:
        wait = max(10.0, min(60.0, fallback * 4.0))
    wait = max(1.0, min(300.0, wait))
    key = router_rate_limit_key(provider, pcfg, model)
    with _RATE_LIMIT_LOCK:
        try:
            state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        now = time.time()
        entry = state.get(key)
        if not isinstance(entry, dict):
            legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
            entry = state.get(legacy_key)
        timestamps = entry.get("timestamps") if isinstance(entry, dict) else []
        recent = router_rate_limit_recent(timestamps, now, 60.0, include_future=True)
        actual_recent = router_rate_limit_recent(timestamps, now, 60.0, include_future=False)
        configured_rpm = router_rate_limit_configured_rpm(provider, pcfg)
        inferred_rpm: int | None = None
        if (
            isinstance(entry, dict)
            and not entry.get("server_rpm")
            and configured_rpm
            and configured_rpm > 0
            and 0 < len(actual_recent) < configured_rpm
        ):
            inferred_rpm = max(1, len(actual_recent))
            rpm = inferred_rpm
        capacity = router_rate_limit_capacity(int(rpm or 0)) if rpm and rpm > 0 else int(rpm or 0)
        if capacity and capacity > 0 and len(actual_recent) >= capacity and actual_recent:
            wait = max(wait, max(0.0, actual_recent[0] + 60.0 - now))
        penalty_until = max(float(entry.get("penalty_until") or 0.0) if isinstance(entry, dict) else 0.0, now + wait)
        state[key] = {
            "timestamps": recent[-max(int(rpm or 0), 240):],
            "rpm": int(rpm or 0),
            "updated_at": now,
            "last_wait": wait,
            "penalty_until": penalty_until,
            "last_429_at": now,
        }
        if isinstance(entry, dict):
            for preserve_key in ("server_rpm", "server_rpm_updated_at", "server_remaining", "server_reset_seconds"):
                if preserve_key in entry:
                    state[key][preserve_key] = entry[preserve_key]
        if inferred_rpm:
            state[key]["server_rpm"] = inferred_rpm
            state[key]["server_rpm_updated_at"] = now
            state[key]["server_rpm_reason"] = "inferred_from_429"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        RATE_LIMIT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
    router_log("WARN", f"rate_limit_429_backoff provider={provider} model={model or ''} wait={wait:.2f}s")
    return wait


def apply_router_rate_limit(provider: str, pcfg: dict[str, Any], model: str | None = None) -> tuple[float, int, int | None]:
    rpm = router_rate_limit_effective_rpm(provider, pcfg, model)
    if rpm is None:
        return 0.0, 0, None
    if rpm <= 0:
        used, limit = record_router_rate_usage(provider, pcfg, model, rpm)
        return 0.0, used, limit
    window = 60.0
    base_interval = window / float(rpm)
    capacity = router_rate_limit_capacity(rpm)
    key = router_rate_limit_key(provider, pcfg, model)
    waited = 0.0
    while True:
        with _RATE_LIMIT_LOCK:
            try:
                state = json.loads(RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8")) if RATE_LIMIT_STATE_PATH.exists() else {}
                if not isinstance(state, dict):
                    state = {}
            except Exception:
                state = {}
            now = time.time()
            entry = state.get(key)
            if not isinstance(entry, dict):
                legacy_key = f"{provider}:{model or current_upstream_model_id(provider, pcfg)}"
                entry = state.get(legacy_key)
            if isinstance(entry, dict):
                timestamps = entry.get("timestamps")
                try:
                    penalty_until = float(entry.get("penalty_until") or 0.0)
                except Exception:
                    penalty_until = 0.0
            elif isinstance(entry, (int, float)):
                timestamps = [float(entry)]
                penalty_until = 0.0
            else:
                timestamps = []
                penalty_until = 0.0
            recent = router_rate_limit_recent(timestamps, now, window, include_future=True)
            used = len(recent)
            usage_ratio = min(1.0, used / float(capacity))
            wait = 0.0
            if penalty_until > now:
                wait = max(wait, penalty_until - now)
            if used >= capacity and recent:
                wait = max(0.0, recent[0] + window - now)
            elif recent:
                elapsed_since_last = max(0.0, now - recent[-1])
                wait = max(0.0, base_interval - elapsed_since_last)
                if usage_ratio >= 0.70:
                    pressure = (usage_ratio - 0.70) / 0.30
                    target_interval = base_interval * (1.0 + max(0.0, min(1.0, pressure)) * 3.0)
                    wait = max(wait, target_interval - elapsed_since_last)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if wait <= 0.001:
                recent.append(now)
                new_entry = {"timestamps": recent[-rpm:], "rpm": rpm, "updated_at": now, "last_wait": waited}
                if penalty_until > now:
                    new_entry["penalty_until"] = penalty_until
                state[key] = new_entry
                RATE_LIMIT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
                return waited, len(recent), rpm
            if used < capacity:
                scheduled = now + wait
                recent.append(scheduled)
                new_entry = {"timestamps": recent[-rpm:], "rpm": rpm, "updated_at": scheduled, "last_wait": wait}
                if penalty_until > now:
                    new_entry["penalty_until"] = penalty_until
                state[key] = new_entry
                RATE_LIMIT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
                router_log("INFO", f"rate_limit_soft_wait provider={provider} model={model or ''} rpm={rpm} wait={wait:.2f}s")
                time.sleep(wait)
                return waited + wait, len(recent), rpm
        sleep_for = min(wait, 10.0)
        router_log("INFO", f"rate_limit_wait provider={provider} model={model or ''} rpm={rpm} wait={wait:.2f}s waited={waited:.2f}s")
        time.sleep(sleep_for)
        waited += sleep_for


RATE_LIMIT_NOTICE_PALETTE = (203, 209, 215, 221, 229, 187, 151, 116, 111, 147, 183, 219)


def colorize_status_text(text: str) -> str:
    if os.environ.get("CLAUDE_ANY_RATE_LIMIT_ANSI", "1").lower() in ("0", "false", "no"):
        return text
    parts: list[str] = []
    phase = int(time.monotonic() * 8)
    for i, ch in enumerate(text):
        if ch.isspace():
            parts.append(ch)
            continue
        color = RATE_LIMIT_NOTICE_PALETTE[(phase + i) % len(RATE_LIMIT_NOTICE_PALETTE)]
        parts.append(f"\033[1;38;5;{color}m{ch}\033[0m")
    return "".join(parts)


def rate_limit_notice(waited: float, used: int = 0, rpm: int | None = None, show_status: bool = False) -> str:
    return ""


def is_url_up(url: str) -> bool:
    try:
        http_json(url, timeout=1.5)
        return True
    except Exception:
        return False


def nvidia_upstream_base_url() -> str:
    return "https://integrate.api.nvidia.com/v1"


def nvidia_proxy_base_url() -> str:
    env = read_env_file(NCP_ENV)
    host = env.get("PROXY_HOST") or "127.0.0.1"
    port = env.get("PROXY_PORT") or "8788"
    return f"http://{host}:{port}"


def nvidia_api_key() -> str:
    return (
        read_env_file(NCP_ENV).get("NVIDIA_API_KEY")
        or os.environ.get("NVIDIA_API_KEY")
        or os.environ.get("NV_API_KEY")
        or ""
    ).strip()


def install_ncp_proxy() -> str | None:
    if os.environ.get("CLAUDE_ANY_AUTO_INSTALL_NCP", "1").lower() in ("0", "false", "no"):
        return None
    NCP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(NCP_LOG, "ab", buffering=0) as log:
        log.write(b"\n[claude-any] installing nvd-claude-proxy with pip\n")
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--upgrade", NCP_PYPI_PACKAGE],
            stdout=log,
            stderr=log,
            timeout=240,
        )
    if proc.returncode != 0:
        return None
    importlib.invalidate_caches()
    return find_executable("ncp")


def ncp_module_available() -> bool:
    return importlib.util.find_spec("nvd_claude_proxy") is not None


def ncp_proxy_executable() -> str | None:
    return find_executable("nvd-claude-proxy") or find_executable("ncp")


def ensure_ncp() -> None:
    cfg = load_config()
    provider = cfg["providers"]["nvidia-hosted"]
    upstream = provider.get("base_url") or nvidia_upstream_base_url()
    env = os.environ.copy()
    env.update(read_env_file(NCP_ENV))
    env["NVIDIA_BASE_URL"] = upstream.rstrip("/")
    env.setdefault("PROXY_HOST", "127.0.0.1")
    env.setdefault("PROXY_PORT", "8788")
    env.setdefault("STORAGE_ENGINE", "sqlite")
    timeout_ms = positive_int(provider.get("request_timeout_ms"))
    if timeout_ms:
        env["REQUEST_TIMEOUT_SECONDS"] = str(max(1, timeout_ms / 1000))
    base = f"http://{env['PROXY_HOST']}:{env['PROXY_PORT']}"
    if is_url_up(f"{base}/v1/models"):
        return
    NCP_LOG.parent.mkdir(parents=True, exist_ok=True)
    ncp_exe = ncp_proxy_executable()
    if not (ncp_exe or ncp_module_available()):
        install_ncp_proxy()
        ncp_exe = ncp_proxy_executable()
    if not (ncp_exe or ncp_module_available()):
        raise RuntimeError("nvd-claude-proxy was not found. Install it with: python -m pip install --user nvd-claude-proxy")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with open(NCP_LOG, "ab", buffering=0) as log:
        if ncp_exe:
            cmd = [ncp_exe]
            log.write(f"\n[claude-any] starting nvd-claude-proxy executable: {ncp_exe}\n".encode())
        else:
            cmd = [sys.executable, "-m", "nvd_claude_proxy.main"]
            log.write(b"\n[claude-any] starting nvd-claude-proxy module\n")
        subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            env=env,
            cwd=str(NCP_ENV.parent),
            creationflags=creationflags,
        )
    deadline = time.time() + 45
    while time.time() < deadline:
        if is_url_up(f"{base}/v1/models"):
            return
        time.sleep(0.5)
    raise RuntimeError("nvd-claude-proxy did not become ready")


def ncp_model_id_for_nvidia_hosted(model_id: str) -> str:
    if model_id.startswith("claude-") and not model_id.startswith("claude-any-"):
        return model_id
    try:
        data = http_json(join_url(nvidia_proxy_base_url(), "/v1/models"), timeout=3.0)
    except Exception:
        return model_id
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return model_id
    for item in items:
        if not isinstance(item, dict):
            continue
        ncp_id = str(item.get("id") or "").strip()
        nvidia_id = str(item.get("nvidia_id") or "").strip()
        if ncp_id == model_id:
            return ncp_id
        if nvidia_id and nvidia_id == model_id and ncp_id:
            return ncp_id
    return model_id


def provider_headers(provider: str, pcfg: dict[str, Any]) -> dict[str, str]:
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    key = pcfg.get("api_key") or "not-used"
    if provider == "anthropic":
        if not pcfg.get("api_key"):
            raise RuntimeError("Anthropic API key is missing. Run: claude-anyctl api-key anthropic")
        headers["x-api-key"] = pcfg["api_key"]
    elif provider in ("ollama", "ollama-cloud", "vllm", "self-hosted-nim"):
        headers["x-api-key"] = key
        headers["authorization"] = f"Bearer {key}"
    elif provider == "nvidia-hosted":
        key = nvidia_api_key() or (str(pcfg.get("api_key") or "") if meaningful_key(pcfg.get("api_key")) else "")
        if key:
            headers["authorization"] = f"Bearer {key}"
            headers["x-api-key"] = key
    return headers


def get_current_provider(cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    provider = normalize_provider(cfg.get("current_provider", "nvidia-hosted"))
    return provider, cfg["providers"][provider]


def native_anthropic_enabled(provider: str) -> bool:
    return provider == "anthropic"


def upstream_model_ids(provider: str, pcfg: dict[str, Any]) -> list[str]:
    cached = read_model_list_cache(provider, pcfg)
    if cached is not None:
        return cached
    if provider == "nvidia-hosted":
        base = (pcfg.get("base_url") or nvidia_upstream_base_url()).rstrip("/")
    else:
        base = provider_upstream_request_base(provider, pcfg)
    ids: list[str] = []
    fetched = False
    try:
        if provider in ("ollama", "ollama-cloud"):
            try:
                data = http_json(join_url(base, "/api/tags"), headers=provider_model_list_headers(provider, pcfg), timeout=4.0)
                ids = [normalize_model_id(provider, mid) for mid in model_ids_from_response(data)]
                fetched = True
            except Exception:
                data = http_json(join_url(base, "/v1/models"), headers=provider_model_list_headers(provider, pcfg), timeout=4.0)
                ids = [normalize_model_id(provider, mid) for mid in model_ids_from_response(data)]
                fetched = True
        elif provider == "nvidia-hosted":
            data = http_json(join_url(base, "/v1/models"), headers=nvidia_hosted_list_headers(), timeout=8.0)
            ids = model_ids_from_response(data)
            fetched = True
        else:
            headers = provider_model_list_headers(provider, pcfg)
            for path in ("/v1/models", "/models"):
                try:
                    data = http_json(join_url(base, path), headers=headers, timeout=6.0)
                    ids = model_ids_from_response(data)
                    fetched = True
                    if ids:
                        break
                except Exception:
                    continue
    except Exception:
        ids = []
    if not fetched:
        return []
    for mid in pcfg.get("custom_models", []) or []:
        mid = normalize_model_id(provider, mid)
        if mid and mid not in ids:
            ids.append(mid)
    cur = normalize_model_id(provider, pcfg.get("current_model") or "")
    if cur and provider != "nvidia-hosted" and cur.startswith(f"claude-any-{provider}-"):
        pass
    elif cur and cur not in ids and not (provider == "nvidia-hosted" and cur.startswith("claude-")):
        ids.insert(0, cur)
    if provider == "nvidia-hosted" and cur and cur not in ids:
        ids.insert(0, cur)
    sorted_ids = sorted_model_ids(unique_model_ids(provider, ids))
    write_model_list_cache(provider, pcfg, sorted_ids)
    return sorted_ids


def model_context_field(item: dict[str, Any]) -> int | None:
    for key in ("max_model_len", "max_context_length", "context_length", "max_context_tokens", "max_position_embeddings"):
        value = positive_int(item.get(key))
        if value:
            return value
    return None


def upstream_model_runtime_info(provider: str, pcfg: dict[str, Any], timeout: float = 3.0) -> dict[str, Any] | None:
    if provider not in ("vllm", "self-hosted-nim"):
        return None
    base = provider_upstream_request_base(provider, pcfg)
    if not base:
        return None
    current = current_upstream_model_id(provider, pcfg)
    try:
        data = http_json(join_url(base, "/v1/models"), headers=provider_model_list_headers(provider, pcfg), timeout=timeout)
    except Exception:
        return None
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    fallback_item: dict[str, Any] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if fallback_item is None:
            fallback_item = item
        if str(item.get("id") or "") == current:
            selected = item
            break
    else:
        selected = fallback_item
    if not selected:
        return None
    return {
        "models_url": join_url(base, "/v1/models"),
        "requested_model": current,
        "runtime_model": str(selected.get("id") or ""),
        "max_model_len": model_context_field(selected),
        "owned_by": selected.get("owned_by"),
        "root": selected.get("root"),
    }


def upstream_model_context_limit(provider: str, pcfg: dict[str, Any], timeout: float = 3.0) -> int | None:
    info = upstream_model_runtime_info(provider, pcfg, timeout=timeout)
    if not info:
        return None
    return positive_int(info.get("max_model_len"))


def model_map_for(provider: str, pcfg: dict[str, Any]) -> dict[str, str]:
    ids = upstream_model_ids(provider, pcfg)
    return {alias_for(provider, mid): mid for mid in ids}


def current_alias(cfg: dict[str, Any]) -> str:
    provider, pcfg = get_current_provider(cfg)
    cur = normalize_model_id(provider, pcfg.get("current_model") or "model")
    if provider == "nvidia-hosted" and cur.startswith("claude-"):
        return cur
    if cur.startswith(f"claude-any-{provider}-"):
        return cur
    return alias_for(provider, cur)


def ollama_native_compat_enabled(provider: str, pcfg: dict[str, Any]) -> bool:
    return provider == "ollama" and bool(pcfg.get("native_compat", True))


def vllm_native_compat_enabled(provider: str, pcfg: dict[str, Any]) -> bool:
    return provider == "vllm" and bool(pcfg.get("native_compat", True))


def nim_native_compat_enabled(provider: str, pcfg: dict[str, Any]) -> bool:
    return provider == "self-hosted-nim" and bool(pcfg.get("native_compat", True))


def nvidia_hosted_native_compat_enabled(provider: str, pcfg: dict[str, Any]) -> bool:
    # NVIDIA's self-hosted NIM server exposes Anthropic-compatible /v1/messages.
    # The hosted API Catalog endpoint at integrate.api.nvidia.com currently
    # exposes OpenAI-compatible /v1/chat/completions instead, so keep it on the
    # claude-any router conversion path even if an old config has native=true.
    return False


def provider_native_compat_enabled(provider: str, pcfg: dict[str, Any]) -> bool:
    return (
        vllm_native_compat_enabled(provider, pcfg)
        or nim_native_compat_enabled(provider, pcfg)
        or nvidia_hosted_native_compat_enabled(provider, pcfg)
    )


def current_upstream_model_id(provider: str, pcfg: dict[str, Any]) -> str:
    cur = normalize_model_id(provider, pcfg.get("current_model") or "model")
    if cur.startswith(f"claude-any-{provider}-"):
        try:
            return unslug_provider_alias(provider, cur, model_map_for(provider, pcfg)) or cur
        except Exception:
            return cur
    return cur


def launch_model_id(provider: str, pcfg: dict[str, Any]) -> str:
    cur = normalize_model_id(provider, pcfg.get("current_model") or "model")
    if provider != "ollama":
        return alias_for(provider, cur) if not (provider == "nvidia-hosted" and cur.startswith("claude-")) else cur
    if not cur.startswith("claude-any-ollama-"):
        return cur
    try:
        return unslug_provider_alias("ollama", cur, model_map_for("ollama", pcfg)) or cur
    except Exception:
        return cur


def resolve_requested_model(provider: str, pcfg: dict[str, Any], requested: str | None) -> str:
    requested = strip_claude_context_suffix(requested)
    fallback = normalize_model_id(provider, pcfg.get("current_model") or "model")
    if provider == "nvidia-hosted":
        if requested and requested.startswith("claude-nvidia-"):
            return requested
        if fallback:
            return fallback
    mmap = model_map_for(provider, pcfg)
    if requested:
        resolved = unslug_provider_alias(provider, requested, mmap)
        if resolved:
            return resolved
        # Built-in Claude aliases and stale aliases from another provider route to current provider's model.
        if requested.startswith("claude-") or requested.startswith("claude-any-"):
            return fallback
        return normalize_model_id(provider, requested)
    return fallback


def list_model_objects(provider: str, pcfg: dict[str, Any]) -> list[dict[str, Any]]:
    return [model_object(provider, mid) for mid in upstream_model_ids(provider, pcfg)]


def provider_upstream_request_base(provider: str, pcfg: dict[str, Any]) -> str:
    return pcfg.get("base_url", "").rstrip("/")


def native_anthropic_base_url(provider: str, pcfg: dict[str, Any]) -> str:
    base = pcfg.get("base_url", "http://127.0.0.1:8000").rstrip("/")
    if provider == "nvidia-hosted" and base.endswith("/v1"):
        return base[:-3].rstrip("/")
    return base


def write_json(handler: BaseHTTPRequestHandler, obj: Any, status: int = 200) -> None:
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def write_empty_response(handler: BaseHTTPRequestHandler, status: int = 202) -> None:
    handler.send_response(status)
    handler.send_header("content-length", "0")
    handler.end_headers()


def write_accepted_response(handler: BaseHTTPRequestHandler) -> None:
    body = b"Accepted"
    handler.send_response(202)
    handler.send_header("content-type", "text/plain")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def reject_external_router_request(handler: BaseHTTPRequestHandler, cfg: dict[str, Any] | None = None) -> bool:
    if router_request_allowed(handler, cfg):
        return False
    write_json(
        handler,
        {
            "type": "error",
            "error": {
                "type": "forbidden",
                "message": "claude-any router external debug access is off.",
            },
        },
        403,
    )
    return True


def write_router_activity(event: str, provider: str, model: str | None = None, **fields: Any) -> None:
    try:
        level = "error" if event == "error" else ("warn" if event in {"retry", "wait"} else "info")
        EVENT_BUS.publish(
            level=level,
            category=f"router.{event}",
            message=f"{event} {provider} {model or ''}".strip(),
            provider=provider,
            model=model,
            data=fields,
        )
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": time.time(),
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            "provider": provider,
            "model": model or "",
        }
        data.update(fields)
        tmp = ROUTER_ACTIVITY_PATH.with_name(f"{ROUTER_ACTIVITY_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(ROUTER_ACTIVITY_PATH)
    except Exception:
        pass


def context_limit_for_status(provider: str, pcfg: dict[str, Any]) -> int | None:
    if provider in ("ollama", "ollama-cloud"):
        return ollama_context_limit_for_budget(pcfg)
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        return openai_context_limit_for_budget(provider, pcfg)
    return positive_int(pcfg.get("context_window")) or positive_int(pcfg.get("max_model_len"))


def write_context_usage(provider: str, pcfg: dict[str, Any], body: dict[str, Any], source: str) -> None:
    try:
        tokens = estimate_tokens(body)
        limit = context_limit_for_status(provider, pcfg)
        percent = round((tokens / limit) * 100.0, 1) if limit else None
        EVENT_BUS.publish(
            level="debug",
            category="context.usage",
            message=f"context usage {tokens}/{limit or '?'} tokens",
            provider=provider,
            model=str(body.get("model") or pcfg.get("current_model") or ""),
            data={
                "source": source,
                "tokens": tokens,
                "context_limit": limit,
                "percent": percent,
                "messages": len(body.get("messages") or []),
                "tools": len(body.get("tools") or []),
            },
        )
        data = {
            "updated_at": time.time(),
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": provider,
            "model": str(body.get("model") or pcfg.get("current_model") or ""),
            "source": source,
            "tokens": tokens,
            "context_limit": limit,
            "percent": percent,
            "messages": len(body.get("messages") or []),
            "tools": len(body.get("tools") or []),
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONTEXT_USAGE_PATH.with_name(f"{CONTEXT_USAGE_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(CONTEXT_USAGE_PATH)
    except Exception:
        pass


def write_text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", content_type)
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def llm_config_payload(messages: list[str] | None = None) -> dict[str, Any]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    lang = cfg.get("language", "en")
    rows, values = llm_option_panel_rows(provider, pcfg, lang)
    option_rows = [
        {"label": row, "key": key, "value": llm_option_prompt_default(provider, pcfg, key)}
        for row, key in zip(rows, values)
        if key not in ("back", "__info__", "preset", "context_setup", "timeout_profile")
    ]
    preset_rows, preset_values = llm_preset_panel_rows(provider, pcfg, lang)
    context_rows, context_values = context_setup_panel_rows(provider, pcfg, lang)
    timeout_rows, timeout_values = timeout_profile_panel_rows(pcfg, lang)
    return {
        "ok": True,
        "messages": messages or [],
        "provider": provider,
        "provider_label": PROVIDER_LABELS.get(provider, provider),
        "model": str(pcfg.get("current_model") or ""),
        "alias": current_alias(cfg),
        "advisor_model": str(pcfg.get("advisor_model") or ""),
        "preset": applied_preset_id(provider, pcfg),
        "context": context_setting_status(provider, pcfg),
        "timeout": timeout_profile_status(pcfg, lang),
        "options": option_rows,
        "presets": [
            {"label": row, "value": value}
            for row, value in zip(preset_rows, preset_values)
            if value not in ("back", "__info__")
        ],
        "contexts": [
            {"label": row, "value": value}
            for row, value in zip(context_rows, context_values)
            if value not in ("back", "__info__")
        ],
        "timeouts": [
            {"label": row, "value": value}
            for row, value in zip(timeout_rows, timeout_values)
            if value not in ("back", "__info__")
        ],
    }


def apply_timeout_profile_config(provider: str, profile_id: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    lines = apply_timeout_profile_to_provider(pcfg, profile_id, cfg.get("language", "en"))
    save_config(cfg)
    clear_model_cache()
    return lines


def handle_llm_config_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    if path != "/ca/config/llm":
        return False
    write_json(handler, llm_config_payload())
    return True


def handle_llm_config_post(handler: BaseHTTPRequestHandler, path: str, body: dict[str, Any]) -> bool:
    if path != "/ca/config/llm":
        return False
    cfg = load_config()
    provider, _pcfg = get_current_provider(cfg)
    action = str(body.get("action") or "option").strip()
    value = str(body.get("value") or "").strip()
    key = str(body.get("key") or "").strip()
    messages: list[str]
    try:
        if action == "model":
            messages = set_model_config(value)
        elif action == "advisor_model":
            messages = set_advisor_model_config(value)
        elif action == "preset":
            messages = apply_llm_preset_config(provider, value)
        elif action == "context_setup":
            messages = apply_context_setup_config(provider, value)
        elif action == "timeout_profile":
            messages = apply_timeout_profile_config(provider, value)
        elif action == "option":
            if not key:
                raise SystemExit("Missing option key")
            messages = set_llm_option_config(provider, key, value)
        else:
            raise SystemExit(f"Unknown LLM config action: {action}")
        EVENT_BUS.publish(level="info", category="config.llm", message=f"updated {action} {key or value}", provider=provider, data={"action": action, "key": key, "value": value})
        write_json(handler, llm_config_payload(messages))
    except SystemExit as exc:
        write_json(handler, {"ok": False, "error": str(exc), "messages": [str(exc)]}, 400)
    except Exception as exc:
        router_log("ERROR", f"llm config update failed: {type(exc).__name__}: {exc}")
        write_json(handler, {"ok": False, "error": f"{type(exc).__name__}: {exc}", "messages": [f"{type(exc).__name__}: {exc}"]}, 500)
    return True


def render_router_home_html(cfg: dict[str, Any], provider: str, pcfg: dict[str, Any]) -> str:
    model = current_alias(cfg)
    upstream = read_json_file(ROUTER_ACTIVITY_PATH)
    context = read_json_file(CONTEXT_USAGE_PATH)
    used, rpm_limit = router_rate_limit_usage(provider, pcfg)
    rpm_text = "off"
    if bool(pcfg.get("rate_limit_status", True)):
        rpm_text = f"{used}/min unmanaged" if rpm_limit == 0 else (f"{used}/{rpm_limit}" if rpm_limit else "unknown")
    timeout_ms = positive_int(pcfg.get("request_timeout_ms")) or DEFAULT_REQUEST_TIMEOUT_MS
    idle_ms = positive_int(pcfg.get("stream_idle_timeout_ms")) or timeout_profile_idle_ms(timeout_ms)
    context_limit = context_limit_for_status(provider, pcfg)
    context_tokens = positive_int(context.get("tokens"))
    context_pct = context.get("percent")
    if isinstance(context_pct, (int, float)):
        context_text = f"{context_tokens or 0:,}/{context_limit or 0:,} tok ({context_pct}%)"
    else:
        context_text = f"{context_tokens or 0:,}/{context_limit or 0:,} tok" if context_limit else "unknown"
    upstream_bits = [
        str(upstream.get("event") or "idle"),
        str(upstream.get("provider") or provider),
        str(upstream.get("model") or pcfg.get("current_model") or ""),
    ]
    upstream_text = " · ".join(bit for bit in upstream_bits if bit)
    links = [
        ("Events UI", "/ca/events", "Live router event stream with filters"),
        ("Recent events JSON", "/ca/events/recent", "Latest structured event records"),
        ("Events SSE", "/ca/events/stream", "Server-sent events stream"),
        ("Chat health", "/ca/chat/health", "Agent chat component status"),
        ("Chat messages", "/ca/chat/messages", "Stored agent chat messages"),
        ("Channel bridge", "/ca/channel/health", "External channel bridge API"),
        ("Channel messages", "/ca/channel/messages", "Messages posted through channel bridge"),
        ("Plan artifacts", "/ca/plan/artifacts", "Plan mode artifacts served by router"),
        ("Models", "/v1/models", "Claude-compatible model list"),
        ("Health", "/health", "Machine-readable health JSON"),
    ]
    link_html = "\n".join(
        f'<a class="link" href="{html_lib.escape(href)}"><strong>{html_lib.escape(label)}</strong><span>{html_lib.escape(desc)}</span></a>'
        for label, href, desc in links
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Claude Any Router</title>
  <style>
    :root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; }}
    body {{ margin: 0; background: #090b0f; color: #e8edf4; }}
    header {{ padding: 22px 24px 16px; border-bottom: 1px solid #253044; background: #101722; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; letter-spacing: 0; }}
    .sub {{ color: #a8b3c5; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .topnav {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 6px; padding: 10px 24px; background: #0b111a; border-bottom: 1px solid #253044; overflow-x: auto; }}
    .tab {{ min-width: 96px; min-height: 34px; border-radius: 6px; border: 1px solid #334155; background: #101722; color: #cbd5e1; cursor: pointer; }}
    .tab:hover {{ border-color: #60a5fa; color: #eff6ff; }}
    .tab.active {{ background: #1d4ed8; border-color: #60a5fa; color: white; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
    .view {{ display: none; }}
    .view.active {{ display: block; }}
    .view h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }}
    .card, .link, .events {{ background: #0d131d; border: 1px solid #253044; border-radius: 8px; padding: 12px; }}
    .label {{ color: #93a4ba; font-size: 12px; text-transform: uppercase; }}
    .value {{ margin-top: 5px; font-size: 15px; word-break: break-word; }}
    .links {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; margin-top: 18px; }}
    a.link {{ display: block; color: #dbeafe; text-decoration: none; }}
    a.link:hover {{ border-color: #60a5fa; }}
    a.link span {{ display: block; margin-top: 4px; color: #93a4ba; font-size: 13px; }}
    .events {{ margin-top: 18px; }}
    .settings {{ background: #0d131d; border: 1px solid #253044; border-radius: 8px; padding: 12px; }}
    .settings h2, .events h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .settings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .control {{ display: grid; gap: 6px; }}
    .control label {{ color: #93a4ba; font-size: 12px; text-transform: uppercase; }}
    input, select, button {{ min-height: 34px; border-radius: 6px; border: 1px solid #334155; background: #080d14; color: #e8edf4; padding: 6px 8px; }}
    button {{ cursor: pointer; background: #12304f; border-color: #2563eb; }}
    button:hover {{ background: #17406a; }}
    .option-row {{ display: grid; grid-template-columns: minmax(240px, 1fr) minmax(160px, 260px) auto; gap: 8px; align-items: center; padding: 8px 0; border-top: 1px solid #1f2937; }}
    .option-row .name {{ color: #dbeafe; word-break: break-word; }}
    .messages {{ margin-top: 10px; color: #c4b5fd; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }}
    .event {{ padding: 8px 0; border-top: 1px solid #1f2937; }}
    .event:first-child {{ border-top: 0; }}
    .meta {{ color: #93a4ba; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }}
    .preview {{ margin-top: 4px; color: #cbd5e1; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }}
    code {{ color: #bfdbfe; }}
  </style>
</head>
<body>
  <header>
    <h1>Claude Any Router</h1>
    <div class="sub">v{html_lib.escape(VERSION)} · {html_lib.escape(provider)} · {html_lib.escape(model)}</div>
  </header>
  <nav class="topnav" aria-label="Router sections">
    <button class="tab active" data-view="overview">Overview</button>
    <button class="tab" data-view="settings">LLM Settings</button>
    <button class="tab" data-view="events">Events</button>
    <button class="tab" data-view="endpoints">Endpoints</button>
  </nav>
  <main>
    <section id="view-overview" class="view active">
      <h2>Overview</h2>
      <div class="grid">
      <div class="card"><div class="label">Provider</div><div class="value">{html_lib.escape(provider)}</div></div>
      <div class="card"><div class="label">Model</div><div class="value">{html_lib.escape(model)}</div></div>
      <div class="card"><div class="label">Context</div><div class="value">{html_lib.escape(context_text)}</div></div>
      <div class="card"><div class="label">Timeout</div><div class="value">{timeout_ms:,} ms · idle {idle_ms:,} ms</div></div>
      <div class="card"><div class="label">RPM</div><div class="value">{html_lib.escape(rpm_text)}</div></div>
      <div class="card"><div class="label">Upstream</div><div class="value">{html_lib.escape(upstream_text)}</div></div>
      </div>
    </section>
    <section id="view-settings" class="view">
      <h2>LLM Settings</h2>
      <div class="settings">
      <div class="settings-grid">
        <div class="control"><label>Model</label><input id="modelInput"><button id="modelApply">Apply model</button></div>
        <div class="control"><label>Advisor Model</label><input id="advisorInput" placeholder="off or model id"><button id="advisorApply">Apply advisor</button></div>
        <div class="control"><label>Preset</label><select id="presetSelect"></select><button id="presetApply">Apply preset</button></div>
        <div class="control"><label>Context Setup</label><select id="contextSelect"></select><button id="contextApply">Apply context</button></div>
        <div class="control"><label>Timeout Profile</label><select id="timeoutSelect"></select><button id="timeoutApply">Apply timeout</button></div>
      </div>
      <div id="optionRows"></div>
      <div id="settingsMessages" class="messages"></div>
      </div>
    </section>
    <section id="view-events" class="view events">
      <h2>Recent Events</h2>
      <div id="events"><div class="meta">Loading /ca/events/recent...</div></div>
    </section>
    <section id="view-endpoints" class="view">
      <h2>Endpoints</h2>
      <div class="links">{link_html}</div>
    </section>
  </main>
  <script>
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const views = Array.from(document.querySelectorAll('.view'));
    function showView(name) {{
      tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.view === name));
      views.forEach(view => view.classList.toggle('active', view.id === 'view-' + name));
      if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    }}
    tabs.forEach(tab => tab.addEventListener('click', () => showView(tab.dataset.view)));
    const initialView = (location.hash || '#overview').slice(1);
    if (tabs.some(tab => tab.dataset.view === initialView)) showView(initialView);
    const el = document.getElementById('events');
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const modelInput = document.getElementById('modelInput');
    const advisorInput = document.getElementById('advisorInput');
    const presetSelect = document.getElementById('presetSelect');
    const contextSelect = document.getElementById('contextSelect');
    const timeoutSelect = document.getElementById('timeoutSelect');
    const optionRows = document.getElementById('optionRows');
    const settingsMessages = document.getElementById('settingsMessages');
    function fillSelect(select, rows, current) {{
      select.innerHTML = (rows || []).map(item => `<option value="${{esc(item.value)}}">${{esc(item.label)}}</option>`).join('');
      if (current) select.value = current;
    }}
    async function loadSettings(messages = []) {{
      const res = await fetch('/ca/config/llm');
      const data = await res.json();
      modelInput.value = data.model || '';
      advisorInput.value = data.advisor_model || '';
      fillSelect(presetSelect, data.presets, data.preset);
      fillSelect(contextSelect, data.contexts);
      fillSelect(timeoutSelect, data.timeouts);
      optionRows.innerHTML = (data.options || []).map(item => `<div class="option-row"><div class="name">${{esc(item.label)}}</div><input data-key="${{esc(item.key)}}" value="${{esc(item.value)}}"><button data-key="${{esc(item.key)}}">Apply</button></div>`).join('');
      settingsMessages.textContent = (messages.length ? messages : data.messages || []).join('\\n');
    }}
    async function postSettings(payload) {{
      settingsMessages.textContent = 'Saving...';
      const res = await fetch('/ca/config/llm', {{method:'POST', headers:{{'content-type':'application/json'}}, body: JSON.stringify(payload)}});
      const data = await res.json();
      if (!res.ok || !data.ok) {{
        settingsMessages.textContent = (data.messages || [data.error || 'Update failed']).join('\\n');
        return;
      }}
      await loadSettings(data.messages || []);
    }}
    document.getElementById('modelApply').onclick = () => postSettings({{action:'model', value:modelInput.value}});
    document.getElementById('advisorApply').onclick = () => postSettings({{action:'advisor_model', value:advisorInput.value}});
    document.getElementById('presetApply').onclick = () => postSettings({{action:'preset', value:presetSelect.value}});
    document.getElementById('contextApply').onclick = () => postSettings({{action:'context_setup', value:contextSelect.value}});
    document.getElementById('timeoutApply').onclick = () => postSettings({{action:'timeout_profile', value:timeoutSelect.value}});
    optionRows.addEventListener('click', ev => {{
      const button = ev.target.closest('button[data-key]');
      if (!button) return;
      const input = optionRows.querySelector(`input[data-key="${{CSS.escape(button.dataset.key)}}"]`);
      postSettings({{action:'option', key:button.dataset.key, value:input ? input.value : ''}});
    }});
    loadSettings();
    fetch('/ca/events/recent?limit=20').then(r => r.json()).then(j => {{
      const events = j.events || [];
      el.innerHTML = events.length ? events.reverse().map(e => {{
        const preview = e.data && e.data.message_preview ? `<div class="preview">${{esc(e.data.message_preview)}}${{e.data.message_preview_truncated ? '…' : ''}}</div>` : '';
        return `<div class="event"><div class="meta">#${{e.id}} ${{esc(e.time)}} · ${{esc(e.level)}} · ${{esc(e.category)}} · ${{esc(e.provider)}} ${{esc(e.model)}}</div><div>${{esc(e.message)}}</div>${{preview}}</div>`;
      }}).join('') : '<div class="meta">No events yet.</div>';
    }}).catch(err => {{ el.innerHTML = '<div class="meta">Could not load events: ' + esc(err) + '</div>'; }});
  </script>
</body>
</html>"""


def parse_json_body(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8") if raw else "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def query_int(params: dict[str, list[str]], name: str, default: int) -> int:
    values = params.get(name) or []
    try:
        return int(values[0])
    except Exception:
        return default


def handle_events_get(handler: BaseHTTPRequestHandler, path: str, query: dict[str, list[str]]) -> bool:
    if path == "/ca/events":
        write_text_response(handler, render_events_html(), content_type="text/html; charset=utf-8")
        return True
    if path == "/ca/events/recent":
        write_json(
            handler,
            {
                "ok": True,
                "events": EVENT_BUS.recent(
                    limit=query_int(query, "limit", 200),
                    min_id=query_int(query, "after", 0),
                    level=(query.get("level") or [None])[0],
                    category=(query.get("category") or [None])[0],
                ),
            },
        )
        return True
    if path == "/ca/events/stream":
        last_id = query_int(query, "after", 0)
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.send_header("cache-control", "no-cache")
        handler.send_header("connection", "close")
        handler.end_headers()
        try:
            for event in EVENT_BUS.recent(limit=200, min_id=last_id):
                last_id = max(last_id, int(event.get("id") or 0))
                handler.wfile.write(f"event: event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
            while True:
                events = EVENT_BUS.wait_after(last_id, timeout=15.0)
                if not events:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    continue
                for event in events:
                    last_id = max(last_id, int(event.get("id") or 0))
                    handler.wfile.write(f"event: event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return True
        except Exception as exc:
            try:
                router_log("DEBUG", f"events stream closed: {type(exc).__name__}: {exc}")
            except Exception:
                pass
        return True
    return False


def _safe_segment(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip(".-")
    return text[:120] or fallback


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        if value.strip().lower() in ("", "all", "*"):
            return ["all"] if value.strip() else []
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _chat_init_next_id() -> int:
    global _CHAT_NEXT_ID
    if _CHAT_NEXT_ID is not None:
        return _CHAT_NEXT_ID
    max_id = 0
    try:
        if CHAT_MESSAGES_PATH.exists():
            with CHAT_MESSAGES_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        max_id = max(max_id, int(item.get("id") or 0))
                    except Exception:
                        continue
    except Exception:
        pass
    _CHAT_NEXT_ID = max_id + 1
    return _CHAT_NEXT_ID


def _message_visible_to(message: dict[str, Any], recipient: str | None) -> bool:
    if not recipient:
        return True
    recipients = _as_string_list(message.get("recipients"))
    if not recipients or "all" in [r.lower() for r in recipients] or "*" in recipients:
        return True
    return recipient in recipients or recipient == str(message.get("sender_id") or "")


def read_chat_messages(after_id: int = 0, channel: str | None = None, recipient: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        if not CHAT_MESSAGES_PATH.exists():
            return []
        with CHAT_MESSAGES_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                try:
                    if int(item.get("id") or 0) <= after_id:
                        continue
                except Exception:
                    continue
                if channel:
                    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
                    aliases = {
                        str(item.get("channel") or ""),
                        str(meta.get("room_id") or ""),
                        str(meta.get("room") or ""),
                        str(meta.get("channel") or ""),
                    }
                    if channel not in aliases:
                        continue
                if not _message_visible_to(item, recipient):
                    continue
                messages.append(item)
                if len(messages) >= limit:
                    break
    except Exception as exc:
        router_log("WARN", f"chat read failed: {exc}")
    return messages


def append_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    global _CHAT_NEXT_ID
    with _CHAT_CONDITION:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CHAT_MESSAGES_PATH.exists() and CHAT_MESSAGES_PATH.stat().st_size > CHAT_MESSAGES_MAX_BYTES:
            CHAT_MESSAGES_PATH.replace(CHAT_MESSAGES_PATH.with_suffix(".jsonl.1"))
            _CHAT_NEXT_ID = 1
        next_id = _chat_init_next_id()
        _CHAT_NEXT_ID = next_id + 1
        message = {
            "id": next_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "channel": str(payload.get("channel") or "default"),
            "sender_id": str(payload.get("sender_id") or payload.get("sender") or "anonymous"),
            "recipients": _as_string_list(payload.get("recipients", payload.get("recipient_id"))),
            "thread_id": str(payload.get("thread_id") or payload.get("parent_id") or next_id),
            "parent_id": payload.get("parent_id"),
            "message": str(payload.get("message") or payload.get("text") or ""),
            "kind": str(payload.get("kind") or "message"),
            "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        }
        with CHAT_MESSAGES_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        _CHAT_CONDITION.notify_all()
        return message


def _channel_sse_status_public(name: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "url": state.get("url"),
        "channel": state.get("channel"),
        "sender_id": state.get("sender_id"),
        "recipient": state.get("recipient"),
        "running": bool(state.get("running")),
        "started_at": state.get("started_at"),
        "last_event_at": state.get("last_event_at"),
        "messages_received": int(state.get("messages_received") or 0),
        "event_filter": state.get("event_filter") or [],
        "read_timeout_seconds": state.get("read_timeout_seconds"),
        "mcp_endpoint": state.get("mcp_endpoint"),
        "mcp_initialized": bool(state.get("mcp_initialized")),
        "mcp_last_error": state.get("mcp_last_error"),
        "last_error": state.get("last_error"),
    }


def channel_sse_status() -> dict[str, Any]:
    with _CHANNEL_SSE_LOCK:
        return {name: _channel_sse_status_public(name, state) for name, state in _CHANNEL_SSE_CONNECTIONS.items()}


def _first_present_dict_value(*sources: Any, keys: tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value is not None:
                return value
    return None


def _event_payload_text(value: Any, depth: int = 0) -> str | None:
    if value is None or depth > 5:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return str(value)
    direct = _first_present_dict_value(value, keys=("content", "message", "text", "body", "summary"))
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    if isinstance(direct, dict):
        nested = _event_payload_text(direct, depth + 1)
        if nested:
            return nested
    for key in ("data", "event", "payload", "message", "notification", "item"):
        nested = _event_payload_text(value.get(key), depth + 1)
        if nested:
            return nested
    event_type = value.get("type") or value.get("event_type") or value.get("kind")
    if event_type:
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else value.get("data")
        if payload is not None:
            return f"{event_type}: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        return str(event_type)
    return None


def _event_meta_from_sources(*sources: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_meta = source.get("meta")
        if isinstance(source_meta, dict):
            meta.update(source_meta)
        for key in (
            "room_id",
            "room",
            "channel",
            "thread_id",
            "parent_id",
            "message_id",
            "event_id",
            "cursor",
            "sequence",
            "seq",
            "task_id",
            "round_id",
            "conversation_id",
            "session_id",
            "agent_id",
            "agent_name",
            "sender_id",
            "sender",
            "recipient_id",
            "recipient",
            "recipients",
            "target_id",
            "target",
            "type",
            "event_type",
            "kind",
            "timestamp",
            "created_at",
            "updated_at",
            "status",
            "priority",
            "title",
            "name",
            "model",
            "runtime",
        ):
            value = source.get(key)
            if value is not None and key not in meta:
                meta[key] = value
    return meta


def _metadata_key_is_sensitive(key: str) -> bool:
    return bool(re.search(r"(authorization|api[_-]?key|token|secret|password|credential|cookie)", key, re.I))


def _json_safe_metadata(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 8000 else value[:8000] + "...<truncated>"
    if isinstance(value, list):
        out = [_json_safe_metadata(item, depth + 1) for item in value[:200]]
        if len(value) > 200:
            out.append(f"...<{len(value) - 200} more>")
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:200]:
            skey = str(key)
            out[skey] = "[redacted]" if _metadata_key_is_sensitive(skey) else _json_safe_metadata(item, depth + 1)
        if len(items) > 200:
            out["..."] = f"<{len(items) - 200} more>"
        return out
    return str(value)


def _compact_json_for_prompt(value: Any, max_chars: int = 2400) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 16] + "...<truncated>"


def _sse_payload_to_chat_payload(data_text: str, event_name: str, defaults: dict[str, Any], event_id: str | None = None) -> dict[str, Any] | None:
    text = (data_text or "").strip()
    if not text or text == "[DONE]":
        return None
    if (event_name or "").strip().lower() == "endpoint":
        return None
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    meta: dict[str, Any] = {
        "sse_event": event_name or "message",
        "sse_source": defaults.get("name") or "",
    }
    if event_id:
        meta["sse_id"] = event_id
    content = text
    kind = "sse"
    method = str(event_name or "message")
    event_filter = defaults.get("event_filter")
    allowed_events = {str(item).strip() for item in event_filter if str(item).strip()} if isinstance(event_filter, list) else set()
    if isinstance(parsed, dict):
        method = str(parsed.get("method") or event_name or "message")
        meta["sse_json"] = _json_safe_metadata(parsed)
        if parsed.get("jsonrpc") is not None:
            meta["jsonrpc"] = parsed.get("jsonrpc")
        if parsed.get("id") is not None:
            meta["rpc_id"] = parsed.get("id")
        if parsed.get("method") is not None:
            meta["mcp_method"] = parsed.get("method")
        params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
        payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
        data = params.get("data") if isinstance(params.get("data"), dict) else {}
        event = params.get("event") if isinstance(params.get("event"), dict) else {}
        nested_payload = (
            data.get("payload") if isinstance(data.get("payload"), dict) else
            event.get("payload") if isinstance(event.get("payload"), dict) else {}
        )
        meta.update(_event_meta_from_sources(parsed, params, payload, data, event, nested_payload))
        content = _event_payload_text(params) or _event_payload_text(payload) or _event_payload_text(data) or _event_payload_text(event) or content
        kind = method.replace("notifications/claude/", "").replace("/", ".") if method else "sse"
    if allowed_events and method not in allowed_events and (event_name or "message") not in allowed_events:
        return None
    channel = defaults.get("channel") or "default"
    if str(channel) == "default" and meta.get("channel"):
        channel = meta.get("channel")
    return {
        "channel": channel,
        "sender_id": meta.get("sender_id") or meta.get("agent_id") or defaults.get("sender_id") or "sse",
        "recipients": meta.get("recipient_id") or defaults.get("recipient") or defaults.get("recipients") or "all",
        "thread_id": meta.get("thread_id"),
        "parent_id": meta.get("parent_id"),
        "kind": kind,
        "message": content,
        "meta": meta,
    }


def _channel_sse_set_state(name: str, **updates: Any) -> None:
    with _CHANNEL_SSE_LOCK:
        state = _CHANNEL_SSE_CONNECTIONS.get(name)
        if state:
            state.update(updates)


def _channel_sse_absolute_endpoint(stream_url: str, endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return urllib.parse.urljoin(stream_url, endpoint)


def _mcp_sse_post_json(endpoint: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> Any:
    request_headers = {**headers, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return data.decode("utf-8", errors="replace")


def _channel_sse_maybe_initialize_mcp(name: str, endpoint_text: str) -> None:
    with _CHANNEL_SSE_LOCK:
        state = _CHANNEL_SSE_CONNECTIONS.get(name)
        if not state:
            return
        if not bool(state.get("mcp_enabled", True)):
            return
        if state.get("mcp_initialized"):
            return
        stream_url = str(state.get("url") or "")
        headers = dict(state.get("headers") or {})
        timeout = max(5.0, min(120.0, float(state.get("mcp_timeout_seconds") or 20.0)))
        protocol_version = str(state.get("mcp_protocol_version") or "2024-11-05")
    endpoint = _channel_sse_absolute_endpoint(stream_url, endpoint_text)
    try:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "claude-any-channel-bridge", "version": VERSION},
            },
        }
        _mcp_sse_post_json(endpoint, headers, initialize, timeout)
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        _mcp_sse_post_json(endpoint, headers, initialized, timeout)
        _channel_sse_set_state(name, mcp_endpoint=endpoint, mcp_initialized=True, mcp_last_error=None)
        router_log("INFO", f"channel_sse_mcp_initialized name={name} endpoint={endpoint}")
    except Exception as exc:
        _channel_sse_set_state(name, mcp_endpoint=endpoint, mcp_initialized=False, mcp_last_error=f"{type(exc).__name__}: {exc}")
        router_log("WARN", f"channel_sse_mcp_initialize_failed name={name} endpoint={endpoint} error={type(exc).__name__}: {exc}")


def _channel_sse_dispatch(name: str, event_name: str, data_lines: list[str], event_id: str | None = None) -> None:
    data_text = "\n".join(data_lines)
    if (event_name or "").strip().lower() == "endpoint":
        _channel_sse_maybe_initialize_mcp(name, data_text)
        return
    with _CHANNEL_SSE_LOCK:
        state = _CHANNEL_SSE_CONNECTIONS.get(name)
        if not state:
            return
        defaults = dict(state)
    payload = _sse_payload_to_chat_payload(data_text, event_name, defaults, event_id=event_id)
    if not payload:
        return
    saved = append_chat_message(payload)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _CHANNEL_SSE_LOCK:
        state = _CHANNEL_SSE_CONNECTIONS.get(name)
        if state:
            state["last_event_at"] = now
            state["messages_received"] = int(state.get("messages_received") or 0) + 1
            state["last_error"] = None
    router_log(
        "INFO",
        f"channel_sse_message_received name={name} event={event_name or 'message'} message_id={saved.get('id')} channel={saved.get('channel')}",
    )


def _channel_sse_worker(name: str) -> None:
    while True:
        with _CHANNEL_SSE_LOCK:
            state = _CHANNEL_SSE_CONNECTIONS.get(name)
            if not state or not state.get("running"):
                return
            url = str(state.get("url") or "")
            headers = dict(state.get("headers") or {})
            read_timeout = max(5.0, min(3600.0, float(state.get("read_timeout_seconds") or 300.0)))
            retry_seconds = max(1.0, min(60.0, float(state.get("retry_seconds") or 5.0)))
        event_name = "message"
        event_id: str | None = None
        data_lines: list[str] = []
        try:
            req = urllib.request.Request(url, headers={**headers, "Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=read_timeout) as response:
                _channel_sse_set_state(name, last_error=None)
                router_log("INFO", f"channel_sse_connected name={name} url={url}")
                while True:
                    with _CHANNEL_SSE_LOCK:
                        current = _CHANNEL_SSE_CONNECTIONS.get(name)
                        if not current or not current.get("running"):
                            return
                    raw = response.readline()
                    if raw == b"":
                        raise ConnectionError("SSE stream ended")
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            _channel_sse_dispatch(name, event_name, data_lines, event_id=event_id)
                        event_name = "message"
                        event_id = None
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    field, _, value = line.partition(":")
                    if value.startswith(" "):
                        value = value[1:]
                    if field == "event":
                        event_name = value or "message"
                    elif field == "data":
                        data_lines.append(value)
                    elif field == "id":
                        event_id = value
                    elif field == "retry":
                        try:
                            retry_seconds = max(1.0, min(60.0, int(value) / 1000.0))
                        except Exception:
                            pass
        except Exception as exc:
            with _CHANNEL_SSE_LOCK:
                state = _CHANNEL_SSE_CONNECTIONS.get(name)
                if not state or not state.get("running"):
                    return
                state["last_error"] = f"{type(exc).__name__}: {exc}"
            router_log("WARN", f"channel_sse_reconnect name={name} error={type(exc).__name__}: {exc}")
            time.sleep(retry_seconds)


def start_channel_sse_connection(config: dict[str, Any]) -> dict[str, Any]:
    url = str(config.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("SSE url must start with http:// or https://")
    name = _safe_segment(str(config.get("name") or urllib.parse.urlparse(url).netloc or "sse"), "sse")
    headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    headers = {str(k): str(v) for k, v in headers.items() if str(k).strip()}
    token = str(config.get("bearer_token") or config.get("token") or "").strip()
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"
    event_filter = config.get("event_filter")
    if isinstance(event_filter, str):
        event_filter = [item.strip() for item in event_filter.split(",") if item.strip()]
    elif isinstance(event_filter, list):
        event_filter = [str(item).strip() for item in event_filter if str(item).strip()]
    else:
        event_filter = []
    with _CHANNEL_SSE_LOCK:
        prior = _CHANNEL_SSE_CONNECTIONS.get(name)
        if prior:
            prior["running"] = False
        state = {
            "name": name,
            "url": url,
            "headers": headers,
            "channel": str(config.get("channel") or "default"),
            "sender_id": str(config.get("sender_id") or config.get("sender") or name),
            "recipient": str(config.get("recipient") or config.get("recipient_id") or config.get("to") or "all"),
            "running": True,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_event_at": None,
            "messages_received": 0,
            "last_error": None,
            "event_filter": event_filter,
            "read_timeout_seconds": float(config.get("read_timeout_seconds") or config.get("timeout") or 300.0),
            "retry_seconds": float(config.get("retry_seconds") or 5.0),
            "mcp_enabled": bool(config.get("mcp", config.get("mcp_enabled", True))),
            "mcp_endpoint": None,
            "mcp_initialized": False,
            "mcp_last_error": None,
            "mcp_protocol_version": str(config.get("mcp_protocol_version") or "2024-11-05"),
            "mcp_timeout_seconds": float(config.get("mcp_timeout_seconds") or 20.0),
        }
        _CHANNEL_SSE_CONNECTIONS[name] = state
    thread = threading.Thread(target=_channel_sse_worker, args=(name,), daemon=True, name=f"claude-any-channel-sse-{name}")
    thread.start()
    return _channel_sse_status_public(name, state)


def stop_channel_sse_connection(name: str | None = None) -> dict[str, Any]:
    stopped: list[str] = []
    with _CHANNEL_SSE_LOCK:
        targets = [name] if name else list(_CHANNEL_SSE_CONNECTIONS)
        for target in targets:
            if not target:
                continue
            state = _CHANNEL_SSE_CONNECTIONS.get(target)
            if state:
                state["running"] = False
                stopped.append(target)
    return {"stopped": stopped, "connections": channel_sse_status()}


def _channel_mcp_session_id() -> str:
    return f"s{os.getpid()}-{time.time_ns()}"


def _native_channel_meta_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(_json_safe_metadata(value), ensure_ascii=False, separators=(",", ":"), default=str)


def _native_channel_meta(message: dict[str, Any]) -> dict[str, str]:
    raw_meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
    meta: dict[str, str] = {}
    for key, value in raw_meta.items():
        name = str(key or "").strip()
        if not name:
            continue
        meta[name] = _native_channel_meta_value(value)
    base = {
        "claude_any_message_id": message.get("id"),
        "channel": message.get("channel") or "default",
        "sender_id": message.get("sender_id") or "channel",
        "thread_id": message.get("thread_id"),
        "parent_id": message.get("parent_id"),
        "kind": message.get("kind"),
    }
    for key, value in base.items():
        if value is not None:
            meta[key] = _native_channel_meta_value(value)
    if raw_meta:
        meta["claude_any_meta_json"] = json.dumps(_json_safe_metadata(raw_meta), ensure_ascii=False, separators=(",", ":"), default=str)
    return meta


def _channel_mcp_notification(message: dict[str, Any]) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", str(message.get("message") or "")).strip()
    channel = str(message.get("channel") or "default")
    sender = str(message.get("sender_id") or "channel")
    prefix = f"[{channel}] {sender}"
    content = f"{prefix}: {text}" if text else prefix
    return {
        "jsonrpc": "2.0",
        "method": "notifications/claude/channel",
        "params": {
            "content": content,
            "meta": _native_channel_meta(message),
        },
    }


def _channel_mcp_capabilities() -> dict[str, Any]:
    return {
        "tools": {"listChanged": False},
        "experimental": {
            "claude/channel": {},
        },
    }


def _write_sse_event(handler: BaseHTTPRequestHandler, event: str, data: Any, event_id: int | None = None) -> None:
    if event_id is not None:
        handler.wfile.write(f"id: {event_id}\n".encode("utf-8"))
    handler.wfile.write(f"event: {event}\n".encode("utf-8"))
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for line in payload.splitlines() or [""]:
        handler.wfile.write(f"data: {line}\n".encode("utf-8"))
    handler.wfile.write(b"\n")
    handler.wfile.flush()


def _send_channel_mcp_sse_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache, no-transform")
    handler.send_header("connection", "keep-alive")
    handler.send_header("x-accel-buffering", "no")
    handler.end_headers()


def _channel_mcp_enqueue(session: str, payload: dict[str, Any]) -> bool:
    if not session:
        return False
    with _CHANNEL_MCP_LOCK:
        state = _CHANNEL_MCP_SESSIONS.get(session)
        if not state:
            return False
        outbox = state.setdefault("outbox", [])
        if isinstance(outbox, list):
            outbox.append(payload)
        else:
            state["outbox"] = [payload]
    with _CHAT_CONDITION:
        _CHAT_CONDITION.notify_all()
    return True


def _channel_mcp_take_outbox(session: str) -> list[dict[str, Any]]:
    with _CHANNEL_MCP_LOCK:
        state = _CHANNEL_MCP_SESSIONS.get(session)
        if not state:
            return []
        outbox = state.get("outbox")
        if not isinstance(outbox, list) or not outbox:
            return []
        state["outbox"] = []
        return [item for item in outbox if isinstance(item, dict)]


def _channel_mcp_initialize_response(request_id: Any, protocol: str) -> dict[str, Any]:
    # This endpoint implements the legacy HTTP+SSE transport, whose stable
    # protocol version is 2024-11-05 even when newer clients initiate the
    # handshake with a newer preferred protocol.
    protocol = "2024-11-05"
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": protocol,
            "capabilities": _channel_mcp_capabilities(),
            "serverInfo": {"name": "claude-any-router", "version": VERSION},
        },
    }


def _channel_mcp_write_cursor_locked(last_id: int) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = CHANNEL_MCP_CURSOR_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps({"last_id": max(0, int(last_id))}, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp_path.replace(CHANNEL_MCP_CURSOR_PATH)


def _channel_mcp_read_cursor_locked() -> int:
    global _CHANNEL_MCP_CURSOR_LAST_ID
    if _CHANNEL_MCP_CURSOR_LAST_ID is not None:
        return _CHANNEL_MCP_CURSOR_LAST_ID
    if CHANNEL_MCP_CURSOR_PATH.exists():
        try:
            data = json.loads(CHANNEL_MCP_CURSOR_PATH.read_text(encoding="utf-8"))
            _CHANNEL_MCP_CURSOR_LAST_ID = max(0, int(data.get("last_id") or 0))
            return _CHANNEL_MCP_CURSOR_LAST_ID
        except Exception as exc:
            router_log("WARN", f"channel_mcp_cursor_read_failed error={type(exc).__name__}: {exc}")
    _CHANNEL_MCP_CURSOR_LAST_ID = max(0, _chat_init_next_id() - 1)
    try:
        _channel_mcp_write_cursor_locked(_CHANNEL_MCP_CURSOR_LAST_ID)
    except Exception as exc:
        router_log("WARN", f"channel_mcp_cursor_write_failed error={type(exc).__name__}: {exc}")
    return _CHANNEL_MCP_CURSOR_LAST_ID


def _channel_mcp_ensure_cursor_initialized() -> int:
    with _CHANNEL_MCP_CURSOR_LOCK:
        return _channel_mcp_read_cursor_locked()


def _channel_mcp_update_cursor(last_id: int) -> None:
    global _CHANNEL_MCP_CURSOR_LAST_ID
    if last_id < 0:
        return
    with _CHANNEL_MCP_CURSOR_LOCK:
        current = _channel_mcp_read_cursor_locked()
        if last_id <= current:
            return
        _CHANNEL_MCP_CURSOR_LAST_ID = int(last_id)
        try:
            _channel_mcp_write_cursor_locked(_CHANNEL_MCP_CURSOR_LAST_ID)
        except Exception as exc:
            router_log("WARN", f"channel_mcp_cursor_write_failed error={type(exc).__name__}: {exc}")


def _channel_mcp_parse_event_id(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(0, int(text))
    except Exception:
        return None


def _channel_mcp_client_last_event_id(handler: BaseHTTPRequestHandler) -> int | None:
    try:
        event_id = _channel_mcp_parse_event_id(handler.headers.get("Last-Event-ID"))
        if event_id is not None:
            return event_id
    except Exception:
        pass
    try:
        params = _query_params(handler)
        for key in ("lastEventId", "last_event_id", "last_id"):
            event_id = _channel_mcp_parse_event_id(_first_param(params, key))
            if event_id is not None:
                return event_id
    except Exception:
        pass
    return None


def _channel_mcp_session_start_last_id(handler: BaseHTTPRequestHandler) -> int:
    cursor_last_id = _channel_mcp_ensure_cursor_initialized()
    client_last_id = _channel_mcp_client_last_event_id(handler)
    if client_last_id is None:
        return cursor_last_id
    if client_last_id > cursor_last_id:
        _channel_mcp_update_cursor(client_last_id)
    router_log("INFO", f"channel_mcp_resume client_last_id={client_last_id} cursor_last_id={cursor_last_id}")
    return client_last_id


def _channel_mcp_notifications_for_messages(
    messages: list[dict[str, Any]],
    session: str = "",
) -> tuple[int, list[tuple[int, dict[str, Any]]]]:
    last_id = 0
    events: list[tuple[int, dict[str, Any]]] = []
    for message in messages:
        message_id = int(message.get("id") or 0)
        last_id = max(last_id, message_id)
        noise_reason = _channel_wake_message_noise_reason(message)
        if noise_reason:
            router_log(
                "INFO",
                f"channel_mcp_skipped_noise session={session or '-'} message_id={message.get('id')} channel={message.get('channel')} reason={noise_reason}",
            )
            continue
        events.append((last_id, _channel_mcp_notification(message)))
        router_log(
            "INFO",
            f"channel_mcp_notification_prepared session={session or '-'} message_id={message.get('id')} channel={message.get('channel')}",
        )
    return last_id, events


def handle_channel_mcp_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    if path == "/ca/mcp/health":
        write_json(handler, {"ok": True, "name": "claude-any-router", "sse": "/ca/mcp/sse"})
        return True
    if path != "/ca/mcp/sse":
        return False
    session = _channel_mcp_session_id()
    last_id = _channel_mcp_session_start_last_id(handler)
    with _CHANNEL_MCP_LOCK:
        _CHANNEL_MCP_SESSIONS[session] = {"created_at": time.time(), "last_id": last_id, "initialized": False, "outbox": []}
    router_log("INFO", f"channel_mcp_session_started session={session} last_id={last_id}")
    started_at = time.time()
    close_reason = "finished"
    _send_channel_mcp_sse_headers(handler)
    _write_sse_event(handler, "endpoint", f"/ca/mcp/messages?sessionId={urllib.parse.quote(session)}")
    try:
        while True:
            with _CHANNEL_MCP_LOCK:
                state = _CHANNEL_MCP_SESSIONS.get(session)
                if not state:
                    close_reason = "session_missing"
                    return True
                last_id = int(state.get("last_id") or 0)
                initialized = bool(state.get("initialized"))
            outbox = _channel_mcp_take_outbox(session)
            if outbox:
                for payload in outbox:
                    _write_sse_event(handler, "message", payload)
                router_log("INFO", f"channel_mcp_rpc_flushed session={session} count={len(outbox)}")
                continue
            if not initialized:
                handler.wfile.write(b": waiting-for-initialize\n\n")
                handler.wfile.flush()
                with _CHAT_CONDITION:
                    _CHAT_CONDITION.wait(timeout=1.0)
                continue
            messages = read_chat_messages(last_id, None, None, 100)
            if messages:
                delivered_last_id, events = _channel_mcp_notifications_for_messages(messages, session)
                last_id = max(last_id, delivered_last_id)
                for event_id, notification in events:
                    _write_sse_event(handler, "message", notification, event_id)
                    router_log("INFO", f"channel_mcp_notification_written session={session} message_id={event_id}")
                if not events:
                    _channel_mcp_update_cursor(last_id)
                with _CHANNEL_MCP_LOCK:
                    state = _CHANNEL_MCP_SESSIONS.get(session)
                    if state:
                        state["last_id"] = last_id
                continue
            handler.wfile.write(b": keepalive\n\n")
            handler.wfile.flush()
            with _CHAT_CONDITION:
                _CHAT_CONDITION.wait(timeout=5.0)
    except (BrokenPipeError, ConnectionError, ConnectionResetError) as exc:
        close_reason = type(exc).__name__
        return True
    except Exception as exc:
        close_reason = type(exc).__name__
        router_log("ERROR", f"channel_mcp_session_failed session={session} error={type(exc).__name__}: {exc}")
        return True
    finally:
        router_log("INFO", f"channel_mcp_session_closed session={session} reason={close_reason} age={time.time() - started_at:.1f}s")
        with _CHANNEL_MCP_LOCK:
            _CHANNEL_MCP_SESSIONS.pop(session, None)


def handle_channel_mcp_post(handler: BaseHTTPRequestHandler, path: str, body: dict[str, Any]) -> bool:
    if path != "/ca/mcp/messages":
        return False
    params = _query_params(handler)
    session = _first_param(params, "sessionId") or _first_param(params, "session")
    with _CHANNEL_MCP_LOCK:
        if session and session in _CHANNEL_MCP_SESSIONS:
            _CHANNEL_MCP_SESSIONS[session]["last_seen_at"] = time.time()
    method = str(body.get("method") or "")
    request_id = body.get("id")
    response: dict[str, Any] | None = None
    if method == "initialize":
        protocol = "2024-11-05"
        req_params = body.get("params") if isinstance(body.get("params"), dict) else {}
        if req_params.get("protocolVersion"):
            protocol = str(req_params["protocolVersion"])
        with _CHANNEL_MCP_LOCK:
            if session and session in _CHANNEL_MCP_SESSIONS:
                _CHANNEL_MCP_SESSIONS[session]["initialized"] = True
        response = _channel_mcp_initialize_response(request_id, protocol)
        router_log("INFO", f"channel_mcp_initialized session={session or '-'} protocol={protocol}")
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": request_id, "result": {"tools": []}}
    elif method == "ping":
        response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
    elif request_id is not None:
        response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if response is not None:
        if not _channel_mcp_enqueue(session, response):
            router_log("WARN", f"channel_mcp_rpc_enqueue_failed session={session or '-'} method={method}")
            write_json(
                handler,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": "MCP SSE session is not connected"},
                },
                404,
            )
            return True
        router_log("INFO", f"channel_mcp_rpc_queued session={session or '-'} method={method} request_id={request_id}")
    write_accepted_response(handler)
    return True


def _query_params(handler: BaseHTTPRequestHandler) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query, keep_blank_values=True)


def _first_param(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    return values[0] if values else default


def handle_chat_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    channel_alias = path.startswith("/ca/channel/")
    if channel_alias:
        path = "/ca/chat/" + path[len("/ca/channel/"):]
    if path == "/ca/chat/health":
        write_json(
            handler,
            {
                "ok": True,
                "base": ROUTER_BASE,
                "messages": "/ca/channel/messages" if channel_alias else "/ca/chat/messages",
                "wait": "/ca/channel/wait" if channel_alias else "/ca/chat/wait",
                "stream": "/ca/channel/stream" if channel_alias else "/ca/chat/stream",
                "notify": "/ca/channel/notify",
                "sse_status": "/ca/channel/sse/status",
                "sse_connect": "POST /ca/channel/sse/connect",
                "sse_disconnect": "POST /ca/channel/sse/disconnect",
                "native_note": "This is the Claude Any bridge API, not Claude Code's gated native --channels path.",
            },
        )
        return True
    if path == "/ca/chat/sse/status":
        write_json(handler, {"ok": True, "connections": channel_sse_status()})
        return True
    if path in ("/ca/chat/messages", "/ca/chat/wait"):
        params = _query_params(handler)
        after = int(_first_param(params, "after", "0") or 0)
        limit = max(1, min(500, int(_first_param(params, "limit", "100") or 100)))
        channel = _first_param(params, "channel", "") or None
        recipient = _first_param(params, "recipient", "") or _first_param(params, "recipient_id", "") or None
        timeout = 0.0 if path.endswith("/messages") else max(0.0, min(300.0, float(_first_param(params, "timeout", "60") or 60)))
        deadline = time.time() + timeout
        messages = read_chat_messages(after, channel, recipient, limit)
        while not messages and timeout > 0 and time.time() < deadline:
            with _CHAT_CONDITION:
                _CHAT_CONDITION.wait(timeout=min(5.0, max(0.0, deadline - time.time())))
            messages = read_chat_messages(after, channel, recipient, limit)
        write_json(handler, {"ok": True, "messages": messages, "last_id": messages[-1]["id"] if messages else after})
        return True
    if path == "/ca/chat/stream":
        params = _query_params(handler)
        after = int(_first_param(params, "after", "0") or 0)
        channel = _first_param(params, "channel", "") or None
        recipient = _first_param(params, "recipient", "") or _first_param(params, "recipient_id", "") or None
        timeout = max(1.0, min(3600.0, float(_first_param(params, "timeout", "300") or 300)))
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.send_header("cache-control", "no-cache")
        handler.send_header("connection", "close")
        handler.end_headers()
        deadline = time.time() + timeout
        last_id = after
        try:
            while time.time() < deadline:
                messages = read_chat_messages(last_id, channel, recipient, 100)
                for message in messages:
                    last_id = int(message["id"])
                    handler.wfile.write(f"id: {last_id}\n".encode("utf-8"))
                    handler.wfile.write(b"event: message\n")
                    handler.wfile.write(("data: " + json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8"))
                    handler.wfile.flush()
                if messages:
                    continue
                handler.wfile.write(b": wait\n\n")
                handler.wfile.flush()
                with _CHAT_CONDITION:
                    _CHAT_CONDITION.wait(timeout=min(15.0, max(0.0, deadline - time.time())))
        except (BrokenPipeError, ConnectionError):
            pass
        return True
    if path.startswith("/ca/chat/files/"):
        name = _safe_segment(urllib.parse.unquote(path[len("/ca/chat/files/"):]), "file")
        target = CHAT_FILES_DIR / name
        if not target.exists() or not target.is_file():
            write_json(handler, {"ok": False, "error": "not_found"}, 404)
            return True
        data = target.read_bytes()
        handler.send_response(200)
        handler.send_header("content-type", "application/octet-stream")
        handler.send_header("content-length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return True
    return False


def handle_chat_post(handler: BaseHTTPRequestHandler, path: str, body: dict[str, Any]) -> bool:
    channel_alias = path.startswith("/ca/channel/")
    if channel_alias:
        path = "/ca/chat/" + path[len("/ca/channel/"):]
    if path == "/ca/chat/sse/connect":
        try:
            status = start_channel_sse_connection(body)
            write_json(handler, {"ok": True, "connection": status})
        except Exception as exc:
            write_json(handler, {"ok": False, "error": str(exc)}, 400)
        return True
    if path == "/ca/chat/sse/disconnect":
        name = body.get("name")
        result = stop_channel_sse_connection(str(name) if name else None)
        write_json(handler, {"ok": True, **result})
        return True
    if path == "/ca/chat/notify":
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        meta = params.get("meta") if isinstance(params.get("meta"), dict) else body.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        content = str(params.get("content") or body.get("content") or body.get("message") or body.get("text") or "")
        message = append_chat_message({
            "channel": body.get("channel") or meta.get("channel") or "default",
            "sender_id": body.get("sender_id") or body.get("sender") or body.get("server") or meta.get("source") or "channel",
            "recipients": body.get("recipients", body.get("recipient_id", meta.get("recipients", "all"))),
            "thread_id": body.get("thread_id") or meta.get("thread_id"),
            "parent_id": body.get("parent_id") or meta.get("parent_id"),
            "kind": body.get("kind") or "channel",
            "message": content,
            "meta": meta,
        })
        write_json(handler, {"ok": True, "message": message})
        return True
    if path == "/ca/chat/messages":
        message = append_chat_message(body)
        write_json(handler, {"ok": True, "message": message})
        return True
    if path == "/ca/chat/files":
        CHAT_FILES_DIR.mkdir(parents=True, exist_ok=True)
        raw_name = str(body.get("name") or f"file-{int(time.time())}.txt")
        name = f"{int(time.time())}-{_safe_segment(raw_name, 'file')}"
        content = body.get("content", "")
        if body.get("encoding") == "base64":
            data = base64.b64decode(str(content).encode("ascii"))
        else:
            data = str(content).encode("utf-8")
        target = CHAT_FILES_DIR / name
        target.write_bytes(data)
        url = f"{ROUTER_BASE}/ca/chat/files/{urllib.parse.quote(name)}"
        if body.get("announce", True):
            append_chat_message({
                "channel": body.get("channel", "default"),
                "sender_id": body.get("sender_id", "system"),
                "recipients": body.get("recipients", "all"),
                "thread_id": body.get("thread_id"),
                "parent_id": body.get("parent_id"),
                "kind": "file",
                "message": url,
                "meta": {"name": raw_name, "url": url},
            })
        write_json(handler, {"ok": True, "name": name, "url": url, "bytes": len(data)})
        return True
    return False


def handle_plan_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    if path == "/ca/plan/artifacts":
        PLAN_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        items = []
        for item in sorted(PLAN_ARTIFACTS_DIR.glob("*")):
            if item.is_file():
                items.append({"name": item.name, "bytes": item.stat().st_size, "url": f"{ROUTER_BASE}/ca/plan/artifacts/{urllib.parse.quote(item.name)}"})
        write_json(handler, {"ok": True, "artifacts": items})
        return True
    if path.startswith("/ca/plan/artifacts/"):
        name = _safe_segment(urllib.parse.unquote(path[len("/ca/plan/artifacts/"):]), "plan.md")
        target = PLAN_ARTIFACTS_DIR / name
        if not target.exists() or not target.is_file():
            write_json(handler, {"ok": False, "error": "not_found"}, 404)
            return True
        content_type = "text/markdown; charset=utf-8" if target.suffix.lower() in (".md", ".markdown") else "text/plain; charset=utf-8"
        write_text_response(handler, target.read_text(encoding="utf-8", errors="replace"), content_type=content_type)
        return True
    return False


def handle_plan_post(handler: BaseHTTPRequestHandler, path: str, body: dict[str, Any]) -> bool:
    if path != "/ca/plan/artifacts":
        return False
    PLAN_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    title = str(body.get("title") or "plan")
    content = str(body.get("content") or body.get("message") or "")
    name = _safe_segment(str(body.get("name") or f"{int(time.time())}-{title}.md"), "plan.md")
    if "." not in name:
        name += ".md"
    target = PLAN_ARTIFACTS_DIR / name
    target.write_text(content, encoding="utf-8")
    latest = PLAN_ARTIFACTS_DIR / "latest.md"
    if target.name != latest.name:
        latest.write_text(content, encoding="utf-8")
    url = f"{ROUTER_BASE}/ca/plan/artifacts/{urllib.parse.quote(name)}"
    if body.get("announce", True):
        append_chat_message({
            "channel": body.get("channel", "plan"),
            "sender_id": body.get("sender_id", "plan"),
            "recipients": body.get("recipients", "all"),
            "kind": "plan",
            "message": url,
            "meta": {"title": title, "url": url, "name": name},
        })
    write_json(handler, {"ok": True, "name": name, "url": url, "latest_url": f"{ROUTER_BASE}/ca/plan/artifacts/latest.md"})
    return True


def estimate_tokens(body: Any, _cache: dict[int, int] | None = None) -> int:
    if _cache is not None:
        body_id = id(body)
        if body_id in _cache:
            return _cache[body_id]
    text = json.dumps(body, ensure_ascii=False)
    result = max(1, len(text) // 4)
    if _cache is not None:
        _cache[id(body)] = result
    return result


def anthropic_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content) if content is not None else ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(str(block.get("text", "")))
        elif btype == "tool_result":
            tool_text = anthropic_content_to_text(block.get("content", ""))
            parts.append(f"Tool result for {block.get('tool_use_id', 'tool')}:\n{tool_text}")
    return "\n".join(part for part in parts if part)


PROMPT_TOOL_INPUT_FIELD_LIMIT = 1200
PROMPT_TOOL_RESULT_LIMIT = 12000
PROMPT_MESSAGE_TEXT_LIMIT = 20000


def truncate_for_prompt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n...[truncated {omitted} chars]..."


def compact_tool_value_for_prompt(value: Any, limit: int = PROMPT_TOOL_INPUT_FIELD_LIMIT) -> Any:
    if isinstance(value, str):
        return truncate_for_prompt(value, limit)
    if isinstance(value, list):
        return [compact_tool_value_for_prompt(item, limit) for item in value[:20]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"content", "old_string", "new_string", "command"} and isinstance(item, str):
                compact[key] = truncate_for_prompt(item, limit)
            else:
                compact[key] = compact_tool_value_for_prompt(item, limit)
        return compact
    return value


def tool_input_for_prompt(tool_input: Any) -> str:
    if not tool_input:
        return "{}"
    compact = compact_tool_value_for_prompt(tool_input)
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def compact_message_text_for_prompt(text: str) -> str:
    return truncate_for_prompt(text, PROMPT_MESSAGE_TEXT_LIMIT)


def is_advisor_request(body: dict[str, Any]) -> bool:
    return "CLAUDE_ANY_ADVISOR_CALL" in latest_user_text(body)


def is_router_debug_request(body: dict[str, Any]) -> bool:
    return "CLAUDE_ANY_ROUTER_DEBUG_ACCESS" in latest_user_text(body)


def parse_channel_bridge_args(raw: str) -> tuple[str, dict[str, str]]:
    text = (raw or "").strip()
    if not text:
        return "status", {}
    try:
        parts = shlex.split(text)
    except Exception:
        parts = text.split()
    if not parts:
        return "status", {}
    command = parts[0].strip().lower()
    if command not in {"status", "poll", "wait", "send", "post", "sse"}:
        parts = ["status", *parts]
        command = "status"
    options: dict[str, str] = {}
    loose: list[str] = []
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            options[key.strip().lower().replace("-", "_")] = value.strip()
        elif part:
            loose.append(part)
    if loose and "message" not in options and command in {"send", "post"}:
        options["message"] = " ".join(loose)
    return command, options


def format_channel_messages(messages: list[dict[str, Any]], after: int) -> str:
    if not messages:
        return f"No channel messages after id {after}."
    lines = [f"Channel bridge messages ({len(messages)}):"]
    for item in messages:
        recipients = item.get("recipients") or []
        if isinstance(recipients, list):
            recipient_text = ",".join(str(r) for r in recipients) or "all"
        else:
            recipient_text = str(recipients or "all")
        text = re.sub(r"\s+", " ", str(item.get("message") or "")).strip()
        if len(text) > 500:
            text = text[:500].rstrip() + "..."
        lines.append(
            f"- #{item.get('id')} [{item.get('channel')}] {item.get('sender_id')} -> {recipient_text}: {text}"
        )
    lines.append(f"Last id: {messages[-1].get('id')}")
    return "\n".join(lines)


def router_debug_value_from_body(body: dict[str, Any]) -> str:
    text = latest_user_text(body)
    marker = "CLAUDE_ANY_ROUTER_DEBUG_ACCESS"
    if marker not in text:
        return "status"
    tail = text.split(marker, 1)[1]
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("value:"):
            value = stripped.split(":", 1)[1].strip()
            return value or "toggle"
    return tail.strip() or "toggle"


def advisor_focus_from_body(body: dict[str, Any]) -> str:
    text = latest_user_text(body)
    marker = "CLAUDE_ANY_ADVISOR_CALL"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].strip()


def advisor_model_enabled(pcfg: dict[str, Any]) -> str:
    return str(pcfg.get("advisor_model") or "").strip()


def advisor_provider_kind(provider: str) -> str:
    if provider in ("ollama", "ollama-cloud"):
        return "ollama"
    if provider == "nvidia-hosted":
        return "openai-compatible"
    return ""


def advisor_provider_supported(provider: str) -> bool:
    return bool(advisor_provider_kind(provider))


def advisor_tool_schema() -> dict[str, Any]:
    return {
        "name": "advisor",
        "description": (
            "Consult a second, stronger advisor model for an independent review before you make an important "
            "plan, architecture, debugging, or final-completion decision. Use this when additional scrutiny could "
            "catch gaps, risks, or better next steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The specific decision, plan, code path, or risk you want the advisor to review.",
                }
            },
            "required": ["question"],
        },
    }


def body_with_advisor_tool(body: dict[str, Any], pcfg: dict[str, Any]) -> dict[str, Any]:
    if not advisor_model_enabled(pcfg):
        return body
    tools = body.get("tools")
    if not isinstance(tools, list):
        tools = []
    if any(isinstance(tool, dict) and str(tool.get("name") or "") == "advisor" for tool in tools):
        return body
    out = dict(body)
    out["tools"] = [*tools, advisor_tool_schema()]
    return out


def advisor_tool_focus_from_message(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if str(block.get("name") or "") != "advisor":
            continue
        tool_input = block.get("input")
        if isinstance(tool_input, dict):
            for key in ("question", "prompt", "focus", "task"):
                value = tool_input.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return "advisor tool call"
    return None


def tool_review_context_from_message(message: dict[str, Any], trigger: str) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    sections: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "").strip()
        if not name:
            continue
        if name == "advisor":
            continue
        tool_input = block.get("input")
        input_text = tool_input_for_prompt(tool_input)
        if name == "ExitPlanMode":
            sections.append(
                "Review target: ExitPlanMode plan before user approval.\n"
                "The executor is about to submit this plan. Review the actual plan/tool input below.\n"
                f"Tool input:\n{input_text}"
            )
        elif trigger:
            sections.append(f"Review target tool: {name} ({trigger}).\nTool input:\n{input_text}")
    return "\n\n".join(sections)


def advisor_focus_for_message(message: dict[str, Any], trigger: str | None) -> tuple[str | None, str | None]:
    explicit_focus = advisor_tool_focus_from_message(message)
    if explicit_focus:
        return "advisor tool call", explicit_focus
    if not trigger:
        return None, None
    review_context = tool_review_context_from_message(message, trigger)
    if review_context:
        return trigger, review_context
    return trigger, trigger


def assistant_tool_call_summary_for_prompt(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    sections: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "tool").strip() or "tool"
        if name == "advisor":
            continue
        sections.append(f"Pending Claude Code tool call: {name}\nTool input:\n{tool_input_for_prompt(block.get('input'))}")
    return "\n\n".join(sections)


def body_has_advisor_feedback(body: dict[str, Any]) -> bool:
    for message in reversed(body.get("messages") or []):
        if not isinstance(message, dict):
            continue
        text = anthropic_content_to_text(message.get("content"))
        if ADVISOR_FEEDBACK_MARKER in text:
            return True
    return False


def anthropic_message_tool_names(message: dict[str, Any]) -> list[str]:
    names: list[str] = []
    content = message.get("content")
    if not isinstance(content, list):
        return names
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def advisor_trigger_for_message(body: dict[str, Any], message: dict[str, Any]) -> str | None:
    names = set(anthropic_message_tool_names(message))
    if "ExitPlanMode" in names:
        return "before ExitPlanMode plan approval"
    if names:
        return None
    text = anthropic_content_to_text(message.get("content")).strip()
    if (
        text
        and message.get("stop_reason") == "end_turn"
        and latest_tool_result_indicates_completed_work(body)
        and not non_actionable_short_response(text)
    ):
        return "before completion/final response"
    return None


def advisor_gate_possible_for_body(provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> bool:
    return bool(advisor_gate_reason_for_body(provider, pcfg, body))


def advisor_gate_reason_for_body(provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> str:
    if not advisor_model_enabled(pcfg) or not advisor_provider_supported(provider):
        return ""
    if is_advisor_request(body) or body_has_advisor_feedback(body):
        return ""
    if plan_mode_active(body):
        return "plan_mode"
    if latest_tool_result_indicates_completed_work(body):
        return "completed_work"
    return ""


def anthropic_system_to_ollama_messages(system: Any) -> list[dict[str, Any]]:
    if not system:
        return []
    if isinstance(system, str):
        text = system
    else:
        text = anthropic_content_to_text(system)
    return [{"role": "system", "content": text}] if text else []


def ollama_claude_code_reminder() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "Claude Code execution reminder: when the user asks to create, edit, or run code, "
            "use the available tools such as Write, Edit, Read, and Bash. Do not stop after saying "
            "you will run something. Do not present a code block as a substitute for creating the file "
            "unless the user explicitly asks for code only. Exception: while Claude Code is in Plan Mode, "
            "do not implement normal project files; explore as needed, write or update the plan file, "
            "then call ExitPlanMode when the plan is ready for approval."
        ),
    }


READ_UNCHANGED_RESULT_RE = re.compile(
    r"(wasted call|unchanged since (?:your )?last read|file unchanged since (?:your )?last read)",
    re.IGNORECASE,
)

def message_attachment(message: dict[str, Any]) -> dict[str, Any] | None:
    attachment = message.get("attachment")
    return attachment if isinstance(attachment, dict) else None


def is_attachment_only_message(message: dict[str, Any]) -> bool:
    if not message_attachment(message):
        return False
    content = message.get("content")
    if content is None:
        return True
    blocks = _message_content_blocks(message)
    if any(isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"} for block in blocks):
        return False
    return not anthropic_content_to_text(content).strip()


def latest_plan_attachment(body: dict[str, Any]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        attachment = message_attachment(message)
        if not attachment:
            continue
        if attachment.get("type") in {"plan_mode", "plan_mode_reentry", "plan_mode_exit"}:
            latest = attachment
    return latest


def plan_file_written_in_body(body: dict[str, Any], plan_file_path: str) -> bool:
    if not plan_file_path:
        return False
    tool_names_by_id: dict[str, str] = {}
    tool_inputs_by_id: dict[str, Any] = {}
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = _message_content_blocks(message)
        if message.get("role") == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                if not tool_id:
                    continue
                tool_names_by_id[tool_id] = str(block.get("name") or "")
                tool_inputs_by_id[tool_id] = block.get("input") if isinstance(block.get("input"), dict) else {}
        elif message.get("role") == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                if tool_names_by_id.get(tool_use_id) not in {"Write", "Edit", "MultiEdit"}:
                    continue
                tool_input = tool_inputs_by_id.get(tool_use_id)
                if not isinstance(tool_input, dict):
                    continue
                if str(tool_input.get("file_path") or "") == plan_file_path and not block.get("is_error"):
                    return True
    return False


def claude_code_state_messages(body: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    plan_attachment = latest_plan_attachment(body)
    if plan_mode_active(body):
        plan_file_path = ""
        plan_exists = None
        if plan_attachment:
            plan_file_path = str(plan_attachment.get("planFilePath") or "")
            plan_exists = plan_attachment.get("planExists")
        plan_written = plan_file_written_in_body(body, plan_file_path)
        parts = [
            "Claude Code state: Plan Mode is active.",
            "In Plan Mode, exploration tools are allowed, but implementation/editing of normal project files must wait until ExitPlanMode approval.",
        ]
        if plan_file_path:
            parts.append(f"Plan file path: {plan_file_path}.")
            parts.append(f"Plan file written or updated in this conversation: {'yes' if plan_written else 'no'}.")
        if plan_exists is not None:
            parts.append(f"Claude Code attachment planExists: {bool(plan_exists)}.")
        parts.append(
            "When the plan file is complete and no new information is needed, call ExitPlanMode with the plan instead of repeating unchanged Read calls."
        )
        messages.append({"role": "system", "content": "\n".join(parts)})
    return messages


def canonical_tool_signature(tool_name: str, tool_input: Any) -> str:
    normalized = tool_input if isinstance(tool_input, dict) else {}
    return f"{tool_name}:{json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def is_read_unchanged_result(tool_name: str, result_text: str) -> bool:
    return tool_name == "Read" and bool(READ_UNCHANGED_RESULT_RE.search(result_text or ""))


def upstream_relevant_message(message: dict[str, Any]) -> bool:
    if is_attachment_only_message(message) or should_skip_upstream_message(message):
        return False
    role = message.get("role")
    if role not in {"assistant", "user", "system", "tool"}:
        return False
    blocks = _message_content_blocks(message)
    if any(isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"} for block in blocks):
        return True
    return bool(anthropic_content_to_text(message.get("content", "")).strip())


def collect_tool_result_context(body: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    tool_names_by_id: dict[str, str] = {}
    tool_inputs_by_id: dict[str, Any] = {}
    successful_results: dict[str, str] = {}
    tool_result_records: list[tuple[int, str, str, Any, str, bool]] = []
    latest_relevant_message_index = -1
    for message_index, message in enumerate(body.get("messages") or []):
        if not isinstance(message, dict):
            continue
        if upstream_relevant_message(message):
            latest_relevant_message_index = message_index
        content = _message_content_blocks(message)
        if message.get("role") == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                if not tool_id:
                    continue
                tool_names_by_id[tool_id] = str(block.get("name") or "")
                tool_inputs_by_id[tool_id] = block.get("input") if isinstance(block.get("input"), dict) else {}
        elif message.get("role") == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                tool_name = tool_names_by_id.get(tool_use_id, "tool")
                tool_input = tool_inputs_by_id.get(tool_use_id) or {}
                result_text = anthropic_content_to_text(block.get("content", ""))
                signature = canonical_tool_signature(tool_name, tool_input)
                is_error = bool(block.get("is_error"))
                tool_result_records.append((message_index, tool_use_id, tool_name, tool_input, result_text, is_error))
                if not is_read_unchanged_result(tool_name, result_text) and not is_error and result_text.strip():
                    successful_results[signature] = result_text
    current_read_noop_ids = {
        tool_use_id
        for message_index, tool_use_id, tool_name, _tool_input, result_text, _is_error in tool_result_records
        if message_index == latest_relevant_message_index and is_read_unchanged_result(tool_name, result_text)
    }
    return successful_results, current_read_noop_ids


def format_tool_result_for_upstream(
    tool_name: str,
    tool_input_text: str,
    result_text: str,
    is_error: bool,
    prior_success_text: str = "",
    include_prior_success: bool = False,
    in_plan_mode: bool = False,
) -> tuple[str, str]:
    if is_error:
        tool_text = (
            f"Tool `{tool_name}` failed.\n"
            f"Input:\n{tool_input_text}\n\n"
            f"Error:\n{result_text}"
        )
        tool_summary = (
            f"The `{tool_name}` tool call above failed. Its input was {tool_input_text}. "
            f"Use the error output to choose a different next step; do not blindly repeat it."
        )
        return tool_text, tool_summary

    if is_read_unchanged_result(tool_name, result_text):
        if not include_prior_success:
            tool_text = (
                "Tool `Read` returned an unchanged/no-op cache result for content that was already "
                "available earlier in this conversation. No new file content was produced by this "
                "historical duplicate observation."
            )
            return tool_text, ""
        previous = ""
        if prior_success_text:
            previous = (
                "\n\nPrevious successful Read result for this exact input remains authoritative:\n"
                f"{truncate_for_prompt(prior_success_text, PROMPT_TOOL_RESULT_LIMIT)}"
            )
        plan_hint = (
            " If you are in Plan Mode and the plan file is already complete, call ExitPlanMode."
            if in_plan_mode
            else ""
        )
        if not prior_success_text:
            tool_text = (
                "Tool `Read` returned a no-op unchanged result.\n"
                f"Input:\n{tool_input_text}\n\n"
                f"Result:\n{result_text}\n\n"
                "No previous successful Read result for this exact input is available in the converted context. "
                "Do not repeat the same Read. If the content is still needed, read a different or broader range once; "
                "otherwise proceed with the next distinct step."
            )
            tool_summary = (
                "The latest `Read` result says the file/range is unchanged, but no prior exact Read content is available "
                "in this converted context. Do not loop on the same Read; either read a different range once or continue "
                f"with the next distinct step.{plan_hint}"
            )
            return tool_text, tool_summary
        tool_text = (
            "Tool `Read` returned a no-op unchanged result.\n"
            f"Input:\n{tool_input_text}\n\n"
            f"Result:\n{result_text}"
            f"{previous}\n\n"
            "This is not new file content. It means the previous successful Read result for the same input is still current."
        )
        tool_summary = (
            "The latest `Read` result is a Claude Code no-op/cache result: no file content changed and no new observation was produced. "
            "Use the previous successful Read result for this exact input as the current observation, then choose the next distinct step."
            f"{plan_hint}"
        )
        return tool_text, tool_summary

    tool_text = (
        f"Tool `{tool_name}` completed successfully.\n"
        f"Input:\n{tool_input_text}\n\n"
        f"Result:\n{result_text}\n\n"
        f"If this result satisfies the user's request, provide the final answer now. "
        f"Do not call `{tool_name}` again with the same arguments."
    )
    tool_summary = (
        f"The `{tool_name}` tool call above already completed successfully. "
        f"Treat its tool output as authoritative. Do not repeat the same or equivalent "
        f"`{tool_name}` call; continue with the next required concrete tool call or final answer."
    )
    return tool_text, tool_summary


def should_skip_upstream_message(message: dict[str, Any]) -> bool:
    if is_claude_code_transcript_event(message):
        return True
    role = message.get("role")
    content = message.get("content", "")
    if role == "user" and message.get("isMeta") is True:
        return True
    text = anthropic_content_to_text(content).strip()
    if is_guard_feedback_text(text):
        return True
    # Router diagnostics must never be fed back to the upstream model. In Claude
    # Code they can also appear in the prompt input after a malformed/empty turn.
    router_diagnostics = (
        "Upstream returned an empty stream.",
        "Upstream returned no stream data.",
    )
    if role in ("assistant", "user") and (
        text in router_diagnostics or text.startswith("Upstream stream error:")
    ):
        return True
    if role == "assistant" and text == "No response requested.":
        return True
    return False


def anthropic_messages_to_ollama(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = anthropic_system_to_ollama_messages(body.get("system"))
    messages.append(ollama_claude_code_reminder())
    messages.extend(claude_code_state_messages(body))
    prior_tool_results, latest_noop_result_ids = collect_tool_result_context(body)
    in_plan_mode = plan_mode_active(body)
    tool_names_by_id: dict[str, str] = {}
    tool_inputs_by_id: dict[str, Any] = {}
    for message in body.get("messages", []) or []:
        if not isinstance(message, dict):
            continue
        if is_attachment_only_message(message):
            continue
        if should_skip_upstream_message(message):
            continue
        role = message.get("role", "user")
        content = message.get("content", "")

        if role == "user" and isinstance(content, list):
            text_blocks: list[Any] = []
            tool_blocks: list[dict[str, Any]] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_blocks.append(block)
                else:
                    text_blocks.append(block)
            text = anthropic_content_to_text(text_blocks)
            if text:
                messages.append({"role": "user", "content": compact_message_text_for_prompt(text)})
            for block in tool_blocks:
                tool_use_id = str(block.get("tool_use_id") or "")
                tool_name = tool_names_by_id.get(tool_use_id, "tool")
                tool_input = tool_inputs_by_id.get(tool_use_id)
                tool_input_text = tool_input_for_prompt(tool_input)
                result_text = truncate_for_prompt(anthropic_content_to_text(block.get("content", "")), PROMPT_TOOL_RESULT_LIMIT)
                signature = canonical_tool_signature(tool_name, tool_input)
                tool_text, tool_summary = format_tool_result_for_upstream(
                    tool_name=tool_name,
                    tool_input_text=tool_input_text,
                    result_text=result_text,
                    is_error=bool(block.get("is_error")),
                    prior_success_text=prior_tool_results.get(signature, ""),
                    include_prior_success=tool_use_id in latest_noop_result_ids,
                    in_plan_mode=in_plan_mode,
                )
                if not block.get("is_error"):
                    if tool_name == "TaskList":
                        tool_summary = (
                            f"The task list is current:\n{result_text}\n\n"
                            "If any task is in_progress and the user's request is not finished, your next response "
                            "must call a concrete work tool such as Write, Edit, Read, or Bash. Do not respond with "
                            "another progress announcement like 'I will write the files now'. If everything is "
                            "actually complete, provide the final answer."
                        )
                messages.append({"role": "tool", "tool_name": tool_name, "content": tool_text})
                if tool_summary:
                    messages.append({"role": "user", "content": tool_summary})
            continue

        text = anthropic_content_to_text(content)
        out: dict[str, Any] = {"role": role, "content": compact_message_text_for_prompt(text)}
        if role == "assistant" and isinstance(content, list):
            calls = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = str(block.get("name") or "tool")
                    tool_id = str(block.get("id") or "")
                    if tool_id:
                        tool_names_by_id[tool_id] = name
                        tool_inputs_by_id[tool_id] = block.get("input") or {}
                    calls.append({"function": {"name": name, "arguments": block.get("input") or {}}})
            if calls:
                out["tool_calls"] = calls
        messages.append(out)
    return messages


def anthropic_tools_to_ollama(tools: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return out
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def anthropic_messages_to_openai(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = anthropic_system_to_ollama_messages(body.get("system"))
    messages.append(ollama_claude_code_reminder())
    messages.extend(claude_code_state_messages(body))
    prior_tool_results, latest_noop_result_ids = collect_tool_result_context(body)
    in_plan_mode = plan_mode_active(body)
    tool_names_by_id: dict[str, str] = {}
    tool_inputs_by_id: dict[str, Any] = {}
    for message in body.get("messages", []) or []:
        if not isinstance(message, dict):
            continue
        if is_attachment_only_message(message):
            continue
        if should_skip_upstream_message(message):
            continue
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "assistant" and isinstance(content, list):
            text_blocks: list[Any] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_id = str(block.get("id") or f"call_{len(tool_calls) + 1}")
                    name = str(block.get("name") or "tool")
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    if tool_id:
                        tool_names_by_id[tool_id] = name
                        tool_inputs_by_id[tool_id] = tool_input
                    tool_calls.append({
                        "id": tool_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(tool_input, ensure_ascii=False),
                        },
                    })
                else:
                    text_blocks.append(block)
            out: dict[str, Any] = {"role": "assistant", "content": compact_message_text_for_prompt(anthropic_content_to_text(text_blocks))}
            if tool_calls:
                out["tool_calls"] = tool_calls
            messages.append(out)
            continue
        if role == "user" and isinstance(content, list):
            text_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_id = str(block.get("tool_use_id") or "call_tool")
                    if tool_id not in tool_names_by_id:
                        result_text = truncate_for_prompt(anthropic_content_to_text(block.get("content", "")), PROMPT_TOOL_RESULT_LIMIT)
                        text_blocks.append({
                            "type": "text",
                            "text": (
                                f"Historical tool result without a retained assistant tool call ({tool_id}):\n"
                                f"{result_text}"
                            ),
                        })
                        continue
                    tool_name = tool_names_by_id.get(tool_id, "tool")
                    tool_input = tool_inputs_by_id.get(tool_id)
                    tool_input_text = tool_input_for_prompt(tool_input)
                    result_text = truncate_for_prompt(anthropic_content_to_text(block.get("content", "")), PROMPT_TOOL_RESULT_LIMIT)
                    signature = canonical_tool_signature(tool_name, tool_input)
                    tool_text, _ = format_tool_result_for_upstream(
                        tool_name=tool_name,
                        tool_input_text=tool_input_text,
                        result_text=result_text,
                        is_error=bool(block.get("is_error")),
                        prior_success_text=prior_tool_results.get(signature, ""),
                        include_prior_success=tool_id in latest_noop_result_ids,
                        in_plan_mode=in_plan_mode,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "id": tool_id,
                        "content": tool_text,
                    })
                else:
                    text_blocks.append(block)
            text = anthropic_content_to_text(text_blocks)
            if text:
                messages.append({"role": "user", "content": compact_message_text_for_prompt(text)})
            continue
        messages.append({"role": role, "content": compact_message_text_for_prompt(anthropic_content_to_text(content))})
    return messages


def anthropic_tool_choice_to_openai(tool_choice: Any) -> Any:
    if not isinstance(tool_choice, dict):
        return tool_choice
    choice_type = tool_choice.get("type")
    if choice_type == "tool" and tool_choice.get("name"):
        return {"type": "function", "function": {"name": str(tool_choice["name"])}}
    if choice_type == "any":
        return "required"
    if choice_type == "auto":
        return "auto"
    return tool_choice


def positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except Exception:
        return None
    return out if out > 0 else None


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def parse_config_value(value: str) -> Any:
    text = value.strip()
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("none", "null"):
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return int(text)
    except Exception:
        pass
    try:
        return float(text)
    except Exception:
        return text


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "yes", "on", "1", "enable", "enabled"):
        return True
    if text in ("false", "no", "off", "0", "disable", "disabled"):
        return False
    return default


def router_debug_external_access_enabled(cfg: dict[str, Any] | None = None) -> bool:
    env = env_bool(os.environ.get("CLAUDE_ANY_ROUTER_DEBUG_EXTERNAL"), None)
    if env is not None:
        return bool(env)
    if cfg is None:
        cfg = load_config()
    return (
        parse_bool(cfg.get("router_debug_external_access"), False)
        and parse_bool(cfg.get("router_debug_external_access_confirmed"), False)
    )


def router_bind_host(cfg: dict[str, Any] | None = None) -> str:
    env_host = (os.environ.get("CLAUDE_ANY_ROUTER_BIND_HOST") or os.environ.get("CLAUDE_ANY_ROUTER_HOST") or "").strip()
    if env_host:
        return env_host
    return "0.0.0.0" if router_debug_external_access_enabled(cfg) else "127.0.0.1"


def is_loopback_address(host: str | None) -> bool:
    host = (host or "").strip().lower()
    return host in ("127.0.0.1", "::1", "localhost") or host.startswith("127.")


def router_request_allowed(handler: BaseHTTPRequestHandler, cfg: dict[str, Any] | None = None) -> bool:
    if router_debug_external_access_enabled(cfg):
        return True
    try:
        return is_loopback_address(str(handler.client_address[0]))
    except Exception:
        return False


def set_router_debug_external_access_config(value: Any) -> list[str]:
    cfg = load_config()
    enabled = parse_bool(value, False)
    cfg["router_debug_external_access"] = enabled
    cfg["router_debug_external_access_confirmed"] = enabled
    save_config(cfg)
    clear_model_cache()
    bind = router_bind_host(cfg)
    if enabled:
        return [
            "Router debug external access: on.",
            f"Router bind host for next launch: {bind}.",
            "External clients are allowed while the router is bound to an external interface.",
        ]
    return [
        "Router debug external access: off.",
        "External clients are denied immediately; next launch binds to 127.0.0.1 unless overridden by environment.",
    ]


def schedule_router_process_restart(delay: float = 0.8) -> None:
    def restart() -> None:
        try:
            router_log("INFO", "router_debug_restart execing router process")
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), "serve"])
        except Exception as exc:
            try:
                router_log("ERROR", f"router_debug_restart_failed {type(exc).__name__}: {exc}")
            except Exception:
                pass

    timer = threading.Timer(delay, restart)
    timer.daemon = True
    timer.start()


def ctx_bucket(target: int, minimum: int, maximum: int) -> int:
    target = max(minimum, min(maximum, target))
    buckets = [4096, 8192, 16384, 32768, 65536, 131072, 262144]
    for bucket in buckets:
        if bucket >= target:
            return min(bucket, maximum)
    return maximum


def ollama_num_ctx_for_payload(pcfg: dict[str, Any], payload: Any, _token_cache: dict[int, int] | None = None) -> int | None:
    override = os.environ.get("CLAUDE_ANY_OLLAMA_NUM_CTX")
    if override:
        return positive_int(override)
    raw = pcfg.get("num_ctx", "auto")
    if isinstance(raw, str) and raw.strip().lower() in ("", "auto", "dynamic"):
        minimum = positive_int(pcfg.get("num_ctx_min")) or 8192
        maximum = positive_int(pcfg.get("num_ctx_max")) or 65536
        if maximum < minimum:
            maximum = minimum
        estimated = estimate_tokens(payload, _token_cache)
        # Leave headroom for tool results, follow-up commands, and model-side formatting.
        target = int(estimated * 1.45) + 2048
        return ctx_bucket(target, minimum, maximum)
    return positive_int(raw)


def ollama_num_ctx_status(pcfg: dict[str, Any]) -> str:
    raw = pcfg.get("num_ctx", "auto")
    if isinstance(raw, str) and raw.strip().lower() in ("", "auto", "dynamic"):
        minimum = positive_int(pcfg.get("num_ctx_min")) or 8192
        maximum = positive_int(pcfg.get("num_ctx_max")) or 65536
        return f"auto ({minimum}-{maximum})"
    return str(positive_int(raw) or raw)


def ollama_extra_options(pcfg: dict[str, Any]) -> dict[str, Any]:
    raw = pcfg.get("ollama_options") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if v is not None}


def ollama_options_status(pcfg: dict[str, Any]) -> str:
    opts = ollama_extra_options(pcfg)
    if not opts:
        return "{}"
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in sorted(opts.items()))


def ollama_request_timeout_seconds(pcfg: dict[str, Any]) -> float:
    raw = pcfg.get("request_timeout_ms", pcfg.get("request_timeout", pcfg.get("timeout_ms", DEFAULT_REQUEST_TIMEOUT_MS)))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 120.0
    if value <= 0:
        return 120.0
    # Values above 10k are treated as milliseconds, matching common UI/API timeout notation.
    if value > 10000:
        return max(1.0, value / 1000.0)
    return value


def configured_output_tokens(pcfg: dict[str, Any], body: dict[str, Any], option_key: str | None = None) -> int | None:
    configured = positive_int(pcfg.get("max_output_tokens"))
    if option_key:
        opts = ollama_extra_options(pcfg)
        configured = positive_int(opts.get(option_key)) or configured
    requested = positive_int(body.get("max_tokens"))
    if configured and requested:
        return min(configured, requested)
    return configured or requested


def cap_output_tokens_for_context(
    pcfg: dict[str, Any],
    body: dict[str, Any],
    payload: Any,
    context_limit: int | None,
    configured: int | None,
    _token_cache: dict[int, int] | None = None,
) -> int | None:
    if not configured:
        return None
    if not context_limit:
        return configured
    reserve = positive_int(pcfg.get("context_reserve_tokens")) or 1024
    estimated_input = estimate_tokens(payload, _token_cache)
    available = context_limit - estimated_input - reserve
    if available <= 0:
        return min(configured, 256)
    return max(1, min(configured, available))


def ollama_context_limit_for_budget(pcfg: dict[str, Any]) -> int:
    raw = pcfg.get("num_ctx", "auto")
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        return positive_int(pcfg.get("num_ctx_max")) or 65536
    return positive_int(raw) or positive_int(pcfg.get("num_ctx_max")) or 65536


def openai_context_limit_for_budget(provider: str, pcfg: dict[str, Any]) -> int:
    configured = positive_int(pcfg.get("context_window")) or positive_int(pcfg.get("max_model_len"))
    if configured:
        return configured
    if provider == "nvidia-hosted":
        return nvidia_hosted_context_default(str(pcfg.get("current_model") or ""))
    return 65536


def compact_ollama_messages_for_budget(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    budget_tokens: int,
) -> list[dict[str, Any]]:
    if not messages:
        return messages
    budget_tokens = max(8192, budget_tokens)
    payload = {"messages": messages, "tools": tools}
    initial_tokens = estimate_tokens(payload)
    if initial_tokens <= budget_tokens:
        return messages

    system_messages = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    first_user: dict[str, Any] | None = next((m for m in non_system if m.get("role") == "user"), None)

    preserved_tail: list[dict[str, Any]] = []
    omitted = 0
    omitted_tokens = 0
    summary: dict[str, Any] = {
        "role": "user",
        "content": (
            "[claude-any context guard: older conversation messages were omitted because the provider context "
            "budget would be exceeded. Large file contents and prior Write/Edit inputs were truncated. "
            "Use Read on specific files if exact old content is needed.]"
        ),
    }

    fixed_prefix = list(system_messages)
    if first_user is not None:
        fixed_prefix.append(first_user)
    fixed_prefix.append(summary)

    for msg in reversed(non_system):
        if first_user is not None and msg is first_user:
            continue
        candidate = fixed_prefix + list(reversed(preserved_tail + [msg]))
        if estimate_tokens({"messages": candidate, "tools": tools}) <= budget_tokens:
            preserved_tail.append(msg)
        else:
            omitted += 1
            omitted_tokens += estimate_tokens(msg)

    if first_user is None:
        fixed_prefix = list(system_messages)
        fixed_prefix.append(summary)

    summary["content"] = (
        f"[claude-any context guard: omitted {omitted} older messages, approx {omitted_tokens} tokens, "
        f"because the provider context budget is {budget_tokens} tokens. Large file contents and prior "
        "Write/Edit inputs were truncated. Continue from the current task list and recent tool results; "
        "use Read on specific files if exact old content is needed.]"
    )
    compacted = fixed_prefix + list(reversed(preserved_tail))
    router_log(
        "WARN",
        f"compacted ollama payload messages {len(messages)}->{len(compacted)} tokens {initial_tokens}->{estimate_tokens({'messages': compacted, 'tools': tools})} budget={budget_tokens}",
    )
    return compacted


def provider_request_timeout_seconds(pcfg: dict[str, Any]) -> float:
    return ollama_request_timeout_seconds(pcfg)


def provider_stream_idle_timeout_seconds(pcfg: dict[str, Any]) -> float:
    raw = positive_int(pcfg.get("stream_idle_timeout_ms"))
    if raw:
        return max(5.0, raw / 1000.0)
    return max(30.0, min(provider_request_timeout_seconds(pcfg), 300.0))


def set_upstream_stream_read_timeout(resp: Any, timeout: float) -> None:
    """Keep one stalled upstream read from holding Claude Code's prompt queue forever."""
    try:
        if hasattr(resp, "fp") and getattr(resp, "fp") is not None:
            raw = getattr(resp.fp, "raw", None)
            sock = getattr(raw, "_sock", None)
            if sock is not None and hasattr(sock, "settimeout"):
                sock.settimeout(timeout)
                return
        sock = getattr(resp, "sock", None)
        if sock is not None and hasattr(sock, "settimeout"):
            sock.settimeout(timeout)
    except Exception:
        pass


def cap_anthropic_body_for_provider(provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    capped = dict(body)
    if provider not in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        return capped
    if provider == "vllm":
        context_limit = positive_int(pcfg.get("context_window")) or positive_int(pcfg.get("max_model_len")) or 32768
    else:
        context_limit = positive_int(pcfg.get("context_window")) or positive_int(pcfg.get("max_model_len"))
    configured = configured_output_tokens(pcfg, capped)
    output_tokens = cap_output_tokens_for_context(pcfg, capped, {k: v for k, v in capped.items() if k != "max_tokens"}, context_limit, configured)
    if output_tokens:
        capped["max_tokens"] = output_tokens
    return capped


def apply_provider_request_options(provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    if provider not in PROVIDER_SAMPLING_OPTION_PROVIDERS:
        return body
    out = dict(body)
    for key in PROVIDER_SAMPLING_OPTIONS:
        value = pcfg.get(key)
        if value is not None:
            out[key] = value
    return out


def ollama_chat_request(model: str, body: dict[str, Any], pcfg: dict[str, Any], stream: bool = True) -> dict[str, Any]:
    messages = anthropic_messages_to_ollama(body)
    tools = anthropic_tools_to_ollama(body.get("tools"))
    context_limit = ollama_context_limit_for_budget(pcfg)
    configured = configured_output_tokens(pcfg, body, "num_predict")
    reserve = positive_int(pcfg.get("context_reserve_tokens")) or 1024
    output_reserve = configured or positive_int(body.get("max_tokens")) or 4096
    input_budget = max(8192, context_limit - output_reserve - reserve)
    messages = compact_ollama_messages_for_budget(messages, tools, input_budget)
    req: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "think": bool(pcfg.get("think", False)),
    }
    if pcfg.get("keep_alive"):
        req["keep_alive"] = str(pcfg["keep_alive"])
    if tools:
        req["tools"] = tools
    options: dict[str, Any] = ollama_extra_options(pcfg)
    payload_for_est = {"messages": messages, "tools": tools}
    token_cache: dict[int, int] = {}
    num_ctx = ollama_num_ctx_for_payload(pcfg, payload_for_est, _token_cache=token_cache)
    num_predict = cap_output_tokens_for_context(
        pcfg,
        body,
        payload_for_est,
        num_ctx,
        configured,
        _token_cache=token_cache,
    )
    if num_predict:
        options["num_predict"] = num_predict
    if num_ctx:
        options.setdefault("num_ctx", num_ctx)
    if options:
        req["options"] = options
    return req


def openai_compatible_chat_request(provider: str, model: str, body: dict[str, Any], pcfg: dict[str, Any], stream: bool = False) -> dict[str, Any]:
    messages = anthropic_messages_to_openai(body)
    tools = anthropic_tools_to_ollama(body.get("tools"))
    context_limit = openai_context_limit_for_budget(provider, pcfg)
    configured = configured_output_tokens(pcfg, body)
    reserve = positive_int(pcfg.get("context_reserve_tokens")) or 1024
    output_reserve = configured or positive_int(body.get("max_tokens")) or 4096
    messages = compact_ollama_messages_for_budget(messages, tools, max(8192, context_limit - output_reserve - reserve))
    req: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        req["tools"] = tools
    if body.get("tool_choice") is not None:
        req["tool_choice"] = anthropic_tool_choice_to_openai(body.get("tool_choice"))
    max_tokens = configured_output_tokens(pcfg, body)
    if max_tokens:
        req["max_tokens"] = max_tokens
    for key in ("temperature", "top_p"):
        if pcfg.get(key) is not None:
            req[key] = pcfg[key]
    return req


ADVISOR_REVIEW_PROMPT = (
    "You are claude-any Advisor, a stronger reviewer model. Review the current task state and provide "
    "concise, actionable guidance for the executor model. Review now; do not say that you will review later. "
    "Do not write code unless a small exact patch is the clearest advice. Use this exact structure: "
    "Verdict: approve, revise, or continue. Key findings: concrete gaps or risks. Required next action: "
    "the next action or Claude Code tool call. Validation: the check that proves the work. "
    "If the executor is stuck after progress announcements, tell it the exact next Claude Code tool to call."
)


def advisor_messages_for_provider(provider: str, body: dict[str, Any], focus_override: str = "") -> list[dict[str, Any]]:
    kind = advisor_provider_kind(provider)
    if kind == "openai-compatible":
        messages = anthropic_messages_to_openai(body)
    else:
        messages = anthropic_messages_to_ollama(body)
    focus = focus_override or advisor_focus_from_body(body)
    messages.insert(0, {"role": "system", "content": ADVISOR_REVIEW_PROMPT})
    if focus:
        messages.append({"role": "user", "content": f"Advisor focus:\n{compact_message_text_for_prompt(focus)}"})
    return messages


def advisor_input_budget(provider: str, pcfg: dict[str, Any]) -> int:
    context_limit = (
        ollama_context_limit_for_budget(pcfg)
        if advisor_provider_kind(provider) == "ollama"
        else openai_context_limit_for_budget(provider, pcfg)
    )
    return max(8192, context_limit - 4096 - (positive_int(pcfg.get("context_reserve_tokens")) or 1024))


def advisor_upstream_model(provider: str, model: str) -> str:
    return ncp_model_id_for_nvidia_hosted(model) if provider == "nvidia-hosted" else model


def advisor_request(provider: str, model: str, body: dict[str, Any], pcfg: dict[str, Any], focus_override: str = "") -> dict[str, Any]:
    messages = advisor_messages_for_provider(provider, body, focus_override=focus_override)
    messages = compact_ollama_messages_for_budget(messages, [], advisor_input_budget(provider, pcfg))
    upstream_model = advisor_upstream_model(provider, model)
    if advisor_provider_kind(provider) == "openai-compatible":
        req: dict[str, Any] = {
            "model": upstream_model,
            "messages": messages,
            "stream": False,
            "max_tokens": min(4096, configured_output_tokens(pcfg, body) or 4096),
        }
        for key in ("temperature", "top_p"):
            if pcfg.get(key) is not None:
                req[key] = pcfg[key]
        return req
    req: dict[str, Any] = {
        "model": upstream_model,
        "messages": messages,
        "stream": False,
        "think": bool(pcfg.get("think", False)),
    }
    options = ollama_extra_options(pcfg)
    options.setdefault("num_predict", min(4096, positive_int(options.get("num_predict")) or 4096))
    num_ctx = ollama_num_ctx_for_payload(pcfg, {"messages": messages, "tools": []})
    if num_ctx:
        options.setdefault("num_ctx", num_ctx)
    if options:
        req["options"] = options
    return req


def advisor_response_text(provider: str, data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    if advisor_provider_kind(provider) == "openai-compatible":
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(message, dict):
                return str(message.get("content") or "").strip()
        return ""
    message = data.get("message") if isinstance(data, dict) else {}
    return str((message or {}).get("content") or "").strip()


def advisor_endpoint(provider: str, pcfg: dict[str, Any]) -> str:
    base = pcfg.get("base_url", "").rstrip("/")
    if advisor_provider_kind(provider) == "openai-compatible":
        return join_url(provider_upstream_request_base(provider, pcfg), "/chat/completions")
    return join_url(base, "/api/chat")


def call_advisor_text(provider: str, pcfg: dict[str, Any], body: dict[str, Any], focus: str = "") -> str:
    advisor_model = advisor_model_enabled(pcfg)
    if not advisor_model or not advisor_provider_supported(provider):
        return ""
    upstream_model = advisor_upstream_model(provider, advisor_model)
    req_body = advisor_request(provider, advisor_model, body, pcfg, focus_override=focus)
    try:
        apply_router_rate_limit(provider, pcfg, upstream_model)
        write_router_activity("advisor", provider, upstream_model, tokens=estimate_tokens(req_body))
        if advisor_provider_kind(provider) == "openai-compatible":
            data = post_json_with_rate_retry(
                advisor_endpoint(provider, pcfg),
                req_body,
                provider_headers(provider, pcfg),
                provider_request_timeout_seconds(pcfg),
                provider,
                pcfg,
                upstream_model,
                None,
            )
        else:
            data = post_json_with_rate_retry(
                advisor_endpoint(provider, pcfg),
                req_body,
                provider_headers(provider, pcfg),
                ollama_request_timeout_seconds(pcfg),
                provider,
                pcfg,
                upstream_model,
                None,
            )
        text = advisor_response_text(provider, data)
        if text:
            router_log("INFO", f"advisor_feedback provider={provider} advisor_model={upstream_model} chars={len(text)}")
        return text
    except Exception as exc:
        router_log("WARN", f"advisor_request_failed provider={provider} advisor_model={upstream_model} error={type(exc).__name__}: {exc}")
        write_router_activity("advisor_error", provider, upstream_model, error=type(exc).__name__)
        return ""


def body_with_internal_advisor_feedback(body: dict[str, Any], assistant_message: dict[str, Any], advisor_text: str, trigger: str) -> dict[str, Any]:
    messages = [m for m in body.get("messages", []) if isinstance(m, dict)]
    assistant_text = anthropic_content_to_text(assistant_message.get("content")).strip()
    tool_names = anthropic_message_tool_names(assistant_message)
    tool_summary = assistant_tool_call_summary_for_prompt(assistant_message)
    if assistant_text:
        messages.append({"role": "assistant", "content": [{"type": "text", "text": compact_message_text_for_prompt(assistant_text)}]})
    elif tool_summary:
        messages.append({"role": "assistant", "content": [{"type": "text", "text": compact_message_text_for_prompt(tool_summary)}]})
    elif tool_names:
        messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": f"I was about to call Claude Code tool(s): {', '.join(tool_names)}."}],
        })
    feedback = (
        f"{ADVISOR_FEEDBACK_MARKER}\n"
        f"Advisor review trigger: {trigger}.\n\n"
        f"{advisor_text}\n\n"
        "Apply this advisor feedback now. If the plan is still ready, call ExitPlanMode with the improved plan. "
        "If the task is complete, provide the final answer. If the advisor found a gap, continue with concrete "
        "Claude Code tool calls instead of stopping after an announcement."
    )
    messages.append({"role": "user", "content": [{"type": "text", "text": feedback}]})
    follow_body = dict(body)
    follow_body["messages"] = messages
    follow_body.pop("tool_choice", None)
    return follow_body


def advisor_visible_summary(advisor_text: str, trigger: str, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", str(advisor_text or "")).strip()
    if not text:
        return ""
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return f"Advisor review ({trigger}): {text}\n\n"


def call_provider_chat_once(provider: str, pcfg: dict[str, Any], body: dict[str, Any], model: str) -> dict[str, Any]:
    if provider in ("ollama", "ollama-cloud"):
        base = pcfg.get("base_url", "").rstrip("/")
        req_body = ollama_chat_request(model, body, pcfg, stream=False)
        apply_router_rate_limit(provider, pcfg, model)
        data = post_json_with_rate_retry(
            join_url(base, "/api/chat"),
            req_body,
            provider_headers(provider, pcfg),
            ollama_request_timeout_seconds(pcfg),
            provider,
            pcfg,
            model,
            None,
        )
        return ollama_chat_to_anthropic(data, model, source_body=body)
    if provider == "nvidia-hosted":
        upstream_model = ncp_model_id_for_nvidia_hosted(model)
        req_body = openai_compatible_chat_request(provider, upstream_model, body, pcfg, stream=False)
        apply_router_rate_limit(provider, pcfg, upstream_model)
        data = post_json_with_rate_retry(
            join_url(provider_upstream_request_base(provider, pcfg), "/chat/completions"),
            req_body,
            provider_headers(provider, pcfg),
            provider_request_timeout_seconds(pcfg),
            provider,
            pcfg,
            upstream_model,
            None,
        )
        return openai_chat_to_anthropic(data, upstream_model, source_body=body)
    raise RuntimeError(f"Advisor refinement is not supported for provider {provider}")


def refine_message_with_advisor(
    provider: str,
    pcfg: dict[str, Any],
    original_body: dict[str, Any],
    message: dict[str, Any],
    main_model: str,
) -> dict[str, Any]:
    if not advisor_model_enabled(pcfg):
        return message
    if not advisor_provider_supported(provider):
        return message
    if is_advisor_request(original_body) or body_has_advisor_feedback(original_body):
        return message
    trigger = advisor_trigger_for_message(original_body, message)
    trigger, advisor_focus = advisor_focus_for_message(message, trigger)
    if not trigger:
        return message
    advisor_text = call_advisor_text(provider, pcfg, original_body, focus=advisor_focus or trigger)
    if not advisor_text:
        return message
    follow_body = body_with_internal_advisor_feedback(original_body, message, advisor_text, trigger)
    visible_summary = advisor_visible_summary(advisor_text, trigger)
    try:
        router_log("INFO", f"advisor_refinement_call trigger={trigger} main_model={main_model}")
        refined = call_provider_chat_once(provider, pcfg, follow_body, main_model)
        router_log("INFO", f"advisor_refinement_done trigger={trigger} stop_reason={refined.get('stop_reason')}")
        return prepend_anthropic_text(refined, visible_summary)
    except Exception as exc:
        router_log("WARN", f"advisor_refinement_failed trigger={trigger} model={main_model} error={type(exc).__name__}: {exc}")
        write_router_activity("advisor_refinement_error", provider, main_model, error=type(exc).__name__)
        return prepend_anthropic_text(message, visible_summary)


def anthropic_text_response(model: str, text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": f"msg_ollama_advisor_{int(time.time() * 1000)}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": max(1, len(text) // 4)},
    }


def write_anthropic_text_response(handler: BaseHTTPRequestHandler, model: str, text: str, stream: bool) -> None:
    if not stream:
        write_json(handler, anthropic_text_response(model, text))
        return
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "close")
    handler.end_headers()
    msg_id = f"msg_ollama_advisor_{int(time.time() * 1000)}"
    events = [
        ("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": max(1, len(text) // 4)}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    for event_name, payload in events:
        handler.wfile.write(f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
    handler.wfile.flush()


def write_anthropic_message_response(handler: BaseHTTPRequestHandler, message: dict[str, Any], stream: bool) -> None:
    if not stream:
        write_json(handler, message)
        return
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "close")
    handler.end_headers()
    handler.wfile.write(f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {**message, 'content': [], 'stop_reason': None}}, ensure_ascii=False)}\n\n".encode())
    for index, block in enumerate(message.get("content") or []):
        btype = block.get("type")
        if btype == "text":
            handler.wfile.write(f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': index, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n".encode())
            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': index, 'delta': {'type': 'text_delta', 'text': block.get('text', '')}}, ensure_ascii=False)}\n\n".encode())
            handler.wfile.write(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index}, ensure_ascii=False)}\n\n".encode())
        elif btype == "tool_use":
            tool_input = block.get("input") or {}
            start = {"type": "content_block_start", "index": index, "content_block": {**block, "input": {}}}
            delta = {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input, ensure_ascii=False)}}
            handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(start, ensure_ascii=False)}\n\n".encode())
            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n".encode())
            handler.wfile.write(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index}, ensure_ascii=False)}\n\n".encode())
    handler.wfile.write(f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': message.get('stop_reason') or 'end_turn', 'stop_sequence': None}, 'usage': message.get('usage') or {'output_tokens': 1}}, ensure_ascii=False)}\n\n".encode())
    handler.wfile.write(b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n")
    handler.wfile.flush()


def _write_anthropic_stream_block(handler: BaseHTTPRequestHandler, index: int, block: dict[str, Any]) -> None:
    btype = block.get("type")
    if btype == "text":
        handler.wfile.write(f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': index, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n".encode())
        handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': index, 'delta': {'type': 'text_delta', 'text': block.get('text', '')}}, ensure_ascii=False)}\n\n".encode())
        handler.wfile.write(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index}, ensure_ascii=False)}\n\n".encode())
    elif btype == "tool_use":
        tool_input = block.get("input") or {}
        start = {"type": "content_block_start", "index": index, "content_block": {**block, "input": {}}}
        delta = {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input, ensure_ascii=False)}}
        handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(start, ensure_ascii=False)}\n\n".encode())
        handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n".encode())
        handler.wfile.write(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index}, ensure_ascii=False)}\n\n".encode())


def write_anthropic_open_stream_start(handler: BaseHTTPRequestHandler, model: str, input_tokens: int = 0) -> None:
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "close")
    handler.end_headers()
    msg_id = f"msg_claude_any_{int(time.time() * 1000)}"
    payload = {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": max(0, int(input_tokens or 0)), "output_tokens": 0},
        },
    }
    handler.wfile.write(f"event: message_start\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
    handler.wfile.flush()


def write_anthropic_stream_blocks(handler: BaseHTTPRequestHandler, blocks: list[dict[str, Any]], start_index: int = 0) -> int:
    index = start_index
    for block in blocks:
        _write_anthropic_stream_block(handler, index, block)
        index += 1
    handler.wfile.flush()
    return index


def write_anthropic_open_stream_stop(handler: BaseHTTPRequestHandler, message: dict[str, Any] | None = None) -> None:
    message = message or {}
    stop_reason = message.get("stop_reason") or "end_turn"
    usage = message.get("usage") or {"output_tokens": 1}
    handler.wfile.write(f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': usage}, ensure_ascii=False)}\n\n".encode())
    handler.wfile.write(b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n")
    handler.wfile.flush()


def prepend_anthropic_text(message: dict[str, Any], text: str) -> dict[str, Any]:
    if not text:
        return message
    out = dict(message)
    content = out.get("content")
    blocks = list(content) if isinstance(content, list) else []
    blocks.insert(0, {"type": "text", "text": text})
    out["content"] = blocks
    return out


def maybe_handle_advisor_request(handler: BaseHTTPRequestHandler, provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> bool:
    if not is_advisor_request(body):
        return False
    advisor_model = str(pcfg.get("advisor_model") or "").strip()
    stream = bool(body.get("stream", True))
    if not advisor_model:
        write_anthropic_text_response(
            handler,
            str(body.get("model") or current_alias(load_config())),
            "Advisor is off. Choose an Advisor Model in the claude-any launch menu, or run `claude-anyctl advisor-model deepseek-v4-pro`, then use `/advisor` again.",
            stream,
        )
        return True
    if not advisor_provider_supported(provider):
        write_anthropic_text_response(
            handler,
            advisor_model,
            f"Advisor Model is configured as `{advisor_model}`, but claude-any advisor calling is not implemented for provider `{provider}`.",
            stream,
        )
        return True
    try:
        text = call_advisor_text(provider, pcfg, body)
        if not text:
            text = "Advisor returned no text."
    except Exception as exc:
        text = f"Advisor request failed: {type(exc).__name__}: {exc}"
    write_anthropic_text_response(handler, advisor_model, "Advisor guidance:\n\n" + text, stream)
    return True


def maybe_handle_router_debug_request(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> bool:
    if not is_router_debug_request(body):
        return False
    stream = bool(body.get("stream", True))
    value = router_debug_value_from_body(body).strip()
    cfg = load_config()
    current = router_debug_external_access_enabled(cfg)
    low = value.lower()
    should_restart = False
    if low in ("", "status", "state", "show", "?"):
        lines = [
            f"Router debug external access: {'on' if current else 'off'}.",
            f"Current router bind host: {router_bind_host(cfg)}.",
        ]
    elif low in ("toggle", "tog", "switch"):
        lines = set_router_debug_external_access_config(not current)
        should_restart = True
    elif low in ("on", "true", "1", "enable", "enabled"):
        lines = set_router_debug_external_access_config(True)
        should_restart = True
    elif low in ("off", "false", "0", "disable", "disabled"):
        lines = set_router_debug_external_access_config(False)
        should_restart = True
    else:
        lines = ["Usage: `/router-debug`, `/router-debug on`, `/router-debug off`, or `/router-debug status`."]
    if should_restart:
        lines.append("Router restart scheduled so the bind address changes immediately.")
    write_anthropic_text_response(handler, str(body.get("model") or current_alias(load_config())), "\n".join(lines), stream)
    if should_restart:
        schedule_router_process_restart()
    return True


def normalize_tool_arguments(tool_name: str, args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        if tool_name == "Bash":
            return {"command": text}
    return {}


PSEUDO_TOOL_START = "<|tool_calls_section_begin|>"
PSEUDO_TOOL_END = "<|tool_calls_section_end|>"
PSEUDO_CALL_BEGIN = "<|tool_call_begin|>"
PSEUDO_ARG_BEGIN = "<|tool_call_argument_begin|>"
PSEUDO_CALL_END = "<|tool_call_end|>"


def infer_tool_name_from_args(args: dict[str, Any]) -> str:
    keys = set(args)
    if "command" in keys:
        return "Bash"
    if {"file_path", "content"}.issubset(keys):
        return "Write"
    if {"file_path", "old_string", "new_string"}.issubset(keys):
        return "Edit"
    if "file_path" in keys:
        return "Read"
    task_update_keys = {"taskId", "task_id", "addBlocks", "addBlockedBy"}
    if keys & task_update_keys:
        return "TaskUpdate"
    return "TaskList" if not args else "Write"


def parse_pseudo_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    if PSEUDO_TOOL_START not in text:
        return text, []
    visible_parts: list[str] = []
    calls: list[dict[str, Any]] = []
    pos = 0
    while True:
        start = text.find(PSEUDO_TOOL_START, pos)
        if start < 0:
            visible_parts.append(text[pos:])
            break
        visible_parts.append(text[pos:start])
        end = text.find(PSEUDO_TOOL_END, start)
        if end < 0:
            section = text[start + len(PSEUDO_TOOL_START):]
            pos = len(text)
        else:
            section = text[start + len(PSEUDO_TOOL_START):end]
            pos = end + len(PSEUDO_TOOL_END)
        for match in re.finditer(
            re.escape(PSEUDO_CALL_BEGIN) + r"(.*?)" + re.escape(PSEUDO_ARG_BEGIN) + r"(.*?)" + re.escape(PSEUDO_CALL_END),
            section,
            flags=re.DOTALL,
        ):
            raw_header = match.group(1).strip()
            raw_args = match.group(2).strip()
            try:
                args = json.loads(raw_args)
            except Exception:
                continue
            if not isinstance(args, dict):
                continue
            name = ""
            for part in re.split(r"[\s:|,]+", raw_header):
                candidate = _fuzzy_match_tool_name(part)
                if candidate:
                    name = candidate
                    break
            if not name:
                name = infer_tool_name_from_args(args)
            calls.append({"function": {"name": name, "arguments": args}, "id": raw_header})
        if end < 0:
            break
    return "".join(visible_parts), calls


def ollama_chat_to_anthropic(data: dict[str, Any], model: str, source_body: dict[str, Any] | None = None) -> dict[str, Any]:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content: list[dict[str, Any]] = []
    text = message.get("content") or ""
    text, pseudo_tool_calls = parse_pseudo_tool_calls(text)
    if text:
        content.append({"type": "text", "text": text})
    tool_id_prefix = f"toolu_ollama_{int(time.time() * 1000)}_{os.getpid()}"
    for i, call in enumerate(list(message.get("tool_calls") or []) + pseudo_tool_calls):
        fn = call.get("function") if isinstance(call, dict) else {}
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        name = str(fn["name"])
        matched_name = _fuzzy_match_tool_name(name) or name
        raw_args = fn.get("arguments")
        normalized_args = normalize_tool_arguments(matched_name, raw_args)
        fixed_input = _validate_and_fix_tool_input(matched_name, normalized_args)
        if source_body is not None:
            matched_name, fixed_input = plan_mode_tool_name_for_emit(source_body, matched_name, fixed_input)
            if matched_name is None:
                continue
        append_tool_call_log(
            "ollama_nonstream_tool_call",
            {
                "model": model,
                "raw_name": name,
                "matched_name": matched_name,
                "raw_arguments": raw_args,
                "normalized_arguments": normalized_args,
                "emitted_input": fixed_input,
            },
        )
        content.append(
            {
                "type": "tool_use",
                "id": f"{tool_id_prefix}_{i}",
                "name": matched_name,
                "input": fixed_input,
            }
        )
    if source_body is not None and should_auto_enter_plan_mode(source_body, text, message.get("tool_calls") or []):
        router_log("WARN", "auto-synthesized EnterPlanMode from short/empty upstream response")
        return synthetic_tool_use_response(model, "EnterPlanMode")
    if source_body is not None and should_keep_work_alive_with_tasklist(source_body, text, message.get("tool_calls") or []):
        router_log("WARN", "auto-synthesized TaskList to keep work moving after tool result")
        content.append(
            {
                "type": "tool_use",
                "id": f"{tool_id_prefix}_keepalive",
                "name": "TaskList",
                "input": {},
            }
        )
    done_reason = data.get("done_reason")
    stop_reason = "tool_use" if any(block.get("type") == "tool_use" for block in content) else "end_turn"
    if done_reason == "length":
        stop_reason = "max_tokens"
    input_tokens = int(data.get("prompt_eval_count") or 0)
    if input_tokens <= 0 and isinstance(source_body, dict):
        input_tokens = estimate_tokens(source_body)
    output_tokens = int(data.get("eval_count") or 0)
    if output_tokens <= 0:
        output_tokens = max(1, len(text) // 4)
    return {
        "id": f"msg_ollama_{int(time.time() * 1000)}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content or [{"type": "text", "text": ""}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


STREAM_WORD_CHUNK_MAX_BUFFER = 64


def _split_word_buffer(buf: str, force: bool = False, max_buffer: int = STREAM_WORD_CHUNK_MAX_BUFFER) -> tuple[str, str]:
    """
    Split text into (to_flush, remainder) for word-boundary streaming.

    Without force: flush up to and including the last whitespace, unless the
    buffer length is at least max_buffer (then flush the entire buffer to avoid
    unbounded buffering on input without whitespace, e.g. very long words or
    CJK text).
    With force=True: flush the entire buffer (used at content_block_stop).
    """
    if not buf:
        return "", ""
    if force:
        return buf, ""
    last_ws = -1
    for i in range(len(buf) - 1, -1, -1):
        if buf[i].isspace():
            last_ws = i
            break
    if last_ws >= 0:
        return buf[:last_ws + 1], buf[last_ws + 1:]
    if len(buf) >= max_buffer:
        return buf, ""
    return "", buf


def _rebatch_anthropic_sse_text(handler: BaseHTTPRequestHandler, resp: Any, model: str = "claude-any-upstream", word_chunking: bool = True) -> None:
    """
    Parse upstream Anthropic SSE and re-emit it with text_delta events buffered
    to word boundaries. Non-text events (message_start/stop, content_block_start/
    stop, input_json_delta, thinking_delta, message_delta, ping, error) are
    forwarded unchanged in the same SSE framing.
    """
    text_buffers: dict[int, str] = {}
    pending_event_type: str | None = None
    pending_event_lines: list[str] = []
    saw_message_start = False
    saw_message_stop = False
    open_content_blocks: set[int] = set()

    def emit_raw(event_type: str | None, data_str: str) -> None:
        if event_type:
            handler.wfile.write(f"event: {event_type}\ndata: {data_str}\n\n".encode())
        else:
            handler.wfile.write(f"data: {data_str}\n\n".encode())
        handler.wfile.flush()

    def emit_text_delta(index: int, text: str) -> None:
        if not text:
            return
        payload = {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        }
        emit_raw("content_block_delta", json.dumps(payload, ensure_ascii=False))

    def flush_buffer(index: int, force: bool = False) -> None:
        buf = text_buffers.get(index, "")
        if not buf:
            return
        to_flush, remainder = _split_word_buffer(buf, force=force)
        text_buffers[index] = remainder
        emit_text_delta(index, to_flush)

    def process_event(event_type: str | None, data_str: str) -> None:
        nonlocal saw_message_start, saw_message_stop
        try:
            event = json.loads(data_str)
        except Exception:
            emit_raw(event_type, data_str)
            return
        if not isinstance(event, dict):
            emit_raw(event_type, data_str)
            return
        evt_type = event.get("type") or event_type
        if evt_type == "message_start":
            saw_message_start = True
        elif evt_type == "message_stop":
            saw_message_stop = True
        elif evt_type == "content_block_start":
            index = event.get("index")
            if isinstance(index, int):
                open_content_blocks.add(index)
        elif evt_type == "content_block_stop":
            index = event.get("index")
            if isinstance(index, int):
                open_content_blocks.discard(index)
        if evt_type == "content_block_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            index = event.get("index")
            if isinstance(index, int) and delta.get("type") == "text_delta":
                text = delta.get("text") or ""
                if not text:
                    return
                if not word_chunking:
                    emit_raw(event_type, data_str)
                    return
                text_buffers[index] = text_buffers.get(index, "") + text
                flush_buffer(index, force=False)
                return
            emit_raw(event_type, data_str)
            return
        if evt_type == "content_block_stop":
            index = event.get("index")
            if isinstance(index, int) and word_chunking:
                flush_buffer(index, force=True)
            emit_raw(event_type, data_str)
            return
        emit_raw(event_type, data_str)

    try:
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore")
            stripped = line.rstrip("\r\n")
            if stripped == "":
                if pending_event_lines:
                    data_str = "\n".join(pending_event_lines)
                    process_event(pending_event_type, data_str)
                pending_event_type = None
                pending_event_lines = []
                continue
            if stripped.startswith("event:"):
                pending_event_type = stripped[len("event:"):].strip() or None
                continue
            if stripped.startswith("data:"):
                pending_event_lines.append(stripped[len("data:"):].lstrip())
                continue
        if pending_event_lines:
            data_str = "\n".join(pending_event_lines)
            process_event(pending_event_type, data_str)
        for index in list(text_buffers.keys()):
            flush_buffer(index, force=True)
    except Exception as exc:
        router_log("ERROR", f"anthropic_sse_forward_error model={model} error={type(exc).__name__}: {exc}")
        try:
            if pending_event_lines:
                data_str = "\n".join(pending_event_lines)
                process_event(pending_event_type, data_str)
                pending_event_lines = []
                pending_event_type = None
            for index in list(text_buffers.keys()):
                flush_buffer(index, force=True)
            for index in sorted(open_content_blocks):
                emit_raw("content_block_stop", json.dumps({"type": "content_block_stop", "index": index}, ensure_ascii=False))
            open_content_blocks.clear()
            if not saw_message_stop:
                if not saw_message_start:
                    payload = {
                        "type": "message_start",
                        "message": {
                            "id": f"msg_claude_any_forward_{int(time.time() * 1000)}",
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": model,
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        },
                    }
                    emit_raw("message_start", json.dumps(payload, ensure_ascii=False))
                    emit_raw(
                        "content_block_start",
                        json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, ensure_ascii=False),
                    )
                    emit_text_delta(0, f"Upstream stream error: {type(exc).__name__}: {exc}")
                    emit_raw("content_block_stop", json.dumps({"type": "content_block_stop", "index": 0}, ensure_ascii=False))
                emit_raw(
                    "message_delta",
                    json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}}, ensure_ascii=False),
                )
                emit_raw("message_stop", "{\"type\":\"message_stop\"}")
        except Exception:
            pass
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _ollama_stream_to_anthropic_sse(handler: BaseHTTPRequestHandler, resp: Any, model: str, word_chunking: bool = False, provider: str = "ollama", source_body: dict[str, Any] | None = None) -> None:
    """Stream Ollama NDJSON /api/chat response as Anthropic SSE /v1/messages format."""
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "close")
    handler.end_headers()
    msg_id = f"msg_ollama_{int(time.time() * 1000)}"
    started = False
    text_started = False
    text_suppressed_for_plan = False
    next_content_index = 0
    text_index: int | None = None
    text_so_far = ""
    text_buffer = ""
    tool_calls: list[dict[str, Any]] = []
    tool_indices: list[int] = []
    stopped_tool_indices: set[int] = set()
    input_tokens = estimate_tokens(source_body) if isinstance(source_body, dict) else 0
    output_tokens = 0
    chunk: dict[str, Any] = {}
    chunks_seen = 0
    text_stopped = False
    last_activity_update = 0.0

    def emit(event_name: str, payload: dict[str, Any]) -> None:
        handler.wfile.write(f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
        handler.wfile.flush()

    def ensure_message_started() -> None:
        nonlocal started
        if started:
            return
        started = True
        event = {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": input_tokens, "output_tokens": 0},
            },
        }
        emit("message_start", event)

    def emit_text_block(index: int, text: str) -> None:
        emit("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
        if text:
            emit("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})
        emit("content_block_stop", {"type": "content_block_stop", "index": index})

    def update_stream_activity(force: bool = False) -> None:
        nonlocal last_activity_update
        now = time.time()
        if not force and now - last_activity_update < 0.5:
            return
        last_activity_update = now
        estimated_output = output_tokens or max(0, len(text_so_far) // 4)
        write_router_activity(
            "request",
            provider,
            model,
            tokens=input_tokens,
            output_tokens=estimated_output,
            chunks=chunks_seen,
            stream=True,
        )

    try:
        for line in resp:
            chunks_seen += 1
            line = line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue
            if not isinstance(chunk, dict):
                continue
            message = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
            input_tokens = max(input_tokens, int(chunk.get("prompt_eval_count") or 0))
            output_tokens = max(output_tokens, int(chunk.get("eval_count") or 0))
            if not started:
                ensure_message_started()
            # Handle text content
            text_chunk = message.get("content") or ""
            if text_chunk:
                if source_body is not None and not text_started and not tool_calls and should_auto_enter_plan_mode(source_body, text_so_far + text_chunk, []):
                    text_so_far += text_chunk
                    text_suppressed_for_plan = True
                    continue
                if text_suppressed_for_plan and not text_started and text_so_far:
                    pending_text = text_so_far + text_chunk
                    text_so_far = pending_text
                    text_suppressed_for_plan = False
                    text_started = True
                    text_index = next_content_index
                    next_content_index += 1
                    event = {
                        "type": "content_block_start",
                        "index": text_index,
                        "content_block": {"type": "text", "text": ""},
                    }
                    handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    handler.wfile.flush()
                    if word_chunking:
                        text_buffer += pending_text
                        to_flush, text_buffer = _split_word_buffer(text_buffer, force=False)
                        if to_flush:
                            event = {
                                "type": "content_block_delta",
                                "index": text_index,
                                "delta": {"type": "text_delta", "text": to_flush},
                            }
                            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                            handler.wfile.flush()
                    else:
                        event = {
                            "type": "content_block_delta",
                            "index": text_index,
                            "delta": {"type": "text_delta", "text": pending_text},
                        }
                        handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                        handler.wfile.flush()
                    update_stream_activity()
                    continue
                if not text_started:
                    text_started = True
                    text_index = next_content_index
                    next_content_index += 1
                    event = {
                        "type": "content_block_start",
                        "index": text_index,
                        "content_block": {"type": "text", "text": ""},
                    }
                    handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    handler.wfile.flush()
                text_so_far += text_chunk
                if word_chunking:
                    text_buffer += text_chunk
                    to_flush, text_buffer = _split_word_buffer(text_buffer, force=False)
                    if to_flush:
                        event = {
                            "type": "content_block_delta",
                            "index": text_index,
                            "delta": {"type": "text_delta", "text": to_flush},
                        }
                        handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                        handler.wfile.flush()
                else:
                    event = {
                        "type": "content_block_delta",
                        "index": text_index,
                        "delta": {"type": "text_delta", "text": text_chunk},
                    }
                    handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    handler.wfile.flush()
                update_stream_activity()
            # Handle tool calls
            for call in message.get("tool_calls") or []:
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                if not isinstance(fn, dict) or not fn.get("name"):
                    continue
                raw_name = str(fn["name"])
                matched_name = _fuzzy_match_tool_name(raw_name) or raw_name
                raw_args = fn.get("arguments")
                normalized_args = normalize_tool_arguments(matched_name, raw_args)
                fixed_input = _validate_and_fix_tool_input(matched_name, normalized_args)
                if source_body is not None:
                    matched_name, fixed_input = plan_mode_tool_name_for_emit(source_body, matched_name, fixed_input)
                    if matched_name is None:
                        continue
                tool_calls.append({"function": {"name": matched_name, "arguments": fixed_input}})
                tool_id = f"toolu_ollama_{int(time.time() * 1000)}_{len(tool_calls) - 1}"
                tool_index = next_content_index
                next_content_index += 1
                tool_indices.append(tool_index)
                append_tool_call_log(
                    "ollama_stream_tool_call",
                    {
                        "model": model,
                        "raw_name": raw_name,
                        "matched_name": matched_name,
                        "raw_arguments": raw_args,
                        "normalized_arguments": normalized_args,
                        "emitted_input": fixed_input,
                        "sse_index": tool_index,
                    },
                )
                tool_event = {
                    "type": "content_block_start",
                    "index": tool_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": matched_name,
                        "input": {},
                    },
                }
                handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(tool_event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
                delta_event = {
                    "type": "content_block_delta",
                    "index": tool_index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(fixed_input, ensure_ascii=False),
                    },
                }
                handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(delta_event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
                update_stream_activity()
            update_stream_activity()
        update_stream_activity(force=True)
        # Flush any remaining buffered text when word-chunking is active
        if source_body is not None and should_auto_enter_plan_mode(source_body, text_so_far, tool_calls):
            ensure_message_started()
            router_log("WARN", "auto-synthesized EnterPlanMode from short/empty upstream stream")
            tool_calls.append({"function": {"name": "EnterPlanMode", "arguments": {}}})
            tool_id = f"toolu_ollama_plan_{int(time.time() * 1000)}"
            tool_index = next_content_index
            next_content_index += 1
            tool_indices.append(tool_index)
            tool_event = {
                "type": "content_block_start",
                "index": tool_index,
                "content_block": {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "EnterPlanMode",
                    "input": {},
                },
            }
            handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(tool_event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
            delta_event = {
                "type": "content_block_delta",
                "index": tool_index,
                "delta": {"type": "input_json_delta", "partial_json": "{}"},
            }
            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(delta_event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
        elif text_suppressed_for_plan and not text_started and text_so_far:
            text_started = True
            text_index = next_content_index
            next_content_index += 1
            event = {
                "type": "content_block_start",
                "index": text_index,
                "content_block": {"type": "text", "text": ""},
            }
            handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
            event = {
                "type": "content_block_delta",
                "index": text_index,
                "delta": {"type": "text_delta", "text": text_so_far},
            }
            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
        if word_chunking and text_started and text_buffer:
            to_flush, text_buffer = _split_word_buffer(text_buffer, force=True)
            if to_flush:
                event = {
                    "type": "content_block_delta",
                    "index": text_index,
                    "delta": {"type": "text_delta", "text": to_flush},
                }
                handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
        if source_body is not None and should_keep_work_alive_with_tasklist(source_body, text_so_far, tool_calls):
            ensure_message_started()
            router_log("WARN", "auto-synthesized TaskList to keep work moving after tool result stream")
            tool_calls.append({"function": {"name": "TaskList", "arguments": {}}})
            tool_id = f"toolu_ollama_keepalive_{int(time.time() * 1000)}"
            tool_index = next_content_index
            next_content_index += 1
            tool_indices.append(tool_index)
            tool_event = {
                "type": "content_block_start",
                "index": tool_index,
                "content_block": {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "TaskList",
                    "input": {},
                },
            }
            handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(tool_event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
            delta_event = {
                "type": "content_block_delta",
                "index": tool_index,
                "delta": {"type": "input_json_delta", "partial_json": "{}"},
            }
            handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(delta_event, ensure_ascii=False)}\n\n".encode())
            handler.wfile.flush()
        # Send content_block_stop for text if any
        if text_started:
            event = {"type": "content_block_stop", "index": text_index}
            emit("content_block_stop", event)
            text_stopped = True
        # Send content_block_stop for each tool call
        for tool_index in tool_indices:
            event = {"type": "content_block_stop", "index": tool_index}
            emit("content_block_stop", event)
            stopped_tool_indices.add(tool_index)
        if not started:
            ensure_message_started()
        if not text_started and not tool_indices:
            router_log("WARN", f"ollama_empty_stream provider={provider} model={model} chunks={chunks_seen}")
            write_router_activity("error", provider, model, error="empty_stream", stream=True)
            empty_index = next_content_index
            next_content_index += 1
            emit_text_block(empty_index, "")
        # Determine stop reason
        stop_reason = "tool_use" if tool_calls else "end_turn"
        if chunk.get("done_reason") == "length":
            stop_reason = "max_tokens"
        # Send message_delta with final stop_reason
        event = {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        }
        emit("message_delta", event)
        # Send message_stop
        emit("message_stop", {"type": "message_stop"})
        if text_started or tool_indices:
            write_router_activity(
                "success",
                provider,
                model,
                tokens=input_tokens,
                output_tokens=output_tokens or max(1, len(text_so_far) // 4),
                chunks=chunks_seen,
                stream=True,
            )
    except Exception as exc:
        router_log("ERROR", f"ollama_stream_error provider={provider} model={model} error={type(exc).__name__}: {exc}")
        write_router_activity("error", provider, model, error=type(exc).__name__, stream=True)
        try:
            ensure_message_started()
            if word_chunking and text_started and text_buffer:
                to_flush, text_buffer = _split_word_buffer(text_buffer, force=True)
                if to_flush and text_index is not None:
                    emit("content_block_delta", {"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": to_flush}})
            if text_started and text_index is not None and not text_stopped:
                emit("content_block_stop", {"type": "content_block_stop", "index": text_index})
            for tool_index in tool_indices:
                if tool_index not in stopped_tool_indices:
                    emit("content_block_stop", {"type": "content_block_stop", "index": tool_index})
            if not text_started and not tool_indices:
                error_index = next_content_index
                next_content_index += 1
                emit_text_block(error_index, "")
            emit("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": max(1, output_tokens or len(text_so_far) // 4)}})
            emit("message_stop", {"type": "message_stop"})
        except Exception:
            pass
    finally:
        try:
            resp.close()
        except Exception:
            pass
        try:
            final_stop_reason = locals().get("stop_reason")
            dump_response_for_trace(
                provider=provider,
                model=model,
                text_so_far=text_so_far,
                tool_calls=tool_calls,
                stop_reason=final_stop_reason if isinstance(final_stop_reason, str) else None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                last_chunk=chunk if isinstance(chunk, dict) else None,
            )
        except Exception:
            pass


def forward_ollama_api_chat(handler: BaseHTTPRequestHandler, provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> None:
    _update_tool_schema_registry(body.get("tools"))
    model = resolve_requested_model(provider, pcfg, body.get("model"))
    base = pcfg.get("base_url", "").rstrip("/")
    original_body = body
    upstream_body = body_with_advisor_tool(body, pcfg) if advisor_provider_supported(provider) else body
    stream_requested = body.get("stream", True)
    if not bool(pcfg.get("stream_enabled", True)):
        stream_requested = False
    if stream_requested and advisor_model_enabled(pcfg) and advisor_provider_supported(provider):
        stream_requested = False
        router_log("INFO", "advisor tool enabled; collecting this turn so advisor tool calls can be resolved internally")
    if stream_requested and advisor_gate_possible_for_body(provider, pcfg, body):
        gate_reason = advisor_gate_reason_for_body(provider, pcfg, body)
        stream_requested = False
        router_log("INFO", f"advisor gate enabled reason={gate_reason}; collecting this turn before returning it to Claude Code")
    word_chunking = bool(pcfg.get("stream_word_chunking", False))
    req_body = ollama_chat_request(model, upstream_body, pcfg, stream=stream_requested)
    headers = provider_headers(provider, pcfg)
    url = join_url(base, "/api/chat")
    waited, rpm_used, rpm_limit = apply_router_rate_limit(provider, pcfg, model)
    rpm_status = bool(pcfg.get("rate_limit_status", True))
    if stream_requested:
        # Stream Ollama response through as Anthropic SSE
        data_bytes = json.dumps(req_body).encode("utf-8")
        req_tokens = estimate_tokens(req_body)
        req_bytes = len(data_bytes)
        gateway_retries = configured_gateway_retries(pcfg)
        max_attempts = max(1, gateway_retries + 1)
        resp = None
        for attempt in range(max_attempts):
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            try:
                write_router_activity(
                    "request",
                    provider,
                    model,
                    attempt=attempt + 1,
                    total=max_attempts,
                    tokens=req_tokens,
                    bytes=req_bytes,
                    timeout=ollama_request_timeout_seconds(pcfg),
                    stream=True,
                )
                router_log("INFO", f"ollama_stream_request provider={provider} model={model} attempt={attempt + 1}/{max_attempts} tokens={req_tokens} bytes={req_bytes}")
                resp = urllib.request.urlopen(req, timeout=ollama_request_timeout_seconds(pcfg))
                set_upstream_stream_read_timeout(resp, provider_stream_idle_timeout_seconds(pcfg))
                learn_router_rate_limit_headers(provider, pcfg, model, resp.headers)
                break
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="ignore")
                learn_router_rate_limit_headers(provider, pcfg, model, exc.headers)
                if exc.code == 429 and attempt + 1 < max_attempts:
                    retry_no = attempt + 1
                    wait = register_router_rate_limit_backoff(provider, pcfg, model, exc.headers.get("Retry-After"))
                    write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, wait=wait, tokens=req_tokens, bytes=req_bytes, stream=True)
                    router_log("WARN", f"ollama_stream_rate_limit_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} wait={wait:.2f}s tokens={req_tokens} bytes={req_bytes}")
                    time.sleep(wait)
                    continue
                if exc.code in UPSTREAM_RETRY_HTTP_CODES and attempt + 1 < max_attempts:
                    retry_no = attempt + 1
                    write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, tokens=req_tokens, bytes=req_bytes, stream=True)
                    router_log("WARN", f"ollama_stream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} code={exc.code} tokens={req_tokens} bytes={req_bytes}")
                    time.sleep(upstream_retry_wait_seconds(retry_no))
                    continue
                write_router_activity("error", provider, model, code=exc.code, tokens=req_tokens, bytes=req_bytes, stream=True)
                write_json(
                    handler,
                    {"type": "error", "error": {"type": "upstream_error", "message": upstream_http_error_message(exc, raw)}},
                    exc.code,
                )
                return
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                if retryable_upstream_exception(exc) and attempt + 1 < max_attempts:
                    retry_no = attempt + 1
                    write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, error=type(exc).__name__, tokens=req_tokens, bytes=req_bytes, stream=True)
                    router_log("WARN", f"ollama_stream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} error={type(exc).__name__} tokens={req_tokens} bytes={req_bytes}")
                    time.sleep(upstream_retry_wait_seconds(retry_no))
                    continue
                write_router_activity("error", provider, model, error=type(exc).__name__, tokens=req_tokens, bytes=req_bytes, stream=True)
                write_json(
                    handler,
                    {"type": "error", "error": {"type": "upstream_error", "message": f"{type(exc).__name__}: {exc}"}},
                    504 if retryable_upstream_exception(exc) else 502,
                )
                return
        if resp is None:
            write_router_activity("error", provider, model, tokens=req_tokens, bytes=req_bytes, stream=True)
            write_json(
                handler,
                {"type": "error", "error": {"type": "upstream_error", "message": "upstream stream request failed"}},
                504,
            )
            return
        # Check if Claude Code requested SSE streaming
        accept = handler.headers.get("accept", "")
        if "text/event-stream" in accept or stream_requested:
            _ollama_stream_to_anthropic_sse(handler, resp, model, word_chunking=word_chunking, provider=provider, source_body=original_body)
        else:
            # Non-SSE client but streaming from Ollama: collect full response
            chunks = []
            for line in resp:
                chunks.append(line)
            resp.close()
            full = b"".join(chunks).decode("utf-8", errors="ignore")
            data = None
            for line in full.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if isinstance(chunk, dict) and chunk.get("done"):
                        data = chunk
                except Exception:
                    continue
            if data is None:
                data = {"message": {"content": ""}, "done": True, "done_reason": "end_turn"}
            message = ollama_chat_to_anthropic(data, model, source_body=original_body)
            message = refine_message_with_advisor(provider, pcfg, original_body, message, model)
            message = prepend_anthropic_text(message, rate_limit_notice(waited, rpm_used, rpm_limit, rpm_status))
            write_json(handler, message)
        return
    # Non-streaming fallback
    data_bytes = json.dumps(req_body).encode("utf-8")
    req_tokens = estimate_tokens(req_body)
    req_bytes = len(data_bytes)
    gateway_retries = configured_gateway_retries(pcfg)
    max_attempts = max(1, gateway_retries + 1)
    data = None
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            write_router_activity(
                "request",
                provider,
                model,
                attempt=attempt + 1,
                total=max_attempts,
                tokens=req_tokens,
                bytes=req_bytes,
                timeout=ollama_request_timeout_seconds(pcfg),
            )
            router_log("INFO", f"ollama_request provider={provider} model={model} attempt={attempt + 1}/{max_attempts} tokens={req_tokens} bytes={req_bytes}")
            with urllib.request.urlopen(req, timeout=ollama_request_timeout_seconds(pcfg)) as resp:
                learn_router_rate_limit_headers(provider, pcfg, model, resp.headers)
                data = json.loads(resp.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            learn_router_rate_limit_headers(provider, pcfg, model, exc.headers)
            if exc.code == 429 and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                wait = register_router_rate_limit_backoff(provider, pcfg, model, exc.headers.get("Retry-After"))
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, wait=wait, tokens=req_tokens, bytes=req_bytes)
                router_log("WARN", f"ollama_rate_limit_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} wait={wait:.2f}s tokens={req_tokens} bytes={req_bytes}")
                time.sleep(wait)
                continue
            if exc.code in UPSTREAM_RETRY_HTTP_CODES and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, tokens=req_tokens, bytes=req_bytes)
                router_log("WARN", f"ollama_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} code={exc.code} tokens={req_tokens} bytes={req_bytes}")
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, code=exc.code, tokens=req_tokens, bytes=req_bytes)
            write_json(
                handler,
                {"type": "error", "error": {"type": "upstream_error", "message": upstream_http_error_message(exc, raw)}},
                exc.code,
            )
            return
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            if retryable_upstream_exception(exc) and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, error=type(exc).__name__, tokens=req_tokens, bytes=req_bytes)
                router_log("WARN", f"ollama_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} error={type(exc).__name__} tokens={req_tokens} bytes={req_bytes}")
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, error=type(exc).__name__, tokens=req_tokens, bytes=req_bytes)
            write_json(
                handler,
                {"type": "error", "error": {"type": "upstream_error", "message": f"{type(exc).__name__}: {exc}"}},
                504 if retryable_upstream_exception(exc) else 502,
            )
            return
    if data is None:
        write_router_activity("error", provider, model, tokens=req_tokens, bytes=req_bytes)
        write_json(
            handler,
            {"type": "error", "error": {"type": "upstream_error", "message": "upstream request failed"}},
            504,
        )
        return
    message = ollama_chat_to_anthropic(data, model, source_body=original_body)
    message = refine_message_with_advisor(provider, pcfg, original_body, message, model)
    message = prepend_anthropic_text(message, rate_limit_notice(waited, rpm_used, rpm_limit, rpm_status))
    write_json(handler, message)


def openai_chat_to_anthropic(data: dict[str, Any], model: str, source_body: dict[str, Any] | None = None) -> dict[str, Any]:
    choice = {}
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    wrapped = {
        "message": {
            "content": message.get("content") or "",
            "tool_calls": message.get("tool_calls") or [],
        },
        "done_reason": "length" if choice.get("finish_reason") == "length" else "stop",
    }
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    wrapped["prompt_eval_count"] = positive_int(usage.get("prompt_tokens")) or (estimate_tokens(source_body) if isinstance(source_body, dict) else 0)
    wrapped["eval_count"] = positive_int(usage.get("completion_tokens")) or 0
    return ollama_chat_to_anthropic(wrapped, model, source_body=source_body)


def stream_openai_chat_to_anthropic_sse(
    handler: BaseHTTPRequestHandler,
    resp: Any,
    model: str,
    provider: str,
    source_body: dict[str, Any] | None = None,
    start_index: int = 0,
    word_chunking: bool = False,
    input_tokens: int | None = None,
    input_bytes: int | None = None,
) -> bool:
    next_content_index = start_index
    text_started = False
    text_suppressed_for_plan = False
    text_index: int | None = None
    text_so_far = ""
    pseudo_text = ""
    pseudo_mode = False
    text_buffer = ""
    text_stopped = False
    tool_fragments: dict[int, dict[str, Any]] = {}
    output_tokens = 0
    finish_reason = "stop"
    chunks_seen = 0
    last_activity_update = 0.0

    def emit(event_name: str, payload: dict[str, Any]) -> None:
        handler.wfile.write(f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
        handler.wfile.flush()

    def ensure_text_started() -> int:
        nonlocal text_started, text_index, next_content_index, text_stopped
        if text_started and text_index is not None:
            return text_index
        text_started = True
        text_stopped = False
        text_index = next_content_index
        next_content_index += 1
        emit(
            "content_block_start",
            {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}},
        )
        return text_index

    def emit_text_delta(text: str) -> None:
        if not text:
            return
        idx = ensure_text_started()
        emit(
            "content_block_delta",
            {"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": text}},
        )

    def update_stream_activity(force: bool = False) -> None:
        nonlocal last_activity_update
        now = time.time()
        if not force and now - last_activity_update < 0.5:
            return
        last_activity_update = now
        estimated_output = output_tokens or max(0, len(text_so_far) // 4)
        write_router_activity(
            "request",
            provider,
            model,
            tokens=input_tokens,
            bytes=input_bytes,
            output_tokens=estimated_output,
            chunks=chunks_seen,
            stream=True,
        )

    try:
        for raw_line in resp:
            chunks_seen += 1
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                break
            try:
                event = json.loads(line)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            usage = event.get("usage")
            if isinstance(usage, dict):
                output_tokens = max(output_tokens, positive_int(usage.get("completion_tokens")) or 0)
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0] if isinstance(choices[0], dict) else {}
            if choice.get("finish_reason"):
                finish_reason = str(choice.get("finish_reason"))
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            text_chunk = delta.get("content") or ""
            if text_chunk:
                if pseudo_mode or PSEUDO_TOOL_START in text_chunk:
                    before, sep, after = text_chunk.partition(PSEUDO_TOOL_START)
                    if before and not pseudo_mode:
                        text_so_far += before
                        if word_chunking:
                            text_buffer += before
                            to_flush, text_buffer = _split_word_buffer(text_buffer, force=False)
                            emit_text_delta(to_flush)
                        else:
                            emit_text_delta(before)
                    pseudo_mode = True
                    pseudo_text += (sep + after) if sep else text_chunk
                    if PSEUDO_TOOL_END in pseudo_text:
                        pseudo_mode = False
                    continue
                if source_body is not None and not text_started and not tool_fragments and should_auto_enter_plan_mode(source_body, text_so_far + text_chunk, []):
                    text_so_far += text_chunk
                    text_suppressed_for_plan = True
                    continue
                if text_suppressed_for_plan and not text_started and text_so_far:
                    pending_text = text_so_far + text_chunk
                    text_so_far = pending_text
                    text_suppressed_for_plan = False
                    if word_chunking:
                        text_buffer += pending_text
                        to_flush, text_buffer = _split_word_buffer(text_buffer, force=False)
                        emit_text_delta(to_flush)
                    else:
                        emit_text_delta(pending_text)
                    update_stream_activity()
                    continue
                text_so_far += text_chunk
                if word_chunking:
                    text_buffer += text_chunk
                    to_flush, text_buffer = _split_word_buffer(text_buffer, force=False)
                    emit_text_delta(to_flush)
                else:
                    emit_text_delta(text_chunk)
                update_stream_activity()
            for call in delta.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                try:
                    call_index = int(call.get("index"))
                except Exception:
                    call_index = len(tool_fragments)
                slot = tool_fragments.setdefault(call_index, {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    slot["id"] = str(call.get("id"))
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                if fn.get("name"):
                    slot["name"] += str(fn.get("name"))
                if fn.get("arguments"):
                    slot["arguments"] += str(fn.get("arguments"))
                update_stream_activity()
        update_stream_activity(force=True)
        if word_chunking and text_buffer:
            to_flush, text_buffer = _split_word_buffer(text_buffer, force=True)
            emit_text_delta(to_flush)

        tool_calls: list[dict[str, Any]] = []
        _, pseudo_tool_calls = parse_pseudo_tool_calls(pseudo_text)
        for i, pseudo in enumerate(pseudo_tool_calls):
            fn = pseudo.get("function") if isinstance(pseudo, dict) else {}
            if isinstance(fn, dict):
                tool_fragments.setdefault(100000 + i, {
                    "id": str(pseudo.get("id") or ""),
                    "name": str(fn.get("name") or ""),
                    "arguments": json.dumps(fn.get("arguments") or {}, ensure_ascii=False),
                })
        for _, fragment in sorted(tool_fragments.items()):
            raw_name = str(fragment.get("name") or "")
            if not raw_name:
                continue
            matched_name = _fuzzy_match_tool_name(raw_name) or raw_name
            normalized_args = normalize_tool_arguments(matched_name, fragment.get("arguments") or {})
            fixed_input = _validate_and_fix_tool_input(matched_name, normalized_args)
            if source_body is not None:
                matched_name, fixed_input = plan_mode_tool_name_for_emit(source_body, matched_name, fixed_input)
                if matched_name is None:
                    continue
            tool_calls.append({"function": {"name": matched_name, "arguments": fixed_input}})
            tool_index = next_content_index
            next_content_index += 1
            tool_id = str(fragment.get("id") or f"toolu_openai_{int(time.time() * 1000)}_{tool_index}")
            append_tool_call_log(
                "openai_stream_tool_call",
                {
                    "model": model,
                    "raw_name": raw_name,
                    "matched_name": matched_name,
                    "raw_arguments": fragment.get("arguments"),
                    "emitted_input": fixed_input,
                    "sse_index": tool_index,
                },
            )
            emit(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": tool_index,
                    "content_block": {"type": "tool_use", "id": tool_id, "name": matched_name, "input": {}},
                },
            )
            emit(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": tool_index,
                    "delta": {"type": "input_json_delta", "partial_json": json.dumps(fixed_input, ensure_ascii=False)},
                },
            )
            emit("content_block_stop", {"type": "content_block_stop", "index": tool_index})

        if source_body is not None and should_auto_enter_plan_mode(source_body, text_so_far, tool_calls):
            router_log("WARN", "auto-synthesized EnterPlanMode from short/empty upstream OpenAI stream")
            tool_index = next_content_index
            next_content_index += 1
            tool_calls.append({"function": {"name": "EnterPlanMode", "arguments": {}}})
            emit(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": tool_index,
                    "content_block": {"type": "tool_use", "id": f"toolu_openai_plan_{int(time.time() * 1000)}", "name": "EnterPlanMode", "input": {}},
                },
            )
            emit("content_block_delta", {"type": "content_block_delta", "index": tool_index, "delta": {"type": "input_json_delta", "partial_json": "{}"}})
            emit("content_block_stop", {"type": "content_block_stop", "index": tool_index})
        elif text_suppressed_for_plan and not text_started and text_so_far:
            emit_text_delta(text_so_far)

        if source_body is not None and should_keep_work_alive_with_tasklist(source_body, text_so_far, tool_calls):
            router_log("WARN", "auto-synthesized TaskList to keep work moving after OpenAI stream")
            tool_index = next_content_index
            next_content_index += 1
            tool_calls.append({"function": {"name": "TaskList", "arguments": {}}})
            emit(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": tool_index,
                    "content_block": {"type": "tool_use", "id": f"toolu_openai_keepalive_{int(time.time() * 1000)}", "name": "TaskList", "input": {}},
                },
            )
            emit("content_block_delta", {"type": "content_block_delta", "index": tool_index, "delta": {"type": "input_json_delta", "partial_json": "{}"}})
            emit("content_block_stop", {"type": "content_block_stop", "index": tool_index})

        if text_started and text_index is not None:
            emit("content_block_stop", {"type": "content_block_stop", "index": text_index})
            text_stopped = True
        stop_reason = "tool_use" if tool_calls else ("max_tokens" if finish_reason == "length" else "end_turn")
        write_anthropic_open_stream_stop(handler, {"stop_reason": stop_reason, "usage": {"output_tokens": output_tokens or max(1, len(text_so_far) // 4)}})
        return True
    except Exception as exc:
        router_log("ERROR", f"openai_stream_error provider={provider} model={model} error={type(exc).__name__}: {exc}")
        write_router_activity("error", provider, model, error=type(exc).__name__, stream=True)
        try:
            if word_chunking and text_buffer:
                to_flush, text_buffer = _split_word_buffer(text_buffer, force=True)
                emit_text_delta(to_flush)
            if not text_started:
                emit_text_delta(f"Upstream stream error: {type(exc).__name__}: {exc}")
            if text_started and text_index is not None and not text_stopped:
                emit("content_block_stop", {"type": "content_block_stop", "index": text_index})
                text_stopped = True
            write_anthropic_open_stream_stop(
                handler,
                {"stop_reason": "end_turn", "usage": {"output_tokens": output_tokens or max(1, len(text_so_far) // 4)}},
            )
        except Exception:
            pass
        return False
    finally:
        try:
            resp.close()
        except Exception:
            pass


def upstream_http_error_message(exc: urllib.error.HTTPError, raw: str | None = None) -> str:
    if raw is None:
        raw = exc.read().decode("utf-8", errors="ignore")
    msg = raw.strip() or str(exc)
    try:
        err = json.loads(raw)
        if isinstance(err, dict):
            if isinstance(err.get("error"), dict):
                msg = str(err["error"].get("message") or err["error"])
            elif err.get("error"):
                msg = str(err["error"])
            elif err.get("message"):
                msg = str(err["message"])
    except Exception:
        pass
    return msg


UPSTREAM_RETRY_HTTP_CODES: frozenset[int] = frozenset({502, 503, 504})


def upstream_retry_message(attempt: int, total: int) -> str:
    lang = str(load_config().get("language") or "en")
    if lang == "ko":
        return f"서버가 응답하지 않아 재시도합니다 ({attempt}/{total})."
    if lang == "ja":
        return f"サーバーが応答しないため再試行します ({attempt}/{total})。"
    if lang == "zh":
        return f"服务器未响应，正在重试 ({attempt}/{total})。"
    return f"Upstream server did not respond; retrying ({attempt}/{total})."


def upstream_rate_limit_retry_message(attempt: int, total: int) -> str:
    lang = str(load_config().get("language") or "en")
    if lang == "ko":
        return f"Upstream rate limit에 도달해 대기 후 재시도합니다 ({attempt}/{total})."
    if lang == "ja":
        return f"Upstream rate limit に達したため、待機して再試行します ({attempt}/{total})。"
    if lang == "zh":
        return f"已达到 upstream rate limit，等待后重试 ({attempt}/{total})。"
    return f"Upstream rate limit reached; waiting before retry ({attempt}/{total})."


def upstream_retry_wait_seconds(attempt: int) -> float:
    return min(20.0, 2.0 * max(1, attempt))


def retryable_upstream_exception(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "timed out",
        "timeout",
        "connection aborted",
        "connection was aborted",
        "connection reset",
        "connection refused",
        "remote end closed connection",
        "remote disconnected",
        "eof occurred in violation of protocol",
        "temporarily unavailable",
        "broken pipe",
    )
    return any(marker in text for marker in markers)


def configured_gateway_retries(pcfg: dict[str, Any]) -> int:
    value = pcfg.get("gateway_retries")
    if value is None:
        return 2
    try:
        retries = int(value)
    except Exception:
        return 2
    return max(0, retries)


def post_json_with_rate_retry(
    url: str,
    req_body: Any,
    headers: dict[str, str],
    timeout: float,
    provider: str,
    pcfg: dict[str, Any],
    model: str,
    retry_notice: Callable[[str], None] | None = None,
) -> Any:
    gateway_retries = configured_gateway_retries(pcfg)
    max_attempts = max(1, gateway_retries + 1)
    token_estimate = estimate_tokens(req_body)
    byte_estimate = len(json.dumps(req_body, ensure_ascii=False).encode("utf-8"))
    for attempt in range(max_attempts):
        try:
            write_router_activity(
                "request",
                provider,
                model,
                attempt=attempt + 1,
                total=max_attempts,
                tokens=token_estimate,
                bytes=byte_estimate,
                timeout=timeout,
            )
            router_log("INFO", f"upstream_request provider={provider} model={model} attempt={attempt + 1}/{max_attempts} tokens={token_estimate} bytes={byte_estimate} timeout={timeout}")
            data_bytes = json.dumps(req_body).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                learn_router_rate_limit_headers(provider, pcfg, model, resp.headers)
                data = json.loads(resp.read().decode("utf-8"))
                write_router_activity("success", provider, model, attempt=attempt + 1, tokens=token_estimate, bytes=byte_estimate)
                return data
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            learn_router_rate_limit_headers(provider, pcfg, model, exc.headers)
            if exc.code == 429 and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                wait = register_router_rate_limit_backoff(provider, pcfg, model, exc.headers.get("Retry-After"))
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, wait=wait, tokens=token_estimate, bytes=byte_estimate)
                router_log("WARN", f"upstream_rate_limit_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} wait={wait:.2f}s tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_rate_limit_retry_message(retry_no, gateway_retries))
                time.sleep(wait)
                continue
            if exc.code in UPSTREAM_RETRY_HTTP_CODES and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, tokens=token_estimate, bytes=byte_estimate)
                router_log("WARN", f"upstream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} code={exc.code} tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_retry_message(retry_no, gateway_retries))
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, code=exc.code, tokens=token_estimate, bytes=byte_estimate)
            raise RuntimeError(upstream_http_error_message(exc, raw)) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            if retryable_upstream_exception(exc) and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, error=type(exc).__name__, tokens=token_estimate, bytes=byte_estimate)
                router_log("WARN", f"upstream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} error={type(exc).__name__} tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_retry_message(retry_no, gateway_retries))
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, error=type(exc).__name__, tokens=token_estimate, bytes=byte_estimate)
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    raise RuntimeError("upstream request failed")


def open_openai_stream_with_rate_retry(
    url: str,
    req_body: Any,
    headers: dict[str, str],
    timeout: float,
    provider: str,
    pcfg: dict[str, Any],
    model: str,
    retry_notice: Callable[[str], None] | None = None,
) -> Any:
    gateway_retries = configured_gateway_retries(pcfg)
    max_attempts = max(1, gateway_retries + 1)
    token_estimate = estimate_tokens(req_body)
    byte_estimate = len(json.dumps(req_body, ensure_ascii=False).encode("utf-8"))
    data_bytes = json.dumps(req_body).encode("utf-8")
    for attempt in range(max_attempts):
        try:
            write_router_activity(
                "request",
                provider,
                model,
                attempt=attempt + 1,
                total=max_attempts,
                tokens=token_estimate,
                bytes=byte_estimate,
                timeout=timeout,
                stream=True,
            )
            router_log("INFO", f"upstream_stream_request provider={provider} model={model} attempt={attempt + 1}/{max_attempts} tokens={token_estimate} bytes={byte_estimate} timeout={timeout}")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            resp = urllib.request.urlopen(req, timeout=timeout)
            set_upstream_stream_read_timeout(resp, provider_stream_idle_timeout_seconds(pcfg))
            learn_router_rate_limit_headers(provider, pcfg, model, resp.headers)
            return resp
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            learn_router_rate_limit_headers(provider, pcfg, model, exc.headers)
            if exc.code == 429 and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                wait = register_router_rate_limit_backoff(provider, pcfg, model, exc.headers.get("Retry-After"))
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, wait=wait, tokens=token_estimate, bytes=byte_estimate, stream=True)
                router_log("WARN", f"upstream_stream_rate_limit_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} wait={wait:.2f}s tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_rate_limit_retry_message(retry_no, gateway_retries))
                time.sleep(wait)
                continue
            if exc.code in UPSTREAM_RETRY_HTTP_CODES and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, code=exc.code, tokens=token_estimate, bytes=byte_estimate, stream=True)
                router_log("WARN", f"upstream_stream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} code={exc.code} tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_retry_message(retry_no, gateway_retries))
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, code=exc.code, tokens=token_estimate, bytes=byte_estimate, stream=True)
            raise RuntimeError(upstream_http_error_message(exc, raw)) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            if retryable_upstream_exception(exc) and attempt + 1 < max_attempts:
                retry_no = attempt + 1
                write_router_activity("retry", provider, model, attempt=retry_no, total=gateway_retries, error=type(exc).__name__, tokens=token_estimate, bytes=byte_estimate, stream=True)
                router_log("WARN", f"upstream_stream_retry provider={provider} model={model} attempt={retry_no}/{gateway_retries} error={type(exc).__name__} tokens={token_estimate} bytes={byte_estimate}")
                if retry_notice:
                    retry_notice(upstream_retry_message(retry_no, gateway_retries))
                time.sleep(upstream_retry_wait_seconds(retry_no))
                continue
            write_router_activity("error", provider, model, error=type(exc).__name__, tokens=token_estimate, bytes=byte_estimate, stream=True)
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    raise RuntimeError("upstream stream request failed")


def forward_openai_compatible_chat(handler: BaseHTTPRequestHandler, provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> None:
    _update_tool_schema_registry(body.get("tools"))
    model = resolve_requested_model(provider, pcfg, body.get("model"))
    if provider == "nvidia-hosted":
        model = ncp_model_id_for_nvidia_hosted(model)
    original_body = body
    upstream_body = body_with_advisor_tool(body, pcfg) if advisor_provider_supported(provider) else body
    url = join_url(provider_upstream_request_base(provider, pcfg), "/chat/completions")
    waited, rpm_used, rpm_limit = apply_router_rate_limit(provider, pcfg, model)
    stream_enabled = bool(pcfg.get("stream_enabled", True))
    stream = True if provider == "nvidia-hosted" else bool(body.get("stream", stream_enabled)) and stream_enabled
    if stream and advisor_model_enabled(pcfg) and advisor_provider_supported(provider):
        stream = False
        router_log("INFO", f"advisor tool enabled for {provider}; collecting this turn so advisor tool calls can be resolved internally")
    if stream and advisor_gate_possible_for_body(provider, pcfg, body):
        gate_reason = advisor_gate_reason_for_body(provider, pcfg, body)
        stream = False
        router_log("INFO", f"advisor gate enabled for {provider} reason={gate_reason}; collecting this turn before returning it to Claude Code")
    notice = rate_limit_notice(waited, rpm_used, rpm_limit, bool(pcfg.get("rate_limit_status", True)))
    if stream:
        req_body = openai_compatible_chat_request(provider, model, upstream_body, pcfg, stream=True)
        req_tokens = estimate_tokens(req_body)
        req_bytes = len(json.dumps(req_body, ensure_ascii=False).encode("utf-8"))
        write_anthropic_open_stream_start(handler, model, input_tokens=req_tokens)
        index = 0
        if notice:
            index = write_anthropic_stream_blocks(handler, [{"type": "text", "text": notice}], index)
        try:
            def emit_retry_notice(text: str) -> None:
                nonlocal index
                index = write_anthropic_stream_blocks(handler, [{"type": "text", "text": text + "\n"}], index)

            resp = open_openai_stream_with_rate_retry(
                url,
                req_body,
                provider_headers(provider, pcfg),
                provider_request_timeout_seconds(pcfg),
                provider,
                pcfg,
                model,
                emit_retry_notice,
            )
            stream_ok = stream_openai_chat_to_anthropic_sse(
                handler,
                resp,
                model,
                provider,
                source_body=original_body,
                start_index=index,
                word_chunking=bool(pcfg.get("stream_word_chunking", False)),
                input_tokens=req_tokens,
                input_bytes=req_bytes,
            )
            if stream_ok:
                write_router_activity("success", provider, model, tokens=req_tokens, bytes=req_bytes, stream=True)
        except RuntimeError as exc:
            msg = str(exc)
            write_anthropic_stream_blocks(handler, [{"type": "text", "text": f"Upstream error: {msg}"}], index)
            write_anthropic_open_stream_stop(handler)
            return
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            write_router_activity("error", provider, model, error=type(exc).__name__, stream=True)
            write_anthropic_stream_blocks(handler, [{"type": "text", "text": f"Upstream error: {msg}"}], index)
            write_anthropic_open_stream_stop(handler)
            return
        return
    req_body = openai_compatible_chat_request(provider, model, upstream_body, pcfg, stream=False)
    try:
        data = post_json_with_rate_retry(
            url,
            req_body,
            provider_headers(provider, pcfg),
            provider_request_timeout_seconds(pcfg),
            provider,
            pcfg,
            model,
            None,
        )
    except RuntimeError as exc:
        write_json(handler, {"type": "error", "error": {"type": "upstream_error", "message": str(exc)}}, 500)
        return
    message = openai_chat_to_anthropic(data, model, source_body=original_body)
    message = refine_message_with_advisor(provider, pcfg, original_body, message, model)
    message = prepend_anthropic_text(message, notice)
    write_anthropic_message_response(handler, message, stream)


class RouterHandler(BaseHTTPRequestHandler):
    server_version = "claude-any/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            router_log("INFO", "access " + (fmt % args))
        except Exception:
            pass

    def log_error(self, fmt: str, *args: Any) -> None:
        try:
            router_log("ERROR", "http " + (fmt % args))
        except Exception:
            pass

    def do_HEAD(self) -> None:
        cfg = load_config()
        if reject_external_router_request(self, cfg):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("content-type", "application/json")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        cfg = load_config()
        if reject_external_router_request(self, cfg):
            return
        if handle_events_get(self, path, query):
            return
        if handle_llm_config_get(self, path):
            return
        if handle_channel_mcp_get(self, path):
            return
        if handle_chat_get(self, path) or handle_plan_get(self, path):
            return
        provider, pcfg = get_current_provider(cfg)
        if path == "/":
            write_text_response(self, render_router_home_html(cfg, provider, pcfg), content_type="text/html; charset=utf-8")
            return
        if path in ("/health", "/healthz"):
            write_json(self, {"ok": True, "provider": provider, "model": current_alias(cfg), "chat": "/ca/chat/health", "plan": "/ca/plan/artifacts", "events": "/ca/events"})
            return
        if path == "/v1/models":
            data = list_model_objects(provider, pcfg)
            write_json(self, {"object": "list", "data": data, "has_more": False})
            return
        if path.startswith("/v1/models/"):
            mid = urllib.parse.unquote(path[len("/v1/models/"):])
            resolved = resolve_requested_model(provider, pcfg, mid)
            write_json(self, model_object(provider, resolved))
            return
        write_json(self, {"type": "error", "error": {"type": "not_found_error", "message": path}}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        cfg = load_config()
        if reject_external_router_request(self, cfg):
            return
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        body = parse_json_body(raw)
        if handle_llm_config_post(self, path, body):
            return
        if handle_channel_mcp_post(self, path, body):
            return
        if handle_chat_post(self, path, body) or handle_plan_post(self, path, body):
            return
        provider, pcfg = get_current_provider(cfg)
        if path == "/v1/messages/count_tokens":
            tokens = estimate_tokens(body)
            write_context_usage(provider, pcfg, body, "count_tokens")
            write_json(self, {"input_tokens": tokens})
            return
        if path != "/v1/messages":
            write_json(self, {"type": "error", "error": {"type": "not_found_error", "message": path}}, 404)
            return
        request_id = f"{os.getpid()}-{time.time_ns()}"
        EVENT_BUS.publish(
            level="info",
            category="router.request",
            message="Anthropic messages request received",
            request_id=request_id,
            provider=provider,
            model=str(body.get("model") or ""),
            data={
                "path": path,
                "messages": len(body.get("messages") or []),
                "tools": len(body.get("tools") or []),
                **router_event_message_preview(body, cfg),
            },
        )
        dump_request_for_trace(provider, path, body)
        if maybe_handle_plan_mode_tool_choice(self, provider, body):
            EVENT_BUS.publish(level="info", category="plan_mode.short_circuit", message="plan mode tool choice handled locally", request_id=request_id, provider=provider, model=str(body.get("model") or ""))
            return
        body = filter_blocked_tools(provider, pcfg, body)
        write_context_usage(provider, pcfg, body, "messages")
        if maybe_handle_router_debug_request(self, body):
            EVENT_BUS.publish(level="info", category="router_debug.short_circuit", message="router debug request handled locally", request_id=request_id, provider=provider, model=str(body.get("model") or ""))
            return
        if maybe_handle_advisor_request(self, provider, pcfg, body):
            EVENT_BUS.publish(level="info", category="advisor.short_circuit", message="advisor request handled locally", request_id=request_id, provider=provider, model=str(body.get("model") or ""))
            return
        router_log("DEBUG", f"POST {path} provider={provider} model={body.get('model')} tools={len(body.get('tools') or [])} msgs={len(body.get('messages') or [])}")
        try:
            if provider in ("ollama", "ollama-cloud"):
                EVENT_BUS.publish(level="info", category="upstream.request", message="forwarding to Ollama-compatible provider", request_id=request_id, provider=provider, model=str(body.get("model") or ""))
                forward_ollama_api_chat(self, provider, pcfg, body)
                return
            if provider == "nvidia-hosted":
                EVENT_BUS.publish(level="info", category="upstream.request", message="forwarding to OpenAI-compatible provider", request_id=request_id, provider=provider, model=str(body.get("model") or ""))
                forward_openai_compatible_chat(self, provider, pcfg, body)
                return
            body = cap_anthropic_body_for_provider(provider, pcfg, body)
            body = apply_provider_request_options(provider, pcfg, body)
            upstream_model = resolve_requested_model(provider, pcfg, body.get("model"))
            if provider == "nvidia-hosted":
                upstream_model = ncp_model_id_for_nvidia_hosted(upstream_model)
            body["model"] = upstream_model
            stream_enabled = bool(pcfg.get("stream_enabled", True))
            word_chunking = bool(pcfg.get("stream_word_chunking", False))
            if not stream_enabled:
                body["stream"] = False
            data = json.dumps(body).encode("utf-8")
            base = provider_upstream_request_base(provider, pcfg)
            url = join_url(base, "/v1/messages")
            headers = provider_headers(provider, pcfg)
            for h in ("anthropic-beta", "anthropic-dangerous-direct-browser-access"):
                if self.headers.get(h):
                    headers[h] = self.headers[h]
            waited, rpm_used, rpm_limit = apply_router_rate_limit(provider, pcfg, upstream_model)
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                EVENT_BUS.publish(level="info", category="upstream.request", message="forwarding to Anthropic-compatible provider", request_id=request_id, provider=provider, model=upstream_model, data={"url": url, "stream": bool(body.get("stream", stream_enabled))})
                resp = urllib.request.urlopen(req, timeout=provider_request_timeout_seconds(pcfg))
                if bool(body.get("stream", stream_enabled)):
                    set_upstream_stream_read_timeout(resp, provider_stream_idle_timeout_seconds(pcfg))
                status = getattr(resp, "status", 200)
                ctype = resp.headers.get("content-type", "application/json")
                if stream_enabled and "text/event-stream" in ctype:
                    self.send_response(status)
                    self.send_header("content-type", ctype)
                    self.send_header("cache-control", "no-cache")
                    self.send_header("connection", "close")
                    self.end_headers()
                    _rebatch_anthropic_sse_text(self, resp, upstream_model, word_chunking=word_chunking)
                else:
                    self.send_response(status)
                    self.send_header("content-type", ctype)
                    self.end_headers()
                    raw_resp = resp.read()
                    notice = rate_limit_notice(waited, rpm_used, rpm_limit, bool(pcfg.get("rate_limit_status", True)))
                    if notice and "application/json" in ctype:
                        try:
                            payload = json.loads(raw_resp.decode("utf-8", errors="replace"))
                            if isinstance(payload, dict):
                                raw_resp = json.dumps(prepend_anthropic_text(payload, notice), ensure_ascii=False).encode("utf-8")
                        except Exception:
                            pass
                    self.wfile.write(raw_resp)
                    self.wfile.flush()
            except urllib.error.HTTPError as e:
                err = e.read()
                EVENT_BUS.publish(level="error", category="upstream.error", message=f"upstream HTTP {e.code}", request_id=request_id, provider=provider, model=upstream_model, data={"status": e.code})
                self.send_response(e.code)
                self.send_header("content-type", e.headers.get("content-type", "application/json"))
                self.end_headers()
                self.wfile.write(err)
        except Exception as exc:
            EVENT_BUS.publish(level="error", category="router.error", message=str(exc), request_id=request_id, provider=provider, model=str(body.get("model") or ""), data={"error_type": type(exc).__name__})
            write_json(self, {"type": "error", "error": {"type": "api_error", "message": str(exc)}}, 500)


def serve(_: argparse.Namespace) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    bind_host = router_bind_host(cfg)
    PID_PATH.write_text(str(os.getpid()))
    os.chmod(PID_PATH, 0o600)
    lvl = current_log_level()
    src = "file" if LOG_LEVEL_PATH.exists() else ("env" if os.environ.get("CLAUDE_ANY_LOG_LEVEL") else "default")
    sys.stderr.write(
        f"claude-any router starting on {bind_host}:{ROUTER_PORT} "
        f"(client base {ROUTER_BASE}, log level {LOG_LEVEL_NAMES.get(lvl, lvl)}, source={src})\n"
    )
    sys.stderr.flush()
    server = ThreadingHTTPServer((bind_host, ROUTER_PORT), RouterHandler)
    try:
        server.serve_forever()
    finally:
        try:
            PID_PATH.unlink()
        except FileNotFoundError:
            pass


def router_up() -> bool:
    try:
        http_json(f"{ROUTER_BASE}/health", timeout=1.0)
        return True
    except Exception:
        return False


def invalid_nvidia_hosted_base_url(value: str | None) -> bool:
    text = (value or "").strip()
    if not text or text.startswith("nv" + "api-") or not text.startswith(("http://", "https://")):
        return True
    parsed = urllib.parse.urlparse(text)
    return (parsed.hostname or "") in ("127.0.0.1", "localhost")


def ensure_nvidia_hosted_base_url(pcfg: dict[str, Any]) -> bool:
    if invalid_nvidia_hosted_base_url(pcfg.get("base_url")):
        pcfg["base_url"] = nvidia_upstream_base_url()
        return True
    return False


def store_nvidia_api_key(key: str) -> None:
    env = read_env_file(NCP_ENV)
    env["NVIDIA_API_KEY"] = key
    env.setdefault("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    env.setdefault("PROXY_HOST", "127.0.0.1")
    env.setdefault("PROXY_PORT", "8788")
    env.setdefault("STORAGE_ENGINE", "sqlite")
    NCP_ENV.parent.mkdir(parents=True, exist_ok=True)
    NCP_ENV.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    os.chmod(NCP_ENV, 0o600)


def set_provider_config(provider: str) -> list[str]:
    cfg = load_config()
    cfg["current_provider"] = provider
    pcfg = cfg["providers"][provider]
    fixed_base = ensure_nvidia_hosted_base_url(pcfg) if provider == "nvidia-hosted" else False
    save_config(cfg)
    clear_model_cache()
    lines = [f"Provider set to {provider} ({PROVIDER_LABELS[provider]})."]
    if fixed_base:
        lines.append(f"Base URL set to {pcfg['base_url']} for NVIDIA hosted.")
    return lines


def set_base_url_config(provider: str, url: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    if provider == "nvidia-hosted" and invalid_nvidia_hosted_base_url(url):
        url = nvidia_upstream_base_url()
    old_url = str(pcfg.get("base_url") or "").rstrip("/")
    new_url = url.rstrip("/")
    pcfg["base_url"] = new_url
    reset_model = old_url != new_url
    if reset_model:
        pcfg["current_model"] = ""
        pcfg["custom_models"] = []
    save_config(cfg)
    clear_model_cache()
    lines = [f"Base URL for {provider} set to {pcfg['base_url']}."]
    if reset_model:
        lines.append("Model selection was reset because the provider endpoint changed.")
    return lines


def set_model_config(value: str) -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    mmap = model_map_for(provider, pcfg)
    model_id = normalize_model_id(provider, unslug_provider_alias(provider, value, mmap) or value)
    pcfg["current_model"] = model_id
    preset = model_preset(model_id)
    if preset.get("num_ctx_min"):
        pcfg["num_ctx_min"] = preset["num_ctx_min"]
    if preset.get("num_ctx_max"):
        pcfg["num_ctx_max"] = preset["num_ctx_max"]
    context_msgs = sync_ollama_library_context_limit(provider, pcfg, model_id)
    context_msgs.extend(cap_context_settings_to_model_capacity(provider, pcfg))
    preset_msgs = auto_apply_recommended_llm_preset_for_model(provider, pcfg, cfg.get("language", "en"))
    timeout_msgs = apply_recommended_timeout_for_model_context(provider, pcfg, use_context_fallback=False)
    known = read_model_list_cache(provider, pcfg) or []
    custom = pcfg.setdefault("custom_models", [])
    if model_id not in custom and model_id not in known:
        custom.append(model_id)
    save_config(cfg)
    clear_model_cache()
    msgs = [f"Model for {provider} set to {model_id}.", f"Claude Code alias: {alias_for(provider, model_id)}"]
    msgs.extend(context_msgs)
    msgs.extend(preset_msgs)
    msgs.extend(timeout_msgs)
    if preset.get("thinking"):
        msgs.append("Note: this is a thinking model; compatibility test uses extended token budget.")
    return msgs


def set_advisor_model_config(value: str) -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    model_id = normalize_model_id(provider, value.strip()) if value.strip() else ""
    pcfg["advisor_model"] = model_id
    if model_id:
        known = read_model_list_cache(provider, pcfg) or []
        custom = pcfg.setdefault("custom_models", [])
        if model_id not in custom and model_id not in known:
            custom.append(model_id)
    save_config(cfg)
    clear_model_cache()
    if not model_id:
        return [f"Advisor Model for {provider} disabled."]
    return [f"Advisor Model for {provider} set to {model_id}."]


def store_api_key_config(provider: str, key: str) -> list[str]:
    if provider == "nvidia-hosted":
        store_nvidia_api_key(key)
        cfg = load_config()
        if ensure_nvidia_hosted_base_url(cfg["providers"][provider]):
            save_config(cfg)
        location = str(NCP_ENV)
    else:
        cfg = load_config()
        cfg["providers"][provider]["api_key"] = key
        save_config(cfg)
        location = str(CONFIG_PATH)
    clear_model_cache()
    return [f"Stored API key for {provider}.", f"Saved: {mask_secret(key)} in {location}"]


def mask_secret(value: str | None) -> str:
    text = value or ""
    if not text:
        return "not set"
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


SECRET_TEXT_PATTERNS = (
    re.compile(r"ak_key_[A-Za-z0-9_-]+_secret_[A-Za-z0-9_-]+"),
    re.compile(r"(AINET_API_KEY\s*=\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(Authorization\s*:\s*Bearer\s+)(\S+)", re.IGNORECASE),
    re.compile(r"(token=)(ak_key_[A-Za-z0-9_-]+_secret_[A-Za-z0-9_-]+)", re.IGNORECASE),
)


def redact_sensitive_text(text: str) -> str:
    redacted = text
    redacted = SECRET_TEXT_PATTERNS[0].sub(lambda m: mask_secret(m.group(0)), redacted)
    for pattern in SECRET_TEXT_PATTERNS[1:]:
        redacted = pattern.sub(lambda m: f"{m.group(1)}{mask_secret(m.group(2))}", redacted)
    return redacted


def redact_sensitive_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [redact_sensitive_obj(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"api_key", "apikey", "token", "authorization", "bearer_token"}:
                redacted[key] = mask_secret(str(item))
            else:
                redacted[key] = redact_sensitive_obj(item)
        return redacted
    return value


def stored_api_key_mask(provider: str, pcfg: dict[str, Any]) -> str:
    if provider == "nvidia-hosted":
        return mask_secret(nvidia_api_key())
    return mask_secret(str(pcfg.get("api_key") or ""))


def read_clipboard_text() -> str:
    commands: list[list[str]] = []
    if os.name == "nt":
        commands.append(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"])
    elif sys.platform == "darwin":
        commands.append(["pbpaste"])
    else:
        commands.extend([["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]])
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
    return ""


def cmd_provider(args: argparse.Namespace) -> None:
    cfg = load_config()
    if not args.name:
        cur = cfg["current_provider"]
        print("Available providers (current: %s)" % cur)
        for i, p in enumerate(PROVIDER_LABELS, 1):
            mark = "*" if p == cur else " "
            base = cfg["providers"][p].get("base_url", "")
            print(f" {mark} {i}. {p:<15} {PROVIDER_LABELS[p]:<16} {base}")
        print("\nUse: /provider <name>")
        print("Example: /provider ollama")
        print("Then run /model to choose a model for the selected provider.")
        return
    provider = normalize_provider(args.name)
    for line in set_provider_config(provider):
        print(line)
    print("Gateway model cache cleared. Run /model to refresh the model picker.")


def cmd_set_api_key(args: argparse.Namespace) -> None:
    provider = normalize_provider(args.provider)
    key = args.key.strip()
    if not key:
        raise SystemExit("No key provided; unchanged.")
    for line in store_api_key_config(provider, key):
        print(line)

def cmd_api_key(args: argparse.Namespace) -> None:
    cfg = load_config()
    if not args.provider:
        print("API key status:")
        for p, pcfg in cfg["providers"].items():
            needs = p in ("anthropic",)
            if p == "nvidia-hosted":
                nenv = read_env_file(NCP_ENV)
                set_ = bool(nenv.get("NVIDIA_API_KEY"))
                print(f" {p:<15} {'set' if set_ else 'missing'} (stored in {NCP_ENV})")
            else:
                set_ = bool(pcfg.get("api_key"))
                label = "set" if set_ else ("missing" if needs else "not required")
                print(f" {p:<15} {label}")
        print("\nSet securely from terminal: claude-anyctl api-key anthropic")
        print("For NVIDIA hosted, use: claude-anyctl api-key nvidia-hosted")
        return
    provider = normalize_provider(args.provider)
    if not sys.stdin.isatty():
        print("For security, do not paste API keys into Claude Code chat.")
        print(f"Run this in the SSH terminal instead: claude-anyctl api-key {provider}")
        return
    key = getpass.getpass(f"API key for {provider}: ").strip()
    if not key:
        raise SystemExit("No key entered; unchanged.")
    for line in store_api_key_config(provider, key):
        print(line)


def cmd_base_url(args: argparse.Namespace) -> None:
    provider = normalize_provider(args.provider)
    for line in set_base_url_config(provider, args.url):
        print(line)


def cmd_model(args: argparse.Namespace) -> None:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    if not args.value:
        print(f"Model menu for {provider} (current: {pcfg.get('current_model')})")
        models = upstream_model_ids(provider, pcfg)
        for i, mid in enumerate(models[:100], 1):
            mark = "*" if mid == pcfg.get("current_model") else " "
            print(f" {mark} {i:>3}. {alias_for(provider, mid)}    [{mid}]")
        if len(models) > 100:
            print(f" ... {len(models) - 100} more")
        print("\nSet direct/custom model with: /set-model MODEL_ID")
        print("Or from terminal: claude-anyctl model MODEL_ID")
        return
    value = " ".join(args.value).strip()
    if value.startswith("add "):
        value = value[4:].strip()
    if not value:
        raise SystemExit("Missing model id")
    for line in set_model_config(value):
        print(line)
    print("Gateway model cache cleared. Run /model to refresh if needed.")


def cmd_advisor_model(args: argparse.Namespace) -> None:
    if not args.value:
        cfg = load_config()
        provider, pcfg = get_current_provider(cfg)
        current = pcfg.get("advisor_model") or "off"
        print(f"Advisor Model for {provider}: {current}")
        print("Set with: claude-anyctl advisor-model deepseek-v4-pro")
        print("Disable with: claude-anyctl advisor-model off")
        return
    value = " ".join(args.value).strip()
    if value.lower() in ("off", "unset", "disable", "disabled", "none", "null"):
        value = ""
    for line in set_advisor_model_config(value):
        print(line)


def cmd_models(args: argparse.Namespace) -> None:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    if args.provider:
        provider = normalize_provider(args.provider)
        pcfg = cfg["providers"][provider]
    models = upstream_model_ids(provider, pcfg)
    print(f"{provider}: {len(models)} models")
    for mid in models:
        print(f"{alias_for(provider, mid)}\t{mid}")


def cmd_ollama_catalog(args: argparse.Namespace) -> None:
    include_contexts = not bool(getattr(args, "no_contexts", False))
    catalog = refresh_ollama_model_catalog(include_contexts=include_contexts, timeout=float(getattr(args, "timeout", 10.0)))
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}
    context_count = 0
    for entry in models.values():
        if isinstance(entry, dict) and isinstance(entry.get("context_windows"), dict) and entry["context_windows"]:
            context_count += 1
    print(f"Ollama catalog saved: {OLLAMA_MODEL_CATALOG_PATH}")
    print(f"API models: {catalog.get('model_count', 0)}")
    print(f"Base models: {len(models)}")
    print(f"Context windows: {context_count}/{len(models)}")


def provider_mode_label(provider: str, pcfg: dict[str, Any]) -> str:
    if native_anthropic_enabled(provider):
        return "anthropic-native"
    if ollama_native_compat_enabled(provider, pcfg):
        return "ollama-native"
    if vllm_native_compat_enabled(provider, pcfg):
        return "vllm-native"
    if nim_native_compat_enabled(provider, pcfg):
        return "nim-native"
    if nvidia_hosted_native_compat_enabled(provider, pcfg):
        return "nvidia-native"
    return "claude-any-router"


def status_lines() -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    mode = provider_mode_label(provider, pcfg)
    direct_native = mode != "claude-any-router"
    return [
        f"provider: {provider}",
        f"language: {cfg.get('language', 'en')}",
        f"mode: {mode}",
        f"base_url: {pcfg.get('base_url')}",
        f"model: {pcfg.get('current_model')}",
        *([f"num_ctx: {ollama_num_ctx_status(pcfg)}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"ollama_options: {ollama_options_status(pcfg)}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"keep_alive: {pcfg.get('keep_alive', 'default')}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"think: {bool(pcfg.get('think', False))}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"request_timeout_ms: {pcfg.get('request_timeout_ms', 'default')}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"stream_idle_timeout_ms: {pcfg.get('stream_idle_timeout_ms', 'auto')}"] if provider in ("ollama", "ollama-cloud") else []),
        *([f"context_window: {pcfg.get('context_window', 'default')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        *([f"context_reserve_tokens: {pcfg.get('context_reserve_tokens', 'default')}"] if provider in ("vllm", "self-hosted-nim") else []),
        *([f"max_output_tokens: {pcfg.get('max_output_tokens', 'default')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        *([f"request_timeout_ms: {pcfg.get('request_timeout_ms', 'default')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        *([f"stream_idle_timeout_ms: {pcfg.get('stream_idle_timeout_ms', 'auto')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        f"claude_model: {current_upstream_model_id(provider, pcfg) if direct_native else current_alias(cfg)}",
        f"log_level: {log_level_status()}",
        f"channels: {channel_status_text(cfg)}",
        f"channel_delivery: {channel_delivery_mode(cfg)}",
        f"router: {'bypassed for native provider compatibility' if direct_native else (('up' if router_up() else 'down') + ' ' + ROUTER_BASE)}",
        f"config: {CONFIG_PATH}",
    ]


def cmd_status(_: argparse.Namespace) -> None:
    print("\n".join(status_lines()))


def cmd_log_level(args: argparse.Namespace) -> None:
    value = getattr(args, "value", None)
    if not value:
        print(f"log_level: {log_level_status()}")
        for numeric in sorted(LOG_LEVEL_NAMES):
            name = LOG_LEVEL_NAMES[numeric]
            mark = "*" if name == log_level_name() else " "
            print(f" {mark} {name:<6} {numeric}")
        print("   DEFAULT reset to environment/default")
        return
    for line in set_log_level_config(str(value)):
        print(line)


def cmd_language(args: argparse.Namespace) -> None:
    cfg = load_config()
    if not args.value:
        current = cfg.get("language", "en")
        print(f"language: {current} ({LANGUAGES.get(current, current)})")
        for code, label in LANGUAGES.items():
            mark = "*" if code == current else " "
            print(f" {mark} {code:<2} {label}")
        return
    value = args.value.strip().lower()
    aliases = {
        "english": "en",
        "korean": "ko",
        "한국어": "ko",
        "japanese": "ja",
        "日本語": "ja",
        "chinese": "zh",
        "中文": "zh",
        "zh-cn": "zh",
        "cn": "zh",
    }
    value = aliases.get(value, value)
    if value not in LANGUAGES:
        raise SystemExit(f"Unknown language: {args.value}\nKnown: {', '.join(LANGUAGES)}")
    cfg["language"] = value
    save_config(cfg)
    print(f"Language set to {value} ({LANGUAGES[value]}).")


def set_web_search_enabled(enabled: bool) -> None:
    cfg = load_config()
    cfg.setdefault("web_search", {})["auto_for_non_native"] = enabled
    save_config(cfg)


def cmd_web_search(args: argparse.Namespace) -> None:
    cfg = load_config()
    web = cfg.setdefault("web_search", {})
    if args.value:
        value = args.value.lower()
        if value in ("on", "enable", "enabled", "true", "1"):
            web["auto_for_non_native"] = True
            save_config(cfg)
        elif value in ("off", "disable", "disabled", "false", "0"):
            web["auto_for_non_native"] = False
            save_config(cfg)
        else:
            raise SystemExit("Use: claude-any web-search on|off|status")
    state = "on" if web.get("auto_for_non_native", True) else "off"
    package = web.get("package", "ddg-mcp-search")
    print(f"web_search: {state}")
    print(f"search_provider: {web.get('provider', 'duckduckgo')}")
    print(f"search_package: {package}")
    print(f"web_fetch: {'on' if web.get('fetch_enabled', True) else 'off'}")
    print(f"fetch_package: {web.get('fetch_package', 'mcp-server-fetch')}")
    print(f"mcp_config: {WEB_TOOLS_MCP_CONFIG}")


def cmd_web_fetch(args: argparse.Namespace) -> None:
    cfg = load_config()
    web = cfg.setdefault("web_search", {})
    if args.value:
        value = args.value.lower()
        if value in ("on", "enable", "enabled", "true", "1"):
            web["fetch_enabled"] = True
            save_config(cfg)
        elif value in ("off", "disable", "disabled", "false", "0"):
            web["fetch_enabled"] = False
            save_config(cfg)
        elif value == "ignore-robots-on":
            web["fetch_ignore_robots_txt"] = True
            save_config(cfg)
        elif value == "ignore-robots-off":
            web["fetch_ignore_robots_txt"] = False
            save_config(cfg)
        else:
            raise SystemExit("Use: claude-any web-fetch on|off|ignore-robots-on|ignore-robots-off")
    print(f"web_fetch: {'on' if web.get('fetch_enabled', True) else 'off'}")
    print(f"fetch_package: {web.get('fetch_package', 'mcp-server-fetch')}")
    print(f"ignore_robots_txt: {bool(web.get('fetch_ignore_robots_txt', False))}")
    print(f"user_agent: {web.get('fetch_user_agent') or 'default'}")
    print(f"mcp_config: {WEB_TOOLS_MCP_CONFIG}")


def channel_specs(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    raw = cfg.setdefault("claude_code", {}).get("channels", [])
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    channels: list[str] = []
    seen: set[str] = set()
    for item in items:
        spec = str(item).strip()
        if not spec or spec in seen:
            continue
        seen.add(spec)
        channels.append(spec)
    return channels


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _path_for_compare(path: Path | str) -> str:
    try:
        return str(Path(path).expanduser().resolve()).replace("\\", "/").rstrip("/").casefold()
    except Exception:
        return str(path).replace("\\", "/").rstrip("/").casefold()


def _project_key_matches_cwd(project_key: str, cwd: Path) -> bool:
    key = str(project_key or "").strip()
    if not key:
        return False
    try:
        project_path = Path(key).expanduser()
    except Exception:
        return False
    if not project_path.is_absolute():
        return False
    project = _path_for_compare(project_path)
    current = _path_for_compare(cwd)
    return current == project or current.startswith(project + "/")


def _mcp_server_names_from_mapping(mapping: Any) -> list[str]:
    if not isinstance(mapping, dict):
        return []
    names: list[str] = []
    for key in ("mcpServers", "servers"):
        servers = mapping.get(key)
        if isinstance(servers, dict):
            names.extend(str(name).strip() for name in servers if str(name).strip())
    return _dedupe_strings(names)


def _mcp_servers_from_mapping(mapping: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(mapping, dict):
        return []
    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for key in ("mcpServers", "servers"):
        servers = mapping.get(key)
        if not isinstance(servers, dict):
            continue
        for raw_name, raw_server in servers.items():
            name = str(raw_name or "").strip()
            if not name or name in seen or not isinstance(raw_server, dict):
                continue
            seen.add(name)
            found.append((name, dict(raw_server)))
    return found


def _read_mcp_server_names_from_json(path: Path, cwd: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    names = _mcp_server_names_from_mapping(data)
    if path.name == ".claude.json" and isinstance(data, dict):
        projects = data.get("projects")
        if isinstance(projects, dict):
            for project_key, project_data in projects.items():
                if _project_key_matches_cwd(str(project_key), cwd):
                    names.extend(_mcp_server_names_from_mapping(project_data))
    return _dedupe_strings(names)


def _read_mcp_servers_from_json(path: Path, cwd: Path) -> list[tuple[str, dict[str, Any]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    servers = _mcp_servers_from_mapping(data)
    if path.name == ".claude.json" and isinstance(data, dict):
        projects = data.get("projects")
        if isinstance(projects, dict):
            for project_key, project_data in projects.items():
                if _project_key_matches_cwd(str(project_key), cwd):
                    servers.extend(_mcp_servers_from_mapping(project_data))
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for name, server in servers:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, server))
    return out


def _mcp_server_is_stdio(server: dict[str, Any]) -> bool:
    if not isinstance(server, dict):
        return False
    server_type = str(server.get("type") or "").strip().lower()
    if server_type and server_type not in ("stdio", "command"):
        return False
    command = resolve_executable_for_subprocess(str(server.get("command") or "").strip())
    if not command:
        return False
    args = [str(item) for item in server.get("args", []) if item is not None] if isinstance(server.get("args", []), list) else []
    return "mcp-proxy" not in args


def _mcp_config_passthrough_values(passthrough: list[str]) -> list[str]:
    values: list[str] = []
    i = 0
    while i < len(passthrough):
        arg = passthrough[i]
        if arg == "--mcp-config":
            i += 1
            while i < len(passthrough) and not passthrough[i].startswith("-"):
                values.append(passthrough[i])
                i += 1
            continue
        if arg.startswith("--mcp-config="):
            value = arg.split("=", 1)[1].strip()
            if value:
                values.append(value)
        i += 1
    return values


def strip_mcp_config_passthrough(passthrough: list[str]) -> list[str]:
    stripped: list[str] = []
    i = 0
    while i < len(passthrough):
        arg = passthrough[i]
        if arg == "--mcp-config":
            i += 1
            while i < len(passthrough) and not passthrough[i].startswith("-"):
                i += 1
            continue
        if arg.startswith("--mcp-config="):
            i += 1
            continue
        stripped.append(arg)
        i += 1
    return stripped


def _safe_mcp_proxy_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return safe[:80] or "server"


def _mcp_config_paths_from_passthrough(passthrough: list[str]) -> list[Path]:
    return [Path(value).expanduser() for value in _mcp_config_passthrough_values(passthrough)]


def claude_mcp_config_paths(passthrough: list[str] | None = None, cwd: Path | None = None, home: Path | None = None) -> list[Path]:
    cwd = cwd or Path.cwd()
    home = home or HOME
    paths: list[Path] = []
    paths.extend(_mcp_config_paths_from_passthrough(passthrough or []))
    current = cwd
    visited: set[str] = set()
    while True:
        key = _path_for_compare(current)
        if key in visited:
            break
        visited.add(key)
        paths.append(current / ".mcp.json")
        if current == current.parent:
            break
        current = current.parent
    paths.extend([
        home / ".mcp.json",
        home / ".claude" / "settings.json",
        home / ".claude.json",
    ])
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = _path_for_compare(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def auto_discovered_mcp_channel_specs(
    passthrough: list[str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> list[str]:
    cwd = cwd or Path.cwd()
    specs: list[str] = []
    for path in claude_mcp_config_paths(passthrough, cwd, home):
        if not path.exists() or not path.is_file():
            continue
        for name in _read_mcp_server_names_from_json(path, cwd):
            if re.search(r"\s", name):
                continue
            specs.append(f"server:{name}" if not is_channel_spec_tagged(name) else name)
    return _dedupe_strings(specs)


def _mcp_sse_servers_from_mapping(mapping: Any) -> list[dict[str, Any]]:
    if not isinstance(mapping, dict):
        return []
    found: list[dict[str, Any]] = []
    for key in ("mcpServers", "servers"):
        servers = mapping.get(key)
        if not isinstance(servers, dict):
            continue
        for raw_name, raw_server in servers.items():
            name = str(raw_name or "").strip()
            if not name or not isinstance(raw_server, dict):
                continue
            url = str(raw_server.get("url") or raw_server.get("endpoint") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            server_type = str(raw_server.get("type") or "").strip().lower()
            if server_type and server_type not in ("sse", "http", "streamable-http"):
                continue
            headers = raw_server.get("headers") if isinstance(raw_server.get("headers"), dict) else {}
            found.append(
                {
                    "name": f"mcp-{name}",
                    "url": url,
                    "headers": {str(k): str(v) for k, v in headers.items() if str(k).strip()},
                    "channel": name,
                    "sender_id": name,
                    "recipient": "all",
                    "mcp": True,
                }
            )
    return found


def _read_mcp_sse_servers_from_json(path: Path, cwd: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    servers = _mcp_sse_servers_from_mapping(data)
    if path.name == ".claude.json" and isinstance(data, dict):
        projects = data.get("projects")
        if isinstance(projects, dict):
            for project_key, project_data in projects.items():
                if _project_key_matches_cwd(str(project_key), cwd):
                    servers.extend(_mcp_sse_servers_from_mapping(project_data))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server in servers:
        key = f"{server.get('name')}|{server.get('url')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(server)
    return out


def auto_start_sse_channels_from_mcp_configs(
    passthrough: list[str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    cwd = cwd or Path.cwd()
    started: list[dict[str, Any]] = []
    for path in claude_mcp_config_paths(passthrough, cwd, home):
        if not path.exists() or not path.is_file():
            continue
        for server in _read_mcp_sse_servers_from_json(path, cwd):
            try:
                status = start_channel_sse_connection(server)
                started.append(status)
                router_log("INFO", f"channel_sse_auto_started name={status.get('name')} url={status.get('url')}")
            except Exception as exc:
                router_log("WARN", f"channel_sse_auto_start_failed path={path} error={type(exc).__name__}: {exc}")
    return started


def channel_specs_for_launch(cfg: dict[str, Any], passthrough: list[str], extra_specs: list[str] | None = None) -> list[str]:
    configured = [spec for spec in channel_specs(cfg) if is_channel_spec_tagged(spec)]
    specs = configured
    if extra_specs:
        specs = [*specs, *extra_specs]
    return _dedupe_strings(spec for spec in specs if is_channel_spec_tagged(spec))


def is_channel_spec_tagged(spec: str) -> bool:
    return spec.startswith("plugin:") or spec.startswith("server:")


def channel_status_text(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    channels = channel_specs(cfg)
    if not channels:
        return "off"
    return f"{len(channels)} channel{'s' if len(channels) != 1 else ''}"


def set_channel_development_enabled(enabled: bool) -> list[str]:
    return ["Channel wake delivery is always enabled by Claude Any."]


def normalize_channel_delivery(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    if text in {"native", "native-channel", "native-channel-bridge", "claude-channel", "claude/native"}:
        return "native"
    if text in {"stdin", "pty", "terminal", "wake", "wake-proxy", "legacy"}:
        return "stdin"
    if text in {"auto", ""}:
        return "native"
    return "native"


def channel_delivery_mode(cfg: dict[str, Any] | None = None) -> str:
    env_value = os.environ.get("CLAUDE_ANY_CHANNEL_DELIVERY")
    if env_value is not None:
        return normalize_channel_delivery(env_value)
    cfg = cfg or load_config()
    return normalize_channel_delivery(cfg.setdefault("claude_code", {}).get("channel_delivery", "native"))


def set_channel_delivery_config(value: Any) -> list[str]:
    mode = normalize_channel_delivery(value)
    cfg = load_config()
    cfg.setdefault("claude_code", {})["channel_delivery"] = mode
    save_config(cfg)
    if mode == "native":
        return ["Channel delivery set to native claude/channel bridge."]
    return ["Channel delivery set to stdin wake proxy."]


def add_channel_spec(spec: str, *, development: bool = False) -> list[str]:
    spec = spec.strip()
    if not spec:
        return ["Channel spec was empty."]
    if not is_channel_spec_tagged(spec):
        return ["Channel spec must start with plugin: or server:."]
    cfg = load_config()
    cc = cfg.setdefault("claude_code", {})
    channels = channel_specs(cfg)
    if spec not in channels:
        channels.append(spec)
    cc["channels"] = channels
    save_config(cfg)
    return [f"Channel added: {spec}."]


def remove_channel_spec(spec: str) -> list[str]:
    cfg = load_config()
    cc = cfg.setdefault("claude_code", {})
    before = channel_specs(cfg)
    after = [item for item in before if item != spec]
    cc["channels"] = after
    save_config(cfg)
    return [f"Channel removed: {spec}." if len(after) != len(before) else f"Channel was not configured: {spec}."]


def clear_channel_specs() -> list[str]:
    cfg = load_config()
    cfg.setdefault("claude_code", {})["channels"] = []
    save_config(cfg)
    return ["Claude Code channels cleared."]


def cmd_channels(args: argparse.Namespace) -> None:
    cfg = load_config()
    values = list(getattr(args, "values", []) or [])
    if not values:
        print(f"channels: {channel_status_text(cfg)}")
        print(f"delivery: {channel_delivery_mode(cfg)}")
        for name, spec in OFFICIAL_CHANNEL_PLUGINS.items():
            mark = "*" if spec in channel_specs(cfg) else " "
            print(f" {mark} {name:<10} {spec}")
        for spec in channel_specs(cfg):
            if spec not in OFFICIAL_CHANNEL_PLUGINS.values():
                print(f" * custom    {spec}")
        return
    head = values[0].strip().lower()
    if head in ("on", "enable", "add"):
        if len(values) < 2:
            raise SystemExit("Usage: claude-any channels add CHANNEL_SPEC")
        for line in add_channel_spec(values[1]):
            print(line)
        return
    if head in ("dev", "development"):
        if len(values) >= 2 and values[1].lower() in ("on", "off", "true", "false", "1", "0"):
            for line in set_channel_development_enabled(True):
                print(line)
            return
        if len(values) < 2:
            raise SystemExit("Usage: claude-any channels add CHANNEL_SPEC")
        for line in add_channel_spec(values[1]):
            print(line)
        return
    if head in ("off", "disable", "remove", "rm"):
        if len(values) < 2:
            raise SystemExit("Usage: claude-any channels remove CHANNEL_SPEC")
        for line in remove_channel_spec(values[1]):
            print(line)
        return
    if head in ("clear", "reset"):
        for line in clear_channel_specs():
            print(line)
        return
    if head in ("delivery", "mode"):
        if len(values) < 2:
            print(f"channel_delivery: {channel_delivery_mode(cfg)}")
            return
        for line in set_channel_delivery_config(values[1]):
            print(line)
        return
    if head in OFFICIAL_CHANNEL_PLUGINS:
        spec = OFFICIAL_CHANNEL_PLUGINS[head]
        if spec in channel_specs(cfg):
            for line in remove_channel_spec(spec):
                print(line)
        else:
            for line in add_channel_spec(spec):
                print(line)
        return
    for line in add_channel_spec(values[0]):
        print(line)


def cmd_channel_delivery(args: argparse.Namespace) -> None:
    value = getattr(args, "value", None)
    if value:
        for line in set_channel_delivery_config(value):
            print(line)
    else:
        print(f"channel_delivery: {channel_delivery_mode()}")


def cmd_ollama_native(args: argparse.Namespace) -> None:
    cfg = load_config()
    pcfg = cfg["providers"]["ollama"]
    if args.value:
        value = args.value.lower()
        if value in ("on", "enable", "enabled", "true", "1"):
            pcfg["native_compat"] = True
            save_config(cfg)
        elif value in ("off", "disable", "disabled", "false", "0"):
            pcfg["native_compat"] = False
            save_config(cfg)
        else:
            raise SystemExit("Use: claude-any ollama-native on|off|status")
    state = "on" if pcfg.get("native_compat", True) else "off"
    print(f"ollama_native_compat: {state}")
    print(f"base_url: {pcfg.get('base_url')}")
    print(f"model: {pcfg.get('current_model')}")
    print("launch_env: ANTHROPIC_BASE_URL=<ollama>, ANTHROPIC_AUTH_TOKEN=ollama, ANTHROPIC_API_KEY=\"\"")


def apply_ollama_option(pcfg: dict[str, Any], token: str) -> None:
    if token.startswith("unset:"):
        key = token.split(":", 1)[1].strip()
        if key in ("num_ctx", "ctx"):
            pcfg["num_ctx"] = "auto"
        elif key in ("num_ctx_min", "ctx_min", "min"):
            pcfg.pop("num_ctx_min", None)
        elif key in ("num_ctx_max", "ctx_max", "max"):
            pcfg.pop("num_ctx_max", None)
        elif key in ("keep_alive", "keepalive"):
            pcfg.pop("keep_alive", None)
        elif key == "think":
            pcfg["think"] = False
        elif key in ("stream", "stream_enabled"):
            pcfg["stream_enabled"] = True
        elif key in ("stream_word_chunking", "word_chunking", "stream_chunk", "stream_words"):
            pcfg["stream_word_chunking"] = False
        elif key in ("stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms"):
            pcfg.pop("stream_idle_timeout_ms", None)
        elif key in ("rate_limit", "rate_limit_rpm", "rpm"):
            pcfg.pop("rate_limit_rpm", None)
        elif key in ("rate_limit_status", "rpm_status"):
            pcfg["rate_limit_status"] = True
        else:
            pcfg.setdefault("ollama_options", {}).pop(key, None)
        return
    if "=" not in token:
        raise SystemExit(f"Expected key=value or unset:key, got: {token}")
    key, raw_value = token.split("=", 1)
    key = key.strip()
    value = parse_config_value(raw_value)
    if key in ("num_ctx", "ctx"):
        if isinstance(value, str) and value.lower() in ("auto", "dynamic"):
            pcfg["num_ctx"] = "auto"
        else:
            fixed = positive_int(value)
            if not fixed:
                raise SystemExit("num_ctx must be auto or a positive integer")
            pcfg["num_ctx"] = fixed
        return
    if key in ("num_ctx_min", "ctx_min", "min"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("num_ctx_min must be a positive integer")
        pcfg["num_ctx_min"] = fixed
        return
    if key in ("num_ctx_max", "ctx_max", "max"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("num_ctx_max must be a positive integer")
        pcfg["num_ctx_max"] = fixed
        return
    if key in ("keep_alive", "keepalive"):
        if value is None:
            pcfg.pop("keep_alive", None)
        else:
            pcfg["keep_alive"] = str(value)
        return
    if key in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("timeout must be a positive integer; values above 10000 are treated as milliseconds")
        pcfg["request_timeout_ms"] = fixed if key.endswith("_ms") or fixed > 10000 else fixed * 1000
        return
    if key in ("stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("stream_idle_timeout_ms must be a positive integer; values above 10000 are treated as milliseconds")
        pcfg["stream_idle_timeout_ms"] = fixed if key.endswith("_ms") or fixed > 10000 else fixed * 1000
        return
    if key in ("max_tokens", "maxtoken", "max_token", "num_predict"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("max_tokens/num_predict must be a positive integer")
        pcfg.setdefault("ollama_options", {})["num_predict"] = fixed
        return
    if key == "think":
        pcfg["think"] = bool(value)
        return
    if key in ("stream", "stream_enabled"):
        pcfg["stream_enabled"] = parse_bool(value, default=True)
        return
    if key in ("stream_word_chunking", "word_chunking", "stream_chunk", "stream_words"):
        pcfg["stream_word_chunking"] = parse_bool(value, default=False)
        return
    if key in ("rate_limit", "rate_limit_rpm", "rpm"):
        fixed = positive_int(value)
        if not fixed:
            if str(value).lower() in ("0", "false", "off", "disable", "disabled", "none", "unset"):
                pcfg["rate_limit_rpm"] = 0
                return
            raise SystemExit("rate_limit_rpm must be a positive integer, or 0 to disable")
        pcfg["rate_limit_rpm"] = fixed
        return
    if key in ("rate_limit_status", "rpm_status"):
        pcfg["rate_limit_status"] = parse_bool(value, default=True)
        return
    opts = pcfg.setdefault("ollama_options", {})
    if value is None:
        opts.pop(key, None)
    else:
        opts[key] = value


def cmd_ollama_options(args: argparse.Namespace) -> None:
    cfg = load_config()
    values = list(getattr(args, "values", []) or [])
    provider = cfg.get("current_provider", "ollama")
    if provider not in ("ollama", "ollama-cloud"):
        provider = "ollama"
    if values:
        try:
            maybe_provider = normalize_provider(values[0])
            if maybe_provider in ("ollama", "ollama-cloud"):
                provider = maybe_provider
                values = values[1:]
        except SystemExit:
            pass
    pcfg = cfg["providers"][provider]
    if values:
        context_changed = any(
            token.split("=", 1)[0].replace("unset:", "").strip() in ("num_ctx", "ctx", "num_ctx_min", "ctx_min", "min", "num_ctx_max", "ctx_max", "max")
            for token in values
        )
        explicit_timeout = any(
            token.split("=", 1)[0].replace("unset:", "").strip() in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms", "stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms")
            for token in values
        )
        for token in values:
            apply_ollama_option(pcfg, token)
        timeout_lines = apply_recommended_timeout_for_model_context(provider, pcfg) if context_changed and not explicit_timeout else []
        save_config(cfg)
        clear_model_cache()
        print(f"Ollama options updated for {provider}.")
        for line in timeout_lines:
            print(line)
    print(f"provider: {provider}")
    print(f"num_ctx: {ollama_num_ctx_status(pcfg)}")
    print(f"keep_alive: {pcfg.get('keep_alive', 'default')}")
    print(f"think: {bool(pcfg.get('think', False))}")
    print(f"request_timeout_ms: {pcfg.get('request_timeout_ms', 'default')}")
    used, limit = router_rate_limit_usage(provider, pcfg)
    if limit is not None:
        print(f"rate_limit_rpm: {limit}")
        if bool(pcfg.get("rate_limit_status", True)):
            suffix = f"{used}/{limit}" if limit > 0 else f"{used}/min (unmanaged)"
            print(f"rpm_used: {suffix}")
    print(f"ollama_options: {ollama_options_status(pcfg)}")
    print("Examples:")
    print("  claude-anyctl ollama-options num_ctx=auto min=32768 max=131072")
    print("  claude-anyctl ollama-options num_ctx=65536 temperature=0.7 top_p=0.8 max_tokens=32768 timeout=300000")
    print("  claude-any --ca-ollama-option temperature=0.7 --ca-ollama-num-ctx 65536")


PROVIDER_OPTION_PROVIDERS = ("anthropic", "vllm", "nvidia-hosted", "self-hosted-nim", "ollama", "ollama-cloud")
PROVIDER_SAMPLING_OPTION_PROVIDERS = ("vllm", "nvidia-hosted", "self-hosted-nim")
PROVIDER_SAMPLING_OPTIONS = ("temperature", "top_p", "top_k")


def sampling_option_key(key: str) -> str | None:
    normalized = key.strip().lower().replace("-", "_")
    aliases = {
        "temp": "temperature",
        "temperature": "temperature",
        "top": "top_p",
        "top_p": "top_p",
        "topp": "top_p",
        "topk": "top_k",
        "top_k": "top_k",
    }
    return aliases.get(normalized)


def validate_sampling_option(key: str, value: Any) -> float | int:
    if key == "temperature":
        fixed = finite_float(value)
        if fixed is None or fixed < 0 or fixed > 2:
            raise SystemExit("temperature must be a number from 0 to 2")
        return fixed
    if key == "top_p":
        fixed = finite_float(value)
        if fixed is None or fixed <= 0 or fixed > 1:
            raise SystemExit("top_p must be a number greater than 0 and up to 1")
        return fixed
    if key == "top_k":
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("top_k must be a positive integer")
        return fixed
    raise SystemExit(f"Unknown provider option: {key}")


def provider_sampling_status(pcfg: dict[str, Any]) -> list[str]:
    return [f"{key}={pcfg.get(key, 'default')}" for key in PROVIDER_SAMPLING_OPTIONS]


def provider_options_status(provider: str, pcfg: dict[str, Any]) -> str:
    timeout = pcfg.get("request_timeout_ms", "default")
    timeout_text = f"{timeout}ms" if timeout != "default" else "default"
    parts = [
        f"max_output_tokens={pcfg.get('max_output_tokens', 'default')}",
        f"timeout={timeout_text}",
    ]
    if pcfg.get("stream_idle_timeout_ms") is not None:
        parts.append(f"stream_idle_timeout={pcfg.get('stream_idle_timeout_ms')}ms")
    if provider in ("nvidia-hosted", "self-hosted-nim", "ollama", "ollama-cloud"):
        parts.append(f"rate_limit_rpm={pcfg.get('rate_limit_rpm', 40)}")
        if bool(pcfg.get("rate_limit_status", True)):
            used, limit = router_rate_limit_usage(provider, pcfg)
            if limit is not None:
                suffix = f"{used}/{limit}" if limit > 0 else f"{used}/min(unmanaged)"
                parts.append(f"rpm_used={suffix}")
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        parts.insert(0, f"context_window={pcfg.get('context_window', 'default')}")
        parts.insert(1, f"reserve={pcfg.get('context_reserve_tokens', 'default')}")
    if provider in ("vllm", "self-hosted-nim"):
        native_default = False if provider == "nvidia-hosted" else True
        parts.append(f"native={bool(pcfg.get('native_compat', native_default))}")
    if provider in PROVIDER_SAMPLING_OPTION_PROVIDERS:
        parts.extend(provider_sampling_status(pcfg))
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim", "ollama", "ollama-cloud"):
        parts.append(f"stream={'on' if bool(pcfg.get('stream_enabled', True)) else 'off'}")
        if bool(pcfg.get("stream_word_chunking", False)):
            parts.append("word_chunk=on")
    return ", ".join(parts)


def llm_options_status(provider: str, pcfg: dict[str, Any]) -> str:
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        pieces = [
            f"ctx {ollama_num_ctx_status(pcfg)}",
            f"keep {pcfg.get('keep_alive', 'default')}",
            f"think {bool(pcfg.get('think', False))}",
            f"timeout {pcfg.get('request_timeout_ms', 'default')}ms",
        ]
        if pcfg.get("stream_idle_timeout_ms") is not None:
            pieces.append(f"stream_idle_timeout={pcfg.get('stream_idle_timeout_ms')}ms")
        for key in ("num_predict", "temperature", "top_p", "top_k"):
            if key in opts:
                pieces.append(f"{key}={opts[key]}")
        return "; ".join(pieces)
    if provider == "anthropic":
        return (
            f"max_output_tokens={pcfg.get('max_output_tokens', 'Claude Code default')}, "
            f"timeout={pcfg.get('request_timeout_ms', 'Claude Code default')}ms"
        )
    if provider in PROVIDER_OPTION_PROVIDERS:
        return provider_options_status(provider, pcfg)
    return "provider defaults"


def model_option_family(provider: str, pcfg: dict[str, Any]) -> str:
    model = str(pcfg.get("current_model") or "").lower()
    if any(marker in model for marker in ("coder", "codegemma", "starcoder", "devstral")):
        return "coding"
    if any(marker in model for marker in ("reason", "thinking", "r1", "qwq")):
        return "reasoning"
    if any(marker in model for marker in ("1m", "v4-pro", "million")):
        return "million-context"
    if any(marker in model for marker in ("70b", "120b", "253b", "405b", "480b", "large", "ultra", "pro")):
        return "large"
    if provider in ("vllm", "self-hosted-nim"):
        server_limit = upstream_model_context_limit(provider, pcfg, timeout=1.5) or 0
        ctx = server_limit or positive_int(pcfg.get("context_window")) or 0
        if ctx >= 524288:
            return "million-context"
        if ctx >= 65536:
            return "long-context"
    if provider in ("ollama", "ollama-cloud"):
        ctx = positive_int(pcfg.get("num_ctx_max")) or positive_int(pcfg.get("num_ctx")) or 0
        if ctx >= 524288:
            return "million-context"
        if ctx >= 65536:
            return "long-context"
    return "general"


def recommended_preset_id(provider: str, pcfg: dict[str, Any]) -> str:
    family = model_option_family(provider, pcfg)
    if family == "reasoning":
        return "reasoning"
    if family == "coding":
        return "coding"
    if family == "million-context":
        return "million-context-1m"
    if family == "long-context":
        return "long-context-65k"
    if family == "large":
        return "balanced"
    return "balanced"


LLM_PRESETS: dict[str, tuple[str, str]] = {
    "balanced": ("Balanced Claude Code", "4K output, stable coding/chat defaults"),
    "coding": ("Coding deterministic", "lower randomness for edits, scripts, reviews"),
    "fast": ("Fast short tasks", "shorter output and timeout for quick jobs"),
    "long-context-65k": ("Long context 65K", "65K context target, 4K output reserve"),
    "million-context-1m": ("Ultra context 1M", "1M context target for high-capacity models"),
    "large-output": ("Large output/report", "larger 8K output for summaries/reports"),
    "reasoning": ("Reasoning model", "reasoning-friendly sampling"),
    "novelist": ("Novelist", "creative prose, voice, scenes, and narrative continuity"),
    "humanities-researcher": ("Humanities researcher", "interpretive research, close reading, and long evidence chains"),
    "mathematician": ("Mathematician", "careful derivations, proofs, and low-randomness reasoning"),
    "product-architect": ("Product architect", "requirements, system structure, tradeoffs, and implementation plans"),
    "teacher": ("Teacher / tutor", "clear explanations, examples, and step-by-step learning"),
}


LLM_PRESET_I18N: dict[str, dict[str, tuple[str, str]]] = {
    "ko": {
        "balanced": ("균형형 Claude Code", "4K 출력, 안정적인 코딩/채팅 기본값"),
        "coding": ("코딩 결정형", "편집, 스크립트, 코드 리뷰용 낮은 무작위성"),
        "fast": ("빠른 짧은 작업", "짧은 출력과 짧은 타임아웃"),
        "long-context-65k": ("긴 컨텍스트 65K", "65K 컨텍스트 목표, 4K 출력 여유"),
        "million-context-1m": ("초장문 컨텍스트 1M", "고용량 모델용 1M 컨텍스트 목표"),
        "large-output": ("긴 출력/리포트", "요약과 리포트용 8K 출력"),
        "reasoning": ("추론 모델", "추론 친화 샘플링"),
        "novelist": ("소설가", "문체, 서사, 장면 전개를 위한 창작 설정"),
        "humanities-researcher": ("인문연구자", "해석, 근거 정리, 긴 문헌 맥락"),
        "mathematician": ("수학자", "낮은 무작위성과 단계적 증명/유도"),
        "product-architect": ("제품 설계자", "요구사항, 구조, 트레이드오프, 구현 계획"),
        "teacher": ("교사/튜터", "쉬운 설명, 예제, 단계별 학습"),
    },
    "ja": {
        "balanced": ("バランス型 Claude Code", "4K 出力、安定したコーディング/チャット既定値"),
        "coding": ("コーディング決定型", "編集、スクリプト、コードレビュー向けの低いランダム性"),
        "fast": ("高速な短い作業", "短い出力と短いタイムアウト"),
        "long-context-65k": ("長いコンテキスト 65K", "65K コンテキスト目標、4K 出力予約"),
        "million-context-1m": ("超長文コンテキスト 1M", "大容量モデル向けの 1M コンテキスト目標"),
        "large-output": ("長い出力/レポート", "要約とレポート向けの 8K 出力"),
        "reasoning": ("推論モデル", "推論向けサンプリング"),
        "novelist": ("小説家", "文体、物語、場面展開向けの創作設定"),
        "humanities-researcher": ("人文学研究者", "解釈、根拠整理、長い文献文脈"),
        "mathematician": ("数学者", "低いランダム性と段階的な証明/導出"),
        "product-architect": ("プロダクト設計者", "要件、構造、トレードオフ、実装計画"),
        "teacher": ("教師/チューター", "分かりやすい説明、例、段階的学習"),
    },
    "zh": {
        "balanced": ("均衡型 Claude Code", "4K 输出，稳定的编码/聊天默认值"),
        "coding": ("编码确定型", "用于编辑、脚本和代码审查的低随机性"),
        "fast": ("快速短任务", "较短输出和较短超时"),
        "long-context-65k": ("长上下文 65K", "65K 上下文目标，4K 输出预留"),
        "million-context-1m": ("超长上下文 1M", "面向高容量模型的 1M 上下文目标"),
        "large-output": ("长输出/报告", "用于摘要和报告的 8K 输出"),
        "reasoning": ("推理模型", "适合推理的采样"),
        "novelist": ("小说家", "面向文风、叙事、场景推进的创作设置"),
        "humanities-researcher": ("人文学研究者", "解释性研究、证据整理和长文献上下文"),
        "mathematician": ("数学家", "低随机性、逐步证明和推导"),
        "product-architect": ("产品架构师", "需求、系统结构、取舍和实现计划"),
        "teacher": ("教师/导师", "清晰解释、示例和分步学习"),
    },
}


TIMEOUT_PRESETS: dict[str, tuple[int, str, str]] = {
    "timeout-fast": (120000, "Fast retry 2m", "short wait, quick retry on stalled providers"),
    "timeout-standard": (300000, "Standard 5m", "balanced wait for normal cloud coding"),
    "timeout-long": (600000, "Long stream 10m", "large edits or slow streamed responses"),
    "timeout-deep": (1200000, "Deep work 20m", "long reasoning, reports, and big context"),
    "timeout-marathon": (3600000, "Marathon 60m", "very long hosted/model-server jobs"),
}


TIMEOUT_PRESET_I18N: dict[str, dict[str, tuple[str, str]]] = {
    "ko": {
        "timeout-fast": ("빠른 재시도 2분", "멈춘 provider를 빨리 감지"),
        "timeout-standard": ("표준 5분", "일반 클라우드 코딩용 균형값"),
        "timeout-long": ("긴 스트림 10분", "큰 편집 또는 느린 스트리밍 응답"),
        "timeout-deep": ("깊은 작업 20분", "긴 추론, 리포트, 큰 컨텍스트"),
        "timeout-marathon": ("장시간 60분", "매우 긴 hosted/model-server 작업"),
    },
    "ja": {
        "timeout-fast": ("高速 retry 2分", "停止した provider を早く検出"),
        "timeout-standard": ("標準 5分", "通常のクラウド coding 向け"),
        "timeout-long": ("長い stream 10分", "大きな編集や遅い streamed 応答"),
        "timeout-deep": ("深い作業 20分", "長い推論、report、大きな context"),
        "timeout-marathon": ("長時間 60分", "非常に長い hosted/model-server 作業"),
    },
    "zh": {
        "timeout-fast": ("快速重试 2分钟", "快速发现卡住的 provider"),
        "timeout-standard": ("标准 5分钟", "普通云端编码的均衡值"),
        "timeout-long": ("长流式 10分钟", "大型编辑或较慢流式响应"),
        "timeout-deep": ("深度工作 20分钟", "长推理、报告和大上下文"),
        "timeout-marathon": ("超长 60分钟", "很长的 hosted/model-server 任务"),
    },
}


LLM_PRESET_TIMEOUT_MS: dict[str, int] = {
    "balanced": DEFAULT_REQUEST_TIMEOUT_MS,
    "coding": DEFAULT_REQUEST_TIMEOUT_MS,
    "fast": 120000,
    "long-context-65k": DEFAULT_REQUEST_TIMEOUT_MS,
    "million-context-1m": 600000,
    "large-output": 600000,
    "reasoning": 1200000,
    "novelist": 600000,
    "humanities-researcher": 1200000,
    "mathematician": 1200000,
    "product-architect": 600000,
    "teacher": 300000,
}


def llm_preset_timeout_ms(preset_id: str) -> int:
    return LLM_PRESET_TIMEOUT_MS.get(preset_id, DEFAULT_REQUEST_TIMEOUT_MS)


def timeout_profile_id_for_ms(ms: int | None) -> str | None:
    if not ms:
        return None
    for preset_id, (preset_ms, _, _) in TIMEOUT_PRESETS.items():
        if ms == preset_ms:
            return preset_id
    return None


def timeout_profile_text(profile_id: str, lang: str | None = None) -> tuple[str, str]:
    lang = lang or load_config().get("language", "en")
    if profile_id == "__custom__":
        return {
            "ko": ("사용자 지정", "직접 입력한 timeout 값"),
            "ja": ("カスタム", "直接入力した timeout 値"),
            "zh": ("自定义", "手动输入的 timeout 值"),
        }.get(lang, ("Custom", "manually entered timeout value"))
    fallback = TIMEOUT_PRESETS[profile_id]
    return TIMEOUT_PRESET_I18N.get(lang, {}).get(profile_id, (fallback[1], fallback[2]))


def timeout_profile_status(pcfg: dict[str, Any], lang: str | None = None) -> str:
    ms = positive_int(pcfg.get("request_timeout_ms")) or DEFAULT_REQUEST_TIMEOUT_MS
    profile_id = timeout_profile_id_for_ms(ms)
    if profile_id:
        label = timeout_profile_text(profile_id, lang)[0]
    else:
        label = timeout_profile_text("__custom__", lang)[0]
    idle = positive_int(pcfg.get("stream_idle_timeout_ms"))
    idle_text = f"; idle {idle}ms" if idle and idle != ms else ""
    return f"{label}; {ms}ms{idle_text}"


def timeout_profile_idle_ms(request_timeout_ms: int) -> int:
    return min(request_timeout_ms, 300000)


def timeout_profile_panel_rows(pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    current_ms = positive_int(pcfg.get("request_timeout_ms")) or DEFAULT_REQUEST_TIMEOUT_MS
    rows = [f"Current timeout: {current_ms} ms = {format_timeout_minutes(current_ms, lang)}"]
    values = ["__info__"]
    current_profile = timeout_profile_id_for_ms(current_ms)
    for profile_id, (ms, _, _) in TIMEOUT_PRESETS.items():
        label, description = timeout_profile_text(profile_id, lang)
        mark = "*" if profile_id == current_profile else " "
        rows.append(f"{mark} {pad_cells(label, 22)} {ms:>7} ms  {description}")
        values.append(profile_id)
    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def apply_timeout_profile_to_provider(pcfg: dict[str, Any], profile_id: str, lang: str | None = None) -> list[str]:
    if profile_id not in TIMEOUT_PRESETS:
        raise SystemExit(f"Unknown timeout preset: {profile_id}")
    ms, _, _ = TIMEOUT_PRESETS[profile_id]
    idle_ms = timeout_profile_idle_ms(ms)
    pcfg["request_timeout_ms"] = ms
    pcfg["stream_idle_timeout_ms"] = idle_ms
    label = timeout_profile_text(profile_id, lang)[0]
    return [f"Timeout preset: {label}", f"request_timeout_ms: {ms}", f"stream_idle_timeout_ms: {idle_ms}"]


def with_preset_timeout_tokens(tokens: list[str], preset_id: str) -> list[str]:
    filtered = [
        token
        for token in tokens
        if not token.startswith(("timeout=", "timeout_ms=", "request_timeout=", "request_timeout_ms=", "stream_idle_timeout=", "stream_idle_timeout_ms="))
    ]
    timeout_ms = llm_preset_timeout_ms(preset_id)
    idle_ms = timeout_profile_idle_ms(timeout_ms)
    filtered.append(f"timeout={timeout_ms}")
    filtered.append(f"stream_idle_timeout_ms={idle_ms}")
    return filtered


CONTEXT_HEAVY_PRESETS = {
    "long-context-65k",
    "million-context-1m",
    "large-output",
    "reasoning",
    "novelist",
    "humanities-researcher",
    "mathematician",
    "product-architect",
    "teacher",
}


def model_context_hint_from_model_id(model_id: str) -> int | None:
    model = (model_id or "").lower()
    if not model:
        return None
    catalog_limit, _, _ = ollama_catalog_context_for_model(model_id)
    if catalog_limit:
        return catalog_limit
    if any(marker in model for marker in ("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4", "v4-pro", "v4-flash", "1m", "million")):
        return 1048576
    if any(marker in model for marker in ("kimi-k2.6", "kimi_k2.6", "kimi2.6", "kimi-k2")):
        return 262144
    if "qwen3.6" in model:
        return 262144
    if "glm-4.7" in model or "glm-5.1" in model:
        return 131072
    if "deepseek-r1" in model or "llama3.3" in model:
        return 131072
    preset = model_preset(model_id)
    return positive_int(preset.get("num_ctx_max"))


def provider_model_context_capacity(provider: str, pcfg: dict[str, Any]) -> int | None:
    model = str(pcfg.get("current_model") or "")
    if provider == "anthropic":
        return None
    if provider == "nvidia-hosted":
        return nvidia_hosted_context_default(model)
    hint = model_context_hint_from_model_id(model)
    if hint:
        return hint
    if provider in ("vllm", "self-hosted-nim"):
        return (
            upstream_model_context_limit(provider, pcfg, timeout=1.0)
            or positive_int(pcfg.get("context_window"))
            or positive_int(pcfg.get("max_model_len"))
        )
    if provider in ("ollama", "ollama-cloud"):
        if ollama_context_model_matches(model, str(pcfg.get("model_context_model") or "")):
            cached = positive_int(pcfg.get("model_context_max"))
            if cached:
                return cached
        return positive_int(pcfg.get("num_ctx_max")) or positive_int(pcfg.get("num_ctx"))
    return positive_int(pcfg.get("context_window")) or positive_int(pcfg.get("max_model_len"))


def cap_context_settings_to_model_capacity(provider: str, pcfg: dict[str, Any]) -> list[str]:
    capacity = provider_model_context_capacity(provider, pcfg)
    if not capacity:
        return []
    messages: list[str] = []
    if provider in ("ollama", "ollama-cloud"):
        maximum = positive_int(pcfg.get("num_ctx_max"))
        if maximum and maximum > capacity:
            pcfg["num_ctx_max"] = capacity
            messages.append(f"Context max capped to selected model limit: {capacity:,} tokens.")
        minimum = positive_int(pcfg.get("num_ctx_min"))
        if minimum and minimum > capacity:
            pcfg["num_ctx_min"] = capacity
        fixed_ctx = positive_int(pcfg.get("num_ctx"))
        if fixed_ctx and fixed_ctx > capacity:
            pcfg["num_ctx"] = capacity
        return messages
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        context_window = positive_int(pcfg.get("context_window"))
        if context_window and context_window > capacity:
            pcfg["context_window"] = capacity
            messages.append(f"Context window capped to selected model limit: {capacity:,} tokens.")
    return messages


def required_context_for_preset(preset_id: str, provider: str | None = None) -> int | None:
    provider = provider or ""
    if preset_id == "million-context-1m":
        return 1048576
    if preset_id == "humanities-researcher":
        return 524288 if provider in ("ollama", "ollama-cloud") else 262144
    if preset_id in ("novelist", "mathematician", "product-architect"):
        return 262144
    if preset_id == "teacher":
        return 131072
    if preset_id == "reasoning":
        return 262144 if provider == "nvidia-hosted" else 131072
    if preset_id == "large-output":
        if provider == "nvidia-hosted":
            return 262144
        if provider in ("ollama", "ollama-cloud"):
            return 131072
        return 65536
    if preset_id == "long-context-65k":
        return 131072 if provider == "nvidia-hosted" else 65536
    return None


def preset_available_for_model(provider: str, pcfg: dict[str, Any], preset_id: str) -> bool:
    required = required_context_for_preset(preset_id, provider)
    if not required:
        return True
    capacity = provider_model_context_capacity(provider, pcfg)
    if not capacity:
        return True
    return required <= capacity


def format_context_tokens(value: int | None) -> str:
    if not value:
        return "unknown"
    if value >= 1024 * 1024 and value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)}M"
    if value >= 1024 and value % 1024 == 0:
        return f"{value // 1024}K"
    return f"{value:,}"


def context_setting_status(provider: str, pcfg: dict[str, Any]) -> str:
    capacity = provider_model_context_capacity(provider, pcfg)
    cap_text = format_context_tokens(capacity)
    if provider in ("ollama", "ollama-cloud"):
        return f"model max {cap_text}; {ollama_num_ctx_status(pcfg)}"
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        window = positive_int(pcfg.get("context_window"))
        reserve = positive_int(pcfg.get("context_reserve_tokens"))
        reserve_text = f"; reserve {format_context_tokens(reserve)}" if reserve else ""
        return f"model max {cap_text}; window {format_context_tokens(window)}{reserve_text}"
    if provider == "anthropic":
        return "managed by Claude Code"
    return f"model max {cap_text}"


def configured_context_window_for_timeout(provider: str, pcfg: dict[str, Any]) -> int | None:
    if provider in ("ollama", "ollama-cloud"):
        return (
            positive_int(pcfg.get("num_ctx_max"))
            or positive_int(pcfg.get("num_ctx"))
            or provider_model_context_capacity(provider, pcfg)
        )
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        return positive_int(pcfg.get("context_window")) or provider_model_context_capacity(provider, pcfg)
    if provider == "anthropic":
        return provider_model_context_capacity(provider, pcfg)
    return provider_model_context_capacity(provider, pcfg)


def recommended_request_timeout_ms(provider: str, pcfg: dict[str, Any], use_context_fallback: bool = True) -> int:
    model = str(pcfg.get("current_model") or "")
    catalog_timeout = ollama_catalog_timeout_for_model(model)
    if catalog_timeout:
        return catalog_timeout
    preset_timeout = positive_int(model_preset(model).get("recommended_timeout_ms"))
    if preset_timeout:
        return preset_timeout
    if not use_context_fallback:
        return DEFAULT_REQUEST_TIMEOUT_MS
    return recommended_timeout_ms_for_context(configured_context_window_for_timeout(provider, pcfg))


def apply_recommended_timeout_for_model_context(
    provider: str,
    pcfg: dict[str, Any],
    use_context_fallback: bool = True,
) -> list[str]:
    timeout_ms = recommended_request_timeout_ms(provider, pcfg, use_context_fallback=use_context_fallback)
    idle_ms = timeout_profile_idle_ms(timeout_ms)
    changed = positive_int(pcfg.get("request_timeout_ms")) != timeout_ms or positive_int(pcfg.get("stream_idle_timeout_ms")) != idle_ms
    pcfg["request_timeout_ms"] = timeout_ms
    pcfg["stream_idle_timeout_ms"] = idle_ms
    context = configured_context_window_for_timeout(provider, pcfg)
    if not changed:
        return []
    return [
        f"Auto timeout: {timeout_ms}ms for context {format_context_tokens(context)}.",
        f"stream_idle_timeout_ms: {idle_ms}",
    ]


def context_mode_values_for_capacity(capacity: int | None) -> dict[str, tuple[int, int, int]]:
    cap = capacity or 131072

    def clamp(value: int) -> int:
        return max(8192, min(cap, value))

    compact = clamp(32768)
    balanced = clamp(65536 if cap <= 131072 else 131072)
    project = clamp(262144 if cap >= 262144 else cap)
    full = clamp(cap)
    return {
        "context-compact": (compact, min(2048, max(1024, compact // 16)), 4096),
        "context-balanced": (balanced, min(4096, max(2048, balanced // 16)), 4096),
        "context-project": (project, min(8192, max(4096, project // 16)), 8192),
        "context-full": (full, min(16384, max(4096, full // 16)), 8192),
    }


def context_setup_text(key: str, lang: str | None = None) -> tuple[str, str]:
    lang = lang or load_config().get("language", "en")
    entries = {
        "en": {
            "context-compact": ("Compact / fast", "small context, faster and cheaper"),
            "context-balanced": ("Balanced", "good default for normal coding sessions"),
            "context-project": ("Large project", "more files/history, slower but safer for big work"),
            "context-full": ("Full model window", "use the selected model's maximum context"),
        },
        "ko": {
            "context-compact": ("컴팩트/빠름", "작은 컨텍스트, 빠르고 가벼움"),
            "context-balanced": ("균형형", "일반 코딩 세션의 권장 기본값"),
            "context-project": ("대형 프로젝트", "파일/히스토리를 더 많이 사용, 큰 작업에 안정적"),
            "context-full": ("모델 최대 컨텍스트", "선택한 모델의 최대 컨텍스트 사용"),
        },
        "ja": {
            "context-compact": ("コンパクト/高速", "小さなコンテキストで高速かつ軽量"),
            "context-balanced": ("バランス", "通常のコーディングセッション向けの既定値"),
            "context-project": ("大規模プロジェクト", "より多くのファイル/履歴を使う大型作業向け"),
            "context-full": ("モデル最大コンテキスト", "選択モデルの最大コンテキストを使用"),
        },
        "zh": {
            "context-compact": ("紧凑/快速", "较小上下文，更快更轻"),
            "context-balanced": ("均衡", "普通编码会话的推荐默认值"),
            "context-project": ("大型项目", "使用更多文件/历史，适合大任务"),
            "context-full": ("模型最大上下文", "使用所选模型的最大上下文"),
        },
    }
    return entries.get(lang, entries["en"]).get(key, entries["en"][key])


def context_setup_panel_rows(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    capacity = provider_model_context_capacity(provider, pcfg)
    rows = [f"Model context capacity: {format_context_tokens(capacity)}"]
    values = ["__info__"]
    if provider == "anthropic":
        rows.append("Claude Code manages Anthropic context automatically.")
        values.append("__info__")
        rows.append(ui_text("back", lang))
        values.append("back")
        return rows, values
    current_window = positive_int(pcfg.get("num_ctx_max" if provider in ("ollama", "ollama-cloud") else "context_window"))
    choices = context_mode_values_for_capacity(capacity)
    ordered_keys = ["context-compact", "context-balanced", "context-project", "context-full"]
    visible_keys: list[str] = []
    seen_windows: set[int] = set()
    for key in reversed(ordered_keys):
        window = choices[key][0]
        if window in seen_windows:
            continue
        seen_windows.add(window)
        visible_keys.append(key)
    for key in reversed(visible_keys):
        window, reserve, output = choices[key]
        label, description = context_setup_text(key, lang)
        mark = "*" if current_window == window else " "
        rows.append(
            f"{mark} {pad_cells(label, 22)} "
            f"{format_context_tokens(window):>6}  out {format_context_tokens(output):>5}  {description}"
        )
        values.append(key)
    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def apply_context_setup_to_provider(provider: str, pcfg: dict[str, Any], mode: str, lang: str | None = None) -> list[str]:
    choices = context_mode_values_for_capacity(provider_model_context_capacity(provider, pcfg))
    if mode not in choices:
        raise SystemExit(f"Unknown context mode: {mode}")
    window, reserve, output = choices[mode]
    label = context_setup_text(mode, lang)[0]
    if provider in ("ollama", "ollama-cloud"):
        pcfg["num_ctx"] = "auto"
        pcfg["num_ctx_max"] = window
        pcfg["num_ctx_min"] = min(window, 32768 if window <= 65536 else 65536)
        pcfg.setdefault("ollama_options", {})["num_predict"] = output
    elif provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        pcfg["context_window"] = window
        pcfg["context_reserve_tokens"] = reserve
        pcfg["max_output_tokens"] = output
    else:
        return ["Context setup is managed by Claude Code for this provider."]
    messages = cap_context_settings_to_model_capacity(provider, pcfg)
    messages.extend(apply_recommended_timeout_for_model_context(provider, pcfg))
    return [
        f"{ui_text('context_setup', lang)}: {label}",
        f"Applied context: {context_setting_status(provider, pcfg)}",
        *messages,
    ]


def apply_context_setup_config(provider: str, mode: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    lines = apply_context_setup_to_provider(provider, pcfg, mode, cfg.get("language", "en"))
    save_config(cfg)
    clear_model_cache()
    return lines


MODEL_FAMILY_I18N: dict[str, dict[str, str]] = {
    "ko": {
        "coding": "코딩",
        "reasoning": "추론",
        "million-context": "1M 컨텍스트",
        "large": "대형 모델",
        "long-context": "긴 컨텍스트",
        "general": "일반",
    },
    "ja": {
        "coding": "コーディング",
        "reasoning": "推論",
        "million-context": "1M コンテキスト",
        "large": "大型モデル",
        "long-context": "長いコンテキスト",
        "general": "汎用",
    },
    "zh": {
        "coding": "编码",
        "reasoning": "推理",
        "million-context": "1M 上下文",
        "large": "大型模型",
        "long-context": "长上下文",
        "general": "通用",
    },
}


def applied_preset_id(provider: str, pcfg: dict[str, Any]) -> str:
    preset_id = str(pcfg.get("llm_preset") or "").strip()
    if preset_id in LLM_PRESETS and preset_available_for_model(provider, pcfg, preset_id):
        return preset_id
    inferred = infer_preset_id_from_options(provider, pcfg)
    if inferred and preset_available_for_model(provider, pcfg, inferred):
        return inferred
    recommended = recommended_preset_id(provider, pcfg)
    if preset_available_for_model(provider, pcfg, recommended):
        return recommended
    return "balanced"


def infer_preset_id_from_options(provider: str, pcfg: dict[str, Any]) -> str | None:
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        num_predict = positive_int(opts.get("num_predict")) or 0
        num_ctx = positive_int(pcfg.get("num_ctx")) or 0
        num_ctx_min = positive_int(pcfg.get("num_ctx_min")) or 0
        num_ctx_max = positive_int(pcfg.get("num_ctx_max")) or 0
        if bool(pcfg.get("think", False)):
            return "reasoning"
        if num_ctx_max >= 524288:
            return "million-context-1m"
        if num_predict >= 8192:
            return "large-output"
        if num_ctx_min >= 65536 or num_ctx_max >= 131072:
            return "long-context-65k"
        if num_ctx and num_ctx <= 32768 and num_predict and num_predict <= 2048:
            return "fast"
        return None
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim", "anthropic"):
        max_output = positive_int(pcfg.get("max_output_tokens")) or 0
        context_window = positive_int(pcfg.get("context_window")) or 0
        if bool(pcfg.get("think", False)):
            return "reasoning"
        if context_window >= 524288:
            return "million-context-1m"
        if max_output >= 8192:
            return "large-output"
        if context_window >= 65536:
            return "long-context-65k"
        if max_output and max_output <= 2048:
            return "fast"
    return None


def llm_preset_text(preset_id: str, lang: str | None = None) -> tuple[str, str]:
    lang = lang or load_config().get("language", "en")
    return LLM_PRESET_I18N.get(lang, {}).get(preset_id, LLM_PRESETS[preset_id])


def model_family_text(family: str, lang: str | None = None) -> str:
    lang = lang or load_config().get("language", "en")
    return MODEL_FAMILY_I18N.get(lang, {}).get(family, family)


def llm_preset_panel_rows(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    recommended = recommended_preset_id(provider, pcfg)
    applied = applied_preset_id(provider, pcfg)
    family = model_option_family(provider, pcfg)
    recommended_label, _ = llm_preset_text(recommended, lang)
    rows = [
        f"{ui_text('model_family', lang)}: {model_family_text(family, lang)}; "
        f"{ui_text('recommended_preset_is', lang)} {recommended_label}"
    ]
    values = ["__info__"]
    for preset_id in LLM_PRESETS:
        if not preset_available_for_model(provider, pcfg, preset_id):
            continue
        label, description = llm_preset_text(preset_id, lang)
        mark = "*" if preset_id == applied else " "
        rows.append(f"{mark} {pad_cells(label, 24)} {description}")
        values.append(preset_id)
    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def apply_llm_preset_to_provider(
    provider: str,
    pcfg: dict[str, Any],
    preset_id: str,
    lang: str | None = None,
    sync_ollama_context: bool = True,
) -> list[str]:
    if preset_id not in LLM_PRESETS:
        raise SystemExit(f"Unknown preset: {preset_id}")
    lang = lang or load_config().get("language", "en")
    label = llm_preset_text(preset_id, lang)[0]
    context_msgs: list[str] = []
    if provider in ("ollama", "ollama-cloud"):
        tokens_by_preset = {
            "balanced": [
                "num_ctx=auto",
                "num_ctx_min=32768",
                "num_ctx_max=65536",
                "num_predict=4096",
                "temperature=0.3",
                "top_p=0.9",
                "top_k=40",
                "think=false",
                "keep_alive=5m",
                "timeout=300000",
            ],
            "coding": [
                "num_ctx=auto",
                "num_ctx_min=32768",
                "num_ctx_max=65536",
                "num_predict=4096",
                "temperature=0.2",
                "top_p=0.8",
                "top_k=40",
                "think=false",
                "keep_alive=5m",
                "timeout=300000",
            ],
            "fast": [
                "num_ctx=32768",
                "num_predict=2048",
                "temperature=0.2",
                "top_p=0.8",
                "top_k=40",
                "think=false",
                "keep_alive=5m",
                "timeout=300000",
            ],
            "long-context-65k": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=131072",
                "num_predict=4096",
                "temperature=0.3",
                "top_p=0.9",
                "top_k=40",
                "think=false",
                "keep_alive=10m",
                "timeout=300000",
            ],
            "million-context-1m": [
                "num_ctx=auto",
                "num_ctx_min=262144",
                "num_ctx_max=1048576",
                "num_predict=8192",
                "temperature=0.3",
                "top_p=0.9",
                "top_k=40",
                "think=false",
                "keep_alive=15m",
                "timeout=300000",
            ],
            "large-output": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=131072",
                "num_predict=8192",
                "temperature=0.3",
                "top_p=0.9",
                "top_k=40",
                "think=false",
                "keep_alive=10m",
                "timeout=300000",
            ],
            "reasoning": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=131072",
                "num_predict=4096",
                "temperature=0.6",
                "top_p=0.95",
                "top_k=40",
                "think=true",
                "keep_alive=10m",
                "timeout=300000",
            ],
            "novelist": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=262144",
                "num_predict=8192",
                "temperature=0.85",
                "top_p=0.95",
                "top_k=80",
                "think=false",
                "keep_alive=10m",
                "timeout=300000",
            ],
            "humanities-researcher": [
                "num_ctx=auto",
                "num_ctx_min=131072",
                "num_ctx_max=524288",
                "num_predict=8192",
                "temperature=0.45",
                "top_p=0.9",
                "top_k=50",
                "think=false",
                "keep_alive=15m",
                "timeout=300000",
            ],
            "mathematician": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=262144",
                "num_predict=8192",
                "temperature=0.15",
                "top_p=0.85",
                "top_k=40",
                "think=true",
                "keep_alive=15m",
                "timeout=300000",
            ],
            "product-architect": [
                "num_ctx=auto",
                "num_ctx_min=65536",
                "num_ctx_max=262144",
                "num_predict=8192",
                "temperature=0.25",
                "top_p=0.85",
                "top_k=40",
                "think=false",
                "keep_alive=10m",
                "timeout=300000",
            ],
            "teacher": [
                "num_ctx=auto",
                "num_ctx_min=32768",
                "num_ctx_max=131072",
                "num_predict=6144",
                "temperature=0.55",
                "top_p=0.9",
                "top_k=60",
                "think=false",
                "keep_alive=10m",
                "timeout=300000",
            ],
        }
        for token in with_preset_timeout_tokens(tokens_by_preset[preset_id], preset_id):
            apply_ollama_option(pcfg, token)
        model_id = str(pcfg.get("current_model") or "").strip()
        if model_id and sync_ollama_context:
            context_msgs = sync_ollama_library_context_limit(provider, pcfg, model_id)
    elif provider == "anthropic":
        tokens_by_preset = {
            "balanced": ["max_output_tokens=4096", "timeout=300000"],
            "coding": ["max_output_tokens=4096", "timeout=300000"],
            "fast": ["max_output_tokens=2048", "timeout=300000"],
            "long-context-65k": ["max_output_tokens=4096", "timeout=300000"],
            "million-context-1m": ["max_output_tokens=8192", "timeout=300000"],
            "large-output": ["max_output_tokens=8192", "timeout=300000"],
            "reasoning": ["max_output_tokens=4096", "timeout=300000"],
            "novelist": ["max_output_tokens=8192", "timeout=300000"],
            "humanities-researcher": ["max_output_tokens=8192", "timeout=300000"],
            "mathematician": ["max_output_tokens=8192", "timeout=300000"],
            "product-architect": ["max_output_tokens=8192", "timeout=300000"],
            "teacher": ["max_output_tokens=6144", "timeout=300000"],
        }
        for token in with_preset_timeout_tokens(tokens_by_preset[preset_id], preset_id):
            apply_provider_option(provider, pcfg, token)
    else:
        native_default = "false" if provider == "nvidia-hosted" else "true"
        server_limit = upstream_model_context_limit(provider, pcfg) if provider in ("vllm", "self-hosted-nim") else None
        if provider == "nvidia-hosted":
            tokens_by_preset = {
                "balanced": [
                    "context_window=65536",
                    "reserve=4096",
                    "max_output_tokens=4096",
                    "timeout=300000",
                    "temperature=0.3",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "coding": [
                    "context_window=65536",
                    "reserve=4096",
                    "max_output_tokens=4096",
                    "timeout=300000",
                    "temperature=0.2",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "fast": [
                    "context_window=65536",
                    "reserve=2048",
                    "max_output_tokens=2048",
                    "timeout=300000",
                    "temperature=0.2",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "long-context-65k": [
                    "context_window=131072",
                    "reserve=8192",
                    "max_output_tokens=4096",
                    "timeout=300000",
                    "temperature=0.3",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "million-context-1m": [
                    "context_window=1048576",
                    "reserve=16384",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.3",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "large-output": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.3",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "reasoning": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=4096",
                    "timeout=300000",
                    "temperature=0.6",
                    "unset:top_p",
                    "unset:top_k",
                ],
                "novelist": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.85",
                    "top_p=0.95",
                    "top_k=80",
                ],
                "humanities-researcher": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.45",
                    "top_p=0.9",
                    "top_k=50",
                ],
                "mathematician": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.15",
                    "top_p=0.85",
                    "top_k=40",
                ],
                "product-architect": [
                    "context_window=262144",
                    "reserve=8192",
                    "max_output_tokens=8192",
                    "timeout=300000",
                    "temperature=0.25",
                    "top_p=0.85",
                    "top_k=40",
                ],
                "teacher": [
                    "context_window=131072",
                    "reserve=4096",
                    "max_output_tokens=6144",
                    "timeout=300000",
                    "temperature=0.55",
                    "top_p=0.9",
                    "top_k=60",
                ],
            }
        else:
            tokens_by_preset = {
            "balanced": [
                "context_window=32768",
                "reserve=2048",
                "max_output_tokens=4096",
                "timeout=300000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "coding": [
                "context_window=32768",
                "reserve=2048",
                "max_output_tokens=4096",
                "timeout=300000",
                "temperature=0.2",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "fast": [
                "context_window=32768",
                "reserve=1024",
                "max_output_tokens=2048",
                "timeout=300000",
                "temperature=0.2",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "long-context-65k": [
                "context_window=65536",
                "reserve=4096",
                "max_output_tokens=4096",
                "timeout=300000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "million-context-1m": [
                "context_window=1048576",
                "reserve=16384",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "large-output": [
                "context_window=65536",
                "reserve=4096",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "reasoning": [
                "context_window=65536",
                "reserve=4096",
                "max_output_tokens=4096",
                "timeout=300000",
                "temperature=0.6",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "novelist": [
                "context_window=262144",
                "reserve=8192",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.85",
                "top_p=0.95",
                "top_k=80",
                f"native={native_default}",
            ],
            "humanities-researcher": [
                "context_window=262144",
                "reserve=8192",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.45",
                "top_p=0.9",
                "top_k=50",
                f"native={native_default}",
            ],
            "mathematician": [
                "context_window=262144",
                "reserve=8192",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.15",
                "top_p=0.85",
                "top_k=40",
                f"native={native_default}",
            ],
            "product-architect": [
                "context_window=262144",
                "reserve=8192",
                "max_output_tokens=8192",
                "timeout=300000",
                "temperature=0.25",
                "top_p=0.85",
                "top_k=40",
                f"native={native_default}",
            ],
            "teacher": [
                "context_window=131072",
                "reserve=4096",
                "max_output_tokens=6144",
                "timeout=300000",
                "temperature=0.55",
                "top_p=0.9",
                "top_k=60",
                f"native={native_default}",
            ],
            }
        for token in with_preset_timeout_tokens(tokens_by_preset[preset_id], preset_id):
            if provider == "nvidia-hosted" and token.startswith("native="):
                continue
            apply_provider_option(provider, pcfg, token)
        if server_limit:
            requested_context = positive_int(pcfg.get("context_window"))
            if requested_context and requested_context > server_limit:
                pcfg["context_window"] = server_limit
                if server_limit <= 32768:
                    pcfg["max_output_tokens"] = min(positive_int(pcfg.get("max_output_tokens")) or 2048, 2048)
                else:
                    pcfg["max_output_tokens"] = min(positive_int(pcfg.get("max_output_tokens")) or 4096, max(1024, server_limit // 8))
    context_msgs.extend(cap_context_settings_to_model_capacity(provider, pcfg))
    context_msgs.extend(apply_recommended_timeout_for_model_context(provider, pcfg))
    pcfg["llm_preset"] = preset_id
    family = model_option_family(provider, pcfg)
    lines = [
        f"{ui_text('apply_preset', lang)}: {label}",
        f"Provider: {provider}; {ui_text('model_family', lang)}: {model_family_text(family, lang)}",
    ]
    lines.extend(context_msgs)
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        server_limit = upstream_model_context_limit(provider, pcfg)
        required_context = required_context_for_preset(preset_id, provider) or 65536
        if server_limit:
            lines.append(f"Server max_model_len: {server_limit}")
            if preset_id in CONTEXT_HEAVY_PRESETS and server_limit < required_context:
                lines.append(f"This preset requires restarting the server with --max-model-len {required_context} or higher.")
                lines.append("Client settings were capped to the server-reported context length.")
        elif preset_id in CONTEXT_HEAVY_PRESETS:
            lines.append("Could not verify server max_model_len; vLLM/NIM must be started with a matching context limit.")
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        lines.append(
            "Applied options: "
            f"context_window={pcfg.get('context_window', 'default')}, "
            f"reserve={pcfg.get('context_reserve_tokens', 'default')}, "
            f"max_output_tokens={pcfg.get('max_output_tokens', 'default')}, "
            f"timeout={pcfg.get('request_timeout_ms', 'default')}ms"
        )
    elif provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        lines.append(
            "Applied options: "
            f"num_ctx={ollama_num_ctx_status(pcfg)}, "
            f"num_predict={opts.get('num_predict', 'default')}, "
            f"timeout={pcfg.get('request_timeout_ms', 'default')}ms"
        )
    elif provider == "anthropic":
        lines.append(
            "Applied options: "
            f"max_output_tokens={pcfg.get('max_output_tokens', 'default')}, "
            f"timeout={pcfg.get('request_timeout_ms', 'default')}ms"
        )
    return lines


def auto_apply_recommended_llm_preset_for_model(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> list[str]:
    preset_id = recommended_preset_id(provider, pcfg)
    if not preset_available_for_model(provider, pcfg, preset_id):
        return []
    label = llm_preset_text(preset_id, lang)[0]
    lines = [f"Auto-applied recommended LLM preset for selected model: {label}."]
    lines.extend(apply_llm_preset_to_provider(provider, pcfg, preset_id, lang, sync_ollama_context=False))
    return lines


def apply_auto_llm_options_config(model_id: str | None = None) -> list[str]:
    if model_id and model_id.strip():
        return set_model_config(model_id.strip())
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    model = str(pcfg.get("current_model") or "").strip()
    if model:
        context_msgs = sync_ollama_library_context_limit(provider, pcfg, model)
        context_msgs.extend(cap_context_settings_to_model_capacity(provider, pcfg))
    else:
        context_msgs = []
    preset_id = recommended_preset_id(provider, pcfg)
    if not preset_available_for_model(provider, pcfg, preset_id):
        preset_id = applied_preset_id(provider, pcfg)
    label = llm_preset_text(preset_id, cfg.get("language", "en"))[0]
    lines = [f"Auto LLM options applied for {provider}{f' model {model}' if model else ''}: {label}."]
    lines.extend(context_msgs)
    lines.extend(apply_llm_preset_to_provider(provider, pcfg, preset_id, cfg.get("language", "en")))
    save_config(cfg)
    clear_model_cache()
    return lines


def apply_llm_preset_config(provider: str, preset_id: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    lines = apply_llm_preset_to_provider(provider, pcfg, preset_id, cfg.get("language", "en"))
    save_config(cfg)
    clear_model_cache()
    return lines


LLM_OPTION_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "preset": {
        "en": "Apply a bundled LLM preset (output tokens, sampling, timeout) tuned for this provider/model family.",
        "ko": "현재 provider/모델 계열에 맞춘 LLM 프리셋(출력 토큰, 샘플링, 타임아웃)을 한 번에 적용합니다.",
        "ja": "現在のprovider/モデル系列向けに調整されたLLMプリセット(出力トークン、サンプリング、タイムアウト)を一括適用します。",
        "zh": "应用为当前 provider/模型系列调优的 LLM 预设（输出 token、采样、超时）。",
    },
    "context_setup": {
        "en": "Begin here: choose how much of the selected model's context window claude-any may use. Larger windows read more files/history but cost more time and provider quota.",
        "ko": "처음엔 여기부터 설정하세요. 선택한 모델의 컨텍스트 창을 claude-any가 얼마나 사용할지 고릅니다. 클수록 파일/히스토리를 더 많이 읽지만 느리고 provider 한도를 더 씁니다.",
        "ja": "まずここから設定します。選択モデルのコンテキスト窓をclaude-anyがどれだけ使うかを選びます。大きいほど多くのファイル/履歴を読めますが、遅くなりprovider枠を使います。",
        "zh": "先从这里设置：选择 claude-any 可使用所选模型多少上下文窗口。越大可读更多文件/历史，但更慢并消耗 provider 配额。",
    },
    "num_ctx": {
        "en": "Ollama context window (num_ctx). Use 'auto' to size per-request between min/max, or a fixed integer like 65536.",
        "ko": "Ollama 컨텍스트 창(num_ctx). auto 면 요청 크기에 따라 min/max 사이에서 자동 선택, 또는 65536 같은 고정 정수.",
        "ja": "Ollamaのコンテキスト窓(num_ctx)。autoでmin/max間を要求毎に自動選択、または65536のような固定整数を指定。",
        "zh": "Ollama 上下文窗口（num_ctx）。auto 在 min/max 间按请求自动选择，或填固定整数如 65536。",
    },
    "num_ctx_min": {
        "en": "Lower bound when num_ctx is auto. Small requests will not go below this value.",
        "ko": "num_ctx=auto일 때 사용할 최소 컨텍스트. 작은 요청도 이 값보다 작게 내려가지 않습니다.",
        "ja": "num_ctx=auto時の最小コンテキスト。小さな要求でもこの値未満にはなりません。",
        "zh": "num_ctx=auto 时的下限。小请求也不会低于此值。",
    },
    "num_ctx_max": {
        "en": "Upper bound when num_ctx is auto. Keep at or below the real server context limit.",
        "ko": "num_ctx=auto일 때 사용할 최대 컨텍스트. 실제 서버 한계 이하로 두세요.",
        "ja": "num_ctx=auto時の最大コンテキスト。実サーバー上限以下にしてください。",
        "zh": "num_ctx=auto 时的上限。应不高于真实服务器上下文上限。",
    },
    "num_predict": {
        "en": "Ollama max output tokens (num_predict). Input + reserved output must fit inside num_ctx.",
        "ko": "Ollama 최대 출력 토큰(num_predict). 입력 + 예약 출력이 num_ctx 안에 들어가야 합니다.",
        "ja": "Ollamaの最大出力トークン(num_predict)。入力と予約出力はnum_ctxの中に収まる必要があります。",
        "zh": "Ollama 最大输出 token（num_predict）。输入加预留输出必须放进 num_ctx。",
    },
    "max_output_tokens": {
        "en": "Max output tokens passed to Claude Code (CLAUDE_CODE_MAX_OUTPUT_TOKENS) and used as the router cap.",
        "ko": "Claude Code에 전달되는 최대 출력 토큰(CLAUDE_CODE_MAX_OUTPUT_TOKENS)이자 라우터 출력 상한.",
        "ja": "Claude Codeへ渡す最大出力トークン(CLAUDE_CODE_MAX_OUTPUT_TOKENS)であり、ルーター出力上限としても使われます。",
        "zh": "传给 Claude Code 的最大输出 token（CLAUDE_CODE_MAX_OUTPUT_TOKENS），同时作为路由器输出上限。",
    },
    "context_window": {
        "en": "vLLM/NIM context window used by claude-any caps. Native mode cannot raise the real server limit.",
        "ko": "claude-any 라우터가 사용하는 vLLM/NIM 컨텍스트 값. native 모드에서는 실제 서버 한계를 늘릴 수 없습니다.",
        "ja": "claude-anyルーターが使うvLLM/NIMコンテキスト値。nativeモードでは実サーバー上限は超えられません。",
        "zh": "claude-any 路由器使用的 vLLM/NIM 上下文值。native 模式无法提高真实服务器上限。",
    },
    "context_reserve_tokens": {
        "en": "Tokens reserved for the input side when claude-any caps max_tokens. Ignored by direct native requests.",
        "ko": "claude-any가 max_tokens를 줄일 때 입력 쪽 여유로 남기는 토큰. direct native 요청에는 적용되지 않습니다.",
        "ja": "claude-anyがmax_tokensを制限する時に入力側へ残す余裕。direct native要求では無視されます。",
        "zh": "claude-any 限制 max_tokens 时为输入侧预留的 token。direct native 请求会忽略。",
    },
    "request_timeout_ms": {
        "en": "Upstream wait timeout in milliseconds.",
        "ko": "업스트림 응답 대기 시간(ms).",
        "ja": "上流応答待ちタイムアウト(ms)。",
        "zh": "上游响应等待超时（毫秒）。",
    },
    "timeout_profile": {
        "en": "Choose a timeout preset. It sets both upstream wait timeout and stream idle timeout.",
        "ko": "타임아웃 프리셋을 선택합니다. 업스트림 대기 시간과 스트림 idle timeout을 함께 설정합니다.",
        "ja": "timeout preset を選びます。上流待機 timeout と stream idle timeout を同時に設定します。",
        "zh": "选择 timeout 预设，同时设置上游等待超时和 stream idle timeout。",
    },
    "stream_idle_timeout_ms": {
        "en": "Maximum silence allowed while a stream is open. If no bytes arrive for this long, claude-any retries or reports a timeout.",
        "ko": "스트림 연결이 열린 뒤 아무 byte도 오지 않아도 기다리는 최대 시간입니다. 이 시간을 넘으면 재시도하거나 timeout으로 처리합니다.",
        "ja": "stream 接続中に byte が来ないまま待つ最大時間です。超えると retry または timeout として扱います。",
        "zh": "流式连接打开后允许无字节到达的最长时间；超过后重试或作为 timeout 处理。",
    },
    "rate_limit_rpm": {
        "en": "Router-side upstream request limit per minute. NIM hosted defaults to 40 RPM; unset/0 disables waiting.",
        "ko": "라우터가 업스트림 요청 수를 분당 제한합니다. NIM hosted 기본값은 40 RPM입니다. unset/0이면 대기하지 않습니다.",
        "ja": "ルーター側の上流リクエスト数/分の制限。NIM hosted は既定で 40 RPM。unset/0 で待機なし。",
        "zh": "路由器侧上游每分钟请求限制。NIM hosted 默认 40 RPM；unset/0 表示不等待。",
    },
    "rate_limit_status": {
        "en": "Show optional colored RPM usage status in Claude responses.",
        "ko": "Claude 응답에 RPM 사용량 상태를 색상 텍스트로 표시합니다.",
        "ja": "Claude応答にRPM使用量状態を色付きテキストで表示します。",
        "zh": "在 Claude 响应中显示彩色 RPM 使用量状态。",
    },
    "temperature": {
        "en": "Sampling temperature (0..2). Higher is more varied; lower is more deterministic.",
        "ko": "샘플링 temperature (0~2). 높을수록 다양, 낮을수록 결정적.",
        "ja": "サンプリングtemperature (0〜2)。高いほど多様、低いほど決定的。",
        "zh": "采样 temperature（0..2）。越高越多样，越低越确定。",
    },
    "top_p": {
        "en": "Nucleus sampling top_p (0..1). Lower restricts token choices; 0.8 is a moderate default.",
        "ko": "누적 확률 top_p (0~1). 낮을수록 후보 토큰을 좁힘. 0.8 정도가 적당한 기본값.",
        "ja": "nucleus samplingのtop_p (0〜1)。低いほど候補を絞ります。0.8は中程度の既定値。",
        "zh": "nucleus 采样 top_p（0..1）。越低候选越窄；0.8 是中等默认值。",
    },
    "top_k": {
        "en": "Top-K sampling cutoff. Smaller values pick from a tighter token shortlist.",
        "ko": "Top-K 샘플링. 값이 작을수록 후보 토큰 집합이 좁아집니다.",
        "ja": "Top-Kサンプリング。値が小さいほど候補集合は狭くなります。",
        "zh": "Top-K 采样。值越小候选集合越窄。",
    },
    "think": {
        "en": "Toggle Ollama 'think' output. Claude Code may not display provider-specific thinking cleanly.",
        "ko": "Ollama thinking 출력 여부. Claude Code가 provider별 thinking을 항상 깔끔히 표시하지는 않습니다.",
        "ja": "Ollama thinking出力を切り替えます。Claude Code側で常に綺麗に表示されるとは限りません。",
        "zh": "切换 Ollama thinking 输出。Claude Code 不一定能完整显示。",
    },
    "keep_alive": {
        "en": "How long Ollama keeps the model loaded after a request. Longer reduces reloads but holds memory.",
        "ko": "요청 후 Ollama가 모델을 메모리에 유지하는 시간. 길수록 재로딩은 줄지만 메모리를 더 잡습니다.",
        "ja": "要求後にOllamaがモデルを保持する時間。長いほど再読み込みは減りますがメモリを保持します。",
        "zh": "请求后 Ollama 保持模型加载的时间。越长减少重载，但占用内存更久。",
    },
    "native_compat": {
        "en": "Use direct Anthropic-compatible /v1/messages on this provider. Off routes through claude-any's translator.",
        "ko": "이 provider의 Anthropic-호환 /v1/messages에 직접 연결합니다. off 면 claude-any 라우터를 거칩니다.",
        "ja": "このproviderのAnthropic互換/v1/messagesに直接接続します。offだとclaude-anyルーターを経由します。",
        "zh": "对该 provider 直接走 Anthropic 兼容 /v1/messages；关闭则经由 claude-any 路由器转换。",
    },
    "stream_enabled": {
        "en": "Toggle streaming. Off forces stream:false upstream and returns the full response, useful when SSE fragmentation causes tool-call/JSON parse errors.",
        "ko": "스트리밍 on/off. off면 업스트림에 stream:false를 강제하고 응답 전체를 받습니다. SSE 단편화로 tool-call/JSON 파싱이 실패할 때 유용합니다.",
        "ja": "ストリーミングを切り替えます。offにすると上流にstream:falseを強制し、応答全体を返します。SSE断片化でtool-call/JSONが失敗する時に有効です。",
        "zh": "切换流式输出。off 时强制对上游 stream:false 并返回完整响应；用于 SSE 分片导致的 tool-call/JSON 解析失败。",
    },
    "stream_word_chunking": {
        "en": "Buffer text deltas at whitespace/word boundaries before flushing the SSE event. Tool deltas pass through unchanged.",
        "ko": "텍스트 delta를 공백/단어 경계까지 모아서 SSE 이벤트로 전송. tool delta는 그대로 통과합니다.",
        "ja": "テキストdeltaを空白/単語境界までバッファしてSSEイベントを送信します。tool deltaはそのまま透過します。",
        "zh": "在空白/单词边界处合并文本 delta 后发送 SSE 事件。工具 delta 原样透传。",
    },
    "router_debug_external_access": {
        "en": "Expose the router UI/API to non-local clients for debugging. Off denies external clients and next launch binds locally unless environment overrides it.",
        "ko": "디버깅을 위해 라우터 UI/API를 외부 클라이언트에 노출합니다. off면 외부 요청을 차단하고 다음 실행부터 환경값이 없으면 로컬에만 바인딩합니다.",
        "ja": "デバッグ用にルーター UI/API を外部クライアントへ公開します。off では外部リクエストを拒否し、次回起動時は環境変数がなければローカルのみで bind します。",
        "zh": "为了调试向外部客户端暴露路由器 UI/API。关闭时会拒绝外部请求；下次启动在没有环境变量覆盖时仅绑定本地。",
    },
    "router_debug_message_preview_chars": {
        "en": "When greater than 0, include the first N characters of the latest user message in router event data for debugging. Keep 0 for privacy.",
        "ko": "0보다 크면 디버깅용 이벤트 data에 최근 사용자 메시지 앞 N자를 포함합니다. 개인정보 보호를 위해 기본값은 0입니다.",
        "ja": "0より大きい場合、デバッグ用イベントdataに直近ユーザーメッセージの先頭N文字を含めます。プライバシー保護のため既定値は0です。",
        "zh": "大于0时，在调试事件data中包含最近用户消息的前N个字符。为保护隐私默认值为0。",
    },
    "back": {
        "en": "Return to the main menu.",
        "ko": "메인 메뉴로 돌아갑니다.",
        "ja": "メインメニューに戻ります。",
        "zh": "返回主菜单。",
    },
}


def llm_option_description(provider: str, key: str, lang: str | None = None) -> str:
    lang = lang or load_config().get("language", "en")
    entry = LLM_OPTION_DESCRIPTIONS.get(key)
    if not entry:
        return ""
    return entry.get(lang) or entry.get("en", "")


def format_timeout_minutes(ms: int, lang: str = "en") -> str:
    seconds = ms / 1000
    minutes = seconds / 60
    labels = {
        "ko": "분",
        "ja": "分",
        "zh": "分钟",
    }
    label = labels.get(lang, "minutes")
    if abs(minutes - round(minutes)) < 0.01:
        return f"{int(round(minutes))}{label if lang in labels else ' ' + label}"
    return f"{minutes:.1f}{label if lang in labels else ' ' + label}"


def llm_option_description_for_value(provider: str, pcfg: dict[str, Any], key: str, lang: str | None = None) -> str:
    text = llm_option_description(provider, key, lang)
    if key not in ("request_timeout_ms", "stream_idle_timeout_ms"):
        return text
    value = positive_int(pcfg.get(key))
    if not value:
        return text
    lang = lang or load_config().get("language", "en")
    suffix = {
        "ko": f" 현재값: {value} ms = {format_timeout_minutes(value, lang)}.",
        "ja": f" 現在値: {value} ms = {format_timeout_minutes(value, lang)}.",
        "zh": f" 当前值：{value} ms = {format_timeout_minutes(value, lang)}。",
    }.get(lang, f" Current value: {value} ms = {format_timeout_minutes(value, lang)}.")
    return text + suffix


# Boolean keys whose Enter handler should flip on/off in place instead of
# prompting for a value. Covers both on/off labels (stream_*) and True/False
# labels (native_compat, think).
LLM_OPTION_TOGGLE_KEYS = {
    "stream_enabled",
    "stream_word_chunking",
    "native_compat",
    "think",
    "rate_limit_status",
    "router_debug_external_access",
}


def llm_option_current_bool(provider: str, pcfg: dict[str, Any], key: str) -> bool:
    if key == "stream_enabled":
        return bool(pcfg.get("stream_enabled", True))
    if key == "stream_word_chunking":
        return bool(pcfg.get("stream_word_chunking", False))
    if key == "native_compat":
        default = False if provider == "nvidia-hosted" else True
        return bool(pcfg.get("native_compat", default))
    if key == "think":
        return bool(pcfg.get("think", False))
    if key == "rate_limit_status":
        return bool(pcfg.get("rate_limit_status", True))
    if key == "router_debug_external_access":
        return router_debug_external_access_enabled()
    return bool(pcfg.get(key, False))


def llm_option_panel_rows(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    rows: list[str] = []
    values: list[str] = []

    def add(label: str, key: str, value: Any) -> None:
        rows.append(f"{label:<24} [{compact_text(value, 56)}]")
        values.append(key)

    add(ui_text("context_setup", lang), "context_setup", context_setting_status(provider, pcfg))
    add(ui_text("apply_preset", lang), "preset", llm_preset_text(applied_preset_id(provider, pcfg), lang)[0])
    add(ui_text("timeout_preset", lang), "timeout_profile", timeout_profile_status(pcfg, lang))
    add("Router debug external", "router_debug_external_access", "on" if router_debug_external_access_enabled() else "off")
    add("Event message preview", "router_debug_message_preview_chars", router_debug_message_preview_chars())
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        add("Context window", "num_ctx", ollama_num_ctx_status(pcfg))
        add("Context min", "num_ctx_min", pcfg.get("num_ctx_min", "default"))
        add("Context max", "num_ctx_max", pcfg.get("num_ctx_max", "default"))
        add("Max output tokens", "num_predict", opts.get("num_predict", "default"))
        add("Temperature", "temperature", opts.get("temperature", "default"))
        add("Top P", "top_p", opts.get("top_p", "default"))
        add("Top K", "top_k", opts.get("top_k", "default"))
        add("Think", "think", bool(pcfg.get("think", False)))
        add("Keep alive", "keep_alive", pcfg.get("keep_alive", "default"))
        add("Timeout ms", "request_timeout_ms", pcfg.get("request_timeout_ms", "default"))
        add("Stream", "stream_enabled", "on" if bool(pcfg.get("stream_enabled", True)) else "off")
        if bool(pcfg.get("stream_enabled", True)):
            add("Stream idle timeout ms", "stream_idle_timeout_ms", pcfg.get("stream_idle_timeout_ms", "auto"))
            add("Stream word chunking", "stream_word_chunking", "on" if bool(pcfg.get("stream_word_chunking", False)) else "off")
        add("Rate limit RPM", "rate_limit_rpm", pcfg.get("rate_limit_rpm", 40))
        add("Rate limit status", "rate_limit_status", "on" if bool(pcfg.get("rate_limit_status", True)) else "off")
    else:
        if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
            add("Context window", "context_window", pcfg.get("context_window", "default"))
            add("Context reserve", "context_reserve_tokens", pcfg.get("context_reserve_tokens", "default"))
        add("Max output tokens", "max_output_tokens", pcfg.get("max_output_tokens", "default"))
        if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
            add("Timeout ms", "request_timeout_ms", pcfg.get("request_timeout_ms", "default"))
            add("Rate limit RPM", "rate_limit_rpm", pcfg.get("rate_limit_rpm", "default"))
            add("Rate limit status", "rate_limit_status", "on" if bool(pcfg.get("rate_limit_status", True)) else "off")
            add("Temperature", "temperature", pcfg.get("temperature", "default"))
            add("Top P", "top_p", pcfg.get("top_p", "default"))
            add("Top K", "top_k", pcfg.get("top_k", "default"))
            if provider in ("vllm", "self-hosted-nim"):
                add("Native compatibility", "native_compat", bool(pcfg.get("native_compat", True)))
            add("Stream", "stream_enabled", "on" if bool(pcfg.get("stream_enabled", True)) else "off")
            if bool(pcfg.get("stream_enabled", True)):
                add("Stream idle timeout ms", "stream_idle_timeout_ms", pcfg.get("stream_idle_timeout_ms", "auto"))
                add("Stream word chunking", "stream_word_chunking", "on" if bool(pcfg.get("stream_word_chunking", False)) else "off")
        elif provider == "anthropic":
            add("Timeout ms", "request_timeout_ms", pcfg.get("request_timeout_ms", "Claude Code default"))

    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def llm_option_prompt_default(provider: str, pcfg: dict[str, Any], key: str) -> str:
    if key == "router_debug_external_access":
        return "true" if router_debug_external_access_enabled() else "false"
    if key == "router_debug_message_preview_chars":
        return str(router_debug_message_preview_chars())
    if key == "stream_enabled":
        return "true" if bool(pcfg.get("stream_enabled", True)) else "false"
    if key == "stream_word_chunking":
        return "true" if bool(pcfg.get("stream_word_chunking", False)) else "false"
    if key == "rate_limit_status":
        return "true" if bool(pcfg.get("rate_limit_status", True)) else "false"
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        if key == "num_ctx":
            return str(pcfg.get("num_ctx", "auto"))
        if key in ("num_ctx_min", "num_ctx_max", "keep_alive", "think", "request_timeout_ms", "stream_idle_timeout_ms"):
            return str(pcfg.get(key, ""))
        if key in opts:
            return str(opts[key])
        return ""
    value = pcfg.get(key)
    return "" if value is None else str(value)


def set_llm_option_config(provider: str, key: str, raw_value: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    value = raw_value.strip()
    if not value:
        return ["Option unchanged."]
    if key == "router_debug_external_access":
        return set_router_debug_external_access_config(value)
    if key == "router_debug_message_preview_chars":
        fixed = positive_int(value)
        if str(value).lower() in ("0", "false", "off", "disable", "disabled", "none", "unset"):
            fixed = 0
        if fixed is None:
            return ["router_debug_message_preview_chars: enter digits only, or 0/off to disable."]
        cfg["router_debug_message_preview_chars"] = min(fixed, 4000)
        save_config(cfg)
        return ["Router event message preview updated.", f"preview chars: {cfg['router_debug_message_preview_chars']}"]
    numeric_keys = {
        "context_window",
        "context",
        "max_model_len",
        "context_reserve_tokens",
        "reserve",
        "max_output_tokens",
        "max_tokens",
        "maxtoken",
        "max_token",
        "num_ctx_min",
        "num_ctx_max",
        "num_predict",
        "timeout",
        "timeout_ms",
        "request_timeout",
        "request_timeout_ms",
        "stream_idle_timeout",
        "stream_idle_timeout_ms",
        "idle_timeout",
        "idle_timeout_ms",
        "rate_limit",
        "rate_limit_rpm",
        "rpm",
        "top_k",
    }
    if key in numeric_keys and value.lower() not in ("default", "unset", "none", "null", "0"):
        if not re.fullmatch(r"\d+", value):
            return [f"{key}: enter digits only, or use default/unset to clear."]
    clear_words = ("default", "unset", "none", "null")
    token = f"unset:{key}" if value.lower() in clear_words else f"{key}={value}"
    context_changed = key in ("context_window", "context", "max_model_len", "num_ctx", "ctx", "num_ctx_min", "ctx_min", "min", "num_ctx_max", "ctx_max", "max")
    explicit_timeout = key in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms", "stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms")
    if provider in ("ollama", "ollama-cloud"):
        apply_ollama_option(pcfg, token)
    elif provider == "anthropic":
        if key in ("max_output_tokens", "max_tokens", "maxtoken", "max_token"):
            apply_provider_option(provider, pcfg, token)
        elif key in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms"):
            apply_provider_option(provider, pcfg, token)
        else:
            raise SystemExit(f"Unknown Anthropic option: {key}")
    else:
        apply_provider_option(provider, pcfg, token)
    timeout_lines = apply_recommended_timeout_for_model_context(provider, pcfg) if context_changed and not explicit_timeout else []
    save_config(cfg)
    clear_model_cache()
    return [f"{PROVIDER_LABELS.get(provider, provider)} option updated.", f"{key}: {value}", *timeout_lines]


def apply_provider_option(provider: str, pcfg: dict[str, Any], token: str) -> None:
    if token.startswith("unset:"):
        key = token.split(":", 1)[1].strip()
        if key in ("context_window", "context", "max_model_len"):
            pcfg.pop("context_window", None)
        elif key in ("context_reserve_tokens", "reserve"):
            pcfg.pop("context_reserve_tokens", None)
        elif key in ("max_output_tokens", "max_tokens", "maxtoken", "max_token"):
            pcfg.pop("max_output_tokens", None)
        elif key in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms"):
            pcfg.pop("request_timeout_ms", None)
        elif key in ("stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms"):
            pcfg.pop("stream_idle_timeout_ms", None)
        elif key in ("rate_limit", "rate_limit_rpm", "rpm"):
            pcfg.pop("rate_limit_rpm", None)
        elif key in ("rate_limit_status", "rpm_status"):
            pcfg["rate_limit_status"] = True
        elif key in ("native", "native_compat"):
            if provider == "nvidia-hosted":
                raise SystemExit(
                    "nvidia-hosted does not expose Anthropic /v1/messages; use router mode. "
                    "Use self-hosted-nim for native NIM /v1/messages."
                )
            pcfg["native_compat"] = True
        elif key in ("stream", "stream_enabled"):
            pcfg["stream_enabled"] = True
        elif key in ("stream_word_chunking", "word_chunking", "stream_chunk", "stream_words"):
            pcfg["stream_word_chunking"] = False
        elif sampling_option_key(key):
            pcfg.pop(sampling_option_key(key), None)
        else:
            raise SystemExit(f"Unknown provider option: {key}")
        return
    if "=" not in token:
        raise SystemExit(f"Expected key=value or unset:key, got: {token}")
    key, raw_value = token.split("=", 1)
    key = key.strip()
    value = parse_config_value(raw_value)
    if key in ("context_window", "context", "max_model_len"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("context_window must be a positive integer")
        pcfg["context_window"] = fixed
        return
    if key in ("context_reserve_tokens", "reserve"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("context_reserve_tokens must be a positive integer")
        pcfg["context_reserve_tokens"] = fixed
        return
    if key in ("max_output_tokens", "max_tokens", "maxtoken", "max_token"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("max_output_tokens must be a positive integer")
        pcfg["max_output_tokens"] = fixed
        return
    if key in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("timeout must be a positive integer; values above 10000 are treated as milliseconds")
        pcfg["request_timeout_ms"] = fixed if key.endswith("_ms") or fixed > 10000 else fixed * 1000
        return
    if key in ("stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("stream_idle_timeout_ms must be a positive integer; values above 10000 are treated as milliseconds")
        pcfg["stream_idle_timeout_ms"] = fixed if key.endswith("_ms") or fixed > 10000 else fixed * 1000
        return
    if key in ("rate_limit", "rate_limit_rpm", "rpm"):
        fixed = positive_int(value)
        if value in (0, "0", False, None):
            pcfg["rate_limit_rpm"] = 0
            return
        if not fixed:
            raise SystemExit("rate_limit_rpm must be a positive integer, or 0/unset to disable")
        pcfg["rate_limit_rpm"] = fixed
        return
    if key in ("native", "native_compat"):
        if provider == "nvidia-hosted":
            raise SystemExit(
                "nvidia-hosted does not expose Anthropic /v1/messages; use router mode. "
                "Use self-hosted-nim for native NIM /v1/messages."
            )
        pcfg["native_compat"] = bool(value)
        return
    if key in ("stream", "stream_enabled"):
        pcfg["stream_enabled"] = parse_bool(value, default=True)
        return
    if key in ("stream_word_chunking", "word_chunking", "stream_chunk", "stream_words"):
        pcfg["stream_word_chunking"] = parse_bool(value, default=False)
        return
    if key in ("rate_limit_status", "rpm_status"):
        pcfg["rate_limit_status"] = parse_bool(value, default=False)
        return
    sample_key = sampling_option_key(key)
    if sample_key:
        if value is None:
            pcfg.pop(sample_key, None)
        else:
            pcfg[sample_key] = validate_sampling_option(sample_key, value)
        return
    raise SystemExit(f"Unknown provider option: {key}")


def cmd_provider_options(args: argparse.Namespace) -> None:
    cfg = load_config()
    values = list(getattr(args, "values", []) or [])
    provider = cfg.get("current_provider", "vllm")
    if values:
        try:
            maybe_provider = normalize_provider(values[0])
            if maybe_provider in PROVIDER_OPTION_PROVIDERS:
                provider = maybe_provider
                values = values[1:]
        except SystemExit:
            pass
    if provider not in PROVIDER_OPTION_PROVIDERS:
        raise SystemExit("Provider options are available for anthropic, ollama, ollama-cloud, vllm, nvidia-hosted, and self-hosted-nim.")
    pcfg = cfg["providers"][provider]
    if values:
        context_changed = any(
            token.split("=", 1)[0].replace("unset:", "").strip() in ("context_window", "context", "max_model_len")
            for token in values
        )
        explicit_timeout = any(
            token.split("=", 1)[0].replace("unset:", "").strip() in ("timeout", "timeout_ms", "request_timeout", "request_timeout_ms", "stream_idle_timeout", "stream_idle_timeout_ms", "idle_timeout", "idle_timeout_ms")
            for token in values
        )
        for token in values:
            apply_provider_option(provider, pcfg, token)
        timeout_lines = apply_recommended_timeout_for_model_context(provider, pcfg) if context_changed and not explicit_timeout else []
        save_config(cfg)
        clear_model_cache()
        print(f"Provider options updated for {provider}.")
        for line in timeout_lines:
            print(line)
    print(f"provider: {provider}")
    print(f"provider_options: {provider_options_status(provider, pcfg)}")
    print("Notes:")
    print("  max_output_tokens is passed to Claude Code as CLAUDE_CODE_MAX_OUTPUT_TOKENS.")
    print("  context_window is a claude-any/router cap; native mode still cannot raise the real server limit.")
    print("  temperature/top_p/top_k are injected by claude-any router mode when the provider supports them.")
    print("Examples:")
    print("  claude-anyctl provider-options nvidia-hosted max_output_tokens=4096 temperature=0.7 top_p=0.8 timeout=300000 rate_limit_rpm=40")
    print("  claude-anyctl provider-options vllm max_output_tokens=4096 context_window=65536 timeout=300000")
    print("  claude-anyctl provider-options self-hosted-nim native=true max_output_tokens=4096")


COMPAT_TOOL_NAME = "compat_echo"


def compatibility_tool_schema() -> dict[str, Any]:
    return {
        "name": COMPAT_TOOL_NAME,
        "description": "A minimal compatibility test tool. It echoes one required text argument.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    }


def compatibility_text_request(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": compat_max_tokens_for_model(model),
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Compatibility text test. Reply with exactly OK and do not call tools.",
            }
        ],
    }


def compatibility_tool_request(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 128,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Compatibility tool test. Use the compat_echo tool exactly once with text set to ping.",
            }
        ],
        "tools": [compatibility_tool_schema()],
        "tool_choice": {"type": "tool", "name": COMPAT_TOOL_NAME},
    }


def compatibility_tool_result_request(model: str, tool_use: dict[str, Any]) -> dict[str, Any]:
    tool_id = str(tool_use.get("id") or "toolu_compat_echo_1")
    tool_input = tool_use.get("input") if isinstance(tool_use.get("input"), dict) else {"text": "ping"}
    return {
        "model": model,
        "max_tokens": 64,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Compatibility tool test. Use the compat_echo tool exactly once with text set to ping.",
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": COMPAT_TOOL_NAME,
                        "input": tool_input,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": "pong",
                    },
                    {
                        "type": "text",
                        "text": "Now reply with FINAL_OK and do not call tools.",
                    },
                ],
            },
        ],
        "tools": [compatibility_tool_schema()],
    }


def response_content_blocks(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    content = data.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def response_content_types(data: Any) -> list[str]:
    return [str(block.get("type", "?")) for block in response_content_blocks(data)]


def response_text_preview(data: Any) -> str:
    parts: list[str] = []
    for block in response_content_blocks(data):
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"].strip())
    return " ".join(parts).strip()[:300]


def find_compat_tool_use(data: Any) -> tuple[dict[str, Any] | None, str]:
    for block in response_content_blocks(data):
        if block.get("type") != "tool_use":
            continue
        if block.get("name") != COMPAT_TOOL_NAME:
            return None, f"unexpected tool name {block.get('name')!r}"
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            return None, "tool input was not a JSON object"
        if tool_input.get("text") != "ping":
            return None, f"tool input text was {tool_input.get('text')!r}, expected 'ping'"
        if not block.get("id"):
            return None, "tool_use block did not include an id"
        return block, ""
    types = ", ".join(response_content_types(data)) or "none"
    preview = response_text_preview(data)
    suffix = f"; text={preview!r}" if preview else ""
    return None, f"no compat_echo tool_use block returned; content blocks: {types}{suffix}"


def summarize_compat_response(data: Any, label: str) -> list[str]:
    lines = [f"{label}: OK"]
    if isinstance(data, dict):
        stop = data.get("stop_reason")
        if stop:
            lines.append(f"Stop reason: {stop}")
        types = response_content_types(data)
        if types:
            lines.append("Content blocks: " + ", ".join(types[:6]))
        usage = data.get("usage")
        if isinstance(usage, dict):
            tokens = []
            if "input_tokens" in usage:
                tokens.append(f"in={usage['input_tokens']}")
            if "output_tokens" in usage:
                tokens.append(f"out={usage['output_tokens']}")
            if tokens:
                lines.append("Tokens: " + ", ".join(tokens))
    return lines


def compatibility_failure_diagnosis(provider: str, code: int | None, msg: str) -> str | None:
    lower = msg.lower()
    if provider == "vllm" and ("tool" in lower or "parse" in lower or "parser" in lower):
        return (
            "Diagnosis: vLLM tool calling depends on the server's model-specific --tool-call-parser and chat template. "
            "For Qwen3-Coder models, current vLLM docs recommend --tool-call-parser qwen3_xml; Hermes is for Hermes-style models "
            "and some older Qwen tool templates."
        )
    if "does not support tools" in lower:
        return "Diagnosis: selected model does not support tool calling, so it is not suitable for normal Claude Code use."
    if provider == "nvidia-hosted" and code == 404:
        return (
            "Diagnosis: NVIDIA API Catalog does not expose this request path/model for the current account. "
            "Use the default router mode for nvidia-hosted, or pick another hosted model."
        )
    if provider == "nvidia-hosted" and code in (502, 503, 504):
        return (
            "Diagnosis: NVIDIA API Catalog or the hosted model backend returned a transient upstream error. "
            "Retry the compatibility test, or choose another NVIDIA hosted model if it repeats."
        )
    if provider == "nvidia-hosted" and (
        "remotedisconnected" in lower
        or "remote end closed connection" in lower
        or "connection reset" in lower
        or "gateway timeout" in lower
    ):
        return (
            "Diagnosis: the NVIDIA hosted upstream closed the request without a complete response. "
            "This is usually a transient API Catalog/backend issue rather than a local claude-any configuration error. "
            "Retry the test, or choose another hosted model if it repeats."
        )
    if provider == "nvidia-hosted" and "function" in lower and "not found" in lower:
        return (
            "Diagnosis: NVIDIA returned a missing function for this hosted model. The model is visible in /v1/models "
            "but is not callable with the current account."
        )
    return None


def vllm_tool_parser_hint(model: str) -> str | None:
    normalized = model.lower()
    if "qwen3-coder" in normalized or "qwen3_coder" in normalized:
        return "vLLM hint: Qwen3-Coder models should be served with --enable-auto-tool-choice --tool-call-parser qwen3_xml."
    if "qwen2.5" in normalized or "qwen2_5" in normalized or "qwq" in normalized:
        return "vLLM hint: Qwen2.5/QwQ tool templates usually use --enable-auto-tool-choice --tool-call-parser hermes."
    if "glm-4.7" in normalized or "glm4.7" in normalized:
        return "vLLM hint: GLM-4.7 models should be served with --enable-auto-tool-choice --tool-call-parser glm47."
    if "glm-4.5" in normalized or "glm4.5" in normalized or "glm-4.6" in normalized or "glm4.6" in normalized:
        return "vLLM hint: GLM-4.5/4.6 models should be served with --enable-auto-tool-choice --tool-call-parser glm45."
    if "deepseek-v3.1" in normalized:
        return "vLLM hint: DeepSeek-V3.1 models should be served with --enable-auto-tool-choice --tool-call-parser deepseek_v31."
    if "deepseek-v3" in normalized or "deepseek-r1" in normalized:
        return "vLLM hint: DeepSeek-V3/R1 models require the matching DeepSeek tool parser and chat template from vLLM examples."
    if "llama-3" in normalized or "llama3" in normalized:
        return "vLLM hint: Llama 3.x models usually need --enable-auto-tool-choice --tool-call-parser llama3_json and the matching tool chat template."
    if "hermes" in normalized:
        return "vLLM hint: Hermes models should be served with --enable-auto-tool-choice --tool-call-parser hermes."
    if "qwen3" in normalized or "qwen-3" in normalized:
        return (
            "vLLM hint: this looks like a Qwen3-family model. Verify its model card/tool format; "
            "Qwen3-Coder uses qwen3_xml, while older Hermes-style Qwen templates use hermes."
        )
    return None


def compatibility_runtime_lines(provider: str, pcfg: dict[str, Any], native: bool) -> list[str]:
    if provider not in ("vllm", "self-hosted-nim"):
        return []
    lines: list[str] = []
    info = upstream_model_runtime_info(provider, pcfg, timeout=4.0)
    configured_context = positive_int(pcfg.get("context_window"))
    configured_output = positive_int(pcfg.get("max_output_tokens"))
    if info:
        lines.append(f"Runtime models URL: {info.get('models_url')}")
        if info.get("runtime_model"):
            lines.append(f"Runtime model id: {info.get('runtime_model')}")
        runtime_limit = positive_int(info.get("max_model_len"))
        if runtime_limit:
            lines.append(f"Runtime max_model_len: {runtime_limit}")
        else:
            lines.append("Runtime max_model_len: not reported by /v1/models")
    else:
        runtime_limit = None
        lines.append("Runtime max_model_len: unavailable (/v1/models did not return model metadata)")
    if configured_context:
        lines.append(f"Configured context_window: {configured_context}")
    if configured_output:
        lines.append(f"Configured max_output_tokens: {configured_output}")
    if runtime_limit and configured_context and configured_context != runtime_limit:
        lines.append(f"Context warning: configured context_window {configured_context} differs from runtime max_model_len {runtime_limit}.")
    if runtime_limit and configured_output and configured_output >= runtime_limit:
        lines.append("Context warning: max_output_tokens is greater than or equal to the full runtime context length.")
    if native:
        lines.append("Runtime mode note: native mode sends Claude Code requests directly; claude-any cannot shrink max_tokens per request.")
    else:
        lines.append("Runtime mode note: router mode can cap max_tokens based on configured context_window.")
    return lines


def set_compatibility_cache(
    cfg: dict[str, Any],
    provider: str,
    model: str,
    ok: bool,
    code: int | None = None,
    message: str = "",
    diagnosis: str = "",
) -> None:
    cache = cfg.setdefault("compatibility_cache", {})
    if not isinstance(cache, dict):
        cache = {}
        cfg["compatibility_cache"] = cache
    provider_cache = cache.setdefault(provider, {})
    if not isinstance(provider_cache, dict):
        provider_cache = {}
        cache[provider] = provider_cache
    provider_cache[model] = {
        "ok": ok,
        "code": code,
        "message": message[:500],
        "diagnosis": diagnosis[:500],
        "tested_at": int(time.time()),
    }
    save_config(cfg)


def _cmd_test(args: argparse.Namespace) -> None:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    test_mode = getattr(args, "mode", "auto") or "auto"
    if test_mode not in ("auto", "quick", "smoke", "full"):
        raise SystemExit("test mode must be auto, quick, smoke, or full")
    effective_mode = "quick" if test_mode == "auto" and provider == "nvidia-hosted" else ("full" if test_mode == "auto" else test_mode)
    ollama_native = ollama_native_compat_enabled(provider, pcfg)
    provider_native = provider_native_compat_enabled(provider, pcfg)
    native = ollama_native or provider_native
    model = current_upstream_model_id(provider, pcfg) if provider_native else (launch_model_id(provider, pcfg) if ollama_native else current_alias(cfg))
    base = native_anthropic_base_url(provider, pcfg) if native else ROUTER_BASE
    if not native:
        # Compatibility tests must exercise the currently installed router.
        # Older long-running routers can keep stale NVIDIA proxy code alive
        # across npm upgrades, producing false nvd-claude-proxy failures.
        stop_router_processes(quiet=True)
        start_router_if_needed()
    url = join_url(base, "/v1/messages")
    headers = provider_headers(provider, pcfg)
    if ollama_native:
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "authorization": "Bearer ollama",
            "x-api-key": "ollama",
        }
    text_body = compatibility_text_request(model)
    tool_body = compatibility_tool_request(model)
    print(f"Testing provider: {provider}")
    print(f"Test mode: {effective_mode}")
    if ollama_native:
        mode = "ollama-native"
    elif vllm_native_compat_enabled(provider, pcfg):
        mode = "vllm-native"
    elif nim_native_compat_enabled(provider, pcfg):
        mode = "nim-native"
    elif nvidia_hosted_native_compat_enabled(provider, pcfg):
        mode = "nvidia-native"
    else:
        mode = "claude-any-router"
    print(f"Mode: {mode}")
    print(f"Claude API URL: {url}")
    if not native:
        print(f"Upstream base URL: {pcfg.get('base_url')}")
        if provider in ("ollama", "ollama-cloud"):
            req_preview = ollama_chat_request(resolve_requested_model(provider, pcfg, model), tool_body, pcfg, stream=False)
            print(f"Ollama num_ctx: {req_preview.get('options', {}).get('num_ctx', 'default')}")
    print(f"Model: {model}")
    for line in compatibility_runtime_lines(provider, pcfg, native):
        print(line)
    if provider == "vllm":
        hint = vllm_tool_parser_hint(model)
        if hint:
            print(hint)

    def fail(message: str, code: int | None = None, diagnosis: str = "") -> None:
        print("Compatibility: FAIL")
        if code is not None:
            print(f"HTTP: {code}")
        print(f"Reason: {message[:1000]}")
        if diagnosis:
            print(diagnosis)
        set_compatibility_cache(cfg, provider, model, False, code, message, diagnosis)
        raise SystemExit(1)

    def run_phase(label: str, request_body: dict[str, Any]) -> Any:
        print(f"{label}: running")
        try:
            return post_json(url, request_body, headers=headers, timeout=args.timeout)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            msg = raw.strip()
            try:
                err = json.loads(raw)
                if isinstance(err, dict):
                    if isinstance(err.get("error"), dict):
                        msg = err["error"].get("message") or json.dumps(err["error"])
                    elif err.get("message"):
                        msg = str(err["message"])
            except Exception:
                pass
            diagnosis = compatibility_failure_diagnosis(provider, exc.code, msg)
            fail(f"{label}: {msg}", exc.code, diagnosis or "")
        except TimeoutError:
            print("Compatibility: TIMEOUT")
            print(f"Reason: {label} did not respond before the {args.timeout:g}s compatibility-test timeout.")
            print("Diagnosis: this timeout was not saved as a model failure. Retry the test or choose another model if it repeats.")
            sys.stdout.flush()
            sys.exit(1)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                print("Compatibility: TIMEOUT")
                print(f"Reason: {label}: {msg}")
                print("Diagnosis: this timeout was not saved as a model failure. Retry the test or choose another model if it repeats.")
                sys.stdout.flush()
                sys.exit(1)
            fail(f"{label}: {msg}")

    text_data = run_phase("Text response", text_body)
    for line in summarize_compat_response(text_data, "Text response"):
        print(line)

    if effective_mode == "quick":
        set_compatibility_cache(cfg, provider, model, True, 200, "text quick OK", "")
        print("Compatibility: OK")
        print("Note: quick mode checked text only; run `claude-any test 120 smoke` for tool_use or `claude-any test 180 full` for tool_result.")
        return

    tool_data = run_phase("Tool use", tool_body)
    tool_use, tool_error = find_compat_tool_use(tool_data)
    if not tool_use:
        diagnosis = (
            "Diagnosis: the model/server did not return a valid Anthropic tool_use block. "
            "Claude Code can fail with 'tool call could not be parsed' on this provider/model."
        )
        if provider == "vllm":
            hint = vllm_tool_parser_hint(model)
            if hint:
                diagnosis = f"{diagnosis} {hint}"
        fail(f"Tool use: {tool_error}", diagnosis=diagnosis)
    for line in summarize_compat_response(tool_data, "Tool use"):
        print(line)

    if effective_mode == "smoke":
        set_compatibility_cache(cfg, provider, model, True, 200, "text/tool_use smoke OK", "")
        print("Compatibility: OK")
        print("Note: smoke mode checked text and tool_use only; run `claude-any test 180 full` for tool_result round trip.")
        return

    result_body = compatibility_tool_result_request(model, tool_use)
    result_data = run_phase("Tool result", result_body)
    result_preview = response_text_preview(result_data)
    if not result_preview:
        fail(
            "Tool result: no final text response after tool_result.",
            diagnosis="Diagnosis: the provider accepted tool_use but did not complete the tool_result round trip.",
        )
    for line in summarize_compat_response(result_data, "Tool result"):
        print(line)
    print(f"Tool result text: {result_preview[:120]}")

    set_compatibility_cache(cfg, provider, model, True, 200, "text/tool_use/tool_result OK", "")
    print("Compatibility: OK")


def cmd_test(args: argparse.Namespace) -> None:
    try:
        _cmd_test(args)
    except SystemExit:
        raise
    except Exception as exc:
        print("Compatibility: FAIL")
        print(f"Reason: {type(exc).__name__}: {exc}")
        raise SystemExit(1)


def claude_code_output_token_limit(provider: str, pcfg: dict[str, Any]) -> int | None:
    configured = positive_int(pcfg.get("max_output_tokens"))
    if configured:
        return configured
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        configured = positive_int(opts.get("num_predict"))
        if configured:
            return configured
    return None


def claude_code_auto_compact_window(provider: str, pcfg: dict[str, Any]) -> int | None:
    limit = context_limit_for_status(provider, pcfg)
    if limit:
        return limit
    return None


def claude_code_context_model_alias(provider: str, pcfg: dict[str, Any], model: str) -> str:
    model = strip_claude_context_suffix(model)
    limit = context_limit_for_status(provider, pcfg)
    if limit and limit >= 1000000 and "[1m]" not in model.lower():
        return f"{model}[1m]"
    return model


def apply_common_claude_env(provider: str, pcfg: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    # Claude Code's AI-generated terminal/session title can be persisted as
    # ai-title records and, in some resume/queued-command states, visually bleed
    # into the prompt area. Disable that side path for claude-any launches.
    env["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] = "1"
    output_tokens = claude_code_output_token_limit(provider, pcfg)
    if output_tokens:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(output_tokens)
    compact_window = claude_code_auto_compact_window(provider, pcfg)
    if compact_window:
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(compact_window)
    advisor_model = str(pcfg.get("advisor_model") or "").strip()
    if advisor_model:
        env["CLAUDE_ANY_ADVISOR_MODEL"] = advisor_model
    return env


def env_vars(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    provider, pcfg = get_current_provider(cfg)
    if native_anthropic_enabled(provider):
        env = {
            "CLAUDE_ANY_PROVIDER": provider,
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
        }
        if meaningful_key(pcfg.get("api_key")):
            env["ANTHROPIC_API_KEY"] = str(pcfg["api_key"])
        if pcfg.get("current_model"):
            env["CLAUDE_ANY_MODEL_ALIAS"] = str(pcfg["current_model"])
        return apply_common_claude_env(provider, pcfg, env)
    if ollama_native_compat_enabled(provider, pcfg):
        model = launch_model_id(provider, pcfg)
        return apply_common_claude_env(provider, pcfg, {
            "CLAUDE_ANY_PROVIDER": provider,
            "ANTHROPIC_BASE_URL": pcfg.get("base_url", "http://127.0.0.1:11434").rstrip("/"),
            "ANTHROPIC_AUTH_TOKEN": "ollama",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "CLAUDE_CODE_SUBAGENT_MODEL": model,
            "CLAUDE_ANY_MODEL_ALIAS": model,
        })
    if provider_native_compat_enabled(provider, pcfg):
        model = current_upstream_model_id(provider, pcfg)
        token = nvidia_api_key() if provider == "nvidia-hosted" else str(pcfg.get("api_key") or "dummy")
        if not token:
            token = "not-used"
        return apply_common_claude_env(provider, pcfg, {
            "CLAUDE_ANY_PROVIDER": provider,
            "ANTHROPIC_BASE_URL": native_anthropic_base_url(provider, pcfg),
            "ANTHROPIC_API_KEY": token,
            "ANTHROPIC_AUTH_TOKEN": token,
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_CUSTOM_MODEL_OPTION": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "CLAUDE_CODE_SUBAGENT_MODEL": model,
            "CLAUDE_ANY_MODEL_ALIAS": model,
        })
    alias = current_alias(cfg)
    claude_model = claude_code_context_model_alias(provider, pcfg, alias)
    return apply_common_claude_env(provider, pcfg, {
        "CLAUDE_ANY_PROVIDER": provider,
        "ANTHROPIC_BASE_URL": ROUTER_BASE,
        "ANTHROPIC_AUTH_TOKEN": "not-used",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
        "ANTHROPIC_MODEL": claude_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": claude_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": claude_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": claude_model,
        "CLAUDE_CODE_SUBAGENT_MODEL": claude_model,
        "CLAUDE_ANY_MODEL_ALIAS": claude_model,
    })


def cmd_env(_: argparse.Namespace) -> None:
    env = env_vars()
    for optional in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"):
        if optional in env:
            print(f"export {optional}={json.dumps(env[optional])}")
        else:
            print(f"unset {optional}")
    if "ANTHROPIC_AUTH_TOKEN" in env:
        print(f"export ANTHROPIC_AUTH_TOKEN={json.dumps(env['ANTHROPIC_AUTH_TOKEN'])}")
    else:
        print('unset ANTHROPIC_AUTH_TOKEN')
    for key in (
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
        "CLAUDE_CODE_ATTRIBUTION_HEADER",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_CUSTOM_MODEL_OPTION",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_ANY_MODEL_ALIAS",
        "CLAUDE_ANY_PROVIDER",
    ):
        if key in env:
            print(f"export {key}={json.dumps(env[key])}")
        else:
            print(f"unset {key}")


def cmd_stop(_: argparse.Namespace) -> None:
    stopped = stop_router_processes(quiet=True)
    stopped = stop_ncp_proxy(quiet=True) or stopped
    print("claude-any managed services stopped" if stopped else "claude-any managed services were not running")


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            out = proc.stdout or ""
            return str(pid) in out and "No tasks" not in out and "INFO:" not in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError):
        return False


def terminate_pid_file(path: Path, label: str, quiet: bool = False) -> bool:
    if not path.exists():
        return False
    try:
        pid = int(path.read_text().strip())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return False
    if not pid_is_running(pid):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return False
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        else:
            os.kill(pid, signal.SIGTERM)
            deadline = time.time() + 4
            while time.time() < deadline and pid_is_running(pid):
                time.sleep(0.1)
            if pid_is_running(pid):
                os.kill(pid, signal.SIGKILL)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        if not quiet:
            print(f"Stopped existing {label} session (pid {pid}).")
        return True
    except Exception as exc:
        if not quiet:
            print(f"Could not stop existing {label} session ({type(exc).__name__}).")
        return False


def windows_pids_on_port(port: int) -> list[int]:
    if os.name != "nt":
        return []
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return []
    pids: set[int] = set()
    marker = f":{port}"
    for line in proc.stdout.splitlines():
        if marker not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(pids)


def terminate_windows_port(port: int, label: str, quiet: bool = False) -> bool:
    pids = windows_pids_on_port(port)
    stopped = False
    for pid in pids:
        if pid in (os.getpid(), os.getppid()):
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            stopped = True
        except Exception:
            pass
    if stopped and not quiet:
        print(f"Stopped existing {label} session(s): {', '.join(map(str, pids))}.")
    return stopped


def terminate_matching_processes(needles: list[str], label: str, quiet: bool = False) -> bool:
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        try:
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
            rows = json.loads(p.stdout or "[]")
        except Exception:
            return False
        if isinstance(rows, dict):
            rows = [rows]
        current = os.getpid()
        matched: list[int] = []
        for row in rows if isinstance(rows, list) else []:
            try:
                pid = int(row.get("ProcessId"))
            except Exception:
                continue
            command = str(row.get("CommandLine") or "")
            if pid == current or pid == os.getppid() or not command:
                continue
            if all(needle in command for needle in needles):
                matched.append(pid)
        stopped = False
        for pid in matched:
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                stopped = True
            except Exception:
                pass
        if stopped and not quiet:
            print(f"Stopped existing {label} session(s): {', '.join(map(str, matched))}.")
        return stopped
    try:
        p = subprocess.run(
            ["ps", "-u", getpass.getuser(), "-o", "pid=,stat=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return False
    current = os.getpid()
    matched: list[int] = []
    for line in p.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        stat, command = parts[1], parts[2]
        if pid == current or pid == os.getppid() or stat.startswith("Z"):
            continue
        if all(needle in command for needle in needles):
            matched.append(pid)
    stopped = False
    for pid in matched:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except Exception:
            pass
    deadline = time.time() + 3
    while time.time() < deadline:
        alive = [pid for pid in matched if pid_is_running(pid)]
        if not alive:
            break
        time.sleep(0.1)
    for pid in matched:
        if pid_is_running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
    if stopped and not quiet:
        print(f"Stopped existing {label} session(s): {', '.join(map(str, matched))}.")
    return stopped


def stop_ncp_proxy(quiet: bool = False) -> bool:
    if os.name == "nt":
        port = positive_int(read_env_file(NCP_ENV).get("PROXY_PORT")) or 8788
        stopped = terminate_windows_port(port, "Nvidia NCP proxy", quiet=True)
        if stopped and not quiet:
            print("Stopped existing Nvidia NCP proxy session if one was running.")
        return stopped
    ncp = find_executable("ncp")
    stopped = False
    if not ncp:
        return terminate_matching_processes(["nvd_claude_proxy"], "Nvidia NCP proxy", quiet=quiet)
    try:
        subprocess.run([ncp, "kill"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        stopped = True
    except Exception:
        pass
    stopped = terminate_matching_processes(["nvd-claude-proxy"], "Nvidia NCP proxy", quiet=True) or stopped
    stopped = terminate_matching_processes(["ncp", "proxy"], "Nvidia NCP proxy", quiet=True) or stopped
    stopped = terminate_matching_processes(["nvd_claude_proxy"], "Nvidia NCP proxy", quiet=True) or stopped
    if stopped and not quiet:
        print("Stopped existing Nvidia NCP proxy session if one was running.")
    return stopped


def stop_router_processes(quiet: bool = False) -> bool:
    stopped = terminate_pid_file(PID_PATH, "claude-any router", quiet=quiet)
    if os.name == "nt":
        stopped = terminate_windows_port(ROUTER_PORT, "claude-any router", quiet=quiet) or stopped
        return stopped
    stopped = terminate_matching_processes(["claude_any.py", "serve"], "claude-any router", quiet=quiet) or stopped
    return stopped


def cleanup_managed_services_for_provider(provider: str, pcfg: dict[str, Any], cfg: dict[str, Any], quiet: bool = False) -> None:
    if not cfg.get("cleanup", {}).get("managed_services_on_launch", True):
        return
    if (
        native_anthropic_enabled(provider)
        or ollama_native_compat_enabled(provider, pcfg)
        or provider_native_compat_enabled(provider, pcfg)
    ):
        stop_router_processes(quiet=quiet)
    if provider != "nvidia-hosted" or provider_native_compat_enabled(provider, pcfg):
        stop_ncp_proxy(quiet=quiet)


def default_base_url(provider: str) -> str:
    return {
        "anthropic": "https://api.anthropic.com",
        "ollama": "http://your-ollama:11434",
        "ollama-cloud": "https://ollama.com",
        "vllm": "http://your-vllm:8000",
        "nvidia-hosted": nvidia_upstream_base_url(),
        "self-hosted-nim": "http://your-nim:8000",
    }.get(provider, "http://localhost:8000")


def meaningful_key(value: str | None) -> bool:
    return meaningful_key_value(value)


def api_key_status_line(provider: str, pcfg: dict[str, Any]) -> str:
    if provider == "nvidia-hosted":
        key = nvidia_api_key()
        return "API key: set (NVIDIA)" if meaningful_key(key) else "API key: missing (NVIDIA required)"
    if provider == "anthropic":
        return "API key: set (Anthropic)" if meaningful_key(pcfg.get("api_key")) else "API key: not set (use API key or Claude login)"
    if provider == "ollama-cloud":
        return "API key: set (Ollama Cloud)" if meaningful_key(pcfg.get("api_key")) else "API key: missing (Ollama Cloud required)"
    if meaningful_key(pcfg.get("api_key")):
        return "API key: set"
    if provider == "ollama":
        return "API key: not required for Ollama"
    return "API key: optional or not configured"


def base_url_status_line(provider: str, pcfg: dict[str, Any]) -> str:
    base = (pcfg.get("base_url") or "").rstrip("/")
    if not base:
        return "Base URL: missing"
    if "your-" in base:
        return f"Base URL: placeholder ({base})"
    if provider == "nvidia-hosted":
        if nvidia_hosted_native_compat_enabled(provider, pcfg):
            return f"Base URL: NVIDIA hosted native ({native_anthropic_base_url(provider, pcfg)}/v1/messages)"
        state = "ready" if router_up() else "starts on launch"
        return f"Base URL: NVIDIA hosted ({base}); local router {ROUTER_BASE} {state}"
    path = "/api/tags" if provider in ("ollama", "ollama-cloud") else "/v1/models"
    headers: dict[str, str] = {}
    key = pcfg.get("api_key")
    if meaningful_key(key):
        headers = {"x-api-key": key, "authorization": f"Bearer {key}"}
    try:
        req = urllib.request.Request(join_url(base, path), headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            body = resp.read(131072).decode("utf-8", errors="ignore")
        count = ""
        try:
            data = json.loads(body)
            if provider in ("ollama", "ollama-cloud"):
                count = f", {len(data.get('models', []))} models"
            elif isinstance(data.get("data"), list):
                count = f", {len(data['data'])} models"
                limit = upstream_model_context_limit(provider, pcfg, timeout=1.0)
                if limit:
                    count += f", max_model_len {limit}"
        except Exception:
            pass
        return f"Base URL: model list reachable ({path}{count})"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return f"Base URL: model list reachable, auth rejected ({exc.code})"
        return f"Base URL: HTTP {exc.code}"
    except Exception as exc:
        if provider == "nvidia-hosted" and "127.0.0.1" in base:
            return "Base URL: proxy down; starts on launch"
        return f"Base URL: unreachable ({type(exc).__name__})"


def preflight_lines() -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    lang = cfg.get("language", "en")
    notes = PROVIDER_NOTES.get(lang, PROVIDER_NOTES["en"]).get(provider, [])
    return [
        base_url_status_line(provider, pcfg),
        api_key_status_line(provider, pcfg),
        *notes,
    ]


def launch_readiness_errors(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_config()
    provider, pcfg = get_current_provider(cfg)
    status = base_url_status_line(provider, pcfg)
    low = status.lower()
    errors: list[str] = []
    if any(marker in low for marker in ("unreachable", "placeholder", "missing")):
        errors.append(f"Launch blocked: {status}")
        if provider == "vllm":
            errors.append("vLLM must be reachable from this machine and expose Anthropic-compatible /v1/messages.")
        elif provider in ("ollama", "ollama-cloud"):
            errors.append("Start Ollama or set a reachable Base URL before launching Claude Code.")
        elif provider == "self-hosted-nim":
            errors.append("Start NIM or set a reachable Anthropic-compatible Base URL before launching Claude Code.")
        else:
            errors.append("Set a reachable Base URL before launching Claude Code.")
    if provider == "nvidia-hosted" and not (nvidia_api_key() or meaningful_key(pcfg.get("api_key"))):
        errors.append("Launch blocked: NVIDIA hosted requires an NVIDIA API key.")
    if provider == "ollama-cloud" and not meaningful_key(pcfg.get("api_key")):
        errors.append("Launch blocked: Ollama Cloud requires an API key.")
    return errors


def settings_ready_except_api_key() -> bool:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    base = pcfg.get("base_url", "")
    model = pcfg.get("current_model", "")
    return bool(provider and base and model and "your-" not in base)


def self_cmd(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return p.returncode, p.stdout


def enable_ansi() -> None:
    if os.name == "nt":
        os.system("")


def ansi(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


ANIMATED_TEXT_PALETTE = (203, 209, 215, 221, 229, 187, 151, 116, 111, 147, 183, 219)


def animated_ansi_text(text: str, *, phase: int | None = None, bold: bool = True) -> str:
    if not sys.stdout.isatty():
        return text
    if phase is None:
        phase = int(time.monotonic() * 8)
    parts: list[str] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            parts.append(ch)
            continue
        code = f"38;5;{ANIMATED_TEXT_PALETTE[(phase + i) % len(ANIMATED_TEXT_PALETTE)]}"
        if bold:
            code = "1;" + code
        parts.append(ansi(ch, code))
    return "".join(parts)


def cell_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return width


def fit_cells(value: Any, width: int) -> str:
    text = str(value if value is not None else "")
    width = max(1, width)
    if cell_width(text) <= width:
        return text
    suffix = "..." if width >= 4 else ""
    limit = max(1, width - cell_width(suffix))
    out: list[str] = []
    used = 0
    for ch in text:
        ch_width = 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1)
        if used + ch_width > limit:
            break
        out.append(ch)
        used += ch_width
    return "".join(out) + suffix


def pad_cells(value: Any, width: int) -> str:
    text = fit_cells(value, width)
    return text + (" " * max(0, width - cell_width(text)))


def color_line(text: str, code: str, width: int) -> str:
    fitted = fit_cells(text, width)
    return ansi(fitted, code)


def clean_render_lines(lines: list[str], width: int) -> list[str]:
    # All menu rows must stay single-line. Windows cmd corrupts redraws after
    # implicit line wrapping, even when ANSI clear-to-end is used.
    return [fit_cells(line, width) for line in lines]


def clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def intro_panel_lines(width: int) -> list[str]:
    width = max(48, min(width, 120))
    line = "-" * (width - 2)
    lines = [f"+{line}+"]
    title = f" {APP_NAME} "
    lines.append(f"|{title}{' ' * max(0, width - len(title) - 2)}|")
    if width >= 92:
        left_w = 39
        right_w = width - left_w - 4
        rows = [
            ("Welcome back!", "Tips for getting started"),
            ("", "Choose provider, model, base URL, and API key before launch."),
            ("   CLAUDE", "Routes Claude Code to Anthropic, Ollama, vLLM, Nvidia, or NIM."),
            ("      ANY", "Adds DuckDuckGo web search tooling for non-native providers."),
            (CREDITS, "Use --ca-* flags for headless runs; Claude flags pass through."),
        ]
        for left, right in rows:
            left_text = left[:left_w].ljust(left_w)
            right_text = right[:right_w].ljust(right_w)
            lines.append(f"| {left_text} | {right_text}|")
    else:
        rows = [
            f"{APP_NAME} routes Claude Code through selectable providers.",
            "Anthropic, Ollama, vLLM, Nvidia Hosted, and self-hosted NIM.",
            "DuckDuckGo web search is attached for non-native providers.",
            "Headless setup uses --ca-* flags; Claude flags pass through.",
            CREDITS,
        ]
        for row in rows:
            lines.append(f"| {row[: width - 4].ljust(width - 4)} |")
    lines.append(f"+{line}+")
    return lines


def print_intro_panel(width: int) -> None:
    print("\n".join(intro_panel_lines(width)))


def append_menu_key_debug_log(line: str) -> None:
    try:
        MENU_KEY_DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MENU_KEY_DEBUG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def read_menu_key(fd: int | None = None) -> str:
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code, "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            return "esc"
        return ch.lower()

    import time
    if fd is None or fd < 0:
        fd = sys.stdin.fileno()
    ch = os.read(fd, 1)
    log = f"{time.time():.3f} first={ch!r}"
    if ch == b"\x1b":
        seq = ch.decode("latin-1")
        b = os.read(fd, 1)
        log += f" next={b!r}"
        if not b:
            append_menu_key_debug_log(log + " result='esc'\n")
            return "esc"
        seq += b.decode("latin-1")
        if b == b"[":
            while True:
                b = os.read(fd, 1)
                log += f" next={b!r}"
                if not b:
                    break
                seq += b.decode("latin-1")
                if 0x40 <= b[0] <= 0x7E:
                    break
        elif b == b"O":
            b = os.read(fd, 1)
            log += f" next={b!r}"
            if b:
                seq += b.decode("latin-1")
        result = {
            "\x1b[A": "up", "\x1b[B": "down", "\x1b[D": "left", "\x1b[C": "right",
            "\x1b[5~": "pageup", "\x1b[6~": "pagedown",
            "\x1b[H": "home", "\x1b[F": "end",
        }.get(seq, "esc")
        log += f" seq={seq!r} result={result!r}"
        append_menu_key_debug_log(log + "\n")
        return result
    if ch in (b"\r", b"\n"):
        result = "enter"
    else:
        result = ch.decode("latin-1").lower()
    append_menu_key_debug_log(log + f" result={result!r}\n")
    return result


def portable_select(
    title: str,
    rows: list[str],
    current: int = 0,
    footer: str = "",
    info_lines: list[str] | None = None,
    show_intro: bool = False,
) -> int | None:
    enable_ansi()
    idx = max(0, min(current, len(rows) - 1))
    status_cache = status_lines()[:5]
    out_fd = sys.stdout.fileno()
    out_is_tty = os.isatty(out_fd) if os.name != "nt" else True
    if out_is_tty:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
    fd = sys.stdin.fileno()
    old_settings = None
    in_is_tty = os.isatty(fd) if os.name != "nt" else False
    if in_is_tty:
        try:
            import termios
            old_settings = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new)
        except Exception:
            fd = -1
    try:
        while True:
            screen: list[str] = []
            columns = shutil.get_terminal_size((100, 24)).columns
            if show_intro:
                screen.extend(intro_panel_lines(columns))
            screen.append(ansi(title, "1"))
            for line in status_cache:
                color = "32" if line.startswith(("provider:", "model:")) else "2"
                screen.append("  " + ansi(line, color))
            screen.append("")
            for i, row in enumerate(rows):
                prefix = "> " if i == idx else "  "
                text = prefix + row
                if i == idx:
                    screen.append(ansi(text, "7;1"))
                elif row.startswith(("Quit", "종료", "終了", "退出")):
                    screen.append(ansi(text, "31"))
                elif "Launch" in row or "실행" in row or "起動" in row or "启动" in row:
                    screen.append(ansi(text, "32;1"))
                else:
                    screen.append(text)
            if info_lines:
                screen.append("")
                screen.append(ansi("-" * min(120, max(72, columns - 4)), "38;5;208"))
                for line in info_lines:
                    screen.append(ansi(line, "1;38;5;208"))
            screen.append("")
            screen.append(ansi(footer or "Up/Down moves. Enter selects. Esc/q cancels.", "2"))
            rendered = "\n".join(screen) + "\n"
            sys.stdout.write("\033[2J\033[H" + rendered)
            sys.stdout.flush()
            key = read_menu_key(fd) if fd >= 0 else read_menu_key()
            if key in ("up", "k"):
                idx = (idx - 1) % len(rows)
            elif key in ("down", "j"):
                idx = (idx + 1) % len(rows)
            elif key == "enter":
                return idx
            elif key in ("esc", "q"):
                return None
    finally:
        if old_settings is not None:
            try:
                import termios
                termios.tcsetattr(fd, termios.TCSANOW, old_settings)
            except Exception:
                pass
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def pause() -> None:
    input("Press Enter to continue...")


def compact_text(value: Any, width: int = 72) -> str:
    return fit_cells(value, width)


def main_menu_rows(cfg: dict[str, Any], provider: str, pcfg: dict[str, Any], lang: str) -> list[str]:
    return [
        f"0. {ui_text('language', lang)}  [{LANGUAGES.get(lang, lang)}]",
        f"1. {ui_text('provider', lang)}  [{provider}]",
        f"2. {ui_text('api_key', lang)}  [{stored_api_key_mask(provider, pcfg)}]",
        f"3. {ui_text('base_url', lang)}  [{compact_text(pcfg.get('base_url', 'unset'), 62)}]",
        f"4. {ui_text('model', lang)}  [{compact_text(pcfg.get('current_model', 'unset'), 62)}]",
        f"5. {ui_text('advisor_model', lang)}  [{compact_text(pcfg.get('advisor_model') or 'off', 62)}]",
        f"6. {ui_text('options', lang)}  [{compact_text(llm_options_status(provider, pcfg), 62)}]",
        f"7. {ui_text('channel_delivery', lang)}  [{channel_delivery_mode(cfg)}]",
        f"8. {ui_text('log_level', lang)}  [{log_level_status()}]",
        f"9. {ui_text('test', lang)}",
        f"10. {ui_text('launch', lang)}",
        ui_text("quit", lang),
    ]


def provider_panel_rows(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows: list[str] = []
    values: list[str] = []
    current = cfg.get("current_provider", "nvidia-hosted")
    for key, label in PROVIDER_LABELS.items():
        pcfg = cfg.get("providers", {}).get(key, {})
        mark = "*" if key == current else " "
        rows.append(f"{mark} {label:<16} {key:<15} {compact_text(pcfg.get('base_url', ''), 54)}")
        values.append(key)
    return rows, values


def language_panel_rows(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows: list[str] = []
    values: list[str] = []
    current = cfg.get("language", "en")
    for code, label in LANGUAGES.items():
        mark = "*" if code == current else " "
        rows.append(f"{mark} {code:<2} {label}")
        values.append(code)
    return rows, values


def log_level_panel_rows(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows: list[str] = []
    values: list[str] = []
    current = log_level_name()
    descriptions = {
        "SILENT": "no router log writes",
        "ERROR": "errors only",
        "WARN": "warnings and errors",
        "INFO": "normal diagnostics",
        "DEBUG": "verbose diagnostics",
        "TRACE": "request/response trace detail",
    }
    for numeric in sorted(LOG_LEVEL_NAMES):
        name = LOG_LEVEL_NAMES[numeric]
        mark = "*" if name == current else " "
        rows.append(f"{mark} {name:<6} {numeric}  {descriptions.get(name, '')}")
        values.append(name)
    rows.append(f"Reset to default/env  [{log_level_status()}]")
    values.append("DEFAULT")
    rows.append(ui_text("back", cfg.get("language", "en")))
    values.append("back")
    return rows, values


def model_panel_rows(provider: str, pcfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    values = unique_model_ids(provider, upstream_model_ids(provider, pcfg))
    rows: list[str] = []
    current = pcfg.get("current_model")
    seen_aliases: set[str] = set()
    deduped_values: list[str] = []
    for mid in values:
        alias = alias_for(provider, mid)
        alias_key = alias.casefold()
        if alias_key in seen_aliases:
            continue
        seen_aliases.add(alias_key)
        deduped_values.append(mid)
        mark = "*" if mid == current else " "
        rows.append(f"{mark} {mid}  {alias}")
    rows.append("+ Custom model id...")
    deduped_values.append("__custom__")
    rows.append("Back")
    deduped_values.append("back")
    return rows, deduped_values


def advisor_model_panel_rows(provider: str, pcfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    values = unique_model_ids(provider, [m for m in DEFAULT_ADVISOR_MODELS if m] + upstream_model_ids(provider, pcfg))
    rows: list[str] = []
    current = pcfg.get("advisor_model", "")
    rows.append(("* Disable Advisor Model" if not current else "  Disable Advisor Model"))
    deduped_values = [""]
    seen: set[str] = set()
    for mid in values:
        if not mid or mid in seen:
            continue
        seen.add(mid)
        mark = "*" if mid == current else " "
        suffix = "  recommended for long context" if mid == "deepseek-v4-pro" else ""
        rows.append(f"{mark} {mid}{suffix}")
        deduped_values.append(mid)
    rows.append("+ Custom advisor model id...")
    deduped_values.append("__custom__")
    rows.append("Back")
    deduped_values.append("back")
    return rows, deduped_values


def channel_panel_rows(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    channels = channel_specs(cfg)
    rows: list[str] = []
    values: list[str] = []
    for name, spec in OFFICIAL_CHANNEL_PLUGINS.items():
        mark = "*" if spec in channels else " "
        rows.append(f"{mark} {name:<10} {spec}")
        values.append(spec)
    rows.append("+ Add custom channel...")
    values.append("__add_custom__")
    if channels:
        rows.append("- Remove channel...")
        values.append("__remove__")
        rows.append("Clear all channels")
        values.append("__clear__")
    rows.append("Back")
    values.append("back")
    return rows, values


def channel_delivery_panel_rows(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    current = channel_delivery_mode(cfg)
    rows = [
        f"{'*' if current == 'native' else ' '} native Claude Code claude/channel queue bridge",
        f"{'*' if current == 'stdin' else ' '} stdin  PTY wake proxy; works broadly, uses terminal input",
        "Back",
    ]
    return rows, ["native", "stdin", "back"]


def api_key_panel_rows(provider: str) -> tuple[list[str], list[str]]:
    rows = [
        "Type or paste API key as hidden input",
        "Read API key from an environment variable",
        "Read API key from clipboard",
        "Back",
    ]
    values = ["input", "env", "clipboard", "back"]
    if os.name != "nt":
        rows[2] = "Read API key from desktop clipboard if available"
    return rows, values


def base_url_panel_rows(provider: str, pcfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    return (
        [
            f"Edit Base URL  [{compact_text(pcfg.get('base_url') or default_base_url(provider), 72)}]",
            f"Reset to provider default  [{default_base_url(provider)}]",
            "Back",
        ],
        ["edit", "default", "back"],
    )


def visible_rows(rows: list[str], selected: int, limit: int) -> list[tuple[int | None, str]]:
    if len(rows) <= limit:
        return [(i, row) for i, row in enumerate(rows)]
    limit = max(4, limit)
    start = max(0, min(selected - limit // 2, len(rows) - limit))
    end = min(len(rows), start + limit)
    visible: list[tuple[int | None, str]] = []
    if start > 0:
        visible.append((None, f"... {start} above"))
    visible.extend((i, rows[i]) for i in range(start, end))
    if end < len(rows):
        visible.append((None, f"... {len(rows) - end} below"))
    return visible


def render_prelaunch_screen(
    main_idx: int,
    panel: str | None,
    panel_idx: int,
    panel_rows: list[str],
    checks: list[str],
    messages: list[str],
    first_render: bool,
) -> bool:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    lang = cfg.get("language", "en")
    columns, height = shutil.get_terminal_size((110, 32))
    render_width = max(40, columns - 1)
    screen: list[str] = []
    def add(text: str = "", code: str | None = None) -> None:
        # Redraws start at cursor home. Each row must overwrite the full
        # previous row; otherwise Windows cmd leaves stale text on the right.
        fitted = pad_cells(text, render_width)
        screen.append(ansi(fitted, code) if code else fitted)

    def add_rendered(visible_text: str, rendered_text: str) -> None:
        visible = fit_cells(visible_text, render_width)
        padding = " " * max(0, render_width - cell_width(visible))
        screen.append(rendered_text + padding)

    mode_line = f"mode: {provider_mode_label(provider, pcfg)}"
    title_text = f"Claude Any v{VERSION}"
    add_rendered(title_text, animated_ansi_text(title_text))
    add(CREDITS, "2")
    add("")
    add(f"provider: {provider}    language: {lang}    {mode_line}", "32")
    add(f"base_url: {pcfg.get('base_url')}", "2")
    add(f"model: {pcfg.get('current_model')}", "32")
    add(api_key_status_line(provider, pcfg), "2")
    add("")
    rows = main_menu_rows(cfg, provider, pcfg, lang)
    for i, row in enumerate(rows):
        line = ("> " if i == main_idx and panel is None else "  ") + row
        if i == main_idx and panel is None:
            add(line, "7;1")
        elif "Launch" in row or "실행" in row or "起動" in row or "启动" in row:
            add(line, "32;1")
        elif row == ui_text("quit", lang):
            add(line, "31")
        else:
            add(line)
    if panel:
        titles = {
            "language": "Language",
            "provider": "Provider",
            "api-key": "API key",
            "base-url": "Base URL",
            "model": "Model",
            "advisor-model": "Advisor Model",
            "test": "Compatibility test",
            "options": ui_text("options", lang),
            "channel-delivery": ui_text("channel_delivery", lang),
            "log-level": ui_text("log_level", lang),
            "channels": "Channels",
            "context": ui_text("context_setup", lang),
            "preset": ui_text("presets", lang),
            "timeout": ui_text("timeout_preset", lang),
        }
        add("")
        add("-" * render_width, "38;5;208")
        panel_title = titles.get(panel, panel)
        title_suffix = "" if panel_title.lower().endswith(("options", "presets", "setup", "설정", "옵션", "프리셋", "設定", "オプション", "プリセット", "设置", "选项", "预设")) else " options"
        add(f"{panel_title}{title_suffix}", "1;38;5;208")
        # Reserve an extra line for the per-row description when shown.
        description_reserve = 2 if panel == "options" else 0
        fixed = len(screen) + len(checks) + len(messages) + 5 + description_reserve
        limit = max(5, height - fixed)
        for actual, row in visible_rows(panel_rows, panel_idx, limit):
            if actual is None:
                add("    " + row, "2")
            elif actual == panel_idx:
                add("  > " + row, "7;1")
            else:
                add("    " + row)
        if panel == "options" and panel_rows:
            # Map panel_idx back to its option key, then show its localized
            # description below the panel so the user always sees the meaning of
            # the currently-highlighted row.
            try:
                _, panel_values = llm_option_panel_rows(provider, pcfg, lang)
            except Exception:
                panel_values = []
            current_key = panel_values[panel_idx] if 0 <= panel_idx < len(panel_values) else ""
            description = llm_option_description_for_value(provider, pcfg, current_key, lang) if current_key else ""
            add("")
            if description:
                add("  " + description, "2")
            else:
                add("")
    if messages:
        add("")
        for line in messages[-8:]:
            add("  " + line, "36;1")
    if checks:
        add("")
        add("-" * render_width, "38;5;208")
        for line in checks[:2]:
            add("  " + line, "1;38;5;208")
    add("")
    help_text = "Up/Down moves. Enter selects. Esc/Left closes submenu. q quits. Actions expand in place."
    add(help_text, "2")
    rendered = "\n".join(screen) + "\n"
    if sys.stdout.isatty():
        prefix = "\033[2J\033[H" if first_render else "\033[H"
        sys.stdout.write(prefix + rendered + "\033[J")
        sys.stdout.flush()
    else:
        print(rendered, end="")
    return False


def _prompt_menu_value_raw(label: str, default: str = "", secret: bool = False) -> str | None:
    if os.name == "nt" or not sys.stdin.isatty():
        return None
    try:
        import codecs
        import select
        import termios
    except Exception:
        return None
    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
        new_settings = termios.tcgetattr(fd)
        new_settings[3] = new_settings[3] & ~(termios.ECHO | termios.ICANON)
        new_settings[6][termios.VMIN] = 1
        new_settings[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, new_settings)
    except Exception:
        return None

    chars: list[str] = []
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        sys.stdout.write("\n" + ansi(label, "1;38;5;208"))
        sys.stdout.flush()
        while True:
            first = os.read(fd, 1)
            if not first:
                continue
            data = bytearray(first)
            try:
                while select.select([fd], [], [], 0)[0]:
                    more = os.read(fd, 4096)
                    if not more:
                        break
                    data.extend(more)
            except Exception:
                pass

            display: list[str] = []
            done = False
            for byte in data:
                b = bytes((byte,))
                if b in (b"\r", b"\n"):
                    display.append("\n")
                    done = True
                    break
                if b in (b"\x03",):
                    raise KeyboardInterrupt
                if b in (b"\x04", b"\x1b"):
                    display.append("\n")
                    sys.stdout.write("".join(display))
                    sys.stdout.flush()
                    return default
                if b in (b"\x7f", b"\x08"):
                    if chars:
                        chars.pop()
                        if not secret:
                            display.append("\b \b")
                    continue
                if b == b"\x15":
                    if chars and not secret:
                        display.append("\b \b" * len(chars))
                    chars.clear()
                    continue
                if byte < 0x20:
                    continue
                text = decoder.decode(b)
                if not text:
                    continue
                for ch in text:
                    if ch in ("\ufffd", "\r", "\n"):
                        continue
                    chars.append(ch)
                    if not secret:
                        display.append(ch)
            if display:
                sys.stdout.write("".join(display))
                sys.stdout.flush()
            if done:
                break
        return "".join(chars).strip() or default
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)
        except Exception:
            pass


def prompt_menu_value(prompt: str, default: str = "", secret: bool = False, restore_tty: Callable[[], None] | None = None, raw_tty: Callable[[], None] | None = None) -> str:
    label = f"{prompt}"
    if default:
        label += f" [{default}]"
    label += ": "
    if restore_tty:
        restore_tty()
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    try:
        raw_value = _prompt_menu_value_raw(label, default, secret)
        if raw_value is not None:
            value = raw_value
        else:
            sys.stdout.write("\n" + ansi(label, "1;38;5;208"))
            sys.stdout.flush()
            if secret:
                value = getpass.getpass("")
            else:
                value = input()
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
        if raw_tty:
            raw_tty()
    value = value.strip()
    return value or default


def portable_provider_menu() -> int:
    cfg = load_config()
    rows, values = provider_panel_rows(cfg)
    selected = portable_select("Select claude-any provider", rows, values.index(cfg.get("current_provider", "nvidia-hosted")))
    if selected is None:
        print("Cancelled.")
        return 1
    for line in set_provider_config(values[selected]):
        print(line)
    return 0


def portable_language_menu() -> int:
    cfg = load_config()
    rows, values = language_panel_rows(cfg)
    selected = portable_select("Select display language", rows, values.index(cfg.get("language", "en")))
    if selected is None:
        print("Cancelled.")
        return 1
    cfg["language"] = values[selected]
    save_config(cfg)
    print(f"Language set to {values[selected]} ({LANGUAGES[values[selected]]}).")
    return 0


def portable_prelaunch_menu() -> int:
    enable_ansi()
    main_idx = 10 if settings_ready_except_api_key() else 0
    panel: str | None = None
    panel_idx = 0
    panel_rows: list[str] = []
    panel_values: list[str] = []
    panel_last_idx: dict[str, int] = {}
    checks = preflight_lines()
    messages: list[str] = []
    first_render = True

    def open_panel(name: str) -> None:
        nonlocal panel, panel_idx, panel_rows, panel_values, messages, first_render
        cfg = load_config()
        provider, pcfg = get_current_provider(cfg)
        panel = name
        panel_idx = panel_last_idx.get(name, 0)
        if name == "language":
            panel_rows, panel_values = language_panel_rows(cfg)
            panel_idx = panel_values.index(cfg.get("language", "en"))
        elif name == "provider":
            panel_rows, panel_values = provider_panel_rows(cfg)
            panel_idx = panel_values.index(provider)
        elif name == "api-key":
            panel_rows, panel_values = api_key_panel_rows(provider)
        elif name == "base-url":
            panel_rows, panel_values = base_url_panel_rows(provider, pcfg)
        elif name == "model":
            panel_rows, panel_values = ["Loading models from current provider..."], []
            first_render = render_prelaunch_screen(main_idx, panel, panel_idx, panel_rows, checks, messages, first_render)
            try:
                panel_rows, panel_values = model_panel_rows(provider, pcfg)
            except Exception as exc:
                panel_rows, panel_values = [f"Model list failed: {type(exc).__name__}: {exc}", "+ Custom model id..."], []
        elif name == "advisor-model":
            try:
                panel_rows, panel_values = advisor_model_panel_rows(provider, pcfg)
            except Exception as exc:
                panel_rows, panel_values = [f"Advisor model list failed: {type(exc).__name__}: {exc}", "+ Custom advisor model id..."], []
        elif name == "test":
            panel_rows, panel_values = ["Run compatibility test", "Back"], ["run", "back"]
        elif name == "options":
            panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
        elif name == "channel-delivery":
            panel_rows, panel_values = channel_delivery_panel_rows(cfg)
        elif name == "log-level":
            panel_rows, panel_values = log_level_panel_rows(cfg)
        elif name == "channels":
            panel_rows, panel_values = channel_panel_rows(cfg)
        elif name == "context":
            panel_rows, panel_values = context_setup_panel_rows(provider, pcfg, cfg.get("language", "en"))
        elif name == "preset":
            panel_rows, panel_values = llm_preset_panel_rows(provider, pcfg, cfg.get("language", "en"))
        elif name == "timeout":
            panel_rows, panel_values = timeout_profile_panel_rows(pcfg, cfg.get("language", "en"))
        if panel_rows:
            panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))

    def close_panel(next_idx: int | None = None) -> None:
        nonlocal panel, panel_idx, panel_rows, panel_values, main_idx
        if panel:
            panel_last_idx[panel] = panel_idx
        panel = None
        panel_idx = 0
        panel_rows = []
        panel_values = []
        if next_idx is not None:
            main_idx = next_idx

    def refresh_checks() -> None:
        nonlocal checks
        checks = preflight_lines()

    fd = sys.stdin.fileno()
    old_settings = None
    if os.name != "nt" and os.isatty(fd):
        try:
            import termios
            old_settings = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new)
        except Exception:
            fd = -1
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
    def restore_line_mode() -> None:
        if old_settings is not None and fd >= 0:
            try:
                import termios
                termios.tcsetattr(fd, termios.TCSANOW, old_settings)
            except Exception:
                pass

    def restore_raw_mode() -> None:
        if old_settings is not None and fd >= 0:
            try:
                import termios
                new = termios.tcgetattr(fd)
                new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
                new[6][termios.VMIN] = 1
                new[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, new)
            except Exception:
                pass

    try:
        while True:
            first_render = render_prelaunch_screen(main_idx, panel, panel_idx, panel_rows, checks, messages, first_render)
            key = read_menu_key(fd) if fd >= 0 else read_menu_key()
            if panel:
                panel_name = panel
                if key in ("up", "k"):
                    panel_idx = (panel_idx - 1) % max(1, len(panel_rows))
                    panel_last_idx[panel_name] = panel_idx
                    continue
                if key in ("down", "j"):
                    panel_idx = (panel_idx + 1) % max(1, len(panel_rows))
                    panel_last_idx[panel_name] = panel_idx
                    continue
                if key in ("esc", "left", "q"):
                    close_panel()
                    continue
                if key != "enter":
                    continue
                cfg = load_config()
                provider, pcfg = get_current_provider(cfg)
                value = panel_values[panel_idx] if panel_idx < len(panel_values) else ""
                if panel == "language" and value:
                    cfg["language"] = value
                    save_config(cfg)
                    messages = [f"Language set to {value} ({LANGUAGES[value]})."]
                    refresh_checks()
                    close_panel(1)
                elif panel == "provider" and value:
                    messages = set_provider_config(value)
                    refresh_checks()
                    main_idx = 4
                    open_panel("model")
                elif panel == "model":
                    if value == "back":
                        close_panel()
                        continue
                    if value == "__custom__" or panel_idx >= len(panel_values):
                        model_value = prompt_menu_value("Model id or alias", restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                    else:
                        model_value = value
                    if model_value:
                        messages = set_model_config(model_value)
                        refresh_checks()
                    close_panel(5)
                elif panel == "advisor-model":
                    if value == "back":
                        close_panel()
                        continue
                    if value == "__custom__" or panel_idx >= len(panel_values):
                        advisor_value = prompt_menu_value("Advisor model id", "deepseek-v4-pro", restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                    else:
                        advisor_value = value
                    messages = set_advisor_model_config(advisor_value)
                    refresh_checks()
                    close_panel(6)
                elif panel == "api-key":
                    if value == "back":
                        close_panel()
                    elif value == "input":
                        key_value = prompt_menu_value(f"API key for {provider}", secret=True, restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        if key_value:
                            messages = store_api_key_config(provider, key_value)
                            refresh_checks()
                        close_panel(3)
                    elif value == "env":
                        default_env = {
                            "anthropic": "ANTHROPIC_API_KEY",
                            "nvidia-hosted": "NVIDIA_API_KEY",
                            "ollama-cloud": "OLLAMA_API_KEY",
                        }.get(provider, "API_KEY")
                        env_name = prompt_menu_value("Environment variable name", default_env, restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        key_value = os.environ.get(env_name, "").strip()
                        if key_value:
                            messages = store_api_key_config(provider, key_value)
                        else:
                            messages = [f"Environment variable {env_name} is empty or not set."]
                        refresh_checks()
                        close_panel(3)
                    elif value == "clipboard":
                        key_value = read_clipboard_text()
                        if not key_value:
                            messages = ["Clipboard did not contain readable text."]
                        else:
                            confirm = prompt_menu_value(f"Clipboard contains {mask_secret(key_value)}. Store it? y/N", restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                            if confirm.lower().startswith("y"):
                                messages = store_api_key_config(provider, key_value)
                            else:
                                messages = ["Clipboard API key was not stored."]
                        refresh_checks()
                        close_panel(3)
                elif panel == "base-url":
                    if value == "back":
                        close_panel()
                    elif value == "default":
                        messages = set_base_url_config(provider, default_base_url(provider))
                        refresh_checks()
                        close_panel(4)
                    elif value == "edit":
                        default = pcfg.get("base_url") or default_base_url(provider)
                        url = prompt_menu_value(f"Base URL for {provider}", default, restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        if url:
                            messages = set_base_url_config(provider, url)
                            refresh_checks()
                        close_panel(4)
                elif panel == "test":
                    if value == "back":
                        close_panel()
                    else:
                        panel_rows, panel_values = ["Testing current provider/model..."], []
                        first_render = render_prelaunch_screen(main_idx, panel, 0, panel_rows, checks, messages, first_render)
                        _, out = self_cmd(["test"])
                        lines = [line for line in out.splitlines() if line.strip()]
                        messages = lines[-8:] if lines else ["Test produced no output."]
                        panel_rows, panel_values = ["Run compatibility test again", "Back"], ["run", "back"]
                        refresh_checks()
                        main_idx = 10 if "Compatibility: OK" in out else 4
                elif panel == "log-level":
                    if value == "back":
                        close_panel()
                    elif value:
                        messages = set_log_level_config(value)
                        refresh_checks()
                        cfg = load_config()
                        panel_rows, panel_values = log_level_panel_rows(cfg)
                        panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))
                elif panel == "channel-delivery":
                    if value == "back":
                        close_panel()
                    elif value:
                        messages = set_channel_delivery_config(value)
                        refresh_checks()
                        cfg = load_config()
                        panel_rows, panel_values = channel_delivery_panel_rows(cfg)
                        panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))
                elif panel == "channels":
                    if value == "back":
                        close_panel()
                    elif value == "__add_custom__":
                        spec = prompt_menu_value("Channel spec (for example plugin:ainet@local or server:ainet)", restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        if spec:
                            messages = add_channel_spec(spec)
                            cfg = load_config()
                            panel_rows, panel_values = channel_panel_rows(cfg)
                    elif value == "__remove__":
                        spec = prompt_menu_value("Channel spec to remove", "", restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        if spec:
                            messages = remove_channel_spec(spec)
                            cfg = load_config()
                            panel_rows, panel_values = channel_panel_rows(cfg)
                    elif value == "__clear__":
                        messages = clear_channel_specs()
                        cfg = load_config()
                        panel_rows, panel_values = channel_panel_rows(cfg)
                        panel_idx = 0
                    elif value:
                        if value in channel_specs(cfg):
                            messages = remove_channel_spec(value)
                        else:
                            messages = add_channel_spec(value)
                        cfg = load_config()
                        panel_rows, panel_values = channel_panel_rows(cfg)
                    refresh_checks()
                elif panel == "options":
                    if value == "back":
                        close_panel()
                    elif value == "context_setup":
                        open_panel("context")
                    elif value == "preset":
                        open_panel("preset")
                    elif value == "timeout_profile":
                        open_panel("timeout")
                    elif value in LLM_OPTION_TOGGLE_KEYS:
                        # Boolean toggles flip on Enter — no input prompt.
                        current = llm_option_current_bool(provider, pcfg, value)
                        try:
                            messages = set_llm_option_config(provider, value, "false" if current else "true")
                        except Exception as exc:
                            messages = [f"Option update failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        old_idx = panel_idx
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                        panel_idx = max(0, min(old_idx, len(panel_rows) - 1))
                        panel_last_idx["options"] = panel_idx
                    else:
                        default = llm_option_prompt_default(provider, pcfg, value)
                        entered = prompt_menu_value(f"{value} for {provider} (default/unset clears)", default, restore_tty=restore_line_mode, raw_tty=restore_raw_mode)
                        try:
                            messages = set_llm_option_config(provider, value, entered)
                        except Exception as exc:
                            messages = [f"Option update failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        old_idx = panel_idx
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                        panel_idx = max(0, min(old_idx, len(panel_rows) - 1))
                        panel_last_idx["options"] = panel_idx
                elif panel == "context":
                    if value == "back":
                        open_panel("options")
                    elif value == "__info__":
                        continue
                    else:
                        try:
                            messages = apply_context_setup_config(provider, value)
                        except Exception as exc:
                            messages = [f"Context setup failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        panel = "options"
                        panel_idx = panel_last_idx.get("options", 0)
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                        panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))
                        panel_last_idx["options"] = panel_idx
                elif panel == "preset":
                    if value == "back":
                        open_panel("options")
                    elif value == "__info__":
                        continue
                    else:
                        try:
                            messages = apply_llm_preset_config(provider, value)
                        except Exception as exc:
                            messages = [f"Preset failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        panel = "options"
                        panel_idx = panel_last_idx.get("options", 0)
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                        panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))
                        panel_last_idx["options"] = panel_idx
                elif panel == "timeout":
                    if value == "back":
                        open_panel("options")
                    elif value == "__info__":
                        continue
                    else:
                        try:
                            cfg = load_config()
                            provider, pcfg = get_current_provider(cfg)
                            messages = apply_timeout_profile_to_provider(pcfg, value, cfg.get("language", "en"))
                            save_config(cfg)
                            clear_model_cache()
                        except Exception as exc:
                            messages = [f"Timeout preset failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        panel = "options"
                        panel_idx = panel_last_idx.get("options", 0)
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                        panel_idx = max(0, min(panel_idx, len(panel_rows) - 1))
                        panel_last_idx["options"] = panel_idx
                continue

            if key in ("up", "k"):
                cfg = load_config()
                provider, pcfg = get_current_provider(cfg)
                main_idx = (main_idx - 1) % len(main_menu_rows(cfg, provider, pcfg, cfg.get("language", "en")))
            elif key in ("down", "j"):
                cfg = load_config()
                provider, pcfg = get_current_provider(cfg)
                main_idx = (main_idx + 1) % len(main_menu_rows(cfg, provider, pcfg, cfg.get("language", "en")))
            elif key in ("esc", "q"):
                return 10
            elif key == "enter":
                actions = ["language", "provider", "api-key", "base-url", "model", "advisor-model", "options", "channel-delivery", "log-level", "test", "launch", "quit"]
                action = actions[main_idx]
                if action == "launch":
                    blockers = launch_readiness_errors()
                    if blockers:
                        messages = blockers
                        refresh_checks()
                        continue
                    return 0
                if action == "quit":
                    return 10
                open_panel(action)
    finally:
        if old_settings is not None:
            try:
                import termios
                termios.tcsetattr(fd, termios.TCSANOW, old_settings)
            except Exception:
                pass
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def run_external_menu(name: str) -> int | None:
    if os.name == "nt":
        return None
    exe = find_executable(name)
    if not exe:
        return None
    return subprocess.call([exe])


def has_noninteractive_claude_args(passthrough: list[str]) -> bool:
    return any(arg == "-p" or arg == "--print" or arg.startswith("--print=") for arg in passthrough)


def run_prelaunch_menu(passthrough: list[str], skip_menu: bool = False, force_menu: bool = False) -> int:
    if not force_menu and (
        skip_menu or has_noninteractive_claude_args(passthrough) or os.environ.get("CLAUDE_ANY_SKIP_MENU") == "1"
    ):
        return 0
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return 0
    if os.environ.get("CLAUDE_ANY_USE_LEGACY_MENU") == "1":
        rc = run_external_menu("claude-any-menu")
        if rc is not None:
            return rc
    return portable_prelaunch_menu()


def start_router_if_needed() -> None:
    if router_up():
        return
    stop_router_processes(quiet=True)
    if router_up():
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), "serve"]
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if flags:
            kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    with open(LOG_PATH, "ab", buffering=0) as log:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **kwargs)
    deadline = time.time() + 30
    while time.time() < deadline:
        if router_up():
            return
        time.sleep(0.5)
    raise RuntimeError(f"claude-any router did not start. See {LOG_PATH}")


def should_attach_web_search(provider: str, cfg: dict[str, Any], override: bool | None) -> bool:
    if override is not None:
        return override
    return provider != "anthropic" and bool(cfg.get("web_search", {}).get("auto_for_non_native", True))


def should_append_compat_prompt(provider: str, cfg: dict[str, Any]) -> bool:
    return provider != "anthropic" and bool(cfg.get("claude_code", {}).get("compat_prompt_for_non_anthropic", True))


def has_passthrough_option(passthrough: list[str], *names: str) -> bool:
    return any(arg in names or any(arg.startswith(name + "=") for name in names) for arg in passthrough)


def normalize_channel_passthrough(passthrough: list[str]) -> list[str]:
    normalized: list[str] = []
    i = 0
    while i < len(passthrough):
        arg = passthrough[i]
        if arg == "--channels":
            normalized.append("--dangerously-load-development-channels")
            i += 1
            while i < len(passthrough) and is_channel_spec_tagged(passthrough[i]):
                normalized.append(passthrough[i])
                i += 1
            continue
        if arg.startswith("--channels="):
            value = arg.split("=", 1)[1].strip()
            if value:
                normalized.extend(["--dangerously-load-development-channels", value])
            else:
                normalized.append("--dangerously-load-development-channels")
            i += 1
            continue
        normalized.append(arg)
        i += 1
    return normalized


def native_channel_passthrough_requested(passthrough: list[str]) -> bool:
    return has_passthrough_option(passthrough, "--channels", "--dangerously-load-development-channels")


def claude_channel_args(cfg: dict[str, Any], passthrough: list[str], extra_specs: list[str] | None = None) -> list[str]:
    return []


def claude_channels_requested(cfg: dict[str, Any], passthrough: list[str], extra_specs: list[str] | None = None) -> bool:
    return native_channel_passthrough_requested(passthrough)


def should_use_native_channel_bridge(use_router_mode: bool, cfg: dict[str, Any], passthrough: list[str]) -> bool:
    return bool(use_router_mode and channel_delivery_mode(cfg) == "native" and not native_channel_passthrough_requested(passthrough))


def write_web_tools_mcp_config(cfg: dict[str, Any]) -> Path:
    web = cfg.get("web_search", {})
    package = web.get("package") or "ddg-mcp-search"
    npx = find_executable("npx") or ("npx.cmd" if os.name == "nt" else "npx")
    servers: dict[str, Any] = {
        "duckduckgo": {
            "command": npx,
            "args": ["-y", package],
        }
    }
    if web.get("fetch_enabled", True):
        fetch_args = [web.get("fetch_package") or "mcp-server-fetch"]
        if web.get("fetch_user_agent"):
            fetch_args.extend(["--user-agent", str(web["fetch_user_agent"])])
        if web.get("fetch_ignore_robots_txt", False):
            fetch_args.append("--ignore-robots-txt")
        fetch_command = find_executable("uvx")
        fetch_command_args = fetch_args
        if not fetch_command:
            uv = find_executable("uv")
            if uv:
                fetch_command = uv
                fetch_command_args = ["tool", "run", *fetch_args]
            elif importlib.util.find_spec("uv") is not None:
                fetch_command = sys.executable
                fetch_command_args = ["-m", "uv", "tool", "run", *fetch_args]
            else:
                pipx = find_executable("pipx")
                if pipx:
                    fetch_command = pipx
                    fetch_command_args = ["run", *fetch_args]
        if fetch_command:
            servers["web_fetch"] = {
                "command": fetch_command,
                "args": fetch_command_args,
                "claude_any_stdio": "jsonl",
            }
        else:
            router_log("WARN", "web_fetch_disabled_missing_runner install=uvx_or_uv")
    data = {"mcpServers": servers}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WEB_TOOLS_MCP_CONFIG.write_text(json.dumps(data, indent=2) + "\n")
    try:
        os.chmod(WEB_TOOLS_MCP_CONFIG, 0o600)
    except Exception:
        pass
    return WEB_TOOLS_MCP_CONFIG


def write_duckduckgo_mcp_config(cfg: dict[str, Any]) -> Path:
    path = write_web_tools_mcp_config(cfg)
    try:
        DUCKDUCKGO_MCP_CONFIG.write_text(path.read_text())
    except Exception:
        pass
    return path


def write_channel_mcp_config() -> Path:
    data = {
        "mcpServers": {
            "claude-any-router": {
                "type": "sse",
                "url": f"{ROUTER_BASE}/ca/mcp/sse",
            }
        }
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CHANNEL_MCP_CONFIG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(CHANNEL_MCP_CONFIG, 0o600)
    except Exception:
        pass
    _channel_mcp_ensure_cursor_initialized()
    return CHANNEL_MCP_CONFIG


def write_mcp_proxy_config(
    passthrough: list[str],
    *,
    extra_config_paths: list[Path | str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Path | None:
    cwd = cwd or Path.cwd()
    extra = [Path(item).expanduser() for item in (extra_config_paths or [])]
    paths = [*extra, *claude_mcp_config_paths(passthrough, cwd, home)]
    servers: dict[str, Any] = {}
    seen: set[str] = set()
    server_dir = CONFIG_DIR / "mcp-proxy-servers"
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        for name, server in _read_mcp_servers_from_json(path, cwd):
            if name in seen:
                continue
            seen.add(name)
            if _mcp_server_is_stdio(server):
                server_dir.mkdir(parents=True, exist_ok=True)
                server_path = server_dir / f"{_safe_mcp_proxy_name(name)}.json"
                server_path.write_text(json.dumps(server, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                try:
                    os.chmod(server_path, 0o600)
                except Exception:
                    pass
                servers[name] = {
                    "command": sys.executable,
                    "args": [
                        str(Path(__file__).resolve()),
                        "mcp-proxy",
                        "--server-name",
                        name,
                        "--server-config",
                        str(server_path),
                    ],
                }
            else:
                servers[name] = server
    if not servers:
        return None
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MCP_PROXY_CONFIG.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(MCP_PROXY_CONFIG, 0o600)
    except Exception:
        pass
    router_log("INFO", f"mcp_proxy_config_written servers={','.join(sorted(servers))}")
    return MCP_PROXY_CONFIG


def should_use_channel_stdin_proxy(use_router_mode: bool, passthrough: list[str], cfg: dict[str, Any] | None = None) -> bool:
    if not use_router_mode or native_channel_passthrough_requested(passthrough):
        return False
    if cfg is not None and channel_delivery_mode(cfg) == "native":
        return False
    return True


def format_channel_wake_prompt(message: dict[str, Any]) -> str:
    channel = str(message.get("channel") or "default")
    sender = str(message.get("sender_id") or "channel")
    mid = str(message.get("id") or "")
    meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
    room = str(meta.get("room_id") or meta.get("room") or channel)
    thread = str(message.get("thread_id") or meta.get("thread_id") or "")
    body = re.sub(r"\s+", " ", str(message.get("message") or "")).strip()
    fields = [f"channel={channel}", f"room={room}", f"from={sender}"]
    if mid:
        fields.append(f"id={mid}")
    if thread:
        fields.append(f"thread={thread}")
    meta_text = f" metadata={_compact_json_for_prompt(meta)}" if meta else ""
    return (
        "[claude-any external channel message] "
        + " ".join(fields)
        + f" text={json.dumps(body, ensure_ascii=False)}"
        + meta_text
        + ". "
        + "If relevant to current work, respond or act now; otherwise keep working."
    )


def _channel_wake_message_noise_reason(message: dict[str, Any]) -> str | None:
    body = re.sub(r"\s+", " ", str(message.get("message") or "")).strip().lower()
    kind = str(message.get("kind") or "").strip().lower()
    if not body:
        return "empty"
    if kind in {"connection", "connected", "heartbeat", "keepalive"}:
        return kind
    if re.fullmatch(r"[a-z0-9_.:-]{1,80}\.(ws|sse)\.connected", body):
        return "transport_connected"
    return None


def _channel_wake_message_is_noise(message: dict[str, Any]) -> bool:
    return _channel_wake_message_noise_reason(message) is not None


def format_channel_wake_batch_prompt(messages: list[dict[str, Any]]) -> str:
    if len(messages) == 1:
        return format_channel_wake_prompt(messages[0])
    parts: list[str] = []
    for message in messages:
        channel = str(message.get("channel") or "default")
        sender = str(message.get("sender_id") or "channel")
        mid = str(message.get("id") or "")
        meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
        room = str(meta.get("room_id") or meta.get("room") or channel)
        thread = str(message.get("thread_id") or meta.get("thread_id") or "")
        body = re.sub(r"\s+", " ", str(message.get("message") or "")).strip()
        fields = [f"id={mid}", f"room={room}", f"from={sender}"]
        if thread:
            fields.append(f"thread={thread}")
        meta_text = f" metadata={_compact_json_for_prompt(meta)}" if meta else ""
        parts.append("(" + " ".join(fields) + ") " + json.dumps(body, ensure_ascii=False) + meta_text)
    return (
        f"[claude-any external channel messages] {len(messages)} new messages: "
        + " ; ".join(parts)
        + ". If relevant to current work, respond or act now; otherwise keep working."
    )


def _write_fd_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _channel_platform_default_enter_bytes(platform: str | None = None, os_name: str | None = None) -> bytes:
    sys_platform = str(platform if platform is not None else sys.platform).lower()
    os_family = str(os_name if os_name is not None else os.name).lower()
    if os_family == "nt" or sys_platform.startswith(("win", "cygwin", "msys")):
        return b"\r\n"
    if os_family == "posix":
        return b"\r\n"
    return b"\r\n"


def _channel_wake_enter_bytes(value: str | bytes | None = None) -> bytes:
    raw: str | bytes | None = value
    if raw is None:
        raw = os.environ.get("CLAUDE_ANY_CHANNEL_WAKE_ENTER")
        if raw is None:
            return _channel_platform_default_enter_bytes()
    if isinstance(raw, bytes):
        return raw if raw in (b"\n", b"\r", b"\r\n") else _channel_platform_default_enter_bytes()
    normalized = str(raw or "").strip().lower()
    if normalized in {"", "auto", "default", "platform"}:
        return _channel_platform_default_enter_bytes()
    if normalized in {"lf", "nl", "newline", "linefeed", "\\n"}:
        return b"\n"
    if normalized in {"cr", "return", "carriage-return", "carriage_return", "\\r"}:
        return b"\r"
    if normalized in {"crlf", "cr-lf", "return-newline", "\\r\\n"}:
        return b"\r\n"
    return _channel_platform_default_enter_bytes()


def _channel_wake_enter_env_is_fixed() -> bool:
    raw = os.environ.get("CLAUDE_ANY_CHANNEL_WAKE_ENTER")
    if raw is None:
        return False
    return str(raw).strip().lower() not in {"", "auto", "default", "platform"}


def _channel_enter_bytes_from_user_input(data: bytes) -> bytes | None:
    if not data:
        return None
    if data in (b"\n", b"\r", b"\r\n"):
        return data
    last_lf = data.rfind(b"\n")
    last_cr = data.rfind(b"\r")
    if last_lf < 0 and last_cr < 0:
        return None
    if last_lf > last_cr:
        return b"\r\n" if last_lf > 0 and data[last_lf - 1 : last_lf] == b"\r" else b"\n"
    return b"\r\n" if last_cr + 1 < len(data) and data[last_cr + 1 : last_cr + 2] == b"\n" else b"\r"


def _channel_synthetic_enter_bytes_from_user_input(data: bytes) -> bytes | None:
    observed = _channel_enter_bytes_from_user_input(data)
    if observed == b"\r":
        # Bare CR is common from raw POSIX terminals, but synthetic CR-only
        # writes can sit in Claude Code's line editor on some PTY stacks.
        return b"\r\n"
    return observed


def _channel_enter_label(enter_bytes: bytes) -> str:
    if enter_bytes == b"\r":
        return "cr"
    if enter_bytes == b"\r\n":
        return "crlf"
    return "lf"


def _channel_wake_input_bytes(prompt: str, enter_bytes: bytes | None = None) -> bytes:
    # Ctrl-U clears any stale line editor text before submitting the synthetic prompt.
    # Claude Code's interactive input is terminal-driven; the submit byte can
    # differ by PTY/input stack, so callers pass the observed Enter sequence.
    return b"\x15" + prompt.encode("utf-8", errors="replace") + _channel_wake_enter_bytes(enter_bytes)


def _inject_pending_channel_messages(master_fd: int, last_id: int, enter_bytes: bytes | None = None) -> int:
    pending: list[dict[str, Any]] = []
    for message in read_chat_messages(last_id, None, None, 100):
        try:
            last_id = max(last_id, int(message.get("id") or 0))
        except Exception:
            continue
        noise_reason = _channel_wake_message_noise_reason(message)
        if noise_reason:
            router_log(
                "INFO",
                f"channel_stdin_proxy_skipped_noise message_id={message.get('id')} channel={message.get('channel')} reason={noise_reason}",
            )
            continue
        pending.append(message)
    if pending:
        prompt = format_channel_wake_batch_prompt(pending)
        submit_bytes = _channel_wake_enter_bytes(enter_bytes)
        _write_fd_all(master_fd, _channel_wake_input_bytes(prompt, submit_bytes))
        ids = ",".join(str(message.get("id") or "") for message in pending)
        channels = ",".join(sorted({str(message.get("channel") or "default") for message in pending}))
        router_log(
            "INFO",
            f"channel_stdin_proxy_injected count={len(pending)} message_ids={ids} channels={channels} enter={_channel_enter_label(submit_bytes)}",
        )
    return last_id


def _chat_messages_file_marker() -> tuple[float, int]:
    try:
        stat = CHAT_MESSAGES_PATH.stat()
        return (stat.st_mtime, stat.st_size)
    except Exception:
        return (0.0, 0)


def subprocess_call_with_channel_wake_proxy(cmd: list[str], env: dict[str, str]) -> int:
    if os.name != "posix" or not sys.stdin.isatty() or not sys.stdout.isatty():
        router_log("INFO", "channel_stdin_proxy_unavailable; using direct subprocess call")
        return subprocess.call(cmd, env=env)
    import pty
    import select
    import termios
    import tty

    last_id = _chat_init_next_id() - 1
    last_channel_marker = _chat_messages_file_marker()
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, env=env, close_fds=True)
    os.close(slave_fd)
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    old_attrs = termios.tcgetattr(stdin_fd)
    last_channel_poll = 0.0
    channel_enter_bytes = _channel_wake_enter_bytes()
    router_log(
        "INFO",
        f"channel_stdin_proxy_enter_default enter={_channel_enter_label(channel_enter_bytes)} os={os.name} platform={sys.platform}",
    )
    try:
        tty.setraw(stdin_fd)
        while proc.poll() is None:
            try:
                readable, _, _ = select.select([stdin_fd, master_fd], [], [], 0.2)
            except OSError:
                break
            if stdin_fd in readable:
                data = os.read(stdin_fd, 4096)
                if data:
                    observed_enter = _channel_synthetic_enter_bytes_from_user_input(data)
                    if observed_enter and not _channel_wake_enter_env_is_fixed():
                        if observed_enter != channel_enter_bytes:
                            router_log(
                                "INFO",
                                f"channel_stdin_proxy_enter_observed enter={_channel_enter_label(observed_enter)}",
                            )
                        channel_enter_bytes = observed_enter
                    _write_fd_all(master_fd, data)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if data:
                    _write_fd_all(stdout_fd, data)
            now = time.time()
            if now - last_channel_poll >= 0.5:
                last_channel_poll = now
                marker = _chat_messages_file_marker()
                if marker != last_channel_marker:
                    last_channel_marker = marker
                    last_id = _inject_pending_channel_messages(master_fd, last_id, channel_enter_bytes)
        while True:
            try:
                readable, _, _ = select.select([master_fd], [], [], 0)
                if master_fd not in readable:
                    break
                data = os.read(master_fd, 4096)
                if not data:
                    break
                _write_fd_all(stdout_fd, data)
            except OSError:
                break
        return proc.returncode if proc.returncode is not None else 0
    finally:
        try:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_attrs)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass


def _mcp_proxy_notification_payload(server_name: str, message: dict[str, Any]) -> dict[str, Any] | None:
    method = str(message.get("method") or "").strip()
    if not method.startswith("notifications/"):
        return None
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    payload = params.get("payload") if isinstance(params.get("payload"), dict) else {}
    data = params.get("data") if isinstance(params.get("data"), dict) else {}
    event = params.get("event") if isinstance(params.get("event"), dict) else {}
    meta: dict[str, Any] = {
        "mcp_server": server_name,
        "mcp_method": method,
        "mcp_json": _json_safe_metadata(message),
    }
    if message.get("jsonrpc") is not None:
        meta["jsonrpc"] = message.get("jsonrpc")
    if message.get("id") is not None:
        meta["rpc_id"] = message.get("id")
    meta.update(_event_meta_from_sources(message, params, payload, data, event))
    content = (
        _event_payload_text(params)
        or _event_payload_text(payload)
        or _event_payload_text(data)
        or _event_payload_text(event)
    )
    if not content and params:
        content = json.dumps(params, ensure_ascii=False, separators=(",", ":"), default=str)
    if not content:
        return None
    channel = str(meta.get("channel") or meta.get("room_id") or meta.get("room") or server_name)
    return {
        "channel": channel,
        "sender_id": str(meta.get("sender_id") or meta.get("agent_id") or server_name),
        "recipients": meta.get("recipient_id") or "all",
        "thread_id": meta.get("thread_id"),
        "parent_id": meta.get("parent_id"),
        "kind": method.replace("notifications/claude/", "").replace("notifications/", "").replace("/", "."),
        "message": content,
        "meta": meta,
    }


def _mcp_proxy_notification_dedupe_key(server_name: str, chat_payload: dict[str, Any]) -> str:
    meta = chat_payload.get("meta") if isinstance(chat_payload.get("meta"), dict) else {}
    body = re.sub(r"\s+", " ", str(chat_payload.get("message") or "")).strip()
    room = str(meta.get("room_id") or meta.get("room") or chat_payload.get("channel") or server_name)
    sender = str(chat_payload.get("sender_id") or meta.get("sender_id") or meta.get("agent_id") or server_name)
    thread = str(chat_payload.get("thread_id") or meta.get("thread_id") or "")
    parent = str(chat_payload.get("parent_id") or meta.get("parent_id") or "")
    event_id = ""
    for key in ("message_id", "event_id", "cursor", "sequence", "seq"):
        value = meta.get(key)
        if value is not None and str(value).strip():
            event_id = str(value).strip()
            break
    return json.dumps(
        [server_name, room, sender, thread, parent, event_id, body],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _mcp_proxy_should_skip_duplicate_notification(server_name: str, chat_payload: dict[str, Any]) -> tuple[bool, str | None]:
    meta = chat_payload.get("meta") if isinstance(chat_payload.get("meta"), dict) else {}
    method = str(meta.get("mcp_method") or "")
    if not method.startswith("notifications/"):
        return False, None
    key = _mcp_proxy_notification_dedupe_key(server_name, chat_payload)
    now = time.time()
    with _MCP_NOTIFICATION_DEDUP_LOCK:
        stale = [
            item_key
            for item_key, (_, seen_at) in _MCP_NOTIFICATION_DEDUP_RECENT.items()
            if now - seen_at > _MCP_NOTIFICATION_DEDUP_TTL_SECONDS
        ]
        for item_key in stale:
            _MCP_NOTIFICATION_DEDUP_RECENT.pop(item_key, None)
        previous = _MCP_NOTIFICATION_DEDUP_RECENT.get(key)
        _MCP_NOTIFICATION_DEDUP_RECENT[key] = (method, now)
    if not previous:
        return False, None
    previous_method, previous_seen_at = previous
    is_native_pair = _NATIVE_CHANNEL_NOTIFICATION_METHOD in {previous_method, method}
    if previous_method != method and is_native_pair and now - previous_seen_at <= _MCP_NOTIFICATION_DEDUP_TTL_SECONDS:
        return True, previous_method
    return False, None


def _mcp_proxy_observe_json_message(server_name: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    chat_payload = _mcp_proxy_notification_payload(server_name, payload)
    if not chat_payload:
        return
    skip_duplicate, previous_method = _mcp_proxy_should_skip_duplicate_notification(server_name, chat_payload)
    if skip_duplicate:
        router_log(
            "INFO",
            f"mcp_proxy_notification_skipped_duplicate server={server_name} method={payload.get('method')} previous_method={previous_method}",
        )
        return
    try:
        saved = append_chat_message(chat_payload)
        router_log(
            "INFO",
            f"mcp_proxy_notification server={server_name} method={payload.get('method')} message_id={saved.get('id')}",
        )
    except Exception as exc:
        router_log("WARN", f"mcp_proxy_notification_failed server={server_name} error={type(exc).__name__}: {exc}")


def _mcp_proxy_observe_stdout_line(server_name: str, line: bytes) -> None:
    try:
        text = line.decode("utf-8", errors="replace").strip()
        if not text or not text.startswith("{"):
            return
        payload = json.loads(text)
    except Exception:
        return
    _mcp_proxy_observe_json_message(server_name, payload)


def _mcp_proxy_header_end(buffer: bytes) -> tuple[int, int] | None:
    crlf = buffer.find(b"\r\n\r\n")
    lf = buffer.find(b"\n\n")
    candidates: list[tuple[int, int]] = []
    if crlf >= 0:
        candidates.append((crlf, 4))
    if lf >= 0:
        candidates.append((lf, 2))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def _mcp_proxy_frame_header(buffer: bytes) -> tuple[int, int, int] | None:
    header = _mcp_proxy_header_end(buffer)
    if not header:
        return None
    header_end, delimiter_len = header
    length = _mcp_proxy_content_length(buffer[:header_end])
    if length is None:
        return None
    return header_end, delimiter_len, length


def _mcp_proxy_content_length(header_bytes: bytes) -> int | None:
    try:
        header_text = header_bytes.decode("ascii", errors="replace")
    except Exception:
        return None
    for line in re.split(r"\r?\n", header_text):
        name, sep, value = line.partition(":")
        if sep and name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except Exception:
                return None
            return length if length >= 0 else None
    return None


class _McpStdoutObserver:
    def __init__(self, server_name: str) -> None:
        self.server_name = server_name
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self.buffer.extend(chunk)
        self._drain()

    def _drop_until_candidate(self) -> bool:
        data = bytes(self.buffer)
        if not data:
            return False
        stripped = data.lstrip()
        if len(stripped) != len(data):
            del self.buffer[: len(data) - len(stripped)]
            data = stripped
        if _mcp_proxy_frame_header(data) or data.startswith(b"{"):
            return True
        lowered = data.lower()
        content_idx = lowered.find(b"content-length:")
        json_idx = data.find(b"{")
        candidates = [idx for idx in (content_idx, json_idx) if idx >= 0]
        newline_idx = data.find(b"\n")
        if candidates:
            keep_from = min(candidates)
            if newline_idx >= 0 and newline_idx < keep_from:
                del self.buffer[: newline_idx + 1]
            elif keep_from > 0:
                del self.buffer[:keep_from]
            return True
        if newline_idx >= 0:
            del self.buffer[: newline_idx + 1]
            return True
        if len(self.buffer) > 1024 * 1024:
            del self.buffer[:-4096]
        return False

    def _drain(self) -> None:
        while self.buffer:
            if not self._drop_until_candidate():
                return
            data = bytes(self.buffer)
            frame = _mcp_proxy_frame_header(data)
            if frame:
                header_end, delimiter_len, length = frame
                body_start = header_end + delimiter_len
                body_end = body_start + length
                if len(data) < body_end:
                    return
                body = data[body_start:body_end]
                del self.buffer[:body_end]
                try:
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                except Exception:
                    continue
                _mcp_proxy_observe_json_message(self.server_name, payload)
                continue
            if data.startswith(b"{"):
                newline_idx = data.find(b"\n")
                if newline_idx < 0:
                    return
                line = data[:newline_idx]
                del self.buffer[: newline_idx + 1]
                _mcp_proxy_observe_stdout_line(self.server_name, line)
                continue
            return


def _mcp_proxy_forward_stdin(proc: subprocess.Popen[bytes]) -> None:
    try:
        stdin_fd = sys.stdin.fileno()
        while True:
            chunk = os.read(stdin_fd, 65536)
            if not chunk:
                break
            if proc.stdin:
                proc.stdin.write(chunk)
                proc.stdin.flush()
    except Exception:
        pass
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass


def _mcp_proxy_stdio_mode(server: dict[str, Any]) -> str:
    mode = str(server.get("claude_any_stdio") or server.get("stdio_mode") or "").strip().lower()
    if mode in ("jsonl", "json-lines", "json_lines", "newline-json", "line-json"):
        return "jsonl"
    return "framed"


def _mcp_proxy_write_proc_jsonl(proc: subprocess.Popen[bytes], body: bytes) -> None:
    line = body.strip()
    if not line or not proc.stdin:
        return
    proc.stdin.write(line + b"\n")
    proc.stdin.flush()


def _mcp_proxy_drain_stdin_jsonl_buffer(proc: subprocess.Popen[bytes], buffer: bytearray, *, final: bool = False) -> None:
    while buffer:
        data = bytes(buffer)
        stripped = data.lstrip()
        if len(stripped) != len(data):
            del buffer[: len(data) - len(stripped)]
            data = stripped
        frame = _mcp_proxy_frame_header(data)
        if frame:
            header_end, delimiter_len, length = frame
            body_start = header_end + delimiter_len
            body_end = body_start + length
            if len(data) < body_end:
                return
            body = data[body_start:body_end]
            del buffer[:body_end]
            _mcp_proxy_write_proc_jsonl(proc, body)
            continue
        if data.startswith(b"{"):
            newline_idx = data.find(b"\n")
            if newline_idx >= 0:
                line = data[:newline_idx]
                del buffer[: newline_idx + 1]
                _mcp_proxy_write_proc_jsonl(proc, line)
                continue
            if final:
                del buffer[:]
                _mcp_proxy_write_proc_jsonl(proc, data)
            return
        lowered = data.lower()
        content_idx = lowered.find(b"content-length:")
        json_idx = data.find(b"{")
        candidates = [idx for idx in (content_idx, json_idx) if idx >= 0]
        newline_idx = data.find(b"\n")
        if candidates:
            keep_from = min(candidates)
            if keep_from > 0:
                del buffer[:keep_from]
            continue
        if newline_idx >= 0:
            del buffer[: newline_idx + 1]
            continue
        if len(buffer) > 1024 * 1024:
            del buffer[:-4096]
        return


def _mcp_proxy_forward_stdin_jsonl(proc: subprocess.Popen[bytes]) -> None:
    buffer = bytearray()
    try:
        stdin_fd = sys.stdin.fileno()
        while True:
            chunk = os.read(stdin_fd, 65536)
            if not chunk:
                break
            buffer.extend(chunk)
            _mcp_proxy_drain_stdin_jsonl_buffer(proc, buffer)
        _mcp_proxy_drain_stdin_jsonl_buffer(proc, buffer, final=True)
    except Exception:
        pass
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass


def _mcp_proxy_write_stdout_frame(body: bytes) -> None:
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()


def _mcp_proxy_emit_jsonl_stdout_line(server_name: str, line: bytes) -> None:
    body = line.strip()
    if not body:
        return
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        try:
            sys.stderr.buffer.write(body + b"\n")
            sys.stderr.buffer.flush()
        except Exception:
            pass
        return
    _mcp_proxy_observe_json_message(server_name, payload)
    _mcp_proxy_write_stdout_frame(body)


def _mcp_proxy_forward_stdout_jsonl(server_name: str, proc: subprocess.Popen[bytes]) -> None:
    if not proc.stdout:
        return
    buffer = bytearray()
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buffer.extend(chunk)
        while True:
            newline_idx = buffer.find(b"\n")
            if newline_idx < 0:
                break
            line = bytes(buffer[:newline_idx])
            del buffer[: newline_idx + 1]
            _mcp_proxy_emit_jsonl_stdout_line(server_name, line)
    if buffer.strip():
        _mcp_proxy_emit_jsonl_stdout_line(server_name, bytes(buffer))


def _mcp_proxy_forward_stderr(proc: subprocess.Popen[bytes]) -> None:
    try:
        if not proc.stderr:
            return
        while True:
            chunk = proc.stderr.read(4096)
            if not chunk:
                break
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()
    except Exception:
        pass


def run_mcp_stdio_proxy(server_name: str, server_config_path: Path) -> int:
    try:
        server = json.loads(server_config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        router_log("ERROR", f"mcp_proxy_config_read_failed server={server_name} error={type(exc).__name__}: {exc}")
        print(f"claude-any mcp-proxy: cannot read server config: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2
    if not isinstance(server, dict) or not _mcp_server_is_stdio(server):
        router_log("ERROR", f"mcp_proxy_invalid_config server={server_name}")
        print("claude-any mcp-proxy: server config is not a stdio MCP server", file=sys.stderr, flush=True)
        return 2
    command = str(server.get("command") or "").strip()
    args = [str(item) for item in server.get("args", [])] if isinstance(server.get("args"), list) else []
    command, args = resolve_mcp_server_process(command, args)
    env = os.environ.copy()
    raw_env = server.get("env")
    if isinstance(raw_env, dict):
        env.update({str(k): str(v) for k, v in raw_env.items() if str(k)})
    cwd_value = server.get("cwd") or server.get("workingDirectory")
    cwd = str(cwd_value) if cwd_value else None
    try:
        proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            bufsize=0,
        )
    except Exception as exc:
        router_log("ERROR", f"mcp_proxy_start_failed server={server_name} command={command} error={type(exc).__name__}: {exc}")
        print(f"claude-any mcp-proxy: failed to start {command}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 127
    stdio_mode = _mcp_proxy_stdio_mode(server)
    router_log("INFO", f"mcp_proxy_started server={server_name} command={command} stdio={stdio_mode}")
    stdin_target = _mcp_proxy_forward_stdin_jsonl if stdio_mode == "jsonl" else _mcp_proxy_forward_stdin
    threading.Thread(target=stdin_target, args=(proc,), daemon=True, name=f"mcp-proxy-stdin-{server_name}").start()
    threading.Thread(target=_mcp_proxy_forward_stderr, args=(proc,), daemon=True, name=f"mcp-proxy-stderr-{server_name}").start()
    try:
        if stdio_mode == "jsonl":
            _mcp_proxy_forward_stdout_jsonl(server_name, proc)
        elif proc.stdout:
            observer = _McpStdoutObserver(server_name)
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                observer.feed(chunk)
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        rc = proc.wait()
        level = "INFO" if rc == 0 else "WARN"
        router_log(level, f"mcp_proxy_exited server={server_name} rc={rc}")
        return rc
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass


def cmd_mcp_proxy(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="claude-any mcp-proxy")
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--server-config", required=True)
    args = parser.parse_args(argv)
    return run_mcp_stdio_proxy(args.server_name, Path(args.server_config).expanduser())


def run_claude_update_check(claude: str, enabled: bool = True) -> None:
    if not enabled:
        return
    if os.environ.get("CLAUDE_ANY_SKIP_CLAUDE_UPDATE") == "1":
        return
    print("Checking Claude Code update before launch...", flush=True)
    current = claude_code_current_version(claude)
    if current:
        print(f"Current Claude Code version: {current}", flush=True)
    npm = find_executable("npm")
    if not npm:
        print("Claude Code update check skipped: npm was not found.", flush=True)
        return
    package_spec = os.environ.get("CLAUDE_ANY_CLAUDE_CODE_PACKAGE", "@anthropic-ai/claude-code@latest")
    latest = npm_latest_package_version(npm, package_spec)
    if not latest:
        print("Claude Code update check could not read the latest npm version; continuing.", flush=True)
        return
    if current and not version_newer(latest, current):
        print(f"Claude Code is up to date ({current}).", flush=True)
        return
    current_label = current or "unknown"
    print(f"Claude Code update available: {current_label} -> {latest}", flush=True)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Claude Code update requires confirmation; skipping in non-interactive mode.", flush=True)
        return
    answer = input("Update Claude Code now with `claude update`? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        return
    update_env = os.environ.copy()
    local_bin = str(HOME / ".local" / "bin")
    update_env["PATH"] = local_bin + os.pathsep + update_env.get("PATH", "")
    try:
        p = subprocess.run(
            [claude, "update"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=update_env,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        print("Claude Code update timed out; continuing with current version.", flush=True)
        return
    except Exception as exc:
        print(f"Claude Code update failed ({type(exc).__name__}); continuing.", flush=True)
        return
    out = (p.stdout or "").strip()
    if out:
        print(out, flush=True)
    if p.returncode != 0:
        print(f"Claude Code update exited with {p.returncode}; continuing with current version.", flush=True)
        return
    new_version = claude_code_current_version(find_executable("claude") or claude)
    if new_version:
        print(f"Claude Code version after update: {new_version}", flush=True)


def parse_version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in re.split(r"[^0-9]+", value.strip()):
        if item:
            parts.append(int(item))
    return tuple(parts)


def version_newer(latest: str, current: str) -> bool:
    left = list(parse_version_tuple(latest))
    right = list(parse_version_tuple(current))
    size = max(len(left), len(right), 1)
    left.extend([0] * (size - len(left)))
    right.extend([0] * (size - len(right)))
    return tuple(left) > tuple(right)


def npm_latest_package_version(npm: str, package_spec: str, timeout: float = 8.0) -> str:
    try:
        p = subprocess.run(
            [npm, "view", package_spec, "version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    out = (p.stdout or "").strip()
    return out.splitlines()[-1].strip() if out else ""


def npm_global_package_root(npm: str, package_name: str = "@oneciel-ai/claude-any", timeout: float = 8.0) -> Path | None:
    try:
        p = subprocess.run(
            [npm, "root", "-g"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    root = (p.stdout or "").strip()
    if not root:
        return None
    package_path = Path(root)
    for part in package_name.split("/"):
        if part:
            package_path /= part
    return package_path


def claude_code_current_version(claude: str) -> str:
    try:
        p = subprocess.run(
            [claude, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
        )
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    match = re.search(r"\d+(?:\.\d+)+", p.stdout or "")
    return match.group(0) if match else ""


def running_from_npm_package() -> bool:
    if os.environ.get("CLAUDE_ANY_NPM_MODE") is not None:
        return True
    path = str(Path(__file__).resolve()).replace("\\", "/")
    return "/node_modules/@oneciel-ai/claude-any/" in path


def claude_any_restart_user_args() -> list[str]:
    args = list(sys.argv[1:])
    if args and args[0] == "cli":
        return args[1:]
    return args


def restart_claude_any_after_update(npm: str) -> None:
    os.environ["CLAUDE_ANY_SKIP_SELF_UPDATE"] = "1"
    user_args = claude_any_restart_user_args()
    package_root = npm_global_package_root(npm)
    package_script = package_root / "claude_any.py" if package_root else None
    if package_script and package_script.exists():
        os.execv(sys.executable, [sys.executable, str(package_script), "cli", *user_args])
    launcher = find_executable("claude-any")
    if launcher:
        raise SystemExit(subprocess.call([launcher, *user_args], env=os.environ.copy()))
    os.execv(sys.executable, [sys.executable, *sys.argv])


def run_claude_any_update_check(enabled: bool = True) -> bool:
    if not enabled:
        return False
    if os.environ.get("CLAUDE_ANY_SKIP_SELF_UPDATE") == "1":
        return False
    if env_bool(os.environ.get("CLAUDE_ANY_SELF_UPDATE_CHECK")) is False:
        return False
    if not running_from_npm_package():
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    npm = find_executable("npm")
    if not npm:
        return False
    latest = npm_latest_package_version(npm, "@oneciel-ai/claude-any@latest")
    if not latest or not version_newer(latest, VERSION):
        return False
    print(f"Claude Any update available: {VERSION} -> {latest}", flush=True)
    answer = input("Update now with npm? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        return False
    try:
        update = subprocess.run(
            [npm, "install", "-g", "@oneciel-ai/claude-any@latest"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("Claude Any update timed out; continuing with current version.", flush=True)
        return False
    except Exception as exc:
        print(f"Claude Any update failed ({type(exc).__name__}); continuing.", flush=True)
        return False
    out = (update.stdout or "").strip()
    if out:
        print(out, flush=True)
    if update.returncode != 0:
        print(f"Claude Any update exited with {update.returncode}; continuing with current version.", flush=True)
        return False
    print("Claude Any updated. Restarting with the new version...", flush=True)
    try:
        restart_claude_any_after_update(npm)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Restart failed ({type(exc).__name__}); continuing with the current process.", flush=True)
    return True


def run_command_for_upgrade(cmd: list[str], timeout: float = 300.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout or "").strip()


def quiet_upgrade_claude_any() -> int:
    npm = find_executable("npm")
    if not npm:
        print("Claude Any update skipped: npm was not found.", flush=True)
        return 1
    latest = npm_latest_package_version(npm, "@oneciel-ai/claude-any@latest")
    if latest and not version_newer(latest, VERSION):
        print(f"Claude Any is up to date ({VERSION}).", flush=True)
        return 0
    target = latest or "latest"
    print(f"Updating Claude Any to {target}...", flush=True)
    rc, out = run_command_for_upgrade([npm, "install", "-g", "@oneciel-ai/claude-any@latest"], timeout=300)
    if out:
        print(out, flush=True)
    if rc != 0:
        print(f"Claude Any update failed ({rc}).", flush=True)
    return rc


def quiet_upgrade_claude_code() -> int:
    claude = find_executable("claude")
    if not claude:
        print("Claude Code update skipped: claude executable was not found.", flush=True)
        return 1
    current = claude_code_current_version(claude)
    npm = find_executable("npm")
    latest = ""
    if npm:
        package_spec = os.environ.get("CLAUDE_ANY_CLAUDE_CODE_PACKAGE", "@anthropic-ai/claude-code@latest")
        latest = npm_latest_package_version(npm, package_spec)
    if current and latest and not version_newer(latest, current):
        print(f"Claude Code is up to date ({current}).", flush=True)
        return 0
    target = latest or "latest"
    current_label = current or "unknown"
    print(f"Updating Claude Code ({current_label} -> {target})...", flush=True)
    rc, out = run_command_for_upgrade([claude, "update"], timeout=180)
    if out:
        print(out, flush=True)
    if rc != 0:
        print(f"Claude Code update failed ({rc}).", flush=True)
    return rc


def run_quiet_upgrade_and_exit() -> int:
    any_rc = quiet_upgrade_claude_any()
    claude_rc = quiet_upgrade_claude_code()
    return 0 if any_rc == 0 and claude_rc == 0 else 1


def launch_claude(
    passthrough: list[str],
    skip_menu: bool = False,
    force_menu: bool = False,
    web_search_override: bool | None = None,
    update_check: bool = True,
    self_update_check: bool = True,
) -> int:
    if has_noninteractive_claude_args(passthrough):
        update_check = False
        self_update_check = False
    run_claude_any_update_check(enabled=self_update_check)
    rc = run_prelaunch_menu(passthrough, skip_menu=skip_menu, force_menu=force_menu)
    if rc == 10:
        return 0
    if rc != 0:
        return rc
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    blockers = launch_readiness_errors(cfg)
    if blockers:
        print("Claude Any launch blocked:", flush=True)
        for line in blockers:
            print(f"- {line}", flush=True)
        return 2
    use_native_anthropic = native_anthropic_enabled(provider)
    use_ollama_native = ollama_native_compat_enabled(provider, pcfg)
    use_provider_native = provider_native_compat_enabled(provider, pcfg)
    use_router_mode = not (use_native_anthropic or use_ollama_native or use_provider_native)
    cleanup_managed_services_for_provider(provider, pcfg, cfg, quiet=True)
    if use_router_mode:
        start_router_if_needed()
    env = os.environ.copy()
    env["PATH"] = str(HOME / ".local" / "bin") + os.pathsep + env.get("PATH", "")
    launch_env = env_vars(cfg)
    launch_passthrough = normalize_channel_passthrough(passthrough)
    native_channel_bridge = should_use_native_channel_bridge(use_router_mode, cfg, launch_passthrough)
    stdin_channel_proxy = should_use_channel_stdin_proxy(use_router_mode, launch_passthrough, cfg)
    if claude_channels_requested(cfg, launch_passthrough) or native_channel_bridge:
        env.pop("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", None)
        launch_env.pop("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", None)
    if use_native_anthropic:
        for key in (
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "CLAUDE_CODE_SUBAGENT_MODEL",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
        ):
            env.pop(key, None)
        if "ANTHROPIC_API_KEY" in launch_env:
            env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.update(launch_env)
    if not use_native_anthropic:
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            if key not in launch_env:
                env.pop(key, None)
        install_claude_any_slash_commands()
        install_tool_guard_hooks()
        install_claude_any_statusline()
    claude = find_executable("claude")
    if not claude:
        raise RuntimeError("claude executable was not found in PATH or ~/.local/bin")
    run_claude_update_check(claude, enabled=update_check)
    claude = find_executable("claude") or claude
    extra_args: list[str] = []
    mcp_config_paths: list[str] = []
    if should_attach_web_search(provider, cfg, web_search_override):
        mcp_config_paths.append(str(write_duckduckgo_mcp_config(cfg)))
    if native_channel_bridge:
        mcp_config_paths.append(str(write_channel_mcp_config()))
    claude_passthrough = list(launch_passthrough)
    if stdin_channel_proxy or native_channel_bridge:
        auto_start_sse_channels_from_mcp_configs(launch_passthrough)
        proxy_config = write_mcp_proxy_config(
            launch_passthrough,
            extra_config_paths=[Path(path) for path in mcp_config_paths],
        )
        if proxy_config:
            mcp_config_paths = [str(proxy_config)]
            claude_passthrough = strip_mcp_config_passthrough(launch_passthrough)
    if mcp_config_paths:
        extra_args.extend(["--mcp-config", *mcp_config_paths])
    if should_append_compat_prompt(provider, cfg) and not has_passthrough_option(launch_passthrough, "--system-prompt"):
        extra_args.extend(["--append-system-prompt", NON_ANTHROPIC_COMPAT_PROMPT])
    extra_args.extend(claude_channel_args(cfg, launch_passthrough))
    cmd = [
        claude,
        "--dangerously-skip-permissions",
    ]
    model = env.get("CLAUDE_ANY_MODEL_ALIAS")
    if model:
        cmd.extend(["--model", model])
    cmd.extend(extra_args)
    cmd.extend(claude_passthrough)
    if stdin_channel_proxy:
        return subprocess_call_with_channel_wake_proxy(cmd, env)
    return subprocess.call(cmd, env=env)


def cli_usage() -> str:
    return """Usage:
  claude-any                         Launch Claude Code through claude-any router

Control plane, runs before Claude Code and does not require LLM connectivity:
  claude-any version                 Print claude-any version
  claude-any language [en|ko|ja|zh] Set display language
  claude-any provider                Pick provider with arrow-key TUI
  claude-any provider list           List providers
  claude-any provider PROVIDER       Set provider
  claude-any base-url PROVIDER URL   Set provider base URL
  claude-any model MODEL_ID          Set current provider model
  claude-any advisor-model MODEL_ID  Set current provider advisor model (off disables)
  claude-any models [PROVIDER]       List models
  claude-any api-key PROVIDER        Store API key securely
  claude-any set-api-key PROVIDER KEY
  claude-any web-search [on|off]     Auto-attach DuckDuckGo MCP for non-native providers
  claude-any web-fetch [on|off]      Auto-attach fetch MCP for web page content
  claude-any log-level [LEVEL]       Show or set router log level
  claude-any channels [cmd]          Configure external channel specs
  claude-any channel-delivery [stdin|native]
                                      Select PTY wake proxy or native claude/channel bridge
  claude-any ollama-native [on|off]  Use Ollama's official Claude Code env path
  claude-any ollama-options [provider] [key=value ...]
                                      Set Ollama num_ctx/options/keep_alive/think
  claude-any provider-options [provider] [key=value ...]
                                      Set vLLM/NIM/NVIDIA output/context/timeouts
  claude-any ollama-catalog          Download Ollama model/context catalog
  claude-any test [seconds] [mode]   Test compatibility; mode is auto, quick, smoke, or full
  claude-any stop                    Stop router/proxy

Headless setup flags, namespaced to avoid Claude CLI collisions:
  claude-any --ca-provider PROVIDER  Set provider, then launch
  claude-any --ca-env-file PATH      Load CLAUDE_ANY_* values from a .env file
  claude-any --ca-menu               Apply setup values, then open the menu
  claude-any --ca-language en|ko|ja|zh
  claude-any --ca-base-url URL       Set current provider base URL, then launch
  claude-any --ca-model MODEL_ID     Set provider model, then launch
  claude-any --ca-advisor-model MODEL_ID
  claude-any --ca-auto-llm-options [MODEL_ID]
                                      Apply recommended LLM options for MODEL_ID or the saved model
  claude-any --ca-api-key KEY        Set current provider API key, then launch
  claude-any --ca-api-key-env ENVVAR Set current provider API key from env, then launch
  claude-any --ca-set-api-key PROVIDER KEY
  claude-any --ca-set-api-key-env PROVIDER ENVVAR
  claude-any --ca-ollama-num-ctx VALUE
  claude-any --ca-ollama-ctx-range MIN MAX
  claude-any --ca-ollama-option KEY=VALUE
  claude-any --ca-max-output-tokens VALUE
  claude-any --ca-context-window VALUE
  claude-any --ca-request-timeout-ms VALUE
  claude-any --ca-stream-idle-timeout-ms VALUE
  claude-any --ca-rate-limit-rpm VALUE
  claude-any --ca-rate-limit-status on|off
  claude-any --ca-stream on|off
  claude-any --ca-stream-word-chunking on|off
  claude-any --ca-log-level LEVEL    Set router log level: SILENT, ERROR, WARN, INFO, DEBUG, TRACE
  claude-any --ca-web-search         Force DuckDuckGo MCP for this launch
  claude-any --ca-no-web-search      Disable DuckDuckGo MCP for this launch
  claude-any --ca-web-fetch          Enable fetch MCP
  claude-any --ca-no-web-fetch       Disable fetch MCP
  claude-any --ca-channel SPEC       Add an official/approved Claude Code channel
  claude-any --ca-channel-delivery MODE
                                      Set channel delivery: stdin or native
  claude-any --ca-clear-channels     Clear saved channel specs
  claude-any --ca-no-self-update-check
                                      Skip Claude Any npm self-update check
  claude-any --ca-no-update-check    Skip Claude Code update check for this launch
  claude-any --ca-upgrade-and-exit   Update Claude Any and Claude Code without prompts, then exit
  claude-any --ca-no-launch          Apply setup flags/env values, then exit without launching Claude
  claude-any --ca-stop               Stop router/proxy
  claude-any --                      Pass all following args directly to Claude Code

Provider names: anthropic, ollama, ollama-cloud, vllm, nvidia-hosted, self-hosted-nim
Any other arguments are passed through to claude. Use -- before Claude flags that
collide with claude-any setup flags."""


def pop_headless_env_file_args(argv: list[str]) -> list[str]:
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--ca-env-file" or arg.startswith("--ca-env-file="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing path for --ca-env-file")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            path = Path(value).expanduser()
            if not path.exists():
                raise SystemExit(f"--ca-env-file not found: {path}")
            load_dotenv_into_environ(path, override=True)
        else:
            cleaned.append(arg)
            i += 1
    return cleaned


def apply_headless_env_config() -> tuple[bool, bool | None, bool | None, bool | None, bool]:
    skip_menu = os.environ.get("CLAUDE_ANY_SKIP_MENU") == "1"
    force_menu = bool(env_bool(os.environ.get("CLAUDE_ANY_FORCE_MENU"), False))
    web_search_override = env_bool(os.environ.get("CLAUDE_ANY_WEB_SEARCH"))
    update_check_override = env_bool(os.environ.get("CLAUDE_ANY_UPDATE_CHECK"))
    self_update_check_override = env_bool(os.environ.get("CLAUDE_ANY_SELF_UPDATE_CHECK"))
    language = os.environ.get("CLAUDE_ANY_LANGUAGE", "").strip()
    if language:
        cmd_language(argparse.Namespace(value=language))
        skip_menu = True
    web_fetch = env_bool(os.environ.get("CLAUDE_ANY_WEB_FETCH"))
    if web_fetch is not None:
        cmd_web_fetch(argparse.Namespace(value="on" if web_fetch else "off"))
        skip_menu = True
    provider = os.environ.get("CLAUDE_ANY_PROVIDER", "").strip()
    if provider:
        cmd_provider(argparse.Namespace(name=provider))
        skip_menu = True
    api_key_env = os.environ.get("CLAUDE_ANY_API_KEY_ENV", "").strip()
    api_key = os.environ.get("CLAUDE_ANY_API_KEY", "").strip()
    current_provider, _ = get_current_provider(load_config())
    if api_key_env:
        value = os.environ.get(api_key_env, "")
        if not value:
            raise SystemExit(f"Environment variable {api_key_env} is empty or not set")
        cmd_set_api_key(argparse.Namespace(provider=current_provider, key=value))
        skip_menu = True
    elif api_key:
        cmd_set_api_key(argparse.Namespace(provider=current_provider, key=api_key))
        skip_menu = True
    base_url = os.environ.get("CLAUDE_ANY_BASE_URL", "").strip()
    if base_url:
        current_provider, _ = get_current_provider(load_config())
        cmd_base_url(argparse.Namespace(provider=current_provider, url=base_url))
        skip_menu = True
    model = os.environ.get("CLAUDE_ANY_MODEL", "").strip()
    if model:
        cmd_model(argparse.Namespace(value=[model]))
        skip_menu = True
    advisor_model = os.environ.get("CLAUDE_ANY_ADVISOR_MODEL", "").strip()
    if advisor_model:
        set_advisor_model_config(advisor_model)
        skip_menu = True
    provider_option_keys = {
        "CLAUDE_ANY_MAX_OUTPUT_TOKENS": "max_output_tokens",
        "CLAUDE_ANY_CONTEXT_WINDOW": "context_window",
        "CLAUDE_ANY_REQUEST_TIMEOUT_MS": "request_timeout_ms",
        "CLAUDE_ANY_STREAM_IDLE_TIMEOUT_MS": "stream_idle_timeout_ms",
        "CLAUDE_ANY_RATE_LIMIT_RPM": "rate_limit_rpm",
        "CLAUDE_ANY_RATE_LIMIT_STATUS": "rate_limit_status",
        "CLAUDE_ANY_STREAM": "stream_enabled",
        "CLAUDE_ANY_STREAM_WORD_CHUNKING": "stream_word_chunking",
    }
    provider_values = [
        f"{option_key}={os.environ[env_key].strip()}"
        for env_key, option_key in provider_option_keys.items()
        if os.environ.get(env_key, "").strip()
    ]
    if provider_values:
        cmd_provider_options(argparse.Namespace(values=provider_values))
        skip_menu = True
    ollama_values: list[str] = []
    if os.environ.get("CLAUDE_ANY_OLLAMA_NUM_CTX", "").strip():
        ollama_values.append(f"num_ctx={os.environ['CLAUDE_ANY_OLLAMA_NUM_CTX'].strip()}")
    for item in os.environ.get("CLAUDE_ANY_OLLAMA_OPTIONS", "").replace(",", " ").split():
        if item.strip():
            ollama_values.append(item.strip())
    if ollama_values:
        cmd_ollama_options(argparse.Namespace(values=ollama_values))
        skip_menu = True
    channel_values = [
        item.strip()
        for item in re.split(r"[\s,]+", os.environ.get("CLAUDE_ANY_CHANNELS", "").strip())
        if item.strip()
    ]
    for channel_value in channel_values:
        add_channel_spec(channel_value)
        skip_menu = True
    dev_channel_values = [
        item.strip()
        for item in re.split(r"[\s,]+", os.environ.get("CLAUDE_ANY_DEV_CHANNELS", "").strip())
        if item.strip()
    ]
    for channel_value in dev_channel_values:
        add_channel_spec(channel_value)
        skip_menu = True
    channel_delivery = os.environ.get("CLAUDE_ANY_CHANNEL_DELIVERY", "").strip()
    if channel_delivery:
        set_channel_delivery_config(channel_delivery)
        skip_menu = True
    return skip_menu, web_search_override, update_check_override, self_update_check_override, force_menu


def run_cli(argv: list[str]) -> int:
    if argv and argv[0] == "mcp-proxy":
        return cmd_mcp_proxy(argv[1:])
    if argv and argv[0] in ("help", "--help", "-h"):
        print(cli_usage())
        return 0
    argv = pop_headless_env_file_args(argv)
    if any(arg in ("--ca-upgrade-and-exit", "--ca-quiet-upgrade", "--ca-upgrade-exit") for arg in argv):
        return run_quiet_upgrade_and_exit()
    if argv:
        head, rest = argv[0], argv[1:]
        if head in ("version", "--version", "-v"):
            print(f"claude-any {VERSION}")
            return 0
        if head in ("language", "lang"):
            cmd_language(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head == "provider":
            if not rest:
                rc = run_external_menu("claude-any-provider")
                return portable_provider_menu() if rc is None else rc
            if rest[0] in ("list", "ls"):
                cmd_provider(argparse.Namespace(name=None))
                return 0
            cmd_provider(argparse.Namespace(name=rest[0]))
            return 0
        if head == "model":
            if not rest:
                raise SystemExit("Missing model id")
            cmd_model(argparse.Namespace(value=rest))
            return 0
        if head in ("advisor-model", "advisormodel", "advisor"):
            cmd_advisor_model(argparse.Namespace(value=rest))
            return 0
        if head == "base-url":
            if len(rest) < 2:
                raise SystemExit("Usage: claude-any base-url PROVIDER URL")
            cmd_base_url(argparse.Namespace(provider=rest[0], url=rest[1]))
            return 0
        if head == "models":
            cmd_models(argparse.Namespace(provider=rest[0] if rest else None))
            return 0
        if head in ("api-key", "apikey"):
            if not rest:
                raise SystemExit("Missing provider")
            cmd_api_key(argparse.Namespace(provider=rest[0]))
            return 0
        if head in ("set-api-key", "set-apikey"):
            if len(rest) < 2:
                raise SystemExit("Usage: claude-any set-api-key PROVIDER KEY")
            cmd_set_api_key(argparse.Namespace(provider=rest[0], key=rest[1]))
            return 0
        if head in ("web-search", "websearch"):
            cmd_web_search(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head in ("web-fetch", "webfetch"):
            cmd_web_fetch(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head in ("log-level", "loglevel", "logging"):
            cmd_log_level(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head in ("channels", "channel"):
            cmd_channels(argparse.Namespace(values=rest))
            return 0
        if head in ("channel-delivery", "channel_delivery"):
            if rest:
                for line in set_channel_delivery_config(rest[0]):
                    print(line)
            else:
                print(f"channel_delivery: {channel_delivery_mode()}")
            return 0
        if head in ("ollama-native", "ollama-compat"):
            cmd_ollama_native(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head in ("ollama-options", "ollama-option", "ollama-opts"):
            cmd_ollama_options(argparse.Namespace(values=rest))
            return 0
        if head in ("provider-options", "provider-option", "provider-opts", "vllm-options", "nim-options"):
            cmd_provider_options(argparse.Namespace(values=rest))
            return 0
        if head in ("ollama-catalog", "ollama-catalog-refresh"):
            no_contexts = "--no-contexts" in rest
            timeout = 10.0
            for item in rest:
                if item.startswith("--timeout="):
                    try:
                        timeout = float(item.split("=", 1)[1])
                    except ValueError:
                        raise SystemExit("Usage: claude-any ollama-catalog [--no-contexts] [--timeout=SECONDS]")
            cmd_ollama_catalog(argparse.Namespace(no_contexts=no_contexts, timeout=timeout))
            return 0
        if head in ("test", "compat", "compatibility"):
            timeout = 60.0
            mode = "auto"
            if rest and rest[0] in ("auto", "quick", "smoke", "full"):
                mode = rest[0]
                rest = rest[1:]
            if rest:
                try:
                    timeout = float(rest[0])
                except ValueError:
                    raise SystemExit("Usage: claude-any test [timeout_seconds] [auto|quick|smoke|full]")
                if len(rest) > 1:
                    mode = rest[1]
            if mode not in ("auto", "quick", "smoke", "full"):
                raise SystemExit("Usage: claude-any test [timeout_seconds] [auto|quick|smoke|full]")
            cmd_test(argparse.Namespace(timeout=timeout, mode=mode))
            return 0
        if head == "status":
            cmd_status(argparse.Namespace())
            return 0
        if head == "stop":
            cmd_stop(argparse.Namespace())
            ncp = find_executable("ncp")
            if ncp:
                subprocess.run([ncp, "kill"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 0

    passthrough: list[str] = []
    configure_only = False
    auto_llm_options = False
    auto_llm_model: str | None = None
    skip_menu, web_search_override, update_check_override, self_update_check_override, force_menu = apply_headless_env_config()
    update_check = True
    if update_check_override is not None:
        update_check = update_check_override
    self_update_check = True
    if self_update_check_override is not None:
        self_update_check = self_update_check_override
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--ca-menu", "--ca-interactive"):
            force_menu = True
            i += 1
        elif arg in ("--ca-no-launch", "--ca-configure-only", "--ca-setup-only"):
            configure_only = True
            skip_menu = True
            i += 1
        elif arg == "--ca-language" or arg.startswith("--ca-language="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing language for --ca-language")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_language(argparse.Namespace(value=value))
            skip_menu = True
        elif arg == "--ca-provider" or arg.startswith("--ca-provider="):
            provider_value = arg.split("=", 1)[1] if "=" in arg else None
            if provider_value:
                cmd_provider(argparse.Namespace(name=provider_value))
                skip_menu = True
                i += 1
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                cmd_provider(argparse.Namespace(name=argv[i + 1]))
                skip_menu = True
                i += 2
            else:
                rc = run_external_menu("claude-any-provider")
                if rc is None:
                    rc = portable_provider_menu()
                if rc != 0:
                    return rc
                skip_menu = True
                i += 1
        elif arg == "--ca-base-url" or arg.startswith("--ca-base-url="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing URL for --ca-base-url")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            provider, _ = get_current_provider(load_config())
            cmd_base_url(argparse.Namespace(provider=provider, url=value))
            skip_menu = True
        elif arg == "--ca-model" or arg.startswith("--ca-model="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing model id for --ca-model")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_model(argparse.Namespace(value=[value]))
            skip_menu = True
        elif arg == "--ca-advisor-model" or arg.startswith("--ca-advisor-model="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing model id for --ca-advisor-model")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in set_advisor_model_config(value):
                print(line)
            skip_menu = True
        elif arg in ("--ca-auto-llm-options", "--ca-auto-llm", "--ca-recommended-llm") or arg.startswith(
            ("--ca-auto-llm-options=", "--ca-auto-llm=", "--ca-recommended-llm=")
        ):
            auto_llm_options = True
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            if value:
                auto_llm_model = value
            skip_menu = True
        elif arg == "--ca-models":
            cmd_models(argparse.Namespace(provider=None))
            return 0
        elif arg == "--ca-api-key" or arg.startswith("--ca-api-key="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing key for --ca-api-key")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            provider, _ = get_current_provider(load_config())
            cmd_set_api_key(argparse.Namespace(provider=provider, key=value))
            skip_menu = True
        elif arg == "--ca-api-key-env" or arg.startswith("--ca-api-key-env="):
            env_name = arg.split("=", 1)[1] if "=" in arg else None
            if env_name is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing env var name for --ca-api-key-env")
                env_name = argv[i + 1]
                i += 2
            else:
                i += 1
            value = os.environ.get(env_name, "")
            if not value:
                raise SystemExit(f"Environment variable {env_name} is empty or not set")
            provider, _ = get_current_provider(load_config())
            cmd_set_api_key(argparse.Namespace(provider=provider, key=value))
            skip_menu = True
        elif arg == "--ca-set-api-key":
            if i + 2 >= len(argv):
                raise SystemExit("Usage: --ca-set-api-key PROVIDER KEY")
            cmd_set_api_key(argparse.Namespace(provider=argv[i + 1], key=argv[i + 2]))
            skip_menu = True
            i += 3
        elif arg == "--ca-set-api-key-env":
            if i + 2 >= len(argv):
                raise SystemExit("Usage: --ca-set-api-key-env PROVIDER ENVVAR")
            value = os.environ.get(argv[i + 2], "")
            if not value:
                raise SystemExit(f"Environment variable {argv[i + 2]} is empty or not set")
            cmd_set_api_key(argparse.Namespace(provider=argv[i + 1], key=value))
            skip_menu = True
            i += 3
        elif arg == "--ca-ollama-num-ctx" or arg.startswith("--ca-ollama-num-ctx="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-ollama-num-ctx")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_ollama_options(argparse.Namespace(values=[f"num_ctx={value}"]))
            skip_menu = True
        elif arg == "--ca-ollama-ctx-range" or arg.startswith("--ca-ollama-ctx-range="):
            if "=" in arg:
                raw = arg.split("=", 1)[1]
                sep = ":" if ":" in raw else "-"
                parts = [p.strip() for p in raw.split(sep, 1)]
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    raise SystemExit("Usage: --ca-ollama-ctx-range MIN MAX")
                min_value, max_value = parts
                i += 1
            else:
                if i + 2 >= len(argv):
                    raise SystemExit("Usage: --ca-ollama-ctx-range MIN MAX")
                min_value, max_value = argv[i + 1], argv[i + 2]
                i += 3
            cmd_ollama_options(
                argparse.Namespace(values=[f"min={min_value}", f"max={max_value}", "num_ctx=auto"])
            )
            skip_menu = True
        elif arg == "--ca-ollama-option" or arg.startswith("--ca-ollama-option="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing KEY=VALUE for --ca-ollama-option")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_ollama_options(argparse.Namespace(values=[value]))
            skip_menu = True
        elif arg == "--ca-max-output-tokens" or arg.startswith("--ca-max-output-tokens="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-max-output-tokens")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"max_output_tokens={value}"]))
            skip_menu = True
        elif arg == "--ca-context-window" or arg.startswith("--ca-context-window="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-context-window")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"context_window={value}"]))
            skip_menu = True
        elif arg == "--ca-request-timeout-ms" or arg.startswith("--ca-request-timeout-ms="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-request-timeout-ms")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"request_timeout_ms={value}"]))
            skip_menu = True
        elif arg == "--ca-stream-idle-timeout-ms" or arg.startswith("--ca-stream-idle-timeout-ms="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-stream-idle-timeout-ms")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"stream_idle_timeout_ms={value}"]))
            skip_menu = True
        elif arg == "--ca-rate-limit-rpm" or arg.startswith("--ca-rate-limit-rpm="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing value for --ca-rate-limit-rpm")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"rate_limit_rpm={value}"]))
            skip_menu = True
        elif arg == "--ca-rate-limit-status" or arg.startswith("--ca-rate-limit-status="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing on/off for --ca-rate-limit-status")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"rate_limit_status={value}"]))
            skip_menu = True
        elif arg == "--ca-stream" or arg.startswith("--ca-stream="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing on/off for --ca-stream")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"stream_enabled={value}"]))
            skip_menu = True
        elif arg == "--ca-stream-word-chunking" or arg.startswith("--ca-stream-word-chunking="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing on/off for --ca-stream-word-chunking")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            cmd_provider_options(argparse.Namespace(values=[f"stream_word_chunking={value}"]))
            skip_menu = True
        elif arg == "--ca-log-level" or arg.startswith("--ca-log-level="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing level for --ca-log-level")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in set_log_level_config(value):
                print(line)
            skip_menu = True
        elif arg == "--ca-web-search":
            web_search_override = True
            skip_menu = True
            i += 1
        elif arg == "--ca-no-web-search":
            web_search_override = False
            skip_menu = True
            i += 1
        elif arg == "--ca-web-fetch":
            cmd_web_fetch(argparse.Namespace(value="on"))
            skip_menu = True
            i += 1
        elif arg == "--ca-no-web-fetch":
            cmd_web_fetch(argparse.Namespace(value="off"))
            skip_menu = True
            i += 1
        elif arg == "--ca-channel" or arg.startswith("--ca-channel="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing channel spec for --ca-channel")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in add_channel_spec(value):
                print(line)
            skip_menu = True
        elif arg == "--ca-channel-delivery" or arg.startswith("--ca-channel-delivery="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing mode for --ca-channel-delivery")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in set_channel_delivery_config(value):
                print(line)
            skip_menu = True
        elif arg == "--ca-dev-channel" or arg.startswith("--ca-dev-channel="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing channel spec for --ca-dev-channel")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in add_channel_spec(value):
                print(line)
            skip_menu = True
        elif arg == "--ca-development-channels" or arg.startswith("--ca-development-channels="):
            value = arg.split("=", 1)[1] if "=" in arg else None
            if value is None:
                if i + 1 >= len(argv):
                    raise SystemExit("Missing on/off for --ca-development-channels")
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            for line in set_channel_development_enabled(True):
                print(line)
            skip_menu = True
        elif arg == "--ca-clear-channels":
            for line in clear_channel_specs():
                print(line)
            skip_menu = True
            i += 1
        elif arg == "--ca-no-update-check":
            update_check = False
            skip_menu = True
            i += 1
        elif arg == "--ca-no-self-update-check":
            self_update_check = False
            skip_menu = True
            i += 1
        elif arg == "--ca-status":
            cmd_status(argparse.Namespace())
            return 0
        elif arg == "--ca-stop":
            cmd_stop(argparse.Namespace())
            return 0
        elif arg == "--":
            passthrough.extend(argv[i + 1 :])
            break
        else:
            passthrough.append(arg)
            i += 1
    if auto_llm_options:
        for line in apply_auto_llm_options_config(auto_llm_model):
            print(line)
    if configure_only:
        return 0
    return launch_claude(
        passthrough,
        skip_menu=skip_menu,
        force_menu=force_menu,
        web_search_override=web_search_override,
        update_check=update_check,
        self_update_check=self_update_check,
    )


def cmd_cli(args: argparse.Namespace) -> None:
    raise SystemExit(run_cli(args.argv))


def cmd_launch(args: argparse.Namespace) -> None:
    raise SystemExit(launch_claude(args.argv))


def cmd_version(args: argparse.Namespace) -> None:
    print(f"claude-any {VERSION}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-anyctl")
    sub = p.add_subparsers(dest="cmd", required=True)
    cli = sub.add_parser("cli", add_help=False)
    cli.add_argument("argv", nargs=argparse.REMAINDER)
    cli.set_defaults(func=cmd_cli)
    launch = sub.add_parser("launch", add_help=False)
    launch.add_argument("argv", nargs=argparse.REMAINDER)
    launch.set_defaults(func=cmd_launch)
    sub.add_parser("serve").set_defaults(func=serve)
    sub.add_parser("version").set_defaults(func=cmd_version)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("env").set_defaults(func=cmd_env)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    lang = sub.add_parser("language")
    lang.add_argument("value", nargs="?")
    lang.set_defaults(func=cmd_language)
    ws = sub.add_parser("web-search")
    ws.add_argument("value", nargs="?")
    ws.set_defaults(func=cmd_web_search)
    wf = sub.add_parser("web-fetch")
    wf.add_argument("value", nargs="?")
    wf.set_defaults(func=cmd_web_fetch)
    ll = sub.add_parser("log-level")
    ll.add_argument("value", nargs="?")
    ll.set_defaults(func=cmd_log_level)
    ch = sub.add_parser("channels")
    ch.add_argument("values", nargs="*")
    ch.set_defaults(func=cmd_channels)
    cd = sub.add_parser("channel-delivery")
    cd.add_argument("value", nargs="?")
    cd.set_defaults(func=cmd_channel_delivery)
    on = sub.add_parser("ollama-native")
    on.add_argument("value", nargs="?")
    on.set_defaults(func=cmd_ollama_native)
    oo = sub.add_parser("ollama-options")
    oo.add_argument("values", nargs="*")
    oo.set_defaults(func=cmd_ollama_options)
    po = sub.add_parser("provider-options")
    po.add_argument("values", nargs="*")
    po.set_defaults(func=cmd_provider_options)
    oc = sub.add_parser("ollama-catalog")
    oc.add_argument("--no-contexts", action="store_true")
    oc.add_argument("--timeout", type=float, default=10.0)
    oc.set_defaults(func=cmd_ollama_catalog)
    test = sub.add_parser("test")
    test.add_argument("timeout", nargs="?", type=float, default=120.0)
    test.add_argument("mode", nargs="?", choices=("auto", "quick", "smoke", "full"), default="auto")
    test.set_defaults(func=cmd_test)
    pp = sub.add_parser("provider")
    pp.add_argument("name", nargs="?")
    pp.set_defaults(func=cmd_provider)
    ak = sub.add_parser("api-key")
    ak.add_argument("provider", nargs="?")
    ak.set_defaults(func=cmd_api_key)
    sak = sub.add_parser("set-api-key")
    sak.add_argument("provider")
    sak.add_argument("key")
    sak.set_defaults(func=cmd_set_api_key)
    bu = sub.add_parser("base-url")
    bu.add_argument("provider")
    bu.add_argument("url")
    bu.set_defaults(func=cmd_base_url)
    mo = sub.add_parser("model")
    mo.add_argument("value", nargs="*")
    mo.set_defaults(func=cmd_model)
    am = sub.add_parser("advisor-model")
    am.add_argument("value", nargs="*")
    am.set_defaults(func=cmd_advisor_model)
    ml = sub.add_parser("models")
    ml.add_argument("provider", nargs="?")
    ml.set_defaults(func=cmd_models)
    return p


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "mcp-proxy":
        raise SystemExit(cmd_mcp_proxy(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "cli":
        raise SystemExit(run_cli(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "launch":
        raise SystemExit(launch_claude(sys.argv[2:]))
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
