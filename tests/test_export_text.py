import json
from unittest.mock import patch


def _fake_summary():
    return {
        'session_id': 'sess-123',
        'student_id': 's-1',
        'assignment_type': 'demo',
        'completion_status': 'complete',
        'insights': ['Do A', 'Improve B'],
        'rubric_alignment': {
            'criteria_met': {
                'clarity': True,
                'evidence': False,
            }
        },
        'readiness_assessment': {
            'overall': 'ready',
            'suggestions': ['Add citations']
        },
        'responses': {
            'plan': {'response': 'Plan text'},
            'draft': {'response': 'Draft text'},
        },
        'cost_analysis': {
            'total_tokens': 100,
            'total_cost_usd': 0.0012,
            'api_calls_count': 3,
        },
    }


@patch('app.call_reflection_mcp', autospec=True)
def test_export_summary_text_endpoint(mock_call, app, client):
    mock_call.return_value = _fake_summary()

    # Seed session
    with client.session_transaction() as sess:
        sess['session_id'] = 'sess-123'
        sess['llm_enabled'] = True

    resp = client.get('/summary/export/text')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Reflection Summary' in body
    assert 'Coaching Insights' in body
    assert 'Rubric Alignment' in body
    assert 'Submission Readiness' in body


def test_mcp_resolution_fallbacks(monkeypatch):
    import app as flask_app
    # Force env override
    monkeypatch.setenv('REFLECTION_MCP_CMD', 'reflection-mcp')
    cmd = flask_app._resolve_reflection_mcp_cmd()
    assert isinstance(cmd, list) and cmd[0]
