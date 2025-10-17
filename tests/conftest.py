"""
pytest configuration and fixtures for reflection UI tests
"""

import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_env():
    """Fixture to provide mock environment variables"""
    with patch.dict(os.environ, {
        'FLASK_SECRET_KEY': 'test_secret_key_for_pytest',
        'OPENAI_API_KEY': 'sk-test-fake-key-for-testing-only',
        'FLASK_ENV': 'testing'
    }):
        yield


@pytest.fixture
def app(mock_env, tmp_path):
    """Create and configure a test Flask app instance"""
    # Import here to get mock_env applied first
    import app as flask_app

    # Override data directories to use tmp_path
    flask_app.DATA_DIR = tmp_path / 'test_data'
    flask_app.SESSIONS_DIR = flask_app.DATA_DIR / 'reflection_sessions'
    flask_app.COAST_DIR = flask_app.DATA_DIR / 'cost_logs'
    flask_app.CANVAS_CACHE_DIR = flask_app.DATA_DIR / 'canvas_cache'

    # Create test directories
    flask_app.DATA_DIR.mkdir(parents=True, exist_ok=True)
    flask_app.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    flask_app.COAST_DIR.mkdir(parents=True, exist_ok=True)
    flask_app.CANVAS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Configure app for testing
    flask_app.app.config['TESTING'] = True
    flask_app.app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for tests

    yield flask_app.app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner"""
    return app.test_cli_runner()


@pytest.fixture
def mock_mcp_response():
    """Fixture providing a mock MCP response"""
    def _make_response(content_dict):
        return Mock(
            returncode=0,
            stdout=json.dumps({
                "result": {
                    "content": [{"text": json.dumps(content_dict)}]
                }
            }),
            stderr=""
        )
    return _make_response


@pytest.fixture
def mock_openai_response():
    """Fixture providing a mock OpenAI API response"""
    def _make_response(content, usage=None):
        if usage is None:
            usage = {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        return Mock(
            status_code=200,
            read=lambda: json.dumps({
                'choices': [{'message': {'content': content}}],
                'usage': usage
            }).encode('utf-8'),
            headers={'openai-request-id': 'test-req-id'}
        )
    return _make_response


@pytest.fixture
def sample_session_data():
    """Sample reflection session data for testing"""
    return {
        'session_id': 'test_session_123',
        'phase_number': 1,
        'total_phases': 3,
        'student_id': 'test_student',
        'assignment_type': 'search_comparison',
        'status': 'active',
        'created_at': '2024-01-01T00:00:00Z',
        'responses': {
            'phase1': 'Sample response'
        },
        'prompts': [
            {'phase': 'phase1', 'prompt': 'Test prompt 1'},
            {'phase': 'phase2', 'prompt': 'Test prompt 2'}
        ]
    }


@pytest.fixture
def sample_cost_data():
    """Sample cost tracking data for testing"""
    return {
        'totals': {
            'total_cost_usd': 0.0045,
            'total_tokens': 150,
            'api_calls_count': 3
        },
        'api_calls': [
            {
                'timestamp': '2024-01-01T00:00:00Z',
                'method': 'start_reflection',
                'tokens': 50,
                'cost_usd': 0.0015
            }
        ]
    }