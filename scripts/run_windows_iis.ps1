<#
Windows run script for IIS App Pool or service wrapper.

Usage (PowerShell):
  # Set environment for the current session (or App Pool env)
  $env:FLASK_SECRET_KEY = "<your-hex-secret>"
  $env:REFLECTION_UI_DATA_DIR = "C:\\reflection_ui_data"
  # Ensure reflection-mcp is callable (sibling repo example)
  $env:REFLECTION_MCP_CMD = "python ..\\reflection-mcp\\mcp_server.py"

  # Choose a port (IIS reverse proxy forwards to this)
  $env:PORT = "5054"

  # Start via waitress (install once: py -m pip install waitress)
  py -m waitress --host=127.0.0.1 --port=$env:PORT app:app

Notes:
- Run from the repo root where app.py is located.
- App Pool: set the same environment vars in the pool’s configuration or in a wrapper task.
- Verify health: curl http://127.0.0.1:$env:PORT/health
#>

Write-Host "Starting Reflection UI for IIS (Windows)" -ForegroundColor Cyan
if (-not $env:FLASK_SECRET_KEY) {
  $env:FLASK_SECRET_KEY = [System.Guid]::NewGuid().ToString("N")
}
if (-not $env:REFLECTION_UI_DATA_DIR) {
  $env:REFLECTION_UI_DATA_DIR = "$PWD\\.local_context"
}
if (-not $env:PORT) { $env:PORT = "5054" }

Write-Host "Data dir: $env:REFLECTION_UI_DATA_DIR" -ForegroundColor DarkCyan
Write-Host "Port: $env:PORT" -ForegroundColor DarkCyan
if (-not $env:REFLECTION_MCP_CMD) {
  Write-Warning "REFLECTION_MCP_CMD not set; relying on PATH/bin fallbacks"
}

Write-Host "Launching waitress..." -ForegroundColor Green
py -m waitress --host=127.0.0.1 --port=$env:PORT app:app
