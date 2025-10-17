#!/bin/bash
set -euo pipefail

echo "🧠 Starting Reflection MCP Testing UI..."
cd "$(dirname "$0")"

# Args: --no-browser, --skip-mcp-check, --port N
NO_BROWSER=0
SKIP_MCP=0
CLI_PORT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-browser) NO_BROWSER=1; shift ;;
    --skip-mcp-check) SKIP_MCP=1; shift ;;
    --port) CLI_PORT=${2:-}; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

# Do not source .env here to avoid shell parsing issues with comments.
# The Python app loads .env and .local_context/secrets.env safely at startup.
ROOT_DIR="$(cd .. && pwd)"

# Resolve desired port (default 5004 or use PORT env or --port)
DESIRED_PORT="${CLI_PORT:-${PORT:-5004}}"
PORT_TO_USE="$DESIRED_PORT"

is_port_free() {
  local p=$1
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -i tcp:"$p" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v nc >/dev/null 2>&1; then
    ! nc -z localhost "$p" >/dev/null 2>&1
  else
    return 0
  fi
}

if ! is_port_free "$PORT_TO_USE"; then
  echo "⚠️  Port $PORT_TO_USE is busy. Searching for a free port..."
  for delta in $(seq 1 10); do
    cand=$((DESIRED_PORT + delta))
    if is_port_free "$cand"; then PORT_TO_USE="$cand"; break; fi
  done
  if [[ "$PORT_TO_USE" != "$DESIRED_PORT" ]]; then
    echo "➡️  Using port $PORT_TO_USE instead of $DESIRED_PORT"
  else
    echo "❌ No free port found in $DESIRED_PORT-$((DESIRED_PORT+10)). Set --port or free a port."
    exit 1
  fi
fi

export PORT="$PORT_TO_USE"
echo "→ UI: http://localhost:$PORT"

# MCP server check (optional) using direct resolution
if [[ "$SKIP_MCP" -eq 0 ]]; then
  echo "Testing reflection MCP server..."
  MCP_CMD=""; MCP_CWD=""
  if [[ -n "${REFLECTION_MCP_CMD:-}" ]]; then
    MCP_CMD="$REFLECTION_MCP_CMD"; MCP_CWD=""
  elif [[ -x "../reflection-mcp/bin/reflection-mcp" ]]; then
    MCP_CMD="./bin/reflection-mcp"; MCP_CWD="../reflection-mcp"
  elif command -v reflection-mcp >/dev/null 2>&1; then
    MCP_CMD="reflection-mcp"; MCP_CWD=""
  elif [[ -f "../reflection-mcp/mcp_server.py" ]]; then
    MCP_CMD="python3 mcp_server.py"; MCP_CWD="../reflection-mcp"
  fi
  if [[ -z "$MCP_CMD" ]]; then
    echo "❌ reflection-mcp command not found via REFLECTION_MCP_CMD, sibling repo, or PATH."
    echo "   Tip: set REFLECTION_MCP_CMD, install sibling repo, or put reflection-mcp on PATH."
    exit 1
  fi
  TEST_JSON='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
  if [[ -n "$MCP_CWD" ]]; then
    if ! (cd "$MCP_CWD" && PYTHONPATH="$PWD" eval "echo '$TEST_JSON' | $MCP_CMD" >/dev/null 2>&1); then
      echo "❌ reflection-mcp not responding."
      echo "   Tried with CWD='$MCP_CWD' CMD='$MCP_CMD'"
      echo "   Tip: set REFLECTION_MCP_CMD (e.g., 'python3 ../reflection-mcp/mcp_server.py'), install sibling repo, or use PATH (reflection-mcp)."
      exit 1
    fi
  else
    if ! eval "echo '$TEST_JSON' | $MCP_CMD" >/dev/null 2>&1; then
      echo "❌ reflection-mcp not responding."
      echo "   Tried CMD='$MCP_CMD'"
      echo "   Tip: set REFLECTION_MCP_CMD, install sibling repo, or use PATH (reflection-mcp)."
      exit 1
    fi
  fi
  echo "✅ Reflection MCP server working"
else
  echo "Skipping MCP server check (per flag)"
fi

# Key presence hint
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "⚠️ No OPENAI_API_KEY detected. The UI will show a key-required banner; use Settings to save a key."
else
  echo "✅ OPENAI_API_KEY detected (masked). You can test it in Settings."
fi

# Start Flask app
export FLASK_ENV=${FLASK_ENV:-development}
python3 app.py &
FLASK_PID=$!
sleep 2

# Optionally open browser
if [[ "$NO_BROWSER" -eq 0 ]]; then
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:$PORT" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:$PORT" || true
  else
    echo "🌐 Open browser to: http://localhost:$PORT"
  fi
else
  echo "⏩ Not opening browser (--no-browser)"
fi

echo "Press Ctrl+C to stop the server"
wait $FLASK_PID
