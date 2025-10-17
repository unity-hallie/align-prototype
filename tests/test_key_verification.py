import json
from unittest.mock import patch, Mock


class DummyResp:
    def __init__(self, body: dict, headers: dict):
        self._body = json.dumps(body).encode('utf-8')
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@patch('app.urllib.request.urlopen')
@patch('app.time.strftime')
def test_settings_test_key_success(mock_strftime, mock_urlopen, client, app):
    # Fix timestamp so we can assert echoed content
    mock_strftime.return_value = '2024-01-01T00:00:00Z'
    body = {
        'choices': [{'message': {'content': 'Echo EXACTLY this token: 2024-01-01T00:00:00Z'}}],
        'usage': {'total_tokens': 3}
    }
    headers = {'openai-request-id': 'test-req-id'}
    mock_urlopen.return_value = DummyResp(body, headers)

    with patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test-key'}, clear=False):
        resp = client.post('/settings/test_key')
        assert resp.status_code == 302
        # Check that last_key_test.json was written with expected fields
        with app.app_context():
            from app import LAST_KEY_TEST_FILE
            assert LAST_KEY_TEST_FILE.exists()
            data = json.loads(LAST_KEY_TEST_FILE.read_text())
            assert data.get('request_id') == 'test-req-id'
            assert data.get('total_tokens') == 3


@patch('app._get_openai_api_key_via_auth_mcp', return_value=None)
def test_settings_saves_key_to_env_file(mock_auth, client, tmp_path, monkeypatch):
    # Point repo root to temp to keep .env writes isolated
    monkeypatch.setenv('REFLECTION_UI_DATA_DIR', str(tmp_path / 'data'))
    # monkeypatch REPO_ROOT indirectly by chdir to repo root (app resolves relative paths)
    # Use client post to save key; settings will write to .env in REPO_ROOT
    resp = client.post('/settings', data={'api_key': 'sk-new-test-key'})
    assert resp.status_code == 302
    # Verify .env now contains the key
    from pathlib import Path
    env_path = Path.cwd() / '.env'
    assert env_path.exists()
    text = env_path.read_text()
    assert 'OPENAI_API_KEY=sk-new-test-key' in text
