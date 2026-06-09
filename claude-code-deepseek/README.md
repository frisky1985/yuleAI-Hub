# Claude Code + DeepSeek V4 配置方案

让 Claude Code 通过 DeepSeek V4 Flash 运行，完全绕过 Anthropic 账号和地域限制。

## 🎯 解决的问题

- ❌ Claude Code 在中国大陆提示"国家不能访问"
- ❌ 交互模式弹"需要登录 Anthropic 账号"
- ❌ API Error: Header '14' has invalid value
- ❌ Sub-agent 调用失败（使用了不存在的 Anthropic 模型）
- ❌ `api.anthropic.com` DNS 被墙导致超时/重试

## 🏗 架构

```
┌─────────┐     ┌──────────────┐     ┌─────────────┐
│ claude   │────▶│  CC Switch   │────▶│ DeepSeek API │  /v1/messages → 真实转发
│          │     │  127.0.0.1   │     └─────────────┘
│          │     │  :8787 HTTP  │     ┌─────────────┐
│          │     │  :443  HTTPS │────▶│ Mock 响应    │  /api/* → 假响应
└─────────┘     └──────────────┘     └─────────────┘
       │               ▲
       │   /etc/hosts   │
       └───────────────┘  api.anthropic.com → 127.0.0.1
```

## 📁 文件清单

| 文件 | 用途 |
|------|------|
| `assets/cc-switch.mjs` | 智能反向代理脚本 |
| `assets/ai.openclaw.cc-switch.plist` | macOS LaunchAgent 开机自启 |
| `assets/settings.json` | Claude Code 配置文件（放 `~/.claude/`） |
| `README.md` | 本文件 |

## 🚀 快速部署

### 前置条件

- Node.js ≥ 22
- DeepSeek API Key (`sk-e2e…`)
- macOS（Linux 用户请自行调整 LaunchAgent → systemd）

### 1. 安装代理脚本

```bash
mkdir -p ~/.openclaw/scripts ~/.openclaw/certs
cp assets/cc-switch.mjs ~/.openclaw/scripts/
chmod +x ~/.openclaw/scripts/cc-switch.mjs
```

### 2. DNS 劫持

```bash
sudo sh -c 'echo "127.0.0.1 api.anthropic.com" >> /etc/hosts'
```

### 3. sudoers 免密

```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/local/bin/node $HOME/.openclaw/scripts/cc-switch.mjs" | sudo tee /etc/sudoers.d/cc-switch
```

### 4. 开机自启

```bash
cp assets/ai.openclaw.cc-switch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/ai.openclaw.cc-switch.plist
```

### 5. Claude Code 配置

复制 `assets/settings.json` 到 `~/.claude/settings.json`，**替换 API Key**。

### 6. 环境变量

在 `~/.zshrc` 中添加：

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
export ANTHROPIC_API_KEY="sk-你的key"
export ANTHROPIC_MODEL="deepseek-v4-flash"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-flash"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-flash"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="32000"
export ANTHROPIC_ALWAYS_THINKING_ENABLED="false"
export NODE_TLS_REJECT_UNAUTHORIZED="0"
```

### 7. 预批准 API Key

首次运行后编辑 `~/.claude.json`，将 key hash 从 `rejected` 移到 `approved`：

```json
"customApiKeyResponses": {
  "approved": ["your-key-hash"],
  "rejected": []
}
```

### 8. 验证

```bash
source ~/.zshrc
echo "say hi" | claude -p --model deepseek-v4-flash  # 非交互
claude                                                    # 交互模式
```

## ⚙️ Mock 端点

代理不会把所有请求都发给 DeepSeek——Anthropic 的遥测/boot 端点会被 Mock 掉：

| 路径 | 行为 | 说明 |
|------|------|------|
| `/v1/messages` | → DeepSeek | 真实 LLM API |
| `/api/claude_cli/bootstrap` | Mock | Feature flags |
| `/api/claude_code_penguin_mode` | Mock | 企鹅模式 |
| `/api/eval/*` | Mock | SDK 遥测 |
| `/api/event_logging/*` | Mock | 事件日志 |
| `/mcp-registry/*` | Mock | MCP 注册表 |
| 其他 | Mock | 兜底 |

## 🔧 故障排查

| 症状 | 原因 | 修复 |
|------|------|------|
| Unable to connect to Anthropic | hosts 未劫持或代理未跑 | 检查 `/etc/hosts` + `lsof -i :443` |
| 提示需要登录 | key 在 rejected 列表 | 编辑 `~/.claude.json` |
| Header '14' invalid | 用了 AUTH_TOKEN | 改用 `ANTHROPIC_API_KEY` |
| Retry model attempt | api.anthropic.com 被墙 | 确保 hosts 劫持 + 443 代理 |
| Sub-agent 失败 | 模型铭文不对 | 检查 `CLAUDE_CODE_SUBAGENT_MODEL` |

## 📚 参考资料

- [腾讯云：Claude Code 接入 DeepSeek 完整指南](https://cloud.tencent.com/developer/article/2653743)
- [DeepSeek API Docs](https://api-docs.deepseek.com/)
- [Claude Code Docs](https://code.claude.com/docs)

## 📄 License

MIT — 欢迎 fork、改、分享。
