#!/usr/bin/env python3
"""
Test OpenAI API key validity without logging the secret.

Usage:
    python3 scripts/test_openai_key.py

Returns:
    Exit 0: Key valid and API accessible
    Exit 1: Key missing or invalid
    Exit 2: API error (key may be valid but quota/network issue)
"""

import os
import sys
import json
import urllib.request
import urllib.error
import time
from pathlib import Path

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_env_file(path: Path) -> dict:
    """Load .env file and return as dict (without modifying os.environ)."""
    env = {}
    if not path.exists():
        return env

    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            # Remove quotes
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            env[k] = v
    except Exception as e:
        print(f"⚠️  Failed to load {path}: {e}", file=sys.stderr)
    return env


def mask_key(key: str) -> str:
    """Mask API key for safe display."""
    if not key or len(key) < 10:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


def test_openai_key(api_key: str, verbose: bool = True) -> tuple[bool, str, dict]:
    """
    Test OpenAI API key with minimal cost call.

    Returns:
        (success: bool, message: str, metadata: dict)
    """
    if not api_key:
        return False, "No API key provided", {}

    if not api_key.startswith('sk-'):
        return False, f"Invalid key format (expected sk-*, got {mask_key(api_key)})", {}

    # Minimal test: echo a timestamp
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": f"Echo exactly: {timestamp}"},
            {"role": "user", "content": "Echo the system timestamp."}
        ],
        "max_tokens": 10,
        "temperature": 0
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    url = "https://api.openai.com/v1/chat/completions"

    try:
        start = time.time()
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            response_headers = dict(resp.headers)
            body = json.loads(resp.read().decode('utf-8'))
            latency_ms = int((time.time() - start) * 1000)

        content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = body.get('usage', {})
        req_id = response_headers.get('openai-request-id', 'unknown')

        metadata = {
            'request_id': req_id,
            'latency_ms': latency_ms,
            'tokens': usage.get('total_tokens', 0),
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'model': body.get('model', 'unknown'),
            'echo_match': timestamp in content
        }

        if timestamp in content:
            return True, f"✅ Key valid · {latency_ms}ms · {metadata['tokens']} tokens · req {req_id[:12]}", metadata
        else:
            return True, f"⚠️  Key works but unexpected response · {latency_ms}ms", metadata

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get('error', {}).get('message', error_body[:100])
        except:
            error_msg = error_body[:100]

        if e.code == 401:
            return False, f"❌ Invalid API key (401 Unauthorized)", {'error': error_msg}
        elif e.code == 429:
            return False, f"⚠️  Rate limit or quota exceeded (429)", {'error': error_msg}
        else:
            return False, f"❌ API error {e.code}: {error_msg}", {'error': error_msg}

    except urllib.error.URLError as e:
        return False, f"❌ Network error: {e.reason}", {'error': str(e)}
    except Exception as e:
        return False, f"❌ Unexpected error: {e}", {'error': str(e)}


def main():
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    # Load key from environment or .env
    env_vars = os.environ.copy()

    # Try loading .env files
    env_file = REPO_ROOT / '.env'
    secrets_file = REPO_ROOT / '.local_context' / 'secrets.env'

    for path in [env_file, secrets_file]:
        loaded = load_env_file(path)
        if loaded.get('OPENAI_API_KEY'):
            env_vars.setdefault('OPENAI_API_KEY', loaded['OPENAI_API_KEY'])
            if verbose:
                print(f"📄 Loaded key from {path.name}")

    api_key = env_vars.get('OPENAI_API_KEY', '').strip()

    if not api_key:
        print("❌ No OPENAI_API_KEY found in environment or .env files")
        print("\nChecked:")
        print(f"  - Environment variables")
        print(f"  - {env_file}")
        print(f"  - {secrets_file}")
        sys.exit(1)

    if verbose:
        print(f"🔑 Testing key: {mask_key(api_key)}")
        print(f"🌐 Endpoint: https://api.openai.com/v1/chat/completions")
        print()

    success, message, metadata = test_openai_key(api_key, verbose=verbose)

    print(message)

    if verbose and metadata:
        print("\nMetadata:")
        for k, v in metadata.items():
            if k != 'error':
                print(f"  {k}: {v}")

    # Write test result to .local_context (for UI integration)
    if success:
        result_file = REPO_ROOT / '.local_context' / 'last_key_test.json'
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps({
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'success': success,
            **metadata
        }, indent=2))
        if verbose:
            print(f"\n📝 Test result saved to {result_file.relative_to(REPO_ROOT)}")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()