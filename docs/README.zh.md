# Claude Any

| [English](../README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | 中文 |
| --- | --- | --- | --- |

Claude Any 是 Claude Code 的启动前供应商选择器。它可以在 Claude Code 启动前
选择 Anthropic、Ollama、Ollama Cloud、vLLM、NVIDIA hosted 或 self-hosted
NIM，并把普通 Claude Code 参数原样传递。

Credits: One Ciel LLC

当前版本: `0.1.17`

## 为什么存在

即使使用 Claude Code 的最高套餐，长时间工作时也可能遇到 token 不足，或者
必须等待下一轮额度才能继续会话。Claude Any 不是为了替代 Claude Code，而是
为了让工作不中断。NVIDIA NIM、Ollama Cloud、vLLM、本地 Ollama 等供应商可
用于摘要、调研、日志、简单编码和后台委派任务。

如果供应商提供 Anthropic 兼容 Messages 端点，Claude Any 会优先使用这条
路径，以尽量保留 Claude Code 的工具、权限、模型选择和工作流体验。远程供应商
无法直接提供的网页搜索能力，则通过独立 MCP 工具补充。

启动前菜单优先考虑控制台和 SSH 工作流。Claude Code 启动前，可以方便地查看
和修改供应商、模型、Base URL、API 密钥和选项。

macOS 尚未充分测试，但项目主要基于 portable Python 和 shell wrapper。如遇
问题请反馈。

- D. Yun

## 安装

要求:

- Python 3.10+
- 已安装 Claude Code，并可通过 `claude` 命令运行
- 只有启用 MCP 网页工具时才需要 Node/npm

当前可直接使用的 GitHub 安装:

```sh
npm install -g https://github.com/OneCielAI/claude-any.git
claude-any
```

源码安装:

```sh
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
./install.sh
claude-any
```

Windows PowerShell 源码安装:

```powershell
git clone https://github.com/OneCielAI/claude-any.git
cd claude-any
.\install.ps1
claude-any
```

首次发布到 npm registry 后安装:

```sh
npm install -g @onecielai/claude-any
claude-any
```

升级:

```sh
# GitHub 安装，当前推荐方式
npm install -g https://github.com/OneCielAI/claude-any.git --force
claude-any version
```

要让 `npm update -g @onecielai/claude-any` 正常工作，必须先用同一个 package
name 发布到 public npm registry。

```sh
npm login
npm publish --access public
npm install -g @onecielai/claude-any
npm update -g @onecielai/claude-any
```

如果使用自动发布，请创建 npm automation token，将它保存为 GitHub repository
secret `NPM_TOKEN`，然后发布 GitHub Release 或手动运行 `Publish to npm`
workflow。

版本使用 SemVer。后续发布时，更新 `package.json` 中的 `version`，创建相同
版本的 Git tag，例如 `v0.1.1`，再发布 GitHub Release 即可触发 npm publish
workflow。发布到 registry 之后，可以使用以下命令升级。

```sh
npm update -g @onecielai/claude-any
```


![Claude Any menu](assets/claude-any-main.zh.png)

## 演示

![Claude Any demo](assets/claude-any-demo.zh.gif)

当前演示展示供应商选择、Base URL、模型选择、LLM 选项和兼容性测试。兼容性
测试不仅检查普通文本响应，还会检查必需的 `tool_use` 和 `tool_result` 往返。

| 供应商 | Base URL | 模型 | LLM 选项 | 兼容性 |
| --- | --- | --- | --- | --- |
| ![Provider](assets/claude-any-provider.zh.png) | ![Base URL](assets/claude-any-base-url.zh.png) | ![Model](assets/claude-any-model.zh.png) | ![Options](assets/claude-any-options.zh.png) | ![Test](assets/claude-any-test.zh.png) |

详细设置、headless 参数和故障排查请看 [manual](manual.md)。演示视频位于
[assets/claude-any-demo.zh.mp4](assets/claude-any-demo.zh.mp4)。

## 开发故事

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

最近的 vLLM 测试说明，服务器端 tool-call parser 必须和模型系列匹配。即使
vLLM 服务器可连接、`/v1/messages` 可用，只要 `--tool-call-parser` 不匹配，
Claude Code 也可能无法解析 tool call 并停止。Qwen3-Coder 系列优先使用
`--enable-auto-tool-choice --tool-call-parser qwen3_xml`；`hermes` 更适合
Hermes 格式模型或部分较旧的 Qwen tool template。

## 推荐用途

适合速度不是主要瓶颈的后台运维任务，例如 Docker 主机维护、Windows/Linux
管理、清理脚本、定期安全检查、日志审查、Windows Event Log 审查、病毒或
勒索软件入侵尝试整理、暴力登录尝试审查和报告草稿生成。

它不能替代专业安全产品，但可以帮助管理员把重复检查变成脚本和可读报告。用
这种方式可以构建免费或低成本的系统安全看护助手。

例如，可以把“在 Docker 容器中安装 PostgreSQL”或“分析今天的 Docker 日志并
通过邮件发送报告”这样的请求转成具体命令、脚本、计划任务和摘要。

一种实用模式是分层监督：小模型负责检测和摘要，大模型负责审核、策略和计划，
然后小模型在大模型监督下执行重复任务。

## 主要功能

- 英语、韩语、日语、中文 UI 的启动前菜单。
- 按供应商列出模型，并支持自定义模型输入。
- 在 Claude Code 聊天输入之外设置 API 密钥。
- LLM 选项/预设，可配置 context window、output tokens、timeout、sampling 和 native compatibility。
- 启动前文本、`tool_use`、`tool_result` 兼容性测试。
- 当 vLLM/NIM 的 `/v1/models` 返回 `max_model_len` 时显示运行时上下文。
- 面向 SSH 和终端的控制台优先 UI。
- 有 Anthropic 兼容端点时优先使用 native 路径。
- 必要时使用 provider-specific router。
- 为 non-native provider 连接 DuckDuckGo/fetch MCP。
- 支持 `--ca-provider`、`--ca-model`、`--ca-base-url` 等 headless 参数。
- Ollama/Ollama Cloud 路由路径的流式代理 — token 到达后立即转发给 Claude Code，
  不再等待完整响应。
- 配置文件缓存 — 路由器将设置缓存到内存，仅在文件修改时重新读取，
  减少了每次请求的磁盘 I/O 开销。

## 更新日志

### 0.1.17

- **菜单兼容性测试超时**: 终端菜单现在以明确的 180 秒限制运行兼容性测试，并在超过 hard limit 时停止子进程，避免较慢的 hosted model 让菜单看起来无限等待。

### 0.1.16

- **NVIDIA hosted proxy 启动修复**: 在 fallback 到 `python -m nvd_claude_proxy.main` 之前，先检测并启动已安装的 `nvd-claude-proxy`/`ncp` 可执行文件。支持 proxy 通过 uv tool 安装、命令可用但无法从 Claude Any 的 Python 解释器 import 的环境。

### 0.1.15

- **Ollama/Ollama Cloud 工具调用流式修复**: 流式工具调用现在使用连续的 Anthropic SSE content block index 和 `input_json_delta` payload 输出，避免 Claude Code 将 malformed streamed tool-use block 拒绝为 `Invalid tool parameters`。
- **Tool guard 自动安装**: 非 Anthropic provider 启动时会将 Claude Any tool guard 合并到 `~/.claude/settings.json`，在执行前规范化生成的工具输入。
- **工具调用诊断日志**: 路由器侧工具调用记录到 `~/.config/claude-any/tool-calls.jsonl`，Claude Code hook 输入记录到 `~/.claude/claude-any-tool-guard/tool-events.jsonl`。
- **工具输入规范化**: guard 会将 `path` 映射为 `file_path`、`cmd` 映射为 `command`、`query` 映射为 `pattern`，并在缺少必填字段时返回明确提示。

### 0.1.14

- **SSH/终端方向键兼容性**: 重写 `read_menu_key()`，加入 ANSI escape sequence 解析器，并将 raw 终端设置移至 `portable_select()`，使菜单循环期间终端始终维持 raw 模式。解决按键间隙 `ECHO` 恢复导致转义序列泄漏到屏幕的问题。方向键、Home、End 键现可在 SSH 会话中稳定工作。
- **测试超时**: 将兼容性测试默认超时从 60 秒延长至 120 秒，以适配较慢的云供应商。
- **Ollama Cloud 兼容性测试修复**: 在兼容性测试请求中添加 `"stream": false`，使路由器向 Ollama Cloud 请求单个 JSON 响应而非 SSE 流式传输，从而解决 `post_json` 在收集所有 SSE 分片时超时的问题。

### 0.1.13

- **Ollama 流式代理**: 路由器现在以 Anthropic SSE 格式实时流式传输 Ollama/Ollama Cloud 响应，替代了之前缓冲完整响应再转发的方式。
- **配置缓存**: `load_config()` 将配置文件缓存到内存，仅在文件修改时间变化时重新读取。消除了路由器每个请求中重复的磁盘读取和 JSON 解析。
- **Token 估算缓存**: `estimate_tokens()` 接受可选的缓存字典，避免单个请求中的冗余 `json.dumps()` 调用。`ollama_chat_request` 和 `cap_output_tokens_for_context` 共享同一缓存。

### 0.1.12

- 刷新文档和演示素材。

### 0.1.11

- 验证工具调用兼容性。

### 0.1.10

- 在测试中显示运行时上下文。

### 0.1.9

- 将预设上限限制到服务器上下文。

### 0.1.8

- 本地化 LLM 预设。

## 供应商说明

| Provider | Mode | Notes |
| --- | --- | --- |
| Anthropic | Native Claude Code | 使用 Claude 登录或 Anthropic API key。 |
| Ollama | Native 优先，必要时 router | 本地 Ollama 通常不需要 API key；通过本地 Ollama 使用 `:cloud` 模型时，需要在 Ollama host 上 `ollama signin`。 |
| Ollama Cloud | Router | 直接调用 `https://ollama.com/api`，需要 Ollama API key。 |
| vLLM | Native Anthropic-compatible endpoint | 使用 Anthropic 兼容 `/v1/messages` endpoint，并让 `--tool-call-parser` 匹配模型系列。 |
| NVIDIA hosted | Router/proxy | 通过 compatibility 路径使用 NVIDIA hosted API。 |
| self-hosted NIM | Native Anthropic-compatible endpoint | 使用 self-hosted NIM 的 Anthropic 兼容 endpoint。 |

为 Claude Code 启动 Qwen3-Coder vLLM 的示例:

```sh
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3-coder-30b \
  --max-model-len 65536 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

链接:

- vLLM Claude Code integration: https://docs.vllm.ai/en/latest/serving/integrations/claude_code/
- vLLM tool calling: https://docs.vllm.ai/en/stable/features/tool_calling/

## 许可证

MIT。请参阅 [LICENSE](../LICENSE)。
