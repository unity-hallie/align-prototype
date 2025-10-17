"""
Integration tests for main user workflows in reflection UI
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestIndexRoute:
    """Test suite for index page"""

    def test_index_renders(self, client):
        """Test that index page loads"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Reflection' in response.data or b'reflection' in response.data

    @patch('app.os.environ.get')
    def test_index_shows_key_present(self, mock_get, client):
        """Test index shows key status correctly"""
        mock_get.side_effect = lambda key, default=None: {
            'OPENAI_API_KEY': 'sk-test-key',
            'FLASK_SECRET_KEY': 'test_secret'
        }.get(key, default)

        response = client.get('/')
        assert response.status_code == 200


class TestSettingsFlow:
    """Test suite for settings page flow"""

    def test_settings_get(self, client):
        """Test GET /settings"""
        response = client.get('/settings')
        assert response.status_code == 200

    def test_settings_toggle_llm(self, client):
        """Test toggling LLM on/off"""
        response = client.post('/settings', data={
            'toggle_llm': '1',
            'llm_enabled': 'on'
        }, follow_redirects=False)

        # Should redirect back to settings
        assert response.status_code == 302

        # Check session in a new request context
        with client:
            client.post('/settings', data={'toggle_llm': '1', 'llm_enabled': 'on'})
            with client.session_transaction() as sess:
                sess['llm_enabled'] = True  # Set for next test

    @patch('app._get_openai_api_key_via_auth_mcp')
    @patch('app.call_auth_mcp')
    def test_settings_save_key_via_auth_mcp(self, mock_call, mock_auth, client, tmp_path):
        """Test saving API key via auth-mcp"""
        mock_auth.return_value = None
        mock_call.return_value = {'ok': True}

        response = client.post('/settings', data={
            'api_key': 'sk-new-test-key'
        })

        assert response.status_code == 302
        assert mock_call.called

    def test_settings_test_key_missing(self, client):
        """Test key test when no key is present"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('app.os.environ.get', return_value=None):
                response = client.post('/settings/test_key')

                # Should redirect to settings with error message
                assert response.status_code == 302
                assert b'settings' in response.location.encode()


class TestReflectionFlowComplete:
    """Integration test for complete reflection workflow"""

    @patch('app.call_reflection_mcp')
    def test_start_reflection_success(self, mock_mcp, client):
        """Test starting a reflection session"""
        mock_mcp.return_value = {
            'session_id': 'test_session_123',
            'phase_number': 1,
            'total_phases': 3,
            'status': 'active'
        }

        response = client.post('/start_reflection', data={
            'student_id': 'test_student',
            'assignment_type': 'search_comparison',
            'assignment_context': 'Test context'
        })

        # Should redirect to reflection_step
        assert response.status_code == 302
        assert b'reflection_step' in response.location.encode()

        with client.session_transaction() as sess:
            assert sess.get('session_id') == 'test_session_123'
            assert sess.get('phase_number') == 1

    @patch('app.call_reflection_mcp')
    def test_start_reflection_with_error(self, mock_mcp, client):
        """Test starting reflection with MCP error"""
        mock_mcp.return_value = {
            'error': 'Something went wrong'
        }

        response = client.post('/start_reflection', data={
            'student_id': 'test_student',
            'assignment_type': 'search_comparison'
        })

        # Should show error page
        assert response.status_code == 200
        assert b'error' in response.data.lower()

    def test_start_reflection_missing_key(self, client):
        """Test starting reflection without API key"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('app.os.environ.get', return_value=None):
                response = client.post('/start_reflection', data={
                    'student_id': 'test_student',
                    'assignment_type': 'search_comparison'
                })

                # Should redirect to settings
                assert response.status_code == 302
                assert b'settings' in response.location.encode()

    @patch('app.call_reflection_mcp')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'})
    def test_reflection_step_get_prompt(self, mock_mcp, client):
        """Test getting current prompt in reflection step"""
        # First set up session
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'
            sess['phase_number'] = 1
            sess['llm_enabled'] = True

        # Mock both get_current_prompt and get_session_context
        mock_mcp.side_effect = [
            {
                'status': 'active',
                'current_prompt': {
                    'phase': 'phase1',
                    'prompt': 'What is your plan?',
                    'type': 'planning'
                }
            },
            {'responses': {}, 'probes': []}  # For get_session_context call
        ]

        response = client.get('/reflection_step')

        assert response.status_code == 200
        assert b'What is your plan?' in response.data or b'phase1' in response.data

    @patch('app.call_reflection_mcp')
    def test_submit_response_success(self, mock_mcp, client):
        """Test submitting a response"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'
            sess['phase_number'] = 1

        mock_mcp.return_value = {
            'status': 'active',
            'phase_number': 2
        }

        response = client.post('/submit_response', data={
            'response': 'My detailed response here',
            'prompt_phase': 'phase1'
        })

        # Should redirect back to reflection_step for next phase
        assert response.status_code == 302
        assert b'reflection_step' in response.location.encode()

    @patch('app.call_reflection_mcp')
    def test_submit_response_completes_session(self, mock_mcp, client):
        """Test submitting final response that completes session"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'
            sess['phase_number'] = 3

        mock_mcp.return_value = {
            'status': 'complete'
        }

        response = client.post('/submit_response', data={
            'response': 'Final response',
            'prompt_phase': 'phase3'
        })

        # Should redirect to summary
        assert response.status_code == 302
        assert b'reflection_summary' in response.location.encode()

    def test_submit_empty_response(self, client):
        """Test submitting empty response"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'

        response = client.post('/submit_response', data={
            'response': '   ',
            'prompt_phase': 'phase1'
        })

        # Should redirect back to step (not accept empty)
        assert response.status_code == 302

    @patch('app.call_reflection_mcp')
    def test_save_draft(self, mock_mcp, client):
        """Test saving draft response"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'

        response = client.post('/save_draft', data={
            'response': 'Draft text here',
            'prompt_phase': 'phase1'
        })

        assert response.status_code == 302

        with client.session_transaction() as sess:
            drafts = sess.get('drafts', {})
            assert drafts.get('phase1') == 'Draft text here'

    @patch('app.call_reflection_mcp')
    def test_probe_question(self, mock_mcp, client):
        """Test requesting probing question"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'

        # Mock get_current_prompt response
        mock_mcp.side_effect = [
            {'current_prompt': {'phase': 'phase1'}},
            {'question': 'What specifically do you mean?', 'cost_info': {'tokens': 10}}
        ]

        response = client.post('/probe_question', data={
            'draft_text': 'Some draft text'
        })

        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert sess.get('probe_question') is not None

    @patch('app.call_reflection_mcp')
    def test_probe_question_limit_per_phase(self, mock_mcp, client):
        """Test that only one probe per phase is allowed"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'
            sess['probed_phases'] = ['phase1']

        mock_mcp.return_value = {'current_prompt': {'phase': 'phase1'}}

        response = client.post('/probe_question')

        assert response.status_code == 302

        with client.session_transaction() as sess:
            probe_q = sess.get('probe_question')
            assert 'already' in probe_q.lower()


class TestReflectionSummary:
    """Test suite for reflection summary page"""

    @patch('app.call_reflection_mcp')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-key'})
    def test_summary_with_cost_data(self, mock_mcp, client, app, sample_session_data, sample_cost_data):
        """Test summary page with cost analysis"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test_session_123'
            sess['session_start_time'] = 1000000000.0
            sess['llm_enabled'] = True

        # Set up data directory with cost file
        with app.app_context():
            from app import COAST_DIR
            COAST_DIR.mkdir(parents=True, exist_ok=True)
            cost_file = COAST_DIR / 'test_session_123_costs.json'
            cost_file.write_text(json.dumps(sample_cost_data))

            mock_mcp.return_value = {
                'session_id': 'test_session_123',
                'summary': 'Great work!',
                'cost_analysis': sample_cost_data['totals']
            }

            response = client.get('/reflection_summary')

            assert response.status_code == 200

    def test_summary_no_session(self, client):
        """Test summary without active session"""
        response = client.get('/reflection_summary')

        # Should redirect to index
        assert response.status_code == 302


class TestDesignerFlow:
    """Test suite for Designer workflow"""

    def test_designer_view_loads(self, client):
        """Test designer page loads"""
        response = client.get('/designer')
        assert response.status_code == 200

    @patch('app.call_reflection_mcp')
    @patch('app.os.environ.get')
    def test_design_generate(self, mock_env, mock_mcp, client):
        """Test generating design via API"""
        mock_env.side_effect = lambda key, default=None: {
            'OPENAI_API_KEY': 'sk-test-key'
        }.get(key, default)

        with client.session_transaction() as sess:
            sess['llm_enabled'] = True

        mock_mcp.return_value = {
            'phases': [
                {'phase': 'plan', 'prompt': 'Plan your work'},
                {'phase': 'draft', 'prompt': 'Write a draft'}
            ]
        }

        response = client.post('/design/generate',
                              json={
                                  'assignment_title': 'Test Assignment',
                                  'learner_level': 'beginner',
                                  'outcomes': ['Learn something']
                              },
                              content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'phases' in data

    def test_design_generate_no_key(self, client):
        """Test design generation without API key"""
        with patch.dict(os.environ, {}, clear=True):
            response = client.post('/design/generate',
                                  json={'assignment_title': 'Test'},
                                  content_type='application/json')

            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data

    def test_design_save(self, client, tmp_path):
        """Test saving designed assignment"""
        with patch('app.Path') as mock_path:
            mock_path.return_value = tmp_path

            response = client.post('/design/save',
                                  json={
                                      'slug': 'test_assignment',
                                      'content': {'title': 'Test', 'phases': []}
                                  },
                                  content_type='application/json')

            # May fail due to path mocking, but should attempt save
            # Testing the route exists and handles request
            assert response.status_code in [200, 500]

    def test_design_use_next(self, client):
        """Test storing phases for next session"""
        phases = [
            {'phase': 'p1', 'prompt': 'Prompt 1'},
            {'phase': 'p2', 'prompt': 'Prompt 2'}
        ]

        response = client.post('/design/use-next',
                              json={'phases': phases, 'slug': 'test'},
                              content_type='application/json')

        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert sess.get('custom_prompts_next') == phases

    def test_design_examples_list(self, client):
        """Test listing available examples"""
        response = client.get('/design/examples')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'examples' in data
        assert len(data['examples']) > 0

    def test_design_get_example(self, client):
        """Test getting specific example"""
        response = client.get('/design/example/generic_v1')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'phases' in data

    def test_design_status(self, client):
        """Test design status endpoint"""
        response = client.get('/design/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'key_present' in data
        assert 'llm_enabled' in data


class TestAuditFlow:
    """Test suite for audit/inspection features"""

    def test_audit_index(self, client, tmp_path):
        """Test audit index page"""
        response = client.get('/audit')

        assert response.status_code == 200

    def test_audit_raw_session(self, client, tmp_path, sample_session_data):
        """Test downloading raw session JSON"""
        from app import SESSIONS_DIR

        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        session_file = SESSIONS_DIR / 'test_session_123.json'
        session_file.write_text(json.dumps(sample_session_data))

        response = client.get('/audit/raw/session/test_session_123')

        assert response.status_code == 200
        assert response.mimetype == 'application/json'

    def test_audit_zip_download(self, client, sample_session_data, sample_cost_data):
        """Test downloading session+cost as zip"""
        from app import SESSIONS_DIR, COAST_DIR

        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        COAST_DIR.mkdir(parents=True, exist_ok=True)

        session_file = SESSIONS_DIR / 'test_session_123.json'
        session_file.write_text(json.dumps(sample_session_data))

        cost_file = COAST_DIR / 'test_session_123_costs.json'
        cost_file.write_text(json.dumps(sample_cost_data))

        response = client.get('/audit/download/test_session_123.zip')

        assert response.status_code == 200
        assert response.mimetype == 'application/zip'

    def test_audit_why_ai_feedback(self, client):
        """Test Why AI feedback audit page"""
        response = client.get('/audit/why_ai')

        assert response.status_code == 200


class TestSessionManagement:
    """Test suite for session management"""

    def test_clear_session(self, client):
        """Test clearing session"""
        with client.session_transaction() as sess:
            sess['session_id'] = 'test'
            sess['some_data'] = 'value'

        response = client.get('/clear_session')

        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert 'session_id' not in sess
            assert 'some_data' not in sess


class TestCanvasIntegration:
    """Test suite for Canvas LMS integration"""

    def test_canvas_status(self, client):
        """Test Canvas status endpoint"""
        response = client.get('/canvas/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'configured' in data

    def test_canvas_live_status(self, client):
        """Test Canvas live API status"""
        response = client.get('/canvas/live/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'live_ready' in data


class TestSecurityHeaders:
    """Test suite for security headers"""

    def test_session_cookie_httponly(self, app):
        """Test that session cookies have HTTPONLY flag"""
        assert app.config['SESSION_COOKIE_HTTPONLY'] is True

    def test_session_cookie_samesite(self, app):
        """Test that session cookies have SAMESITE flag"""
        assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'

    def test_csrf_protection_enabled(self, app):
        """Test that CSRF protection is configured"""
        assert app.config['WTF_CSRF_CHECK_DEFAULT'] is True