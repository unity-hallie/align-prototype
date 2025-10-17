import os
import tempfile
from pathlib import Path

from utils.mcp_discovery import resolve_reflection_cmd


def test_no_env_no_server_returns_none(tmp_path: Path, monkeypatch):
    # Simulate repo without local server
    repo_root = tmp_path
    (repo_root / 'bin').mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv('REFLECTION_MCP_CMD', raising=False)
    assert resolve_reflection_cmd(repo_root) is None


def test_env_cmd_existing_file_wins(tmp_path: Path, monkeypatch):
    repo_root = tmp_path
    (repo_root / 'bin').mkdir(parents=True, exist_ok=True)
    # Create a temp executable
    cmd = tmp_path / 'fake-mcp'
    cmd.write_text('#!/bin/sh\nexit 0\n')
    cmd.chmod(0o755)
    monkeypatch.setenv('REFLECTION_MCP_CMD', str(cmd))
    assert resolve_reflection_cmd(repo_root) == str(cmd)

