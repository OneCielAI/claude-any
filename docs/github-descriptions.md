# GitHub Descriptions

Use these for the GitHub repository description, social preview text, release
notes, or project directory listings.

## Short Description

English:
Claude Code provider selector for Anthropic, Ollama, Ollama Cloud, vLLM, NVIDIA hosted, and self-hosted NIM.

한국어:
Anthropic, Ollama, Ollama Cloud, vLLM, NVIDIA hosted, self-hosted NIM을 Claude Code에서 선택해 쓰는 실행 전 설정 런처.

日本語:
Anthropic、Ollama、Ollama Cloud、vLLM、NVIDIA hosted、self-hosted NIM を Claude Code で選択できる起動前ランチャー。

中文:
用于 Claude Code 的启动前供应商选择器，支持 Anthropic、Ollama、Ollama Cloud、vLLM、NVIDIA hosted 和 self-hosted NIM。

## Longer About Text

English:
Claude Any gives Claude Code a pre-launch configuration screen for provider,
model, base URL, API key, compatibility testing, and provider-specific options.
It keeps Claude Code flags pass-through friendly while adding native or router
compatibility for non-Anthropic providers.
When a provider exposes an Anthropic-compatible endpoint, Claude Any prefers the
native path to preserve Claude Code tooling and workflow behavior. Web search is
added through separate MCP tools for providers that cannot supply it remotely.
The console-first menu is designed for SSH and terminal workflows. macOS has not
been fully tested by the maintainer yet; issue reports are welcome.

한국어:
Claude Any는 Claude Code 실행 전에 프로바이더, 모델, Base URL, API 키,
호환성 테스트, 프로바이더별 옵션을 설정하는 화면을 제공합니다. Claude Code
기본 플래그는 그대로 전달하면서, Anthropic 외 프로바이더를 native 또는 router
호환 방식으로 사용할 수 있게 합니다.
Anthropic 호환 엔드포인트가 있는 프로바이더는 native 경로를 우선 사용해
Claude Code의 툴링과 작업 흐름을 최대한 유지하고, 원격 웹검색은 별도 MCP
도구로 보강합니다. 콘솔 우선 메뉴라 SSH와 터미널 작업 흐름에서 설정을 쉽게
바꿀 수 있습니다. macOS는 아직 충분히 테스트하지 않았으므로 문제 제보를
환영합니다.

日本語:
Claude Any は Claude Code の起動前に、プロバイダー、モデル、Base URL、
API キー、互換性テスト、プロバイダー固有オプションを設定できる画面を提供
します。Claude Code の通常フラグをそのまま渡しつつ、Anthropic 以外の
プロバイダーを native または router 互換方式で利用できます。
Anthropic 互換エンドポイントがある場合は native 経路を優先し、Claude Code
のツールとワークフローをできるだけ維持します。リモート Web 検索は別の
MCP ツールで補完します。コンソール第一のメニューなので、SSH やターミナル
中心の作業でも設定を変更しやすくしています。macOS はまだ十分にテストして
いないため、問題報告を歓迎します。

中文:
Claude Any 在 Claude Code 启动前提供供应商、模型、Base URL、API 密钥、
兼容性测试和供应商选项配置界面。它保留 Claude Code 参数透传，同时通过
native 或 router 兼容方式连接非 Anthropic 供应商。
如果供应商提供 Anthropic 兼容端点，Claude Any 会优先使用 native 路径，以
尽量保留 Claude Code 的工具和工作流体验；远程网页搜索则通过独立 MCP 工具
补充。控制台优先的菜单适合 SSH 和终端工作流。macOS 尚未由维护者充分测试，
欢迎反馈问题。

## Origin Statement

English:
Claude Any exists to keep Claude Code workflows moving when premium-model token
windows are temporarily exhausted. It lets slower but usable third-party
providers handle summaries, research, journals, simple coding, and delegated
background tasks, saving Claude/Codex tokens for the hardest work. - D. Yun
It also tries to preserve Claude Code's native strengths by using
Anthropic-compatible endpoints whenever possible and adding separate web-search
tooling only where remote providers need it.

한국어:
Claude Any는 프리미엄 모델의 토큰 창이 잠시 막혀도 Claude Code 작업 흐름을
멈추지 않기 위해 시작되었습니다. 속도는 느려도 쓸만한 third-party
프로바이더에게 요약, 조사, 저널, 간단한 코딩, 백그라운드 위임 작업을 맡겨
Claude/Codex 토큰을 가장 어려운 작업에 남겨둘 수 있습니다. - D. Yun
가능한 경우 Anthropic 호환 엔드포인트를 사용해 Claude Code의 네이티브 장점을
유지하고, 원격 프로바이더에 필요한 웹검색은 별도 도구로 제공합니다.

日本語:
Claude Any は、プレミアムモデルのトークン枠が一時的に尽きても Claude Code
の作業を止めないために始まりました。速度は落ちても実用的な third-party
プロバイダーに要約、調査、ジャーナル、簡単なコーディング、バックグラウンド
作業を任せ、Claude/Codex トークンを最も難しい作業に残せます。 - D. Yun
可能な場合は Anthropic 互換エンドポイントを使って Claude Code のネイティブ
な利点を維持し、必要な Web 検索は別ツールとして提供します。

中文:
Claude Any 的起点，是在高级模型 token 窗口暂时耗尽时仍然保持 Claude Code
工作流不断。它可以把摘要、调研、日志、简单编码和后台委派任务交给速度较慢
但可用的第三方供应商，从而把 Claude/Codex token 留给最困难的工作。 - D. Yun
在可能的情况下，它使用 Anthropic 兼容端点来保留 Claude Code 的原生优势；
远程供应商需要的网页搜索则通过独立工具提供。

## Recommended Uses

English:
Best for background work where speed is not the main constraint: Docker host
maintenance, Windows/Linux administration, cleanup scripts, periodic security
checks, log review, Windows Event Log review, virus/ransomware intrusion-attempt
triage, brute-force attempt review, and readable report drafting. It
does not replace dedicated security tools, but it can help administrators turn
routine checks into repeatable scripts and reports without spending premium
tokens every time.
Used this way, it can become a free or low-cost system security watcher for
routine checks and summaries.
It can also turn operational requests like installing PostgreSQL in Docker or
emailing a Docker-log report into concrete commands and scheduled scripts.
A useful workflow is tiered supervision: smaller models detect and summarize,
a larger model reviews, writes policy, and plans, then smaller models execute
routine steps under supervision.

한국어:
속도가 핵심이 아닌 백그라운드 운영 작업에 적합합니다. Docker 호스트 관리,
Windows/Linux 서버 관리, 정리 스크립트, 주기적인 보안 점검, 로그 리뷰, 침입
시도 흔적 확인, Windows 이벤트 로그 리뷰, 바이러스/랜섬웨어 침입 시도 정리,
무차별 로그인 시도 리뷰, 리포트 초안 생성 등에 추천합니다. 전문 보안 도구를 대체하지는
않지만, 반복 점검을 스크립트와 보고서로 정리하는 서버 관리자 보조 역할에
유용합니다.
이런 방식으로 무료 또는 저비용의 시스템 보안 지키미를 만들 수 있습니다.
Docker 컨테이너에 PostgreSQL을 설치하거나 Docker 로그를 분석해 이메일 리포트로
보내는 식의 운영 요청을 명령어와 스케줄 스크립트로 구체화하는 데도 적합합니다.
작은 모델이 탐지와 요약을 맡고, 큰 모델이 리뷰와 정책, 계획을 담당한 뒤,
다시 작은 모델이 큰 모델의 감독 아래 반복 작업을 수행하는 계층형 운영에도
잘 맞습니다.

日本語:
速度が最重要ではないバックグラウンド作業に向いています。Docker ホストの
保守、Windows/Linux 管理、クリーンアップスクリプト、定期的なセキュリティ
確認、ログレビュー、侵入試行の確認、レポート作成などです。専用のセキュリティ
製品を置き換えるものではありませんが、管理者が反復作業をスクリプト化し、
読みやすいレポートにまとめる補助として使えます。

中文:
适合速度不是主要瓶颈的后台运维任务，例如 Docker 主机维护、Windows/Linux
管理、清理脚本、定期安全检查、日志审查、入侵尝试线索整理和报告草稿生成。
它不能替代专业安全工具，但可以帮助管理员把重复检查变成脚本和报告，同时
节省高级模型 token。

## Development Story

English:
The project evolved through real Claude Code sessions: provider switching,
model discovery, API-key prompts, compatibility checks, timeout handling,
web-search MCP wiring, and repeated tool-calling failures were all tested in the
terminal. The main integration lesson was that Anthropic-compatible Messages
endpoints are the cleanest path for Claude Code when providers expose them.
Ollama, vLLM, and NIM can provide Anthropic-compatible routes, so Claude Any
prefers those paths. Generic OpenAI-compatible chat endpoints were not used as
the primary integration layer because tool-call translation was less stable in
testing.
Local Qwen 3.6 27B Q4 runs were also tested through Ollama and vLLM on RTX 5090
and MSI GB10-class hardware. They worked, but this local setup should not be
measured directly against native Claude Code or Codex. Some hosted/cloud models
from NVIDIA NIM and Ollama Cloud felt more practical than expected for hybrid
background work.

한국어:
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

日本語:
Claude Any は、実用的な統合テストの積み重ねとして作られました。まず
プロバイダー切り替えを試し、続いてモデル検出、API キー入力、互換性テスト、
Web 検索ツール、タイムアウト処理、Claude Code のネイティブ動作を確認
しました。得られた重要な結論は、プロバイダーが Anthropic 互換 Messages
エンドポイントを提供する場合、その経路が最もきれいな統合方法だという
ことです。Ollama、vLLM、NIM は Anthropic 互換ルートを提供でき、この経路は
汎用 OpenAI 互換 chat ルートよりも Claude Code のツールモデルを保ちやすい
ものでした。
ローカル Ollama と vLLM では、RTX 5090 および MSI GB10 クラスの環境で Qwen
3.6 27B Q4 も試しました。動作はしましたが、速度は native Claude Code や
Codex と直接比較する種類のものではありませんでした。このハイブリッド用途では
NVIDIA NIM や Ollama Cloud の hosted/cloud モデルが予想以上に実用的でした。
OpenAI 互換エンドポイントは、Claude Code 用の主経路から意図的に外しました。
テストでは、generic OpenAI chat 互換層を通した tool-call 変換が、tool
parameter、tool result、反復呼び出し、retry、モデル選択の周辺でより不安定
でした。そのため Claude Any は native Anthropic 互換 endpoint を優先し、
provider-specific な変換が必要な場合だけ小さな router を使います。

中文:
Claude Any 是通过一系列实际集成测试构建出来的：先尝试供应商切换，然后验证
模型发现、API 密钥输入、兼容性测试、网页搜索工具、超时处理，以及 Claude
Code 的原生行为。最有用的结论是：当供应商提供 Anthropic 兼容 Messages 端点时，
这是最干净的集成路径。Ollama、vLLM 和 NIM 都可以提供 Anthropic 兼容路由，
这种路径比通用 OpenAI 兼容 chat 路由更能保留 Claude Code 的工具模型。
本地 Ollama 和 vLLM 也在 RTX 5090 与 MSI GB10 级硬件上测试过 Qwen 3.6 27B
Q4。它可以运行，但速度不应直接与 native Claude Code 或 Codex 比较。对于这类
混合后台工作，NVIDIA NIM 和 Ollama Cloud 的一些 hosted/cloud 模型反而比预期
更实用。
OpenAI 兼容端点被有意排除在 Claude Code 的主要路径之外。在测试中，通过
generic OpenAI chat 兼容层进行 tool-call 转换时，在 tool parameter、tool
result、重复调用、retry 和模型选择附近表现得更脆弱。因此 Claude Any 优先
使用 native Anthropic 兼容 endpoint，只在需要 provider-specific 适配时使用
一个小型 router。
