# Deployment on Windows IIS (Demo)

This guide assumes `reflection-mcp` is already available on the server.

1. Install Python 3.9+ and Waitress: `py -m pip install waitress`
2. Clone this repo and the sibling `reflection-mcp` repo.
3. Configure environment (App Pool or wrapper):
   - `FLASK_SECRET_KEY` (hex)
   - `REFLECTION_UI_DATA_DIR` (e.g., `C:\\reflection_ui_data`)
   - `REFLECTION_MCP_CMD` (e.g., `python ..\\reflection-mcp\\mcp_server.py`)
   - `PORT` (e.g., `5054`)
4. Start the UI using `scripts\\run_windows_iis.ps1`.
5. Configure IIS reverse proxy to `http://127.0.0.1:<PORT>/` via URL Rewrite + ARR.
6. Verify health at `/health` and run a demo reflection; test `GET /summary/export/text`.

Troubleshooting:
- If MCP calls time out, set `REFLECTION_MCP_TIMEOUT` (seconds) and `REFLECTION_MCP_RETRIES`.
- Ensure the service user has access to `reflection-mcp` and data directories.

