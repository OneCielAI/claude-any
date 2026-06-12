# claude-any 코드베이스 아키텍처 분석

> 작성일: 2026-06-10
> 대상 커밋: `b76d172` (nightly) / 기준 `2df409c` (main)
> 방법: 8개 도메인 멀티에이전트 정독 + 96개 핵심 주장 교차검증(63 확인 / 33 교정, 5건 반박). 모든 `file:line`은 정독 시점 기준이며, 교정으로 약화·반박된 주장은 본문에 명시했다.

---

## 한 줄 요약

claude-any(`@oneciel-ai/claude-any` v0.1.106)는 **Anthropic의 `claude` CLI를 다른 LLM 백엔드(Ollama·DeepSeek·vLLM·LM Studio·NVIDIA NIM 등)로 돌리게 해주는 프로바이더 셀렉터**다. 동작 원리는 ① 로컬에 Anthropic `/v1/messages` API를 흉내내는 HTTP 라우터를 띄우고 ② `claude`를 `ANTHROPIC_BASE_URL=로컬라우터`로 실행해 ③ 들어온 Anthropic 요청을 업스트림 프로토콜로 번역·전달하고 응답을 다시 Anthropic SSE로 역번역하는 것이다.

프로젝트의 본질은 (작성자 표현대로) **"streamable HTTP를 지원하지 못하는 Claude를 위한 헬퍼"** — SSE/MCP 메시지를 세션에 잘 끼워 넣는 것이고, 웹챗은 부산물이다. 거의 전부가 **단일 파일 `claude_any.py` 27,933줄, 정의 약 1,013개**에 들어 있다.

---

## 전체 구조

```
npm-bin/*.js (Node 런처: Python 찾아 re-exec만)
  └─ claude_any.py  ← 사실상 모든 것
       ├─ 진입: main()@27929 → {mcp-proxy | cli→run_cli | launch→launch_claude | argparse}
       ├─ launch_claude@26689  ← 오케스트레이션 코어
       │    ├─ 업데이트 체크 → 프리런치 TUI → 네이티브 vs 라우티드 판정
       │    ├─ start_router_if_needed (라우티드면 `serve` 서브프로세스 spawn)
       │    └─ `claude --dangerously-skip-permissions ... --mcp-config ...` 실행
       ├─ serve@14538 → ThreadingHTTPServer + RouterHandler@14266
       │    └─ do_POST@14356 → /v1/messages → forward_* (3경로)
       ├─ 채널/MCP 브리지 (8400~9580, 23200~26200)
       ├─ config/모델/프리셋/레이트리밋 (446~899, 1896~2270, 4587~5604, 17300~18600)
       └─ TUI 메뉴 + CLI cmd_* + 프로세스/포트 라이프사이클
```

> **교정①**: 라인 2692의 `def main()`은 별개 진입점이 아니다. `STATUSLINE_SCRIPT`(2544~2843) raw 문자열 **안에 통째로 박힌 독립 statusline 프로그램**이며, `install_claude_any_statusline`(2846)이 디스크에 써서 Claude 설정에 등록한다. 즉 파일이 "또 다른 프로그램을 문자열 페이로드로 들고 다니는" 구조다.

---

## 1. 진입점 & 라이프사이클

**런치 경로**: `claude-any` → Node 래퍼가 `CLAUDE_ANY_NPM_MODE`(빈 문자열=raw 서브커맨드, `cli`=run_cli 정문)를 env로 지정 → `python claude_any.py cli ...` → `run_cli`(거대한 수제 argv 루프, `--ca-*` 플래그 파싱 + claude passthrough 분리) → `launch_claude`.

**네이티브 vs 라우티드** (`launch_claude:26716`):
- `use_native_anthropic = direct_native_anthropic_enabled(...)` → provider가 "anthropic"이고 라우티드 아님일 때 true
- 네이티브 모드는 **하드 계약**: env에서 `ANTHROPIC_*`/`CLAUDE_CODE_*`/`CLAUDE_ANY_*` 약 20개를 전부 제거(26757~26781)해 Claude Code가 claude-any 없는 것처럼 동작 → "백엔드가 바뀌어도 동일 UX" 목적과 정확히 부합
- **교정②**: "네이티브면 라우터를 절대 안 띄운다"는 부정확. `start_router_if_needed`는 `if use_router_mode or llm_channel_delivery`(26747) 조건이라, 네이티브라도 채널 LLM 전달이 필요하면 라우터가 뜬다.

**라우터 신원 = 소스 해시**: `SOURCE_FINGERPRINT = sha256(claude_any.py)[:16]`(269). `router_health_matches_current`(14581)가 VERSION + 소스해시 + user + config가 모두 맞아야 기존 라우터를 재사용 → 파일을 한 바이트만 고쳐도 다음 런치에서 라우터 재시작. 멀티테넌트 안전: 다른 config의 라우터는 죽이지 않고 'skipped_foreign_config' 로깅.

**라이프사이클**: 클라이언트측 supervisor(20253, 죽으면 재시작 + 종료 시 정리)와 서버측 idle/owner watchdog(20142, 기본 90초 idle 종료)이 `ROUTER_CLIENTS_DIR`의 PID 파일로만 조율. stale PID/PID 재사용 시 조기 종료 위험은 약하게만 뒷받침됨.

> **교정③ (반박)**: 기본 `--dangerously-skip-permissions`(26898 무조건) + 조건부 `--permission-mode bypassPermissions`(26902)를 "안전 자세(safety posture)"로 표현한 건 **뒤집힌 것**. 실제로는 **권한 프롬프트를 기본으로 끄는 것** — 가드레일 비활성화다. 라우티드 자동 채널 운영을 위한 의도된 설계지만 명백한 보안 리스크로 분류해야 한다.

---

## 2. 프로바이더 라우팅 & 요청/응답 번역

`do_POST`(14356)가 body 전처리(스키마 캐싱·thinking 정규화·도구 필터·plan-mode 단락·채널 주입) 후 **3경로**로 분기:

| 경로 | 대상 | 변환 |
|---|---|---|
| **Anthropic passthrough** | deepseek, opencode-messages, native-compat인 lm-studio/vllm/nim | body를 `/v1/messages`로 그대로 POST, `_rebatch_anthropic_sse_text`로 SSE 재배치 |
| **Ollama NDJSON** | ollama, ollama-cloud | `anthropic_messages_to_ollama` ↔ `ollama_chat_to_anthropic`, `/api/chat` |
| **OpenAI chat** | vllm/lm-studio/nvidia-hosted/nim(non-native), opencode(openai-chat) | `anthropic_messages_to_openai` + `repair_openai_tool_call_adjacency` ↔ `openai_chat_to_anthropic`, `/v1/chat/completions` |

**영리한 재사용**: `openai_chat_to_anthropic`(13510)는 OpenAI 응답을 Ollama 모양 dict로 감싸 `ollama_chat_to_anthropic`에 위임 → 도구 정규화·plan-mode 합성·빈응답 복구 로직이 한 곳에 산다.

**도구 호출 라운드트립**: 인바운드 도구 스키마를 `_TOOL_SCHEMA_REGISTRY`에 캐싱 → 업스트림이 도구 호출(또는 `<|tool_calls_section_begin|>` 같은 의사-센티넬 텍스트, `parse_pseudo_tool_calls`) → `resolve_emitted_tool_name` → `normalize_tool_arguments` → `_validate_and_fix_tool_input`(타입 강제, 필수 누락 시 기본값 주입, `task_id→taskId` 별칭 리맵).

**프로바이더별 특수성**: nvidia-hosted는 네이티브 compat을 일부러 끔(6325, 카탈로그가 OpenAI 전용) — 별도 NCP 프록시(127.0.0.1:8788)는 **모델 ID 리맵·리스팅에만** 쓰고 채팅 요청은 `integrate.api.nvidia.com`으로 직접. deepseek-v4는 `supportsToolChoice=false`라 강제 tool_choice를 조용히 드롭(3447).

**리스크**:
- `_fuzzy_match_tool_name`이 양방향 substring 매칭(1097) → 짧거나 이상한 이름이 무관한 도구로 오라우팅될 수 있음.
- 하드코딩 프로바이더 튜플이 파일 전역에 산재(provider_headers, native_anthropic_base_url, OPENAI_COMPATIBLE_ROUTER_PROVIDERS 등) → 추가 시 누락하면 조용히 오라우팅.
- `_validate_and_fix_tool_input`이 누락 필수 필드에 빈 타입값 주입 후 WARN만(1324) → 의미상 빈 도구 호출이 Claude Code로 전달돼 잘못된 모델 출력을 가림(교정: 일부 예시는 부정확하나 메커니즘은 확인).

---

## 3. 스트리밍 / SSE 번역

업스트림 청크를 Claude Code가 기대하는 정확한 Anthropic 이벤트 생명주기(`message_start → (content_block_start/delta/stop)* → message_delta → message_stop`)로 번역. 3개 변환기 + 단어경계 버퍼.

**단어경계 재배치** (`_split_word_buffer` 12158): 업스트림이 단어 중간을 쪼개 보내므로, 마지막 공백까지만 flush하고 나머지 부분단어는 보류 → UI가 깔끔한 단어 단위 스트리밍. 64자 cap으로 CJK·긴 토큰 같은 공백없는 입력에서도 진행 보장(12179).

**OpenAI reasoning → thinking**: OpenAI엔 암호학적 thinking 서명이 없어 `close_reasoning_block`이 `claude-any-openai-reasoning-<sha>`로 가짜 서명을 위조(13617)해 Anthropic 블록 모양을 충족.

**suppressed-thinking keepalive**: passthrough에서 thinking 억제 시 `: suppressed-thinking` SSE 주석을 초당 1회 보내 연결 유지(12233).

**빈/숨은 응답 복구**: 3개 변환기 모두 업스트림이 빈/clarification 응답을 줄 때 EnterPlanMode나 TaskList를 합성하고 `stop_reason`을 `tool_use`로 재작성해 Claude Code 에이전트 루프를 살림.

**disconnect 감지**: `router_client_connection_closed`(11261)가 select() + 1바이트 MSG_PEEK로 다운스트림 종료를 능동 감지 → `UpstreamClientDisconnected`로 깔끔히 중단(쓰기 실패에만 의존하지 않음).

**리스크**:
- **3중 중복**: 빈응답/plan/keepalive 도구합성 + 블록종료 로직이 3개 변환기에 독립 재구현 → 이미 드리프트.
- **OpenAI 경로 관측성 비대칭**: `stream_openai_chat_to_anthropic_sse`의 `emit()`는 per-emit BrokenPipe 가드가 없고(Ollama엔 있음, 12834), `iter_upstream_lines_until_client_disconnect`도 안 씀 → 취소된 OpenAI 스트림이 업스트림 끝까지 drain. **교정④**: 단, "처리 안 된 OSError를 던진다"는 결과는 반박됨 — disconnect는 13893의 일반 except에서 `openai_stream_error`로 잡힌다. 영향은 미관측 종료 + drain이지 크래시는 아님.
- **교정⑤**: SSE trace(`make_outgoing_sse_trace`)는 **Ollama 변환기에서 정확히 1회만** 호출됨(12825). "각 변환기가 trace 생성"은 과장 — OpenAI 경로엔 trace가 아예 없어 관측성 비대칭은 사실.
- `set_upstream_stream_read_timeout`이 urllib 내부(`resp.fp.raw._sock`)에 의존(11245) → Python 변경 시 조용히 no-op돼 hang 재발 가능.
- **교정⑥**: re-batcher 인덱스 압축의 "`mapped_content_index`가 None 반환" 실패 모드는 반박됨 — 억제되지 않은 정수 인덱스엔 raw 인덱스로 폴백. 공유 상태 결합 자체는 실재.
- 출력 토큰 회계는 usage 부재 시 `len(text)//4` 휴리스틱(부정확).

---

## 4. 채널 / MCP 브리지 (가장 복잡·최근 변경 집중)

외부 이벤트원(웹챗, MCP 알림)이 Claude Code 세션을 깨우고 구동하는 **3경로**:

1. **소스 MCP 구독**: `_channel_sse_worker`/`_channel_streamable_http_worker`가 원격 MCP 서버의 SSE/streamable-HTTP 알림을 읽어 채팅 스토어 메시지로 변환. streamable-HTTP는 405 시 SSE로 투명 다운그레이드(8876).
2. **라우터 자신이 MCP 서버**: `/ca/mcp/sse`(GET)가 저장 메시지를 MCP 알림으로 스트리밍, `/ca/mcp/messages`(POST)는 JSON-RPC 응답을 **인라인 반환하지 않고** SSE 아웃박스에 큐잉 후 202 반환(레거시 MCP SSE 전송 계약).
3. **라우터 소유 "다이렉트 LLM"**: `_channel_direct_llm_router_response`(24099)가 숨은 `claude -p` 없이 **바운드된 10턴 도구루프**를 소스 MCP에 직접 돌려 채널 DM에 자율 응답.

**가시 세션 전달**: PTY wake-prompt 주입(`subprocess_call_with_channel_wake_proxy` — 0.5초마다 채팅/요약 파일 폴링, `Ctrl-U + 프롬프트 + Enter`를 PTY 마스터에 씀) 또는 다음 라우티드 `/v1/messages` body에 펜딩 메시지/요약 주입. Enter 바이트는 PTY마다 달라 **실제 사용자 키스트로크를 관찰해 학습**(25148).

**두 개의 헷갈리는 wait-cap 시스템** (혼동 주의):
- `cap_mcp_notification_wait_tool_input`(1416): 라우티드 스트림에서 **모델의 아웃바운드** wait-도구 인자(timeout_ms)를 클램프(기본 1000ms, 90초 내 중복 시 100ms) — 모델이 스트림을 긴 wait로 막지 못하게. (env `CLAUDE_ANY_MCP_NOTIFICATION_WAIT_TIMEOUT_MS`)
- `_mcp_proxy_wait_timeout_seconds`(25651): **MCP 프록시 자신**이 알림 결과를 합성하기 전 블록하는 시간(기본 10초/최대 30초). (env `CLAUDE_ANY_MCP_WAIT_DEFAULT_SECONDS`/`_MAX`)

최근 커밋들(MCP 알림 wait capping, streamable 알림 큐잉, 채널 알림 스케줄링)이 모두 이 영역이며, 운영 중 "알림을 받았는데 LLM에 surface 안 됨" 문제의 핵심 후보 지대다.

**리스크** (자율 루프가 위험의 핵심):
- **자율 도구 allowlist가 휴리스틱**: prefix/term 기반(`create_`는 허용, `delete_`/`payment` 차단). `create_payout` 같은 잘못 명명된 파괴적 도구가 사용자 승인 없이 자율 호출될 수 있음.
- **PTY 합성 입력의 안전 핸드셰이크 부재**: 사용자가 타이핑 중이거나 모달이 열렸을 때 `Ctrl-U + 프롬프트 + Enter`가 입력을 clobber하거나 오순간 제출. (안정적 active-REPL 큐가 없음 — 연구 노트의 Open Question.)
- **자연어 regex 의존**: `_channel_direct_*` 가드들이 한/영 정규식·마커로 deferral/decline/reply를 판정 → 모델 출력의 사소한 표현 변화가 제어흐름을 조용히 바꿈. 테스트 곤란.
- 알림 dedupe가 stable-id 휴리스틱 → 타임스탬프만 바뀌고 stable id 없는 소스는 dedupe 우회 → 반복 자율 응답.
- **교정 7·8**: "커서 이중 진행으로 메시지 누락"과 "회전 후 ID 재사용"의 **위험 결론은 코드로 뒷받침 안 됨**(라인 인용은 정확, 인과는 약함). `append_chat_message`가 매번 파일 전체 재스캔으로 O(n)인 성능 문제는 사실. `handle_channel_mcp_get`이 매 wake마다 처음부터 재읽기도 사실이나 회전이 파일을 20MB로 bound함.

---

## 5. Config · 모델 카탈로그 · 프리셋

**Config 파이프라인**: `deep_merge(DEFAULT_CONFIG, 파일)` → 마커게이트 멱등 마이그레이션(`apply_config_migrations`) → 프로바이더별 모델ID 정규화. mtime 키 인프로세스 캐시. 원자적 쓰기(tmp + chmod 0o600 + replace).

**모델 ID**: 업스트림 ID를 `claude-any-<provider>-<slug>` 별칭으로 슬러그(NVIDIA `claude-*`는 통과), `[1m]` 컨텍스트 접미사 제거.

**3개 디스크 캐시**: 범용 `model-registry.json`(base_url/키유무/커스텀모델 키), 단명 `model-list-cache.json`, 별도 Ollama 라이브러리 카탈로그(ollama.com HTML에서 컨텍스트 윈도우를 **정규식 스크레이핑** — K/M/G는 1024 기반이라 128K가 131072). Anthropic 모델은 OAuth에서 `/v1/models`가 없어 **공식 docs HTML 스크레이핑**(`fetch_anthropic_public_model_ids`).

**프리셋**: `apply_llm_preset_to_provider`(18070)가 프로바이더별 토큰 매트릭스(~450줄 인라인 하드코딩)를 적용 → 모델 family/capacity에 묶고 capacity로 cap, 자동 타임아웃 선택(>=1M:300s, >=512K:180s, else 120s).

**레이트리밋**: 파일백 글로벌-per-provider RPM 윈도우(`rate-limit-state.json`), 서버 헤더 학습(429에서 server_rpm 추론해 과낙관 설정 자동 보정), API 키 라운드로빈.

**리스크**:
- **레이트리미터 cross-process 경쟁** (높음): 매 요청·헤더 갱신마다 상태 파일 전체를 read-modify-write하는데 **락이 인프로세스 전용**(`_RATE_LIMIT_LOCK`) → 같은 CONFIG_DIR 공유 다중 라우터가 타임스탬프 갱신을 잃음(last-writer-wins). 동시 세션 시 레이트리밋 무력화 가능.
- Ollama 컨텍스트 스크레이핑이 고정 정규식 → 마크업 변경 시 조용히 이름 휴리스틱 폴백.
- 손상 config(`load_config:2040`)를 경고 없이 빈 dict→기본값으로 조용히 리셋.
- 프리셋 매트릭스가 4곳에 병렬 중복 → 프로바이더별 dict에 프리셋 키 누락 시 적용 시점 KeyError.
- `apply_router_rate_limit` 대기 루프에 전체 데드라인 없음 → 먼 미래의 penalty_until이 요청 스레드를 penalty 기간 내내 블록.

> **교정 9**: `model_context_hint_from_model_id`의 "pro/large substring으로 오분류" 예시는 부정확 — 17567에서 pro는 `deepseek-v4-pro`/`v4-pro`로만 스코프되고 large는 그 함수에 없음. `1m`/`million` 광역 substring 위험만 사실.

---

## 6. Claude Code 동작 셰이핑

비-Anthropic 모델이 Claude Code UX를 깨지 않게 요청을 주입·재작성하고 응답을 합성하는 계층. (이 도메인 리더는 출력 토큰 한도로 실패해, 함수 시그니처 기준 1차 인덱싱이며 깊은 검증은 미수행.)

- **Plan mode**: `should_auto_enter_plan_mode`(3829)가 응답·도구호출을 보고 구현계획 요청이면 EnterPlanMode 자동 진입. `backfill_exit_plan_mode_allowed_prompts`(3673)로 exit 시 허용 도구 채움.
- **합성 TaskList 복구**: `should_keep_work_alive_with_tasklist`(4110)·`should_recover_empty_end_turn_with_tasklist`(4143)가 빈 end_turn·작업중단을 감지해 `append_synthetic_tasklist_to_message`(4188)로 TaskList를 합성 → 약한 모델의 조기 종료 방지.
- **Thinking 처리 3방식**: passthrough는 thinking 블록 유지 / OpenAI-chat reasoning-passback(deepseek-via-opencode만)은 블록 보존하되 top-level thinking 드롭 / 그 외는 thinking 완전 제거 후 `remember_suppressed_thinking_passback`(3513)으로 캐싱해 나중에 rehydrate.
- **도구 게이팅**: `resolve_blocked_tools`(3144)·`filter_blocked_tools`(4244).
- **Advisor 모델**: `maybe_handle_advisor_request`(11897)·`call_advisor_text`(11546) — 별도 어드바이저 모델을 시스템에 주입하거나 메시지를 정제(`refine_message_with_advisor`).
- **Ultracode 감지**: `body_ultracode_runtime_enabled`(3273)·`claude_code_ultracode_enabled`(4734).
- **tool-guard 훅**(`claude-any-tool-guard.py`, 857줄): 별도 프로세스 PreToolUse 훅으로 도구 입력 검증·정정.

---

## 7. 메뉴 UI · CLI · 테스트

**TUI**: `portable_prelaunch_menu`(21829)는 단일화면 redraw 루프. 패널이 CLI `cmd_*`와 **동일한 `set_*_config` 뮤테이터**를 호출 → 메뉴와 CLI가 config 의미론에서 드리프트 불가(강점).

> **교정 10 (반박)**: "메뉴가 키 누를 때마다 디스크에서 config 재로드 → UI가 디스크 지연에 묶임"은 반박됨 — `load_config`의 mtime 캐시(2029)로 실제 읽기는 mtime 변경 시에만.
> **교정 11**: 키스트로크 디버그 로그가 `/tmp` 고정이라는 주장은 `claude_any.py` 쪽 반박 — `CONFIG_DIR/ca-key-debug.log`(회귀 테스트로 고정). 레거시 포크만 `/tmp` 고정.

**`claude-any-menu.py`는 죽은 분기 포크**: 별도 2,035줄 프로그램이 인프로세스 헬퍼 대신 `claude-anyctl` 바이너리로 shell-out. `CLAUDE_ANY_USE_LEGACY_MENU=1` + POSIX에서만 도달 → Windows 체크아웃에선 사실상 dead code이고 opencode 프로바이더를 모르는 등 뒤처짐.

**테스트**: 28파일/~537 메서드, `py_compile` 게이트 후 `unittest discover`. 커버리지 도구·pytest·JS 테스트 없음, **Windows/macOS CI 없음**(ubuntu 단일 잡).

> **교정 12 (반박)**: "py_compile 게이트가 파싱만 증명 → false confidence"는 반박됨 — `package.json:48`은 `py_compile && unittest discover`로 실제 537 테스트를 연결하고, 29개 중 28개가 `claude_any`를 import해 내부 함수를 직접 호출. 단 정량 전제(거대 파일)는 사실.
> **교정 13 (반박)**: "레이트리밋이 Anthropic 네이티브만 테스트"는 반박됨 — `test_api_key_rotation.py`(190~257)가 opencode(OpenAI 호환)에 대해 공유 재시도 래퍼를 429로 직접 테스트.
> **교정 14 (반박)**: "채널브리지 통합테스트의 SSE 업스트림이 서브프로세스에 공급"은 반박됨 — 인용 293-294는 별개 in-process 단위테스트이고, `mcp-proxy` 서브프로세스 테스트의 업스트림은 stdio 가짜 서버다.

**진짜 커버리지 공백** (검증 완료):
- `forward_ollama_api_chat`(13264): **테스트 전무**. 순수 헬퍼만 테스트 → Ollama 스트리밍 회귀가 CI 통과.
- `forward_openai_compatible_chat`(14173): 모든 라우터 테스트에서 모킹 → 실업스트림 미실행. OpenAI→Anthropic 스트리밍은 단일 opencode/deepseek 케이스만.
- 버전동기 sed가 brittle하고, **테스트가 재작성 전에 돌아** desync가 가드를 **우회**(빌드 실패가 아니라 잘못된 nightly로 빠져나감).

---

## 리스크 / 기술부채 (심각도 순)

**높음**
1. **레이트리미터 cross-process 경쟁** — 인프로세스 락만으로 공유 상태 파일을 RMW. 동시 세션 시 레이트리밋 무력화.
2. **핵심 포워더 무/저커버리지** — `forward_ollama_api_chat` 테스트 0, `forward_openai_compatible_chat` 항상 모킹. 제품 1차 목적인 포워딩 경로가 가장 적게 검증.
3. **Windows/macOS CI 부재** — Windows가 1급 타깃인데 ubuntu 단일 잡.
4. **자율 도구 allowlist 휴리스틱** — 잘못 명명된 파괴적 도구가 사용자 승인 없이 자율 호출 가능.
5. **기본 권한 우회** — `--dangerously-skip-permissions`/bypassPermissions 기본 활성(가드레일 off).
6. **거대 단일 파일** — 27,933줄, ~1,013 정의. 결합도·변경추적 부담(모듈 분리는 `claude_any_support/`로 점진 시작됨 — "전혀 미착수"는 과장).

**중간**
7. SSE 변환기 3중 중복 → 드리프트, OpenAI 경로만 disconnect 능동감지·trace 누락.
8. 하드코딩 프로바이더 튜플 산재 → 추가 시 누락하면 조용히 오라우팅.
9. PTY 합성 입력 안전 핸드셰이크 부재 → 입력 clobber/오순간 제출.
10. 채널 자율 가드의 자연어 regex 의존 → 모델 표현 변화가 제어흐름을 바꿈.
11. 프리셋 매트릭스 4중 중복 → 키 누락 시 KeyError.
12. 버전동기 sed 취약 + 가드 우회.

**낮음**
13. Ollama 컨텍스트 스크레이핑 정규식 취약. 14. 출력 토큰 회계 휴리스틱. 15. 손상 config 조용한 리셋. 16. 레이트리밋 무기한 블록(전체 데드라인 없음). 17. 포트 탐지 regex 파싱(무관 프로세스 kill 가능 — 헤드라인 위험은 약하게 뒷받침). 18. 죽은 포크(`claude-any-menu.py`) 드리프트.

---

## 강점

- **충실한 무해 패스스루 계약** — 네이티브 모드에서 env 약 20개 제거로 Claude Code 동작 불간섭("징검다리" 목적 부합).
- **단일 진실 공급원 config 뮤테이터** — 메뉴·CLI·웹 패널이 동일 `set_*_config` 호출.
- **멀티테넌트 안전 라이프사이클** — foreign config 라우터 보호, 지시적 에러.
- **견고한 disconnect/idle 처리**(Ollama·rebatch 경로) — MSG_PEEK 기반.
- **구조적 secret redaction** — `EventBus._redact_value`가 정규식 아닌 구조적으로 secret 키 마스킹.
- **원자적 상태 쓰기** — config·trace·커서가 tmp+replace(레이트리밋 파일의 cross-process 락 부재만 예외).
- **채널 브리지의 실통합 테스트** — 역설적으로 핵심 포워딩보다 더 철저히 통합 테스트됨.

## 확인 불가 항목

- 단일 파일의 실제 라인 커버리지는 측정 도구가 없어 **알 수 없음**(낮을 것으로 추정되나 정량 미확인).
- nvidia-hosted 프록시/hosted 엔드포인트 모델 ID 불일치는 **조건부 위험**으로, 코드가 명확한 버그를 시연하지는 않음.

---

## 부록: 핵심 함수 인덱스

| 영역 | 함수 | 위치 |
|---|---|---|
| 진입 | `main` | claude_any.py:27929 |
| 진입 | `run_cli` | 27267 |
| 오케스트레이션 | `launch_claude` | 26689 |
| 라우터 | `serve` / `RouterHandler` | 14538 / 14266 |
| 라우터 | `do_POST` | 14356 |
| 포워딩 | `forward_ollama_api_chat` | 13264 |
| 포워딩 | `forward_openai_compatible_chat` | 14173 |
| 번역 | `anthropic_messages_to_ollama` / `_to_openai` | 10561 / 10664 |
| 번역 | `ollama_chat_to_anthropic` / `openai_chat_to_anthropic` | 12056 / 13510 |
| 스트리밍 | `_ollama_stream_to_anthropic_sse` | 12793 |
| 스트리밍 | `stream_openai_chat_to_anthropic_sse` | 13538 |
| 스트리밍 | `_rebatch_anthropic_sse_text` / `_split_word_buffer` | 12184 / 12158 |
| 채널 | `_channel_direct_llm_router_response` | 24099 |
| 채널 | `subprocess_call_with_channel_wake_proxy` | 25085 |
| 채널 | `cap_mcp_notification_wait_tool_input` | 1416 |
| config | `load_config` / `apply_config_migrations` | 2029 / 1906 |
| config | `apply_llm_preset_to_provider` | 18070 |
| 레이트리밋 | `apply_router_rate_limit` | 5505 |
