#!/usr/bin/env python3
"""
Pre-submission reflection MCP server
Supports structured one-shot reflection with possibility space opening
"""

import json
import sys
import os
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'

def mcp_result_text(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _auth_mcp_cmd() -> Optional[str]:
    # Allow external override; fallback to repo bin if present
    c = (os.environ.get('AUTH_MCP_CMD') or '').strip()
    if c:
        return c
    cand = REPO_ROOT / 'bin' / 'auth-mcp'
    return str(cand) if cand.exists() else None


def _call_auth_mcp(method: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cmd = _auth_mcp_cmd()
    if not cmd:
        return None
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": method, "arguments": arguments},
    }
    try:
        proc = os.popen(f"{cmd}", 'w')  # ensure process exists? Use subprocess for robust call
    except Exception:
        proc = None
    import subprocess as _sp
    try:
        result = _sp.run([cmd], input=json.dumps(payload) + "\n", capture_output=True, text=True, cwd=str(REPO_ROOT), env=os.environ.copy())
        if result.returncode != 0:
            return None
        out = json.loads(result.stdout.strip())
        txt = (((out.get('result') or {}).get('content') or [{}])[0]).get('text')
        return json.loads(txt) if txt else None
    except Exception:
        return None


def _get_openai_api_key() -> Optional[str]:
    # Prefer auth-mcp vault; fallback to env
    res = _call_auth_mcp('get_secret', {"name": "openai_api_key"})
    if isinstance(res, dict) and res.get('found'):
        v = str(res.get('value') or '').strip()
        if v:
            return v
    env = os.environ.get('OPENAI_API_KEY', '').strip()
    return env or None

def list_tools() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "provider_status",
                "description": "Report OpenAI provider status; optional 1-token probe to read rate-limit headers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "probe": {"type": "boolean", "description": "If true, makes a single minimal API call (1 token) to fetch headers", "default": False}
                    },
                    "required": []
                }
            },
            {
                "name": "get_costs",
                "description": "Return cost totals and recent call details. Reads current tracker or saved logs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Optional session id to load saved totals"},
                        "recent_n": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                        "aggregate_last": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Optional: include aggregated stats over last N sessions"}
                    },
                    "required": []
                }
            },
            {
                "name": "start_reflection",
                "description": "Begin a structured reflection session for an assignment",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "student_id": {"type": "string", "description": "Student identifier"},
                        "assignment_type": {"type": "string", "description": "Type of assignment (e.g., 'search_comparison')"},
                        "assignment_context": {"type": "string", "description": "Assignment description or rubric"},
                        "ai_instructions": {"type": "string", "description": "Optional instructor guidance to shape insights (shown to students)"},
                        "guardrails": {
                            "type": "object",
                            "description": "Optional LLM guardrails applied at summary",
                            "properties": {
                                "temperature": {"type": "number", "minimum": 0, "maximum": 1},
                                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 200}
                            }
                        },
                        "rubric_config": {"type": "string", "description": "Optional JSON rubric definition for LLM scoring"}
                    },
                    "required": ["student_id", "assignment_type"]
                }
            },
            {
                "name": "get_probing_question",
                "description": "Return a single reflective question to deepen current phase thinking (no answers, question only)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "phase": {"type": "string", "description": "Optional current phase name"},
                        "draft_text": {"type": "string", "description": "Optional current draft text for this phase"}
                    },
                    "required": ["session_id"]
                }
            },
            {
                "name": "submit_reflection_response",
                "description": "Submit student response to a reflection prompt",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Reflection session ID"},
                        "response": {"type": "string", "description": "Student's reflection response"},
                        "prompt_phase": {"type": "string", "description": "Which reflection phase this responds to"}
                    },
                    "required": ["session_id", "response", "prompt_phase"]
                }
            },
            {
                "name": "get_reflection_summary",
                "description": "Get final reflection summary and insights",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Reflection session ID"}
                    },
                    "required": ["session_id"]
                }
            },
            {
                "name": "propose_prompt_workflow",
                "description": "Design-time: propose a phased prompt workflow from outcomes/rubric (LLM required)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "assignment_title": {"type": "string"},
                        "assignment_instructions": {"type": "string"},
                        "learner_level": {"type": "string"},
                        "outcomes": {"type": "array", "items": {"type": "string"}},
                        "rubric": {"type": "array", "items": {"type": "object"}},
                        "constraints": {"type": "object"},
                        "examples": {"type": "array", "items": {"type": "string"}},
                        "pitfalls": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["assignment_title"]
                }
            },
            {
                "name": "get_session_context",
                "description": "Return prior responses and probing questions for the session",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"}
                    },
                    "required": ["session_id"]
                }
            },
            {
                "name": "get_current_prompt",
                "description": "Get the current prompt for a reflection session",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Reflection session ID"}
                    },
                    "required": ["session_id"]
                }
            }
        ]
    }

class ReflectionServer:
    """MCP server for pre-submission reflection with structured scaffolding"""

    def __init__(self):
        self.sessions = {}  # Simple in-memory storage for now
        # Create sessions directory if it doesn't exist
        self.sessions_dir = REPO_ROOT / ".local_context" / "reflection_sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Initialize cost tracker
        try:
            sys.path.insert(0, str(REPO_ROOT / "reflection_mcp"))
            from cost_tracker import CostTracker
            self.cost_tracker = CostTracker()
            print(f"Cost tracker initialized", file=sys.stderr)
        except Exception as e:
            print(f"Cost tracker failed: {e}", file=sys.stderr)
            self.cost_tracker = None  # Graceful fallback

    def _load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session from file if not in memory"""
        if session_id in self.sessions:
            return self.sessions[session_id]

        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                session_data = json.loads(session_file.read_text())
                self.sessions[session_id] = session_data
                return session_data
            except Exception:
                pass
        return None

    def _save_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Save session to both memory and file"""
        self.sessions[session_id] = session_data
        session_file = self.sessions_dir / f"{session_id}.json"
        try:
            session_file.write_text(json.dumps(session_data, indent=2))
        except Exception:
            pass  # Continue even if file save fails

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove simple triple-backtick code fences (```json ... ``` or ``` ... ```)
        to get at the raw JSON payload returned by some models."""
        if not isinstance(text, str):
            return text
        t = text.strip()
        if t.startswith("```json") and t.endswith("```"):
            return t[7:-3].strip()
        if t.startswith("```") and t.endswith("```"):
            return t[3:-3].strip()
        return t

    def start_reflection(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new reflection session with structured prompts"""
        student_id = args["student_id"]
        assignment_type = args["assignment_type"]
        assignment_context = args.get("assignment_context", "")
        # Optional instructor guidance and guardrails
        ai_instructions = (args.get("ai_instructions", "") or "").strip()
        if len(ai_instructions) > 500:
            ai_instructions = ai_instructions[:500]
        raw_guardrails = args.get("guardrails") or {}
        # Parse and clamp guardrails
        gr_temp = None
        gr_max = None
        try:
            if raw_guardrails.get("temperature") is not None:
                gr_temp = float(raw_guardrails.get("temperature"))
        except Exception:
            gr_temp = None
        try:
            if raw_guardrails.get("max_tokens") is not None:
                gr_max = int(raw_guardrails.get("max_tokens"))
        except Exception:
            gr_max = None
        if gr_temp is not None:
            gr_temp = max(0.0, min(1.0, gr_temp))
        if gr_max is not None:
            gr_max = max(1, min(200, gr_max))
        guardrails = {}
        if gr_temp is not None:
            guardrails["temperature"] = gr_temp
        if gr_max is not None:
            guardrails["max_tokens"] = gr_max

        # Optional rubric_config (JSON string)
        rubric_config = None
        raw_rubric = args.get("rubric_config")
        if raw_rubric:
            try:
                rubric_config = json.loads(raw_rubric)
            except Exception:
                rubric_config = None

        # Generate session ID
        session_id = f"{student_id}_{assignment_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Get prompts for assignment type
        # Optional custom prompts (designer-provided)
        custom_prompts = args.get("custom_prompts")
        prompts = None
        if isinstance(custom_prompts, list) and custom_prompts:
            # Minimal validation: accept either 'phase' or 'id' for identifier
            prompts = []
            for p in custom_prompts:
                if isinstance(p, dict) and p.get('type') and p.get('prompt'):
                    phase_id = p.get('phase') or p.get('id')
                    if phase_id:
                        prompts.append({"phase": phase_id, "type": p['type'], "prompt": p['prompt']})
        if not prompts:
            prompts = self.get_reflection_prompts(assignment_type)

        # Initialize session
        session_data = {
            "session_id": session_id,
            "student_id": student_id,
            "assignment_type": assignment_type,
            "assignment_context": assignment_context,
            "ai_instructions": ai_instructions,
            "guardrails": guardrails,
            "rubric_config": rubric_config,
            "prompts": prompts,
            "responses": {},
            "current_phase": 0,
            "created_at": _now_iso(),
            "status": "active"
        }

        self._save_session(session_id, session_data)

        # Return first prompt
        first_prompt = prompts[0] if prompts else {"phase": "complete", "prompt": "No prompts available"}

        # Begin cost tracking early so adaptive probes are accounted for
        try:
            if self.cost_tracker:
                self.cost_tracker.start_session(session_id)
        except Exception:
            pass

        return {
            "session_id": session_id,
            "current_prompt": first_prompt,
            "total_phases": len(prompts),
            "phase_number": 1
        }

    def submit_reflection_response(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Submit student response and get next prompt"""
        session_id = args["session_id"]
        response = args["response"]
        prompt_phase = args["prompt_phase"]

        session = self._load_session(session_id)
        if not session:
            return {"error": "Session not found"}

        # Store response (and keep per-phase history for refinement loops)
        entry = {"response": response, "timestamp": _now_iso()}
        session.setdefault("responses_history", {})
        hist = session["responses_history"].setdefault(prompt_phase, [])
        hist.append(entry)
        session["responses"][prompt_phase] = entry

        # Move to next phase
        session["current_phase"] += 1
        current_phase = session["current_phase"]

        self._save_session(session_id, session)

        # Check if we have more prompts
        if current_phase < len(session["prompts"]):
            next_prompt = session["prompts"][current_phase]
            return {
                "session_id": session_id,
                "current_prompt": next_prompt,
                "phase_number": current_phase + 1,
                "total_phases": len(session["prompts"])
            }
        else:
            # Reflection complete
            session["status"] = "complete"
            session["completed_at"] = _now_iso()
            self._save_session(session_id, session)

            return {
                "session_id": session_id,
                "status": "complete",
                "message": "Reflection complete! You can now review your insights and submit your assignment."
            }

    def get_current_prompt(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get the current prompt for a session"""
        session_id = args["session_id"]
        session = self._load_session(session_id)

        if not session:
            return {"error": "Session not found"}

        current_phase = session["current_phase"]
        prompts = session["prompts"]

        if current_phase < len(prompts):
            current_prompt = prompts[current_phase]
            return {
                "session_id": session_id,
                "current_prompt": current_prompt,
                "phase_number": current_phase + 1,
                "total_phases": len(prompts),
                "status": session["status"]
            }
        else:
            return {
                "session_id": session_id,
                "status": "complete",
                "message": "All reflection prompts completed"
            }

    def get_reflection_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate reflection summary and insights"""
        session_id = args["session_id"]
        session = self._load_session(session_id)

        if not session:
            return {"error": "Session not found"}

        api_key = _get_openai_api_key() or ''
        # Strict: require API for summary features (no heuristics)
        if not api_key:
            return {"error": "LLM unavailable: provide OPENAI_API_KEY"}

        # If API is available, accumulate cost across all summary-time calls
        if self.cost_tracker and 'session_id' in session:
            try:
                cur = self.cost_tracker.current_session
                if not cur or cur.get('session_id') != session['session_id']:
                    self.cost_tracker.start_session(session['session_id'])
            except Exception:
                pass

        insights = self.generate_insights(session)

        # Determine rubric configuration
        rubric_config = session.get("rubric_config")
        atype = session.get("assignment_type")
        if not rubric_config and atype == "search_comparison":
            rubric_config = [
                {"id": "documented_process", "description": "Clearly describes process on both Google and an academic database"},
                {"id": "specific_examples", "description": "Provides specific, concrete examples from the searches"},
                {"id": "balanced_analysis", "description": "Compares platforms with attention to quality and relevance"},
                {"id": "future_application", "description": "States how learning will shape future research choices"}
            ]
        elif not rubric_config and atype == "scope_exercise":
            # Minimal SCOPE rubric to trigger analysis + scoring passes
            rubric_config = [
                {"id": "non_yes_no_stem", "description": "Question framed with How/Why/What factors/To what extent (not yes/no)"},
                {"id": "bounded_scope", "description": "Population, time, and place specified"},
                {"id": "mechanism_named", "description": "Mechanisms/constructs are named (e.g., sleep latency; exposure-response)"},
                {"id": "lit_check_viable", "description": "Quick literature check indicates sufficient credible sources"}
            ]

        # Score rubric via LLM only (no heuristic fallback)
        if rubric_config:
            analysis = self.generate_structured_analysis(session)
            rubric_alignment = self.score_rubric_with_llm(session, analysis, rubric_config)
        else:
            rubric_alignment = None

        readiness = self.assess_submission_readiness(session)

        # End and attach cost analysis if a session is being tracked
        cost_totals = None
        if self.cost_tracker and self.cost_tracker.current_session:
            try:
                cost_totals = self.cost_tracker.end_session()
                if cost_totals:
                    session['cost_analysis'] = cost_totals
            except Exception:
                pass

        # Generate summary
        summary = {
            "session_id": session_id,
            "student_id": session["student_id"],
            "assignment_type": session["assignment_type"],
            "responses": session["responses"],
            "insights": insights,
            "rubric_alignment": rubric_alignment,
            "readiness_assessment": readiness,
            "completion_status": session.get("status", "active"),
            "created_at": session["created_at"],
            "completed_at": session.get("completed_at"),
            "cost_analysis": session.get("cost_analysis"),
            "applied_ai_instructions": session.get("ai_instructions"),
            "guardrails": session.get("guardrails") or {}
        }

        return summary

    def get_session_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = args.get("session_id")
        session = self._load_session(session_id)
        if not session:
            return {"error": "Session not found"}
        return {
            "session_id": session_id,
            "responses": session.get("responses", {}),
            "probes": session.get("probes", [])
        }

    def get_costs(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return cost totals and recent call details.

        Inputs:
          - session_id (optional): if provided, tries to load saved *_costs.json
          - recent_n (optional): include last N api_calls from current tracker
          - aggregate_last (optional): include aggregated stats across last N sessions
        """
        recent_n = int(args.get('recent_n') or 5)
        out: Dict[str, Any] = {}
        # Current tracker snapshot (in-memory, if any)
        cur = getattr(self, 'cost_tracker', None)
        if cur and cur.current_session:
            cs = cur.current_session
            out['current'] = {
                'session_id': cs.get('session_id'),
                'model': cs.get('model'),
                'started_at': cs.get('started_at'),
                'api_calls_count': len(cs.get('api_calls', [])),
                'recent_calls': cs.get('api_calls', [])[-recent_n:]
            }
        # Saved log for a session_id
        sid = (args.get('session_id') or '').strip()
        if sid:
            try:
                from pathlib import Path as _P
                log_path = _P(__file__).resolve().parents[1] / '.local_context' / 'cost_logs' / f'{sid}_costs.json'
                if log_path.exists():
                    data = json.loads(log_path.read_text())
                    out['saved'] = {
                        'session_id': data.get('session_id'),
                        'totals': data.get('totals'),
                        'first_api_meta': (data.get('api_calls') or [{}])[0].get('meta') if data.get('api_calls') else None
                    }
                else:
                    out['saved'] = {'error': 'not_found'}
            except Exception as e:
                out['saved'] = {'error': str(e)}
        # Aggregated stats across recent sessions
        agg_n = args.get('aggregate_last')
        if cur and agg_n:
            try:
                out['aggregate'] = cur.get_aggregated_stats(int(agg_n))
            except Exception as e:
                out['aggregate'] = {'error': str(e)}
        return out

    def get_reflection_prompts(self, assignment_type: str) -> List[Dict[str, Any]]:
        """Get structured prompts for assignment type"""

        if assignment_type == "search_comparison":
            return [
                {
                    "phase": "context_capture",
                    "type": "divergent",
                    "prompt": "Describe your search experience with both the academic database and Google. What did the actual process of searching feel like on each platform? Include specific details about navigation, search strategies, and any challenges you encountered."
                },
                {
                    "phase": "quality_patterns",
                    "type": "divergent",
                    "prompt": "What patterns did you notice in the types of sources each platform returned? Think about authority, publication types, recency, depth of coverage, and credibility indicators. What surprised you about the differences?"
                },
                {
                    "phase": "relevance_assessment",
                    "type": "scaffolded",
                    "prompt": "Which platform returned results more directly relevant to your research question? Consider not just the immediate usefulness, but also how the sources might support academic research differently. What made certain sources feel more or less valuable?"
                },
                {
                    "phase": "insight_synthesis",
                    "type": "convergent",
                    "prompt": "Based on your experience, what is your main insight about the fundamental differences between academic and general web search? How do these differences serve different research purposes?"
                },
                {
                    "phase": "application_planning",
                    "type": "convergent",
                    "prompt": "How will this comparison change your research approach for future assignments? When would you use each type of search, and what role should each play in academic research?"
                },
                {
                    "phase": "submission_check",
                    "type": "self_assessment",
                    "prompt": "Review your work: Have you thoroughly documented your Google search process? Does your reflection include specific examples from both searches? Is your analysis balanced rather than simply favoring one platform? Will your insights help you make better research decisions?"
                }
            ]

        # Default generic prompts for other assignment types
        return [
            {
                "phase": "experience_capture",
                "type": "divergent",
                "prompt": "Describe your experience working on this assignment. What went well? What was challenging? Include specific details about your process and approach."
            },
            {
                "phase": "learning_reflection",
                "type": "convergent",
                "prompt": "What did you learn from this assignment? How does it connect to course concepts and your broader understanding of the subject?"
            },
            {
                "phase": "quality_check",
                "type": "self_assessment",
                "prompt": "Review your work against the assignment requirements. What aspects are you most confident about? What might need more attention before submission?"
            }
        ]

    def generate_insights(self, session: Dict[str, Any]) -> List[str]:
        """Generate insights from reflection responses using LLM"""
        api_key = _get_openai_api_key() or ''
        if not api_key:
            raise RuntimeError("LLM unavailable: provide OPENAI_API_KEY")

        responses = session["responses"]
        assignment_type = session["assignment_type"]

        # Prepare reflection text for analysis
        reflection_text = ""
        for phase, resp_data in responses.items():
            reflection_text += f"{phase}: {resp_data.get('response', '')}\n\n"

        # LLM prompt for insight generation
        system_prompt = (
            "You are a supportive learning coach. Analyze the student's own reflection and provide short, student-facing coaching notes. "
            "Return ONLY a JSON array of 3-5 notes. Focus on: specificity (concrete details), evidence (what supports the claim), balance (compare alternatives), and next steps. "
            "Avoid grading or evaluative language; speak directly to the student. Each note must be grounded in their own text."
        )

        # Append optional instructor guidance transparently
        extra_guidance = session.get("ai_instructions") or ""
        if extra_guidance:
            system_prompt += "\n\nInstructor guidance (show to student): " + extra_guidance

        user_prompt = f"Assignment type: {assignment_type}\n\nStudent reflection:\n{reflection_text}"

        try:
            # Apply optional guardrails
            gr = session.get("guardrails") or {}
            temperature = gr.get("temperature", 0.1)
            max_tokens = gr.get("max_tokens", 200)

            payload = {
                "model": "gpt-4o-mini",  # Low cost model
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": max_tokens  # Keep costs low
            }

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )

            start_time = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
            latency_ms = int((time.time() - start_time) * 1000)

            # Log the actual API call with real token usage
            if self.cost_tracker and self.cost_tracker.current_session:
                self.cost_tracker.log_api_call(
                    payload,
                    data,
                    latency_ms,
                    metadata={
                        "stage": "runtime_summary",
                        "tool_name": "generate_structured_analysis"
                    }
                )

            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            content = self._strip_code_fence(content)
            try:
                insights = json.loads(content)
            except Exception:
                # Fallback: wrap raw text, avoid hard failure
                return [content[:300] or "(empty response)"]
            if isinstance(insights, list):
                return [str(insight) for insight in insights[:5]]  # Max 5 insights
            else:
                return ["Generated insight analysis"]

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else ''
            raise RuntimeError(f"LLM call failed: HTTP {getattr(e, 'code', '?')} — {body[:400]}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def _generate_heuristic_insights(self, session: Dict[str, Any]) -> List[str]:
        """Deprecated: heuristics removed. Kept for compatibility."""
        raise RuntimeError("Heuristic insights disabled: LLM required")

    def generate_structured_analysis(self, session: Dict[str, Any]) -> Dict[str, Any]:
        api_key = _get_openai_api_key() or ''
        responses = session.get("responses", {})
        assignment_type = session.get("assignment_type", "")
        if not api_key:
            raise RuntimeError("LLM unavailable: provide OPENAI_API_KEY")
        reflection_text = "\n\n".join(f"{k}: {v.get('response','')}" for k,v in responses.items())
        system_prompt = (
            "Extract structured analysis from student reflection. Return ONLY JSON with keys: "
            "phases (map phase->key_points[list of strings]), patterns[list], concerns[list], strengths[list]."
        )
        user_prompt = f"Assignment type: {assignment_type}\n\nReflection text:\n{reflection_text}"
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 200
        }
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
            latency_ms = int((time.time() - start_time) * 1000)
            if self.cost_tracker and self.cost_tracker.current_session:
                self.cost_tracker.log_api_call(
                    payload,
                    data,
                    latency_ms,
                    metadata={
                        "stage": "runtime_summary",
                        "tool_name": "score_rubric_with_llm"
                    }
                )
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            content = self._strip_code_fence(content)
            try:
                return json.loads(content)
            except Exception:
                # Tolerant fallback structure for downstream consumers
                return {"phases": {}, "patterns": [], "concerns": [], "strengths": [], "_raw": content, "_parse_error": True}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else ''
            raise RuntimeError(f"LLM call failed: HTTP {getattr(e, 'code', '?')} — {body[:400]}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def provider_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Report provider configuration; optionally make a 1-token probe to get headers.

        Returns:
          - key_present: bool
          - model: str
          - probe_result: {status_code, headers, error?} when probe=True
        """
        api_key = (_get_openai_api_key() or '').strip()
        out: Dict[str, Any] = {
            "key_present": bool(api_key),
            "model": "gpt-4o-mini"
        }
        if not args.get("probe"):
            return out
        if not api_key:
            out["probe_result"] = {"error": "no_api_key"}
            return out
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Return the word pong."},
                {"role": "user", "content": "ping"}
            ],
            "max_tokens": 1
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                # Collect rate-limit headers when available
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                out["probe_result"] = {
                    "status_code": resp.status,
                    "headers": {k: hdrs.get(k) for k in (
                        "x-ratelimit-limit-requests",
                        "x-ratelimit-remaining-requests",
                        "x-ratelimit-limit-tokens",
                        "x-ratelimit-remaining-tokens",
                        "x-request-id"
                    )}
                }
        except urllib.error.HTTPError as e:
            hdrs = {k.lower(): v for k, v in (getattr(e, 'headers', {}) or {}).items()}
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else ''
            out["probe_result"] = {
                "status_code": getattr(e, 'code', None),
                "headers": {k: hdrs.get(k) for k in (
                    "retry-after",
                    "x-ratelimit-limit-requests",
                    "x-ratelimit-remaining-requests",
                    "x-ratelimit-limit-tokens",
                    "x-ratelimit-remaining-tokens",
                    "x-request-id"
                )},
                "error": body[:400]
            }
        except Exception as e:
            out["probe_result"] = {"error": str(e)}
        return out

    def score_rubric_with_llm(self, session: Dict[str, Any], analysis: Dict[str, Any], rubric: List[Dict[str, Any]]) -> Dict[str, Any]:
        api_key = _get_openai_api_key() or ''
        if not api_key:
            raise RuntimeError("LLM unavailable: provide OPENAI_API_KEY")
        system_prompt = (
            "Score the rubric strictly using the provided analysis. Return ONLY JSON: "
            "{criteria_met:{id:bool}, details:{id:{rationale:string, evidence:[short quotes]}}}. "
            "Do not infer beyond analysis; if evidence is missing, mark false."
        )
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"analysis": analysis, "rubric": rubric})}
            ],
            "max_tokens": 220
        }
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latency_ms = int((time.time() - start_time) * 1000)
            if self.cost_tracker and self.cost_tracker.current_session:
                self.cost_tracker.log_api_call(
                    payload,
                    data,
                    latency_ms,
                    metadata={
                        "stage": "runtime_summary",
                        "tool_name": "generate_insights"
                    }
                )
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            content = self._strip_code_fence(content)
            try:
                result = json.loads(content)
            except Exception:
                result = {"criteria_met": {}, "details": {}, "_raw": content, "_parse_error": True}
            return {
                "criteria_met": result.get("criteria_met", {}),
                "details": result.get("details", {})
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else ''
            raise RuntimeError(f"LLM call failed: HTTP {getattr(e, 'code', '?')} — {body[:400]}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def get_probing_question(self, args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = args.get("session_id")
        phase = args.get("phase")
        draft_text = (args.get("draft_text") or "").strip()
        session = self._load_session(session_id)
        if not session:
            return {"error": "Session not found"}
        api_key = _get_openai_api_key() or ''
        if not api_key:
            return {"error": "LLM unavailable: provide OPENAI_API_KEY"}
        # Build prompt from last or current phase
        text = draft_text
        if not text and phase and phase in session.get("responses", {}):
            text = session["responses"][phase]["response"]
        elif not text and session.get("responses"):
            # Use most recent response
            last = list(session["responses"].values())[-1]
            text = last.get("response", "")
        system_prompt = (
            "Return ONE short reflective question (no answers) to deepen the student's thinking. "
            "Keep it under 20 words."
        )
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Student response: {text}"}
            ],
            "max_tokens": 40
        }
        try:
            # Basic retry for transient rate limits
            attempt = 0
            last_err = None
            data = None
            start_time = time.time()
            while attempt < 3 and data is None:
                req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    },
                    method="POST"
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        break
                except urllib.error.HTTPError as e:
                    last_err = e
                    code = getattr(e, 'code', 0)
                    if code in (429, 500, 502, 503):
                        retry_after = 0.7
                        try:
                            hdr_ra = e.headers.get('Retry-After') if hasattr(e, 'headers') else None
                            if hdr_ra:
                                retry_after = max(retry_after, float(hdr_ra))
                        except Exception:
                            pass
                        time.sleep(retry_after)
                        attempt += 1
                        continue
                    else:
                        raise
            if data is None and last_err is not None:
                body = last_err.read().decode("utf-8", errors="ignore") if hasattr(last_err, 'read') else ''
                raise RuntimeError(f"LLM call failed: HTTP {getattr(last_err, 'code', '?')} — {body[:400]}")
            latency_ms = int((time.time() - start_time) * 1000)
            # Ensure cost session exists for probes
            if self.cost_tracker and (not self.cost_tracker.current_session) and session.get('session_id'):
                try:
                    self.cost_tracker.start_session(session['session_id'])
                except Exception:
                    pass
            if self.cost_tracker and self.cost_tracker.current_session:
                self.cost_tracker.log_api_call(
                    payload,
                    data,
                    latency_ms,
                    metadata={
                        "stage": "runtime_probe",
                        "tool_name": "get_probing_question",
                        "phase": phase,
                        "used_draft": bool(draft_text)
                    }
                )
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "").strip()
            # Prepare lightweight cost info from this call
            usage = data.get("usage", {})
            cost_info = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "latency_ms": latency_ms,
                "cost_usd": self.cost_tracker._calculate_cost(payload.get('model'), usage.get('prompt_tokens',0), usage.get('completion_tokens',0)) if self.cost_tracker else None
            }
            # Persist probe
            session.setdefault('probes', []).append({
                'phase': phase,
                'question': content,
                'timestamp': _now_iso()
            })
            self._save_session(session_id, session)
            return {"question": content, "cost_info": cost_info}
        except Exception as e:
            return {"error": f"LLM call failed: {e}"}

    def propose_prompt_workflow(self, args: Dict[str, Any]) -> Dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return {"error": "LLM unavailable: provide OPENAI_API_KEY"}
        title = args.get('assignment_title') or 'Assignment'
        instructions = args.get('assignment_instructions') or ''
        outcomes = args.get('outcomes') or []
        rubric = args.get('rubric') or []
        constraints = args.get('constraints') or {}
        phases = constraints.get('phases') or 6
        system_prompt = (
            "You are assisting a learning designer. Propose a phased reflection workflow. "
            "If rubric is empty, infer a concise rubric (3-6 items) and include it as inferred_rubric. "
            "Return ONLY valid JSON. Double-check that all strings are properly quoted and escaped. "
            "Format: {\"phases\":[{\"id\":1,\"type\":\"divergent\",\"prompt\":\"text\",\"rationale\":\"text\",\"maps_to_outcomes\":[],\"maps_to_rubric\":[]}], \"generated_at\":\"ISO_DATE\", \"model\":\"gpt-4o-mini\"}. "
            "Use concise, student-facing prompts. Types must be one of: divergent, convergent, scaffolded, self_assessment. "
            "Ensure all JSON strings are properly escaped and terminated."
        )
        user_payload = {
            "assignment_title": title,
            "outcomes": outcomes,
            "rubric": rubric,
            "constraints": constraints,
            "phases": phases
        }
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload | {"assignment_instructions": instructions})}
            ],
            "max_tokens": 500
        }
        try:
            start = time.time()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latency_ms = int((time.time() - start) * 1000)
            if self.cost_tracker and not self.cost_tracker.current_session:
                self.cost_tracker.start_session(f"design_{int(time.time())}")
            if self.cost_tracker and self.cost_tracker.current_session:
                self.cost_tracker.log_api_call(
                    payload,
                    data,
                    latency_ms,
                    metadata={"stage": "design", "tool_name": "propose_prompt_workflow"}
                )
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            content = self._strip_code_fence(content)
            if not content.strip():
                return {"error": "Empty response from LLM"}
            try:
                result = json.loads(content)
            except json.JSONDecodeError as je:
                return {"error": f"LLM returned invalid JSON: {je}. Content: {content[:200]}..."}
            # Attach cost snippet for UI
            usage = data.get('usage', {})
            cost_info = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "latency_ms": latency_ms,
                "cost_usd": self.cost_tracker._calculate_cost(payload.get('model'), usage.get('prompt_tokens',0), usage.get('completion_tokens',0)) if self.cost_tracker else None
            }
            result["cost_info"] = cost_info
            if "model" not in result:
                result["model"] = payload["model"]
            return result
        except Exception as e:
            return {"error": f"Design generation failed: {e}"}

    def check_rubric_alignment(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Check alignment with assignment rubric"""
        responses = session["responses"]
        assignment_type = session["assignment_type"]

        alignment = {
            "criteria_met": {},
            "overall_alignment": "good"
        }

        if assignment_type == "search_comparison":
            # Check for documented process
            has_process_doc = any("google" in resp_data.get("response", "").lower() and
                                "database" in resp_data.get("response", "").lower()
                                for resp_data in responses.values())
            alignment["criteria_met"]["documented_process"] = has_process_doc

            # Check for specific examples
            has_examples = any(len(resp_data.get("response", "")) > 150
                             for resp_data in responses.values())
            alignment["criteria_met"]["specific_examples"] = has_examples

            # Check for balanced analysis
            has_balance = "quality_patterns" in responses and "relevance_assessment" in responses
            alignment["criteria_met"]["balanced_analysis"] = has_balance

            # Check for future application
            has_future = "application_planning" in responses
            alignment["criteria_met"]["future_application"] = has_future

        return alignment

    def assess_submission_readiness(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Assess if student is ready to submit"""
        responses = session["responses"]
        prompts = session["prompts"]

        readiness = {
            "overall": "ready",
            "suggestions": []
        }

        # Check completion
        if len(responses) < len(prompts):
            readiness["overall"] = "incomplete"
            missing_phases = [p["phase"] for i, p in enumerate(prompts) if str(i) not in responses]
            readiness["suggestions"].append(f"Complete remaining reflection prompts: {', '.join(missing_phases)}")

        # Check for substantive responses
        short_responses = []
        for phase, resp_data in responses.items():
            if len(resp_data.get("response", "")) < 75:  # Minimum threshold
                phase_name = next((p["phase"] for p in prompts if p["phase"] == phase), phase)
                short_responses.append(phase_name)

        if short_responses:
            readiness["suggestions"].append(f"Expand these responses with more detail: {', '.join(short_responses)}")

        # Success message if ready
        if readiness["overall"] == "ready" and not readiness["suggestions"]:
            readiness["suggestions"].append("Your reflection demonstrates thoughtful engagement with the assignment. You're ready to submit!")

        return readiness

    def handle_call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name == "start_reflection":
                result = self.start_reflection(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "submit_reflection_response":
                result = self.submit_reflection_response(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "get_reflection_summary":
                result = self.get_reflection_summary(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "get_current_prompt":
                result = self.get_current_prompt(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "provider_status":
                result = self.provider_status(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "get_costs":
                result = self.get_costs(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "get_session_context":
                result = self.get_session_context(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "get_probing_question":
                result = self.get_probing_question(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            elif name == "propose_prompt_workflow":
                result = self.propose_prompt_workflow(args)
                return mcp_result_text(json.dumps(result, ensure_ascii=False))
            else:
                return mcp_result_text(json.dumps({"error": f"Unknown tool: {name}"}))
        except Exception as e:
            return mcp_result_text(json.dumps({"error": str(e)}))

def main():
    server = ReflectionServer()

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        try:
            req = json.loads(line)
            method = req.get('method')
            _id = req.get('id')

            if method == 'initialize':
                resp = {
                    "jsonrpc": "2.0",
                    "id": _id,
                    "result": {
                        "serverInfo": {
                            "name": "reflection-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
            elif method == 'tools/list':
                resp = {"jsonrpc": "2.0", "id": _id, "result": list_tools()}
            elif method == 'tools/call':
                params = req.get('params') or {}
                name = params.get('name')
                args = params.get('arguments') or {}
                try:
                    result = server.handle_call(name, args)
                    resp = {"jsonrpc": "2.0", "id": _id, "result": result}
                except Exception as e:
                    resp = {"jsonrpc": "2.0", "id": _id, "error": {"code": -32603, "message": f"Internal error: {e}"}}
            else:
                resp = {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": "Method not found"}}

        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

if __name__ == '__main__':
    main()
