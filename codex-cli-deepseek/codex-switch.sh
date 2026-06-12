#!/bin/bash
# Codex Switch - macOS version
# Start DeepSeek proxy and launch Codex CLI

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEEPSEEK_PROXY="$SCRIPT_DIR/deepseek-proxy.js"
PROXY_PORT=3333
PID_FILE="/tmp/codex-proxy.pid"
DEBUG=false

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --debug) DEBUG=true ;;
    --kill)  MODE=kill ;;
    status)  MODE=status ;;
    *)       MODEL="$1" ;;
  esac
  shift
done

# Load DeepSeek API key
if [ -f ~/.hermes/.env ]; then
  source ~/.hermes/.env 2>/dev/null
fi

if [ -z "$DEEPSEEK_API_KEY" ]; then
  echo "ERROR: DEEPSEEK_API_KEY not set"
  exit 1
fi
export DEEPSEEK_API_KEY

check_proxy() {
  if [ -f "$PID_FILE" ]; then
    local PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_proxy() {
  if check_proxy; then
    echo "  Proxy already running (PID $(cat $PID_FILE))"
    return 0
  fi
  local DEBUG_FLAG=""
  if $DEBUG; then DEBUG_FLAG="--debug"; fi
  nohup node "$DEEPSEEK_PROXY" $DEBUG_FLAG > /tmp/codex-proxy.log 2>&1 &
  echo $! > "$PID_FILE"
  sleep 2
  if check_proxy; then
    echo "  Proxy started (PID $(cat $PID_FILE))"
    return 0
  else
    echo "  ERROR: Proxy failed to start"
    return 1
  fi
}

stop_proxy() {
  if [ -f "$PID_FILE" ]; then
    local PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    echo "  Proxy stopped"
  fi
}

case "${MODE:-}" in
  kill)
    echo "Stopping proxy..."
    stop_proxy
    exit 0
    ;;
  status)
    if check_proxy; then
      echo "  Proxy: RUNNING (PID $(cat $PID_FILE))"
      curl -s http://127.0.0.1:$PROXY_PORT/stats 2>/dev/null || echo "  Stats: unavailable"
    else
      echo "  Proxy: STOPPED"
    fi
    exit 0
    ;;
esac

echo "╔══════════════════════════════════════════╗"
echo "║     Codex Switch - DeepSeek Backend      ║"
echo "╚══════════════════════════════════════════╝"

start_proxy || exit 1

# Launch Codex
export CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX=1
exec codex
