# Agent Mesh 架构

## 概述

Agent Mesh 是一个多 Agent 协作框架。Agent 通过 MCP Bridge 直接对话，由 OpenClaw 编排管道。

## 架构分层

```
┌────────────────────────────────────────────┐
│             OpenClaw (编排层)                │
│  • 管道编排（Harness Engineering 管道）      │
│  • 阶段推进与状态管理                        │
│  • 失败接管（3 次重试后自动介入）            │
│  • 最终报告输出                             │
├────────────────────────────────────────────┤
│             MCP Bridge (通信层)              │
│  • agent-chat     — 同步 8s 内快速对话      │
│  • agent-delegate — 异步任务委托             │
│  • context-read   — 共享上下文读取           │
│  • context-write  — 共享上下文写入           │
│  • task-result    — 异步任务结果查询          │
│  • agent-status   — Agent 健康检查           │
├────────────────────────────────────────────┤
│          Agent Messenger (消息总线)           │
│  • 文件级消息队列（p2p 直接通信）            │
│  • 支持 send/read/reply/wait/broadcast      │
│  • 每个角色独立邮箱                          │
├────────────────────────────────────────────┤
│             Agent 层                         │
│  ┌────────┐ ┌────────┐ ┌────────┐          │
│  │ OpenClaw│ │ Hermes  │ │ QoderCLI│        │
│  │ (主控)  │ │ (分析)  │ │ (编码)  │         │
│  └────────┘ └────────┘ └────────┘          │
│  ┌────────┐ ┌────────┐ ┌────────┐          │
│  │Architect│ │Planner  │ │Tester   │         │
│  │(Qoder)  │ │(Qoder)  │ │(Qoder)  │         │
│  └────────┘ └────────┘ └────────┘          │
└────────────────────────────────────────────┘
```

## Agent 角色定义

| 角色 | 后端 | 职责 | 通信方式 |
|------|------|------|---------|
| Orchestrator | OpenClaw | 管道编排、阶段推进、报告输出 | agent-chat → Hermes / QoderCLI |
| Hermes | DeepSeek API | 需求分析、排期、测试用例、测试执行 | agent-delegate / 消息总线 |
| QoderCLI | DeepSeek API | 架构设计、编码实现 | agent-delegate / 消息总线 |
| Architect | QoderCLI | 系统架构、模块边界 | 消息总线 |
| Researcher | QoderCLI | 代码探索、事实发现 | 消息总线 |
| Planner | QoderCLI | 任务分解、排期细化 | 消息总线 |
| Implementer | QoderCLI | TDD 编码实现 | 消息总线 |
| Tester | QoderCLI | 单元测试、覆盖率 | 消息总线 |
| Reviewer | QoderCLI | 代码审查、质量门禁 | 消息总线 |

## 通信协议

### 方式 1：MCP Bridge（编排→Agent）
```
OpenClaw ──agent-chat──▶ Hermes  (同步，<8s)
OpenClaw ──agent-delegate──▶ QoderCLI (异步)
```

### 方式 2：消息总线（Agent↔Agent）
```
Architect ──send──▶ Planner  (文件消息队列)
Planner ──reply──▶ Architect
```

### 消息载荷结构

```json
{
  "message_id": "uuid",
  "from": "architect",
  "to": "planner",
  "subject": "architecture-review",
  "body": { ... },
  "timestamp": "2026-05-30T23:00:00Z",
  "in_reply_to": null,
  "contract": "contract-v1"
}
```

## 上下文传递契约

每阶段通过 `context-write` 写入共享上下文：

```json
{
  "pipeline_status": "running",
  "current_phase": "plan",
  "phase_history": [
    {"phase":"brainstorm","status":"done","agent":"orchestrator"},
    {"phase":"research","status":"done","agent":"researcher"},
    {"phase":"plan","status":"running","agent":"planner"}
  ],
  "artifacts": {
    "design_doc": "docs/plans/2026-05-30-design.md",
    "architecture_doc": "docs/architecture/...",
    "plan_doc": "docs/exec-plans/..."
  }
}
```

## 失败处理

- 每阶段最大尝试：3 次
- 尝试失败 → 记录到 tech-debt-tracker
- 3 次全失败 → OpenClaw 接管，输出异常报告
- 超时处理：同步 8s，异步 300s

## 保证 Agent 直接对话的机制

### 1. 消息总线 — 物理基础设施

所有 Agent 共享同一个文件级消息总线，这是对话的基础。

```
~/.openclaw/mcp-bridge/workspace/messages/
  ├── queue/
  │   ├── architect/       ← 每个角色有独立收件箱
  │   ├── researcher/
  │   ├── planner/
  │   ├── implementer/
  │   ├── tester/
  │   ├── reviewer/
  │   ├── hermes/
  │   ├── qodercli/
  │   └── orchestrator/
  ├── archive/              ← 过期消息自动移入
  ├── topics/               ← 广播主题存档
  ├── threads/              ← 对话线程追踪
  └── subscriptions.json    ← 主题订阅表
```

**核心原则：Agent 从不直接发消息给对方——而是写入对方的收件箱文件。对方自读。**

### 2. 对话流程（点对点）

```
Agent A                   Agent B
   │                         │
   │  1. send(role, subject) │
   │────────────────────────▶│  (写入 B 的收件箱)
   │                         │
   │  2. (B 在忙别的)         │
   │                         │
   │  3. B 空闲时 poll
   │     messenger.py wait   │
   │                         │
   │  4. 读到消息             │
   │                         │
   │  5. reply(msg_id, body) │
   │◀────────────────────────│  (写入 A 的收件箱)
   │                         │
   │  6. A 下次 read 看到回复  │
```

**保证机制**：写文件是原子操作，不会丢消息。不依赖网络、不依赖两者同时在线。

### 3. 三种对话模式

#### 模式 A：点对点（最常见）

```bash
# 发消息
python3 agent-messenger.py send architect planner "design-review"

# 等待收信（最长 60s）
python3 agent-messenger.py wait planner --timeout 60
# → [{"from": "architect", "subject": "design-review", ...}]

# 回复
python3 agent-messenger.py reply <msg_id> planner
```

#### 模式 B：广播 + 订阅

```bash
# 订阅：Tester 和 Reviewer 注册自己关心的主题
python3 agent-messenger.py subscribe tester "code/review-request"
python3 agent-messenger.py subscribe reviewer "code/review-request"

# 广播：Implementer 一发代码，所有订阅者自动收到
python3 agent-messenger.py broadcast implementer "code/review-request" "代码已完成"
```

#### 模式 C：对话线程追踪

```bash
# 追踪完整对话历史
python3 agent-messenger.py thread <origin_msg_id>
# → [msg1, reply1, reply2, ...]
```

### 4. 不丢消息的保证

| 机制 | 说明 |
|------|------|
| **原子写** | `_save_msg()` 把消息序列化为 JSON 再写入收件箱文件，不会写一半 |
| **自动清理** | 消息在收件箱超过 30 分钟自动移入 archive，不丢失不堆积 |
| **存档保留** | archive 目录永久保留，purge 默认只清理 24h 以上 |
| **契约校验** | 每条消息带 `contract: "message-v1"`，格式不合规可拒绝 |
| **发现机制** | `discover` 自动列出所有在线 Agent，发错角色名会报错 |

### 5. Orchestrator 不中转

旧模式（v1）—— Orchestrator 代理：

```
Orchestrator → 问 Hermes → 拿结果 → 给 QoderCLI
```

新模式（v2）—— Orchestrator 引导后 Agent 自己聊：

```
Orchestrator 说："Implementer，你的任务结束，broadcast 通知 Reviewer"
     ↓
Reviewer 听到广播，自动开始审查
     ↓
审查完直接 broadcast "pipeline/phase-complete"
     ↓
Orchestrator 收到广播，推进下一阶段
```

**Orchestrator 只在阶段边界出现，中间的高频对话全是 Agent 之间 p2p。**

### 6. 一键验证

```bash
# 查看整个通信链路
python3 agent-messenger.py discover
# → 所有 Agent 在线 + 角色清单

python3 agent-messenger.py status
# → 所有收件箱为空，系统就绪

# 测试：Architect → Planner → 回传
python3 agent-messenger.py send architect planner "ping" '{"test": true}'
python3 agent-messenger.py read planner --last 1
python3 agent-messenger.py reply <msg_id> planner '{"pong": true}'
python3 agent-messenger.py thread <msg_id>
# → 完整 ping-pong 记录
```

## 边界规则

1. OpenClaw 只编排，不替 Agent 写代码
2. Agent 之间直接沟通——不经过 OpenClaw 中转
3. 每阶段输出必须有验证
4. 生成与审查必须分离（不同 Agent）
5. 架构变更必须经 Architect 评审
6. 消息必须遵守 `message-v1` 契约格式
