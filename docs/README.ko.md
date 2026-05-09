# Claude Any

| [English](../README.md) | 한국어 | [日本語](README.ja.md) | [中文](README.zh.md) |
| --- | --- | --- | --- |

Claude Any는 Claude Code 실행 전에 Anthropic, Ollama, Ollama Cloud, vLLM,
NVIDIA hosted, self-hosted NIM을 선택하고, Claude Code의 일반 인자는 그대로
전달하는 프로바이더 선택 런처입니다.

Credits: One Ciel LLC

현재 버전: `0.1.13`

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

요구사항:

- Python 3.10+
- `claude` 명령으로 실행 가능한 Claude Code
- MCP 웹 도구를 사용할 경우 Node/npm

현재 바로 동작하는 GitHub 설치:

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

소스 설치:

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

npm registry에 최초 publish한 뒤 설치:

```sh
npm install -g @onecielai/claude-any
claude-any
```

업그레이드:

```sh
# GitHub 설치, 현재 권장 경로
npm install -g https://github.com/OneCielAI/claude-any.git --force
claude-any version
```

`npm update -g @onecielai/claude-any`가 동작하려면 같은 패키지 이름으로 public
npm registry에 publish되어 있어야 합니다.

```sh
npm login
npm publish --access public
npm install -g @onecielai/claude-any
npm update -g @onecielai/claude-any
```

자동 배포를 쓰려면 npm automation token을 GitHub repository secret `NPM_TOKEN`
으로 저장한 뒤 GitHub Release를 만들거나 `Publish to npm` workflow를 수동
실행하면 됩니다.

버전은 SemVer를 사용합니다. 다음 릴리스에서는 `package.json`의 `version`을
올리고, `v0.1.1` 같은 같은 버전의 Git tag와 GitHub Release를 만들면 npm publish
workflow를 실행할 수 있습니다. registry publish 이후에는 다음 명령으로
업그레이드할 수 있습니다.

```sh
npm update -g @onecielai/claude-any
```


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
- 설정 파일 캐싱 — 라우터의 요청마다 디스크에서 읽던 설정을 메모리에 캐시하여
  파일 수정 시에만 다시 읽습니다.

## 변경 이력

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
