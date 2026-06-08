---
name: "deepseek-codex-claude"
description: "Configure Codex CLI and Claude Code CLI to use DeepSeek models. Local Proxy for Codex, native endpoint for Claude. No Anthropic login needed."
---

# DeepSeek Codex & Claude CLI 配置 Skill

让 Codex CLI 和 Claude Code CLI 都使用 DeepSeek 模型，零 Anthropic 登录依赖。

## 架构

| CLI | 协议 | DeepSeek 端点 | 方式 |
|-----|------|-------------|------|
| **Codex CLI** (v0.137+) | Responses API → Chat Completions | `https://api.deepseek.com/v1` | 本地代理 (port 8787) |
| **Claude Code CLI** (v2.1+) | Anthropic Messages API | `https://api.deepseek.com/anthropic` | 直连 |

## 文件结构

```
~/.codex/
├── deepseek-proxy.py          # Codex → DeepSeek 本地代理 (responses → chat 格式转换)
├── start-proxy.sh             # 代理启停脚本
├── config.toml                # Codex 默认配置 (deepseek-v4-flash)
├── reasoner.config.toml       # Codex 推理配置 (deepseek-v4-pro)
├── auth.json                  # API Key 存储

~/Library/LaunchAgents/
└── com.deepseek.codex-proxy.plist   # LaunchAgent 开机自启
```

## 前置条件

- Node.js 18+ (`node --version`)
- Python 3.9+ with aiohttp (`pip3 install aiohttp`)
- Codex CLI (`npm install -g @openai/codex`)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- DeepSeek API Key (从 https://platform.deepseek.com/api_keys 获取)

## Codex CLI 配置

### 1. 本地代理 (deepseek-proxy.py)

将以下脚本保存为 `~/.codex/deepseek-proxy.py`。

代理的核心功能：
- 接收 Codex CLI 的 Responses API 格式请求 (`POST /v1/responses`)
- 转换为 DeepSeek 的 Chat Completions 格式 (`POST /v1/chat/completions`)
- 支持流式 SSE 事件双向转换
- 从 `~/.codex/auth.json` 自动读取 API Key
- 返回模型元数据（`/v1/models` 含 `context_window` 等信息）

```python
import json, os, uuid, time, aiohttp
from aiohttp import web

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "8787"))

def _resolve_apikey(request=None):
    if request:
        ah = request.headers.get("Authorization", "")
        if ah:
            return ah.replace("Bearer ", "").strip()
    try:
        with open(os.path.expanduser("~/.codex/auth.json")) as f:
            auth = json.load(f)
            return auth.get("DEEPSEEK_API_KEY") or auth.get("OPENAI_API_KEY", "") or ""
    except:
        return os.environ.get("DEEPSEEK_API_KEY", "")

def rewrite_tools(tools):
    # 将 Codex 内建类型 (shell_command, apply_patch, namespace 等) 转为标准 function 类型
    if not tools: return None
    rewritten = []
    for tool in tools:
        t = dict(tool)
        ttype = t.get("type", "function")
        if ttype == "function":
            if "function" not in t:
                func = {}
                for k in ("name","description","parameters","strict"):
                    if k in t: func[k] = t[k]
                if "schema" in t and "parameters" not in func:
                    func["parameters"] = t["schema"]
                if "parameters" not in func:
                    func["parameters"] = {"type":"object","properties":{}}
                t["function"] = func
            rewritten.append({"type":"function","function":t["function"]})
            continue
        name = t.get("name", ttype)
        func = {"name": name, "parameters": t.get("parameters",t.get("schema",{"type":"object","properties":{}}))}
        if "description" in t: func["description"] = t["description"]
        rewritten.append({"type":"function","function":func})
    return rewritten if rewritten else None

def responses_to_chat_completions(body):
    cc = {"model": body.get("model", "deepseek-v4-flash"), "messages": []}
    instructions = body.get("instructions")
    if instructions:
        cc["messages"].append({"role":"system","content":instructions})
    input_items = body.get("input", [])
    if isinstance(input_items, str):
        cc["messages"].append({"role":"user","content":input_items})
        return cc
    for item in (input_items if isinstance(input_items,list) else [input_items]):
        if isinstance(item, str):
            cc["messages"].append({"role":"user","content":item}); continue
        role = item.get("role","user")
        if role == "developer": role = "system"
        content = item.get("content","")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, str): parts.append(c)
                elif isinstance(c, dict):
                    ct = c.get("type","")
                    if ct in ("input_text","output_text","text"): parts.append(c.get("text",""))
                    elif ct == "input_image": parts.append(json.dumps(c))
                    elif ct == "input_file": parts.append(c.get("text","") or c.get("content",""))
                    else: parts.append(json.dumps(c))
                else: parts.append(str(c))
            content = "\n".join(parts) if parts else ""
        if role == "assistant" and "tool_calls" in item:
            tc_list = [{"id":tc.get("call_id",tc.get("id",f"call_{uuid.uuid4().hex[:8]}")),"type":"function","function":{"name":tc.get("name",""),"arguments":json.dumps(tc.get("arguments",{})) if isinstance(tc.get("arguments"),dict) else tc.get("arguments","{}")}} for tc in item["tool_calls"]]
            cc["messages"].append({"role":"assistant","content":content or None,"tool_calls":tc_list}); continue
        if role == "tool":
            cc["messages"].append({"role":"tool","content":content,"tool_call_id":item.get("call_id",item.get("id",""))}); continue
        cc["messages"].append({"role":role,"content":content or ""})
    if not cc["messages"]: cc["messages"].append({"role":"user","content":"Hello"})
    tools = rewrite_tools(body.get("tools"))
    if tools: cc["tools"] = tools
    if body.get("stream"): cc.update({"stream":True,"stream_options":{"include_usage":True}})
    for k in ("temperature","top_p"): 
        if k in body: cc[k] = body[k]
    if "max_output_tokens" in body and body["max_output_tokens"]: cc["max_tokens"] = body["max_output_tokens"]
    return cc

def chat_completion_to_responses(cc_resp, model):
    choice, usage = cc_resp.get("choices",[{}])[0], cc_resp.get("usage",{})
    message = choice.get("message",{})
    output = []
    reasoning = message.get("reasoning_content","")
    if reasoning:
        output.append({"type":"reasoning","id":f"rs_{uuid.uuid4().hex[:16]}","status":"completed","content":[{"type":"output_text","text":reasoning,"annotations":[]}]})
    content = message.get("content","")
    if content:
        output.append({"type":"message","id":str(uuid.uuid4()),"status":"completed","role":"assistant","content":[{"type":"output_text","text":content,"annotations":[]}]})
    for tc in message.get("tool_calls",[]):
        args = tc.get("function",{}).get("arguments","{}")
        try: args = json.loads(args) if isinstance(args,str) else args
        except: args = {"raw":args}
        output.append({"type":"function_call","id":f"fc_{uuid.uuid4().hex[:16]}","call_id":tc.get("id",f"call_{uuid.uuid4().hex[:8]}"),"name":tc.get("function",{}).get("name",""),"arguments":json.dumps(args) if isinstance(args,dict) else str(args),"status":"completed"})
    return {"id":f"resp_{uuid.uuid4().hex[:24]}","object":"response","created_at":int(time.time()),"status":"completed","model":model,"output":output,"usage":{"input_tokens":usage.get("prompt_tokens",0),"output_tokens":usage.get("completion_tokens",0),"total_tokens":usage.get("total_tokens",0)},"error":None,"incomplete_details":None}

async def stream_chat_to_responses(aiohttp_resp, model):
    response_id = f"resp_{uuid.uuid4().hex[:24]}"; msg_id = str(uuid.uuid4()); item_id = f"msg_{uuid.uuid4().hex[:16]}"
    yield f"data: {json.dumps({'type':'response.created','response':{'id':response_id,'status':'in_progress','model':model,'output':[]}})}\n\n"
    yield f"data: {json.dumps({'type':'response.output_item.added','output_index':0,'item':{'type':'message','id':msg_id,'status':'in_progress','role':'assistant','content':[]}})}\n\n"
    yield f"data: {json.dumps({'type':'response.content_part.added','item_id':msg_id,'output_index':0,'content_index':0,'part':{'type':'output_text','text':''}})}\n\n"
    content_buffer = ""
    async for line in aiohttp_resp.content:
        line = line.decode("utf-8",errors="replace").strip()
        if not line or not line.startswith("data:"): continue
        d = line[5:].strip()
        if d == "[DONE]": break
        try: chunk = json.loads(d)
        except: continue
        for c in chunk.get("choices",[]):
            delta = c.get("delta",{})
            text = delta.get("content","")
            if text:
                content_buffer += text
                yield f"data: {json.dumps({'type':'response.content_part.delta','item_id':msg_id,'output_index':0,'content_index':0,'delta':{'type':'output_text','text':text}})}\n\n"
    yield f"data: {json.dumps({'type':'response.content_part.done','item_id':msg_id,'output_index':0,'content_index':0,'part':{'type':'output_text','text':content_buffer,'annotations':[]}})}\n\n"
    yield f"data: {json.dumps({'type':'response.output_item.done','output_index':0,'item':{'type':'message','id':msg_id,'status':'completed','role':'assistant','content':[{'type':'output_text','text':content_buffer,'annotations':[]}]}})}\n\n"
    yield f"data: {json.dumps({'type':'response.completed','response':{'id':response_id,'status':'completed','model':model,'output':[{'type':'message','id':msg_id,'status':'completed','role':'assistant','content':[{'type':'output_text','text':content_buffer,'annotations':[]}]}],'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}})}\n\n"

async def handle_responses(request):
    try: body = await request.json()
    except: return web.json_response({"error":"Invalid JSON"},status=400)
    is_stream = body.get("stream",False)
    cc_body = responses_to_chat_completions(body)
    api_key = _resolve_apikey(request)
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    async with aiohttp.ClientSession() as s:
        if is_stream:
            async with s.post(url,json=cc_body,headers=headers) as r:
                if r.status!=200: return web.Response(text=f"data: {json.dumps({'type':'error','error':{'message':await r.text()}})}\n\n",content_type="text/event-stream")
                resp = web.StreamResponse(status=200,headers={"Content-Type":"text/event-stream","Cache-Control":"no-cache"})
                await resp.prepare(request)
                async for e in stream_chat_to_responses(r,body.get("model","deepseek-v4-flash")):
                    await resp.write(e.encode())
                return resp
        else:
            async with s.post(url,json=cc_body,headers=headers) as r:
                return web.json_response(chat_completion_to_responses(await r.json(),body.get("model")) if r.status==200 else {"error":await r.text()},status=r.status)

async def handle_models(request):
    models = [{"id":name,"object":"model","created":1700000000,"owned_by":"deepseek","metadata":{"context_window":65536,"max_context_window":65536}} for name in ["deepseek-v4-flash","deepseek-v4-pro","deepseek-chat","deepseek-reasoner"]]
    return web.json_response({"object":"list","data":models})

async def handle_health(request):
    return web.json_response({"status":"ok"})

async def catch_all(request):
    api_key = _resolve_apikey(request)
    h = {"Authorization":f"Bearer {api_key}","Content-Type":request.content_type or "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.request(request.method,f"{DEEPSEEK_BASE_URL}{request.path}",data=await request.read(),headers=h) as r:
            return web.Response(body=await r.read(),status=r.status,content_type=r.content_type)

def main():
    app = web.Application()
    app.router.add_post("/v1/responses",handle_responses)
    app.router.add_get("/v1/models",handle_models)
    app.router.add_get("/health",handle_health)
    app.router.add_route("*","/{_:.*}",catch_all)
    print(f"Proxy on :{LISTEN_PORT} → {DEEPSEEK_BASE_URL}")
    web.run_app(app,host="0.0.0.0",port=LISTEN_PORT)

if __name__ == "__main__":
    main()
```

### 2. 启动脚本 (start-proxy.sh)

`~/.codex/start-proxy.sh`:

```bash
#!/bin/bash
PIDFILE="/tmp/deepseek-proxy.pid"
PROXY="$HOME/.codex/deepseek-proxy.py"
PYTHON="/opt/homebrew/bin/python3"
start() {
    [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null && echo "Already running" && return
    nohup "$PYTHON" "$PROXY" > /tmp/deepseek-proxy.log 2>&1 & echo $! > "$PIDFILE"
    sleep 1; echo "Started (PID $(cat $PIDFILE))"
}
stop() { [ -f "$PIDFILE" ] && kill $(cat "$PIDFILE") 2>/dev/null && rm -f "$PIDFILE" && echo "Stopped"; }
status() { [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null && echo "Running" || echo "Not running"; }
case "${1:-}" in start) start;; stop) stop;; status) status;; *) echo "Usage: $0 {start|stop|status}"; esac
```

```bash
chmod +x ~/.codex/start-proxy.sh
```

### 3. Codex 配置

`~/.codex/config.toml`:
```toml
model = "deepseek-v4-flash"
model_provider = "deepseek"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "http://localhost:8787/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

`~/.codex/reasoner.config.toml`:
```toml
model = "deepseek-v4-pro"
model_provider = "deepseek"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "http://localhost:8787/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

### 4. 存储 API Key

`~/.codex/auth.json`:
```json
{
  "auth_mode": "apikey",
  "DEEPSEEK_API_KEY": "sk-your-deepseek-api-key"
}
```

### 5. 环境变量 (Shell 集成)

添加到 `~/.zshrc`:

```bash
# DeepSeek API Key
export DEEPSEEK_API_KEY="sk-your-deepseek-api-key"

# Codex proxy auto-start
codex() {
    if ! pgrep -f "deepseek-proxy.py" > /dev/null 2>&1; then
        ~/.codex/start-proxy.sh start
    fi
    command codex "$@"
}

# Claude Code → DeepSeek（ANTHROPIC_AUTH_TOKEN 绕过登录！）
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="sk-your-deepseek-api-key"
export ANTHROPIC_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_EFFORT_LEVEL="max"
```

### 6. LaunchAgent (开机自启)

`~/Library/LaunchAgents/com.deepseek.codex-proxy.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.deepseek.codex-proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>~/.codex/deepseek-proxy.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/deepseek-proxy.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/deepseek-proxy.log</string>
</dict>
</plist>
```

## 使用方式

```bash
# Codex CLI
codex                              # deepseek-v4-flash
codex --profile reasoner           # deepseek-v4-pro
codex exec -                       # 非交互模式 (pipe)

# Claude Code CLI
claude                             # 交互模式
echo 'say "hi"' | claude -p        # 非交互模式
```

## 关键注意点

1. **Claude Code 要用 `ANTHROPIC_AUTH_TOKEN` 而不是 `ANTHROPIC_API_KEY`** — 前者绕过 Anthropic 登录检查，后者触发 "Not logged in"
2. **Codex 代理自动从 `auth.json` 读 Key** — 不需要额外设置环境变量
3. **Proxy 端口 8787** — 如果冲突，修改 `PROXY_PORT` 环境变量
4. **Claude Code 直连 DeepSeek** — 不需要本地代理
