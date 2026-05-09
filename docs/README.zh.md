# Claude Any

| [English](../README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | 中文 |
| --- | --- | --- | --- |

Claude Any 是 Claude Code 的启动前供应商选择器。它可以在 Claude Code 启动前
选择 Anthropic、Ollama、Ollama Cloud、vLLM、NVIDIA hosted 或 self-hosted
NIM，并把普通 Claude Code 参数原样传递。

Credits: One Ciel LLC

当前版本: `0.1.8`

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
- 启动前兼容性测试。
- 面向 SSH 和终端的控制台优先 UI。
- 有 Anthropic 兼容端点时优先使用 native 路径。
- 必要时使用 provider-specific router。
- 为 non-native provider 连接 DuckDuckGo/fetch MCP。
- 支持 `--ca-provider`、`--ca-model`、`--ca-base-url` 等 headless 参数。

## 许可证

MIT。请参阅 [LICENSE](../LICENSE)。
