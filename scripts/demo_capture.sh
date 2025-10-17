#!/usr/bin/env bash
set -euo pipefail

# Capture end-to-end demo artifacts: cost logs + text export
# Usage: PORT=5054 bash scripts/demo_capture.sh

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-5054}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.local_context/demo_capture}"
mkdir -p "$OUT_DIR"

echo "[demo_capture] Checking health..."
curl -fsS "http://127.0.0.1:${PORT}/health" -o "$OUT_DIR/health.json" || {
  echo "Service not healthy on port ${PORT}" >&2; exit 1;
}

echo "[demo_capture] Attempting summary export (requires active session)..."
if curl -fsS "http://127.0.0.1:${PORT}/summary/export/text" -o "$OUT_DIR/summary.txt"; then
  echo "[demo_capture] Export saved to $OUT_DIR/summary.txt"
else
  echo "[demo_capture] No active session; run a demo first via the UI." >&2
fi

echo "[demo_capture] Copying recent cost logs if present..."
DATA_DIR="${REFLECTION_UI_DATA_DIR:-$HOME/.reflection_ui}"
if [ -d "$DATA_DIR/cost_logs" ]; then
  find "$DATA_DIR/cost_logs" -type f -name '*_costs.json' -mtime -1 -exec cp {} "$OUT_DIR" \; || true
fi
echo "[demo_capture] Done. Artifacts in $OUT_DIR"

