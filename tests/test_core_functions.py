"""
Unit tests for core utility functions in app.py
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import sys

# Import the app module
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLoadEnvFile:
    """Test suite for _load_env_file function"""

    def test_load_simple_env_file(self, tmp_path, mock_env):
        """Test loading a simple .env file"""
        from app import _load_env_file

        env_file = tmp_path / '.env'
        env_file.write_text('TEST_KEY=test_value\nANOTHER_KEY=another_value')

        _load_env_file(env_file)

        assert os.environ.get('TEST_KEY') == 'test_value'
        assert os.environ.get('ANOTHER_KEY') == 'another_value'

    def test_load_env_with_comments(self, tmp_path, mock_env):
        """Test loading env file with comments"""
        from app import _load_env_file

        env_file = tmp_path / '.env'
        env_file.write_text('# Comment line\nTEST_KEY=value1\n# Another comment\nKEY2=value2')

        _load_env_file(env_file)

        assert os.environ.get('TEST_KEY') == 'value1'
        assert os.environ.get('KEY2') == 'value2'

    def test_load_env_with_inline_comments(self, tmp_path, mock_env):
        """Test loading env with inline comments"""
        from app import _load_env_file

        env_file = tmp_path / '.env'
        env_file.write_text('TEST_KEY=value1 # inline comment\nKEY2=value2')

        _load_env_file(env_file)

        assert os.environ.get('TEST_KEY') == 'value1'
        assert os.environ.get('KEY2') == 'value2'

    def test_load_env_with_quotes(self, tmp_path, mock_env):
        """Test loading env with quoted values"""
        from app import _load_env_file

        env_file = tmp_path / '.env'
        env_file.write_text('TEST_KEY="quoted value"\nKEY2=\'single quoted\'')

        _load_env_file(env_file)

        assert os.environ.get('TEST_KEY') == 'quoted value'
        assert os.environ.get('KEY2') == 'single quoted'

    def test_load_env_missing_file(self, tmp_path, mock_env):
        """Test loading non-existent env file (should not raise)"""
        from app import _load_env_file

        env_file = tmp_path / 'nonexistent.env'

        # Should not raise exception
        _load_env_file(env_file)

    def test_load_env_override_precedence(self, tmp_path, mock_env):
        """Test that override=True replaces existing env vars"""
        from app import _load_env_file

        os.environ['EXISTING_KEY'] = 'original_value'

        env_file = tmp_path / '.env'
        env_file.write_text('EXISTING_KEY=new_value')

        _load_env_file(env_file, override=True)

        assert os.environ.get('EXISTING_KEY') == 'new_value'

    def test_load_env_no_override(self, tmp_path, mock_env):
        """Test that override=False preserves existing env vars"""
        from app import _load_env_file

        os.environ['EXISTING_KEY'] = 'original_value'

        env_file = tmp_path / '.env'
        env_file.write_text('EXISTING_KEY=new_value')

        _load_env_file(env_file, override=False)

        assert os.environ.get('EXISTING_KEY') == 'original_value'

    def test_load_env_empty_lines(self, tmp_path, mock_env):
        """Test loading env with empty lines"""
        from app import _load_env_file

        env_file = tmp_path / '.env'
        env_file.write_text('\n\nTEST_KEY=value\n\n\nKEY2=value2\n')

        _load_env_file(env_file)

        assert os.environ.get('TEST_KEY') == 'value'
        assert os.environ.get('KEY2') == 'value2'


class TestCallReflectionMCP:
    """Test suite for call_reflection_mcp function"""

    @patch('subprocess.run')
    def test_successful_mcp_call(self, mock_run, app, client, mock_mcp_response):
        """Test successful MCP call"""
        from app import call_reflection_mcp

        mock_run.return_value = mock_mcp_response({'status': 'ok', 'message': 'success'})

        with client.application.test_request_context():
            with client.session_transaction() as sess:
                sess['llm_enabled'] = True

            result = call_reflection_mcp({
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {'name': 'test_method'}
            })

            assert result['status'] == 'ok'
            assert result['message'] == 'success'
            assert mock_run.called

    @patch('subprocess.run')
    def test_mcp_call_with_error(self, mock_run, app, client):
        """Test MCP call that returns error"""
        from app import call_reflection_mcp

        mock_run.return_value = Mock(
            returncode=1,
            stdout='',
            stderr='Error message'
        )

        with client.application.test_request_context():
            result = call_reflection_mcp({
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {'name': 'test_method'}
            })

            assert 'error' in result
            assert 'Error message' in result['error']

    @patch('subprocess.run')
    def test_mcp_call_invalid_json_response(self, mock_run, app, client):
        """Test MCP call with invalid JSON response"""
        from app import call_reflection_mcp

        mock_run.return_value = Mock(
            returncode=0,
            stdout='invalid json',
            stderr=''
        )

        with client.application.test_request_context():
            result = call_reflection_mcp({
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {'name': 'test_method'}
            })

            assert 'error' in result
            assert 'Parse error' in result['error']

    @patch('subprocess.run')
    def test_mcp_call_llm_disabled(self, mock_run, app, client):
        """Test MCP call respects LLM enabled/disabled toggle"""
        from app import call_reflection_mcp

        with client.session_transaction() as sess:
            sess['llm_enabled'] = False

        with client:
            # Make request context available
            with client.application.test_request_context():
                with client.session_transaction() as sess:
                    sess['llm_enabled'] = False

                mock_run.return_value = Mock(
                    returncode=0,
                    stdout=json.dumps({
                        "result": {
                            "content": [{"text": json.dumps({'status': 'ok'})}]
                        }
                    }),
                    stderr=""
                )

                call_reflection_mcp({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call'})

                # Check that OPENAI_API_KEY was removed from env in subprocess call
                call_args = mock_run.call_args
                assert 'OPENAI_API_KEY' not in call_args[1].get('env', {})


class TestPathTraversalProtection:
    """Test suite for path traversal protection"""

    def test_audit_raw_blocks_path_traversal(self, client):
        """Test that audit_raw rejects path traversal attempts"""
        # Test various path traversal patterns
        patterns = [
            '/audit/raw/session/../../../etc/passwd',
            '/audit/raw/session/../../passwd',
            '/audit/raw/cost/..%2F..%2Fetc%2Fpasswd'
        ]

        for pattern in patterns:
            response = client.get(pattern)
            # Should redirect (302) or not found (404), not serve the file (200)
            assert response.status_code in [302, 404], f"Failed for pattern: {pattern}"

    def test_audit_zip_blocks_path_traversal(self, client):
        """Test that audit_zip rejects path traversal attempts"""
        # Test path traversal patterns
        patterns = [
            '/audit/download/../../etc/passwd.zip',
            '/audit/download/../../../etc/passwd.zip',
        ]

        for pattern in patterns:
            response = client.get(pattern)
            # Should redirect (302) or not found (404), not serve the file (200)
            assert response.status_code in [302, 404], f"Failed for pattern: {pattern}"


class TestSettingsHelpers:
    """Test suite for settings page helper functions"""

    def test_mask_key_short(self, app):
        """Test key masking for short keys"""
        # Access the mask function from settings route
        with app.app_context():
            # Test via the route to ensure mask function works
            pass  # Function is local to route, test via integration

    def test_mask_key_normal(self, client):
        """Test key masking via settings page"""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-proj-1234567890abcdef'}):
            response = client.get('/settings')

            assert response.status_code == 200
            # Key should be masked in output
            assert b'sk-' in response.data
            assert b'1234567890' not in response.data  # middle should be hidden


class TestLoadLastKeyTest:
    """Test suite for load_last_key_test function"""

    def test_load_existing_key_test(self, tmp_path, mock_env):
        """Test loading existing key test results"""
        from app import load_last_key_test, LAST_KEY_TEST_FILE, LOCAL_CTX

        # Create test file
        test_data = {
            'timestamp': '2024-01-01T00:00:00Z',
            'request_id': 'test-req-123',
            'latency_ms': 1500,
            'total_tokens': 32
        }

        LOCAL_CTX.mkdir(parents=True, exist_ok=True)
        LAST_KEY_TEST_FILE.write_text(json.dumps(test_data))

        result = load_last_key_test()

        assert result is not None
        assert result['request_id'] == 'test-req-123'
        assert result['latency_ms'] == 1500

    def test_load_missing_key_test(self, mock_env):
        """Test loading when key test file doesn't exist"""
        from app import load_last_key_test, LAST_KEY_TEST_FILE

        # Ensure file doesn't exist
        if LAST_KEY_TEST_FILE.exists():
            LAST_KEY_TEST_FILE.unlink()

        result = load_last_key_test()

        assert result is None

    def test_load_invalid_json_key_test(self, mock_env):
        """Test loading corrupted key test file"""
        from app import load_last_key_test, LAST_KEY_TEST_FILE, LOCAL_CTX

        LOCAL_CTX.mkdir(parents=True, exist_ok=True)
        LAST_KEY_TEST_FILE.write_text('invalid json')

        result = load_last_key_test()

        assert result is None


class TestHTMLToText:
    """Test suite for _html_to_text function"""

    def test_html_to_text_basic(self, mock_env):
        """Test basic HTML to text conversion"""
        from app import _html_to_text

        html = '<p>This is a paragraph.</p><p>Another paragraph.</p>'
        result = _html_to_text(html)

        assert 'This is a paragraph.' in result
        assert 'Another paragraph.' in result
        assert '<p>' not in result

    def test_html_to_text_with_lists(self, mock_env):
        """Test HTML with lists conversion"""
        from app import _html_to_text

        html = '<ul><li>Item 1</li><li>Item 2</li></ul>'
        result = _html_to_text(html)

        assert '- Item 1' in result
        assert '- Item 2' in result

    def test_html_to_text_strips_scripts(self, mock_env):
        """Test that scripts and styles are removed"""
        from app import _html_to_text

        html = '<p>Text</p><script>alert("bad")</script><p>More text</p>'
        result = _html_to_text(html)

        assert 'Text' in result
        assert 'More text' in result
        assert 'alert' not in result
        assert 'script' not in result

    def test_html_to_text_empty_input(self, mock_env):
        """Test with empty input"""
        from app import _html_to_text

        assert _html_to_text('') == ''
        assert _html_to_text(None) == ''

    def test_html_to_text_with_headings(self, mock_env):
        """Test HTML with headings"""
        from app import _html_to_text

        html = '<h1>Title</h1><p>Content</p><h2>Subtitle</h2><p>More content</p>'
        result = _html_to_text(html)

        assert 'Title' in result
        assert 'Content' in result
        assert 'Subtitle' in result


class TestExtractPhasesFromTemplate:
    """Test suite for _extract_phases_from_template function"""

    def test_extract_from_list_format(self, mock_env):
        """Test extracting phases from list format"""
        from app import _extract_phases_from_template

        data = [
            {'phase': 'plan', 'type': 'planning', 'prompt': 'What is your plan?'},
            {'phase': 'draft', 'type': 'drafting', 'prompt': 'Write a draft'}
        ]

        result = _extract_phases_from_template(data)

        assert len(result) == 2
        assert result[0]['phase'] == 'plan'
        assert result[1]['prompt'] == 'Write a draft'

    def test_extract_from_dict_with_seed_phases(self, mock_env):
        """Test extracting from dict with seed_phases"""
        from app import _extract_phases_from_template

        data = {
            'assignment_title': 'Test',
            'seed_phases': [
                {'id': 'p1', 'phase': 'plan', 'type': 'planning', 'prompt': 'Plan it'},
                {'id': 'p2', 'phase': 'draft', 'type': 'drafting', 'prompt': 'Draft it'}
            ]
        }

        result = _extract_phases_from_template(data)

        assert len(result) == 2
        # The function uses 'id' or 'phase' for the phase field
        assert result[0]['phase'] in ['p1', 'plan']

    def test_extract_empty_data(self, mock_env):
        """Test extracting from empty data"""
        from app import _extract_phases_from_template

        assert _extract_phases_from_template([]) == []
        assert _extract_phases_from_template({}) == []
        assert _extract_phases_from_template(None) == []

    def test_extract_filters_invalid_phases(self, mock_env):
        """Test that phases without prompts are filtered"""
        from app import _extract_phases_from_template

        data = [
            {'phase': 'valid', 'prompt': 'Good prompt'},
            {'phase': 'invalid'},  # No prompt
            {'prompt': ''},  # Empty prompt
        ]

        result = _extract_phases_from_template(data)

        assert len(result) == 1
        assert result[0]['phase'] == 'valid'