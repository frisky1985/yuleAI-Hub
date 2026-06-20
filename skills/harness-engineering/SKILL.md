---
name: harness-engineering
description: "Harness Engineering 学习指南 — OpenAI提出的工程范式：工程师设计环境、明确意图、构建反馈回路，让AI智能体可靠地完成工作。来源: https://github.com/deusyu/harness-engineering"
metadata:
  source: https://github.com/deusyu/harness-engineering.git
  topics: [harness-engineering, agent-first, codex, ai-engineering]
---

# Harness Engineering 学习指南

> 人类掌舵，智能体执行。

**Harness Engineering**（驭缰工程）是 OpenAI 在 2026 年 2 月提出的工程范式：工程师不再写代码，而是设计环境、明确意图、构建反馈回路，让 AI 智能体可靠地完成工作。

来源：[OpenAI — Harness Engineering](https://openai.com/zh-Hans-CN/index/harness-engineering/)

## 核心理念

```
传统工程：人类写代码 → 机器执行代码
Harness Engineering：人类设计约束 → 智能体写代码 → 机器执行代码
```

核心转变：**工程师的产出从代码变成了约束系统**——AGENTS.md、架构规则、自定义 linter、反馈回路。

## 六大核心概念

1. **仓库即记录系统** — 不在仓库里的东西，对智能体不存在
2. **地图而非手册** — AGENTS.md 是目录页，不是百科全书
3. **语义化版本控制的沟通** — 规范的 commit message 是智能体的信号系统
4. **渐进式上下文披露** — 从入口文件出发，按需深入
5. **可机械验证的规范** — 规范必须可被脚本检查，仅靠文字无法约束智能体
6. **反馈即燃料** — 迭代回路是智能体进步的核心

## 仓库结构

| 目录 | 内容 |
|------|------|
| `concepts/` | 概念笔记 — 原文核心概念的拆解与整理 |
| `thinking/` | 独立思考 — 自己的理解、质疑、延伸思考 |
| `practice/` | 动手实践 — 小项目实验，验证方法论 |
| `feedback/` | 反馈记录 — 实践中的踩坑、修正、迭代 |
| `works/` | 作品输出 — 可展示的成果 |
| `tools/` | 工具具像化 — 降低复杂度的杠杆库 |
| `prompts/` | 提示词积累 — 验证有效的提示词 |
| `references/` | 外部资源索引 |

## 使用方式

在项目中使用 Harness Engineering 时，加载本技能并参考以下指南：

1. **创建 AGENTS.md** — 项目入口文档，~100 行，告诉智能体项目结构和工作方式
2. **建立规范检查** — 使用脚本验证规范一致性（参考 `scripts/check-consistency.sh`）
3. **渐进式上下文** — 主文档指向子文档，智能体按需深入
4. **反馈回路** — 每次实践后记录反馈，迭代改进

## 参考链接

- 完整知识库: https://github.com/deusyu/harness-engineering
- AGENTS.md 入口: https://github.com/deusyu/harness-engineering/blob/main/AGENTS.md
- OpenAI 原文: https://openai.com/zh-Hans-CN/index/harness-engineering/
