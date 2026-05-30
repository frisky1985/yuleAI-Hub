# Orchestrator 技能清单

**运行于**: OpenClaw
**通信方式**: agent-chat / agent-delegate

## 能力
- 管道编排：按阶段推进 Harness Engineering 管道
- 状态管理：维护 orchestrator-state.json
- 失败接管：3 次重试后自动介入修复
- 报告输出：生成最终总结报告

## 入口
```
python3 ~/.openclaw/mcp-bridge/harness-orchestrator.py run "<goal>"
python3 ~/.openclaw/mcp-bridge/harness-orchestrator.py resume   # 续传
python3 ~/.openclaw/mcp-bridge/harness-orchestrator.py status   # 状态
```

## 工具集
- agent-chat: 同步对话（<8s），用于快速问答
- agent-delegate: 异步任务委托，适合长任务
- context-read/write: 共享上下文
