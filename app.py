#!/usr/bin/env python3
"""
Interactive UI for testing reflection MCP server
"""

import os
import json
import subprocess
import sys
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file
import io
import zipfile
from pathlib import Path
from typing import Optional
import hashlib
import urllib.request
import urllib.error
import re
import requests

# Add parent directory to path for pure_cost_logger
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_12345')

REPO_ROOT = Path(__file__).resolve().parent
LOCAL_CTX = REPO_ROOT / ".local_context"
# Decoupled data directory for UI artifacts; defaults to ~/.reflection_ui
DATA_DIR = Path(os.environ.get('REFLECTION_UI_DATA_DIR', str(Path.home() / '.reflection_ui')))
SESSIONS_DIR = DATA_DIR / "reflection_sessions"
COAST_DIR = DATA_DIR / "cost_logs"
CANVAS_CACHE_DIR = DATA_DIR / "canvas_cache"

# Load local environment files with precedence: OS env < .env < secrets.env
def _load_env_file(path: Path, override: bool = True):
    try:
        if path.exists():
            cleaned_lines = []
            modified = False
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    cleaned_lines.append(raw)
                    continue
                if '=' not in line:
                    cleaned_lines.append(raw)
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                # Strip inline comments if preceded by whitespace
                v_stripped = v.strip()
                if ' #' in v_stripped:
                    v_stripped = v_stripped.split(' #', 1)[0].rstrip()
                    modified = True
                # Remove surrounding single/double quotes if present
                if (v_stripped.startswith('"') and v_stripped.endswith('"')) or (
                    v_stripped.startswith("'") and v_stripped.endswith("'")):
                    v_stripped = v_stripped[1:-1]
                    modified = True
                if override or k not in os.environ:
                    os.environ[k] = v_stripped
                # Re-compose cleaned line for potential write-back
                cleaned_lines.append(f"{k}={v_stripped}" if v_stripped else raw)
            # If we modified any lines, write a cleaned copy next to original for visibility
            if modified:
                try:
                    backup = path.with_suffix(path.suffix + '.backup')
                    if not backup.exists():
                        backup.write_text(path.read_text())
                    path.write_text("\n".join(cleaned_lines) + "\n")
                except Exception:
                    pass
    except Exception:
        pass

# Apply precedence
_load_env_file(REPO_ROOT / '.env', override=True)
_load_env_file(LOCAL_CTX / 'secrets.env', override=True)

def _ensure_env_loaded():
    """Best-effort re-load of .env and local secrets so keys are present even if process env changed."""
    try:
        _load_env_file(REPO_ROOT / '.env', override=True)
    except Exception:
        pass
    try:
        _load_env_file(LOCAL_CTX / 'secrets.env', override=True)
    except Exception:
        pass

LAST_KEY_TEST_FILE = LOCAL_CTX / 'last_key_test.json'

def _auth_mcp_cmd() -> Optional[str]:
    # Prefer explicit env; fallback to repo bin if present
    c = (os.environ.get('AUTH_MCP_CMD') or '').strip()
    if c:
        return c
    cand = REPO_ROOT / 'bin' / 'auth-mcp'
    return str(cand) if cand.exists() else None


def call_auth_mcp(method: str, arguments: dict) -> Optional[dict]:
    cmd = _auth_mcp_cmd()
    if not cmd:
        return None
    env = os.environ.copy()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": method, "arguments": arguments},
    }
    try:
        result = subprocess.run([cmd], input=json.dumps(payload) + "\n", capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)
        if result.returncode != 0:
            return None
        out = json.loads(result.stdout.strip())
        # unwrap text content
        txt = (((out.get('result') or {}).get('content') or [{}])[0]).get('text')
        return json.loads(txt) if txt else None
    except Exception:
        return None


def _get_openai_api_key_via_auth_mcp() -> Optional[str]:
    res = call_auth_mcp('get_secret', {"name": "openai_api_key"})
    if isinstance(res, dict) and res.get('found'):
        return str(res.get('value') or '').strip() or None
    return None


def load_last_key_test():
    try:
        if LAST_KEY_TEST_FILE.exists():
            return json.loads(LAST_KEY_TEST_FILE.read_text())
    except Exception:
        return None
    return None


def call_reflection_mcp(method_data):
    """Call reflection MCP and return parsed response"""
    # Prefer Python entry on Windows to avoid WinError 193 from shell wrappers
    if os.name == 'nt':
        cmd = [sys.executable, str(REPO_ROOT / 'reflection_mcp' / 'server.py')]
    else:
        cmd = [str(REPO_ROOT / "bin" / "reflection-mcp")]
    # Respect LLM enable/disable toggle by adjusting env for subprocess
    env = os.environ.copy()
    if session.get('llm_enabled') is False:
        env.pop('OPENAI_API_KEY', None)
    result = subprocess.run(
        cmd,
        input=json.dumps(method_data) + "\n",
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env
    )

    if result.returncode != 0:
        return {"error": f"MCP Error: {result.stderr}"}

    try:
        response = json.loads(result.stdout.strip())
        if "result" in response and "content" in response["result"]:
            return json.loads(response["result"]["content"][0]["text"])
        return {"error": "Invalid MCP response format"}
    except Exception as e:
        return {"error": f"Parse error: {str(e)}"}

@app.route('/')
def index():
    key_present = bool(_get_openai_api_key_via_auth_mcp() or os.environ.get('OPENAI_API_KEY'))
    llm_enabled = session.get('llm_enabled', key_present)
    last_key = load_last_key_test() or {}
    # Demo ready if key present+enabled and last test within last 30 minutes
    demo_ready = False
    demo_msg = None
    try:
        ts = last_key.get('timestamp')
        if key_present and llm_enabled and ts:
            # compare seconds since epoch-ish via time parsing
            # timestamp stored as ISO string; consider it recent if file mtime < 30 min
            age_sec = time.time() - (LAST_KEY_TEST_FILE.stat().st_mtime)
            demo_ready = age_sec <= 30 * 60
            if demo_ready:
                demo_msg = f"Key verified recently · req {last_key.get('request_id','n/a')} · {last_key.get('latency_ms','?')}ms"
    except Exception:
        pass
    return render_template('index.html', key_present=key_present, llm_enabled=llm_enabled,
                           demo_ready=demo_ready, demo_msg=demo_msg, open_designer=False)

@app.get('/designer')
def designer_view():
    """Dedicated Designer full-page view (replaces modal)."""
    return render_template('designer.html')

@app.get('/designer/prototype')
def designer_prototype():
    """Static prototype of the redesigned Designer layout (no wiring)."""
    return render_template('designer_prototype.html')

@app.post('/design/improve_outcomes')
def design_improve_outcomes():
    """AI assist: refine/clarify existing learning objectives. Returns JSON list.
    Requires OPENAI_API_KEY; does not run without a key. Keeps costs low and returns usage info.
    Body: {outcomes:[str], style?:str}
    """
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return jsonify({'error': 'LLM unavailable: provide OPENAI_API_KEY'}), 400
    data = request.get_json(silent=True) or {}
    outcomes = data.get('outcomes') or []
    if not isinstance(outcomes, list) or not outcomes:
        return jsonify({'error': 'Provide outcomes as a non-empty list'}), 400
    style = (data.get('style') or 'Concise, measurable, student-facing').strip()
    # Build prompt: ask for JSON array only
    system_prompt = (
        'You refine course learning objectives. Return ONLY a JSON array of strings. '
        'Keep each objective concise, measurable, and student-facing. Do not invent new objectives beyond rewording.'
    )
    user_prompt = json.dumps({'style': style, 'outcomes': outcomes}, ensure_ascii=False)
    payload = {
        'model': 'gpt-4o-mini',
        'temperature': 0.2,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'response_format': {'type': 'json_object'},
        'max_tokens': 200
    }
    try:
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        latency_ms = int((time.time() - start) * 1000)
        content = (((body.get('choices') or [{}])[0]).get('message') or {}).get('content', '')
        # Expect JSON object due to response_format; try to decode
        try:
            obj = json.loads(content)
            refined = obj.get('outcomes') if isinstance(obj, dict) else None
        except Exception:
            # Fallback: try raw list
            try:
                refined = json.loads(content)
            except Exception:
                refined = None
        if not isinstance(refined, list):
            return jsonify({'error': 'LLM returned invalid format'}), 500
        usage = body.get('usage', {})
        cost_info = {
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0),
            'latency_ms': latency_ms
        }
        return jsonify({'outcomes': refined, 'cost_info': cost_info})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    # Helper: mask API key
    def mask(key: str) -> str:
        if not key:
            return ''
        if len(key) <= 6:
            return '*' * len(key)
        return key[:3] + '*' * (len(key) - 6) + key[-3:]

    saved_path = REPO_ROOT / '.local_context' / 'secrets.env'
    saved_key = ''
    # Prefer auth-mcp if available
    ak = _get_openai_api_key_via_auth_mcp()
    if ak:
        saved_key = ak
    elif saved_path.exists():
        try:
            for line in saved_path.read_text().splitlines():
                if line.startswith('OPENAI_API_KEY='):
                    saved_key = line.split('=',1)[1].strip()
                    break
        except Exception:
            pass

    message = request.args.get('msg')
    if request.method == 'POST' and 'test_key' not in request.form:
        # Toggle LLM usage
        if 'toggle_llm' in request.form:
            enabled = request.form.get('llm_enabled') == 'on'
            session['llm_enabled'] = enabled
            message = 'LLM usage ' + ('enabled' if enabled else 'disabled') + ' for this session.'
        # Save new API key
        new_key = (request.form.get('api_key') or '').strip()
        if new_key:
            # Try auth-mcp first
            used_auth = False
            res = call_auth_mcp('put_secret', {"name": "openai_api_key", "value": new_key})
            if isinstance(res, dict) and res.get('ok'):
                used_auth = True
            if not used_auth:
                try:
                    saved_path.parent.mkdir(parents=True, exist_ok=True)
                    saved_path.write_text(f"OPENAI_API_KEY={new_key}\n")
                    os.environ['OPENAI_API_KEY'] = new_key
                    message = (message + ' ' if message else '') + 'API key saved to local secrets.'
                except Exception as e:
                    message = f'Error saving key: {e}'
            else:
                message = (message + ' ' if message else '') + 'API key saved via auth-mcp.'

    current_key = _get_openai_api_key_via_auth_mcp() or os.environ.get('OPENAI_API_KEY', '')
    return render_template('settings.html',
                           llm_enabled=session.get('llm_enabled', bool(current_key)),
                           current_key_masked=mask(current_key),
                           saved_key_masked=mask(saved_key),
                           message=message)

@app.post('/settings/test_key')
def settings_test_key():
    """Advocate agent: verify API key with a 1-token echo and show honest status."""
    api_key = (_get_openai_api_key_via_auth_mcp() or os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return redirect(url_for('settings', msg='No API key set in process env. Save a key first.'))

    timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": f"Echo EXACTLY this token: {timestamp}"},
            {"role": "user", "content": "Repeat the system token only."}
        ],
        "max_tokens": 12
    }
    payload_json = json.dumps(payload, sort_keys=True)
    req_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"ReflectionUI-KeyTest/{timestamp}"
        },
        method="POST"
    )
    try:
        start = time.time()
        with urllib.request.urlopen(req, timeout=12) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode('utf-8'))
        latency = int((time.time() - start) * 1000)
        content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
        ok = (timestamp in content)
        usage = body.get('usage', {})
        req_id = headers.get('openai-request-id', 'n/a')
        # Persist last key test
        try:
            LOCAL_CTX.mkdir(parents=True, exist_ok=True)
            LAST_KEY_TEST_FILE.write_text(json.dumps({
                'timestamp': timestamp,
                'request_id': req_id,
                'latency_ms': latency,
                'total_tokens': usage.get('total_tokens', 0),
                'hash8': req_hash[:8]
            }, indent=2))
        except Exception:
            pass
        msg = f"Key test {'passed' if ok else 'unexpected reply'} · req {req_id} · {latency}ms · tokens {usage.get('total_tokens',0)} · hash {req_hash[:8]}"
        return redirect(url_for('settings', msg=msg))
    except Exception as e:
        return redirect(url_for('settings', msg=f"Key test failed: {e}"))

@app.route('/start_reflection', methods=['POST'])
def start_reflection():
    student_id = request.form.get('student_id', 'test_student')
    assignment_type = request.form.get('assignment_type', 'search_comparison')
    assignment_context = request.form.get('assignment_context', '')
    # Optional advanced fields
    ai_instructions = request.form.get('ai_instructions', '').strip()
    gr_temp = request.form.get('gr_temperature', '').strip()
    gr_max = request.form.get('gr_max_tokens', '').strip()
    rubric_config = request.form.get('rubric_config', '').strip()
    custom_prompts_json = (request.form.get('custom_prompts') or '').strip()
    autofill_demo = request.form.get('autofill_demo', '') == 'on'
    guardrails = {}
    if gr_temp:
        try:
            guardrails['temperature'] = float(gr_temp)
        except Exception:
            pass
    if gr_max:
        try:
            guardrails['max_tokens'] = int(gr_max)
        except Exception:
            pass

    # Enforce LLM availability: require API key and enabled toggle
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))

    # Track UI session timing only (costs are logged by MCP)

    method_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "start_reflection",
            "arguments": {
                "student_id": student_id,
                "assignment_type": assignment_type,
                "assignment_context": assignment_context,
                "ai_instructions": ai_instructions,
                "guardrails": guardrails,
                "rubric_config": rubric_config
            }
        }
    }
    # Attach optional custom prompts if provided
    used_custom = False
    if custom_prompts_json:
        try:
            cps = json.loads(custom_prompts_json)
            if isinstance(cps, list):
                method_data['params']['arguments']['custom_prompts'] = cps
                used_custom = True
        except Exception:
            pass
    else:
        # Fallback to any design-time prompts stored for next session
        pending = session.pop('custom_prompts_next', None)
        if isinstance(pending, list) and pending:
            method_data['params']['arguments']['custom_prompts'] = pending
            used_custom = True

    result = call_reflection_mcp(method_data)

    if "error" in result:
        return render_template('error.html', error=result["error"])

    session['session_id'] = result['session_id']
    session['phase_number'] = result['phase_number']
    session['total_phases'] = result['total_phases']
    session['session_start_time'] = time.time()
    session['drafts'] = {}
    session['autofill_demo'] = autofill_demo
    session['assignment_type'] = assignment_type
    session['using_custom_prompts'] = used_custom
    # Load demo texts for assignment type into session for easy access
    try:
        session['demo_texts'] = _load_demo_texts(assignment_type)
    except Exception:
        session['demo_texts'] = {}
    # Default LLM enabled if key is present unless user toggled off
    if 'llm_enabled' not in session:
        session['llm_enabled'] = bool(os.environ.get('OPENAI_API_KEY'))

    return redirect(url_for('reflection_step'))

@app.route('/reflection_step')
def reflection_step():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))

    # Get current prompt
    method_data = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "get_current_prompt",
            "arguments": {"session_id": session['session_id']}
        }
    }

    result = call_reflection_mcp(method_data)

    # Fetch session context (prior responses and probes)
    ctx = {'responses': {}, 'probes': []}
    try:
        ctx_res = call_reflection_mcp({
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "get_session_context",
                "arguments": {"session_id": session['session_id']}
            }
        })
        if isinstance(ctx_res, dict):
            ctx['responses'] = ctx_res.get('responses', {})
            ctx['probes'] = ctx_res.get('probes', [])
    except Exception:
        pass

    if "error" in result:
        return render_template('error.html', error=result["error"])

    if result.get('status') == 'complete':
        return redirect(url_for('reflection_summary'))

    # Determine current phase and pull any saved draft
    cur_phase = (result.get('current_prompt') or {}).get('phase')
    draft_text = ''
    if cur_phase:
        drafts = session.get('drafts') or {}
        demo_texts = session.get('demo_texts') or {}
        draft_text = drafts.get(cur_phase, '')
        # Optional auto-fill with demo text when empty, if enabled and no prior response
        if not draft_text and session.get('autofill_demo'):
            # Only auto-fill if there is no saved response for this phase
            has_response = False
            try:
                if isinstance(ctx, dict) and isinstance(ctx.get('responses'), dict):
                    has_response = cur_phase in ctx['responses']
            except Exception:
                has_response = False
            if not has_response and demo_texts.get(cur_phase):
                draft_text = demo_texts.get(cur_phase, '')
                drafts[cur_phase] = draft_text
                session['drafts'] = drafts

    probe_q = session.pop('probe_question', None)
    # Pull and clear last probe cost for display
    last_probe_cost = session.pop('last_probe_cost', None)
    return render_template('reflection_step.html',
                         prompt_data=result,
                         session_id=session['session_id'],
                         probe_question=probe_q,
                         session_context=ctx,
                         last_probe_cost=last_probe_cost,
                         draft_text=draft_text,
                         using_custom=session.get('using_custom_prompts', False))

@app.route('/submit_response', methods=['POST'])
def submit_response():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))

    response_text = request.form.get('response', '')
    prompt_phase = request.form.get('prompt_phase', '')

    if not response_text.strip():
        return redirect(url_for('reflection_step'))

    method_data = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "submit_reflection_response",
            "arguments": {
                "session_id": session['session_id'],
                "response": response_text,
                "prompt_phase": prompt_phase
            }
        }
    }

    result = call_reflection_mcp(method_data)

    if "error" in result:
        return render_template('error.html', error=result["error"])

    if result.get('status') == 'complete':
        return redirect(url_for('reflection_summary'))

    # Update session phase info
    if 'phase_number' in result:
        session['phase_number'] = result['phase_number']
    # Clear draft for submitted phase
    try:
        drafts = session.get('drafts') or {}
        if prompt_phase in drafts:
            drafts.pop(prompt_phase, None)
            session['drafts'] = drafts
    except Exception:
        pass

    return redirect(url_for('reflection_step'))

@app.route('/save_draft', methods=['POST'])
def save_draft():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    text = request.form.get('response', '')
    prompt_phase = request.form.get('prompt_phase', '')
    drafts = session.get('drafts') or {}
    if prompt_phase:
        drafts[prompt_phase] = text
        session['drafts'] = drafts
    return redirect(url_for('reflection_step'))

@app.route('/load_demo', methods=['POST'])
def load_demo():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    prompt_phase = request.form.get('prompt_phase', '')
    demo_texts = session.get('demo_texts') or {}
    drafts = session.get('drafts') or {}
    if prompt_phase and demo_texts.get(prompt_phase):
        drafts[prompt_phase] = demo_texts[prompt_phase]
        session['drafts'] = drafts
    return redirect(url_for('reflection_step'))

@app.route('/probe_question', methods=['POST'])
def probe_question():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))
    # Ask MCP for a probing question for current phase
    # First get current prompt to determine phase
    md = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {
            "name": "get_current_prompt",
            "arguments": {"session_id": session['session_id']}
        }
    }
    cur = call_reflection_mcp(md)
    phase = None
    if isinstance(cur, dict):
        phase = (cur.get('current_prompt') or {}).get('phase')
    # Enforce one probe per phase
    probed = set(session.get('probed_phases', []))
    if phase and phase in probed:
        session['probe_question'] = "You already asked a reflective question for this phase."
        return redirect(url_for('reflection_step'))
    md = {
        "jsonrpc": "2.0",
        "id": 22,
        "method": "tools/call",
        "params": {
            "name": "get_probing_question",
            "arguments": {"session_id": session['session_id'], "phase": phase}
        }
    }
    # Allow passing current draft text for more grounded probes
    current_draft = request.form.get('draft_text', '')
    if current_draft:
        md['params']['arguments']['draft_text'] = current_draft
    res = call_reflection_mcp(md)
    if isinstance(res, dict):
        session['probe_question'] = res.get('question')
        if res.get('cost_info'):
            session['last_probe_cost'] = res.get('cost_info')
        if phase:
            probed.add(phase)
            session['probed_phases'] = list(probed)
    return redirect(url_for('reflection_step'))

@app.route('/reflection_summary')
def reflection_summary():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))

    method_data = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "get_reflection_summary",
            "arguments": {"session_id": session['session_id']}
        }
    }

    result = call_reflection_mcp(method_data)

    if "error" in result:
        return render_template('error.html', error=result["error"])

    # Prefer real cost data from MCP summary; do not estimate
    cost_data = result.get('cost_analysis') or None
    environmental_impact = {}

    # Compute environmental messaging only when explicitly enabled
    show_sust = bool(session.get('show_sustainability', False))
    if show_sust and cost_data and isinstance(cost_data, dict):
        try:
            total_cost = float(cost_data.get('total_cost_usd', 0) or 0)
            email_cost_usd = float(os.environ.get('EMAIL_COST_USD', '0.00004'))
            paper_cost_usd = float(os.environ.get('PRINT_PAGE_COST_USD', '0.05'))

            # Comparison phrasing: express relative to one email
            ratio = total_cost / email_cost_usd if email_cost_usd > 0 else 0
            if ratio > 1:
                email_msg = f"~{ratio:.1f}× the cost of sending an email"
            elif ratio > 0:
                email_msg = f"~{(1/ratio):.1f}× less than sending an email"
            else:
                email_msg = "Negligible vs sending an email"

            paper_ratio = paper_cost_usd / total_cost if total_cost > 0 else 0
            paper_msg = f"Saves ~{paper_ratio:.0f}× vs printing a one-page worksheet" if paper_ratio > 0 else ""

            environmental_impact = {
                'email_comparison': email_msg,
                'paper_comparison': paper_msg,
                'efficiency_message': f"Processed {cost_data.get('total_tokens', 0)} tokens"
            }
        except Exception as e:
            print(f"Env impact calc error: {e}")

    no_api_key = (not bool(os.environ.get('OPENAI_API_KEY'))) or (session.get('llm_enabled') is False)
    regenerated = bool(session.pop('summary_regenerated', False))
    view_mode = session.get('summary_view', 'student')
    feedback_msg = session.pop('feedback_msg', None)
    # Load recent API calls for process trail (Instructor view)
    api_calls = []
    try:
        cost_file = COAST_DIR / f"{session['session_id']}_costs.json"
        if cost_file.exists():
            cdata = json.loads(cost_file.read_text())
            api_calls = cdata.get('api_calls') or []
    except Exception:
        api_calls = []
    return render_template('reflection_summary.html',
                         summary=result,
                           cost_data=cost_data,
                           environmental_impact=environmental_impact,
                           session_duration=time.time() - session.get('session_start_time', time.time()),
                           no_api_key=no_api_key,
                           regenerated=regenerated,
                           view_mode=view_mode,
                           show_sustainability=show_sust,
                           feedback_msg=feedback_msg,
                           api_calls=api_calls)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/docs/llm_risks')
def doc_llm_risks():
    doc_path = REPO_ROOT / 'docs' / 'reflection_llm_risk_mitigations.md'
    content = None
    if doc_path.exists():
        try:
            content = doc_path.read_text(encoding='utf-8')
        except Exception as e:
            content = f"Error reading document: {e}"
    else:
        content = "Document not found. Check docs/reflection_llm_risk_mitigations.md in the repository."
    return render_template('doc_view.html', title='LLM Scoring Risks & Mitigations', content=content)

@app.route('/docs/demo')
def doc_demo_script():
    doc_path = REPO_ROOT / 'docs' / 'DEMO_SCRIPT.md'
    content = None
    if doc_path.exists():
        try:
            content = doc_path.read_text(encoding='utf-8')
        except Exception as e:
            content = f"Error reading document: {e}"
    else:
        content = "Demo script not found. See docs/DEMO_SCRIPT.md."
    return render_template('doc_view.html', title='Demo Script', content=content)

@app.route('/audit')
def audit_index():
    """Rough audit view: list sessions with links to raw logs, with basic metadata."""
    sessions = []
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        COAST_DIR.mkdir(parents=True, exist_ok=True)
        for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            sid = f.stem
            cost_file = COAST_DIR / f"{sid}_costs.json"
            meta = {
                'session_id': sid,
                'session_path': str(f),
                'session_mtime': f.stat().st_mtime,
                'session_size': f.stat().st_size,
                'student_id': None,
                'assignment_type': None,
                'created_at': None,
                'status': None,
                'responses_count': 0,
                'total_phases': None,
                'cost_exists': cost_file.exists(),
                'cost_path': str(cost_file) if cost_file.exists() else None,
                'cost_size': cost_file.stat().st_size if cost_file.exists() else 0,
                'cost_total_usd': None,
                'cost_tokens': None,
                'cost_calls': None,
            }
            try:
                data = json.loads(f.read_text())
                meta['student_id'] = data.get('student_id')
                meta['assignment_type'] = data.get('assignment_type')
                meta['created_at'] = data.get('created_at')
                meta['status'] = data.get('status')
                meta['responses_count'] = len((data.get('responses') or {}).keys())
                meta['total_phases'] = len(data.get('prompts') or [])
            except Exception:
                pass
            if cost_file.exists():
                try:
                    cdata = json.loads(cost_file.read_text())
                    totals = cdata.get('totals') or {}
                    meta['cost_total_usd'] = totals.get('total_cost_usd')
                    meta['cost_tokens'] = totals.get('total_tokens')
                    meta['cost_calls'] = totals.get('api_calls_count')
                except Exception:
                    pass
            sessions.append(meta)
    except Exception as e:
        return render_template('doc_view.html', title='Audit', content=f'Error listing sessions: {e}')
    return render_template('audit.html', sessions=sessions)

@app.route('/audit/why_ai')
def audit_why_ai():
    """Aggregate Why AI feedback across sessions and show recent entries."""
    feedback_dir = REPO_ROOT / '.local_context' / 'why_ai_feedback'
    records = []
    try:
        feedback_dir.mkdir(parents=True, exist_ok=True)
        for p in sorted(feedback_dir.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                rec = json.loads(p.read_text())
                rec['_path'] = str(p)
                records.append(rec)
            except Exception:
                continue
    except Exception:
        pass
    # Aggregate averages per key
    keys = ['adaptive_prompts','grounded_feedback','goal_alignment','actionable_readiness','prefer_over_worksheet','clarity_of_behavior']
    totals = {k: 0 for k in keys}
    counts = {k: 0 for k in keys}
    for rec in records:
        ratings = rec.get('ratings') or {}
        for k in keys:
            v = ratings.get(k)
            if isinstance(v, int):
                totals[k] += v
                counts[k] += 1
    avgs = {k: (totals[k] / counts[k] if counts[k] else None) for k in keys}
    return render_template('audit_why_ai.html', records=records[:50], averages=avgs, counts=counts)

@app.route('/summary/<session_id>')
def summary_for_session(session_id):
    """Open summary view for a past session ID (read-only). Requires key/toggle like normal."""
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    if not session.get('llm_enabled', key_present) or not key_present:
        return redirect(url_for('settings'))
    session['session_id'] = session_id
    session['summary_regenerated'] = True
    # Provide placeholders for timing if absent
    if 'session_start_time' not in session:
        session['session_start_time'] = time.time()
    return redirect(url_for('reflection_summary'))

@app.route('/summary/view/<mode>')
def set_summary_view(mode):
    if mode not in ('student','instructor'):
        return redirect(url_for('reflection_summary'))
    session['summary_view'] = mode
    return redirect(url_for('reflection_summary'))

@app.route('/toggle_sustainability', methods=['POST'])
def toggle_sustainability():
    session['show_sustainability'] = not bool(session.get('show_sustainability', False))
    return redirect(url_for('reflection_summary'))

@app.route('/why_ai_feedback', methods=['POST'])
def why_ai_feedback():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    role = (request.form.get('role') or 'student').strip().lower()
    keys = ['adaptive_prompts','grounded_feedback','goal_alignment','actionable_readiness','prefer_over_worksheet']
    ratings = {}
    for k in keys:
        try:
            v = int((request.form.get(k) or '').strip() or 0)
        except Exception:
            v = 0
        if 1 <= v <= 5:
            ratings[k] = v
    free_text = (request.form.get('comments') or '')[:500]
    cost_file = COAST_DIR / f"{session['session_id']}_costs.json"
    totals = {}
    try:
        if cost_file.exists():
            data = json.loads(cost_file.read_text())
            totals = data.get('totals') or {}
    except Exception:
        pass
    rec = {
        'session_id': session['session_id'],
        'assignment_type': session.get('assignment_type'),
        'role': role,
        'ratings': ratings,
        'comments': free_text,
        'created_at': time.time(),
        'cost_totals': totals,
    }
    out_dir = REPO_ROOT / '.local_context' / 'why_ai_feedback'
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = out_dir / f"{session['session_id']}_{int(time.time())}.json"
        fname.write_text(json.dumps(rec, indent=2))
        fb = session.get('why_ai_feedbacks') or []
        fb.append(rec)
        session['why_ai_feedbacks'] = fb
        session['feedback_msg'] = 'Thanks — feedback saved.'
    except Exception as e:
        session['feedback_msg'] = f'Error saving feedback: {e}'
    return redirect(url_for('reflection_summary'))

@app.route('/audit/raw/<kind>/<session_id>')
def audit_raw(kind, session_id):
    """Serve raw JSON for session or cost log as attachment."""
    if kind not in ('session','cost'):
        return redirect(url_for('audit_index'))
    if any(c in session_id for c in ('/','..')):
        return redirect(url_for('audit_index'))
    path = SESSIONS_DIR / f"{session_id}.json" if kind == 'session' else COAST_DIR / f"{session_id}_costs.json"
    if not path.exists():
        return render_template('doc_view.html', title='Audit', content=f'File not found: {path}')
    return send_file(str(path), mimetype='application/json', as_attachment=True, download_name=path.name)

@app.route('/audit/download/<session_id>.zip')
def audit_zip(session_id):
    """Bundle session + cost files into a zip for download."""
    if any(c in session_id for c in ('/','..')):
        return redirect(url_for('audit_index'))
    sess_path = SESSIONS_DIR / f"{session_id}.json"
    cost_path = COAST_DIR / f"{session_id}_costs.json"
    if not sess_path.exists() and not cost_path.exists():
        return render_template('doc_view.html', title='Audit', content='No files found for this session.')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if sess_path.exists():
            zf.write(sess_path, arcname=sess_path.name)
        if cost_path.exists():
            zf.write(cost_path, arcname=cost_path.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{session_id}_audit.zip')

@app.route('/clear_session')
def clear_session():
    session.clear()
    return redirect(url_for('index'))

@app.route('/design/generate', methods=['POST'])
def design_generate():
    """Generate a proposed prompt workflow with LLM (design-time). Returns JSON.
    Blocks hard when missing/disabled API key — no mock data.
    """
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    payload = request.get_json(silent=True) or {}
    args = {
        "assignment_title": payload.get('assignment_title') or payload.get('assignment_type') or 'Assignment',
        "learner_level": payload.get('learner_level') or 'introductory',
        "outcomes": payload.get('outcomes') or [],
        "rubric": payload.get('rubric') or [],
        "assignment_instructions": payload.get('assignment_instructions') or '',
        "constraints": payload.get('constraints') or {},
        "examples": payload.get('examples') or [],
        "pitfalls": payload.get('pitfalls') or []
    }
    # Require LLM path (no demo/mocks) with explicit reason
    llm_enabled = session.get('llm_enabled', key_present)
    if not key_present or not llm_enabled:
        reason = 'missing_api_key' if not key_present else 'llm_disabled'
        return jsonify({
            "error": "Designer is unavailable without a valid API key.",
            "reason": reason,
            "hint": "Open Settings to test/save an API key, ensure LLM is enabled, then retry.",
            "settings_url": url_for('settings')
        }), 400
    md = {
        "jsonrpc": "2.0",
        "id": 777,
        "method": "tools/call",
        "params": {"name": "propose_prompt_workflow", "arguments": args}
    }
    res = call_reflection_mcp(md)
    if isinstance(res, dict) and res.get('error'):
        return jsonify({
            "error": "Designer error",
            "reason": "mcp_error",
            "details": res.get('error')
        }), 400
    return jsonify(res)

@app.route('/design/save', methods=['POST'])
def design_save():
    """Persist a designed assignment template under data_dir/reflection_templates.
    Body: {slug, content(json)}
    """
    data = request.get_json(silent=True) or {}
    slug = (data.get('slug') or '').strip()
    content = data.get('content')
    if not slug or not content:
        return jsonify({"error": "Missing slug or content"}), 400
    try:
        path = (Path(os.environ.get('REFLECTION_UI_DATA_DIR', str(Path.home() / '.reflection_ui'))) / 'reflection_templates')
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{slug}.json").write_text(json.dumps(content, indent=2))
        return jsonify({"status": "saved", "path": str(path / f"{slug}.json")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/design/use-next', methods=['POST'])
def design_use_next():
    """Store proposed phases in session to apply on next Start."""
    data = request.get_json(silent=True) or {}
    phases = data.get('phases')
    slug = (data.get('slug') or '').strip()
    if not isinstance(phases, list) or not phases:
        return jsonify({"error": "Invalid phases"}), 400
    session['custom_prompts_next'] = phases
    if slug:
        session['custom_prompts_preset_slug'] = slug
    return jsonify({"status": "ok", "count": len(phases), "slug": slug})

@app.route('/design/examples', methods=['GET'])
def design_examples():
    """List available example templates (bundled + local)."""
    examples = []
    # Always include a built-in generic template entry
    examples.append({'slug': 'generic_v1', 'title': 'Generic Assignment', 'source': 'built-in', 'phases_count': 6})
    # Bundled examples
    ex_dir = REPO_ROOT / 'docs' / 'examples' / 'assignment_templates'
    for p in sorted(ex_dir.glob('*.json')):
        try:
            data = json.loads(p.read_text())
            phases = _extract_phases_from_template(data)
            examples.append({
                'slug': p.stem,
                'title': data.get('assignment_title') or p.stem,
                'source': 'bundled',
                'phases_count': len(phases)
            })
        except Exception:
            continue
    # Local templates (data dir)
    local_dir = Path(os.environ.get('REFLECTION_UI_DATA_DIR', str(Path.home() / '.reflection_ui'))) / 'reflection_templates'
    if local_dir.exists():
        for p in sorted(local_dir.glob('*.json')):
            try:
                data = json.loads(p.read_text())
                phases = _extract_phases_from_template(data)
                examples.append({
                    'slug': p.stem,
                    'title': data.get('assignment_title') or p.stem,
                    'source': 'local',
                    'phases_count': len(phases)
                })
            except Exception:
                continue
    return jsonify({'examples': examples})

@app.route('/design/status', methods=['GET'])
def design_status():
    """Return current designer status for client gating.
    Includes key presence, session toggle, and last key test info (age only).
    """
    key_present = bool(os.environ.get('OPENAI_API_KEY'))
    llm_enabled = session.get('llm_enabled', key_present)
    last = load_last_key_test() or {}
    verified_recently = False
    try:
        if LAST_KEY_TEST_FILE.exists():
            age_sec = time.time() - LAST_KEY_TEST_FILE.stat().st_mtime
            verified_recently = age_sec <= 30 * 60
    except Exception:
        verified_recently = False
    return jsonify({
        'key_present': key_present,
        'llm_enabled': llm_enabled,
        'verified_recently': verified_recently,
        'last_request_id': last.get('request_id')
    })

@app.route('/design/example/<slug>', methods=['GET'])
def design_get_example(slug: str):
    """Return example phases for a given slug from bundled or local templates."""
    # Built-in templates fallback
    def builtin(sl: str):
        if sl == 'generic_v1':
            data = {
                'assignment_title': 'Generic Assignment',
                'outcomes': ['Communicate clearly', 'Support claims with evidence', 'Reflect on feedback'],
                'rubric': [
                    {'id': 'clarity', 'description': 'Clarity and organization'},
                    {'id': 'evidence', 'description': 'Use of evidence and sources'},
                    {'id': 'reflection', 'description': 'Reflection and iteration'}
                ],
                'constraints': {'phases': 6},
                'assignment_instructions': 'Complete the assignment addressing the outcomes with clear writing and appropriate citations.',
                'seed_phases': [
                    {'id': 'plan', 'phase': 'plan', 'type': 'planning', 'prompt': 'What is your plan? Describe steps and timeline.'},
                    {'id': 'draft', 'phase': 'draft', 'type': 'drafting', 'prompt': 'Write a short draft focusing on clarity and evidence.'},
                    {'id': 'reflect', 'phase': 'reflect', 'type': 'reflection', 'prompt': 'Reflect: what worked, what needs revision, and why?'}
                ]
            }
            phases = _extract_phases_from_template(data)
            return {'slug': sl, 'phases': phases, 'title': data['assignment_title'], 'outcomes': data['outcomes'], 'rubric': data['rubric'], 'constraints': data['constraints'], 'assignment_instructions': data['assignment_instructions']}
        if sl == 'search_comparison_v1':
            data = {
                'assignment_title': 'Search Comparison (DB vs Web)',
                'outcomes': ['Formulate search strategies', 'Compare scholarly vs web sources', 'Cite appropriately'],
                'rubric': [
                    {'id': 'strategy', 'description': 'Search strategy and query design'},
                    {'id': 'comparison', 'description': 'Comparison of database vs web findings'},
                    {'id': 'citations', 'description': 'Use of in-text citations and references'}
                ],
                'constraints': {'phases': 6},
                'assignment_instructions': 'Search for sources in both databases and the open web. Compare results and cite accordingly.',
                'seed_phases': [
                    {'id': 'capture', 'phase': 'capture', 'type': 'evidence', 'prompt': 'Capture 2-3 findings from each platform (DB and web).'},
                    {'id': 'analyze', 'phase': 'analyze', 'type': 'analysis', 'prompt': 'Analyze differences in credibility and relevance between platforms.'},
                    {'id': 'apply', 'phase': 'apply', 'type': 'application', 'prompt': 'State how you will use each platform for future research.'}
                ]
            }
            phases = _extract_phases_from_template(data)
            return {'slug': sl, 'phases': phases, 'title': data['assignment_title'], 'outcomes': data['outcomes'], 'rubric': data['rubric'], 'constraints': data['constraints'], 'assignment_instructions': data['assignment_instructions']}
        return None

    b = builtin(slug)
    if b:
        return jsonify(b)
    paths = [
        (Path(os.environ.get('REFLECTION_UI_DATA_DIR', str(Path.home() / '.reflection_ui'))) / 'reflection_templates' / f'{slug}.json'),
        REPO_ROOT / 'docs' / 'examples' / 'assignment_templates' / f'{slug}.json'
    ]
    for path in paths:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                phases = _extract_phases_from_template(data)
                # Extract optional template fields for autofill
                tpl = {}
                if isinstance(data, dict):
                    tpl['title'] = data.get('assignment_title')
                    tpl['outcomes'] = data.get('outcomes')
                    tpl['rubric'] = data.get('rubric')
                    tpl['constraints'] = data.get('constraints')
                    # Some templates might include instructions
                    tpl['assignment_instructions'] = data.get('assignment_instructions') or data.get('instructions')
                return jsonify({'slug': slug, 'phases': phases, **tpl})
            except Exception as e:
                return jsonify({'error': f'Failed to load example: {e}'}), 500
    return jsonify({'error': f'Example not found: {slug}'}), 404

@app.get('/canvas/status')
def canvas_status():
    """Report Canvas configuration and cache availability for UI gating."""
    _ensure_env_loaded()
    base = (os.environ.get('CANVAS_BASE_URL') or '').strip()
    key_present = bool((os.environ.get('CANVAS_API_KEY') or os.environ.get('CANVAS_API_TOKEN') or '').strip())
    cache_present = (CANVAS_CACHE_DIR.exists() and any(CANVAS_CACHE_DIR.glob('*.json')))
    courses_cache = CANVAS_CACHE_DIR / 'courses.json'
    course_count = 0
    try:
        if courses_cache.exists():
            arr = json.loads(courses_cache.read_text())
            if isinstance(arr, list):
                course_count = len(arr)
    except Exception:
        course_count = 0
    return jsonify({
        'configured': bool(base) and key_present,
        'base_url': base or None,
        'has_key': key_present,
        'cache_available': cache_present,
        'cached_courses': course_count
    })

@app.get('/canvas/courses')
def canvas_list_courses():
    """List courses from local cache (no network)."""
    courses_path = CANVAS_CACHE_DIR / 'courses.json'
    if not courses_path.exists():
        return jsonify({'error': 'No cached courses available'}), 404
    try:
        data = json.loads(courses_path.read_text())
        # Minimize payload
        out = []
        for c in data if isinstance(data, list) else []:
            out.append({'id': c.get('id'), 'name': c.get('name'), 'course_code': c.get('course_code')})
        return jsonify({'courses': out})
    except Exception as e:
        return jsonify({'error': f'Failed to read cached courses: {e}'}), 500

@app.get('/canvas/assignments/<int:course_id>')
def canvas_list_assignments(course_id: int):
    """List assignments for a course from local cache (no network)."""
    a_path = CANVAS_CACHE_DIR / f'assignments-{course_id}.json'
    if not a_path.exists():
        return jsonify({'error': f'No cached assignments for course {course_id}'}), 404
    try:
        data = json.loads(a_path.read_text())
        out = []
        for a in data if isinstance(data, list) else []:
            out.append({
                'id': a.get('id'),
                'name': a.get('name'),
                'due_at': a.get('due_at'),
                'points_possible': a.get('points_possible'),
                'submission_types': a.get('submission_types')
            })
        return jsonify({'assignments': out})
    except Exception as e:
        return jsonify({'error': f'Failed to read cached assignments: {e}'}), 500

def _read_cached_assignment_html(course_id: int, assignment_id: int) -> str:
    p = CANVAS_CACHE_DIR / 'assignments' / str(course_id) / f'{assignment_id}.html'
    try:
        if p.exists():
            return p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''
    return ''

def _html_to_text(html: str) -> str:
    if not html:
        return ''
    # Remove scripts/styles
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.S|re.I)
    # Replace <li> with bullets
    html = re.sub(r'\s*<li[^>]*>\s*', '\n- ', html, flags=re.I)
    # Replace headings with newlines
    html = re.sub(r'</?(h\d)[^>]*>', '\n\n', html, flags=re.I)
    # Replace <br> and <p> with newlines
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'</p>', '\n\n', html, flags=re.I)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', html)
    # Collapse whitespace
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()

@app.get('/canvas/assignment/<int:course_id>/<int:assignment_id>')
def canvas_get_assignment(course_id: int, assignment_id: int):
    """Return minimal assignment details from cache to seed designer.
    Includes title (from assignments list) and instructions (HTML->text).
    """
    # Title from assignments list
    title = None
    a_path = CANVAS_CACHE_DIR / f'assignments-{course_id}.json'
    try:
        if a_path.exists():
            arr = json.loads(a_path.read_text())
            if isinstance(arr, list):
                for a in arr:
                    if int(a.get('id') or -1) == assignment_id:
                        title = a.get('name')
                        break
    except Exception:
        title = None
    html = _read_cached_assignment_html(course_id, assignment_id)
    instructions = _html_to_text(html) if html else ''
    return jsonify({
        'course_id': course_id,
        'assignment_id': assignment_id,
        'title': title,
        'instructions': instructions,
    })

# ===== Live Canvas integration (guarded) =====
def _canvas_live_client():
    _ensure_env_loaded()
    try:
        from scripts.canvas.canvas_config import load_canvas_config, validate_against_template  # type: ignore
        from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
    except Exception as e:
        return None, None, None, f'Canvas config modules not available: {e}'
    try:
        cfg = load_canvas_config()
        ok, reason = validate_against_template(cfg)
    except SystemExit as se:
        # Convert hard exits (e.g., signature failure) into a soft error for UI
        return None, None, None, str(se)
    if not ok and os.environ.get('CANVAS_POLICY_OVERRIDE') != '1':
        return None, None, None, f'Canvas policy rejected: {reason}'
    base = (cfg.get('base_url') or '').strip()
    token = (cfg.get('api_key') or os.environ.get('CANVAS_API_KEY') or '').strip()
    if base and not base.startswith(('http://','https://')):
        base = 'https://' + base
    if not base or not token:
        return None, None, None, 'Missing CANVAS_BASE_URL or CANVAS_API_KEY'
    sess = requests.Session()
    sess.headers.update({'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
    allow = cfg.get('allow') or {}
    return base.rstrip('/'), sess, allow, None

def _canvas_paginate(sess: requests.Session, allow: dict, url: str, params=None):
    next_url = url
    p = params
    while next_url:
        ok, reason = None, None
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', next_url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            raise RuntimeError(f'Denied by Canvas allowlist: {reason}')
        r = sess.get(next_url, params=p, timeout=20)
        if not r.ok:
            raise RuntimeError(f'HTTP {r.status_code} for {next_url}')
        data = r.json()
        if isinstance(data, list):
            for item in data:
                yield item
        else:
            yield data
        # Parse Link header
        next_val = None
        link = r.headers.get('Link', '')
        for part in link.split(','):
            if 'rel="next"' in part:
                segs = part.strip().split(';')
                if segs:
                    u = segs[0].strip()
                    if u.startswith('<') and u.endswith('>'):
                        next_val = u[1:-1]
        next_url = next_val
        p = None

@app.get('/canvas/live/status')
def canvas_live_status():
    base, sess, allow, err = _canvas_live_client()
    return jsonify({
        'live_ready': bool(base and sess and not err),
        'error': err,
        'base_url': base,
        'has_key': bool(os.environ.get('CANVAS_API_KEY') or os.environ.get('CANVAS_API_TOKEN'))
    })

@app.get('/canvas/live/courses')
def canvas_live_courses():
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    search = (request.args.get('search') or '').strip()
    url = f"{base}/api/v1/courses"
    params = {'per_page': 50}
    if search:
        params['search_term'] = search
    try:
        items = []
        for c in _canvas_paginate(sess, allow, url, params=params):
            # minimal fields
            items.append({'id': c.get('id'), 'name': c.get('name'), 'course_code': c.get('course_code')})
        # Optional filter by prefixes/regex (preferred policy)
        prefixes = (allow.get('course_code_prefixes') or []) if isinstance(allow, dict) else []
        regex = (allow.get('course_code_regex') or '').strip() if isinstance(allow, dict) else ''
        if prefixes or regex:
            filtered = []
            for c in items:
                code = (c.get('course_code') or '')
                ok = (not prefixes or any(str(code).startswith(p) for p in prefixes))
                if ok and regex:
                    try:
                        ok = bool(re.match(regex, str(code)))
                    except re.error:
                        ok = ok
                if ok:
                    filtered.append(c)
            items = filtered
        # Fallback filter to allowed course IDs only if no prefix/regex policy present
        try:
            allowed_courses = set(int(x) for x in (allow.get('courses') or []))
        except Exception:
            allowed_courses = set()
        if (not prefixes and not regex) and allowed_courses:
            items = [c for c in items if int(c.get('id') or -1) in allowed_courses]
        return jsonify({'courses': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/canvas/live/assignments/<int:course_id>')
def canvas_live_assignments(course_id: int):
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    url = f"{base}/api/v1/courses/{course_id}/assignments"
    try:
        items = []
        for a in _canvas_paginate(sess, allow, url, params={'per_page': 100}):
            items.append({
                'id': a.get('id'),
                'name': a.get('name'),
                'due_at': a.get('due_at'),
                'points_possible': a.get('points_possible'),
                'submission_types': a.get('submission_types')
            })
        return jsonify({'assignments': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/canvas/live/assignment/<int:course_id>/<int:assignment_id>')
def canvas_live_assignment(course_id: int, assignment_id: int):
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    url = f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    try:
        ok, reason = None, None
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
        r = sess.get(url, timeout=20)
        if not r.ok:
            return jsonify({'error': f'HTTP {r.status_code}'}), 502
        data = r.json() or {}
        title = data.get('name')
        desc_html = data.get('description') or ''
        instructions = _html_to_text(desc_html)
        return jsonify({'course_id': course_id, 'assignment_id': assignment_id, 'title': title, 'instructions': instructions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _extract_list_after_heading(html: str, keywords: list[str]) -> list[str]:
    if not isinstance(html, str) or not html:
        return []
    try:
        # find a heading whose text matches any keyword
        for m in re.finditer(r'(?is)<h[1-6][^>]*>(.*?)</h[1-6]>', html):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip().lower()
            if any(k in text for k in (kw.lower() for kw in keywords)):
                # search next <ul> after heading
                # Try <ul> or <ol> after heading
                seg = html[m.end():]
                ul = re.search(r'(?is)<(ul|ol)[^>]*>(.*?)</\1>', seg)
                if ul:
                    items = []
                    for li in re.finditer(r'(?is)<li[^>]*>(.*?)</li>', ul.group(2)):
                        it = re.sub(r'<[^>]+>', '', li.group(1)).strip()
                        if it:
                            items.append(it)
                    if items:
                        return items
                break
    except Exception:
        return []
    return []

def _extract_objectives_fallback(html: str) -> list[str]:
    """Best-effort fallback: collect prominent bullet-like lines if no heading found."""
    if not isinstance(html, str) or not html:
        return []
    # Gather all list items in the document
    items = []
    try:
        for li in re.finditer(r'(?is)<li[^>]*>(.*?)</li>', html):
            it = re.sub(r'<[^>]+>', '', li.group(1)).strip()
            if it:
                items.append(it)
    except Exception:
        items = []
    # Limit to a reasonable number to avoid dumping entire page
    return items[:12]

@app.get('/canvas/live/course_objectives/<int:course_id>')
def canvas_live_course_objectives(course_id: int):
    """Extract learning objectives/outcomes from syllabus or front page (best effort)."""
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    try:
        ok, reason = None, None
        url = f"{base}/api/v1/courses/{course_id}"
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
        r = sess.get(url, params={'include[]': 'syllabus_body'}, timeout=20)
        if r.ok:
            data = r.json() or {}
            html = data.get('syllabus_body') or ''
            objs = _extract_list_after_heading(html, ['Learning Objectives', 'Objectives', 'Outcomes', 'Learning Outcomes'])
            if objs:
                return jsonify({'objectives': objs, 'source': 'syllabus'})
        # Try front page
        fp_url = f"{base}/api/v1/courses/{course_id}/front_page"
        ok, reason = None, None
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', fp_url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
        r = sess.get(fp_url, timeout=20)
        if r.ok:
            pg = r.json() or {}
            url_slug = pg.get('url')
            if url_slug:
                page_url = f"{base}/api/v1/courses/{course_id}/pages/{url_slug}"
                ok, reason = None, None
                try:
                    from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
                    ok, reason = is_allowed_request('', page_url, 'GET', allow)
                except Exception:
                    ok = True
                if not ok:
                    return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
                rp = sess.get(page_url, timeout=20)
                if rp.ok:
                    body = (rp.json() or {}).get('body') or ''
                    objs = _extract_list_after_heading(body, ['Learning Objectives', 'Objectives', 'Outcomes', 'Learning Outcomes'])
                    if objs:
                        return jsonify({'objectives': objs, 'source': 'front_page'})
        # Fallback: try any <li> items as rough objectives
        try:
            any_html = html if 'html' in locals() else ''
        except Exception:
            any_html = ''
        fallback = _extract_objectives_fallback(any_html)
        return jsonify({'objectives': fallback, 'source': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/canvas/live/course_rubrics/<int:course_id>')
def canvas_live_course_rubrics(course_id: int):
    """List course rubrics with basic criteria."""
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    url = f"{base}/api/v1/courses/{course_id}/rubrics"
    try:
        ok, reason = None, None
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
        r = sess.get(url, timeout=20)
        if not r.ok:
            return jsonify({'error': f'HTTP {r.status_code}'}), 502
        data = r.json() or []
        out = []
        for rub in data if isinstance(data, list) else []:
            crits = []
            for i, c in enumerate(rub.get('data') or [], start=1):
                desc = (c.get('description') or c.get('long_description') or '').strip()
                cid = c.get('id') or c.get('criterion_id') or f'crit_{i}'
                if desc:
                    crits.append({'id': str(cid), 'description': desc})
            out.append({'id': rub.get('id'), 'title': rub.get('title'), 'criteria': crits})
        return jsonify({'rubrics': out})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/canvas/live/assignment_full/<int:course_id>/<int:assignment_id>')
def canvas_live_assignment_full(course_id: int, assignment_id: int):
    """Return assignment detail including rubric (if available)."""
    base, sess, allow, err = _canvas_live_client()
    if err:
        return jsonify({'error': err}), 400
    url = f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    try:
        ok, reason = None, None
        try:
            from scripts.canvas.canvas_guard import is_allowed_request  # type: ignore
            ok, reason = is_allowed_request('', url, 'GET', allow)
        except Exception:
            ok = True
        if not ok:
            return jsonify({'error': f'Denied by Canvas allowlist: {reason}'}), 403
        r = sess.get(url, params={'include[]': 'rubric'}, timeout=20)
        if not r.ok:
            return jsonify({'error': f'HTTP {r.status_code}'}), 502
        data = r.json() or {}
        title = data.get('name')
        desc_html = data.get('description') or ''
        instructions = _html_to_text(desc_html)
        rubric_items = []
        rub = data.get('rubric') or []
        if isinstance(rub, list) and rub:
            for i, crit in enumerate(rub, start=1):
                desc = (crit.get('description') or crit.get('long_description') or '').strip()
                cid = crit.get('id') or crit.get('criterion_id') or f'crit_{i}'
                if desc:
                    rubric_items.append({'id': str(cid), 'description': desc})
        return jsonify({'course_id': course_id, 'assignment_id': assignment_id, 'title': title, 'instructions': instructions, 'rubric': rubric_items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Load environment
    env_file = REPO_ROOT / ".env"
    # Also load local secrets if present (not tracked)
    secrets_file = REPO_ROOT / '.local_context' / 'secrets.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    if secrets_file.exists():
        with open(secrets_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

    port = int(os.environ.get('PORT', '5004'))
    app.run(debug=True, host='0.0.0.0', port=port)

# Helpers (defined at end to avoid cluttering route logic)
def _load_demo_texts(assignment_type: str) -> dict:
    """Load optional demo texts for an assignment type.
    Checks local context first, then docs examples. Returns {phase: text}.
    """
    def load_json(path: Path):
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            return None
        return None

    # Prefer local overrides
    local_dir = Path(os.environ.get('REFLECTION_UI_DATA_DIR', str(Path.home() / '.reflection_ui'))) / 'reflection_templates'
    local_file = local_dir / f'{assignment_type}_demo_texts.json'
    data = load_json(local_file)
    if isinstance(data, dict):
        return data
    # Fallback to bundled examples
    ex_dir = REPO_ROOT / 'docs' / 'examples' / 'assignment_templates'
    ex_file = ex_dir / f'{assignment_type}_demo_texts.json'
    data = load_json(ex_file)
    if isinstance(data, dict):
        return data
    return {}

def _extract_phases_from_template(data) -> list:
    """Normalize various template shapes to a phases list of {phase,type,prompt}."""
    if isinstance(data, list):
        # Already a phases array
        return [p for p in data if isinstance(p, dict) and p.get('prompt')]
    if isinstance(data, dict):
        if isinstance(data.get('seed_phases'), list):
            return [
                {'phase': (p.get('id') or p.get('phase')), 'type': p.get('type'), 'prompt': p.get('prompt')}
                for p in data['seed_phases'] if isinstance(p, dict) and p.get('prompt')
            ]
        if isinstance(data.get('phases'), list):
            return [p for p in data['phases'] if isinstance(p, dict) and p.get('prompt')]
    return []
