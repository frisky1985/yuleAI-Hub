# DeepSeek Codex & Claude CLI 配置指南

> 让你的 Codex CLI 和 Claude Code CLI 都跑在 DeepSeek 模型上，零 Anthropic 登录依赖。

---

## 目录

1. [概述](#概述)
2. [前置条件](#前置条件)
3. [Codex CLI 配置](#codex-cli-配置)
   - [架构](#codex-架构)
   - [安装步骤](#codex-安装步骤)
   - [使用方式](#codex-使用方式)
4. [Claude Code CLI 配置](#claude-code-cli-配置)
   - [原理](#claude-原理)
   - [安装步骤](#claude-安装步骤)
   - [使用方式](#claude-使用方式)
5. [常见问题](#常见问题)
6. [文件清单](#文件清单)

---

## 概述

| CLI | 协议 | DeepSeek 端点 | 需代理 |
|-----|------|-------------|--------|
| **Codex CLI** (v0.137+) | OpenAI Responses API (`/v1/responses`) | `https://api.deepseek.com/v1/chat/completions` | ✅ 本地代理 (port 8787) |
| **Claude Code CLI** (v2.1+) | Anthropic Messages API (`/v1/messages`) | `https://api.deepseek.com/anthropic` | ❌ 直连 |

- **Codex** 需要本地代理转换 Responses API ↔ Chat Completions
- **Claude** 可以直接通过 DeepSeek 的 Anthropic 兼容端点连接

---

## 前置条件

- macOS (本指南以 macOS 为例)
- **Node.js 18+**（用于安装 Codex CLI 和 Claude Code CLI）
- **Python 3.9+ + aiohttp**（用于 Codex 本地代理）
- **DeepSeek API Key**（到 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 申请）

---

## Codex CLI 配置

### Codex 架构

```
┌─────────────┐     Responses API      ┌──────────────┐     Chat Completions     ┌──────────────┐
│  Codex CLI  │ ──── /v1/responses ──▶ │  本地代理      │ ──── /chat/completions ──▶ │  DeepSeek    │
│             │ ◀───────────────────── │  port 8787   │ ◀─────────────────────── │  API         │
└─────────────┘                        └──────────────┘                          └──────────────┘
```

转换内容：
- 请求体字段映射（`input` → `messages`, `instructions` → `system` 等）
- 工具类型重写（`shell_command` → `function`）
- 角色映射（`developer` → `system`）
- SSE 流式事件转换

### Codex 安装步骤

#### 1. 安装 Codex CLI

```bash
npm install -g @openai/codex
codex --version  # 确认版本 ≥ 0.137.0
```

#### 2. 安装 Python 依赖

```bash
pip3 install aiohttp
```

#### 3. 配置本地代理

创建 `~/.codex/deepseek-proxy.py`（见 [proxy 源码](#proxy-源码)）。

创建启动脚本 `~/.codex/start-proxy.sh`：

```bash
#!/bin/bash
PIDFILE="/tmp/deepseek-proxy.pid"
PROXY_SCRIPT="$HOME/.codex/deepseek-proxy.py"
PYTHON="/opt/homebrew/bin/python3"  # macOS Homebrew Python

start() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Proxy already running (PID $(cat "$PIDFILE"))"
        return
    fi
    nohup "$PYTHON" "$PROXY_SCRIPT" > /tmp/deepseek-proxy.log 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Proxy started (PID $(cat "$PIDFILE"))"
    else
        echo "Failed to start proxy"
    fi
}

stop() {
    if [ -f "$PIDFILE" ]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null
        rm -f "$PIDFILE"
        echo "Proxy stopped"
    fi
}

status() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Proxy running (PID $(cat "$PIDFILE"))"
    else
        echo "Proxy not running"
    fi
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|status}" ;;
esac
```

```bash
chmod +x ~/.codex/start-proxy.sh
```

#### 4. 创建 Codex 配置文件

`~/.codex/config.toml`（默认模型，deepseek-v4-flash）：

```toml
model = "deepseek-v4-flash"
model_provider = "deepseek"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "http://localhost:8787/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

`~/.codex/reasoner.config.toml`（推理模型，deepseek-v4-pro，搭配 `--profile reasoner`）：

```toml
model = "deepseek-v4-pro"
model_provider = "deepseek"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "http://localhost:8787/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

#### 5. 存储 API Key

`~/.codex/auth.json`：

```json
{
  "auth_mode": "apikey",
  "DEEPSEEK_API_KEY": "sk-your-deepseek-api-key"
}
```

> 代理会自动从 `auth.json` 读取 API Key，不需要额外环境变量。

#### 6. 添加环境变量和 Shell 函数

添加到 `~/.zshrc`：

```bash
# DeepSeek API Key
export DEEPSEEK_API_KEY="sk-your-deepseek-api-key"

# Codex CLI: 自动启动代理
codex() {
    if ! pgrep -f "deepseek-proxy.py" > /dev/null 2>&1; then
        ~/.codex/start-proxy.sh start
    fi
    command codex "$@"
}
```

#### 7. （可选）开机自启 LaunchAgent

`~/Library/LaunchAgents/com.deepseek.codex-proxy.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.deepseek.codex-proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Users/你的用户名/.codex/deepseek-proxy.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/deepseek-proxy.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/deepseek-proxy.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.deepseek.codex-proxy.plist
```

### Codex 使用方式

```bash
codex                              # 默认: deepseek-v4-flash
codex --profile reasoner           # 推理: deepseek-v4-pro
codex exec -                       # 非交互模式（管道输入）
```

### 验证

```bash
# 代理健康检查
curl http://localhost:8787/health

# 测试 API 转换
curl -X POST http://localhost:8787/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","input":"say hello","max_output_tokens":20}'
```

---

## Claude Code CLI 配置

### Claude 原理

DeepSeek 提供了 **原生 Anthropic API 兼容端点**：

```
POST https://api.deepseek.com/anthropic/v1/messages
```

所以 Claude Code 可以直连，不需要本地代理。关键是用 `ANTHROPIC_AUTH_TOKEN` 而非 `ANTHROPIC_API_KEY` 来绕过 Anthropic 登录检查。

### Claude 安装步骤

#### 1. 安装 Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
claude --version  # 确认安装成功
```

#### 2. 配置环境变量

添加到 `~/.zshrc`：

```bash
# Claude Code → DeepSeek（官方集成方式）
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="sk-your-deepseek-api-key"    # 注意！用 AUTH_TOKEN 不是 API_KEY
export ANTHROPIC_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_EFFORT_LEVEL="max"
```

> **关键**：`ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_API_KEY` 是两个不同的变量！
> - `ANTHROPIC_API_KEY` → 会触发 Anthropic 本地登录检查 → ❌ "Not logged in"
> - `ANTHROPIC_AUTH_TOKEN` → 绕过登录，直接透传给 DeepSeek → ✅ 完美运行

### Claude 使用方式

```bash
claude                             # 交互模式
echo 'say "hello"' | claude -p     # 非交互模式（-p = print）
```

### 验证

```bash
echo 'say "hello from deepseek"' | claude -p
# 预期输出: Hello from DeepSeek
```

---

## 常见问题

### Codex 相关问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `Missing environment variable: DEEPSEEK_API_KEY` | 环境变量未设置或设置了错误的变量名 | 代理已改为从 `~/.codex/auth.json` 读取 key，不需要环境变量 |
| `Model metadata for deepseek-v4-flash not found` | `/v1/models` 缺少 `context_window` 元数据 | 代理返回的模型列表已包含元数据 |
| `We're currently experiencing high demand` | DeepSeek 服务器限流 | 等几分钟重试，不是配置问题 |
| `Address already in use: port 8787` | 代理已运行或端口被占用 | `lsof -i :8787` 查看占用进程 |

### Claude 相关问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `Not logged in · Please run /login` | 用了 `ANTHROPIC_API_KEY` 而非 `ANTHROPIC_AUTH_TOKEN` | 改用 `ANTHROPIC_AUTH_TOKEN` |
| `Failed to authenticate` | API Key 无效或已过期 | 检查 key 是否有效 |
| `We're currently experiencing high demand` | DeepSeek 服务器限流 | 等几分钟重试 |

---

## 文件清单

```
~/.codex/
├── deepseek-proxy.py          # Codex → DeepSeek 本地代理 (Response → Chat 格式转换)
├── start-proxy.sh             # 代理启停脚本
├── config.toml                # Codex 默认配置 (flash 模型)
├── reasoner.config.toml       # Codex 推理配置 (pro 模型)
├── auth.json                  # API Key 存储

~/Library/LaunchAgents/
└── com.deepseek.codex-proxy.plist   # 开机自启

~/.zshrc                       # 环境变量 + Shell 函数
```

---

## 参考

- [DeepSeek API 文档 - Claude Code 集成指南](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code)
- [DeepSeek API 文档 - Anthropic API](https://api-docs.deepseek.com/guides/anthropic_api)
- [OpenAI Codex CLI](https://github.com/openai/codex)
- [Anthropic Claude Code](https://github.com/anthropics/claude-code)
