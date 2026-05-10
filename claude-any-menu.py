#!/usr/bin/env python3
from __future__ import annotations

import curses
import json
import subprocess
import sys
import time
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CTL = str(Path.home() / ".local/bin/claude-anyctl")
CONFIG = Path.home() / ".config/claude-any/config.json"
NCP_ENV = Path.home() / ".config/nvd-claude-proxy/.env"
PROVIDERS = [
    ("anthropic", "Anthropic"),
    ("ollama", "Ollama"),
    ("ollama-cloud", "Ollama Cloud"),
    ("vllm", "vLLM"),
    ("nvidia-hosted", "Nvidia Hosted"),
    ("self-hosted-nim", "Self Hosted NIM"),
]
APP_NAME = "Claude Any"
CREDITS = "Credits: One Ciel LLC"
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
        "ollama_options": "Ollama options",
        "provider_options": "Provider options",
        "test": "Test compatibility",
        "launch": "Launch Claude Code",
        "quit": "Quit",
        "title": "claude-any pre-launch",
        "select_language": "Enter selects language. Up/Down moves inside submenu. Esc closes submenu.",
        "select_provider": "Enter selects provider. Up/Down moves inside submenu. Esc closes submenu.",
        "select_model": "Enter selects model. Up/Down moves inside submenu. Esc closes submenu. Custom input is at the end.",
        "select_ollama_options": "Enter applies this Ollama option. Custom input accepts KEY=VALUE or unset:KEY.",
        "select_provider_options": "Enter applies this provider option. Custom input accepts KEY=VALUE or unset:KEY.",
        "test_result": "Compatibility result is shown inline. Esc closes the result. Enter runs the test again.",
        "help_launch": "Enter launches Claude Code with the selected provider and model.",
        "help_test": "Enter tests current provider/model with a minimal Claude Code tool request.",
        "help_language": "Enter expands language submenu inline.",
        "help_provider": "Enter expands provider submenu inline.",
        "help_model": "Enter expands model submenu inline when the provider endpoint is reachable.",
        "help_ollama_options": "Enter expands Ollama context and generation options.",
        "help_provider_options": "Enter expands provider output/context/timeout options.",
        "help_api_key": "Enter opens secure API key setup in the terminal. Keys are not pasted into Claude Code.",
        "help_base_url": "Enter edits the current provider base URL on this row.",
        "help_quit": "Enter exits without launching Claude Code.",
        "running_test": "Running compatibility test...",
        "test_passed": "Compatibility test passed.",
        "test_failed": "Compatibility test failed.",
        "loading_models": "Loading models from current provider...",
        "api_key_unchanged": "API key unchanged.",
    },
    "ko": {
        "language": "언어",
        "provider": "프로바이더",
        "api_key": "API 키",
        "base_url": "Base URL",
        "model": "모델",
        "ollama_options": "Ollama 옵션",
        "provider_options": "프로바이더 옵션",
        "test": "호환성 테스트",
        "launch": "Claude Code 실행",
        "quit": "종료",
        "title": "claude-any 실행 전 설정",
        "select_language": "Enter로 언어를 선택합니다. 위/아래로 이동, Esc로 닫기.",
        "select_provider": "Enter로 프로바이더를 선택합니다. 위/아래로 이동, Esc로 닫기.",
        "select_model": "Enter로 모델을 선택합니다. 위/아래로 이동, Esc로 닫기. 마지막 항목은 직접 입력입니다.",
        "select_ollama_options": "Enter로 Ollama 옵션을 적용합니다. 직접 입력은 KEY=VALUE 또는 unset:KEY를 받습니다.",
        "select_provider_options": "Enter로 프로바이더 옵션을 적용합니다. 직접 입력은 KEY=VALUE 또는 unset:KEY를 받습니다.",
        "test_result": "호환성 결과가 메뉴 안에 표시됩니다. Esc로 닫고 Enter로 다시 테스트합니다.",
        "help_launch": "선택한 프로바이더와 모델로 Claude Code를 실행합니다.",
        "help_test": "현재 프로바이더/모델에 최소 Claude Code 도구 요청을 보내 호환성을 확인합니다.",
        "help_language": "언어 선택 메뉴를 펼칩니다.",
        "help_provider": "프로바이더 선택 메뉴를 펼칩니다.",
        "help_model": "프로바이더 엔드포인트가 유효하면 모델 선택 메뉴를 펼칩니다.",
        "help_ollama_options": "Ollama 컨텍스트 크기와 생성 파라미터 메뉴를 펼칩니다.",
        "help_provider_options": "프로바이더의 출력 토큰, 컨텍스트, 타임아웃 옵션 메뉴를 펼칩니다.",
        "help_api_key": "API 키 입력을 이 터미널에서 안전하게 엽니다. 키는 Claude Code 채팅에 붙여넣지 않습니다.",
        "help_base_url": "현재 프로바이더의 Base URL을 이 줄에서 수정합니다.",
        "help_quit": "Claude Code를 실행하지 않고 종료합니다.",
        "running_test": "호환성 테스트 실행 중...",
        "test_passed": "호환성 테스트 성공.",
        "test_failed": "호환성 테스트 실패.",
        "loading_models": "현재 프로바이더에서 모델을 불러오는 중...",
        "api_key_unchanged": "API 키는 변경되지 않았습니다.",
    },
    "ja": {
        "language": "言語",
        "provider": "プロバイダー",
        "api_key": "APIキー",
        "base_url": "Base URL",
        "model": "モデル",
        "ollama_options": "Ollamaオプション",
        "provider_options": "プロバイダーオプション",
        "test": "互換性テスト",
        "launch": "Claude Codeを起動",
        "quit": "終了",
        "title": "claude-any 起動前設定",
        "select_language": "Enterで言語を選択します。上下で移動、Escで閉じます。",
        "select_provider": "Enterでプロバイダーを選択します。上下で移動、Escで閉じます。",
        "select_model": "Enterでモデルを選択します。上下で移動、Escで閉じます。最後は手入力です。",
        "select_ollama_options": "EnterでOllamaオプションを適用します。手入力はKEY=VALUEまたはunset:KEYです。",
        "select_provider_options": "Enterでプロバイダーオプションを適用します。手入力はKEY=VALUEまたはunset:KEYです。",
        "test_result": "互換性結果はメニュー内に表示されます。Escで閉じ、Enterで再テストします。",
        "help_launch": "選択したプロバイダーとモデルでClaude Codeを起動します。",
        "help_test": "現在のプロバイダー/モデルへ最小のClaude Codeツール要求を送り互換性を確認します。",
        "help_language": "言語選択メニューを展開します。",
        "help_provider": "プロバイダー選択メニューを展開します。",
        "help_model": "プロバイダーのエンドポイントが有効な場合、モデル選択メニューを展開します。",
        "help_ollama_options": "Ollamaのコンテキストサイズと生成パラメータを開きます。",
        "help_provider_options": "プロバイダーの出力トークン、コンテキスト、タイムアウト設定を開きます。",
        "help_api_key": "APIキー入力をこの端末で安全に開きます。キーはClaude Codeチャットに貼り付けません。",
        "help_base_url": "現在のプロバイダーのBase URLをこの行で編集します。",
        "help_quit": "Claude Codeを起動せずに終了します。",
        "running_test": "互換性テストを実行中...",
        "test_passed": "互換性テスト成功。",
        "test_failed": "互換性テスト失敗。",
        "loading_models": "現在のプロバイダーからモデルを読み込み中...",
        "api_key_unchanged": "APIキーは変更されませんでした。",
    },
    "zh": {
        "language": "语言",
        "provider": "提供商",
        "api_key": "API 密钥",
        "base_url": "Base URL",
        "model": "模型",
        "ollama_options": "Ollama 选项",
        "provider_options": "提供商选项",
        "test": "兼容性测试",
        "launch": "启动 Claude Code",
        "quit": "退出",
        "title": "claude-any 启动前设置",
        "select_language": "按 Enter 选择语言。上下移动，Esc 关闭。",
        "select_provider": "按 Enter 选择提供商。上下移动，Esc 关闭。",
        "select_model": "按 Enter 选择模型。上下移动，Esc 关闭。最后一项可手动输入。",
        "select_ollama_options": "按 Enter 应用 Ollama 选项。手动输入支持 KEY=VALUE 或 unset:KEY。",
        "select_provider_options": "按 Enter 应用提供商选项。手动输入支持 KEY=VALUE 或 unset:KEY。",
        "test_result": "兼容性结果会在菜单内显示。Esc 关闭，Enter 重新测试。",
        "help_launch": "使用所选提供商和模型启动 Claude Code。",
        "help_test": "向当前提供商/模型发送最小 Claude Code 工具请求以检查兼容性。",
        "help_language": "展开语言选择菜单。",
        "help_provider": "展开提供商选择菜单。",
        "help_model": "当提供商端点可用时展开模型选择菜单。",
        "help_ollama_options": "展开 Ollama 上下文大小和生成参数。",
        "help_provider_options": "展开提供商输出 token、上下文和超时选项。",
        "help_api_key": "在此终端安全输入 API 密钥。不要把密钥粘贴到 Claude Code 聊天中。",
        "help_base_url": "在这一行编辑当前提供商的 Base URL。",
        "help_quit": "不启动 Claude Code 并退出。",
        "running_test": "正在运行兼容性测试...",
        "test_passed": "兼容性测试成功。",
        "test_failed": "兼容性测试失败。",
        "loading_models": "正在从当前提供商加载模型...",
        "api_key_unchanged": "API 密钥未更改。",
    },
}


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
            "Hosted catalog models are OpenAI-style, so claude-any keeps a compatibility route for Claude Code.",
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
            "Hosted catalog 모델은 OpenAI 방식이므로 Claude Code에는 claude-any 호환 라우트를 유지합니다.",
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
            "Hosted catalogモデルはOpenAI形式のため、Claude Codeにはclaude-any互換ルートを維持します。",
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
            "Hosted catalog 模型是 OpenAI 风格，因此 Claude Code 仍使用 claude-any 兼容路由。",
        ],
    },
}


def init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except Exception:
        pass
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_RED, -1)
    curses.init_pair(5, curses.COLOR_WHITE, -1)
    orange = 208 if getattr(curses, "COLORS", 0) > 208 else curses.COLOR_YELLOW
    curses.init_pair(6, orange, -1)


def cp(n: int) -> int:
    return curses.color_pair(n) if curses.has_colors() else curses.A_NORMAL


def load_cfg() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text())
        except Exception:
            pass
    return {"current_provider": "nvidia-hosted", "providers": {}}


KNOWN_NVIDIA_MODEL_STATUS = {
    "claude-nvidia-llama-3.1-nemotron-ultra-253b-v1": ("FAIL 404", "listed but not callable for this NVIDIA account"),
}
COMPAT_OK_TTL_SECONDS = 24 * 60 * 60
COMPAT_FAIL_TTL_SECONDS = 5 * 60


def cache_age_seconds(entry: dict) -> int | None:
    try:
        tested_at = int(entry.get("tested_at"))
    except Exception:
        return None
    return max(0, int(time.time()) - tested_at)


def cache_entry_fresh(entry: dict) -> bool:
    age = cache_age_seconds(entry)
    if age is None:
        return False
    ttl = COMPAT_OK_TTL_SECONDS if entry.get("ok") else COMPAT_FAIL_TTL_SECONDS
    return age <= ttl


def human_age(seconds: int | None) -> str:
    if seconds is None:
        return "unknown age"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def compatibility_entry(provider: str, upstream: str, alias: str | None = None) -> dict | None:
    cache = load_cfg().get("compatibility_cache", {})
    if not isinstance(cache, dict):
        return None
    provider_cache = cache.get(provider, {})
    if not isinstance(provider_cache, dict):
        return None
    for key in (alias, upstream):
        if key and isinstance(provider_cache.get(key), dict):
            entry = provider_cache[key]
            return entry if cache_entry_fresh(entry) else None
    return None


def compatibility_badge(provider: str, upstream: str, alias: str | None = None) -> str:
    if provider == "nvidia-hosted":
        known = KNOWN_NVIDIA_MODEL_STATUS.get(upstream) or (KNOWN_NVIDIA_MODEL_STATUS.get(alias or "") if alias else None)
        if known:
            return f"[{known[0]}]"
    entry = compatibility_entry(provider, upstream, alias)
    if not entry:
        return "[untested]" if provider == "nvidia-hosted" else ""
    if entry.get("ok"):
        return "[OK]"
    code = entry.get("code")
    if code:
        return f"[FAIL {code}]"
    msg = str(entry.get("message") or "").lower()
    if "timeout" in msg or "timed out" in msg:
        return "[TIMEOUT]"
    return "[FAIL]"


def current_compatibility_line(provider: str, pcfg: dict) -> str | None:
    model = str(pcfg.get("current_model") or "")
    if not model:
        return "Compatibility: no model selected"
    badge = compatibility_badge(provider, model, model)
    if badge:
        entry = compatibility_entry(provider, model, model)
        if entry and not entry.get("ok"):
            msg = str(entry.get("message") or entry.get("diagnosis") or "")[:90]
            return f"Compatibility: {badge} {model} {msg}".strip()
        known = KNOWN_NVIDIA_MODEL_STATUS.get(model)
        if known:
            return f"Compatibility: {badge} {model} - {known[1]}"
        return f"Compatibility: {badge} {model}"
    return None


def current_language() -> str:
    lang = load_cfg().get("language", "en")
    return lang if lang in LANGUAGES else "en"


def t(key: str) -> str:
    lang = current_language()
    return UI_TEXT.get(lang, UI_TEXT["en"]).get(key, UI_TEXT["en"].get(key, key))


def run_cmd(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def meaningful_key(value: str | None) -> bool:
    return bool(value and value not in ("dummy", "not-used", "ollama"))


def api_key_status(provider: str, pcfg: dict) -> str:
    if provider == "nvidia-hosted":
        return "API key: set (NVIDIA)" if meaningful_key(read_env_file(NCP_ENV).get("NVIDIA_API_KEY")) else "API key: missing (NVIDIA required)"
    if provider == "anthropic":
        return "API key: set (Anthropic)" if meaningful_key(pcfg.get("api_key")) else "API key: not set (use API key or Claude login)"
    if provider == "ollama-cloud":
        return "API key: set (Ollama Cloud)" if meaningful_key(pcfg.get("api_key")) else "API key: missing (Ollama Cloud required)"
    key = pcfg.get("api_key")
    if meaningful_key(key):
        return "API key: set"
    if provider == "ollama":
        return "API key: not required for Ollama"
    return "API key: optional or not configured"


def join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return base + path[3:]
    return base + path


def probe_base_url(provider: str, pcfg: dict) -> str:
    base = (pcfg.get("base_url") or "").rstrip("/")
    if not base:
        return "Base URL: missing"
    if "your-" in base:
        return f"Base URL: placeholder ({base})"
    if provider == "nvidia-hosted":
        return f"Base URL: NVIDIA hosted ({base}); proxy starts on launch"
    path = "/api/tags" if provider in ("ollama", "ollama-cloud") else "/v1/models"
    url = join_url(base, path)
    headers = {}
    key = pcfg.get("api_key")
    if meaningful_key(key):
        headers = {"x-api-key": key, "authorization": f"Bearer {key}"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            body = resp.read(131072).decode("utf-8", errors="ignore")
        count = ""
        try:
            data = json.loads(body)
            if provider in ("ollama", "ollama-cloud"):
                count = f", {len(data.get('models', []))} models"
            elif isinstance(data.get("data"), list):
                count = f", {len(data['data'])} models"
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


def preflight_checks() -> list[str]:
    provider, pcfg = current_provider_cfg()
    lang = current_language()
    notes = PROVIDER_NOTES.get(lang, PROVIDER_NOTES["en"]).get(provider, [])
    lines = [
        probe_base_url(provider, pcfg),
        api_key_status(provider, pcfg),
        *notes,
    ]
    compat = current_compatibility_line(provider, pcfg)
    if compat:
        lines.append(compat)
    return lines


def provider_preview_checks(provider: str) -> list[str]:
    cfg = load_cfg()
    pcfg = cfg.get("providers", {}).get(provider, {})
    lang = current_language()
    notes = PROVIDER_NOTES.get(lang, PROVIDER_NOTES["en"]).get(provider, [])
    return [
        f"Base URL: {pcfg.get('base_url') or 'unset'}",
        api_key_status(provider, pcfg),
        *notes,
    ]


def selected_provider_value(sub: dict | None) -> str | None:
    if not sub or sub.get("kind") != "provider":
        return None
    try:
        return str(sub["items"][sub["idx"]]["value"])
    except Exception:
        return None


def status_text() -> list[str]:
    _, out = run_cmd([CTL, "status"])
    return out.strip().splitlines() if out else ["status unavailable"]


def current_provider() -> str:
    return load_cfg().get("current_provider", "nvidia-hosted")


def current_provider_cfg() -> tuple[str, dict]:
    cfg = load_cfg()
    provider = cfg.get("current_provider", "nvidia-hosted")
    return provider, cfg.get("providers", {}).get(provider, {})


def is_ollama_provider(provider: str) -> bool:
    return provider in ("ollama", "ollama-cloud")


def has_provider_options(provider: str) -> bool:
    return provider in ("vllm", "nvidia-hosted", "self-hosted-nim")


def ollama_ctx_text(pcfg: dict) -> str:
    value = pcfg.get("num_ctx", "auto")
    if str(value).lower() == "auto":
        return f"auto {pcfg.get('num_ctx_min', 32768)}-{pcfg.get('num_ctx_max', 131072)}"
    return str(value)


def ollama_options_summary(pcfg: dict) -> str:
    parts = [
        f"ctx {ollama_ctx_text(pcfg)}",
        f"keep {pcfg.get('keep_alive', 'default')}",
        f"think {str(bool(pcfg.get('think', False))).lower()}",
        f"timeout {pcfg.get('request_timeout_ms', 'default')}ms",
    ]
    opts = pcfg.get("ollama_options") or {}
    if isinstance(opts, dict) and opts:
        extra = ", ".join(f"{k}={v}" for k, v in sorted(opts.items())[:3])
        parts.append(extra)
    return "; ".join(parts)


def provider_options_summary(provider: str, pcfg: dict) -> str:
    timeout = pcfg.get("request_timeout_ms", "default")
    timeout_text = f"{timeout}ms" if timeout != "default" else "default"
    parts = [
        f"max {pcfg.get('max_output_tokens', 'default')}",
        f"timeout {timeout_text}",
    ]
    if provider in ("vllm", "self-hosted-nim"):
        parts.insert(0, f"ctx {pcfg.get('context_window', 'default')}")
        parts.insert(1, f"reserve {pcfg.get('context_reserve_tokens', 'default')}")
        parts.append(f"native {str(bool(pcfg.get('native_compat', True))).lower()}")
    return "; ".join(parts)


def main_items() -> list[tuple[str, str]]:
    provider, pcfg = current_provider_cfg()
    lang = current_language()
    model = pcfg.get("current_model", "unset")
    base = pcfg.get("base_url", "unset")
    rows: list[tuple[str, str]] = []

    def add(key: str, label: str) -> None:
        rows.append((key, f"{len(rows)}. {label}"))

    add("language", f"{t('language')}  [{LANGUAGES.get(lang, lang)}]")
    add("provider", f"{t('provider')}  [{provider}]")
    add("api-key", t("api_key"))
    add("base-url", f"{t('base_url')}  [{base}]")
    add("model", f"{t('model')}  [{model}]")
    if is_ollama_provider(provider):
        add("ollama-options", f"{t('ollama_options')}  [{ollama_options_summary(pcfg)}]")
    if has_provider_options(provider):
        add("provider-options", f"{t('provider_options')}  [{provider_options_summary(provider, pcfg)}]")
    add("test", t("test"))
    add("launch", t("launch"))
    rows.append(("quit", t("quit")))
    return rows


def settings_ready_except_api_key() -> bool:
    provider, pcfg = current_provider_cfg()
    base = pcfg.get("base_url", "")
    model = pcfg.get("current_model", "")
    return bool(provider and base and model and "your-" not in base)

def default_base_url(provider: str) -> str:
    return {
        "anthropic": "https://api.anthropic.com",
        "ollama": "http://your-ollama:11434",
        "ollama-cloud": "https://ollama.com",
        "vllm": "http://your-vllm:8000",
        "nvidia-hosted": "https://integrate.api.nvidia.com/v1",
        "self-hosted-nim": "http://your-nim:8000",
    }.get(provider, "http://localhost:8000")


def help_for_action(action: str, sub_kind: str | None = None) -> str:
    if sub_kind == "language":
        return t("select_language")
    if sub_kind == "provider":
        return t("select_provider")
    if sub_kind == "model":
        return t("select_model")
    if sub_kind == "ollama-options":
        return t("select_ollama_options")
    if sub_kind == "provider-options":
        return t("select_provider_options")
    if sub_kind == "test-result":
        return t("test_result")
    return {
        "launch": t("help_launch"),
        "test": t("help_test"),
        "language": t("help_language"),
        "provider": t("help_provider"),
        "model": t("help_model"),
        "ollama-options": t("help_ollama_options"),
        "provider-options": t("help_provider_options"),
        "api-key": t("help_api_key"),
        "base-url": t("help_base_url"),
        "quit": t("help_quit"),
    }.get(action, "Enter selects this action.")


def get_models_for_current_provider() -> tuple[list[tuple[str, str]], str]:
    code, out = run_cmd([CTL, "models"])
    models: list[tuple[str, str]] = []
    for line in out.splitlines()[1:]:
        if "\t" not in line:
            continue
        alias, upstream = line.split("\t", 1)
        if alias.strip() and upstream.strip():
            models.append((upstream.strip(), alias.strip()))
    return models, out


def build_provider_submenu() -> dict:
    cfg = load_cfg()
    current = cfg.get("current_provider", "nvidia-hosted")
    items = []
    idx = 0
    for i, (key, label) in enumerate(PROVIDERS):
        if key == current:
            idx = i
        base = cfg.get("providers", {}).get(key, {}).get("base_url", "")
        items.append({"value": key, "label": f"{label:<16} {key:<15} {base}", "current": key == current})
    return {"kind": "provider", "parent": "provider", "items": items, "idx": idx, "offset": 0}


def build_language_submenu() -> dict:
    current = current_language()
    items = []
    idx = 0
    for i, (code, label) in enumerate(LANGUAGES.items()):
        if code == current:
            idx = i
        items.append({"value": code, "label": f"{code:<2} {label}", "current": code == current})
    return {"kind": "language", "parent": "language", "items": items, "idx": idx, "offset": 0}


def build_api_key_submenu() -> dict:
    current = current_provider()
    items = []
    idx = 0
    for i, (key, label) in enumerate(PROVIDERS):
        if key == current:
            idx = i
        items.append({"value": key, "label": f"{label:<16} {key:<15}", "current": key == current})
    return {"kind": "api-key", "parent": "api-key", "items": items, "idx": idx, "offset": 0}

def build_model_submenu() -> tuple[dict | None, list[str]]:
    models, raw = get_models_for_current_provider()
    if not models:
        lines = raw.strip().splitlines() or ["No models found. Use custom input."]
        return None, lines[:2]
    provider, pcfg = current_provider_cfg()
    current = pcfg.get("current_model", "")
    items = []
    idx = 0
    for i, (upstream, alias) in enumerate(models):
        is_current = upstream == current or alias == current
        if is_current:
            idx = i
        badge = compatibility_badge(provider, upstream, alias)
        description = ""
        known = KNOWN_NVIDIA_MODEL_STATUS.get(upstream) or KNOWN_NVIDIA_MODEL_STATUS.get(alias)
        entry = compatibility_entry(provider, upstream, alias)
        if known:
            description = known[1]
        elif entry:
            state = "OK" if entry.get("ok") else "failed"
            detail = entry.get("diagnosis") or entry.get("message") or ""
            description = f"Last compatibility test: {state} ({human_age(cache_age_seconds(entry))}). {detail}".strip()
        items.append({
            "value": upstream,
            "label": f"{badge:<11} {upstream:<58} {alias}",
            "current": is_current,
            "description": description,
        })
    items.append({"value": "__custom__", "label": "Custom model id...", "current": False})
    return {"kind": "model", "parent": "model", "items": items, "idx": idx, "offset": 0}, []


OLLAMA_OPTION_DESCRIPTIONS = {
    "__edit_num_ctx__": {
        "en": "Edit Ollama num_ctx. This is the context window sent to Ollama; it cannot exceed the server/model limit.",
        "ko": "Ollama num_ctx를 수정합니다. 한 번에 볼 컨텍스트 창이며 서버/모델 한계를 넘게 설정해도 실제 한계는 늘지 않습니다.",
        "ja": "Ollamaのnum_ctxを編集します。Ollamaへ送るコンテキスト幅で、サーバー/モデル上限は超えられません。",
        "zh": "编辑 Ollama num_ctx。这是发送给 Ollama 的上下文窗口，不能超过服务器/模型上限。",
    },
    "__edit_min__": {
        "en": "Edit the minimum context used when num_ctx is auto. Small requests will not go below this value.",
        "ko": "num_ctx=auto일 때 사용할 최소 컨텍스트입니다. 작은 요청도 이 값보다 작게 내려가지 않습니다.",
        "ja": "num_ctx=auto時の最小コンテキストです。小さな要求でもこの値未満にはなりません。",
        "zh": "编辑 num_ctx=auto 时的最小上下文。小请求也不会低于此值。",
    },
    "__edit_max__": {
        "en": "Edit the maximum context used when num_ctx is auto. Keep it at or below the real server context limit.",
        "ko": "num_ctx=auto일 때 사용할 최대 컨텍스트입니다. 실제 서버 컨텍스트 한계 이하로 두는 것이 맞습니다.",
        "ja": "num_ctx=auto時の最大コンテキストです。実際のサーバー上限以下にしてください。",
        "zh": "编辑 num_ctx=auto 时的最大上下文。应不高于真实服务器上下文上限。",
    },
    "__edit_keep_alive__": {
        "en": "Edit how long Ollama keeps the model loaded after a request. Longer values reduce reloads but hold memory.",
        "ko": "요청 후 Ollama가 모델을 메모리에 유지하는 시간입니다. 길수록 재로딩은 줄지만 메모리를 더 오래 잡습니다.",
        "ja": "要求後にOllamaがモデルを保持する時間です。長いほど再読み込みは減りますがメモリを保持します。",
        "zh": "编辑请求后 Ollama 保持模型加载的时间。更长可减少重载，但会占用内存。",
    },
    "__edit_temperature__": {
        "en": "Edit sampling temperature. Higher is more varied; lower is more deterministic.",
        "ko": "샘플링 temperature입니다. 높을수록 답변이 다양해지고, 낮을수록 결정적으로 동작합니다.",
        "ja": "サンプリングtemperatureです。高いほど多様、低いほど決定的になります。",
        "zh": "编辑采样 temperature。越高越多样，越低越确定。",
    },
    "__edit_top_p__": {
        "en": "Edit nucleus sampling top_p. Lower values restrict token choices; 0.8 is a moderate default.",
        "ko": "누적 확률 top_p입니다. 낮을수록 후보 토큰을 좁히며, 0.8은 중간 정도의 기본값입니다.",
        "ja": "nucleus samplingのtop_pです。低いほど候補を絞り、0.8は中程度の既定値です。",
        "zh": "编辑 nucleus sampling top_p。越低候选越窄；0.8 是中等默认值。",
    },
    "__edit_max_tokens__": {
        "en": "Edit max output tokens (Ollama num_predict). Input plus reserved output must fit in the context window.",
        "ko": "최대 출력 토큰(Ollama num_predict)입니다. 입력과 예약 출력이 컨텍스트 창 안에 같이 들어가야 합니다.",
        "ja": "最大出力トークン(Ollama num_predict)です。入力と予約出力は同じコンテキスト内に収まる必要があります。",
        "zh": "编辑最大输出 token（Ollama num_predict）。输入加预留输出必须放进上下文窗口。",
    },
    "__edit_timeout__": {
        "en": "Edit upstream wait timeout in milliseconds. 1800000 means 30 minutes.",
        "ko": "업스트림 응답 대기 시간(ms)입니다. 1800000은 30분입니다.",
        "ja": "上流応答待ちタイムアウト(ms)です。1800000は30分です。",
        "zh": "编辑上游响应等待超时（毫秒）。1800000 表示 30 分钟。",
    },
    "__custom__": {
        "en": "Enter any Ollama option as KEY=VALUE, or unset:KEY to remove it.",
        "ko": "임의의 Ollama 옵션을 KEY=VALUE로 입력합니다. 삭제하려면 unset:KEY를 입력합니다.",
        "ja": "任意のOllamaオプションをKEY=VALUEで入力します。削除はunset:KEYです。",
        "zh": "用 KEY=VALUE 输入任意 Ollama 选项；用 unset:KEY 删除。",
    },
}


def ollama_option_description(value: str) -> str:
    lang = current_language()
    if value in OLLAMA_OPTION_DESCRIPTIONS:
        entry = OLLAMA_OPTION_DESCRIPTIONS[value]
        return entry.get(lang, entry["en"])
    if value.startswith("num_ctx=auto"):
        return {
            "en": "Use automatic context sizing based on request size, bounded by the configured min/max.",
            "ko": "요청 크기에 따라 컨텍스트를 자동 선택합니다. 설정된 최소/최대 범위 안에서만 움직입니다.",
            "ja": "要求サイズに応じてコンテキストを自動選択します。設定した最小/最大範囲内です。",
            "zh": "根据请求大小自动选择上下文，并限制在设置的最小/最大范围内。",
        }.get(lang, "Use automatic context sizing based on request size, bounded by the configured min/max.")
    if value.startswith("num_ctx="):
        return {
            "en": "Use a fixed context window for every Ollama request. Larger values use more memory and may be slower.",
            "ko": "모든 Ollama 요청에 고정 컨텍스트를 사용합니다. 값이 클수록 메모리를 더 쓰고 느려질 수 있습니다.",
            "ja": "全てのOllama要求で固定コンテキストを使います。大きいほどメモリ使用量と遅延が増えます。",
            "zh": "为每个 Ollama 请求使用固定上下文。值越大内存占用越高，也可能更慢。",
        }.get(lang, "Use a fixed context window for every Ollama request.")
    if value.startswith("min="):
        return {
            "en": "Set the lower bound for automatic num_ctx selection.",
            "ko": "자동 num_ctx 선택의 하한값을 설정합니다.",
            "ja": "自動num_ctx選択の下限を設定します。",
            "zh": "设置自动 num_ctx 选择的下限。",
        }.get(lang, "Set the lower bound for automatic num_ctx selection.")
    if value.startswith("max="):
        return {
            "en": "Set the upper bound for automatic num_ctx selection.",
            "ko": "자동 num_ctx 선택의 상한값을 설정합니다.",
            "ja": "自動num_ctx選択の上限を設定します。",
            "zh": "设置自动 num_ctx 选择的上限。",
        }.get(lang, "Set the upper bound for automatic num_ctx selection.")
    if value.startswith("keep_alive="):
        return OLLAMA_OPTION_DESCRIPTIONS["__edit_keep_alive__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__edit_keep_alive__"]["en"])
    if value.startswith("think="):
        return {
            "en": "Toggle Ollama thinking output support. Claude Code may not display provider-specific thinking cleanly.",
            "ko": "Ollama thinking 출력 요청 여부입니다. Claude Code가 provider별 thinking을 항상 깔끔하게 표시하지는 않습니다.",
            "ja": "Ollama thinking出力の要求を切り替えます。Claude Code側で常に綺麗に表示されるとは限りません。",
            "zh": "切换 Ollama thinking 输出请求。Claude Code 不一定能完整显示各提供商的 thinking。",
        }.get(lang, "Toggle Ollama thinking output support.")
    if value.startswith("temperature="):
        return OLLAMA_OPTION_DESCRIPTIONS["__edit_temperature__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__edit_temperature__"]["en"])
    if value.startswith("top_p="):
        return OLLAMA_OPTION_DESCRIPTIONS["__edit_top_p__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__edit_top_p__"]["en"])
    if value.startswith(("max_tokens=", "num_predict=")):
        return OLLAMA_OPTION_DESCRIPTIONS["__edit_max_tokens__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__edit_max_tokens__"]["en"])
    if value.startswith("timeout="):
        return OLLAMA_OPTION_DESCRIPTIONS["__edit_timeout__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__edit_timeout__"]["en"])
    return OLLAMA_OPTION_DESCRIPTIONS["__custom__"].get(lang, OLLAMA_OPTION_DESCRIPTIONS["__custom__"]["en"])


def build_ollama_options_submenu() -> dict:
    provider, pcfg = current_provider_cfg()
    ctx = pcfg.get("num_ctx", "auto")
    keep = str(pcfg.get("keep_alive", "5m"))
    think = bool(pcfg.get("think", False))
    options = pcfg.get("ollama_options") or {}
    if not isinstance(options, dict):
        options = {}
    choices = [
        ("__edit_num_ctx__", f"Edit num_ctx [{ollama_ctx_text(pcfg)}]", False),
        ("__edit_min__", f"Edit auto minimum [{pcfg.get('num_ctx_min', 32768)}]", False),
        ("__edit_max__", f"Edit auto maximum [{pcfg.get('num_ctx_max', 131072)}]", False),
        ("__edit_keep_alive__", f"Edit keep_alive [{keep}]", False),
        ("__edit_temperature__", f"Edit temperature [{options.get('temperature', 'unset')}]", False),
        ("__edit_top_p__", f"Edit top_p [{options.get('top_p', 'unset')}]", False),
        ("__edit_max_tokens__", f"Edit max_tokens/num_predict [{options.get('num_predict', 'unset')}]", False),
        ("__edit_timeout__", f"Edit timeout ms [{pcfg.get('request_timeout_ms', 'default')}]", False),
        ("__custom__", "Custom KEY=VALUE or unset:KEY...", False),
        ("num_ctx=auto", f"num_ctx auto ({pcfg.get('num_ctx_min', 32768)}-{pcfg.get('num_ctx_max', 131072)})", str(ctx).lower() == "auto"),
        ("num_ctx=32768", "num_ctx 32768", ctx == 32768),
        ("num_ctx=65536", "num_ctx 65536", ctx == 65536),
        ("num_ctx=131072", "num_ctx 131072", ctx == 131072),
        ("min=32768", "auto minimum 32768", pcfg.get("num_ctx_min", 32768) == 32768),
        ("max=131072", "auto maximum 131072", pcfg.get("num_ctx_max", 131072) == 131072),
        ("keep_alive=5m", "keep_alive 5m", keep == "5m"),
        ("keep_alive=30m", "keep_alive 30m", keep == "30m"),
        ("think=false", "think false", not think),
        ("think=true", "think true", think),
        ("temperature=0.7", f"temperature 0.7 (current {options.get('temperature', 'unset')})", options.get("temperature") == 0.7),
        ("top_p=0.8", f"top_p 0.8 (current {options.get('top_p', 'unset')})", options.get("top_p") == 0.8),
        ("max_tokens=4096", f"max_tokens 4096 (current {options.get('num_predict', 'unset')})", options.get("num_predict") == 4096),
        ("timeout=1800000", f"timeout 1800000ms (current {pcfg.get('request_timeout_ms', 'default')})", pcfg.get("request_timeout_ms") == 1800000),
    ]
    items = [
        {"value": value, "label": label, "current": current, "description": ollama_option_description(value)}
        for value, label, current in choices
    ]
    return {"kind": "ollama-options", "parent": "ollama-options", "items": items, "idx": 0, "offset": 0}


PROVIDER_OPTION_DESCRIPTIONS = {
    "__edit_context_window__": {
        "en": "Edit the context window value used by claude-any tests and router caps. Native mode cannot raise the real server limit.",
        "ko": "claude-any 테스트와 라우터 제한 계산에 쓰는 컨텍스트 값입니다. native 모드에서는 실제 서버 한계를 늘리지 못합니다.",
        "ja": "claude-anyのテストとルーター制限計算に使うコンテキスト値です。nativeモードでは実サーバー上限は増やせません。",
        "zh": "编辑 claude-any 测试和路由器限制计算使用的上下文值。native 模式不能提高真实服务器上限。",
    },
    "__edit_reserve__": {
        "en": "Reserve input-side room when claude-any router caps max_tokens. This is ignored by direct native Claude Code requests.",
        "ko": "claude-any 라우터가 max_tokens를 줄일 때 입력 쪽 여유로 남기는 토큰입니다. direct native 요청에는 적용되지 않습니다.",
        "ja": "claude-anyルーターがmax_tokensを制限する時に入力側へ残す余裕です。direct native要求では無視されます。",
        "zh": "claude-any 路由器限制 max_tokens 时预留给输入侧的空间。direct native 请求会忽略它。",
    },
    "__edit_max_output__": {
        "en": "Set Claude Code's CLAUDE_CODE_MAX_OUTPUT_TOKENS and the claude-any router cap. 4096 is the default.",
        "ko": "Claude Code의 CLAUDE_CODE_MAX_OUTPUT_TOKENS와 claude-any 라우터 출력 제한입니다. 기본값은 4096입니다.",
        "ja": "Claude CodeのCLAUDE_CODE_MAX_OUTPUT_TOKENSとclaude-anyルーターの出力制限です。既定値は4096です。",
        "zh": "设置 Claude Code 的 CLAUDE_CODE_MAX_OUTPUT_TOKENS 和 claude-any 路由器输出上限。默认 4096。",
    },
    "__edit_timeout__": {
        "en": "Edit claude-any compatibility-test/router upstream timeout in milliseconds. Claude Code native networking has its own timeout behavior.",
        "ko": "claude-any 호환성 테스트/라우터의 업스트림 대기 시간(ms)입니다. Claude Code native 네트워크 대기는 자체 동작을 따릅니다.",
        "ja": "claude-any互換性テスト/ルーターの上流タイムアウト(ms)です。Claude Code native通信は独自の挙動です。",
        "zh": "编辑 claude-any 兼容性测试/路由器上游超时（毫秒）。Claude Code native 网络有自身超时行为。",
    },
    "__edit_native__": {
        "en": "Toggle direct Anthropic Messages compatibility. Use it for vLLM/self-hosted NIM servers that implement /v1/messages.",
        "ko": "Anthropic Messages 호환 엔드포인트에 직접 연결할지 정합니다. /v1/messages를 구현한 vLLM/self-hosted NIM에서 사용합니다.",
        "ja": "Anthropic Messages互換エンドポイントへ直接接続するかを切り替えます。/v1/messages対応のvLLM/self-hosted NIMで使います。",
        "zh": "切换是否直接连接 Anthropic Messages 兼容端点。用于实现 /v1/messages 的 vLLM/self-hosted NIM。",
    },
    "__custom__": {
        "en": "Enter provider option as KEY=VALUE, or unset:KEY to remove it.",
        "ko": "프로바이더 옵션을 KEY=VALUE로 입력합니다. 삭제하려면 unset:KEY를 입력합니다.",
        "ja": "プロバイダーオプションをKEY=VALUEで入力します。削除はunset:KEYです。",
        "zh": "用 KEY=VALUE 输入提供商选项；用 unset:KEY 删除。",
    },
}


def provider_option_description(value: str) -> str:
    lang = current_language()
    if value in PROVIDER_OPTION_DESCRIPTIONS:
        entry = PROVIDER_OPTION_DESCRIPTIONS[value]
        return entry.get(lang, entry["en"])
    if value.startswith("context_window="):
        return PROVIDER_OPTION_DESCRIPTIONS["__edit_context_window__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__edit_context_window__"]["en"])
    if value.startswith("context_reserve_tokens="):
        return PROVIDER_OPTION_DESCRIPTIONS["__edit_reserve__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__edit_reserve__"]["en"])
    if value.startswith("max_output_tokens="):
        return PROVIDER_OPTION_DESCRIPTIONS["__edit_max_output__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__edit_max_output__"]["en"])
    if value.startswith(("timeout=", "request_timeout_ms=")):
        return PROVIDER_OPTION_DESCRIPTIONS["__edit_timeout__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__edit_timeout__"]["en"])
    if value.startswith(("native=", "native_compat=")):
        return PROVIDER_OPTION_DESCRIPTIONS["__edit_native__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__edit_native__"]["en"])
    return PROVIDER_OPTION_DESCRIPTIONS["__custom__"].get(lang, PROVIDER_OPTION_DESCRIPTIONS["__custom__"]["en"])


def build_provider_options_submenu() -> dict:
    provider, pcfg = current_provider_cfg()
    max_output = pcfg.get("max_output_tokens", "4096")
    timeout = pcfg.get("request_timeout_ms", "1800000")
    choices = [
        ("__edit_max_output__", f"Edit max_output_tokens [{max_output}]", False),
        ("__edit_timeout__", f"Edit timeout ms [{timeout}]", False),
    ]
    if provider in ("vllm", "self-hosted-nim"):
        native = bool(pcfg.get("native_compat", True))
        choices = [
            ("__edit_context_window__", f"Edit context_window [{pcfg.get('context_window', 'default')}]", False),
            ("__edit_reserve__", f"Edit context reserve [{pcfg.get('context_reserve_tokens', 'default')}]", False),
            *choices,
            ("__edit_native__", f"Edit native mode [{str(native).lower()}]", False),
        ]
    choices.extend([
        ("__custom__", "Custom KEY=VALUE or unset:KEY...", False),
        ("max_output_tokens=4096", f"max_output_tokens 4096 (current {max_output})", str(max_output) == "4096"),
        ("max_output_tokens=8192", f"max_output_tokens 8192 (current {max_output})", str(max_output) == "8192"),
        ("timeout=1800000", f"timeout 1800000ms (current {timeout})", str(timeout) == "1800000"),
    ])
    if provider in ("vllm", "self-hosted-nim"):
        choices.extend([
            ("context_window=32768", f"context_window 32768 (current {pcfg.get('context_window', 'default')})", pcfg.get("context_window") == 32768),
            ("context_window=65536", f"context_window 65536 (current {pcfg.get('context_window', 'default')})", pcfg.get("context_window") == 65536),
            ("native=true", "native true", bool(pcfg.get("native_compat", True))),
            ("native=false", "native false", not bool(pcfg.get("native_compat", True))),
        ])
    items = [
        {"value": value, "label": label, "current": current, "description": provider_option_description(value)}
        for value, label, current in choices
    ]
    return {"kind": "provider-options", "parent": "provider-options", "items": items, "idx": 0, "offset": 0}


def after_model_action() -> str:
    provider = current_provider()
    if is_ollama_provider(provider):
        return "ollama-options"
    if has_provider_options(provider):
        return "provider-options"
    return "test"


def summarize_test_output(code: int, out: str) -> list[str]:
    raw = out.strip().splitlines()
    if not raw:
        return ["Compatibility: FAIL" if code else "Compatibility: OK", "No output from compatibility test."]
    if any(line.startswith("Traceback ") for line in raw):
        reason = next((line.strip() for line in reversed(raw) if line.strip() and not line.lstrip().startswith("~")), "Internal test error")
        return ["Compatibility: FAIL", "Reason: internal claude-any test error", reason[:160]]
    keep_prefixes = (
        "Testing provider:",
        "Mode:",
        "URL:",
        "Claude API URL:",
        "Upstream base URL:",
        "Model:",
        "Compatibility:",
        "HTTP:",
        "Reason:",
        "Diagnosis:",
        "Stop reason:",
        "Content blocks:",
        "Tokens:",
    )
    lines = [line for line in raw if line.startswith(keep_prefixes)]
    if not lines:
        lines = raw[:8]
    if code != 0 and not any(line.startswith("Compatibility:") for line in lines):
        lines.insert(0, "Compatibility: FAIL")
    return lines[:10]


def test_submenu(lines: list[str]) -> dict:
    return {
        "kind": "test-result",
        "parent": "test",
        "items": [{"value": "", "label": line, "current": False} for line in lines],
        "idx": 0,
        "offset": 0,
        "readonly": True,
    }


def run_test_with_animation(stdscr, idx: int, checks: list[str]) -> tuple[int, str]:
    frames = ["|", "/", "-", "\\"]
    started = time.monotonic()
    proc = subprocess.Popen(
        [CTL, "test"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    frame = 0
    while proc.poll() is None:
        elapsed = int(time.monotonic() - started)
        notice = [f"{frames[frame % len(frames)]} {t('running_test')} ({elapsed}s)"]
        render(stdscr, idx, None, notice, checks)
        frame += 1
        time.sleep(0.2)
    out, _ = proc.communicate()
    return proc.returncode or 0, out or ""


def read_menu_key(stdscr) -> int:
    ch = stdscr.getch()
    if ch != 27:
        return ch

    stdscr.nodelay(True)
    try:
        time.sleep(0.1)
        seq = []
        for _ in range(3):
            nxt = stdscr.getch()
            if nxt == -1:
                break
            seq.append(nxt)
    finally:
        stdscr.nodelay(False)

    if len(seq) >= 2:
        if seq[:2] in ([ord("["), ord("A")], [ord("O"), ord("A")]):
            for extra in reversed(seq[2:]):
                curses.ungetch(extra)
            return curses.KEY_UP
        if seq[:2] in ([ord("["), ord("B")], [ord("O"), ord("B")]):
            for extra in reversed(seq[2:]):
                curses.ungetch(extra)
            return curses.KEY_DOWN
        if seq[:2] == [ord("["), ord("5")]:
            for extra in reversed(seq[3:]):
                curses.ungetch(extra)
            return curses.KEY_PPAGE
        if seq[:2] == [ord("["), ord("6")]:
            for extra in reversed(seq[3:]):
                curses.ungetch(extra)
            return curses.KEY_NPAGE
    return 27


def inline_prompt(stdscr, prompt_text: str, row: int, default: str = "") -> str:
    curses.echo()
    h, w = stdscr.getmaxyx()
    y = max(1, min(row, h - 3))
    stdscr.move(y, 0)
    stdscr.clrtoeol()
    stdscr.addstr(y, 0, " " * max(0, w - 1), curses.A_REVERSE)
    label = prompt_text
    stdscr.addstr(y, 2, label[: max(0, w - 4)], curses.A_REVERSE | curses.A_BOLD)
    x = min(len(label) + 2, max(0, w - 2))
    if default:
        stdscr.addstr(y, x, default[: max(0, w - x - 1)], curses.A_REVERSE)
        stdscr.move(y, min(x + len(default), max(0, w - 2)))
    else:
        stdscr.move(y, x)
    stdscr.refresh()
    try:
        value = stdscr.getstr(y, x, max(1, w - x - 1)).decode().strip()
    finally:
        curses.noecho()
    return value or default


def inline_secret_prompt(stdscr, prompt_text: str, row: int) -> str:
    curses.noecho()
    h, w = stdscr.getmaxyx()
    y = max(1, min(row, h - 3))
    stdscr.move(y, 0)
    stdscr.clrtoeol()
    stdscr.addstr(y, 0, " " * max(0, w - 1), curses.A_REVERSE)
    stdscr.addstr(y, 2, prompt_text[: max(0, w - 4)], curses.A_REVERSE | curses.A_BOLD)
    x = min(len(prompt_text) + 2, max(0, w - 2))
    stdscr.move(y, x)
    stdscr.refresh()
    chars = []
    while True:
        ch = read_menu_key(stdscr)
        if ch in (10, 13, curses.KEY_ENTER):
            break
        if ch in (27,):
            return ""
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if chars:
                chars.pop()
        elif 0 <= ch < 256 and chr(ch).isprintable():
            chars.append(chr(ch))
        stdscr.move(y, x)
        stdscr.clrtoeol()
        stdscr.addstr(y, 0, " " * max(0, w - 1), curses.A_REVERSE)
        stdscr.addstr(y, 2, prompt_text[: max(0, w - 4)], curses.A_REVERSE | curses.A_BOLD)
        masked = "*" * len(chars)
        stdscr.addstr(y, x, masked[: max(0, w - x - 1)], curses.A_REVERSE)
        stdscr.move(y, min(x + len(masked), max(0, w - 2)))
        stdscr.refresh()
    return "".join(chars).strip()

def message(stdscr, title: str, lines: list[str]) -> None:
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(0, 0, title[: w - 1], curses.A_BOLD)
    for i, line in enumerate(lines[: h - 4]):
        stdscr.addstr(2 + i, 0, line[: w - 1])
    stdscr.addstr(h - 2, 0, "Press any key to continue", curses.A_DIM | cp(5))
    stdscr.refresh()
    stdscr.getch()


def api_key_flow(stdscr) -> list[str]:
    provider = current_provider()
    curses.endwin()
    try:
        subprocess.run([CTL, "api-key", provider], check=False)
        input("Press Enter to return to claude-any menu...")
    finally:
        stdscr.refresh()
    return [f"API key flow completed for {provider}"]


def visible_sub_window(sub: dict, max_rows: int) -> tuple[int, int]:
    count = len(sub["items"])
    idx = sub["idx"]
    offset = sub.get("offset", 0)
    if idx < offset:
        offset = idx
    if idx >= offset + max_rows:
        offset = idx - max_rows + 1
    offset = max(0, min(offset, max(0, count - max_rows)))
    sub["offset"] = offset
    return offset, min(count, offset + max_rows)


def selected_sub_description(sub: dict | None) -> str:
    if not sub:
        return ""
    try:
        item = sub["items"][sub["idx"]]
    except Exception:
        return ""
    return str(item.get("description") or "")


def index_for_action(action: str) -> int:
    items = main_items()
    return next((i for i, (key, _) in enumerate(items) if key == action), 0)


def add(stdscr, y: int, x: int, text: str, attr: int = curses.A_NORMAL) -> None:
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    try:
        stdscr.addstr(y, max(0, x), text[: max(0, w - max(0, x) - 1)], attr)
    except curses.error:
        pass


def draw_intro_panel(stdscr) -> int:
    h, w = stdscr.getmaxyx()
    if h < 20:
        add(stdscr, 0, 0, f"{APP_NAME} - {CREDITS}", curses.A_BOLD)
        return 1

    panel_w = max(40, w - 2)
    panel_h = 8 if h >= 24 else 7
    border = cp(4)
    title = f" {APP_NAME} "
    add(stdscr, 0, 0, "+" + "-" * (panel_w - 2) + "+", border)
    add(stdscr, 0, 4, title, border | curses.A_BOLD)
    for y in range(1, panel_h - 1):
        add(stdscr, y, 0, "|", border)
        add(stdscr, y, panel_w - 1, "|", border)
    add(stdscr, panel_h - 1, 0, "+" + "-" * (panel_w - 2) + "+", border)

    if w >= 92:
        split = min(44, panel_w // 2)
        for y in range(1, panel_h - 1):
            add(stdscr, y, split, "|", border)
        add(stdscr, 1, 8, "Welcome back!", curses.A_BOLD | cp(5))
        add(stdscr, 3, 9, "CLAUDE", curses.A_BOLD | cp(2))
        add(stdscr, 4, 12, "ANY", curses.A_BOLD | cp(3))
        add(stdscr, 6, 6, CREDITS, curses.A_BOLD | cp(5))

        right = split + 3
        add(stdscr, 1, right, "Tips for getting started", curses.A_BOLD | cp(4))
        add(stdscr, 2, right, "Choose provider, model, base URL, and API key before launch.", cp(5))
        add(stdscr, 3, right, "Routes Claude Code to Anthropic, Ollama, vLLM, Nvidia, or NIM.", cp(5))
        add(stdscr, 4, right, "Adds DuckDuckGo web search tooling for non-native providers.", cp(5))
        add(stdscr, 5, right, "Use --ca-* flags for headless runs; Claude flags pass through.", cp(5))
    else:
        add(stdscr, 1, 3, f"{APP_NAME} routes Claude Code through selectable providers.", curses.A_BOLD | cp(5))
        add(stdscr, 2, 3, "Anthropic, Ollama, vLLM, Nvidia Hosted, and self-hosted NIM.", cp(5))
        add(stdscr, 3, 3, "DuckDuckGo web search is attached for non-native providers.", cp(5))
        add(stdscr, 4, 3, "Headless setup uses --ca-* flags; Claude flags pass through.", cp(5))
        if panel_h > 6:
            add(stdscr, 6, 3, CREDITS, curses.A_BOLD | cp(3))
        else:
            add(stdscr, 5, 3, CREDITS, curses.A_BOLD | cp(3))

    return panel_h + 1


def render(stdscr, idx: int, sub: dict | None, notice: list[str], checks: list[str]) -> dict[str, int]:
    lines = status_text()
    items = main_items()
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    top = draw_intro_panel(stdscr)
    status_count = 5 if h >= 28 else 4 if h >= 23 else 2
    for i, line in enumerate(lines[:status_count]):
        color = cp(2) if line.startswith("provider:") or line.startswith("model:") else cp(5)
        add(stdscr, top + i, 2, line, color)

    row = top + status_count + 1
    row_by_action: dict[str, int] = {}
    sub_selected_row = -1
    submenu_budget = max(3, min(10, h - row - len(items) - len(checks) - 4))
    if sub and sub.get("kind") == "test-result":
        submenu_budget = max(4, min(10, h - row - len(items) - len(checks) - 3))

    for i, (key, label) in enumerate(items):
        row_by_action[key] = row
        if row >= h - 3:
            break
        if i == idx and (sub is None or sub.get("readonly")):
            attr = curses.A_REVERSE | curses.A_BOLD
        elif key == "launch":
            attr = cp(2) | curses.A_BOLD
        elif key == "test":
            attr = cp(3) | curses.A_BOLD
        elif key == "quit":
            attr = cp(4)
        elif key in ("language", "provider", "model", "ollama-options", "provider-options", "api-key", "base-url"):
            attr = cp(3)
        else:
            attr = curses.A_NORMAL
        stdscr.addstr(row, 2, label[: max(0, w - 4)], attr)
        row += 1

        if sub and sub.get("parent") == key:
            start, end = visible_sub_window(sub, submenu_budget)
            if start > 0 and row < h - 3:
                stdscr.addstr(row, 6, f"... {start} above", curses.A_DIM | cp(5))
                row += 1
            for si in range(start, end):
                if row >= h - 3:
                    break
                item = sub["items"][si]
                if sub.get("kind") == "test-result":
                    text = f"  {item['label']}"
                    if "FAIL" in item["label"] or "TIMEOUT" in item["label"] or item["label"].startswith(("HTTP:", "Reason:", "Diagnosis:")):
                        attr = cp(4) | curses.A_BOLD
                    elif "OK" in item["label"]:
                        attr = cp(2) | curses.A_BOLD
                    else:
                        attr = curses.A_DIM | cp(5)
                else:
                    marker = "*" if item.get("current") else " "
                    prefix = ">" if si == sub["idx"] else " "
                    text = f"{prefix} {marker} {item['label']}"
                    if si == sub["idx"]:
                        attr = curses.A_REVERSE | curses.A_BOLD
                        sub_selected_row = row
                    elif item.get("current"):
                        attr = cp(2) | curses.A_BOLD
                    elif "[OK]" in item["label"]:
                        attr = cp(2)
                    elif "[FAIL" in item["label"] or "[TIMEOUT]" in item["label"]:
                        attr = cp(4) | curses.A_BOLD
                    else:
                        attr = curses.A_DIM
                if si == sub["idx"] and not sub.get("readonly"):
                    attr = curses.A_REVERSE | curses.A_BOLD
                    sub_selected_row = row
                stdscr.addstr(row, 4, text[: max(0, w - 6)], attr)
                row += 1
            remaining = len(sub["items"]) - end
            if remaining > 0 and row < h - 3:
                stdscr.addstr(row, 6, f"... {remaining} more", curses.A_DIM | cp(5))
                row += 1

    desc = selected_sub_description(sub)
    if desc and row < h - 5:
        stdscr.addstr(row, 2, ("-" * max(8, w - 4))[: max(0, w - 4)], curses.A_DIM | cp(6))
        row += 1
        for line in textwrap.wrap(desc, width=max(24, w - 6))[:2]:
            if row >= h - 4:
                break
            stdscr.addstr(row, 2, line[: max(0, w - 4)], curses.A_BOLD | cp(6))
            row += 1

    if row < h - 4:
        stdscr.addstr(row, 2, ("-" * max(8, w - 4))[: max(0, w - 4)], curses.A_DIM | cp(6))
        row += 1
        for line in checks[: max(0, h - row - 3)]:
            stdscr.addstr(row, 2, line[: max(0, w - 4)], curses.A_BOLD | cp(6))
            row += 1

    if notice:
        y = max(0, h - 5 - min(len(notice), 2))
        for j, line in enumerate(notice[:2]):
            stdscr.addstr(y + j, 0, line[: w - 1], cp(2) if j == 0 else curses.A_DIM)

    current_action = items[idx][0]
    stdscr.addstr(h - 2, 0, help_for_action(current_action, sub.get("kind") if sub else None)[: w - 1], curses.A_DIM | cp(5))
    stdscr.refresh()
    row_by_action["__sub_selected__"] = sub_selected_row
    return row_by_action


def main(stdscr) -> int:
    stdscr.keypad(True)
    curses.curs_set(0)
    init_colors()
    idx = index_for_action("launch") if settings_ready_except_api_key() else 0
    sub: dict | None = None
    notice: list[str] = []
    checks = preflight_checks()
    row_by_action: dict[str, int] = {}

    def apply_test_result(code: int, out: str) -> None:
        nonlocal sub, notice, checks, idx
        ok = code == 0
        sub = test_submenu(summarize_test_output(code, out))
        notice = [t("test_passed") if ok else t("test_failed")]
        checks = preflight_checks()
        idx = index_for_action("launch" if ok else "model")

    while True:
        items = main_items()
        idx = max(0, min(idx, len(items) - 1))
        row_by_action = render(stdscr, idx, sub, notice, checks)
        ch = read_menu_key(stdscr)

        if sub and sub.get("readonly"):
            if ch in (27, ord("q")):
                sub = None
                notice = []
                continue
            if ch in (curses.KEY_UP, ord("k")):
                notice = []
                idx = (idx - 1) % len(items)
                continue
            if ch in (curses.KEY_DOWN, ord("j")):
                notice = []
                idx = (idx + 1) % len(items)
                continue
            if ch in (10, 13, curses.KEY_ENTER):
                action = items[idx][0]
                if action == "launch":
                    return 0
                if action == "test":
                    code, out = run_test_with_animation(stdscr, idx, checks)
                    apply_test_result(code, out)
                    continue
                sub = None
            else:
                continue

        if sub:
            if ch in (27, ord("q")):
                sub = None
                notice = []
                checks = preflight_checks()
                continue
            if ch in (curses.KEY_UP, ord("k")):
                notice = []
                sub["idx"] = (sub["idx"] - 1) % len(sub["items"])
                provider_preview = selected_provider_value(sub)
                if provider_preview:
                    checks = provider_preview_checks(provider_preview)
                continue
            if ch in (curses.KEY_DOWN, ord("j")):
                notice = []
                sub["idx"] = (sub["idx"] + 1) % len(sub["items"])
                provider_preview = selected_provider_value(sub)
                if provider_preview:
                    checks = provider_preview_checks(provider_preview)
                continue
            if ch in (curses.KEY_NPAGE,):
                sub["idx"] = min(len(sub["items"]) - 1, sub["idx"] + 10)
                provider_preview = selected_provider_value(sub)
                if provider_preview:
                    checks = provider_preview_checks(provider_preview)
                continue
            if ch in (curses.KEY_PPAGE,):
                sub["idx"] = max(0, sub["idx"] - 10)
                provider_preview = selected_provider_value(sub)
                if provider_preview:
                    checks = provider_preview_checks(provider_preview)
                continue
            if ch in (10, 13, curses.KEY_ENTER):
                item = sub["items"][sub["idx"]]
                if sub["kind"] == "language":
                    _, out = run_cmd([CTL, "language", item["value"]])
                    notice = (out.strip().splitlines() or [item["value"]])[:2]
                    checks = preflight_checks()
                    sub = None
                    idx = index_for_action("provider")
                elif sub["kind"] == "provider":
                    _, out = run_cmd([CTL, "provider", item["value"]])
                    notice = (out.strip().splitlines() or [item["value"]])[:2]
                    checks = preflight_checks()
                    sub = None
                    idx = index_for_action("api-key")
                elif sub["kind"] == "api-key":
                    row = row_by_action.get("__sub_selected__", row_by_action.get("api-key", 10))
                    key = inline_secret_prompt(stdscr, f"API key for {item['value']}: ", row)
                    if key:
                        _, out = run_cmd([CTL, "set-api-key", item["value"], key])
                        notice = (out.strip().splitlines() or [item["value"]])[:2]
                        checks = preflight_checks()
                        idx = index_for_action("base-url")
                    else:
                        notice = [t("api_key_unchanged")]
                    sub = None
                elif sub["kind"] == "model":
                    if item["value"] == "__custom__":
                        row = row_by_action.get("__sub_selected__", row_by_action.get("model", 10))
                        value = inline_prompt(stdscr, "Model id or alias: ", row)
                        if value:
                            _, out = run_cmd([CTL, "model", value])
                            notice = (out.strip().splitlines() or [value])[:2]
                            checks = preflight_checks()
                            idx = index_for_action(after_model_action())
                        sub = None
                    else:
                        _, out = run_cmd([CTL, "model", item["value"]])
                        notice = (out.strip().splitlines() or [item["value"]])[:2]
                        checks = preflight_checks()
                        sub = None
                        idx = index_for_action(after_model_action())
                elif sub["kind"] == "ollama-options":
                    provider = current_provider()
                    row = row_by_action.get("__sub_selected__", row_by_action.get("ollama-options", 10))
                    provider_now, pcfg_now = current_provider_cfg()
                    opts_now = pcfg_now.get("ollama_options") or {}
                    if not isinstance(opts_now, dict):
                        opts_now = {}
                    action_value = item["value"]
                    value = ""
                    if action_value == "__edit_num_ctx__":
                        default = str(pcfg_now.get("num_ctx", "auto"))
                        entered = inline_prompt(stdscr, "num_ctx (auto or integer): ", row, default)
                        value = f"num_ctx={entered}" if entered else ""
                    elif action_value == "__edit_min__":
                        default = str(pcfg_now.get("num_ctx_min", 32768))
                        entered = inline_prompt(stdscr, "num_ctx auto minimum: ", row, default)
                        value = f"min={entered}" if entered else ""
                    elif action_value == "__edit_max__":
                        default = str(pcfg_now.get("num_ctx_max", 131072))
                        entered = inline_prompt(stdscr, "num_ctx auto maximum: ", row, default)
                        value = f"max={entered}" if entered else ""
                    elif action_value == "__edit_keep_alive__":
                        default = str(pcfg_now.get("keep_alive", "5m"))
                        entered = inline_prompt(stdscr, "keep_alive: ", row, default)
                        value = f"keep_alive={entered}" if entered else ""
                    elif action_value == "__edit_temperature__":
                        default = str(opts_now.get("temperature", "0.7"))
                        entered = inline_prompt(stdscr, "temperature (unset:temperature clears): ", row, default)
                        value = entered if entered.startswith("unset:") else (f"temperature={entered}" if entered else "")
                    elif action_value == "__edit_top_p__":
                        default = str(opts_now.get("top_p", "0.8"))
                        entered = inline_prompt(stdscr, "top_p (unset:top_p clears): ", row, default)
                        value = entered if entered.startswith("unset:") else (f"top_p={entered}" if entered else "")
                    elif action_value == "__edit_max_tokens__":
                        default = str(opts_now.get("num_predict", "4096"))
                        entered = inline_prompt(stdscr, "max_tokens / num_predict: ", row, default)
                        value = f"max_tokens={entered}" if entered else ""
                    elif action_value == "__edit_timeout__":
                        default = str(pcfg_now.get("request_timeout_ms", "1800000"))
                        entered = inline_prompt(stdscr, "timeout ms: ", row, default)
                        value = f"timeout={entered}" if entered else ""
                    elif action_value == "__custom__":
                        value = inline_prompt(stdscr, "Ollama option KEY=VALUE: ", row, "temperature=0.7")
                    else:
                        value = action_value
                    if value:
                        _, out = run_cmd([CTL, "ollama-options", provider, value])
                        notice = (out.strip().splitlines() or [value])[:2]
                        checks = preflight_checks()
                        idx = index_for_action("test")
                    sub = None
                elif sub["kind"] == "provider-options":
                    provider = current_provider()
                    row = row_by_action.get("__sub_selected__", row_by_action.get("provider-options", 10))
                    provider_now, pcfg_now = current_provider_cfg()
                    action_value = item["value"]
                    value = ""
                    if action_value == "__edit_context_window__":
                        default = str(pcfg_now.get("context_window", "32768"))
                        entered = inline_prompt(stdscr, "context_window: ", row, default)
                        value = f"context_window={entered}" if entered else ""
                    elif action_value == "__edit_reserve__":
                        default = str(pcfg_now.get("context_reserve_tokens", "1024"))
                        entered = inline_prompt(stdscr, "context_reserve_tokens: ", row, default)
                        value = f"context_reserve_tokens={entered}" if entered else ""
                    elif action_value == "__edit_max_output__":
                        default = str(pcfg_now.get("max_output_tokens", "4096"))
                        entered = inline_prompt(stdscr, "max_output_tokens: ", row, default)
                        value = f"max_output_tokens={entered}" if entered else ""
                    elif action_value == "__edit_timeout__":
                        default = str(pcfg_now.get("request_timeout_ms", "1800000"))
                        entered = inline_prompt(stdscr, "timeout ms: ", row, default)
                        value = f"timeout={entered}" if entered else ""
                    elif action_value == "__edit_native__":
                        default = "true" if pcfg_now.get("native_compat", True) else "false"
                        entered = inline_prompt(stdscr, "native true/false: ", row, default)
                        value = f"native={entered}" if entered else ""
                    elif action_value == "__custom__":
                        value = inline_prompt(stdscr, "Provider option KEY=VALUE: ", row, "max_output_tokens=4096")
                    else:
                        value = action_value
                    if value:
                        _, out = run_cmd([CTL, "provider-options", provider, value])
                        notice = (out.strip().splitlines() or [value])[:2]
                        checks = preflight_checks()
                        idx = index_for_action("test")
                    sub = None
                continue
            continue

        if ch in (ord("q"), 27):
            return 10
        if ch in (curses.KEY_UP, ord("k")):
            notice = []
            idx = (idx - 1) % len(items)
            continue
        if ch in (curses.KEY_DOWN, ord("j")):
            notice = []
            idx = (idx + 1) % len(items)
            continue
        if ch not in (10, 13, curses.KEY_ENTER):
            continue

        action = items[idx][0]
        if action == "launch":
            return 0
        if action == "test":
            code, out = run_test_with_animation(stdscr, idx, checks)
            apply_test_result(code, out)
            continue
        if action == "quit":
            return 10
        if action == "language":
            sub = build_language_submenu()
            notice = []
        elif action == "provider":
            sub = build_provider_submenu()
            notice = []
            provider_preview = selected_provider_value(sub)
            if provider_preview:
                checks = provider_preview_checks(provider_preview)
        elif action == "model":
            notice = [t("loading_models")]
            render(stdscr, idx, None, notice, checks)
            sub, fallback_notice = build_model_submenu()
            notice = fallback_notice
            if sub is None:
                row = row_by_action.get("model", 10)
                value = inline_prompt(stdscr, "Model id or alias: ", row)
                if value:
                    _, out = run_cmd([CTL, "model", value])
                    notice = (out.strip().splitlines() or [value])[:2]
                    checks = preflight_checks()
                    idx = index_for_action(after_model_action())
        elif action == "ollama-options":
            provider = current_provider()
            if is_ollama_provider(provider):
                sub = build_ollama_options_submenu()
                notice = []
            else:
                notice = ["Ollama options are available only for ollama and ollama-cloud."]
        elif action == "provider-options":
            provider = current_provider()
            if has_provider_options(provider):
                sub = build_provider_options_submenu()
                notice = []
            else:
                notice = ["Provider options are available for vLLM, NVIDIA hosted, and self-hosted NIM."]
        elif action == "api-key":
            provider = current_provider()
            row = row_by_action.get("api-key", 10)
            key = inline_secret_prompt(stdscr, f"API key for {provider}: ", row)
            if key:
                _, out = run_cmd([CTL, "set-api-key", provider, key])
                notice = (out.strip().splitlines() or [provider])[:2]
                checks = preflight_checks()
            else:
                notice = [t("api_key_unchanged")]
            idx = index_for_action("base-url")
        elif action == "base-url":
            provider = current_provider()
            row = row_by_action.get("base-url", 12)
            value = inline_prompt(stdscr, f"Base URL for {provider}: ", row, default_base_url(provider))
            if value:
                _, out = run_cmd([CTL, "base-url", provider, value])
                notice = (out.strip().splitlines() or [value])[:2]
                checks = preflight_checks()
            idx = index_for_action("model")


if __name__ == "__main__":
    raise SystemExit(curses.wrapper(main))
