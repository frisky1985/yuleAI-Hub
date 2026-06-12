# Codex CLI 对接 DeepSeek 规范

> 规范编号: OSH-CODEX-001
> 版本: v1.0
> 状态: 生效
> 适用范围: Codex CLI 通过本地代理使用 DeepSeek 作为后端

---

## 1. 架构规范

### 1.1 通信拓扑

```
Codex CLI ──Responses API──→ Proxy (:3333) ──Chat Completions──→ api.deepseek.com
```

- **Codex CLI**: 使用 OpenAI Responses API 协议
- **Proxy**: 本地 Node.js 服务，翻译 Responses API → Chat Completions
- **DeepSeek**: 标准 OpenAI-compatible API

### 1.2 端口规范

| 组件 | 协议 | 端口 | 绑定地址 |
|:-----|:-----|:-----|:---------|
| Proxy | HTTP（非 TLS） | 3333 | 127.0.0.1 |
| DeepSeek API | HTTPS | 443（出站） | — |

---

## 2. Codex 配置规范

### 2.1 config.toml

```toml
model_provider = "deepseek"
model          = "deepseek-v4-flash"
model_reasoning_effort = "medium"
model_catalog_json = "/path/to/deepseek-catalog.json"

[model_providers.deepseek]
name     = "DeepSeek (via proxy)"
base_url = "http://127.0.0.1:3333"
env_key  = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

### 2.2 配置项说明

| 键 | 值 | 说明 |
|:---|:---|:------|
| `model_provider` | `"deepseek"` | 激活的自定义 provider |
| `model` | `"deepseek-v4-flash"` 或 `"deepseek-v4-pro"` | 默认模型 slug |
| `model_catalog_json` | 绝对路径 | 模型目录文件路径 |
| `model_providers.<name>.base_url` | `http://127.0.0.1:3333` | 代理地址 |
| `model_providers.<name>.env_key` | `"DEEPSEEK_API_KEY"` | API key 的环境变量名 |
| `model_providers.<name>.wire_api` | `"responses"` | 使用 Responses API 协议 |

---

## 3. 代理规范

### 3.1 端点定义

| 方法 | 路径 | 功能 |
|:-----|:-----|:------|
| POST | `/v1/responses` | 翻译 Responses API → DeepSeek |
| GET | `/v1/models` | 返回模型列表（Codex `/model` 选择器） |
| GET | `/v1/models/:slug` | 返回单个模型信息 |
| GET | `/health` | 健康检查 |
| GET | `/stats` | 会话统计 |

### 3.2 协议翻译

**Responses API → Chat Completions:**

| Responses API | Chat Completions |
|:--------------|:-----------------|
| `input` (array) | `messages` (array) |
| `instructions` | system message（首条） |
| `tools[].function` | `tools[].function` |
| `tool_choice` | `tool_choice` |
| `max_output_tokens` | `max_tokens` |
| `temperature` | `temperature` |
| `stream: true` | `stream: true` |

**消息类型映射:**

- `message(role=developer)` → `role=system`
- `message(role=user/assistant)` → 原样传递
- `function_call` → 合并为单条 `role=assistant` + `tool_calls`
- `function_call_output` → `role=tool`

### 3.3 流式翻译

DeepSeek 的流式 SSE 事件被翻译为 Codex 期望的 Responses API 事件序列：

```
response.created
  → response.output_item.added
    → response.content_part.added
      → response.output_text.delta  (逐块)
    → response.content_part.done
  → response.output_item.done
response.completed
response.done
```

对于工具调用：

```
response.output_item.added (function_call)
  → response.function_call_arguments.delta
  → response.function_call_arguments.done
response.output_item.done (function_call)
```

### 3.4 DeepSeek Thinking 模式

DeepSeek 的 `reasoning_content` 字段在流式响应中被捕获并缓存，在下一轮请求时回传给上下文。

---

## 4. 模型目录规范

### 4.1 字段要求

| 字段 | 必填 | 说明 |
|:-----|:-----|:------|
| `slug` | ✅ | 模型标识（如 `deepseek-v4-flash`） |
| `display_name` | ✅ | Codex 界面显示名 |
| `default_reasoning_level` | ✅ | 默认推理级别 |
| `supported_reasoning_levels` | ✅ | 支持的推理级别数组 |
| `shell_type` | ✅ | 固定 `"shell_command"` |
| `visibility` | ✅ | 固定 `"list"` |
| `context_window` | ✅ | 上下文窗口大小 |
| `base_instructions` | ✅ | Codex 系统提示词 |

---

## 5. 启动与停止规范

### 5.1 启动顺序

1. 确保 `DEEPSEEK_API_KEY` 环境变量已设置
2. 启动 proxy（`node deepseek-proxy.js`）
3. 验证 `/health` 返回 200
4. 启动 Codex CLI（`codex`）

### 5.2 停止顺序

1. 退出 Codex（`/quit` 或 Ctrl+C）
2. 停止 proxy（Ctrl+C 或 `kill $(cat /tmp/codex-proxy.pid)`）

---

## 6. 验收标准

### 6.1 功能验收

- [ ] `node deepseek-proxy.js` 启动无错误
- [ ] `curl http://127.0.0.1:3333/health` 返回 200
- [ ] `curl http://127.0.0.1:3333/v1/models` 返回模型列表
- [ ] `codex exec "echo ok"` 正常返回结果
- [ ] `/model` 命令可切换 Flash / Pro

### 6.2 异常处理

- [ ] DeepSeek API 不可达时，proxy 返回错误事件
- [ ] API Key 无效时，proxy 启动时报错并退出
- [ ] 代理意外停止时，Codex 能检测到连接失败

---

## 附录

### A. 术语表

| 术语 | 说明 |
|:-----|:------|
| Responses API | OpenAI 的新一代 API 协议，支持流式响应和工具调用 |
| Chat Completions | OpenAI 兼容的标准 API 格式，DeepSeek 使用此格式 |
| SSE | Server-Sent Events，流式传输格式 |
| Tool Calls | 函数调用机制，Codex 通过此执行 shell 命令 |
| Reasoning Content | DeepSeek 的思维链推理内容 |

### B. 相关资源

- [Codex CLI GitHub](https://github.com/openai/codex)
- [DeepSeek API 文档](https://api-docs.deepseek.com/)
- [yuleAI-Hub: 完整指南](../codex-cli-deepseek/README.md)
- [CC Switch 原项目](https://github.com/pedromarttins/codex-switch)
