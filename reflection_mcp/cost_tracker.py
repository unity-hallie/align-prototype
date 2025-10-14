#!/usr/bin/env python3
"""
Real-time cost tracking for reflection MCP
Tracks actual API usage and costs during execution
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import math

class CostTracker:
    """Track actual API costs during reflection sessions"""

    def __init__(self):
        self.log_dir = Path(__file__).parent.parent / ".local_context" / "cost_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_session = None

    def start_session(self, session_id: str, model: str = "gpt-4o-mini"):
        """Start tracking costs for a session"""
        self.current_session = {
            "session_id": session_id,
            "model": model,
            "started_at": datetime.utcnow().isoformat(),
            "api_calls": []
        }

    def log_api_call(self, request_data: dict, response_data: dict, latency_ms: int, metadata: Optional[Dict] = None):
        """Log an actual API call with token usage from response"""
        if not self.current_session:
            return

        # OpenAI returns usage in the response
        usage = response_data.get("usage", {})

        api_call = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": request_data.get("model"),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "latency_ms": latency_ms,
            # Store actual content for verification
            "messages_char_count": sum(len(msg.get("content", ""))
                                      for msg in request_data.get("messages", [])),
            "response_char_count": len(response_data.get("choices", [{}])[0]
                                     .get("message", {}).get("content", ""))
        }
        if metadata and isinstance(metadata, dict):
            # Include high-level context for decision-makers
            # e.g., stage: design|runtime_probe|runtime_summary, tool_name, phase, used_draft
            api_call["meta"] = metadata

        # Calculate cost based on actual model used
        api_call["cost_usd"] = self._calculate_cost(
            api_call["model"],
            api_call["prompt_tokens"],
            api_call["completion_tokens"]
        )

        self.current_session["api_calls"].append(api_call)

        # Persist incrementally so multi-process tool calls accumulate
        try:
            sid = self.current_session.get("session_id")
            log_file = self.log_dir / f"{sid}_costs.json"
            if log_file.exists():
                try:
                    existing = json.loads(log_file.read_text())
                except Exception:
                    existing = {}
            else:
                existing = {}
            # Merge
            merged = {
                "session_id": sid,
                "model": self.current_session.get("model"),
                "started_at": existing.get("started_at") or self.current_session.get("started_at"),
                "api_calls": (existing.get("api_calls") or []) + [api_call]
            }
            log_file.write_text(json.dumps(merged, indent=2))
        except Exception:
            pass

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost based on current OpenAI pricing"""
        # These should be fetched from OpenAI or config, not hardcoded
        # But for now using current published prices (Sept 2024)
        pricing = {
            "gpt-4o-mini": {
                "input": 0.150 / 1_000_000,  # per token
                "output": 0.600 / 1_000_000   # per token
            },
            "gpt-4o": {
                "input": 2.50 / 1_000_000,
                "output": 10.00 / 1_000_000
            },
            "gpt-3.5-turbo": {
                "input": 0.50 / 1_000_000,
                "output": 1.50 / 1_000_000
            }
        }

        model_pricing = pricing.get(model, pricing["gpt-4o-mini"])

        input_cost = prompt_tokens * model_pricing["input"]
        output_cost = completion_tokens * model_pricing["output"]

        return round(input_cost + output_cost, 8)

    def end_session(self):
        """End session and save cost log"""
        if not self.current_session:
            return None

        self.current_session["ended_at"] = datetime.utcnow().isoformat()

        # Merge with any existing incremental log before computing totals
        sid = self.current_session.get("session_id")
        log_path = self.log_dir / f"{sid}_costs.json"
        combined_calls = []
        if log_path.exists():
            try:
                existing = json.loads(log_path.read_text())
                combined_calls.extend(existing.get("api_calls") or [])
            except Exception:
                pass
        # Avoid double-counting calls already persisted incrementally
        existing_keys = set()
        for c in combined_calls:
            k = (c.get("timestamp"), c.get("model"), c.get("total_tokens"))
            existing_keys.add(k)
        for c in self.current_session.get("api_calls", []):
            k = (c.get("timestamp"), c.get("model"), c.get("total_tokens"))
            if k not in existing_keys:
                combined_calls.append(c)

        # Calculate totals on combined
        total_cost = sum(call.get("cost_usd", 0) for call in combined_calls)
        total_prompt_tokens = sum(call.get("prompt_tokens", 0) for call in combined_calls)
        total_completion_tokens = sum(call.get("completion_tokens", 0) for call in combined_calls)

        self.current_session["totals"] = {
            "api_calls_count": len(combined_calls),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "total_cost_usd": round(total_cost, 8),
            "average_latency_ms": (
                sum(call.get("latency_ms", 0) for call in combined_calls) // len(combined_calls)
            ) if combined_calls else 0
        }

        # Save final file (JSON)
        final_payload = self.current_session.copy()
        final_payload["api_calls"] = combined_calls
        log_path.write_text(json.dumps(final_payload, indent=2))

        # Also write a concise human-readable markdown log alongside JSON
        try:
            md = []
            md.append(f"# Cost Log — {self.current_session['session_id']}")
            md.append("")
            md.append(f"Started: {self.current_session.get('started_at','')}  ")
            md.append(f"Ended:   {self.current_session.get('ended_at','')}")
            md.append("")
            t = self.current_session.get('totals', {})
            md.append("## Totals")
            md.append(f"- API calls: {t.get('api_calls_count',0)}")
            md.append(f"- Tokens: {t.get('total_tokens',0)} (prompt {t.get('total_prompt_tokens',0)}, completion {t.get('total_completion_tokens',0)})")
            md.append(f"- Cost: ${t.get('total_cost_usd',0):.6f}")
            md.append(f"- Avg latency: {t.get('average_latency_ms',0)} ms")
            md.append("")
            calls = self.current_session.get('api_calls', [])
            if calls:
                md.append("## Recent Calls")
                for c in calls[-5:]:
                    meta = c.get('meta') or {}
                    stage = meta.get('stage') or meta.get('tool_name') or '-'
                    md.append(f"- {c.get('timestamp','')} — model {c.get('model')} — {c.get('total_tokens',0)} tok — ${c.get('cost_usd',0):.6f} — stage: {stage}")
                md.append("")
            (self.log_dir / f"{self.current_session['session_id']}_costs.md").write_text("\n".join(md) + "\n")
        except Exception:
            # Best-effort: do not fail session teardown on log write
            pass

        result = self.current_session["totals"].copy()
        self.current_session = None

        return result

    def get_aggregated_stats(self, last_n_sessions: int = 100) -> dict:
        """Get aggregated cost statistics across sessions"""
        log_files = sorted(self.log_dir.glob("*_costs.json"),
                          key=lambda x: x.stat().st_mtime,
                          reverse=True)[:last_n_sessions]

        if not log_files:
            return {"error": "No cost logs found"}

        all_costs = []
        all_tokens = []
        all_latencies = []
        zero_sessions = 0
        nonzero_costs = []
        nonzero_tokens = []
        nonzero_latencies = []

        for log_file in log_files:
            data = json.loads(log_file.read_text())
            totals = data.get("totals", {})
            c = float(totals.get("total_cost_usd", 0) or 0)
            t = int(totals.get("total_tokens", 0) or 0)
            l = int(totals.get("average_latency_ms", 0) or 0)
            all_costs.append(c)
            all_tokens.append(t)
            all_latencies.append(l)
            if c <= 0 or t <= 0:
                zero_sessions += 1
            else:
                nonzero_costs.append(c)
                nonzero_tokens.append(t)
                nonzero_latencies.append(l)

        def _stats(vals: list) -> Dict[str, float]:
            n = len(vals)
            if n == 0:
                return {"min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "total": 0}
            s = sorted(vals)
            median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
            p95_idx = max(0, min(n - 1, int(math.ceil(0.95 * n) - 1)))
            return {
                "min": s[0],
                "max": s[-1],
                "mean": sum(vals) / n,
                "median": median,
                "p95": s[p95_idx],
                "total": sum(vals),
            }

        out = {
            "sessions_analyzed": len(log_files),
            "zero_sessions": zero_sessions,
            "cost_stats": _stats(all_costs),
            "token_stats": {
                "min": min(all_tokens) if all_tokens else 0,
                "max": max(all_tokens) if all_tokens else 0,
                "mean": (sum(all_tokens) / len(all_tokens)) if all_tokens else 0,
                "total": sum(all_tokens) if all_tokens else 0,
            },
            "latency_stats": {
                "min_ms": min(all_latencies) if all_latencies else 0,
                "max_ms": max(all_latencies) if all_latencies else 0,
                "mean_ms": (sum(all_latencies) / len(all_latencies)) if all_latencies else 0,
            },
            "cost_per_1000_students": ((sum(all_costs) / len(all_costs)) * 1000) if all_costs else 0,
            "raw_data_files": [str(f) for f in log_files[:10]],  # First 10 for reference
        }

        # Also include stats for non-zero sessions to avoid misleading averages
        if nonzero_costs:
            out["nonzero"] = {
                "sessions_analyzed": len(nonzero_costs),
                "cost_stats": _stats(nonzero_costs),
                "token_stats": {
                    "min": min(nonzero_tokens),
                    "max": max(nonzero_tokens),
                    "mean": sum(nonzero_tokens) / len(nonzero_tokens),
                    "total": sum(nonzero_tokens),
                },
                "latency_stats": {
                    "min_ms": min(nonzero_latencies),
                    "max_ms": max(nonzero_latencies),
                    "mean_ms": sum(nonzero_latencies) / len(nonzero_latencies),
                },
                "cost_per_1000_students": (sum(nonzero_costs) / len(nonzero_costs)) * 1000,
            }

        return out
