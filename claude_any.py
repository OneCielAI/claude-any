#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import math
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = Path.home()
CONFIG_DIR = HOME / ".config" / "claude-any"
CONFIG_PATH = CONFIG_DIR / "config.json"
LOG_PATH = CONFIG_DIR / "router.log"
PID_PATH = CONFIG_DIR / "router.pid"
MODEL_LIST_CACHE_PATH = CONFIG_DIR / "model-list-cache.json"
WEB_TOOLS_MCP_CONFIG = CONFIG_DIR / "web-tools-mcp.json"
DUCKDUCKGO_MCP_CONFIG = CONFIG_DIR / "duckduckgo-mcp.json"
ROUTER_HOST = "127.0.0.1"
ROUTER_PORT = 8799
ROUTER_BASE = f"http://{ROUTER_HOST}:{ROUTER_PORT}"
CLAUDE_GATEWAY_CACHE = HOME / ".claude" / "cache" / "gateway-models.json"
NCP_ENV = HOME / ".config" / "nvd-claude-proxy" / ".env"
NCP_LOG = HOME / ".config" / "nvd-claude-proxy" / "proxy.log"
MODEL_CACHE_TTL_SECONDS = 300
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
APP_NAME = "Claude Any"
VERSION = "0.1.14"
CREDITS = "Credits: One Ciel LLC"
NON_ANTHROPIC_COMPAT_PROMPT = (
    "You are running inside Claude Code through a non-Anthropic model provider. "
    "Do not stop after announcing what you plan to do. When the user asks you to create, edit, or run code, "
    "immediately use the available Claude Code tools such as Write, Edit, Read, and Bash as appropriate, "
    "then report the concrete result. If you decide not to use tools, provide the complete requested code or answer in the same turn. "
    "Use skills only when the user's request clearly matches that skill; never invoke keybindings-help unless the user asks about keybindings. "
    "Keep final answers concise and do not expose hidden chain-of-thought. "
    "When calling Claude Code tools, use exactly the tool schema and do not invent extra fields. "
    "Bash accepts command, description, timeout, and run_in_background; it does not accept content. "
    "Read accepts file_path, offset, and limit; it does not accept description. "
    "Write accepts file_path and content. Edit accepts file_path, old_string, new_string, and replace_all. "
    "TaskList accepts no input. TaskUpdate requires taskId and status only. "
    "Never write pseudo tool calls, partial JSON, or markdown code fences when a real Claude Code tool call is required."
)
LANGUAGES = {
    "en": "English",
    "ko": "한국어",
    "ja": "日本語",
    "zh": "中文",
}
UI_TEXT = {
    "en": {
        "language": "Language",
        "provider": "Provider",
        "api_key": "API key",
        "base_url": "Base URL",
        "model": "Model",
        "test": "Test compatibility",
        "options": "LLM options",
        "presets": "LLM presets",
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
        "test": "호환성 테스트",
        "options": "LLM 옵션",
        "presets": "LLM 프리셋",
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
        "test": "互換性テスト",
        "options": "LLMオプション",
        "presets": "LLMプリセット",
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
        "test": "兼容性测试",
        "options": "LLM 选项",
        "presets": "LLM 预设",
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

DEFAULT_CONFIG: dict[str, Any] = {
    "current_provider": "nvidia-hosted",
    "language": "en",
    "migrations": {},
    "claude_code": {
        "disable_skills_for_non_anthropic": False,
        "blocked_skills_for_non_anthropic": ["keybindings-help"],
        "compat_prompt_for_non_anthropic": True,
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
            "custom_models": [],
        },
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "api_key": "ollama",
            "current_model": "qwen3-coder",
            "custom_models": ["qwen3-coder"],
            "native_compat": True,
            "num_ctx": "auto",
            "num_ctx_min": 32768,
            "num_ctx_max": 131072,
            "keep_alive": "5m",
            "think": False,
            "request_timeout_ms": 1800000,
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
            "custom_models": ["glm-5.1"],
            "num_ctx": "auto",
            "num_ctx_min": 32768,
            "num_ctx_max": 131072,
            "keep_alive": "5m",
            "think": False,
            "request_timeout_ms": 1800000,
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
            "custom_models": ["my-model"],
            "native_compat": True,
            "context_window": 32768,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "context_reserve_tokens": 1024,
            "request_timeout_ms": 1800000,
        },
        "nvidia-hosted": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "not-used",
            "current_model": "qwen/qwen3-coder-480b-a35b-instruct",
            "custom_models": [],
            "native_compat": False,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "request_timeout_ms": 1800000,
        },
        "self-hosted-nim": {
            "base_url": "http://127.0.0.1:8000",
            "api_key": "not-used",
            "current_model": "model",
            "custom_models": ["model"],
            "native_compat": True,
            "context_window": 32768,
            "max_output_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.8,
            "context_reserve_tokens": 1024,
            "request_timeout_ms": 1800000,
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
    model_id = model_id.strip()
    if provider == "ollama-cloud" and model_id and not model_id.endswith(":cloud"):
        return f"{model_id}:cloud"
    return model_id


def alias_for(provider: str, model_id: str) -> str:
    if provider == "nvidia-hosted" and model_id.startswith("claude-"):
        return model_id
    return f"claude-any-{provider}-{slug(model_id)}"


def unslug_provider_alias(provider: str, alias: str, model_map: dict[str, str]) -> str | None:
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


def executable_candidates(name: str) -> list[str]:
    if os.name == "nt" and not Path(name).suffix:
        return [f"{name}.exe", f"{name}.cmd", f"{name}.bat", name]
    return [name]


def executable_extra_dirs() -> list[Path]:
    dirs = [HOME / ".local" / "bin"]
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
    return dirs


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


def http_json(url: str, headers: dict[str, str] | None = None, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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
    if not ncp_module_available():
        install_ncp_proxy()
    if not ncp_module_available():
        raise RuntimeError("nvd-claude-proxy Python module was not found. Install it with: python -m pip install --user nvd-claude-proxy")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with open(NCP_LOG, "ab", buffering=0) as log:
        log.write(b"\n[claude-any] starting nvd-claude-proxy module\n")
        subprocess.Popen(
            [sys.executable, "-m", "nvd_claude_proxy.main"],
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
    try:
        if provider in ("ollama", "ollama-cloud"):
            try:
                data = http_json(join_url(base, "/api/tags"), headers=provider_model_list_headers(provider, pcfg), timeout=4.0)
                ids = [normalize_model_id(provider, mid) for mid in model_ids_from_response(data)]
            except Exception:
                data = http_json(join_url(base, "/v1/models"), headers=provider_model_list_headers(provider, pcfg), timeout=4.0)
                ids = [normalize_model_id(provider, mid) for mid in model_ids_from_response(data)]
        elif provider == "nvidia-hosted":
            data = http_json(join_url(base, "/v1/models"), headers=nvidia_hosted_list_headers(), timeout=8.0)
            ids = model_ids_from_response(data)
        else:
            headers = provider_model_list_headers(provider, pcfg)
            for path in ("/v1/models", "/models"):
                try:
                    data = http_json(join_url(base, path), headers=headers, timeout=6.0)
                    ids = model_ids_from_response(data)
                    if ids:
                        break
                except Exception:
                    continue
    except Exception:
        ids = []
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
    return provider == "nvidia-hosted" and bool(pcfg.get("native_compat", False))


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
    if provider == "nvidia-hosted":
        return nvidia_proxy_base_url()
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
            "unless the user explicitly asks for code only."
        ),
    }


def anthropic_messages_to_ollama(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = anthropic_system_to_ollama_messages(body.get("system"))
    messages.append(ollama_claude_code_reminder())
    tool_names_by_id: dict[str, str] = {}
    tool_inputs_by_id: dict[str, Any] = {}
    for message in body.get("messages", []) or []:
        if not isinstance(message, dict):
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
                messages.append({"role": "user", "content": text})
            for block in tool_blocks:
                tool_use_id = str(block.get("tool_use_id") or "")
                tool_name = tool_names_by_id.get(tool_use_id, "tool")
                tool_input = tool_inputs_by_id.get(tool_use_id)
                tool_input_text = json.dumps(tool_input, ensure_ascii=False, sort_keys=True) if tool_input else "{}"
                result_text = anthropic_content_to_text(block.get("content", ""))
                if not block.get("is_error"):
                    tool_text = (
                        f"Tool `{tool_name}` completed successfully.\n"
                        f"Input:\n{tool_input_text}\n\n"
                        f"Result:\n{result_text}\n\n"
                        f"If this result satisfies the user's request, provide the final answer now. "
                        f"Do not call `{tool_name}` again with the same arguments."
                    )
                    tool_summary = (
                        f"The `{tool_name}` tool call above already completed successfully. "
                        f"Its input was {tool_input_text}. Its result was:\n{result_text}\n\n"
                        f"Treat this as authoritative tool output. Do not repeat the same or equivalent "
                        f"`{tool_name}` call; continue with the next required step or final answer."
                    )
                else:
                    tool_text = (
                        f"Tool `{tool_name}` failed.\n"
                        f"Input:\n{tool_input_text}\n\n"
                        f"Error:\n{result_text}"
                    )
                    tool_summary = (
                        f"The `{tool_name}` tool call above failed. Its input was {tool_input_text}. "
                        f"Use the error output to choose a different next step; do not blindly repeat it."
                    )
                messages.append({"role": "tool", "tool_name": tool_name, "content": tool_text})
                messages.append({"role": "user", "content": tool_summary})
            continue

        text = anthropic_content_to_text(content)
        out: dict[str, Any] = {"role": role, "content": text}
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
    raw = pcfg.get("request_timeout_ms", pcfg.get("request_timeout", pcfg.get("timeout_ms", 600000)))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 600.0
    if value <= 0:
        return 600.0
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


def provider_request_timeout_seconds(pcfg: dict[str, Any]) -> float:
    return ollama_request_timeout_seconds(pcfg)


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
        configured_output_tokens(pcfg, body, "num_predict"),
        _token_cache=token_cache,
    )
    if num_predict:
        options["num_predict"] = num_predict
    if num_ctx:
        options.setdefault("num_ctx", num_ctx)
    if options:
        req["options"] = options
    return req


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


def ollama_chat_to_anthropic(data: dict[str, Any], model: str) -> dict[str, Any]:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content: list[dict[str, Any]] = []
    text = message.get("content") or ""
    if text:
        content.append({"type": "text", "text": text})
    tool_id_prefix = f"toolu_ollama_{int(time.time() * 1000)}_{os.getpid()}"
    for i, call in enumerate(message.get("tool_calls") or []):
        fn = call.get("function") if isinstance(call, dict) else {}
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        name = str(fn["name"])
        content.append(
            {
                "type": "tool_use",
                "id": f"{tool_id_prefix}_{i}",
                "name": name,
                "input": normalize_tool_arguments(name, fn.get("arguments")),
            }
        )
    done_reason = data.get("done_reason")
    stop_reason = "tool_use" if any(block.get("type") == "tool_use" for block in content) else "end_turn"
    if done_reason == "length":
        stop_reason = "max_tokens"
    return {
        "id": f"msg_ollama_{int(time.time() * 1000)}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content or [{"type": "text", "text": ""}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(data.get("prompt_eval_count") or 0),
            "output_tokens": int(data.get("eval_count") or 0),
        },
    }


def _ollama_stream_to_anthropic_sse(handler: BaseHTTPRequestHandler, resp: Any, model: str) -> None:
    """Stream Ollama NDJSON /api/chat response as Anthropic SSE /v1/messages format."""
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "keep-alive")
    handler.end_headers()
    msg_id = f"msg_ollama_{int(time.time() * 1000)}"
    started = False
    text_so_far = ""
    tool_calls: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    try:
        for line in resp:
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
                started = True
                # Send message_start event
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
                handler.wfile.write(f"event: message_start\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
            # Handle text content
            text_chunk = message.get("content") or ""
            if text_chunk:
                text_so_far += text_chunk
                event = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text_chunk},
                }
                handler.wfile.write(f"event: content_block_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
            # Handle tool calls
            for call in message.get("tool_calls") or []:
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                if not isinstance(fn, dict) or not fn.get("name"):
                    continue
                tool_calls.append(call)
                tool_id = f"toolu_ollama_{int(time.time() * 1000)}_{len(tool_calls) - 1}"
                tool_event = {
                    "type": "content_block_start",
                    "index": 1 + len([b for b in tool_calls[:-1] if False]),  # tool blocks after text block
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": str(fn["name"]),
                        "input": normalize_tool_arguments(str(fn["name"]), fn.get("arguments")),
                    },
                }
                handler.wfile.write(f"event: content_block_start\ndata: {json.dumps(tool_event, ensure_ascii=False)}\n\n".encode())
                handler.wfile.flush()
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
        handler.wfile.write(f"event: message_delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
        handler.wfile.flush()
    except Exception:
        # On error, try to send a minimal message_stop
        try:
            handler.wfile.write(b"event: message_stop\ndata: {}\n\n")
            handler.wfile.flush()
        except Exception:
            pass


def forward_ollama_api_chat(handler: BaseHTTPRequestHandler, provider: str, pcfg: dict[str, Any], body: dict[str, Any]) -> None:
    model = resolve_requested_model(provider, pcfg, body.get("model"))
    base = pcfg.get("base_url", "").rstrip("/")
    stream_requested = body.get("stream", True)
    req_body = ollama_chat_request(model, body, pcfg, stream=stream_requested)
    headers = provider_headers(provider, pcfg)
    url = join_url(base, "/api/chat")
    if stream_requested:
        # Stream Ollama response through as Anthropic SSE
        data_bytes = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=ollama_request_timeout_seconds(pcfg))
        except urllib.error.HTTPError as exc:
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
            write_json(
                handler,
                {"type": "error", "error": {"type": "upstream_error", "message": msg}},
                exc.code,
            )
            return
        # Check if Claude Code requested SSE streaming
        accept = handler.headers.get("accept", "")
        if "text/event-stream" in accept or stream_requested:
            _ollama_stream_to_anthropic_sse(handler, resp, model)
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
            write_json(handler, ollama_chat_to_anthropic(data, model))
        return
    # Non-streaming fallback
    try:
        data = post_json(url, req_body, headers=headers, timeout=ollama_request_timeout_seconds(pcfg))
    except urllib.error.HTTPError as exc:
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
        write_json(
            handler,
            {"type": "error", "error": {"type": "upstream_error", "message": msg}},
            exc.code,
        )
        return
    write_json(handler, ollama_chat_to_anthropic(data, model))


class RouterHandler(BaseHTTPRequestHandler):
    server_version = "claude-any/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), fmt % args))

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        cfg = load_config()
        provider, pcfg = get_current_provider(cfg)
        if path in ("/health", "/healthz"):
            write_json(self, {"ok": True, "provider": provider, "model": current_alias(cfg)})
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
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        cfg = load_config()
        provider, pcfg = get_current_provider(cfg)
        if path == "/v1/messages/count_tokens":
            write_json(self, {"input_tokens": estimate_tokens(body)})
            return
        if path != "/v1/messages":
            write_json(self, {"type": "error", "error": {"type": "not_found_error", "message": path}}, 404)
            return
        try:
            if provider == "nvidia-hosted":
                ensure_ncp()
            if provider in ("ollama", "ollama-cloud"):
                forward_ollama_api_chat(self, provider, pcfg, body)
                return
            body = cap_anthropic_body_for_provider(provider, pcfg, body)
            body = apply_provider_request_options(provider, pcfg, body)
            upstream_model = resolve_requested_model(provider, pcfg, body.get("model"))
            if provider == "nvidia-hosted":
                upstream_model = ncp_model_id_for_nvidia_hosted(upstream_model)
            body["model"] = upstream_model
            data = json.dumps(body).encode("utf-8")
            base = provider_upstream_request_base(provider, pcfg)
            url = join_url(base, "/v1/messages")
            headers = provider_headers(provider, pcfg)
            for h in ("anthropic-beta", "anthropic-dangerous-direct-browser-access"):
                if self.headers.get(h):
                    headers[h] = self.headers[h]
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req, timeout=provider_request_timeout_seconds(pcfg))
                status = getattr(resp, "status", 200)
                self.send_response(status)
                ctype = resp.headers.get("content-type", "application/json")
                self.send_header("content-type", ctype)
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except urllib.error.HTTPError as e:
                err = e.read()
                self.send_response(e.code)
                self.send_header("content-type", e.headers.get("content-type", "application/json"))
                self.end_headers()
                self.wfile.write(err)
        except Exception as exc:
            write_json(self, {"type": "error", "error": {"type": "api_error", "message": str(exc)}}, 500)


def serve(_: argparse.Namespace) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    os.chmod(PID_PATH, 0o600)
    server = ThreadingHTTPServer((ROUTER_HOST, ROUTER_PORT), RouterHandler)
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
    pcfg["base_url"] = url.rstrip("/")
    save_config(cfg)
    clear_model_cache()
    return [f"Base URL for {provider} set to {pcfg['base_url']}."]


def set_model_config(value: str) -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    mmap = model_map_for(provider, pcfg)
    model_id = normalize_model_id(provider, unslug_provider_alias(provider, value, mmap) or value)
    pcfg["current_model"] = model_id
    known = read_model_list_cache(provider, pcfg) or []
    custom = pcfg.setdefault("custom_models", [])
    if model_id not in custom and model_id not in known:
        custom.append(model_id)
    save_config(cfg)
    clear_model_cache()
    return [f"Model for {provider} set to {model_id}.", f"Claude Code alias: {alias_for(provider, model_id)}"]


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


def status_lines() -> list[str]:
    cfg = load_config()
    provider, pcfg = get_current_provider(cfg)
    if native_anthropic_enabled(provider):
        mode = "anthropic-native"
    elif ollama_native_compat_enabled(provider, pcfg):
        mode = "ollama-native"
    elif vllm_native_compat_enabled(provider, pcfg):
        mode = "vllm-native"
    elif nim_native_compat_enabled(provider, pcfg):
        mode = "nim-native"
    elif nvidia_hosted_native_compat_enabled(provider, pcfg):
        mode = "nvidia-native"
    else:
        mode = "claude-any-router"
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
        *([f"context_window: {pcfg.get('context_window', 'default')}"] if provider in ("vllm", "self-hosted-nim") else []),
        *([f"context_reserve_tokens: {pcfg.get('context_reserve_tokens', 'default')}"] if provider in ("vllm", "self-hosted-nim") else []),
        *([f"max_output_tokens: {pcfg.get('max_output_tokens', 'default')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        *([f"request_timeout_ms: {pcfg.get('request_timeout_ms', 'default')}"] if provider in ("vllm", "nvidia-hosted", "self-hosted-nim") else []),
        f"claude_model: {current_upstream_model_id(provider, pcfg) if direct_native else current_alias(cfg)}",
        f"router: {'bypassed for native provider compatibility' if direct_native else (('up' if router_up() else 'down') + ' ' + ROUTER_BASE)}",
        f"config: {CONFIG_PATH}",
    ]


def cmd_status(_: argparse.Namespace) -> None:
    print("\n".join(status_lines()))


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
    if key in ("max_tokens", "maxtoken", "max_token", "num_predict"):
        fixed = positive_int(value)
        if not fixed:
            raise SystemExit("max_tokens/num_predict must be a positive integer")
        pcfg.setdefault("ollama_options", {})["num_predict"] = fixed
        return
    if key == "think":
        pcfg["think"] = bool(value)
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
        for token in values:
            apply_ollama_option(pcfg, token)
        save_config(cfg)
        clear_model_cache()
        print(f"Ollama options updated for {provider}.")
    print(f"provider: {provider}")
    print(f"num_ctx: {ollama_num_ctx_status(pcfg)}")
    print(f"keep_alive: {pcfg.get('keep_alive', 'default')}")
    print(f"think: {bool(pcfg.get('think', False))}")
    print(f"request_timeout_ms: {pcfg.get('request_timeout_ms', 'default')}")
    print(f"ollama_options: {ollama_options_status(pcfg)}")
    print("Examples:")
    print("  claude-anyctl ollama-options num_ctx=auto min=32768 max=131072")
    print("  claude-anyctl ollama-options num_ctx=65536 temperature=0.7 top_p=0.8 max_tokens=32768 timeout=1800000")
    print("  claude-any --ca-ollama-option temperature=0.7 --ca-ollama-num-ctx 65536")


PROVIDER_OPTION_PROVIDERS = ("anthropic", "vllm", "nvidia-hosted", "self-hosted-nim")
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
    if provider in ("vllm", "self-hosted-nim"):
        parts.insert(0, f"context_window={pcfg.get('context_window', 'default')}")
        parts.insert(1, f"reserve={pcfg.get('context_reserve_tokens', 'default')}")
    if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
        native_default = False if provider == "nvidia-hosted" else True
        parts.append(f"native={bool(pcfg.get('native_compat', native_default))}")
    if provider in PROVIDER_SAMPLING_OPTION_PROVIDERS:
        parts.extend(provider_sampling_status(pcfg))
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
    if any(marker in model for marker in ("70b", "120b", "253b", "405b", "480b", "large", "ultra", "pro")):
        return "large"
    if provider in ("vllm", "self-hosted-nim"):
        server_limit = upstream_model_context_limit(provider, pcfg, timeout=1.5) or 0
        ctx = server_limit or positive_int(pcfg.get("context_window")) or 0
        if ctx >= 65536:
            return "long-context"
    if provider in ("ollama", "ollama-cloud"):
        ctx = positive_int(pcfg.get("num_ctx_max")) or positive_int(pcfg.get("num_ctx")) or 0
        if ctx >= 65536:
            return "long-context"
    return "general"


def recommended_preset_id(provider: str, pcfg: dict[str, Any]) -> str:
    family = model_option_family(provider, pcfg)
    if family == "reasoning":
        return "reasoning"
    if family == "coding":
        return "coding"
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
    "large-output": ("Large output/report", "larger 8K output for summaries/reports"),
    "reasoning": ("Reasoning model", "higher timeout and reasoning-friendly sampling"),
}


LLM_PRESET_I18N: dict[str, dict[str, tuple[str, str]]] = {
    "ko": {
        "balanced": ("균형형 Claude Code", "4K 출력, 안정적인 코딩/채팅 기본값"),
        "coding": ("코딩 결정형", "편집, 스크립트, 코드 리뷰용 낮은 무작위성"),
        "fast": ("빠른 짧은 작업", "짧은 출력과 짧은 타임아웃"),
        "long-context-65k": ("긴 컨텍스트 65K", "65K 컨텍스트 목표, 4K 출력 여유"),
        "large-output": ("긴 출력/리포트", "요약과 리포트용 8K 출력"),
        "reasoning": ("추론 모델", "긴 타임아웃과 추론 친화 샘플링"),
    },
    "ja": {
        "balanced": ("バランス型 Claude Code", "4K 出力、安定したコーディング/チャット既定値"),
        "coding": ("コーディング決定型", "編集、スクリプト、コードレビュー向けの低いランダム性"),
        "fast": ("高速な短い作業", "短い出力と短いタイムアウト"),
        "long-context-65k": ("長いコンテキスト 65K", "65K コンテキスト目標、4K 出力予約"),
        "large-output": ("長い出力/レポート", "要約とレポート向けの 8K 出力"),
        "reasoning": ("推論モデル", "長いタイムアウトと推論向けサンプリング"),
    },
    "zh": {
        "balanced": ("均衡型 Claude Code", "4K 输出，稳定的编码/聊天默认值"),
        "coding": ("编码确定型", "用于编辑、脚本和代码审查的低随机性"),
        "fast": ("快速短任务", "较短输出和较短超时"),
        "long-context-65k": ("长上下文 65K", "65K 上下文目标，4K 输出预留"),
        "large-output": ("长输出/报告", "用于摘要和报告的 8K 输出"),
        "reasoning": ("推理模型", "更长超时和适合推理的采样"),
    },
}


MODEL_FAMILY_I18N: dict[str, dict[str, str]] = {
    "ko": {
        "coding": "코딩",
        "reasoning": "추론",
        "large": "대형 모델",
        "long-context": "긴 컨텍스트",
        "general": "일반",
    },
    "ja": {
        "coding": "コーディング",
        "reasoning": "推論",
        "large": "大型モデル",
        "long-context": "長いコンテキスト",
        "general": "汎用",
    },
    "zh": {
        "coding": "编码",
        "reasoning": "推理",
        "large": "大型模型",
        "long-context": "长上下文",
        "general": "通用",
    },
}


def llm_preset_text(preset_id: str, lang: str | None = None) -> tuple[str, str]:
    lang = lang or load_config().get("language", "en")
    return LLM_PRESET_I18N.get(lang, {}).get(preset_id, LLM_PRESETS[preset_id])


def model_family_text(family: str, lang: str | None = None) -> str:
    lang = lang or load_config().get("language", "en")
    return MODEL_FAMILY_I18N.get(lang, {}).get(family, family)


def llm_preset_panel_rows(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    recommended = recommended_preset_id(provider, pcfg)
    family = model_option_family(provider, pcfg)
    recommended_label, _ = llm_preset_text(recommended, lang)
    rows = [
        f"{ui_text('model_family', lang)}: {model_family_text(family, lang)}; "
        f"{ui_text('recommended_preset_is', lang)} {recommended_label}"
    ]
    values = ["__info__"]
    for preset_id in LLM_PRESETS:
        label, description = llm_preset_text(preset_id, lang)
        mark = "*" if preset_id == recommended else " "
        rows.append(f"{mark} {pad_cells(label, 24)} {description}")
        values.append(preset_id)
    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def apply_llm_preset_to_provider(provider: str, pcfg: dict[str, Any], preset_id: str, lang: str | None = None) -> list[str]:
    if preset_id not in LLM_PRESETS:
        raise SystemExit(f"Unknown preset: {preset_id}")
    lang = lang or load_config().get("language", "en")
    label = llm_preset_text(preset_id, lang)[0]
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
                "timeout=600000",
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
                "timeout=600000",
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
                "timeout=900000",
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
                "timeout=1200000",
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
                "timeout=1800000",
            ],
        }
        for token in tokens_by_preset[preset_id]:
            apply_ollama_option(pcfg, token)
    elif provider == "anthropic":
        tokens_by_preset = {
            "balanced": ["max_output_tokens=4096", "timeout=600000"],
            "coding": ["max_output_tokens=4096", "timeout=600000"],
            "fast": ["max_output_tokens=2048", "timeout=300000"],
            "long-context-65k": ["max_output_tokens=4096", "timeout=900000"],
            "large-output": ["max_output_tokens=8192", "timeout=1200000"],
            "reasoning": ["max_output_tokens=4096", "timeout=1800000"],
        }
        for token in tokens_by_preset[preset_id]:
            apply_provider_option(provider, pcfg, token)
    else:
        native_default = "false" if provider == "nvidia-hosted" else "true"
        server_limit = upstream_model_context_limit(provider, pcfg) if provider in ("vllm", "self-hosted-nim") else None
        tokens_by_preset = {
            "balanced": [
                "context_window=32768",
                "reserve=2048",
                "max_output_tokens=4096",
                "timeout=600000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "coding": [
                "context_window=32768",
                "reserve=2048",
                "max_output_tokens=4096",
                "timeout=600000",
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
                "timeout=900000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "large-output": [
                "context_window=65536",
                "reserve=4096",
                "max_output_tokens=8192",
                "timeout=1200000",
                "temperature=0.3",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
            "reasoning": [
                "context_window=65536",
                "reserve=4096",
                "max_output_tokens=4096",
                "timeout=1800000",
                "temperature=0.6",
                "unset:top_p",
                "unset:top_k",
                f"native={native_default}",
            ],
        }
        for token in tokens_by_preset[preset_id]:
            if provider == "nvidia-hosted" and token.startswith(("context_window=", "reserve=")):
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
    family = model_option_family(provider, pcfg)
    lines = [
        f"{ui_text('apply_preset', lang)}: {label}",
        f"Provider: {provider}; {ui_text('model_family', lang)}: {model_family_text(family, lang)}",
    ]
    if provider in ("vllm", "self-hosted-nim"):
        server_limit = upstream_model_context_limit(provider, pcfg)
        if server_limit:
            lines.append(f"Server max_model_len: {server_limit}")
            if preset_id in ("long-context-65k", "large-output") and server_limit < 65536:
                lines.append("Long-context preset requires restarting the server with --max-model-len 65536 or higher.")
                lines.append("Client settings were capped to the server-reported context length.")
        elif preset_id in ("long-context-65k", "large-output"):
            lines.append("Could not verify server max_model_len; vLLM/NIM must be started with a matching context limit.")
    return lines


def apply_llm_preset_config(provider: str, preset_id: str) -> list[str]:
    cfg = load_config()
    pcfg = cfg["providers"][provider]
    lines = apply_llm_preset_to_provider(provider, pcfg, preset_id, cfg.get("language", "en"))
    save_config(cfg)
    clear_model_cache()
    return lines


def llm_option_panel_rows(provider: str, pcfg: dict[str, Any], lang: str | None = None) -> tuple[list[str], list[str]]:
    lang = lang or load_config().get("language", "en")
    rows: list[str] = []
    values: list[str] = []

    def add(label: str, key: str, value: Any) -> None:
        rows.append(f"{label:<24} [{compact_text(value, 56)}]")
        values.append(key)

    add(ui_text("apply_preset", lang), "preset", llm_preset_text(recommended_preset_id(provider, pcfg), lang)[0])
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
    else:
        if provider in ("vllm", "self-hosted-nim"):
            add("Context window", "context_window", pcfg.get("context_window", "default"))
            add("Context reserve", "context_reserve_tokens", pcfg.get("context_reserve_tokens", "default"))
        add("Max output tokens", "max_output_tokens", pcfg.get("max_output_tokens", "default"))
        if provider in ("vllm", "nvidia-hosted", "self-hosted-nim"):
            add("Timeout ms", "request_timeout_ms", pcfg.get("request_timeout_ms", "default"))
            add("Temperature", "temperature", pcfg.get("temperature", "default"))
            add("Top P", "top_p", pcfg.get("top_p", "default"))
            add("Top K", "top_k", pcfg.get("top_k", "default"))
            add("Native compatibility", "native_compat", bool(pcfg.get("native_compat", False)))
        elif provider == "anthropic":
            add("Timeout ms", "request_timeout_ms", pcfg.get("request_timeout_ms", "Claude Code default"))

    rows.append(ui_text("back", lang))
    values.append("back")
    return rows, values


def llm_option_prompt_default(provider: str, pcfg: dict[str, Any], key: str) -> str:
    if provider in ("ollama", "ollama-cloud"):
        opts = ollama_extra_options(pcfg)
        if key == "num_ctx":
            return str(pcfg.get("num_ctx", "auto"))
        if key in ("num_ctx_min", "num_ctx_max", "keep_alive", "think", "request_timeout_ms"):
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
    clear_words = ("default", "unset", "none", "null")
    token = f"unset:{key}" if value.lower() in clear_words else f"{key}={value}"
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
    save_config(cfg)
    clear_model_cache()
    return [f"{PROVIDER_LABELS.get(provider, provider)} option updated.", f"{key}: {value}"]


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
        elif key in ("native", "native_compat"):
            pcfg["native_compat"] = True
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
    if key in ("native", "native_compat"):
        pcfg["native_compat"] = bool(value)
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
        raise SystemExit("Provider options are available for anthropic, vllm, nvidia-hosted, and self-hosted-nim.")
    pcfg = cfg["providers"][provider]
    if values:
        for token in values:
            apply_provider_option(provider, pcfg, token)
        save_config(cfg)
        clear_model_cache()
        print(f"Provider options updated for {provider}.")
    print(f"provider: {provider}")
    print(f"provider_options: {provider_options_status(provider, pcfg)}")
    print("Notes:")
    print("  max_output_tokens is passed to Claude Code as CLAUDE_CODE_MAX_OUTPUT_TOKENS.")
    print("  context_window is a claude-any/router cap; native mode still cannot raise the real server limit.")
    print("  temperature/top_p/top_k are injected by claude-any router mode when the provider supports them.")
    print("Examples:")
    print("  claude-anyctl provider-options nvidia-hosted max_output_tokens=4096 temperature=0.7 top_p=0.8 timeout=120000 native=false")
    print("  claude-anyctl provider-options vllm max_output_tokens=4096 context_window=65536 timeout=1800000")
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
        "max_tokens": 16,
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
    ollama_native = ollama_native_compat_enabled(provider, pcfg)
    provider_native = provider_native_compat_enabled(provider, pcfg)
    native = ollama_native or provider_native
    model = current_upstream_model_id(provider, pcfg) if provider_native else (launch_model_id(provider, pcfg) if ollama_native else current_alias(cfg))
    base = native_anthropic_base_url(provider, pcfg) if native else ROUTER_BASE
    if not native:
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


def apply_common_claude_env(provider: str, pcfg: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    output_tokens = claude_code_output_token_limit(provider, pcfg)
    if output_tokens:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(output_tokens)
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
            "ANTHROPIC_AUTH_TOKEN": token,
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
    alias = current_alias(cfg)
    return apply_common_claude_env(provider, pcfg, {
        "CLAUDE_ANY_PROVIDER": provider,
        "ANTHROPIC_BASE_URL": ROUTER_BASE,
        "ANTHROPIC_AUTH_TOKEN": "not-used",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
        "ANTHROPIC_MODEL": alias,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": alias,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": alias,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": alias,
        "CLAUDE_CODE_SUBAGENT_MODEL": alias,
        "CLAUDE_ANY_MODEL_ALIAS": alias,
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
        "ANTHROPIC_MODEL",
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
        proxy = nvidia_proxy_base_url()
        state = "ready" if is_url_up(f"{proxy}/v1/models") else "starts on launch"
        return f"Base URL: NVIDIA hosted ({base}); local proxy {proxy} {state}"
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
    debug_path = "/tmp/ca-key-debug.log"
    if fd is None:
        fd = sys.stdin.fileno()
    ch = os.read(fd, 1)
    log = f"{time.time():.3f} first={ch!r}"
    if ch == b"\x1b":
        seq = ch.decode("latin-1")
        b = os.read(fd, 1)
        log += f" next={b!r}"
        if not b:
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(log + " result='esc'\n")
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
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(log + "\n")
        return result
    if ch in (b"\r", b"\n"):
        result = "enter"
    else:
        result = ch.decode("latin-1").lower()
    with open(debug_path, "a", encoding="utf-8") as f:
        f.write(log + f" result={result!r}\n")
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
    first_render = True
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
    fd = -1
    old_settings = None
    if os.name != "nt" and sys.stdin.isatty():
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
        new[6][termios.VMIN] = 1
        new[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, new)
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
            if sys.stdout.isatty():
                prefix = "\033[2J\033[H" if first_render else "\033[H"
                sys.stdout.write(prefix + rendered + "\033[J")
                sys.stdout.flush()
                first_render = False
            else:
                print(rendered, end="")
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
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)
        if sys.stdout.isatty():
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
        f"5. {ui_text('options', lang)}  [{compact_text(llm_options_status(provider, pcfg), 62)}]",
        f"6. {ui_text('test', lang)}",
        f"7. {ui_text('launch', lang)}",
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

    mode_line = next((line for line in status_lines() if line.startswith("mode:")), "mode: claude-any-router")
    add(f"Claude Any v{VERSION}", "1;31")
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
            "test": "Compatibility test",
            "options": ui_text("options", lang),
            "preset": ui_text("presets", lang),
        }
        add("")
        add("-" * render_width, "38;5;208")
        panel_title = titles.get(panel, panel)
        title_suffix = "" if panel_title.lower().endswith(("options", "presets", "옵션", "프리셋", "オプション", "プリセット", "选项", "预设")) else " options"
        add(f"{panel_title}{title_suffix}", "1;38;5;208")
        fixed = len(screen) + len(checks) + len(messages) + 5
        limit = max(5, height - fixed)
        for actual, row in visible_rows(panel_rows, panel_idx, limit):
            if actual is None:
                add("    " + row, "2")
            elif actual == panel_idx:
                add("  > " + row, "7;1")
            else:
                add("    " + row)
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


def prompt_menu_value(prompt: str, default: str = "", secret: bool = False) -> str:
    label = f"{prompt}"
    if default:
        label += f" [{default}]"
    label += ": "
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    sys.stdout.write("\n" + ansi(label, "1;38;5;208"))
    sys.stdout.flush()
    try:
        if secret:
            value = getpass.getpass("")
        else:
            value = input()
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
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
    main_idx = 7 if settings_ready_except_api_key() else 0
    panel: str | None = None
    panel_idx = 0
    panel_rows: list[str] = []
    panel_values: list[str] = []
    checks = preflight_lines()
    messages: list[str] = []
    first_render = True

    def open_panel(name: str) -> None:
        nonlocal panel, panel_idx, panel_rows, panel_values, messages, first_render
        cfg = load_config()
        provider, pcfg = get_current_provider(cfg)
        panel = name
        panel_idx = 0
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
        elif name == "test":
            panel_rows, panel_values = ["Run compatibility test", "Back"], ["run", "back"]
        elif name == "options":
            panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
        elif name == "preset":
            panel_rows, panel_values = llm_preset_panel_rows(provider, pcfg, cfg.get("language", "en"))

    def close_panel(next_idx: int | None = None) -> None:
        nonlocal panel, panel_idx, panel_rows, panel_values, main_idx
        panel = None
        panel_idx = 0
        panel_rows = []
        panel_values = []
        if next_idx is not None:
            main_idx = next_idx

    def refresh_checks() -> None:
        nonlocal checks
        checks = preflight_lines()

    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
    try:
        while True:
            first_render = render_prelaunch_screen(main_idx, panel, panel_idx, panel_rows, checks, messages, first_render)
            key = read_menu_key()
            if panel:
                if key in ("up", "k"):
                    panel_idx = (panel_idx - 1) % max(1, len(panel_rows))
                    continue
                if key in ("down", "j"):
                    panel_idx = (panel_idx + 1) % max(1, len(panel_rows))
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
                        model_value = prompt_menu_value("Model id or alias")
                    else:
                        model_value = value
                    if model_value:
                        messages = set_model_config(model_value)
                        refresh_checks()
                    close_panel(6)
                elif panel == "api-key":
                    if value == "back":
                        close_panel()
                    elif value == "input":
                        key_value = prompt_menu_value(f"API key for {provider}", secret=True)
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
                        env_name = prompt_menu_value("Environment variable name", default_env)
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
                            confirm = prompt_menu_value(f"Clipboard contains {mask_secret(key_value)}. Store it? y/N")
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
                        url = prompt_menu_value(f"Base URL for {provider}", default)
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
                        main_idx = 7 if "Compatibility: OK" in out else 4
                elif panel == "options":
                    if value == "back":
                        close_panel()
                    elif value == "preset":
                        open_panel("preset")
                    else:
                        default = llm_option_prompt_default(provider, pcfg, value)
                        entered = prompt_menu_value(f"{value} for {provider} (default/unset clears)", default)
                        try:
                            messages = set_llm_option_config(provider, value, entered)
                        except Exception as exc:
                            messages = [f"Option update failed: {type(exc).__name__}: {exc}"]
                        refresh_checks()
                        cfg = load_config()
                        provider, pcfg = get_current_provider(cfg)
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
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
                        panel_idx = 0
                        panel_rows, panel_values = llm_option_panel_rows(provider, pcfg, cfg.get("language", "en"))
                continue

            if key in ("up", "k"):
                main_idx = (main_idx - 1) % 9
            elif key in ("down", "j"):
                main_idx = (main_idx + 1) % 9
            elif key in ("esc", "q"):
                return 10
            elif key == "enter":
                actions = ["language", "provider", "api-key", "base-url", "model", "options", "test", "launch", "quit"]
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
        if sys.stdout.isatty():
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


def run_prelaunch_menu(passthrough: list[str], skip_menu: bool = False) -> int:
    if skip_menu or has_noninteractive_claude_args(passthrough) or os.environ.get("CLAUDE_ANY_SKIP_MENU") == "1":
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


def should_disable_claude_skills(provider: str, cfg: dict[str, Any], override: bool | None) -> bool:
    if override is not None:
        return override
    return provider != "anthropic" and bool(cfg.get("claude_code", {}).get("disable_skills_for_non_anthropic", False))


def blocked_claude_skills(provider: str, cfg: dict[str, Any], override: bool | None) -> list[str]:
    if provider == "anthropic" or override is False or should_disable_claude_skills(provider, cfg, override):
        return []
    blocked = cfg.get("claude_code", {}).get("blocked_skills_for_non_anthropic", ["keybindings-help"])
    if not isinstance(blocked, list):
        return []
    return [str(name).strip() for name in blocked if str(name).strip()]


def should_append_compat_prompt(provider: str, cfg: dict[str, Any]) -> bool:
    return provider != "anthropic" and bool(cfg.get("claude_code", {}).get("compat_prompt_for_non_anthropic", True))


def has_passthrough_option(passthrough: list[str], *names: str) -> bool:
    return any(arg in names or any(arg.startswith(name + "=") for name in names) for arg in passthrough)


def write_web_tools_mcp_config(cfg: dict[str, Any]) -> Path:
    web = cfg.get("web_search", {})
    package = web.get("package") or "ddg-mcp-search"
    npx = find_executable("npx") or ("npx.cmd" if os.name == "nt" else "npx")
    uvx = find_executable("uvx") or "uvx"
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
        servers["web_fetch"] = {
            "command": uvx,
            "args": fetch_args,
        }
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


def run_claude_update_check(claude: str, enabled: bool = True) -> None:
    if not enabled:
        return
    if os.environ.get("CLAUDE_ANY_SKIP_CLAUDE_UPDATE") == "1":
        return
    print("Checking Claude Code update before launch...", flush=True)
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
        print("Claude Code update check timed out; continuing with current version.", flush=True)
        return
    except Exception as exc:
        print(f"Claude Code update check failed ({type(exc).__name__}); continuing.", flush=True)
        return
    out = (p.stdout or "").strip()
    if out:
        print(out, flush=True)
    if p.returncode != 0:
        print(f"Claude Code update check exited with {p.returncode}; continuing.", flush=True)


def launch_claude(
    passthrough: list[str],
    skip_menu: bool = False,
    web_search_override: bool | None = None,
    disable_skills_override: bool | None = None,
    update_check: bool = True,
) -> int:
    rc = run_prelaunch_menu(passthrough, skip_menu=skip_menu)
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
    cleanup_managed_services_for_provider(provider, pcfg, cfg, quiet=True)
    if not (use_native_anthropic or use_ollama_native or use_provider_native):
        start_router_if_needed()
    env = os.environ.copy()
    env["PATH"] = str(HOME / ".local" / "bin") + os.pathsep + env.get("PATH", "")
    launch_env = env_vars(cfg)
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
    claude = find_executable("claude")
    if not claude:
        raise RuntimeError("claude executable was not found in PATH or ~/.local/bin")
    run_claude_update_check(claude, enabled=update_check)
    claude = find_executable("claude") or claude
    extra_args: list[str] = []
    if should_attach_web_search(provider, cfg, web_search_override):
        extra_args.extend(["--mcp-config", str(write_duckduckgo_mcp_config(cfg))])
    if (
        should_disable_claude_skills(provider, cfg, disable_skills_override)
        and "--disable-slash-commands" not in passthrough
    ):
        extra_args.append("--disable-slash-commands")
    if should_disable_claude_skills(provider, cfg, disable_skills_override):
        extra_args.extend(["--disallowedTools", "Skill"])
    else:
        for skill_name in blocked_claude_skills(provider, cfg, disable_skills_override):
            extra_args.extend(["--disallowedTools", f"Skill({skill_name})"])
    if should_append_compat_prompt(provider, cfg) and not has_passthrough_option(passthrough, "--system-prompt"):
        extra_args.extend(["--append-system-prompt", NON_ANTHROPIC_COMPAT_PROMPT])
    cmd = [
        claude,
        "--dangerously-skip-permissions",
    ]
    model = env.get("CLAUDE_ANY_MODEL_ALIAS")
    if model:
        cmd.extend(["--model", model])
    cmd.extend(extra_args)
    cmd.extend(passthrough)
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
  claude-any models [PROVIDER]       List models
  claude-any api-key PROVIDER        Store API key securely
  claude-any set-api-key PROVIDER KEY
  claude-any web-search [on|off]     Auto-attach DuckDuckGo MCP for non-native providers
  claude-any web-fetch [on|off]      Auto-attach fetch MCP for web page content
  claude-any ollama-native [on|off]  Use Ollama's official Claude Code env path
  claude-any ollama-options [provider] [key=value ...]
                                      Set Ollama num_ctx/options/keep_alive/think
  claude-any provider-options [provider] [key=value ...]
                                      Set vLLM/NIM/NVIDIA output/context/timeouts
  claude-any test                    Test current provider/model Claude Code compatibility
  claude-any stop                    Stop router/proxy

Headless setup flags, namespaced to avoid Claude CLI collisions:
  claude-any --ca-provider PROVIDER  Set provider, then launch
  claude-any --ca-base-url URL       Set current provider base URL, then launch
  claude-any --ca-model MODEL_ID     Set provider model, then launch
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
  claude-any --ca-web-search         Force DuckDuckGo MCP for this launch
  claude-any --ca-no-web-search      Disable DuckDuckGo MCP for this launch
  claude-any --ca-disable-skills     Disable Claude Code skills for this launch
  claude-any --ca-enable-skills      Keep Claude Code skills enabled for this launch
  claude-any --ca-no-update-check    Skip Claude Code update check for this launch
  claude-any --ca-stop               Stop router/proxy
  claude-any --                      Pass all following args directly to Claude Code

Provider names: anthropic, ollama, ollama-cloud, vllm, nvidia-hosted, self-hosted-nim
Any other arguments are passed through to claude. Use -- before Claude flags that
collide with claude-any setup flags."""


def run_cli(argv: list[str]) -> int:
    if argv and argv[0] in ("help", "--help", "-h"):
        print(cli_usage())
        return 0
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
        if head in ("ollama-native", "ollama-compat"):
            cmd_ollama_native(argparse.Namespace(value=rest[0] if rest else None))
            return 0
        if head in ("ollama-options", "ollama-option", "ollama-opts"):
            cmd_ollama_options(argparse.Namespace(values=rest))
            return 0
        if head in ("provider-options", "provider-option", "provider-opts", "vllm-options", "nim-options"):
            cmd_provider_options(argparse.Namespace(values=rest))
            return 0
        if head in ("test", "compat", "compatibility"):
            timeout = 60.0
            if rest:
                try:
                    timeout = float(rest[0])
                except ValueError:
                    raise SystemExit("Usage: claude-any test [timeout_seconds]")
            cmd_test(argparse.Namespace(timeout=timeout))
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
    skip_menu = False
    web_search_override: bool | None = None
    disable_skills_override: bool | None = None
    update_check = True
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--ca-provider" or arg.startswith("--ca-provider="):
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
        elif arg == "--ca-web-search":
            web_search_override = True
            skip_menu = True
            i += 1
        elif arg == "--ca-no-web-search":
            web_search_override = False
            skip_menu = True
            i += 1
        elif arg == "--ca-disable-skills":
            disable_skills_override = True
            skip_menu = True
            i += 1
        elif arg == "--ca-enable-skills":
            disable_skills_override = False
            skip_menu = True
            i += 1
        elif arg == "--ca-no-update-check":
            update_check = False
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
    return launch_claude(
        passthrough,
        skip_menu=skip_menu,
        web_search_override=web_search_override,
        disable_skills_override=disable_skills_override,
        update_check=update_check,
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
    on = sub.add_parser("ollama-native")
    on.add_argument("value", nargs="?")
    on.set_defaults(func=cmd_ollama_native)
    oo = sub.add_parser("ollama-options")
    oo.add_argument("values", nargs="*")
    oo.set_defaults(func=cmd_ollama_options)
    po = sub.add_parser("provider-options")
    po.add_argument("values", nargs="*")
    po.set_defaults(func=cmd_provider_options)
    test = sub.add_parser("test")
    test.add_argument("timeout", nargs="?", type=float, default=120.0)
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
    ml = sub.add_parser("models")
    ml.add_argument("provider", nargs="?")
    ml.set_defaults(func=cmd_models)
    return p


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "cli":
        raise SystemExit(run_cli(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "launch":
        raise SystemExit(launch_claude(sys.argv[2:]))
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
