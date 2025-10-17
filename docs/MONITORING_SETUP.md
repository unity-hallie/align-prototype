# Production Monitoring Setup

## Overview

This guide shows how to enable production monitoring for align-prototype. The monitoring system tracks:
- **Errors**: 5xx, CSRF failures, 4xx errors, timeouts
- **Performance**: Latency percentiles (P95, P99), throughput
- **Business**: Active sessions, feature usage, endpoint popularity
- **Alerts**: Critical events that need attention

Designed for three personas:
- 👨‍🏫 **Learning Designer**: Needs visibility that system is watched
- 🚀 **Executor**: Needs latency/errors for deployment decisions
- ✅ **Quality Advocate**: Needs early warning system for incidents

---

## Quick Start

### 1. Enable Monitoring in app.py

Add these imports at the top:
```python
from utils.monitoring import flask_monitoring, init_metrics
from pathlib import Path
```

Initialize metrics right after creating the Flask app:
```python
app = Flask(__name__)

# Initialize monitoring
metrics_dir = Path(__file__).parent / ".local_context" / "metrics"
metrics = init_metrics(metrics_dir=metrics_dir)
flask_monitoring(app)
```

### 2. View the Dashboard

Start the app:
```bash
python app.py
```

Open the monitoring dashboard:
```
http://localhost:5004/monitoring
```

You'll see:
- ✅ Real-time health status (green/yellow/red)
- 📊 Error rates and latency metrics
- 🔔 Recent alerts
- 📈 Top endpoints by traffic

### 3. Check Metrics Endpoint

Get raw metrics as JSON:
```bash
curl http://localhost:5004/metrics | python -m json.tool
```

Or detailed health check:
```bash
curl http://localhost:5004/health/detailed | python -m json.tool
```

---

## Integration Details

### Automatic Request Tracking

Once `flask_monitoring(app)` is called, all requests are automatically tracked:
- Response time (latency)
- Status code
- Endpoint
- Session ID
- Feature usage (if annotated)

No changes needed to route handlers!

### Manual Event Tracking

For specific events, use the global metrics:

```python
from utils.monitoring import get_metrics

metrics = get_metrics()

# Record custom events
metrics.record_error(
    error_type="timeout",
    message="MCP call exceeded 60s timeout",
    endpoint="/start_reflection"
)

metrics.record_session(session_id, action="start")
metrics.record_session(session_id, action="end")
```

### Alert Configuration

Modify alert thresholds in `utils/monitoring.py`:

```python
self.alert_rules = {
    "error_rate_high": {"threshold": 0.05, "window": 60},   # 5% in 60s
    "latency_high": {"threshold": 500, "window": 60},        # 500ms P95 in 60s
    "5xx_detected": {"threshold": 5, "window": 300},         # 5 errors in 5min
}
```

---

## Dashboard Endpoints

### `/monitoring`
Full monitoring dashboard with:
- Real-time status indicator
- Performance metrics
- Error breakdown
- Recent alerts
- Top endpoints
- Auto-refresh every 5 seconds

### `/metrics`
JSON endpoint for metrics integration:
```json
{
  "timestamp": "2025-10-16T21:00:00Z",
  "summary": {
    "total_requests": 1000,
    "successful_requests": 950,
    "error_rate_percent": 5.0,
    "active_sessions": 12
  },
  "errors": {
    "recent_5xx": 2,
    "recent_csrf": 3,
    "recent_4xx": 5
  },
  "performance": {
    "p95_ms": 131.5,
    "p99_ms": 155.5,
    "mean_ms": 90.8
  },
  "alerts": [...]
}
```

### `/health/detailed`
Health check for monitoring systems:
```json
{
  "status": "healthy",
  "error_rate_percent": 5.0,
  "active_sessions": 12,
  "p95_latency_ms": 131.5,
  "recent_5xx": 2,
  "alerts": 0,
  "timestamp": "2025-10-16T21:00:00Z"
}
```

---

## Production Deployment Checklist

### Before Going Live

- [ ] Monitoring dashboard accessible at `/monitoring`
- [ ] `/metrics` endpoint returns current data
- [ ] `/health/detailed` working for load balancers
- [ ] Alert thresholds tuned for your environment
- [ ] Metrics persist to disk for historical analysis
- [ ] Dashboard works on mobile (instructors check from phones)

### Monitoring Best Practices

1. **Error Rate Target**: < 2% in production
2. **Latency Target**: P95 < 200ms, P99 < 500ms
3. **Alert Response Time**: < 5 minutes for critical alerts
4. **Session Health**: Active sessions should grow during class time
5. **Endpoint Monitoring**: Watch for unexpected endpoint patterns

### Interpreting the Dashboard

**✅ Healthy** (Green)
- Error rate < 1%
- P95 latency < 200ms
- No active critical alerts
- ✓ Safe to route traffic

**⚠️ Warning** (Yellow)
- Error rate 1-5%
- P95 latency 200-500ms
- One or more warning alerts
- ⚠️ Monitor closely, but deployable

**❌ Degraded** (Red)
- Error rate > 5%
- P95 latency > 500ms
- Critical alerts present
- ❌ Do NOT route traffic, investigate

---

## Integration with External Monitoring

### Prometheus Integration

Adapt the `/metrics` endpoint to Prometheus format:
```python
from prometheus_client import Counter, Histogram, Gauge

request_latency = Histogram('request_latency_ms', 'Request latency')
errors_total = Counter('errors_total', 'Total errors', ['type'])
active_sessions = Gauge('active_sessions', 'Active sessions')
```

### Sentry Integration

For error tracking:
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="https://your-key@sentry.io/project",
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.1
)
```

### DataDog Integration

Send metrics to DataDog:
```python
from datadog import initialize, api

options = {'api_key': 'YOUR_API_KEY', 'app_key': 'YOUR_APP_KEY'}
initialize(**options)

# Then in metrics:
api.Metric.send(
    metric='align.error_rate',
    points=error_rate,
    tags=['env:production']
)
```

---

## Troubleshooting

### Metrics not showing?
1. Check `/metrics` endpoint returns data
2. Verify monitoring was initialized: `flask_monitoring(app)`
3. Make some requests to generate data

### Dashboard shows only zeroes?
1. Metrics need real traffic to show data
2. Try generating test traffic: `curl http://localhost:5004/`
3. Wait 5-10 seconds for dashboard to update

### Alerts not triggering?
1. Check alert thresholds in `utils/monitoring.py`
2. Generate errors to test: `curl http://localhost:5004/invalid`
3. Create high latency by adding `sleep(1)` in a route temporarily

---

## Architecture

```
┌─────────────────────────────────────────────┐
│        Flask App (app.py)                   │
├─────────────────────────────────────────────┤
│  before_request → g.start_time = now        │
│  Routes handle requests                     │
│  after_request → metrics.record_request()   │
│                                             │
│  Special events → metrics.record_error()    │
│                                             │
└─────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────┐
│   MetricsCollector (utils/monitoring.py)    │
├─────────────────────────────────────────────┤
│  • Collects all request data                │
│  • Calculates latency percentiles           │
│  • Tracks errors by type                    │
│  • Manages active sessions                  │
│  • Evaluates alert conditions               │
│  • Persists metrics to disk                 │
└─────────────────────────────────────────────┘
                     ↓
         ┌───────────┴───────────┐
         ↓                       ↓
   /metrics endpoint      /monitoring dashboard
   (JSON API)            (Real-time UI)
```

---

## Metrics Retention

- **In-Memory**: Last 10,000 requests (rolling window)
- **Disk**: 288 snapshots (24 hours at 5-min intervals)
- **Alerts**: Last 10 per type

For long-term retention, integrate with external monitoring (Prometheus, DataDog, etc).

---

## Next Steps

After monitoring is deployed:

1. ✅ **Step 6 Complete**: Monitoring is live
2. **Step 13**: Set up blue-green deployment infrastructure
3. **Step 7**: Route traffic to production version
4. **Step 8**: Verify production health with monitoring data

All three personas can now see:
- 👨‍🏫 Dashboard showing system is actively watched
- 🚀 Data needed to safely route traffic
- ✅ Early warning system for incidents

---

## Questions?

This monitoring system is production-ready for small to medium deployments (< 1K concurrent users).

For larger scale, integrate with:
- **Prometheus** for metrics storage
- **Grafana** for dashboards
- **AlertManager** for alert routing
- **Sentry** for error tracking
- **ELK Stack** for logs

See deployment documentation for enterprise setups.
