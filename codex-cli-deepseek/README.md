# Codex CLI + DeepSeek V4 — macOS 部署指南

让 [OpenAI Codex CLI](https://github.com/openai/codex) 使用 **DeepSeek V4 Flash / Pro** 作为后端模型，通过本地 API 翻译代理实现。

无需 OpenAI 账号，零网络限制，国内网络友好。

## 架构

```
codex (Responses API)
  │
  ▼
deepseek-proxy.js  ──HTTP──→  api.deepseek.com
(localhost:3333)               (Chat Completions API)
```

代理在本地 `:3333` 运行，将 Codex 的 Responses API 实时翻译为 DeepSeek 的 Chat Completions 格式，包括工具调用、流式输出、推理内容（thinking mode）。

## 前置条件

- macOS (arm64)
- Node.js ≥ 18
- Codex CLI: `npm install -g @openai/codex`
- [DeepSeek API Key](https://platform.deepseek.com/api-keys)

## 快速开始

### 1. 设置 API Key

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
```

建议写入 `~/.zshrc` 或 `~/.hermes/.env`：

```bash
echo 'export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"' >> ~/.zshrc
```

### 2. 启动代理

```bash
# 启动代理（前台）
node ~/codex-proxy/deepseek-proxy.js

# 或后台运行
nohup node ~/codex-proxy/deepseek-proxy.js > /tmp/codex-proxy.log 2>&1 &
```

### 3. 配置 Codex

写入 `~/.codex/config.toml`：

```toml
model_provider = "deepseek"
model          = "deepseek-v4-flash"
model_reasoning_effort = "medium"
model_catalog_json = "/path/to/deepseek-catalog.json"

[model_providers.deepseek]
name     = "DeepSeek (via proxy)"
base_url = "http://127.0.0.1:3333"
env_key  = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

### 4. 登录 + 验证

```bash
# 用你的 DeepSeek API Key 登录 Codex
echo "$DEEPSEEK_API_KEY" | codex login --with-api-key

# 测试
codex exec "say hello world"
```

预期输出：
```
model: deepseek-v4-flash
provider: deepseek
--------
hello world
```

## 文件清单

| 文件 | 用途 |
|:-----|:------|
| `deepseek-proxy.js` | API 翻译代理（核心） |
| `deepseek-catalog.json` | 模型目录（Codex 用来显示模型列表） |
| `codex-switch.sh` | macOS 一键启停脚本 |
| `codex-config.example.toml` | Codex 配置示例 |

## 使用脚本（推荐）

```bash
# 启动代理 + Codex
bash codex-switch.sh

# 查看状态
bash codex-switch.sh status

# 停止代理
bash codex-switch.sh --kill

# 调试模式（显示请求日志）
bash codex-switch.sh --debug
```

## 切换模型

在 Codex 会话内使用 `/model` 命令选择：
- `DeepSeek V4 Flash` — 日常编码（快速、经济）
- `DeepSeek V4 Pro` — 复杂任务（更强推理）

## 常见问题

### 代理启动失败

```bash
Error: DEEPSEEK_API_KEY not set.
```

确保 `DEEPSEEK_API_KEY` 环境变量已设置。

### Codex 报「认证失败」

```bash
echo "$DEEPSEEK_API_KEY" | codex login --with-api-key
```

### 流式输出卡住

检查代理日志中的错误信息，确认 DeepSeek API 可访问：

```bash
curl https://api.deepseek.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"stream":false}'
```
