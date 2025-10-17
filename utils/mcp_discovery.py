import os
from pathlib import Path
from typing import List, Optional, Union

def resolve_reflection_cmd(repo_root: Optional[Union[str, Path]] = None) -> Optional[Union[str, List[str]]]:
    """Compat resolver used by imported tests.

    - When repo_root is provided, mimic legacy behavior: if no env and no
      bin is found relative to repo_root, return None (do not guess PATH).
    - Otherwise, defer to app._resolve_reflection_mcp_cmd and return its list.
    """
    # Legacy strict behavior when a specific root is passed
    if repo_root is not None:
        root = Path(repo_root)
        env_cmd = (os.environ.get('REFLECTION_MCP_CMD') or '').strip()
        if env_cmd:
            return env_cmd
        for name in ("reflection-mcp", "reflection-mcp-service"):
            cand = root / 'bin' / name
            if cand.exists():
                return str(cand)
        sib = root.parent / 'reflection-mcp' / 'bin' / 'reflection-mcp'
        if sib.exists():
            return str(sib)
        # Nothing found in strict mode
        return None

    # Fallback to app logic
    try:
        from app import _resolve_reflection_mcp_cmd
        return _resolve_reflection_mcp_cmd()
    except Exception:
        return None
