# Server Validation & Handoff

1. Confirm reflection-mcp path
   - Verify `REFLECTION_MCP_CMD` resolves (`reflection-mcp` on PATH or `python ..\\reflection-mcp\\mcp_server.py`).
2. Start UI behind IIS
   - Windows: `scripts\\run_windows_iis.ps1` binds to `127.0.0.1:<PORT>`.
   - Configure URL Rewrite + ARR to proxy site traffic to the port.
3. Health checks
   - `GET /health` returns `{ok:true}`.
4. Demo validation
   - Create a reflection session through the UI.
   - Open summary and click “Copy Full Report (text)” or download via `GET /summary/export/text`.
5. Collect artifacts
   - Save `export/text` output, cost logs from `${REFLECTION_UI_DATA_DIR}/cost_logs/`, and session JSON from `${REFLECTION_UI_DATA_DIR}/reflection_sessions/`.
6. Timeouts & retries
   - If backend is slow, set `REFLECTION_MCP_TIMEOUT` (default 60) and `REFLECTION_MCP_RETRIES` (default 1).

Handoff Checklist
- [ ] Environment variables set and persisted for the App Pool
- [ ] Reverse proxy configured and tested
- [ ] `/health` reachable
- [ ] Demo session completed
- [ ] Text export collected
- [ ] Logs archived for review

