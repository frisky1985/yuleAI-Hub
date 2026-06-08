#!/usr/bin/env python3
"""
MCP Bridge v2 — Cross-agent collaboration server.

Optimized for fast response: long tasks submit in background,
returning a task_id immediately instead of blocking.

Tools:
  agent-status     — Quick check all agents (instant)
  agent-chat       — Send prompt to another agent (sync, shorter timeout)
  agent-delegate   — Delegate task (async with task_id)
  task-result      — Poll for completed task result
  task-list        — List recent tasks and their status
  context-read     — Read shared context
  context-write    — Write shared context
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

# ── config ─────────────────────────────────────────────────────────────────
BRIDGE_DIR = pathlib.Path(__file__).resolve().parent
WORKSPACE = pathlib.Path(os.environ.get("BRIDGE_WORKSPACE", BRIDGE_DIR / "workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)
TASKS_DIR = WORKSPACE / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT_FILE = WORKSPACE / "context.json"

AGENTS = {
    "openclaw":  {"check": ["openclaw", "--version"]},
    "hermes":    {"check": ["hermes", "--version"]},
    "qodercli":  {"check": ["qodercli", "--version"]},
}

MAX_SYNC_SEC = 8   # fast tasks finish synchronously
MAX_ASYNC_SEC = 300  # background timeout


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Task runner (background) ──────────────────────────────────────────────

def _run_agent(agent: str, prompt: str, task_id: str) -> None:
    """Run agent task in background and write result to task file."""
    meta = {"task_id": task_id, "agent": agent, "prompt": prompt,
            "status": "running", "started_at": _now()}
    _write_json(TASKS_DIR / f"{task_id}.json", meta)

    try:
        if agent == "hermes":
            p = subprocess.run(["hermes", "-z", prompt, "--yolo"],
                               capture_output=True, text=True, timeout=MAX_ASYNC_SEC)
            out = p.stdout.strip() or p.stderr.strip()
        elif agent == "qodercli":
            p = subprocess.run(["qodercli", "-p", "--dangerously-skip-permissions", prompt],
                               capture_output=True, text=True, timeout=MAX_ASYNC_SEC)
            out = p.stdout.strip() or p.stderr.strip()
        elif agent == "openclaw":
            p = subprocess.run(["openclaw", "session", "start", "--prompt", prompt],
                               capture_output=True, text=True, timeout=MAX_ASYNC_SEC)
            out = p.stdout.strip() or p.stderr.strip()
        else:
            out = f"Unknown agent: {agent}"

        result = {
            "task_id": task_id, "agent": agent,
            "status": "completed", "output": out,
            "finished_at": _now()
        }
    except subprocess.TimeoutExpired:
        result = {"task_id": task_id, "agent": agent,
                  "status": "timeout", "output": "timed out"}
    except FileNotFoundError as e:
        result = {"task_id": task_id, "agent": agent,
                  "status": "error", "output": str(e)}

    _write_json(TASKS_DIR / f"{task_id}.json", result)
    log(f"[{_now()}] Task {task_id} ({agent}) → {result['status']}")


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ── MCP Server ─────────────────────────────────────────────────────────────

class MCPServer:
    def __init__(self):
        self.tools = {
            "agent-status": {
                "name": "agent-status",
                "description": "Check if each agent is available (instant, <1s)",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "agent-chat": {
                "name": "agent-chat",
                "description": "Quick chat with another agent (waits up to 8s, for fast questions)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": ["hermes", "qodercli"],
                                  "description": "Target agent"},
                        "prompt": {"type": "string", "description": "Quick question"},
                    },
                    "required": ["agent", "prompt"],
                },
            },
            "agent-delegate": {
                "name": "agent-delegate",
                "description": "Delegate a task to another agent (returns task_id immediately, run in background)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": ["hermes", "qodercli", "openclaw"],
                                  "description": "Target agent"},
                        "task": {"type": "string", "description": "Task description"},
                    },
                    "required": ["agent", "task"],
                },
            },
            "task-result": {
                "name": "task-result",
                "description": "Check a delegated task's result by task_id",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID from agent-delegate"},
                    },
                    "required": ["task_id"],
                },
            },
            "task-list": {
                "name": "task-list",
                "description": "List recent delegated tasks and their status",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "context-read": {
                "name": "context-read",
                "description": "Read shared context from the bridge workspace",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Context key (optional, omit to read all)"},
                    },
                },
            },
            "context-write": {
                "name": "context-write",
                "description": "Write shared context data for other agents to read",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Context key"},
                        "value": {"type": "string", "description": "JSON value"},
                    },
                    "required": ["key", "value"],
                },
            },
        }

    # ── MCP protocol ────────────────────────────────────────────────────
    def _read_message(self) -> dict | None:
        try:
            content_length = 0
            while True:
                line = sys.stdin.readline()
                if not line: return None
                line = line.strip()
                if not line: break
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
            if content_length == 0: return None
            body = sys.stdin.read(content_length)
            return json.loads(body) if body else None
        except (json.JSONDecodeError, EOFError, ValueError):
            return None

    def _send(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        sys.stdout.write(f"Content-Length: {len(data)}\r\n\r\n{data}")
        sys.stdout.flush()

    def _result(self, req_id, text):
        self._send({
            "jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": text}],
            },
        })

    # ── Tool handlers ───────────────────────────────────────────────────
    def _handle_agent_status(self):
        results = {}
        for name, info in AGENTS.items():
            try:
                p = subprocess.run(info["check"], capture_output=True, text=True, timeout=5)
                results[name] = {"available": p.returncode == 0,
                                 "version": p.stdout.strip()[:60] or p.stderr.strip()[:60]}
            except Exception as e:
                results[name] = {"available": False, "error": str(e)}
        return json.dumps(results, ensure_ascii=False, indent=2)

    def _handle_agent_chat(self, agent: str, prompt: str) -> str:
        """Quick chat — try sync first, up to 8s."""
        try:
            if agent == "hermes":
                p = subprocess.run(["hermes", "-z", prompt, "--yolo"],
                                   capture_output=True, text=True, timeout=MAX_SYNC_SEC)
            elif agent == "qodercli":
                p = subprocess.run(["qodercli", "-p", "--dangerously-skip-permissions", prompt],
                                   capture_output=True, text=True, timeout=MAX_SYNC_SEC)
            else:
                return json.dumps({"error": f"agent-chat doesn't support '{agent}'"})
            out = p.stdout.strip() or p.stderr.strip()
            return json.dumps({"agent": agent, "output": out[:3000], "exit_code": p.returncode},
                              ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({"status": "timeout",
                "hint": f"{agent} didn't respond in {MAX_SYNC_SEC}s. Use agent-delegate for async."})
        except FileNotFoundError:
            return json.dumps({"error": f"{agent} not found"})

    def _handle_delegate(self, agent: str, task: str) -> str:
        import secrets
        task_id = f"task_{secrets.token_hex(4)}"
        task_file = TASKS_DIR / f"{task_id}.json"
        _write_json(task_file, {"task_id": task_id, "agent": agent, "status": "running", "started_at": _now()})
        runner = "/Users/ingeek/.local/bin/agent-runner"
        subprocess.Popen(["nohup", runner, agent, task_id, task],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return json.dumps({"status": "queued","task_id": task_id,"agent": agent}, ensure_ascii=False)

    def _handle_task_result(self, task_id: str) -> str:
        data = _read_json(TASKS_DIR / f"{task_id}.json")
        if not data:
            return json.dumps({"error": f"Task '{task_id}' not found"})
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _handle_task_list(self) -> str:
        tasks = []
        for f in sorted(TASKS_DIR.glob("task_*.json"), reverse=True)[:10]:
            data = _read_json(f)
            if data:
                tasks.append({"task_id": data.get("task_id"), "agent": data.get("agent"),
                              "status": data.get("status"), "prompt": (data.get("prompt","")[:60])})
        return json.dumps(tasks, ensure_ascii=False, indent=2)

    def _handle_context_read(self, key: str = "") -> str:
        ctx = _read_json(CONTEXT_FILE) or {}
        if key:
            return json.dumps({key: ctx.get(key)}, ensure_ascii=False, indent=2)
        return json.dumps(ctx, ensure_ascii=False, indent=2)

    def _handle_context_write(self, key: str, value: str) -> str:
        ctx = _read_json(CONTEXT_FILE) or {}
        try:
            ctx[key] = json.loads(value) if value.startswith(("{", "[")) else value
        except json.JSONDecodeError:
            ctx[key] = value
        _write_json(CONTEXT_FILE, ctx)
        return json.dumps({"status": "stored", "key": key})

    # ── Router ──────────────────────────────────────────────────────────
    def handle_request(self, msg: dict) -> dict | None:
        req_id, method, params = msg.get("id"), msg.get("method",""), msg.get("params",{})

        if method == "initialize":
            return {"jsonrpc":"2.0","id":req_id,"result":{
                "protocolVersion":"2024-11-05","capabilities":{"tools":{}},
                "serverInfo":{"name":"mcp-bridge","version":"2.0.0"}}}
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return {"jsonrpc":"2.0","id":req_id,"result":{}}

        if method == "tools/list":
            return {"jsonrpc":"2.0","id":req_id,"result":{"tools":list(self.tools.values())}}

        if method == "tools/call":
            tn = params.get("name","")
            ta = params.get("arguments",{})
            handler_map = {
                "agent-status":    lambda: self._handle_agent_status(),
                "agent-chat":      lambda: self._handle_agent_chat(ta.get("agent",""), ta.get("prompt","")),
                "agent-delegate":  lambda: self._handle_delegate(ta.get("agent",""), ta.get("task","")),
                "task-result":     lambda: self._handle_task_result(ta.get("task_id","")),
                "task-list":       lambda: self._handle_task_list(),
                "context-read":    lambda: self._handle_context_read(ta.get("key","")),
                "context-write":   lambda: self._handle_context_write(ta.get("key",""), ta.get("value","")),
            }
            handler = handler_map.get(tn)
            if not handler:
                return {"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"Unknown tool: {tn}"}}
            text = handler()
            return {"jsonrpc":"2.0","id":req_id,"result":{"content":[{"type":"text","text":text}]}}

        return {"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"Unknown method: {method}"}}

    def run(self):
        log(f"[{_now()}] 🚀 MCP Bridge v2 ready")
        while True:
            msg = self._read_message()
            if msg is None: break
            resp = self.handle_request(msg)
            if resp: self._send(resp)


def main():
    server = MCPServer()
    try: server.run()
    except KeyboardInterrupt:
        log("👋 MCP Bridge stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
