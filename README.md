Reflection UI
=============

Standalone Flask UI for Reflection MCP. Uses a shared local auth-mcp vault for API key storage (optional) and a decoupled data directory for sessions, logs, and templates.

Quick Start
-----------

1. **Install dependencies**:
   ```bash
   cd reflection_ui
   pip install -r requirements.txt
   ```

2. **Set OpenAI API key** (choose one):
   - Via auth-mcp (recommended): `export AUTH_MCP_CMD=/path/to/auth-mcp`
   - Direct environment variable: `export OPENAI_API_KEY=sk-...`

3. **Run the UI**:
   ```bash
   bash start_ui.sh --port 5054
   ```
   The script will auto-find a free port if 5054 is busy and test that reflection-mcp is available.

Environment Variables
--------------------

- `AUTH_MCP_CMD`: path to auth-mcp CLI for secrets (recommended)
- `REFLECTION_UI_DATA_DIR`: data root (default: `~/.reflection_ui`)
- `FLASK_SECRET_KEY`: Flask session key (auto-generated if not set)
- `OPENAI_API_KEY`: used only if auth-mcp is not configured
- `PORT`: override UI port (start script has `--port`)

Data Directories
---------------

Under `REFLECTION_UI_DATA_DIR` (default: `~/.reflection_ui`):
- `reflection_sessions/`: saved session JSON
- `cost_logs/`: cost logs from MCP summaries
- `reflection_templates/`: user-saved designer templates
- `canvas_cache/`: optional offline Canvas cache files

Templates
---------

- Bundled examples read from repo `docs/examples/assignment_templates`
- Local templates are read from `reflection_templates/` in the data dir

Secrets Management
------------------

- **Recommended**: Set `AUTH_MCP_CMD` to use auth-mcp vault (shared with other tools)
- **Fallback**: `.local_context/secrets.env` in the repo (legacy)
- **Direct**: `OPENAI_API_KEY` environment variable

Dependencies
-----------

**reflection_ui**:
- Flask >= 3.0.0
- requests >= 2.31.0
- Python stdlib (json, os, sys, subprocess, pathlib, time)

**reflection_mcp** (backend):
- Python stdlib only (no external dependencies)
- Uses auth-mcp for API key storage if available

Deployment (Ai2/Server)
-----------------------

### Prerequisites
- Python 3.9+
- Access to OpenAI API
- Optional: auth-mcp for key management

### Production Setup

1. **Clone and setup**:
   ```bash
   git clone <repo-url>
   cd reflection_ui
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   export REFLECTION_UI_DATA_DIR=/var/lib/reflection_ui  # or your preferred path
   export OPENAI_API_KEY=sk-...  # or use AUTH_MCP_CMD
   ```

3. **Create data directory**:
   ```bash
   mkdir -p "$REFLECTION_UI_DATA_DIR"/{reflection_sessions,cost_logs,reflection_templates,canvas_cache}
   ```

4. **Run with production WSGI server**:
   ```bash
   # Using gunicorn (recommended)
   pip install gunicorn
   cd reflection_ui
   gunicorn -w 4 -b 0.0.0.0:5054 app:app

   # Or using waitress
   pip install waitress
   waitress-serve --host=0.0.0.0 --port=5054 app:app
   ```

5. **Optional: Run as systemd service**:
   ```bash
   # Create /etc/systemd/system/reflection-ui.service
   [Unit]
   Description=Reflection MCP UI
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/reflection_ui
   Environment="FLASK_SECRET_KEY=your-secret-key"
   Environment="REFLECTION_UI_DATA_DIR=/var/lib/reflection_ui"
   Environment="OPENAI_API_KEY=your-key"
   ExecStart=/usr/bin/gunicorn -w 4 -b 0.0.0.0:5054 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable reflection-ui
   sudo systemctl start reflection-ui
   ```

### Testing the Deployment

```bash
# Health check - main page should load
curl http://localhost:5054/

# Test settings page
curl http://localhost:5054/settings

# Test designer page
curl http://localhost:5054/designer

# Test reflection workflow
curl -X POST http://localhost:5054/start_reflection \
  -H "Content-Type: application/json" \
  -d '{"student_id": "test_001", "assignment_type": "test", "assignment_context": "Testing deployment"}'
```

### Canvas Integration (Optional)

If you want Canvas assignment import functionality:

1. Get Canvas API token from your institution
2. Set via auth-mcp or UI settings page
3. Cache will be stored in `${REFLECTION_UI_DATA_DIR}/canvas_cache/`

### Monitoring and Logs

- Cost logs: `${REFLECTION_UI_DATA_DIR}/cost_logs/`
- Session data: `${REFLECTION_UI_DATA_DIR}/reflection_sessions/`
- Flask logs: stdout/stderr (capture with systemd or supervisor)

Migration Notes
---------------

- Previously: UI stored data under repo `.local_context/`
- Now: set `REFLECTION_UI_DATA_DIR` to keep artifacts outside the repo (recommended)
- If you have existing Canvas cache in `.local_context/cache/canvas`, copy it into `${REFLECTION_UI_DATA_DIR}/canvas_cache`

Text Export (for Testing)
------------------------

- Export full reflection summary as plaintext: `GET /summary/export/text`
- Copy from UI: "Copy Full Report (text)" button on the summary page
- Use this export to test outputs locally and on servers (no SMS integration required)

Reflection MCP Command Resolution
---------------------------------

The UI discovers `reflection-mcp` via:
1. `REFLECTION_MCP_CMD` env override (e.g., `../reflection-mcp/bin/reflection-mcp`)
2. `bin/reflection-mcp` (in this repo)
3. `bin/reflection-mcp-service` (legacy alias)
4. `../reflection-mcp/bin/reflection-mcp` (sibling repo)
5. `reflection-mcp` on PATH
6. Windows fallback: `python ..\\reflection-mcp\\mcp_server.py`

Windows / IIS Notes
-------------------

- Prefer a reverse proxy to a persistent process (e.g., run Gunicorn/Waitress behind IIS).
- Ensure the service user has permission to run `reflection-mcp` and access data dir.
- Set `REFLECTION_MCP_CMD` explicitly in the App Pool environment if PATH is not shared.

Demo Readiness (Local + IIS)
----------------------------

- Use `scripts/run_windows_iis.ps1` on Windows. Set `PORT`, `REFLECTION_MCP_CMD`, `FLASK_SECRET_KEY`, and `REFLECTION_UI_DATA_DIR`.
- Expose only via reverse proxy: bind UI to `127.0.0.1:<PORT>` and terminate TLS at IIS.
- Healthcheck: `GET /health` returns `{ok:true}` for monitoring and proxy checks.

Reverse Proxy Notes
-------------------

- Map IIS site route `/` → `http://127.0.0.1:<PORT>/` using URL Rewrite + ARR.
- Allow only expected methods (GET/POST) and set timeouts to >= 60s for reflection operations.
- Preserve headers; do not compress JSON bodies at the proxy layer if not needed.

Deployment Checklist
--------------------

- [ ] Python 3.9+ and waitress (Windows) or gunicorn (Linux) installed
- [ ] Set `FLASK_SECRET_KEY` (hex), `REFLECTION_UI_DATA_DIR`, and `REFLECTION_MCP_CMD`
- [ ] Start the UI (Windows: `scripts/run_windows_iis.ps1`, Linux: gunicorn)
- [ ] Configure IIS reverse proxy to `127.0.0.1:<PORT>`
- [ ] Verify `GET /health` and settings page load
- [ ] Run a sample reflection and verify `GET /summary/export/text`

One-Command Local Demo
----------------------

- Run: `bash scripts/local_demo.sh`
  - Installs dependencies
  - Auto-detects `reflection-mcp` and persists `REFLECTION_MCP_CMD` in `.env`
  - Starts the UI
- Then open Settings to paste your `OPENAI_API_KEY` (stored in `.env`).
