# Hermes 技能清单

**运行于**: DeepSeek API（Hermes CLI）
**通信方式**: agent-chat / agent-delegate

## 能力
- 需求分析：解析用户需求，输出结构化需求文档
- 排期：基于需求文档制定时间线和里程碑
- 测试用例：为代码创建测试用例
- 测试执行：运行测试并输出测试报告
- 代码审查（一次性）：快速代码审查

## 调用方式
```
hermes -z "prompt" --yolo          # 同步（agent-chat）
hermes -z "long task" --yolo       # 异步（agent-delegate）
```
