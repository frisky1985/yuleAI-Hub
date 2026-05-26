---
name: agent-mesh-keepalive
description: 跨 Agent 对话保活与在线维持。自动检测 OpenClaw、Hermes、QoderCLI 在线状态，定期保活，保持上下文同步。当需要跨 Agent 协作、确保 Agent 可用、或恢复断开的会话时触发。
---

# Agent Mesh Keepalive — 跨 Agent 对话保活技能

确保 OpenClaw、Hermes、QoderCLI 三个 Agent 始终在线、上下文一致，会话不断连。

## 架构

```
┌─────────────────────────────────────────┐
│         Agent Mesh Keepalive            │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────┐  │
│  │  健康检查  │  │ 上下文同步 │  │ 保活 │  │
│  └──────────┘  └──────────┘  └──────┘  │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌───────┐  ┌────────┐  ┌──────────┐
│Hermes │  │QoderCLI│  │ OpenClaw │
└───────┘  └────────┘  └──────────┘
```

## 1. 一键检查所有 Agent 状态

```bash
# 通过 MCP Bridge 检查
openclaw  # 然后在对话中调用 agent-status

# 或直接终端检查
echo "=== Agent Online Check ==="
for cmd in openclaw hermes qodercli; do
  if command -v $cmd &>/dev/null; then
    echo "  ✓ $cmd: $($cmd --version 2>&1 | head -1)"
  else
    echo "  ✗ $cmd: NOT FOUND"
  fi
done
```

## 2. 保活机制

### 方式 A：MCP Bridge 保活

在任何 Agent 对话中：

> 用 `agent-status` 检查所有 Agent 是否在线

如果某个 Agent 掉线，启动它：

```bash
# 启动 Hermes（后台）
hermes -z "我上线了" --yolo &

# 启动 QoderCLI
qodercli -p "ready" --dangerously-skip-permissions &

# OpenClaw 已在运行中
```

### 方式 B：cron 定时保活

```bash
# 每 30 分钟检查一次所有 Agent
cat > ~/.local/bin/agent-ping << 'EOF'
#!/usr/bin/env bash
# Agent 保活脚本 — 建议 crontab 每 30 分钟执行
for cmd in openclaw hermes qodercli; do
  if ! command -v $cmd &>/dev/null; then
    echo "[WARN] $cmd 未安装"
  fi
done

# 通过 MCP Bridge 同步上下文
python3 ~/.openclaw/mcp-bridge/mcp_bridge_server.py <<< '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"agent-status","arguments":{}}}' 2>/dev/null &
EOF
chmod +x ~/.local/bin/agent-ping

# 添加到 crontab
(crontab -l 2>/dev/null; echo "*/30 * * * * ~/.local/bin/agent-ping") | crontab -
```

## 3. 上下文同步（跨 Agent 对话延续）

当需要保持跨 Agent 对话连续时，使用 MCP Bridge 的 context-read/write：

### 保存当前对话状态

```bash
# 在任意 Agent 中
"用 context-write，key=conversation_state, value={\"topic\":\"网站设计\",\"progress\":\"方案A已定稿\",\"next_step\":\"部署上线\"}"
```

### 恢复对话

```bash
# 其他 Agent 读取上下文
"用 context-read 查 conversation_state"

# 或终端查
cat ~/.openclaw/mcp-bridge/workspace/context.json
```

### 会话接力流程

```
Agent A 完成分析
  → context-write 存结果
Agent B 开始工作
  → context-read 读上下文
  → 继续推进
Agent C 收尾
  → context-read 读完整上下文
  → 输出最终结果
```

## 4. 快速恢复断连会话

### 如果 Hermes 掉线

```bash
# 重启 Hermes 并恢复上下文
hermes -z "继续之前的任务。上次进度：$(cat ~/.openclaw/mcp-bridge/workspace/context.json 2>/dev/null)" --yolo
```

### 如果 QoderCLI 掉线

```bash
qodercli -p "恢复会话。当前上下文保存在 ~/.openclaw/mcp-bridge/workspace/context.json，请先读取"
```

### 如果 OpenClaw 重启

OpenClaw 重启后自动重连 MCP Bridge，直接调用 `agent-status` 检查网络即可。

## 5. 日常使用流程

```
每天早上:
  1. agent-status → 确认三个 Agent 在线
  2. context-read → 回顾昨天的上下文
  3. 开始新任务

任务进行中:
  1. Agent A 完成任务 → context-write 存结果
  2. Agent B context-read → 继续
  3. 每一步都写上下文，保证不掉线

晚上收工:
  1. context-write 存最终状态
  2. 记录今天进度到 yuleAI-Hub/memory/
```

## 6. 报警机制

如果 Agent 掉线超过 1 小时，触发通知：

```bash
# 检查最后活跃时间
ls -lt ~/.openclaw/mcp-bridge/workspace/context.json

# 如果文件超过 1 小时没更新，发提醒
find ~/.openclaw/mcp-bridge/workspace/context.json -mmin +60 \
  -exec echo "⚠️  Agent Mesh 超过 1 小时无活动，请检查" \;
```
