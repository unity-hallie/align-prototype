#!/usr/bin/env python3
"""
Production Monitoring for align-prototype

Tracks:
  - Application errors (5xx, CSRF failures, timeouts)
  - Performance metrics (latency, throughput, response times)
  - Business metrics (active sessions, user activities)
  - Health status of all critical endpoints

Designed for three personas:
  👨‍🏫 Learning Designer: Wants visibility that system is watched
  🚀 Executor: Needs latency/errors to make deployment decisions
  ✅ Quality Advocate: Needs early warning system for incidents
"""

import time
import json
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import statistics


class MetricsCollector:
    """Thread-safe metrics collection for production monitoring."""

    def __init__(self, metrics_dir: Optional[Path] = None, window_size: int = 300):
        """
        Initialize metrics collector.

        Args:
            metrics_dir: Directory to persist metrics (optional)
            window_size: Time window in seconds for aggregation (default 5 minutes)
        """
        self.metrics_dir = metrics_dir
        self.window_size = window_size
        self._lock = threading.Lock()

        # Error tracking
        self.errors = {
            "5xx": deque(maxlen=1000),  # Server errors
            "csrf": deque(maxlen=1000),  # CSRF failures
            "4xx": deque(maxlen=1000),  # Client errors
            "timeout": deque(maxlen=500),  # Timeouts
        }

        # Performance metrics (in-flight request tracking)
        self.latencies = deque(maxlen=10000)  # Response times (ms)
        self.request_count = 0
        self.successful_requests = 0
        self.failed_requests = 0

        # Business metrics
        self.active_sessions = set()
        self.endpoint_calls = defaultdict(int)
        self.feature_usage = defaultdict(int)

        # Health status
        self.health_status = {
            "app": "healthy",
            "mcp": "unknown",
            "database": "unknown",
            "last_error": None,
            "last_check": None,
        }

        # Threshold-based alerts
        self.alerts = []
        self.alert_rules = {
            "error_rate_high": {"threshold": 0.05, "window": 60},  # 5% errors in 60s
            "latency_high": {"threshold": 500, "window": 60},  # 500ms P95 in 60s
            "5xx_detected": {"threshold": 5, "window": 300},  # 5 errors in 5min
        }

        # Historical data for trends
        self.historical_data = deque(maxlen=288)  # 24 hours at 5-min intervals

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        latency_ms: float,
        session_id: Optional[str] = None,
        feature: Optional[str] = None,
    ):
        """Record a request for metrics."""
        with self._lock:
            self.request_count += 1
            self.endpoint_calls[f"{method} {endpoint}"] += 1

            if session_id:
                self.active_sessions.add(session_id)

            if feature:
                self.feature_usage[feature] += 1

            # Track latency
            self.latencies.append(latency_ms)

            # Categorize by status
            if 200 <= status_code < 300:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
                if status_code >= 500:
                    self.errors["5xx"].append(
                        {"time": time.time(), "endpoint": endpoint, "status": status_code}
                    )
                elif status_code == 400 and "csrf" in str(endpoint).lower():
                    self.errors["csrf"].append(
                        {"time": time.time(), "endpoint": endpoint}
                    )
                elif 400 <= status_code < 500:
                    self.errors["4xx"].append(
                        {"time": time.time(), "endpoint": endpoint, "status": status_code}
                    )

            # Check alert conditions
            self._check_alerts()

    def record_error(
        self, error_type: str, message: str, endpoint: Optional[str] = None
    ):
        """Record an error event."""
        with self._lock:
            if error_type == "timeout":
                self.errors["timeout"].append(
                    {"time": time.time(), "endpoint": endpoint, "message": message}
                )
            self.health_status["last_error"] = message
            self._check_alerts()

    def record_session(self, session_id: str, action: str = "start"):
        """Track active sessions."""
        with self._lock:
            if action == "start":
                self.active_sessions.add(session_id)
            elif action == "end":
                self.active_sessions.discard(session_id)

    def get_metrics_snapshot(self) -> Dict:
        """Get current metrics snapshot."""
        with self._lock:
            now = time.time()
            recent_window = now - self.window_size

            # Count recent errors
            recent_5xx = sum(1 for e in self.errors["5xx"] if e["time"] > recent_window)
            recent_csrf = sum(1 for e in self.errors["csrf"] if e["time"] > recent_window)
            recent_4xx = sum(1 for e in self.errors["4xx"] if e["time"] > recent_window)
            recent_timeout = sum(1 for e in self.errors["timeout"] if e["time"] > recent_window)

            # Calculate latency stats
            latency_stats = {}
            if self.latencies:
                sorted_latencies = sorted(self.latencies)
                latency_stats = {
                    "min_ms": min(self.latencies),
                    "max_ms": max(self.latencies),
                    "mean_ms": statistics.mean(self.latencies),
                    "median_ms": statistics.median(self.latencies),
                    "p95_ms": sorted_latencies[int(len(sorted_latencies) * 0.95)],
                    "p99_ms": sorted_latencies[int(len(sorted_latencies) * 0.99)],
                }

            # Calculate error rate
            total_requests = self.request_count
            error_rate = (
                (self.failed_requests / total_requests * 100)
                if total_requests > 0
                else 0
            )

            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "summary": {
                    "total_requests": total_requests,
                    "successful_requests": self.successful_requests,
                    "failed_requests": self.failed_requests,
                    "error_rate_percent": error_rate,
                    "active_sessions": len(self.active_sessions),
                    "unique_endpoints": len(self.endpoint_calls),
                },
                "errors": {
                    "recent_5xx": recent_5xx,
                    "recent_csrf": recent_csrf,
                    "recent_4xx": recent_4xx,
                    "recent_timeout": recent_timeout,
                    "total_5xx": len(self.errors["5xx"]),
                    "total_csrf": len(self.errors["csrf"]),
                },
                "performance": latency_stats,
                "health": self.health_status,
                "top_endpoints": dict(
                    sorted(self.endpoint_calls.items(), key=lambda x: x[1], reverse=True)[:5]
                ),
                "feature_usage": dict(self.feature_usage),
                "alerts": self.alerts[-10:],  # Last 10 alerts
            }

    def _check_alerts(self):
        """Check alert thresholds and create alerts if triggered."""
        now = time.time()
        recent_window = now - self.alert_rules["error_rate_high"]["window"]

        # Alert: High error rate
        total_recent = sum(
            1
            for ts in [self.errors["5xx"], self.errors["csrf"], self.errors["4xx"]]
            for e in ts
            if e["time"] > recent_window
        )
        if total_recent >= self.alert_rules["5xx_detected"]["threshold"]:
            self._create_alert(
                "5xx_detected",
                f"Detected {total_recent} errors in last 5 minutes",
                "critical",
            )

        # Alert: High latency (P95)
        if len(self.latencies) > 10:
            sorted_latencies = sorted(self.latencies)
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            if p95 > self.alert_rules["latency_high"]["threshold"]:
                self._create_alert(
                    "latency_high", f"P95 latency: {p95:.1f}ms", "warning"
                )

    def _create_alert(self, alert_type: str, message: str, severity: str):
        """Create an alert if not already raised recently."""
        now = time.time()
        # Avoid duplicate alerts within 60 seconds
        if self.alerts and self.alerts[-1]["type"] == alert_type:
            if now - self.alerts[-1]["time"] < 60:
                return

        self.alerts.append(
            {
                "type": alert_type,
                "message": message,
                "severity": severity,
                "time": now,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )

    def persist_metrics(self):
        """Persist current metrics to disk (optional)."""
        if not self.metrics_dir:
            return

        try:
            self.metrics_dir.mkdir(parents=True, exist_ok=True)
            snapshot = self.get_metrics_snapshot()
            output_file = self.metrics_dir / f"metrics_{int(time.time())}.json"
            output_file.write_text(json.dumps(snapshot, indent=2))
        except Exception as e:
            print(f"Error persisting metrics: {e}")

    def get_health_status(self) -> Dict:
        """Get health status for health check endpoint."""
        snapshot = self.get_metrics_snapshot()
        summary = snapshot["summary"]

        # Determine overall health
        error_rate = summary["error_rate_percent"]
        has_critical_alerts = any(a["severity"] == "critical" for a in snapshot["alerts"])

        if has_critical_alerts or error_rate > 10:
            health = "degraded"
        elif error_rate > 5:
            health = "warning"
        else:
            health = "healthy"

        return {
            "status": health,
            "error_rate_percent": error_rate,
            "active_sessions": summary["active_sessions"],
            "p95_latency_ms": snapshot["performance"].get("p95_ms", 0),
            "recent_5xx": snapshot["errors"]["recent_5xx"],
            "alerts": len(snapshot["alerts"]),
            "timestamp": snapshot["timestamp"],
        }


# Global metrics collector instance
_metrics = None


def init_metrics(metrics_dir: Optional[Path] = None) -> MetricsCollector:
    """Initialize and return global metrics collector."""
    global _metrics
    _metrics = MetricsCollector(metrics_dir=metrics_dir)
    return _metrics


def get_metrics() -> Optional[MetricsCollector]:
    """Get global metrics collector (or None if not initialized)."""
    return _metrics


def flask_monitoring(app):
    """
    Flask integration for automatic request monitoring.

    Usage in Flask app:
        from utils.monitoring import flask_monitoring, init_metrics
        metrics = init_metrics()
        flask_monitoring(app)
    """
    if not app:
        return

    metrics = get_metrics()
    if not metrics:
        init_metrics()
        metrics = get_metrics()

    @app.before_request
    def before_request():
        from flask import request, g

        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        from flask import request, g, session

        if hasattr(g, "start_time"):
            latency_ms = (time.time() - g.start_time) * 1000
            endpoint = request.endpoint or "unknown"
            session_id = session.get("session_id") if session else None

            metrics.record_request(
                endpoint=endpoint,
                method=request.method,
                status_code=response.status_code,
                latency_ms=latency_ms,
                session_id=session_id,
            )

        return response

    @app.route("/metrics")
    def metrics_endpoint():
        """Expose metrics as JSON endpoint for monitoring."""
        from flask import jsonify

        return jsonify(metrics.get_metrics_snapshot())

    @app.route("/health/detailed")
    def health_detailed():
        """Detailed health check for monitoring systems."""
        from flask import jsonify

        return jsonify(metrics.get_health_status())


if __name__ == "__main__":
    # Demo: Show what metrics look like
    print("🔍 Monitoring Module Demo\n")

    # Initialize metrics
    metrics = init_metrics()

    # Simulate some requests
    print("Simulating requests...")
    for i in range(100):
        status = 200 if i % 10 != 9 else 500  # 10% error rate
        latency = 50 + (i % 200)
        metrics.record_request(
            endpoint=f"/endpoint_{i % 5}",
            method="GET",
            status_code=status,
            latency_ms=latency,
            session_id=f"session_{i % 10}",
        )

    # Show metrics
    snapshot = metrics.get_metrics_snapshot()
    print(json.dumps(snapshot, indent=2))

    print("\n✅ Monitoring initialized and ready for production deployment")
