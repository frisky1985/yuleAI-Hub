# QoderCLI 技能清单

**运行于**: DeepSeek API（QoderCLI）
**通信方式**: agent-delegate

## 能力
- 架构设计：系统架构、模块边界、接口定义
- 编码实现：TDD 驱动编码
- 代码审查：深度审查、架构合规检查
- 代码探索：代码库分析、技术债务识别

## 子角色
| 角色 | 对应 Qoder Agent | 职责 |
|------|-----------------|------|
| Architect | ingeek-sw-arch | 系统架构设计 |
| Researcher | ingeek-sw-reviewer | 代码探索 |
| Planner | ingeek-sw-arch | 任务分解 |
| Implementer | ingeek-sw-dev | 编码实现 |
| Tester | ingeek-sw-test | 测试 |
| Reviewer | ingeek-sw-reviewer | 代码审查 |

## 调用方式
```
qodercli -p --dangerously-skip-permissions "prompt"
```
