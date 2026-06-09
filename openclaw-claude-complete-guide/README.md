# OpenClaw + Claude Code 完整配置指南

> 一次搞定 Claude Code（DeepSeek 后端）+ OpenClaw 三 Agent（小明/小克/小马）全链路配置

## 目录

1. [Claude Code 接入 DeepSeek](#1-claude-code-接入-deepseek)
2. [Memory 索引修复（Ollama）](#2-memory-索引修复ollama)
3. [OpenClaw 子 Agent 模型配置](#3-openclaw-子-agent-模型配置)
4. [环境变量隔离（防子 Agent 串线）](#4-环境变量隔离防子-agent-串线)
5. [完整的配置文件清单](#5-完整的配置文件清单)
6. [故障排查速查表](#6-故障排查速查表)

---

## 1. Claude Code 接入 DeepSeek

### 问题

Claude Code 在中国大陆使用时报错：
- `Unable to connect to Anthropic services`
- `Failed to connect to api.anthropic.com: ERR_BAD_REQUEST`
- 交互模式弹"需要登录 Anthropic 账号"

### 根因分析

1. **`api.anthropic.com` 被墙** — 这个域名在中国大陆 DNS 被污染，导致 Claude Code 的遥测/boot/feature flags 等辅助请求全部超时
2. **Claude Code 交互模式需要登录 OAuth** — 即使配置了 API Key，也要求"批准"一次，涉及连接 Anthropic 认证服务器
3. **DeepSeek Anthropic 端点不兼容 `AUTH_TOKEN`** — `ANTHROPIC_AUTH_TOKEN` 发送的 `Authorization: Bearer` 头会触发 Header 解析错误，必须用 `ANTHROPIC_API_KEY`（`x-api-key` 头）
4. **模型名冲突** — Claude Code 内置了 `claude-opus/sonnet/haiku` 模型名，DeepSeek 不认识，需要用 `ANTHROPIC_DEFAULT_*_MODEL` 全部映射到 `deepseek-v4-flash`

### 方案架构

```
claude 命令
  ├─ /v1/messages → CC Switch 代理 → DeepSeek API (真实转发)
  ├─ /api/bootstrap → CC Switch → Mock {flags:{},settings:{}}
  ├─ /api/event_logging → CC Switch → Mock {ok:true}
  ├─ /api/eval/* → CC Switch → Mock {status:"ok"}
  ├─ /mcp-registry/* → CC Switch → Mock {servers:[]}
  └─ api.anthropic.com → /etc/hosts DNS劫持 → 127.0.0.1:443 → CC Switch
```

### 部署清单

#### 1.1 CC Switch 代理脚本

`~/.openclaw/scripts/cc-switch.mjs`

```javascript
#!/usr/bin/env node
// CC Switch — Claude Code → DeepSeek 智能代理
// /v1/* → DeepSeek | 其他 → Mock

import http from "node:http";
import https from "node:https";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const TARGET = "api.deepseek.com";
const PREFIX = "/anthropic";
const CERT_DIR = path.join(import.meta.dirname, "..", "certs");

function ensureCerts() {
  fs.mkdirSync(CERT_DIR, { recursive: true });
  const k = path.join(CERT_DIR, "key.pem");
  const c = path.join(CERT_DIR, "crt.pem");
  if (!fs.existsSync(k)) {
    execSync(`openssl req -x509 -newkey rsa:2048 -keyout "${k}" -out "${c}" -days 3650 -nodes -subj "/CN=localhost"`, { stdio: "pipe" });
  }
  return { key: fs.readFileSync(k), cert: fs.readFileSync(c) };
}

const MOCK_OK = JSON.stringify({ ok: true });
const MOCK_BOOTSTRAP = JSON.stringify({ flags: {}, settings: {}, endpoint: "https://api.anthropic.com" });

function handle(clientReq, clientRes) {
  const { method, url } = clientReq;
  const h = { ...clientReq.headers }; delete h.host;

  if (method === "OPTIONS") {
    clientRes.writeHead(204, { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" });
    return clientRes.end();
  }

  if (url.startsWith("/v1/")) {
    console.log(`→ ${method} ${url} → DeepSeek`);
    const upstream = https.request(
      { hostname: TARGET, port: 443, path: PREFIX + url, method, headers: { ...h, host: TARGET } },
      (up) => {
        const rh = {};
        for (const [k, v] of Object.entries(up.headers))
          if (!["transfer-encoding","connection","keep-alive"].includes(k.toLowerCase())) rh[k] = v;
        rh["access-control-allow-origin"] = "*";
        clientRes.writeHead(up.statusCode, rh);
        up.pipe(clientRes);
      }
    );
    upstream.on("error", () => { if (!clientRes.headersSent) clientRes.writeHead(502); clientRes.end(); });
    return clientReq.pipe(upstream);
  }

  // Mock 端点
  console.log(`Ⓜ ${method} ${url} → mock`);
  clientRes.writeHead(200, { "content-type": "application/json", "access-control-allow-origin": "*" });
  if (url.startsWith("/api/claude_cli/bootstrap")) return clientRes.end(MOCK_BOOTSTRAP);
  if (url.startsWith("/api/claude_code_penguin_mode")) return clientRes.end(JSON.stringify({ enabled: false }));
  if (url.startsWith("/api/eval/")) return clientRes.end(JSON.stringify({ status: "ok" }));
  if (url.startsWith("/api/event_logging")) return clientRes.end(MOCK_OK);
  if (url.includes("mcp-registry")) return clientRes.end(JSON.stringify({ servers: [] }));
  if (url === "/api/hello") return clientRes.end(JSON.stringify({ message: "hello" }));
  clientRes.end(MOCK_OK);
}

const handler = (req, res) => { try { handle(req, res); } catch { if (!res.headersSent) res.writeHead(500); res.end(); } };

// HTTP (8787) — ANTHROPIC_BASE_URL
const httpSrv = http.createServer(handler);
httpSrv.on("error", (e) => { if (e.code !== "EADDRINUSE") throw e; });
httpSrv.listen(8787, "127.0.0.1", () => console.log("🔥 CC Switch HTTP → :8787"));

// HTTPS (443) — api.anthropic.com DNS 劫持
try {
  const { key, cert } = ensureCerts();
  const httpsSrv = https.createServer({ key, cert }, handler);
  httpsSrv.on("error", (e) => { if (e.code !== "EADDRINUSE") console.error(e.message); });
  httpsSrv.listen(443, "127.0.0.1", () => console.log("🔥 CC Switch HTTPS → :443"));
} catch (e) { console.error("HTTPS 不可用:", e.message); }
```

#### 1.2 DNS 劫持

```bash
sudo sh -c 'echo "127.0.0.1 api.anthropic.com" >> /etc/hosts'
```

#### 1.3 sudoers 免密

```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/l…node $HOME/.openclaw/scripts/cc-switch.mjs" | sudo tee /etc/sudoers.d/cc-switch
```

#### 1.4 LaunchAgent 开机自启

`~/Library/LaunchAgents/ai.openclaw.cc-switch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.openclaw.cc-switch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>exec sudo /usr/local/bin/node $HOME/.openclaw/scripts/cc-switch.mjs</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/cc-switch.log</string>
    <key>StandardErrorPath</key><string>/tmp/cc-switch.err</string>
</dict>
</plist>
```

#### 1.5 Claude Code 配置

`~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "sk-你的DeepSeek-Key",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787",
    "ANTHROPIC_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
    "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-v4-flash",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000"
  },
  "alwaysThinkingEnabled": false
}
```

#### 1.6 Shell Wrapper + API Key 自动审批

将以下代码添加到 `~/.zshrc`:

```bash
# Claude Code via DeepSeek (CC Switch 本地代理) — 变量收在 wrapper 内

claude() {
  # 专属环境变量（不在全局暴露，防止子 agent 继承）
  export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
  export ANTHROPIC_API_KEY="sk-你的Key"
  export ANTHROPIC_MODEL="deepseek-v4-flash"
  export ANTHROPIC_SMALL_FAST_MODEL="deepseek-v4-flash"
  export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-flash"
  export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-flash"
  export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
  export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
  export CLAUDE_CODE_MAX_OUTPUT_TOKENS="32000"
  export ANTHROPIC_ALWAYS_THINKING_ENABLED="false"
  export NODE_TLS_REJECT_UNAUTHORIZED="0"

  # 自动拉起代理
  if ! curl -sk --max-time 1 -o /dev/null https://127.0.0.1:443/health 2>/dev/null; then
    echo "🔥 CC Switch 代理启动中..."
    launchctl load ~/Library/LaunchAgents/ai.openclaw.cc-switch.plist 2>/dev/null || true
    launchctl kickstart -k gui/$(id -u)/ai.openclaw.cc-switch 2>/dev/null || \
      sudo nohup node $HOME/.openclaw/scripts/cc-switch.mjs > /tmp/cc-switch.log 2>&1 &
    sleep 1.5
  fi

  # 自动修复 API key 审批（Claude Code 重启后会重新验证并踢到 rejected）
  python3 -c "
import json
with open('$HOME/.claude.json') as f: d=json.load(f)
r=d['customApiKeyResponses']
for k in list(r.get('rejected',[])): r.setdefault('approved',[]).append(k); r['rejected'].remove(k)
if r.get('approved'):
    with open('$HOME/.claude.json','w') as f: json.dump(d,f,indent=2)
" 2>/dev/null

  command claude "$@"
}
```

#### 1.7 Mock 端点速查

| 路径 | 行为 | 说明 |
|------|------|------|
| `/v1/messages` | → DeepSeek | 真实 LLM API |
| `/api/claude_cli/bootstrap` | Mock `{flags:{},settings:{}}` | Feature flags |
| `/api/claude_code_penguin_mode` | Mock `{enabled:false}` | 企鹅模式 |
| `/api/eval/*` | Mock `{status:"ok"}` | SDK 遥测 |
| `/api/event_logging/*` | Mock `{ok:true}` | 事件日志 |
| `/mcp-registry/*` | Mock `{servers:[]}` | MCP 注册表 |
| 其他 | Mock `{ok:true}` | 兜底 |

---

## 2. Memory 索引修复（Ollama）

### 问题

`memory_search` 不可用，报错：

```
memory index was built for model fts-only but config expects text-embedding-3-small
```

且 OpenAI API Key 缺失，无法使用默认的 `openai` 嵌入提供商。

### 方案

DeepSeek 没有 Embedding API。使用本地 **Ollama** + `nomic-embed-text`（274MB，免费）。

#### 2.1 安装 Ollama 模型

```bash
ollama pull nomic-embed-text
```

#### 2.2 OpenClaw 配置

在 `~/.openclaw/openclaw.json` 的 `agents.defaults` 中添加：

```json
"memorySearch": {
  "provider": "ollama",
  "model": "nomic-embed-text"
}
```

#### 2.3 重建索引

```bash
openclaw memory index --force --agent main
openclaw memory index --force --agent claude-agent
openclaw memory index --force --agent hermes-agent
```

---

## 3. OpenClaw 子 Agent 模型配置

### 问题

三个 Agent（main / claude-agent / hermes-agent）的 `auth-profiles.json` 中只有 main 配置了 DeepSeek API Key，另外两个是空的 `{}`。

### 方案

统一为所有 Agent 配置 DeepSeek 认证：

**`~/.openclaw/agents/claude-agent/agent/auth-profiles.json`** 和 **`~/.openclaw/agents/hermes-agent/agent/auth-profiles.json`**:

```json
{
  "version": 1,
  "profiles": {
    "deepseek:default": {
      "type": "api_key",
      "provider": "deepseek",
      "key": "sk-你的DeepSeek-API-Key"
    }
  }
}
```

**`~/.openclaw/openclaw.json`** 中的 agent 模型配置：

```json
"list": [
  {
    "id": "main"
  },
  {
    "id": "claude-agent",
    "name": "小克 👨‍💻",
    "model": "deepseek/deepseek-v4-flash"
  },
  {
    "id": "hermes-agent",
    "name": "小马 🐴",
    "model": "deepseek/deepseek-v4-flash"
  }
]
```

### 三人小队配置总览

| Agent | 角色 | 模型 | 认证 | API 端点 |
|-------|------|------|------|----------|
| 小明（main） | 项目经理 | `deepseek-v4-flash` | ✅ 35字符 key | `api.deepseek.com` |
| 小克 👨‍💻 | 编码/架构 | `deepseek-v4-flash` | ✅ 35字符 key | `api.deepseek.com` |
| 小马 🐴 | 质量架构师 | `deepseek-v4-flash` | ✅ 35字符 key | `api.deepseek.com` |

---

## 4. 环境变量隔离（防子 Agent 串线）

### ⚠️ 关键问题

`ANTHROPIC_BASE_URL` 等变量如果是**全局 export**，OpenClaw 子 Agent（hermes/claude）启动时会继承 shell 环境，导致它们也走 CC Switch 代理（Anthropic 格式），模型名 `deepseek/deepseek-v4-flash` 被直接传给 DeepSeek API 报 400：

```
Error: HTTP 400: The supported API model names are deepseek-v4-pro or deepseek-v4-flash,
but you passed deepseek/deepseek-v4-flash.
```

### 修复原则

```
❌ 全局 export ANTHROPIC_BASE_URL=...   → 子 Agent 继承，走代理出错
✅ claude() { export ANTHROPIC_BASE_URL=...; ... }  → 只在 claude 内生效
```

所有 `ANTHROPIC_*`、`CLAUDE_CODE_*` 变量**必须**收进 `claude()` shell wrapper 函数内，不能在 `.zshrc` 全局作用域 export。

### `NODE_TLS_REJECT_UNAUTHORIZED`

这个变量虽然不影响子 Agent，但也建议放在 wrapper 内或注释掉全局 export，保持全局环境干净。

### 启动前清理残留

如果终端还残留旧的 env vars（从变更前继承），需要：

```bash
# 清理当前 shell 残留
unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_MODEL \
      ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL \
      ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL \
      CLAUDE_CODE_MAX_OUTPUT_TOKENS ANTHROPIC_ALWAYS_THINKING_ENABLED

# 重启 Gateway
openclaw gateway restart

# 或直接开新终端、重新登录
```

---

## 5. 完整的配置文件清单

| 文件路径 | 用途 | 注意 |
|----------|------|------|
| `~/.openclaw/scripts/cc-switch.mjs` | CC Switch 代理脚本 | 双端口 + Mock 路由 |
| `~/Library/LaunchAgents/ai.openclaw.cc-switch.plist` | 代理开机自启 | KeepAlive + sudo |
| `/etc/sudoers.d/cc-switch` | sudo 免密 | 只允许 node 运行代理 |
| `/etc/hosts` | api.anthropic.com DNS 劫持 | `127.0.0.1 api.anthropic.com` |
| `~/.claude/settings.json` | Claude Code 模型别名 + 禁用 thinking | API Key 在此填写 |
| `~/.claude.json` | Claude Code 状态（API key 审批） | wrapper 自动维护 |
| `~/.zshrc` | claude() wrapper 函数 | **不在全局 export ANTHROPIC_*** |
| `~/.openclaw/openclaw.json` | OpenClaw 主配置 | memorySearch + agent 模型 |
| `~/.openclaw/agents/*/agent/auth-profiles.json` | 子 Agent 认证 | main/claude/hermes 都要配 |
| `~/.openclaw/certs/key.pem, crt.pem` | HTTPS 自签证书 | 代理首次启动自动生成 |

---

## 6. 故障排查速查表

| 症状 | 根因 | 修复 |
|------|------|------|
| Claude: `Unable to connect to Anthropic services` | api.anthropic.com 被墙 | 确认 hosts 劫持 + 443 代理运行 |
| Claude: 弹"需要登录" | API key 在 rejected 列表 | wrapper 自动修复，或手动移 .claude.json |
| Claude: `Header '14' has invalid value` | 用了 `ANTHROPIC_AUTH_TOKEN` | 改用 `ANTHROPIC_API_KEY` |
| Claude: 模型调用失败/重试 | 模型别名未配 | 确保 `ANTHROPIC_DEFAULT_*` 全设 deepseek-v4-flash |
| Claude: Sub-agent 失败 | 子代理用 Anthropic 模型名 | 设 `CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash` |
| Hermes: `deepseek/deepseek-v4-flash` 400 | 继承了 ANTHROPIC_BASE_URL | 收进 wrapper + unset 残留 + 重启 gateway |
| Hermes: auth 失败 | auth-profiles.json 为空 | 写入 deepseek:default profile |
| Memory: 搜索不可用 | 索引格式不匹配 / 缺 OpenAI key | 用 Ollama + nomic-embed-text + 重建索引 |
| 代理: 443 端口拒绝 | 没 sudo | 检查 sudoers 规则 + `sudo lsof -i :443` |
| 代理: 8787 端口占用 | 旧进程残留 | `sudo kill -9 $(lsof -ti :8787)` |

---

## 参考资料

- [腾讯云：Claude Code 接入 DeepSeek 完整指南](https://cloud.tencent.com/developer/article/2653743)
- [DeepSeek API Docs](https://api-docs.deepseek.com/)
- [Claude Code Docs](https://code.claude.com/docs)
- [Ollama](https://ollama.com/)

---

> 📅 配置日期: 2026-06-09
> 🖥 环境: macOS (Darwin arm64), Node.js v24, OpenClaw 2026.6.1, Claude Code 2.1.158
> 🔑 所有 API Key 已脱敏，请替换为实际值
