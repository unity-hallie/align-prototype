import json
import os
from pathlib import Path

import importlib


ROOT = Path(__file__).resolve().parents[1]
AUTH_CLI = str(ROOT / "bin" / "auth-mcp")


def mcp_call(cli_path: str, name: str, arguments: dict) -> dict:
    import subprocess
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    res = subprocess.run([cli_path], input=json.dumps(payload) + "\n", capture_output=True, text=True, cwd=str(ROOT), env=os.environ.copy())
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip())
    text = (((out.get('result') or {}).get('content') or [{}])[0]).get('text')
    return json.loads(text) if text else {}


def test_settings_saves_key_via_auth_mcp(monkeypatch, tmp_path):
    # Route under test: POST /settings with api_key should save via auth-mcp
    monkeypatch.setenv("AUTH_MCP_CMD", AUTH_CLI)
    # Use a temp data dir to avoid writing to user home
    monkeypatch.setenv("REFLECTION_UI_DATA_DIR", str(tmp_path / "data"))

    # Import the app module fresh with env set
    mod = importlib.import_module('reflection_ui.app')
    app = getattr(mod, 'app')
    client = app.test_client()

    # Save key
    resp = client.post('/settings', data={'api_key': 'sk-ui-123'}, follow_redirects=True)
    assert resp.status_code == 200

    # Ensure key is stored in the vault
    got = mcp_call(AUTH_CLI, "get_secret", {"name": "openai_api_key"})
    assert got.get("found") is True
    assert got.get("value") == "sk-ui-123"

