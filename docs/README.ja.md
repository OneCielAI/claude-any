# Claude Any

| [English](../README.md) | [한국어](README.ko.md) | 日本語 | [中文](README.zh.md) |
| --- | --- | --- | --- |

Claude Any は、Claude Code の起動前に Anthropic、Ollama、Ollama Cloud、
vLLM、NVIDIA hosted、self-hosted NIM を選択し、通常の Claude Code 引数を
そのまま渡すプロバイダー選択ランチャーです。

Credits: One Ciel LLC

現在のバージョン: `0.1.14`

## 作られた理由

Claude Code の最上位プランでも、長い作業ではトークンが不足したり、次の
クォータまで待つ必要があります。Claude Any は Claude Code を置き換える
ものではなく、作業を止めないための補助ツールです。NVIDIA NIM、Ollama
Cloud、vLLM、ローカル Ollama などを、要約、調査、ジャーナル、簡単な
コーディング、バックグラウンド作業に使えます。

プロバイダーが Anthropic 互換 Messages エンドポイントを提供する場合は、
その経路を優先して Claude Code のツール、権限、モデル選択、ワークフローを
できるだけ維持します。リモートプロバイダーが直接提供しにくい Web 検索は
別の MCP ツールで補完します。

起動前メニューはコンソールと SSH 作業を重視しています。Claude Code 起動前に
プロバイダー、モデル、Base URL、API キー、オプションを確認・変更できます。

macOS はまだ十分にテストしていませんが、portable Python と shell wrapper を
中心にしています。問題があれば知らせてください。

- D. Yun

## インストール

要件:

- Python 3.10+
- `claude` コマンドで実行できる Claude Code
- MCP Web ツールを使う場合のみ Node/npm

現在すぐに使える GitHub インストール:

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

ソースからインストール:

```sh
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
./install.sh
claude-any
```

Windows PowerShell でソースからインストール:

```powershell
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
.\install.ps1
claude-any
```

npm registry に初回 publish した後:

```sh
npm install -g @onecielai/claude-any
claude-any
```

アップグレード:

```sh
# GitHub インストール、現在の推奨経路
npm install -g https://github.com/OneCielAI/claude-any.git --force
claude-any version
```

`npm update -g @onecielai/claude-any` を動作させるには、同じ package 名で
public npm registry に publish されている必要があります。

```sh
npm login
npm publish --access public
npm install -g @onecielai/claude-any
npm update -g @onecielai/claude-any
```

自動公開を使う場合は、npm automation token を GitHub repository secret
`NPM_TOKEN` として保存し、GitHub Release を作成するか `Publish to npm`
workflow を手動実行します。

バージョン管理には SemVer を使います。次のリリースでは `package.json` の
`version` を更新し、`v0.1.1` のような同じバージョンの Git tag と GitHub
Release を作成すると npm publish workflow を実行できます。registry 公開後は
次のコマンドでアップグレードできます。

```sh
npm update -g @onecielai/claude-any
```


![Claude Any menu](assets/claude-any-main.ja.png)

## デモ

![Claude Any demo](assets/claude-any-demo.ja.gif)

現在のデモは、プロバイダー選択、Base URL、モデル選択、LLM オプション、
互換性テストの順に表示します。互換性テストは単純なテキスト応答だけでなく、
必須の `tool_use` と `tool_result` の往復も確認します。

| プロバイダー | Base URL | モデル | LLM オプション | 互換性 |
| --- | --- | --- | --- | --- |
| ![Provider](assets/claude-any-provider.ja.png) | ![Base URL](assets/claude-any-base-url.ja.png) | ![Model](assets/claude-any-model.ja.png) | ![Options](assets/claude-any-options.ja.png) | ![Test](assets/claude-any-test.ja.png) |

詳しい設定、headless フラグ、トラブルシューティングは [manual](manual.md) を
参照してください。デモ動画は [assets/claude-any-demo.ja.mp4](assets/claude-any-demo.ja.mp4)
にあります。

## 開発ストーリー

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

最近の vLLM テストでは、サーバー側の tool-call parser をモデル系列に合わせる
必要があることが分かりました。vLLM サーバーに接続でき、`/v1/messages` が
動作していても、`--tool-call-parser` が違うと Claude Code が tool call を
解析できず止まることがあります。Qwen3-Coder 系では `--enable-auto-tool-choice
--tool-call-parser qwen3_xml` を優先し、`hermes` は Hermes 形式のモデルや
一部の古い Qwen tool template 向けとして扱います。

## 推奨用途

速度が最重要ではないバックグラウンド運用に向いています。Docker ホスト管理、
Windows/Linux 管理、クリーンアップスクリプト、定期的なセキュリティ確認、
ログレビュー、Windows Event Log レビュー、ウイルス/ランサムウェア侵入試行
の整理、ブルートフォース試行の確認、レポート作成などです。

専用のセキュリティ製品を置き換えるものではありませんが、管理者が反復作業を
スクリプト化し、読みやすいレポートにまとめる補助として使えます。無料または
低コストのシステムセキュリティウォッチャーを作る用途にも向いています。

たとえば「Docker コンテナに PostgreSQL をインストールする」「今日の Docker
ログを分析してメールレポートにする」といった依頼を、コマンド、スクリプト、
スケジュールジョブ、要約にできます。

小さなモデルが検出と要約を行い、大きなモデルがレビュー、ポリシー、計画を
担当し、その後小さなモデルが監督下で反復作業を実行する階層型運用にも合います。

## 主な機能

- 英語、韓国語、日本語、中国語 UI の起動前メニュー。
- プロバイダー別モデル一覧とカスタムモデル入力。
- Claude Code チャット外での API キー設定。
- context window、output tokens、timeout、sampling、native compatibility の LLM オプション/プリセット。
- 起動前にテキスト、`tool_use`、`tool_result` を確認する互換性テスト。
- vLLM/NIM の `/v1/models` が `max_model_len` を返す場合は runtime context を表示。
- SSH とターミナル向けのコンソール優先 UI。
- Anthropic 互換エンドポイントがある場合は native 経路を優先。
- 必要に応じた provider-specific router。
- non-native provider 向け DuckDuckGo/fetch MCP。
- `--ca-provider`、`--ca-model`、`--ca-base-url` などの headless フラグ。
- Ollama/Ollama Cloud ルーター経路でのストリーミングプロキシ — トークンが届く
  すぐに Claude Code に転送し、レスポンス全体のバッファリングを待ちません。
- 設定ファイルキャッシュ — ルーターがリクエストごとにディスクから読み込んでいた
  設定をメモリにキャッシュし、ファイル変更時のみ再読み込みします。

## 変更履歴

### 0.1.13

- **Ollama ストリーミングプロキシ**: ルーターが Ollama/Ollama Cloud のレスポンスを Anthropic SSE 形式でリアルタイムにストリーミングするようになりました。レスポンス全体をバッファリングしてから転送する方式から、トークン生成と同時に転送する方式に変更されました。
- **設定キャッシュ**: `load_config()` が設定ファイルをメモリにキャッシュし、ファイル変更時刻が変わった時だけ再読み込みします。ルーターの全リクエストで発生していたディスク I/O と JSON パースの繰り返しを削減しました。
- **トークン推定キャッシュ**: `estimate_tokens()` がオプションのキャッシュ dict を受け取り、単一リクエスト内の重複 `json.dumps()` 呼び出しを回避します。`ollama_chat_request` と `cap_output_tokens_for_context` が同じキャッシュを共有します。

### 0.1.12

- ドキュメントとデモアセットの更新。

### 0.1.11

- ツール呼び出し互換性の検証。

### 0.1.10

- テストでのランタイムコンテキスト表示。

### 0.1.9

- サーバーコンテキストに合わせたプリセット上限。

### 0.1.8

- LLM プリセットのローカライズ。

## プロバイダーの注意点

| Provider | Mode | Notes |
| --- | --- | --- |
| Anthropic | Native Claude Code | Claude login または Anthropic API key を使用。 |
| Ollama | Native 優先、必要時 router | ローカル Ollama は通常 API key 不要。ローカル Ollama で `:cloud` model を使う場合は Ollama host で `ollama signin` が必要。 |
| Ollama Cloud | Router | `https://ollama.com/api` を直接呼び出し、Ollama API key が必要。 |
| vLLM | Native Anthropic-compatible endpoint | Anthropic 互換 `/v1/messages` endpoint を使い、モデル系列に合う `--tool-call-parser` を指定。 |
| NVIDIA hosted | Router/proxy | NVIDIA hosted API を compatibility 経路で使用。 |
| self-hosted NIM | Native Anthropic-compatible endpoint | self-hosted NIM の Anthropic 互換 endpoint を使用。 |

Qwen3-Coder を Claude Code 用に vLLM で起動する例:

```sh
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3-coder-30b \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

リンク:

- vLLM Claude Code integration: https://docs.vllm.ai/en/latest/serving/integrations/claude_code/
- vLLM tool calling: https://docs.vllm.ai/en/stable/features/tool_calling/

## ライセンス

MIT。詳細は [LICENSE](../LICENSE) を参照してください。
