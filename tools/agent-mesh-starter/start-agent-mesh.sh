#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Agent Mesh 一键启动 → 进入 OpenClaw 对话
# 双击此文件 → 自动启动 Warp → 拉起所有 Agents → 可进入对话
# ─────────────────────────────────────────────────────────────

# 让脚本在 Finder 双击时保持在 Warp 中打开
if [ -z "$TERM_PROGRAM" ] || [ "$TERM_PROGRAM" != "WarpTerminal" ]; then
  exec open -a Warp "$0"
  exit 0
fi

# ── 路径 ────────────────────────────────────────────────────
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$HOME/.local/bin:$PATH"
export HOME="$HOME"

BRIDGE_DIR="$HOME/.openclaw/mcp-bridge"
PID_DIR="$BRIDGE_DIR/pids"
LOG_DIR="$BRIDGE_DIR/logs"
WORKSPACE="$BRIDGE_DIR/workspace"
mkdir -p "$PID_DIR" "$LOG_DIR" "$WORKSPACE"

GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
CYAN='\033[36m'
BOLD='\033[1m'
NC='\033[0m'

ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; }
info()  { echo -e "  ${CYAN}→${NC} $1"; }
title() { echo -e "\n${BOLD}── $1 ──${NC}"; }

refresh_status() {
  ~/.openclaw/mcp-bridge/agent-keepalive.sh 2>/dev/null || true
  echo -e "\n${CYAN}── 当前状态 ──${NC}"
  cat "$WORKSPACE/keepalive-state.json" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
  echo ""
}

clear
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║      🤖 Agent Mesh 一键启动          ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: 检测基础环境 ────────────────────────────────────
title "1/5 检测环境"
for cmd in openclaw hermes qodercli python3; do
  if command -v "$cmd" &>/dev/null; then
    ok "$cmd → $(command -v "$cmd")"
  else
    fail "$cmd → 未安装"
  fi
done

# ── Step 2: MCP Bridge ─────────────────────────────────────
# MCP Bridge 是 stdio 模式，由 OpenClaw 按需自动启动
# 这里只做快速连通性测试
BRIDGE_TEST=$(python3 -c "
import subprocess, json, time
p = subprocess.Popen(
    ['python3', '$BRIDGE_DIR/mcp_bridge_server.py'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, bufsize=0
)
time.sleep(0.2)
body = json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
req = f'Content-Length: {len(body)}\
\
\
\
{body}'
try:
    out, _ = p.communicate(input=req, timeout=5)
    if 'tools' in out: print('ok')
except:
    pass
" 2>/dev/null)
if [ "$BRIDGE_TEST" = "ok" ]; then
  title "2/5 MCP Bridge"
  ok "就绪"
fi

# ── Step 3: 启动 Gateway ────────────────────────────────────
title "3/5 Gateway"
GW_RUNNING=$(openclaw gateway status 2>/dev/null | grep -c "Runtime: running" || true)
if [ "$GW_RUNNING" -ge 1 ]; then
  ok "已在运行 (PID $(openclaw gateway status 2>/dev/null | grep -o 'pid [0-9]*' | head -1))"
else
  info "正在启动..."
  openclaw gateway start 2>/dev/null
  sleep 3
  GW_RUNNING=$(openclaw gateway status 2>/dev/null | grep -c "Runtime: running" || true)
  if [ "$GW_RUNNING" -ge 1 ]; then
    ok "Gateway 已启动"
  else
    info "尝试安装服务..."
    openclaw gateway install 2>/dev/null
    openclaw gateway start 2>/dev/null
    sleep 3
    if openclaw gateway status 2>/dev/null | grep -q "Runtime: running"; then
      ok "Gateway 安装并启动成功"
    else
      fail "Gateway 启动失败，请运行 openclaw doctor"
    fi
  fi
fi

# ── Step 4: 检测 Agent 状态 ─────────────────────────────────
title "4/5 Agent 状态"
for agent in "OpenClaw" "Hermes" "QoderCLI"; do
  cmd=$(echo "$agent" | tr '[:upper:]' '[:lower:]')
  if command -v "$cmd" &>/dev/null; then
    ok "$agent → 就绪"
  else
    fail "$agent → 未找到"
  fi
done

# ── Step 5: 验证整体状态 ────────────────────────────────────
title "5/5 最终验证"
sleep 1
openclaw gateway status 2>/dev/null | grep -E "Runtime:|Dashboard:" | sed 's/^/  /'
echo ""
echo -e "  Dashboard: ${CYAN}http://127.0.0.1:18789/${NC}"

# 跑一次 keepalive 刷新状态
refresh_status

echo ""
echo -e "${GREEN}${BOLD}✅ Agent Mesh 已就绪${NC}"
echo ""

# ── 提示进入对话 ────────────────────────────────────────────
echo -e "  ${BOLD}[r]${NC} 进入 OpenClaw 对话   ${BOLD}[q]${NC} 退出"
while true; do
  read -r -n 1 key
  if [ "$key" = "r" ] || [ "$key" = "R" ]; then
    echo ""
    echo -e "${CYAN}→ 进入 OpenClaw 对话...${NC}\n"
    GW_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.openclaw/openclaw.json'))['gateway']['auth']['token'])" 2>/dev/null)
    openclaw tui --session main ${GW_TOKEN:+--token "$GW_TOKEN"}
    # TUI 退出后关闭窗口
    echo ""
    echo -e "${CYAN}对话已结束，关闭窗口...${NC}"
    break
  elif [ "$key" = "q" ] || [ "$key" = "Q" ]; then
    echo ""
    echo -e "  ${CYAN}退出启动器${NC}"
    exit 0
  fi
done

# 关闭 Warp 窗口
osascript -e 'tell application "Warp" to quit' 2>/dev/null || true
exit 0
