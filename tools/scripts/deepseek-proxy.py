#!/usr/bin/env python3
"""
DeepSeek Responses API Proxy
Translates OpenAI Responses API <-> DeepSeek Chat Completions API
For use with Codex CLI v0.137+
"""

import json
import os
import sys
import uuid
import time
import asyncio

# Load API key from auth.json, then env var, then auth header
def _resolve_apikey(request=None):
    # Priority: Authorization header > auth.json > env var
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
import aiohttp
from aiohttp import web

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "8787"))

def rewrite_tools(tools):
    """Rewrite Codex-specific tool types to standard Chat Completions 'function' type."""
    if not tools:
        return None
    rewritten = []
    for tool in tools:
        t = dict(tool)
        ttype = t.get("type", "function")

        if ttype == "function":
            # Ensure proper nesting: function key should contain name/parameters
            if "function" not in t:
                func = {}
                if "name" in t:
                    func["name"] = t["name"]
                if "description" in t:
                    func["description"] = t["description"]
                if "parameters" in t:
                    func["parameters"] = t["parameters"]
                elif "schema" in t:
                    func["parameters"] = t["schema"]
                else:
                    func["parameters"] = {"type": "object", "properties": {}}
                if "strict" in t:
                    func["strict"] = t["strict"]
                t["function"] = func
            rewritten.append({"type": "function", "function": t["function"]})
            continue

        # Codex built-in types: shell_command, apply_patch, namespace, etc.
        # Convert to standard function type
        name = t.get("type", "unknown")
        if "name" not in t or not t["name"]:
            t["name"] = name

        # Build parameters
        params = t.get("parameters", t.get("schema", {"type": "object", "properties": {}}))

        func = {
            "name": t.get("name", name),
            "parameters": params,
        }
        if "description" in t:
            func["description"] = t["description"]

        rewritten.append({"type": "function", "function": func})

    return rewritten if rewritten else None


def responses_to_chat_completions(body):
    """Convert Responses API request body to Chat Completions format."""
    cc = {}
    cc["model"] = body.get("model", "deepseek-v4-flash")

    # Convert input -> messages
    messages = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    input_items = body.get("input", [])
    if isinstance(input_items, str):
        messages.append({"role": "user", "content": input_items})
    elif isinstance(input_items, list):
        for item in input_items:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue

            role = item.get("role", "user")
            # Map OpenAI-specific roles to DeepSeek-compatible roles
            if role == "developer":
                role = "system"
            content = item.get("content", "")

            # Handle nested content arrays (text, input_text, etc.)
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, dict):
                        ctype = c.get("type", "")
                        if ctype in ("input_text", "output_text", "text"):
                            parts.append(c.get("text", ""))
                        elif ctype == "input_image":
                            # Pass through image content
                            parts.append(c)
                        elif ctype == "input_file":
                            parts.append(c.get("text", "") or c.get("content", ""))
                        else:
                            parts.append(json.dumps(c))
                    else:
                        parts.append(str(c))
                content = "\n".join(parts) if parts else ""

            # Handle tool calls from assistant messages
            if role == "assistant" and "tool_calls" in item:
                tc_list = []
                for tc in item["tool_calls"]:
                    tc_list.append({
                        "id": tc.get("call_id", tc.get("id", f"call_{uuid.uuid4().hex[:8]}")),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else tc.get("arguments", "{}"),
                        }
                    })
                msg = {"role": "assistant", "content": content or None, "tool_calls": tc_list}
                messages.append(msg)
                continue

            # Handle tool results
            if role == "tool":
                messages.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": item.get("call_id", item.get("id", "")),
                })
                continue

            # Handle previous_response_id items with output
            if "output" in item:
                output = item["output"]
                if isinstance(output, list):
                    for o in output:
                        if isinstance(o, dict) and o.get("type") == "message":
                            ocontent = o.get("content", "")
                            if isinstance(ocontent, list):
                                ocontent = "\n".join(c.get("text", "") for c in ocontent if isinstance(c, dict))
                            messages.append({"role": "assistant", "content": ocontent})
                continue

            messages.append({"role": role, "content": content or ""})

    if not messages:
        messages.append({"role": "user", "content": "Hello"})

    cc["messages"] = messages

    # Tools
    tools = rewrite_tools(body.get("tools"))
    if tools:
        cc["tools"] = tools

    # Standard params
    if body.get("stream"):
        cc["stream"] = True
        cc["stream_options"] = {"include_usage": True}

    if "temperature" in body:
        cc["temperature"] = body["temperature"]
    if "top_p" in body:
        cc["top_p"] = body["top_p"]
    if "max_output_tokens" in body and body["max_output_tokens"]:
        cc["max_tokens"] = body["max_output_tokens"]
    if "tool_choice" in body:
        tc = body["tool_choice"]
        if isinstance(tc, str):
            cc["tool_choice"] = tc
        elif isinstance(tc, dict):
            if tc.get("type") == "function":
                cc["tool_choice"] = {"type": "function", "function": {"name": tc.get("function", {}).get("name", "")}}
            else:
                cc["tool_choice"] = "auto"

    return cc


def make_response_id():
    return f"resp_{uuid.uuid4().hex[:24]}"

def make_msg_id():
    return str(uuid.uuid4())


def chat_completion_to_responses(cc_resp, model):
    """Convert non-streaming Chat Completions response to Responses API format."""
    choice = cc_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = cc_resp.get("usage", {})

    output = []

    # Reasoning content (DeepSeek reasoner models)
    reasoning = message.get("reasoning_content", "")
    if reasoning:
        output.append({
            "type": "reasoning",
            "id": f"rs_{uuid.uuid4().hex[:16]}",
            "status": "completed",
            "content": [{"type": "output_text", "text": reasoning, "annotations": []}],
        })

    # Text content
    content = message.get("content", "")
    if content:
        output.append({
            "type": "message",
            "id": make_msg_id(),
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        })

    # Tool calls
    tool_calls = message.get("tool_calls", [])
    for tc in tool_calls:
        args = tc.get("function", {}).get("arguments", "{}")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            args = {"raw": args}

        output.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:16]}",
            "call_id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": tc.get("function", {}).get("name", ""),
            "arguments": json.dumps(args) if isinstance(args, dict) else str(args),
            "status": "completed",
        })

    return {
        "id": make_response_id(),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "input_tokens_details": {"cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)},
            "output_tokens_details": {"reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)},
        },
        "error": None,
        "incomplete_details": None,
    }


async def stream_chat_to_responses(aiohttp_resp, model):
    """Async generator that converts streaming Chat Completions SSE to Responses API events."""
    response_id = make_response_id()
    msg_id = make_msg_id()
    item_id = f"msg_{uuid.uuid4().hex[:16]}"

    # response.created
    yield _sse({"type": "response.created", "response": {"id": response_id, "object": "response", "status": "in_progress", "model": model, "output": []}})
    # response.in_progress
    yield _sse({"type": "response.in_progress", "response": {"id": response_id, "object": "response", "status": "in_progress", "model": model, "output": []}})

    # output_item.added (message)
    yield _sse({"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "id": msg_id, "status": "in_progress", "role": "assistant", "content": []}})
    # content_part.added
    yield _sse({"type": "response.content_part.added", "item_id": msg_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": ""}})

    full_content = ""
    full_reasoning = ""
    tool_calls_accum = {}  # index -> {id, name, arguments}
    usage_data = None

    async for line in aiohttp_resp.content:
        line = line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        # Capture usage
        if chunk.get("usage"):
            usage_data = chunk["usage"]

        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # Reasoning content
        reasoning_content = delta.get("reasoning_content", "")
        if reasoning_content:
            full_reasoning += reasoning_content

        # Text content
        content = delta.get("content", "")
        if content:
            full_content += content
            yield _sse({
                "type": "response.content_part.delta",
                "item_id": msg_id,
                "output_index": 0,
                "content_index": 0,
                "delta": {"type": "output_text", "text": content},
            })

        # Tool calls
        for tc_delta in delta.get("tool_calls", []):
            idx = tc_delta.get("index", 0)
            if idx not in tool_calls_accum:
                call_id = tc_delta.get("id", f"call_{uuid.uuid4().hex[:8]}")
                name = tc_delta.get("function", {}).get("name", "")
                tool_calls_accum[idx] = {"id": call_id, "name": name, "arguments": ""}

                # Emit function_call item added
                fc_id = f"fc_{uuid.uuid4().hex[:16]}"
                tool_calls_accum[idx]["_fc_id"] = fc_id
                yield _sse({
                    "type": "response.output_item.added",
                    "output_index": 1 + idx,
                    "item": {
                        "type": "function_call",
                        "id": fc_id,
                        "call_id": call_id,
                        "name": name,
                        "arguments": "",
                        "status": "in_progress",
                    }
                })

            args_chunk = tc_delta.get("function", {}).get("arguments", "")
            if args_chunk:
                tool_calls_accum[idx]["arguments"] += args_chunk
                yield _sse({
                    "type": "response.function_call_arguments.delta",
                    "item_id": tool_calls_accum[idx].get("_fc_id", ""),
                    "output_index": 1 + idx,
                    "delta": args_chunk,
                })

    # content_part.done
    yield _sse({
        "type": "response.content_part.done",
        "item_id": msg_id,
        "output_index": 0,
        "content_index": 0,
        "part": {"type": "output_text", "text": full_content, "annotations": []},
    })

    # output_item.done (message)
    yield _sse({
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": msg_id,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": full_content, "annotations": []}],
        },
    })

    # Done with tool call items
    for idx, tc in sorted(tool_calls_accum.items()):
        fc_id = tc.get("_fc_id", f"fc_{uuid.uuid4().hex[:16]}")
        yield _sse({
            "type": "response.function_call_arguments.done",
            "item_id": fc_id,
            "output_index": 1 + idx,
            "arguments": tc["arguments"],
        })
        yield _sse({
            "type": "response.output_item.done",
            "output_index": 1 + idx,
            "item": {
                "type": "function_call",
                "id": fc_id,
                "call_id": tc["id"],
                "name": tc["name"],
                "arguments": tc["arguments"],
                "status": "completed",
            },
        })

    # Build final output
    final_output = []
    if full_reasoning:
        final_output.append({
            "type": "reasoning",
            "id": f"rs_{uuid.uuid4().hex[:16]}",
            "status": "completed",
            "content": [{"type": "output_text", "text": full_reasoning, "annotations": []}],
        })
    final_output.append({
        "type": "message",
        "id": msg_id,
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": full_content, "annotations": []}],
    })
    for idx, tc in sorted(tool_calls_accum.items()):
        final_output.append({
            "type": "function_call",
            "id": tc.get("_fc_id", ""),
            "call_id": tc["id"],
            "name": tc["name"],
            "arguments": tc["arguments"],
            "status": "completed",
        })

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
             "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}
    if usage_data:
        usage["input_tokens"] = usage_data.get("prompt_tokens", 0)
        usage["output_tokens"] = usage_data.get("completion_tokens", 0)
        usage["total_tokens"] = usage_data.get("total_tokens", 0)
        usage["input_tokens_details"] = {"cached_tokens": usage_data.get("prompt_tokens_details", {}).get("cached_tokens", 0)}
        usage["output_tokens_details"] = {"reasoning_tokens": usage_data.get("completion_tokens_details", {}).get("reasoning_tokens", 0)}

    # response.completed
    yield _sse({
        "type": "response.completed",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "completed",
            "model": model,
            "output": final_output,
            "usage": usage,
            "error": None,
            "incomplete_details": None,
        },
    })


def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def handle_responses(request):
    """Handle POST /v1/responses"""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": {"message": "Invalid JSON"}}, status=400)

    model = body.get("model", "deepseek-v4-flash")
    is_stream = body.get("stream", False)

    # Convert to Chat Completions
    cc_body = responses_to_chat_completions(body)

    print(f"[PROXY] Request: model={model}, stream={is_stream}, tools={len(body.get('tools', []))}, messages={len(cc_body.get('messages', []))}", flush=True)

    # Get API key from Authorization header
    api_key = _resolve_apikey(request)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"

    async with aiohttp.ClientSession() as session:
        if is_stream:
            # Streaming
            try:
                async with session.post(url, json=cc_body, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        print(f"[PROXY] ERROR from DeepSeek: {error_body[:500]}", flush=True)
                        return web.Response(
                            text=f"data: {json.dumps({'type': 'error', 'error': {'message': error_body}})}\n\n",
                            content_type="text/event-stream",
                        )

                    response = web.StreamResponse(
                        status=200,
                        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"},
                    )
                    await response.prepare(request)

                    async for event in stream_chat_to_responses(resp, model):
                        await response.write(event.encode("utf-8"))

                    await response.write_eof()
                    return response
            except Exception as e:
                print(f"[PROXY] Streaming error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                return web.Response(
                    text=f"data: {json.dumps({'type': 'error', 'error': {'message': str(e)}})}\n\n",
                    content_type="text/event-stream",
                )
        else:
            # Non-streaming
            async with session.post(url, json=cc_body, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return web.json_response({"error": {"message": error_text}}, status=resp.status)

                cc_resp = await resp.json()
                responses_resp = chat_completion_to_responses(cc_resp, model)
                return web.json_response(responses_resp)


async def handle_models(request):
    """Return model list with metadata Codex expects."""
    models = [
        {
            "id": "deepseek-v4-flash",
            "object": "model",
            "created": 1700000000,
            "owned_by": "deepseek",
            "metadata": {
                "context_window": 65536,
                "max_context_window": 65536,
            }
        },
        {
            "id": "deepseek-v4-pro",
            "object": "model",
            "created": 1700000000,
            "owned_by": "deepseek",
            "metadata": {
                "context_window": 65536,
                "max_context_window": 65536,
            }
        },
        {
            "id": "deepseek-chat",
            "object": "model",
            "created": 1700000000,
            "owned_by": "deepseek",
            "metadata": {
                "context_window": 65536,
                "max_context_window": 65536,
            }
        },
        {
            "id": "deepseek-reasoner",
            "object": "model",
            "created": 1700000000,
            "owned_by": "deepseek",
            "metadata": {
                "context_window": 65536,
                "max_context_window": 65536,
            }
        },
    ]
    return web.json_response({"object": "list", "data": models})

async def handle_health(request):
    return web.json_response({"status": "ok", "configured": True})


async def handle_catch_all(request):
    """Forward any other requests to DeepSeek as-is."""
    api_key = _resolve_apikey(request)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": request.content_type or "application/json",
    }

    path = request.path
    url = f"{DEEPSEEK_BASE_URL}{path}"

    async with aiohttp.ClientSession() as session:
        try:
            body = await request.read()
            async with session.request(request.method, url, data=body, headers=headers) as resp:
                resp_body = await resp.read()
                return web.Response(body=resp_body, status=resp.status, content_type=resp.content_type)
        except Exception as e:
            return web.json_response({"error": {"message": str(e)}}, status=502)


def main():
    app = web.Application()
    app.router.add_post("/v1/responses", handle_responses)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)
    app.router.add_route("*", "/{path:.*}", handle_catch_all)

    print(f"DeepSeek Responses Proxy running on http://localhost:{LISTEN_PORT}")
    print(f"Forwarding to {DEEPSEEK_BASE_URL}")
    web.run_app(app, host="0.0.0.0", port=LISTEN_PORT, print=None)


if __name__ == "__main__":
    main()
