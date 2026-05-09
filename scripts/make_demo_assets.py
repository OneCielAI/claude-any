#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
WIDTH = 1500
HEIGHT = 920


COLORS = {
    "bg": (0, 0, 0),
    "fg": (220, 220, 220),
    "muted": (150, 150, 150),
    "red": (212, 76, 76),
    "green": (30, 220, 70),
    "yellow": (225, 220, 0),
    "orange": (255, 145, 40),
    "white": (245, 245, 245),
    "select_bg": (235, 235, 235),
    "select_fg": (20, 20, 20),
}


LANG = {
    "en": {
        "name": "English",
        "welcome": "Welcome back!",
        "tips_title": "Tips for getting started",
        "status": ["provider: ollama-cloud", "language: en", "mode: claude-any-router", "base_url: https://ollama.com", "model: qwen3-coder:480b:cloud"],
        "tips": [
            "Choose provider, model, base URL, and API key before launch.",
            "Routes Claude Code to Anthropic, Ollama, vLLM, Nvidia, or NIM.",
            "Headless runs use --ca-* flags; Claude flags pass through.",
        ],
        "menu": [
            "0. Language  [English]",
            "1. Provider  [ollama-cloud]",
            "2. API key",
            "3. Base URL  [https://ollama.com]",
            "4. Model  [qwen3-coder:480b:cloud]",
            "5. Options  [max 4096; timeout 1800000ms]",
            "6. Compatibility test",
            "7. Launch Claude Code",
            "Quit",
        ],
        "provider": ["Provider menu", "Anthropic", "Ollama", "Ollama Cloud [selected]", "vLLM"],
        "base": ["Base URL", "https://ollama.com", "Local Ollama uses http://host:11434"],
        "model": ["Model picker", "glm-5.1:cloud", "qwen3-coder:480b:cloud [selected]", "Custom model..."],
        "test": ["Compatibility: PASS", "HTTP: 200", "Text: OK", "Tokens: in=71, out=2"],
        "footers": [
            "Ollama Cloud calls https://ollama.com/api directly and requires an API key.",
            "Enter edits the current row. Esc closes inline input.",
            "Models are sorted alphabetically when the endpoint can list them.",
            "Successful tests advance focus to Launch Claude Code.",
        ],
    },
    "ko": {
        "name": "한국어",
        "welcome": "환영합니다!",
        "tips_title": "시작 도움말",
        "status": ["provider: ollama-cloud", "language: ko", "mode: claude-any-router", "base_url: https://ollama.com", "model: qwen3-coder:480b:cloud"],
        "tips": [
            "실행 전에 프로바이더, 모델, Base URL, API 키를 선택합니다.",
            "Claude Code를 Anthropic, Ollama, vLLM, Nvidia, NIM으로 라우팅합니다.",
            "자동 실행은 --ca-* 플래그를 쓰고 Claude 플래그는 그대로 전달됩니다.",
        ],
        "menu": [
            "0. 언어  [한국어]",
            "1. 프로바이더  [ollama-cloud]",
            "2. API 키",
            "3. Base URL  [https://ollama.com]",
            "4. 모델  [qwen3-coder:480b:cloud]",
            "5. 옵션  [max 4096; timeout 1800000ms]",
            "6. 호환성 테스트",
            "7. Claude Code 실행",
            "종료",
        ],
        "provider": ["프로바이더 메뉴", "Anthropic", "Ollama", "Ollama Cloud [선택됨]", "vLLM"],
        "base": ["Base URL", "https://ollama.com", "로컬 Ollama는 http://host:11434 를 사용합니다"],
        "model": ["모델 선택", "glm-5.1:cloud", "qwen3-coder:480b:cloud [선택됨]", "사용자 모델 입력..."],
        "test": ["호환성: 통과", "HTTP: 200", "응답: OK", "토큰: in=71, out=2"],
        "footers": [
            "Ollama Cloud는 https://ollama.com/api 를 직접 호출하며 API 키가 필요합니다.",
            "Enter는 현재 줄을 편집합니다. Esc는 입력을 닫습니다.",
            "엔드포인트가 목록을 제공하면 모델은 알파벳순으로 정렬됩니다.",
            "테스트가 성공하면 포커스가 Claude Code 실행으로 이동합니다.",
        ],
    },
    "ja": {
        "name": "日本語",
        "welcome": "おかえり!",
        "tips_title": "はじめるためのヒント",
        "status": ["provider: ollama-cloud", "language: ja", "mode: claude-any-router", "base_url: https://ollama.com", "model: qwen3-coder:480b:cloud"],
        "tips": [
            "起動前にプロバイダー、モデル、Base URL、APIキーを選択します。",
            "Claude CodeをAnthropic、Ollama、vLLM、Nvidia、NIMへ接続します。",
            "自動実行では--ca-*を使い、Claudeの引数はそのまま渡します。",
        ],
        "menu": [
            "0. 言語  [日本語]",
            "1. プロバイダー  [ollama-cloud]",
            "2. APIキー",
            "3. Base URL  [https://ollama.com]",
            "4. モデル  [qwen3-coder:480b:cloud]",
            "5. オプション  [max 4096; timeout 1800000ms]",
            "6. 互換性テスト",
            "7. Claude Code 起動",
            "終了",
        ],
        "provider": ["プロバイダーメニュー", "Anthropic", "Ollama", "Ollama Cloud [選択中]", "vLLM"],
        "base": ["Base URL", "https://ollama.com", "ローカルOllamaは http://host:11434 を使います"],
        "model": ["モデル選択", "glm-5.1:cloud", "qwen3-coder:480b:cloud [選択中]", "カスタムモデル..."],
        "test": ["互換性: 成功", "HTTP: 200", "応答: OK", "トークン: in=71, out=2"],
        "footers": [
            "Ollama Cloudは https://ollama.com/api を直接呼び出し、APIキーが必要です。",
            "Enterで現在の行を編集します。Escで入力を閉じます。",
            "エンドポイントが一覧を返す場合、モデルはアルファベット順に並びます。",
            "テスト成功後、フォーカスはClaude Code起動へ移動します。",
        ],
    },
    "zh": {
        "name": "中文",
        "welcome": "欢迎回来!",
        "tips_title": "入门提示",
        "status": ["provider: ollama-cloud", "language: zh", "mode: claude-any-router", "base_url: https://ollama.com", "model: qwen3-coder:480b:cloud"],
        "tips": [
            "启动前选择供应商、模型、Base URL 和 API 密钥。",
            "将 Claude Code 路由到 Anthropic、Ollama、vLLM、Nvidia 或 NIM。",
            "自动运行使用 --ca-* 参数；Claude 参数会原样传递。",
        ],
        "menu": [
            "0. 语言  [中文]",
            "1. 供应商  [ollama-cloud]",
            "2. API 密钥",
            "3. Base URL  [https://ollama.com]",
            "4. 模型  [qwen3-coder:480b:cloud]",
            "5. 选项  [max 4096; timeout 1800000ms]",
            "6. 兼容性测试",
            "7. 启动 Claude Code",
            "退出",
        ],
        "provider": ["供应商菜单", "Anthropic", "Ollama", "Ollama Cloud [已选择]", "vLLM"],
        "base": ["Base URL", "https://ollama.com", "本地 Ollama 使用 http://host:11434"],
        "model": ["模型选择", "glm-5.1:cloud", "qwen3-coder:480b:cloud [已选择]", "自定义模型..."],
        "test": ["兼容性: 通过", "HTTP: 200", "响应: OK", "Token: in=71, out=2"],
        "footers": [
            "Ollama Cloud 直接调用 https://ollama.com/api，需要 API 密钥。",
            "Enter 编辑当前行。Esc 关闭输入。",
            "如果端点能列出模型，模型会按字母顺序排序。",
            "测试成功后，焦点会移动到启动 Claude Code。",
        ],
    },
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT = font(28)
FONT_BOLD = font(28, bold=True)
FONT_BIG = font(34, bold=True)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: str = "fg", big: bool = False) -> None:
    draw.text(xy, text, font=FONT_BIG if big else FONT, fill=COLORS[color])


def draw_header(draw: ImageDraw.ImageDraw, data: dict) -> None:
    draw.rectangle((10, 10, WIDTH - 10, 235), outline=COLORS["red"], width=2)
    draw_text(draw, (110, 38), "--- Claude Any ---", "red", big=True)
    draw_text(draw, (135, 92), data["welcome"], "white", big=True)
    draw_text(draw, (165, 145), "CLAUDE", "green", big=True)
    draw_text(draw, (185, 185), "ANY", "yellow", big=True)
    draw.line((520, 40, 520, 205), fill=COLORS["red"], width=2)
    draw_text(draw, (560, 48), data["tips_title"], "red", big=True)
    for i, line in enumerate(data["tips"]):
        draw_text(draw, (560, 92 + i * 40), line, "fg")


def draw_status(draw: ImageDraw.ImageDraw, data: dict) -> None:
    y = 270
    for i, line in enumerate(data["status"]):
        color = "green" if i in (0, 4) else "fg"
        draw_text(draw, (40, y + i * 42), line, color)


def draw_menu(draw: ImageDraw.ImageDraw, data: dict, selected: int, extra: list[tuple[str, str]]) -> None:
    y = 495
    for i, item in enumerate(data["menu"]):
        row_y = y + i * 34
        if i == selected:
            draw.rectangle((35, row_y - 2, 760, row_y + 34), fill=COLORS["select_bg"])
            draw.text((48, row_y), item, font=FONT_BOLD, fill=COLORS["select_fg"])
        else:
            color = "green" if i == 7 else "yellow"
            draw_text(draw, (48, row_y), item, color)
    x = 815
    y2 = 492
    for label, color in extra:
        draw_text(draw, (x, y2), label, color)
        y2 += 42


def draw_footer(draw: ImageDraw.ImageDraw, line: str) -> None:
    draw.line((30, HEIGHT - 105, WIDTH - 30, HEIGHT - 105), fill=COLORS["orange"], width=2)
    draw_text(draw, (40, HEIGHT - 92), line, "orange")


def frame(data: dict, selected: int, extra_key: str, footer_idx: int) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    draw_header(draw, data)
    draw_status(draw, data)
    items = data[extra_key]
    extra = [(items[0], "red"), *[(item, "green" if "[" in item else "fg") for item in items[1:]]]
    draw_menu(draw, data, selected, extra)
    draw_footer(draw, data["footers"][footer_idx])
    return img


def save_mp4(frames: list[Image.Image], path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for i, img in enumerate(frames):
            img.save(tmp / f"frame-{i:02d}.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                "0.8",
                "-i",
                str(tmp / "frame-%02d.png"),
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def save_language_assets(code: str, data: dict) -> None:
    frames = [
        frame(data, 1, "provider", 0),
        frame(data, 3, "base", 1),
        frame(data, 4, "model", 2),
        frame(data, 6, "test", 3),
    ]
    suffix = f".{code}"
    names = [
        f"claude-any-provider{suffix}.png",
        f"claude-any-base-url{suffix}.png",
        f"claude-any-model{suffix}.png",
        f"claude-any-test{suffix}.png",
    ]
    for img, name in zip(frames, names, strict=True):
        img.save(ASSET_DIR / name)
    frames[0].save(ASSET_DIR / f"claude-any-main{suffix}.png")
    frames[0].save(
        ASSET_DIR / f"claude-any-demo{suffix}.gif",
        save_all=True,
        append_images=frames[1:],
        duration=1250,
        loop=0,
        optimize=True,
    )
    save_mp4(frames, ASSET_DIR / f"claude-any-demo{suffix}.mp4")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for code, data in LANG.items():
        save_language_assets(code, data)
    # Backward-compatible English defaults.
    for stem in ("main", "provider", "base-url", "model", "test"):
        shutil.copyfile(ASSET_DIR / f"claude-any-{stem}.en.png", ASSET_DIR / f"claude-any-{stem}.png")
    shutil.copyfile(ASSET_DIR / "claude-any-demo.en.gif", ASSET_DIR / "claude-any-demo.gif")
    if (ASSET_DIR / "claude-any-demo.en.mp4").exists():
        shutil.copyfile(ASSET_DIR / "claude-any-demo.en.mp4", ASSET_DIR / "claude-any-demo.mp4")
    print(f"Wrote localized demo assets to {ASSET_DIR}")


if __name__ == "__main__":
    main()
