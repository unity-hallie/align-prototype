#!/usr/bin/env bash
set -euo pipefail

# One-command local demo runner for align-prototype
# - Installs deps
# - Auto-detects reflection-mcp and persists REFLECTION_MCP_CMD in .env
# - Starts the UI

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$ROOT_DIR"

echo "[local_demo] Installing Python dependencies..."
python3 -m pip install -r requirements.txt >/dev/null

ENV_FILE="$ROOT_DIR/.env"
touch "$ENV_FILE"

# Helper to upsert a key=value in .env
upsert_env() {
  local key="$1"; shift
  local value="$1"; shift
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

if [ -z "${REFLECTION_MCP_CMD:-}" ]; then
  # Detect common options (avoid selecting our own shim to prevent recursion)
  if [ -x "$ROOT_DIR/../reflection-mcp/bin/reflection-mcp" ]; then
    DETECTED_CMD="$ROOT_DIR/../reflection-mcp/bin/reflection-mcp"
  elif command -v reflection-mcp >/dev/null 2>&1; then
    DETECTED_CMD="reflection-mcp"
  elif [ "$(uname -s)" = "MINGW" ] || [ "$(uname -s)" = "CYGWIN" ] || [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    # Basic Windows detection fallback
    if [ -f "$ROOT_DIR/../reflection-mcp/mcp_server.py" ]; then
      DETECTED_CMD="python ..\\reflection-mcp\\mcp_server.py"
    fi
  fi
  if [ -n "${DETECTED_CMD:-}" ]; then
    echo "[local_demo] Detected reflection-mcp: $DETECTED_CMD"
    export REFLECTION_MCP_CMD="$DETECTED_CMD"
    upsert_env "REFLECTION_MCP_CMD" "$DETECTED_CMD"
  else
    echo "[local_demo] Could not auto-detect reflection-mcp. You may set REFLECTION_MCP_CMD in .env or run start_ui with --skip-mcp-check."
  fi
fi

if ! grep -q '^OPENAI_API_KEY=' "$ENV_FILE"; then
  echo "[local_demo] Note: OPENAI_API_KEY not found in .env. You can set it via the Settings page."
fi

echo "[local_demo] Launching UI..."
exec bash start_ui.sh "$@"
