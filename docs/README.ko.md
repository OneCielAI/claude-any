# Claude Any

| [English](../README.md) | 한국어 | [日本語](README.ja.md) | [中文](README.zh.md) |
| --- | --- | --- | --- |

[![npm version](https://img.shields.io/npm/v/@oneciel-ai/claude-any?logo=npm&label=npm)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![npm downloads](https://img.shields.io/npm/dm/@oneciel-ai/claude-any?logo=npm&label=downloads)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

> ## 🚀 Claude Code의 모든 기능을 무료/저비용 LLM 으로
>
> - **무료** — [NVIDIA hosted NIM](https://build.nvidia.com/) (qwen3-coder-480b, gpt-oss 등) 을 API Catalog 로 사용.
> - **저비용** — [Ollama Cloud](https://ollama.com/cloud) 로 GLM, Qwen, DeepSeek 같은 오픈 가중치 모델을 frontier 모델 대비 매우 낮은 가격에 사용.
> - **무료 + 로컬** — [Ollama](https://ollama.com/) 또는 [vLLM](https://github.com/vllm-project/vllm) 을 본인 GPU 에서 완전 오프라인으로 사용.
>
> 프로바이더, 모델, Base URL, API 키, 스트리밍 동작, LLM 옵션을 Claude Code 실행 **전에** 콘솔 메뉴에서 모두 선택합니다. Claude Code 본체는 그대로 — 모든 native 툴링, slash command, 워크플로우가 유지됩니다.

### 데모

![NVIDIA hosted NIM 로 Claude Code 구동 (deepseek-4-flash)](assets/claude-any-nvidia-nim.gif)

NVIDIA hosted NIM (deepseek-4-flash) 이 claude-any 라우터를 통해 Claude Code 를 구동. &nbsp;[전체 mp4 ⤓](https://github.com/OneCielAI/claude-any/raw/main/demo/claude-any-nvidia-nim.mp4)

![Ollama Cloud 를 claude-any 라우터로 (glm-5.1)](assets/claude-any-ollama-cloud.gif)

Ollama Cloud (glm-5.1) 를 SSE 단어경계 청킹 활성화 상태에서 claude-any 라우터로 스트리밍. &nbsp;[전체 mp4 ⤓](https://github.com/OneCielAI/claude-any/raw/main/demo/claude-any-ollama-cloud.mp4)

---

Claude Any는 Claude Code 실행 전에 Anthropic, Ollama, Ollama Cloud, vLLM,
NVIDIA hosted, self-hosted NIM을 선택하고, Claude Code의 일반 인자는 그대로
전달하는 프로바이더 선택 런처입니다.

Credits: One Ciel LLC

현재 버전: `0.1.27`

## 왜 만들었나

Claude Code의 가장 높은 플랜을 사용해도 긴 작업 중에는 토큰이 부족해지거나,
다음 토큰이 열릴 때까지 세션을 이어가기 어려운 순간이 생깁니다. Claude Any는
Claude Code를 대체하려는 도구가 아니라, 작업 흐름을 멈추지 않기 위한 보조
도구입니다. NVIDIA NIM, Ollama Cloud, vLLM, 로컬 Ollama처럼 충분히 쓸만한
프로바이더를 요약, 조사, 저널, 간단한 코딩, 백그라운드 위임 작업에 사용할 수
있습니다.

가능한 경우 Anthropic 호환 Messages 엔드포인트를 우선 사용해 Claude Code의
툴링, 권한, 모델 선택, 작업 흐름의 장점을 최대한 유지합니다. 원격 프로바이더가
직접 제공하기 어려운 웹검색은 별도의 MCP 도구로 보강합니다.

실행 전 메뉴는 콘솔과 SSH 작업을 우선 고려했습니다. Claude Code가 시작되기
전에 프로바이더, 모델, Base URL, API 키, 옵션을 쉽게 확인하고 바꿀 수 있습니다.

macOS에서는 아직 충분히 테스트하지 않았지만, portable Python과 shell wrapper
중심으로 작성했습니다. 문제가 있으면 알려주세요.

- D. Yun

## 설치

[![npm version](https://img.shields.io/npm/v/@oneciel-ai/claude-any.svg)](https://www.npmjs.com/package/@oneciel-ai/claude-any)
[![npm downloads](https://img.shields.io/npm/dm/@oneciel-ai/claude-any.svg)](https://www.npmjs.com/package/@oneciel-ai/claude-any)

요구사항:

- Python 3.10+
- `claude` 명령으로 실행 가능한 Claude Code
- Node/npm (설치 shim 과 선택적인 MCP 웹 도구용)

**npm registry 에서 설치 (권장):**

```sh
npm install -g @oneciel-ai/claude-any
claude-any
```

**업그레이드:**

```sh
npm update -g @oneciel-ai/claude-any
claude-any version
```

**제거:**

```sh
npm uninstall -g @oneciel-ai/claude-any
```

### 다른 설치 경로

GitHub 저장소에서 직접 설치 (publish 사이의 미릴리스 커밋을 시험할 때 유용):

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

POSIX 소스 설치:

```sh
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
./install.sh
claude-any
```

Windows PowerShell 소스 설치:

```powershell
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
.\install.ps1
claude-any
```

### 릴리즈 (메인테이너용)

새 GitHub Release 가 publish 되면
[`Publish to npm`](../.github/workflows/npm-publish.yml) 워크플로가
자동으로 npm 에 배포합니다. 워크플로는 `@oneciel-ai/claude-any` 에 대한
*Bypass 2FA for publishing* 권한이 있는 granular token 을 저장소 secret
`NPM_TOKEN` 으로 받습니다.

릴리즈 절차:

1. `package.json` 의 `version` 과 `claude_any.py` 의 `VERSION` 을 올림.
2. Changelog 항목 추가.
3. `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
4. `gh release create vX.Y.Z --title "..." --notes "..."` — publish 워크플로 트리거.


![Claude Any 메뉴](assets/claude-any-main.ko.png)

## 데모

![Claude Any 데모](assets/claude-any-demo.ko.gif)

현재 데모는 프로바이더 선택, Base URL, 모델 선택, LLM 옵션, 호환성 테스트
순서로 구성되어 있습니다. 호환성 테스트는 단순 텍스트 응답뿐 아니라 필수
`tool_use`와 `tool_result` 후속 응답까지 확인합니다.

| 프로바이더 | Base URL | 모델 | LLM 옵션 | 호환성 |
| --- | --- | --- | --- | --- |
| ![프로바이더](assets/claude-any-provider.ko.png) | ![Base URL](assets/claude-any-base-url.ko.png) | ![모델](assets/claude-any-model.ko.png) | ![옵션](assets/claude-any-options.ko.png) | ![테스트](assets/claude-any-test.ko.png) |

자세한 설정법, headless 플래그, 문제 해결은 [manual](manual.md)을 참고하세요.
데모 영상은 [assets/claude-any-demo.ko.mp4](assets/claude-any-demo.ko.mp4)에 있습니다.

## 개발 스토리

Claude Any는 실제적인 통합 테스트의 연속으로 만들어졌습니다. 먼저 프로바이더
전환을 시도했고, 이어서 모델 목록 조회, API 키 입력, 호환성 테스트, 웹검색
툴링, 타임아웃 처리, Claude Code 기본 동작 보존을 차례로 확인했습니다. 가장
유용한 결론은 프로바이더가 Anthropic 호환 Messages 엔드포인트를 제공할 때 그
경로가 가장 깔끔한 통합 방식이라는 점이었습니다. Ollama, vLLM, NIM은 모두
Anthropic 호환 경로를 제공할 수 있고, 이 경로는 일반 OpenAI 호환 chat 경로보다
Claude Code의 툴링 모델을 더 잘 보존할 수 있습니다.

로컬 Ollama와 vLLM에서는 RTX 5090 및 MSI GB10급 장비에서 Qwen 3.6 27B Q4도
테스트했습니다. 동작은 했지만 Claude native나 Codex와 직접 비교할 속도 범주는
아니었습니다. 하이브리드 백그라운드 작업에는 오히려 NVIDIA NIM과 Ollama Cloud
쪽에서 체감 성능이 괜찮았던 모델들이 있었습니다.

OpenAI 호환 엔드포인트는 Claude Code 사용을 위한 기본 경로에서 의도적으로
제외했습니다. 테스트 중 generic OpenAI chat 호환 계층을 통한 tool-call 변환은
tool parameter, tool result, 반복 호출, retry, 모델 선택 주변에서 더 불안정한
동작을 보였습니다. 그래서 Claude Any는 native Anthropic 호환 endpoint를 우선
사용하고, provider-specific 변환이 필요한 경우에만 작은 router를 사용합니다.

최근 vLLM 테스트에서 확인한 중요한 점은 서버의 tool-call parser가 모델 계열과
정확히 맞아야 한다는 것입니다. vLLM 서버가 접속 가능하고 `/v1/messages`가
동작해도 `--tool-call-parser`가 틀리면 Claude Code가 tool call을 파싱하지 못하고
멈출 수 있습니다. Qwen3-Coder 계열은 `--enable-auto-tool-choice
--tool-call-parser qwen3_xml` 조합을 우선 사용해야 하며, `hermes`는 Hermes 형식
모델이나 일부 오래된 Qwen tool template에 맞는 선택입니다.

## 추천 사용처

속도가 핵심이 아닌 백그라운드 운영 작업에 적합합니다. Docker 호스트 관리,
Windows/Linux 서버 관리, 정리 스크립트, 주기적인 보안 점검, 로그 리뷰,
Windows 이벤트 로그 리뷰, 바이러스/랜섬웨어 침입 시도 정리, 무차별 로그인
시도 리뷰, 리포트 초안 생성 등에 추천합니다.

전문 보안 도구를 대체하지는 않지만, 반복 점검을 스크립트와 보고서로 정리하는
서버 관리자 보조 역할에 유용합니다. 이런 방식으로 무료 또는 저비용의 시스템
보안 지키미를 만들 수 있습니다.

예를 들어 "Docker 컨테이너에 PostgreSQL 설치해줘", "오늘 Docker 로그를 분석해서
이메일 리포트로 보내줘" 같은 요청을 명령어, 스크립트, 스케줄 작업, 요약 보고서로
구체화할 수 있습니다.

작은 모델이 탐지와 요약을 맡고, 큰 모델이 리뷰와 정책, 계획을 담당한 뒤,
다시 작은 모델이 큰 모델의 감독 아래 반복 작업을 수행하는 계층형 운영에도
잘 맞습니다.

## 주요 기능

- 영어, 한국어, 일본어, 중국어 UI를 가진 실행 전 프로바이더 선택 메뉴.
- 프로바이더별 모델 목록과 사용자 모델 직접 입력.
- Claude Code 채팅 입력 밖에서 API 키 설정.
- context window, output tokens, timeout, sampling, native compatibility를 위한 LLM 옵션/프리셋.
- 실행 전 텍스트, `tool_use`, `tool_result` 호환성 테스트.
- vLLM/NIM의 `/v1/models`가 `max_model_len`을 제공하면 런타임 컨텍스트 표시.
- SSH와 터미널 작업에 맞춘 콘솔 우선 메뉴.
- Anthropic 호환 엔드포인트가 있는 경우 native 경로 우선.
- 필요한 경우 provider-specific router 사용.
- non-native provider용 DuckDuckGo/fetch MCP 연결.
- `--ca-provider`, `--ca-model`, `--ca-base-url`, `--ca-api-key-env` 등 headless 플래그.
- Ollama/Ollama Cloud 라우터 경로의 스트리밍 프록시 — 전체 응답을 기다리지 않고
  토큰이 도착하는 즉시 Claude Code로 전달합니다.
- 프로바이더별 `stream` on/off 토글과 `stream_word_chunking` 옵션으로 텍스트
  delta 를 단어 경계 단위로 묶어서 전송 — 긴 스트리밍 응답에서 tool-call /
  JSON 파싱을 깨뜨릴 수 있는 SSE 단편화 문제를 완화합니다.
- LLM options 메뉴에서 강조된 행의 의미를 현재 언어(영어/한국어/일본어/중국어)로
  하단에 표시하고, boolean 행(`Stream`, `Stream word chunking`,
  `Native compatibility`, `Think`) 은 Enter 키 한 번에 즉시 토글됩니다.
- Tool guard hook 등록을 Claude Code 의 전체 hook event 로 확장
  (`WorktreeCreate` / `WorktreeRemove` 포함) — git 저장소가 아닌 작업 디렉터리에서
  Agent isolation 이 `Cannot create agent worktree: not in a git repository...`
  에러로 실패하던 문제 해결.
- 설정 파일 캐싱 — 라우터의 요청마다 디스크에서 읽던 설정을 메모리에 캐시하여
  파일 수정 시에만 다시 읽습니다.

## 변경 이력

### 0.1.27

- **non-Anthropic provider의 Plan mode 지원**: 라우터가 `EnterPlanMode`를 유지하고, 업스트림 모델이 Claude Code 내부 Plan tool을 안정적으로 선택하지 못해도 Claude Code Plan mode로 전환할 수 있게 처리합니다. `tool_choice=EnterPlanMode`가 강제된 요청은 라우터가 로컬에서 유효한 Anthropic `tool_use`로 응답하고, 긴 구현 요청에 대해 짧거나 빈 비실행 텍스트만 돌아오면 언어에 의존하지 않는 구조 검사로 `EnterPlanMode`로 승격합니다.
- **Plan-mode self-tool 처리**: 지원하지 않는 Claude Code self-tool은 non-Anthropic provider에서 계속 제거하지만, Plan-mode tool은 별도 처리하여 planning 기능을 비활성화하지 않습니다.

### 0.1.25

- **Plan mode 진단**: `~/.config/claude-any/log-level`에 `TRACE`를 쓰면 `requests.jsonl` / `responses.jsonl`에 요청/응답 요약이 남습니다.
- **헤드리스 에이전트 채팅**: 라우터가 `/ca/chat/messages`, `/ca/chat/wait`, `/ca/chat/stream`을 제공합니다. 서브 코딩 에이전트는 마지막 message id 이후의 업데이트를 받거나 SSE로 답변을 기다릴 수 있습니다.
- **Plan artifact 서빙**: `/ca/plan/artifacts`로 plan 파일을 만들고 로컬 URL로 공유할 수 있습니다. Anthropic 내부 구현을 복제하지 않고 파일/아티팩트 중심 흐름만 독립 구현했습니다.

### 0.1.24

- **첫 npm registry 공개 배포**: 올바른 스코프 `@oneciel-ai/claude-any` 로 게시. 이전 0.1.x 는 registry 에 올라가지 않은 상태였고, 이 버전부터 `npm install -g @oneciel-ai/claude-any` 로 직접 설치 가능합니다.

### 0.1.23

- **스트림 토글**: 각 non-Anthropic provider 에 `stream_enabled` 설정 추가
  (LLM options 메뉴, `claude-anyctl ollama-options` / `provider-options`, headless 플래그
  모두 지원). off 면 라우터가 업스트림에 `stream:false` 를 강제하고 응답 전체를
  Claude Code 에 반환 — 스트리밍 단편화로 tool-call/JSON 파싱이 깨질 때의 우회책.
- **단어 경계 스트리밍**: `stream_word_chunking` 옵션 추가. SSE text delta 를 공백/
  단어 경계까지 모아서 한 번에 보냅니다. Ollama 라우터 경로와 native 패스스루 경로
  (vLLM, NVIDIA hosted, self-hosted NIM) 양쪽 모두에 구현. Tool delta 와 텍스트가
  아닌 SSE 이벤트는 그대로 통과합니다.
- **전체 hook 처리**: `install_tool_guard_hooks` 가 Claude Code 의 모든 hook event
  (PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionRequest,
  PermissionDenied, SessionStart/End, Setup, UserPromptSubmit/Expansion, Stop,
  StopFailure, InstructionsLoaded, ConfigChange, CwdChanged, Notification,
  SubagentStart/Stop, TeammateIdle, TaskCreated, TaskCompleted, PreCompact, PostCompact,
  WorktreeCreate, WorktreeRemove, Elicitation, ElicitationResult) 를 등록합니다.
  WorktreeCreate 핸들러가 `worktreePath = base_path` 를 반환해 git 저장소가 아닌
  디렉터리에서도 Agent isolation 이 동작합니다.
- **Windows hook 호환성**: `shell_command_string` 이 Windows 에서 forward slash 와
  POSIX 인용을 사용하도록 변경 — Claude Code 의 sh 기반 hook 실행기가
  `C:\Users\...` 같은 경로의 백슬래시를 escape 문자로 먹어버리던 문제 해결.
- **LLM options UX**: 강조된 행의 설명을 사용자 언어로 패널 하단에 표시. boolean
  토글(`Stream`, `Stream word chunking`, `Native compatibility`, `Think`) 은 Enter
  키로 즉시 on/off 전환 — 입력 프롬프트 없이 in-place 토글.

### 0.1.22

- **Headless 매뉴얼 확장**: 자동화 및 원격 서버용 headless setup / launch / test / passthrough / cleanup 예제로 매뉴얼을 확장했습니다.

### 0.1.21

- **서비스 생명주기 문서화**: Claude Any가 실행 시 선택된 provider에 필요한 router/proxy만 시작하며, `claude-any stop`이 명시적인 정리 명령임을 명확히 설명합니다.

### 0.1.20

- **NVIDIA hosted quick test**: `auto` 모드가 NVIDIA hosted provider에서는 text-only quick test를 사용합니다. 메뉴 확인 중 느리거나 불안정한 tool_use 요청을 피합니다. text + tool_use는 `smoke`, 전체 text/tool_use/tool_result 왕복은 `full`을 사용하세요.
- **메뉴 테스트 타임아웃**: 터미널 메뉴는 `claude-any test 60 auto`를 실행하여 hosted 모델의 pre-launch 테스트가 더 빠르게 끝나도록 합니다.

### 0.1.19

- **더 빠른 호환성 테스트**: `claude-any test`가 `auto`, `smoke`, `full` 모드를 지원합니다.
- **메뉴 기본 테스트 속도 개선**: 터미널 메뉴는 `claude-any test 120 auto`를 실행합니다. NVIDIA hosted 호환성 확인은 더 빨라지고, 전체 검증은 `claude-any test 180 full`로 계속 사용할 수 있습니다.

### 0.1.18

- **NVIDIA hosted 일시 장애 진단**: 호환성 테스트가 `RemoteDisconnected`, connection reset, 502/503/504 응답을 NVIDIA hosted backend/API Catalog의 일시적인 upstream 실패로 표시합니다.
- **NVIDIA proxy 정리 개선**: `claude-any stop`이 `nvd-claude-proxy` 실행 파일 프로세스도 찾아 정리하므로 stale proxy session이 더 안정적으로 종료됩니다.

### 0.1.17

- **메뉴 호환성 테스트 타임아웃**: 터미널 메뉴가 호환성 테스트를 명시적으로 180초 제한으로 실행하고, hard limit을 넘으면 child process를 종료합니다. 느린 hosted 모델 때문에 메뉴가 무기한 대기하는 것처럼 보이는 문제를 방지합니다.

### 0.1.16

- **NVIDIA hosted proxy 시작 수정**: `python -m nvd_claude_proxy.main`으로 fallback하기 전에 설치된 `nvd-claude-proxy`/`ncp` 실행 파일을 감지해 실행합니다. proxy가 uv tool로 설치되어 명령은 있지만 Claude Any의 Python 인터프리터에서 import되지 않는 환경을 지원합니다.

### 0.1.15

- **Ollama/Ollama Cloud 툴 호출 스트리밍 수정**: 스트리밍 툴 호출을 순차 Anthropic SSE content block index와 `input_json_delta` payload로 내보내도록 변경. Claude Code가 잘못된 streamed tool-use block을 `Invalid tool parameters`로 거절하던 문제를 방지합니다.
- **툴 guard 자동 설치**: 비 Anthropic provider 실행 시 Claude Any tool guard를 `~/.claude/settings.json`에 병합하여, 실행 전 생성된 툴 입력을 정규화합니다.
- **툴 호출 진단 로그**: 라우터가 만든 툴 호출은 `~/.config/claude-any/tool-calls.jsonl`, Claude Code hook 입력은 `~/.claude/claude-any-tool-guard/tool-events.jsonl`에 기록합니다.
- **툴 입력 정규화**: guard가 `path`를 `file_path`, `cmd`를 `command`, `query`를 `pattern`으로 변환하고, 필수 필드가 없을 때 명확한 안내를 반환합니다.

### 0.1.14

- **SSH/터미널 방향키 호환성**: `read_menu_key()`에 ANSI escape sequence 파서를 추가하여 재작성하고, raw 터미널 설정을 `portable_select()`로 이동해 메뉴 루프 동안 터미널이 계속 raw 모드를 유지하도록 변경. 키 입력 사이 `ECHO`가 복원되면서 escape sequence가 화면에 노출되던 문제 해결. 방향키, Home, End 키가 SSH 세션에서 안정적으로 동작합니다.
- **테스트 타임아웃**: 느린 클라우드 공급자를 위해 호환성 테스트 기본 타임아웃을 60초에서 120초로 증가.
- **Ollama Cloud 호환성 테스트 수정**: 호환성 테스트 요청에 `"stream": false`를 추가하여 라우터가 Ollama Cloud에 SSE 스트리밍 대신 단일 JSON 응답을 요청하도록 변경. 이로써 `post_json`이 모든 SSE 청크를 모으는 동안 timeout되던 문제 해결.

### 0.1.13

- **Ollama 스트리밍 프록시**: 라우터가 Ollama/Ollama Cloud 응답을 Anthropic SSE 포맷으로 실시간 스트리밍합니다. 전체 응답을 버퍼링한 뒤 전달하던 기존 방식에서 토큰이 생성되는 즉시 전달하는 방식으로 변경되었습니다.
- **설정 캐싱**: `load_config()`가 설정 파일을 메모리에 캐시하고 파일 수정 시간이 변경될 때만 다시 읽습니다. 라우터의 모든 요청에서 반복되던 디스크 I/O와 JSON 파싱이 제거되었습니다.
- **토큰 추정 캐싱**: `estimate_tokens()`가 선택적 캐시 딕셔너리를 받아 단일 요청 내의 중복 `json.dumps()` 호출을 피합니다. `ollama_chat_request`와 `cap_output_tokens_for_context`가 같은 캐시를 공유합니다.

### 0.1.12

- 문서와 데모 에셋 갱신.

### 0.1.11

- 툴 호출 호환성 검증.

### 0.1.10

- 테스트에 런타임 컨텍스트 표시.

### 0.1.9

- 서버 컨텍스트에 맞춘 프리셋 상한.

### 0.1.8

- LLM 프리셋 현지화.

## 프로바이더

| Provider | Mode | Notes |
| --- | --- | --- |
| Anthropic | Native Claude Code | Claude 로그인 또는 Anthropic API 키 사용. |
| Ollama | Native 우선, 필요 시 router | 로컬 Ollama는 보통 API 키가 필요 없습니다. 로컬 Ollama에서 `:cloud` 모델을 쓰려면 Ollama host에서 `ollama signin`이 필요합니다. |
| Ollama Cloud | Router | `https://ollama.com/api` 직접 호출. Ollama API 키 필요. |
| vLLM | Native Anthropic-compatible endpoint | Anthropic 호환 `/v1/messages`를 제공하는 vLLM endpoint 사용. 모델 계열에 맞는 `--tool-call-parser` 필요. |
| NVIDIA hosted | Router/proxy | NVIDIA hosted API를 compatibility 경로로 사용. |
| self-hosted NIM | Native Anthropic-compatible endpoint | self-hosted NIM Anthropic 호환 endpoint 사용. |

## 서비스 생명주기

Claude Any는 가능한 모든 backend helper를 항상 띄워두지 않습니다. 기본
생명주기는 다음과 같습니다.

- 실행 전 관리 중인 router/proxy는 `claude-any stop`으로 정리할 수 있습니다.
- `claude-any`가 Claude Code를 시작할 때, 선택된 provider에 필요한 서비스만
  시작합니다.
- Ollama/Ollama Cloud router mode는 `127.0.0.1:8799`의 Claude Any router를
  사용합니다.
- NVIDIA hosted router mode는 `127.0.0.1:8799`의 Claude Any router를 쓰고,
  해당 provider에 필요할 때만 `127.0.0.1:8788`의 `nvd-claude-proxy`를
  시작합니다.
- NVIDIA hosted에서 다른 provider로 전환할 때 NVIDIA proxy를 계속 살려둘
  필요는 없습니다. 새 테스트나 실행 전 stale session은 `claude-any stop`으로
  정리하세요.

이 방식은 Claude Code가 하나의 안정적인 Claude Any 진입점을 사용하게 하면서,
provider-specific helper는 필요한 시점에만 시작하도록 합니다.

## 헤드리스 에이전트 채팅

라우터가 실행 중이면 서브 에이전트는 메뉴 없이 로컬 HTTP로 대화할 수 있습니다.

```sh
curl -s http://127.0.0.1:8799/ca/chat/messages \
  -H 'content-type: application/json' \
  -d '{"channel":"agents","sender_id":"codex","recipients":["kimi"],"message":"테스트 실패 로그가 필요합니다."}'

curl -s 'http://127.0.0.1:8799/ca/chat/messages?channel=agents&recipient=kimi&after=0'

curl -N 'http://127.0.0.1:8799/ca/chat/stream?channel=agents&recipient=codex&after=10&timeout=300'

curl -s http://127.0.0.1:8799/ca/plan/artifacts \
  -H 'content-type: application/json' \
  -d '{"title":"handoff","name":"handoff.md","content":"# Plan\n- reproduce\n- patch\n- verify"}'
```

메시지는 `~/.config/claude-any/chat-messages.jsonl`, plan 파일은
`~/.config/claude-any/plan-artifacts/`에 저장됩니다.

Qwen3-Coder를 vLLM에서 Claude Code용으로 실행하는 예:

```sh
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3-coder-30b \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

## 링크

- Ollama Cloud: [cloud overview](https://ollama.com/cloud), [API key settings](https://ollama.com/settings/keys), [authentication docs](https://docs.ollama.com/api/authentication).
- Ollama Anthropic compatibility: [docs](https://docs.ollama.com/api/anthropic-compatibility).
- vLLM: [Claude Code integration](https://docs.vllm.ai/en/latest/serving/integrations/claude_code/), [tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/), [GitHub](https://github.com/vllm-project/vllm).
- NVIDIA hosted NIM: [NVIDIA API Catalog](https://build.nvidia.com/), [quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart).
- Self-hosted NVIDIA NIM: [Claude Code with NIM](https://docs.nvidia.com/nim/large-language-models/latest/ai-assistant-integrations/claude-code.html), [getting started](https://docs.nvidia.com/nim/large-language-models/1.14.0/getting-started.html), [NGC keys](https://org.ngc.nvidia.com/setup/personal-keys).

## 라이선스

MIT. [LICENSE](../LICENSE)를 참고하세요.
