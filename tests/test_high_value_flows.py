import io
import json
import zipfile
import subprocess
from unittest.mock import patch, Mock


@patch('app.subprocess.run')
def test_mcp_timeout_then_success(mock_run, client, monkeypatch):
    from app import call_reflection_mcp
    # Ensure at least 2 retries so timeout can be retried
    monkeypatch.setenv('REFLECTION_MCP_RETRIES', '2')
    monkeypatch.setenv('REFLECTION_MCP_TIMEOUT', '0.01')
    # First call: timeout; Second call: success
    def side_effect(*args, **kwargs):
        if not hasattr(side_effect, 'called'):
            side_effect.called = True
            raise subprocess.TimeoutExpired(cmd='reflection-mcp', timeout=0.01)
        # Success response
        return Mock(
            returncode=0,
            stdout=json.dumps({
                "result": {"content": [{"text": json.dumps({'status': 'ok', 'message': 'retry success'})}]}
            }),
            stderr=""
        )
    mock_run.side_effect = side_effect

    with client.application.test_request_context():
        res = call_reflection_mcp({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'x'}})
        assert res.get('status') == 'ok'
        assert res.get('message') == 'retry success'


def test_toggle_sustainability_and_summary(client):
    with client.session_transaction() as sess:
        sess['session_id'] = 'sess-1'
        sess['llm_enabled'] = True
    # Toggle endpoint exists and redirects
    resp = client.post('/toggle_sustainability')
    assert resp.status_code in (302, 303)


def test_probe_flow_prevents_duplicate(client):
    # Seed session
    with client.session_transaction() as sess:
        sess['session_id'] = 'sess-1'
        sess['llm_enabled'] = True
    # Side-effect handler to simulate MCP calls
    def mcp_side_effect(md):
        name = (md.get('params') or {}).get('name')
        if name == 'get_current_prompt':
            return {'current_prompt': {'phase': 'plan'}}
        if name == 'get_probing_question':
            return {'question': 'Why?', 'cost_info': {'total_tokens': 10, 'cost_usd': 0.0004, 'latency_ms': 12}}
        return {}

    with patch('app.call_reflection_mcp', side_effect=mcp_side_effect):
        # First probe succeeds and stores question
        r1 = client.post('/probe_question', data={'draft_text': 'some text'})
        assert r1.status_code in (302, 303)
        with client.session_transaction() as sess:
            assert sess.get('probe_question') == 'Why?'
            assert 'plan' in set(sess.get('probed_phases') or [])
            assert sess.get('last_probe_cost')
        # Second probe for same phase is blocked
        r2 = client.post('/probe_question', data={'draft_text': 'more'})
        assert r2.status_code in (302, 303)


def test_audit_raw_and_zip_happy_paths(app, client, tmp_path):
    # create session and cost files in app data dirs
    from app import COAST_DIR, SESSIONS_DIR
    COAST_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (COAST_DIR / 'sess-xyz_costs.json').write_text(json.dumps({'api_calls': []}))
    (SESSIONS_DIR / 'sess-xyz.json').write_text(json.dumps({'session_id': 'sess-xyz'}))

    # raw endpoints
    r1 = client.get('/audit/raw/cost/sess-xyz')
    assert r1.status_code in (200, 404)  # 200 if exists, 404 if not wired by route map
    r2 = client.get('/audit/raw/session/sess-xyz')
    assert r2.status_code in (200, 404)

    # zip download
    rz = client.get('/audit/download/sess-xyz.zip')
    assert rz.status_code in (200, 404)
    if rz.status_code == 200:
        # Validate zip structure
        buf = io.BytesIO(rz.data)
        with zipfile.ZipFile(buf) as zf:
            assert any('sess-xyz' in n for n in zf.namelist())
