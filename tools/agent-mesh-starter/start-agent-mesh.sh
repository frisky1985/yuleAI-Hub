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

# ── Step 2: 启动 MCP Bridge ─────────────────────────────────
title "2/5 MCP Bridge"
BPID=$(pgrep -f "mcp_bridge_server.py" 2>/dev/null | head -1)
if [ -n "$BPID" ]; then
  ok "已在运行 (PID $BPID)"
else
  info "正在启动..."
  nohup python3 "$BRIDGE_DIR/mcp_bridge_server.py" \
    > "$LOG_DIR/bridge.log" 2>&1 &
  echo $! > "$PID_DIR/bridge.pid"
  sleep 2
  if pgrep -f "mcp_bridge_server.py" &>/dev/null; then
    ok "已启动 (PID $(cat "$PID_DIR/bridge.pid"))"
  else
    fail "启动失败，请检查日志: $LOG_DIR/bridge.log"
  fi
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
echo -e "  按 ${BOLD}r${NC} 进入 OpenClaw 对话 · 直接关闭窗口退出"
while true; do
  read -r -n 1 key
  if [ "$key" = "r" ] || [ "$key" = "R" ]; then
    echo ""
    echo -e "${CYAN}→ 进入 OpenClaw 对话...${NC}\n"
    openclaw tui --session main
    # TUI 退出后关闭窗口
    echo ""
    echo -e "${CYAN}对话已结束，关闭窗口...${NC}"
    break
  fi
done

# 关闭 Warp 窗口
osascript -e 'tell application "Warp" to quit' 2>/dev/null || true
exit 0
