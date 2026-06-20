# Agent Mesh v2 产品规范

## 版本
- **版本**: 2.0.0
- **状态**: 已发布
- **最后更新**: 2026-05-30

## 概览

Agent Mesh v2 是 OpenClaw Agent 协作基础设施的升级版本。在 v1 (MCP Bridge) 基础上增加了 Agent 技能合同、结构化消息契约、可执行治理检查、形式化架构文档和 CI 验证。

## 核心能力

| 能力 | v1 | v2 |
|------|----|----|
| Agent 间通信 | MCP Bridge 子进程调用 | MCP Bridge + 消息总线 |
| Agent 角色定义 | orchestrator.py 硬编码 | 独立技能清单文件 |
| 消息结构 | 自由格式 | 合同约束的 JSON Schema |
| 上下文传递 | 无结构 context.json | 合同约束的阶段式上下文 |
| 治理检查 | 无 | bun 脚本 + CI |
| 架构文档 | 无 | docs/ARCHITECTURE.md |
| 失败恢复 | 基础重试 | 3 次重试 + 记录到 tech-debt |

## Agent 技能清单

每个 Agent 在 `~/.openclaw/mcp-bridge/skills/` 下拥有独立技能清单：

- `orchestrator.md` — 管道编排、状态管理
- `hermes.md` — 需求分析、测试
- `qodercli.md` — 架构、编码、审查
- `architect.md` — 系统架构设计
- `researcher.md` — 代码探索
- `planner.md` — 任务分解
- `implementer.md` — TDD 编码
- `tester.md` — 测试编写与执行
- `reviewer.md` — 代码审查

## 消息契约

见 `~/.openclaw/mcp-bridge/contracts/` 下的 JSON Schema 文件。

## 管道阶段

```
Phase 0: Init       — 加载状态，检查前置条件
Phase 1: Brainstorm  — 需求分析+设计（Hermes 分析 → Architect 架构）
Phase 2: Research    — 代码库探索（QoderCLI/Researcher）
Phase 3: Plan        — 任务分解+排期（Planner → Hermes 排期）
Phase 4: Implement   — TDD 编码（Implementer → Tester → Reviewer）
Phase 5: Review      — 最终代码审查（Reviewer）
Phase 6: Report      — 总结报告输出（Orchestrator）
```

## 质量门禁

- 每阶段输出必须有下一个阶段的确认
- 代码必须通过 TDD 循环（失败测试 → 实现 → 通过 → 审查）
- 审查与生成必须不同 Agent
- 阶段 3 次失败 → OpenClaw 接管
