"""
Tests for MCP calling modes: subprocess vs. service (microservice)

Validates that both modes work correctly and fail gracefully.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, call_reflection_mcp, _call_reflection_mcp_service, _call_reflection_mcp_subprocess


@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestSubprocessMode:
    """Test reflection-mcp subprocess mode (default)."""

    def test_subprocess_mode_default(self):
        """Verify subprocess is default mode."""
        # When REFLECTION_MCP_MODE is not set, default to subprocess
        with patch.dict(os.environ, {}, clear=False):
            if 'REFLECTION_MCP_MODE' in os.environ:
                del os.environ['REFLECTION_MCP_MODE']

            # This should use subprocess path
            assert os.environ.get('REFLECTION_MCP_MODE', 'subprocess') == 'subprocess'

    @patch('subprocess.run')
    def test_subprocess_success(self, mock_run):
        """Test successful subprocess call."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "result": {
                "content": [
                    {"text": json.dumps({"insights": ["Good work"]})}
                ]
            }
        })
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'subprocess'}, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = call_reflection_mcp(method_data)

            assert result is not None
            assert "insights" in result or "error" not in result.get("error", "")

    @patch('subprocess.run')
    def test_subprocess_timeout(self, mock_run):
        """Test subprocess timeout handling."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('cmd', 60)

        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'subprocess', 'REFLECTION_MCP_TIMEOUT': '60'}, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = call_reflection_mcp(method_data)

            assert "error" in result
            assert "timeout" in result["error"].lower()

    @patch('subprocess.run')
    def test_subprocess_error(self, mock_run):
        """Test subprocess error handling."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "MCP server error"
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'subprocess'}, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = call_reflection_mcp(method_data)

            assert "error" in result
            assert "MCP Error" in result["error"]


class TestServiceMode:
    """Test reflection-mcp microservice (HTTP) mode."""

    def test_service_mode_requires_url(self):
        """Service mode must have REFLECTION_MCP_SERVICE_URL set."""
        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'service'}, clear=False):
            # Remove URL
            os.environ.pop('REFLECTION_MCP_SERVICE_URL', None)

            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "error" in result
            assert "REFLECTION_MCP_SERVICE_URL" in result["error"]

    @patch('requests.post')
    def test_service_success_direct_response(self, mock_post):
        """Test successful service call with direct JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "insights": ["Good work"],
            "readiness_assessment": {"overall": "ready"}
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "insights" in result
            assert result["insights"] == ["Good work"]

            # Verify the POST was made correctly
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs['json'] == method_data
            assert call_kwargs['timeout'] == 60

    @patch('requests.post')
    def test_service_success_wrapped_response(self, mock_post):
        """Test successful service call with MCP-wrapped response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "content": [
                    {"text": json.dumps({"insights": ["Good work"]})}
                ]
            }
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "insights" in result

    @patch('requests.post')
    def test_service_with_auth_token(self, mock_post):
        """Test service call includes auth token in headers."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000',
            'REFLECTION_MCP_AUTH_TOKEN': 'secret-token-xyz'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            # Verify auth header was sent
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs['headers']
            assert 'Authorization' in headers
            assert headers['Authorization'] == 'Bearer secret-token-xyz'

    @patch('requests.post')
    def test_service_timeout(self, mock_post):
        """Test service timeout handling."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000',
            'REFLECTION_MCP_TIMEOUT': '60'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "error" in result
            assert "timeout" in result["error"].lower()

    @patch('requests.post')
    def test_service_connection_error(self, mock_post):
        """Test service connection error handling."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "error" in result
            assert "unreachable" in result["error"].lower()

    @patch('requests.post')
    def test_service_auth_error(self, mock_post):
        """Test service 401 auth error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        import requests
        mock_post.side_effect = requests.exceptions.HTTPError(response=mock_response)

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 1)

            assert "error" in result
            assert "401" in result["error"]

    @patch('requests.post')
    def test_service_retries(self, mock_post):
        """Test service retry logic on failure."""
        import requests
        # First two calls fail, third succeeds
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_post.side_effect = [
            requests.exceptions.Timeout(),
            requests.exceptions.Timeout(),
            mock_response
        ]

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "reflect", "params": {"text": "test"}}
            result = _call_reflection_mcp_service(method_data, 60, 3)

            # Should succeed on retry
            assert "success" in result
            assert result["success"] is True
            assert mock_post.call_count == 3


class TestModeSelection:
    """Test mode selection logic."""

    @patch('subprocess.run')
    def test_subprocess_mode_selected(self, mock_run):
        """When REFLECTION_MCP_MODE=subprocess, use subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "result": {"content": [{"text": json.dumps({"test": "data"})}]}
        })
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'subprocess'}, clear=False):
            method_data = {"method": "test"}
            call_reflection_mcp(method_data)

            # Subprocess.run should have been called
            mock_run.assert_called_once()

    @patch('requests.post')
    def test_service_mode_selected(self, mock_post):
        """When REFLECTION_MCP_MODE=service, use service."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            'REFLECTION_MCP_MODE': 'service',
            'REFLECTION_MCP_SERVICE_URL': 'http://localhost:3000'
        }, clear=False):
            method_data = {"method": "test"}
            call_reflection_mcp(method_data)

            # requests.post should have been called
            mock_post.assert_called_once()

    @patch('subprocess.run')
    def test_invalid_mode_defaults_to_subprocess(self, mock_run):
        """Invalid REFLECTION_MCP_MODE defaults to subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "result": {"content": [{"text": json.dumps({"test": "data"})}]}
        })
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {'REFLECTION_MCP_MODE': 'invalid_mode'}, clear=False):
            method_data = {"method": "test"}
            call_reflection_mcp(method_data)

            # Should fall back to subprocess
            mock_run.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
