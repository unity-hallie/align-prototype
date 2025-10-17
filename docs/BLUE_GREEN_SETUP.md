# Blue-Green Deployment Setup

## Overview

Blue-green deployment enables **zero-downtime deployments** by running two versions of the application simultaneously and switching traffic between them atomically.

**Key Benefits:**
- ✅ Zero-downtime deployments
- ✅ Instant rollback capability
- ✅ Full confidence testing before traffic switch
- ✅ Production-safe deployment pipeline

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Users/Load Balancer                                     │
│ Requests → http://app:5004 (proxy/router)               │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ├──────────────────┐
                   ↓                  ↓
        ┌──────────────────┐  ┌──────────────────┐
        │ BLUE VERSION     │  │ GREEN VERSION    │
        │ Port 5005        │  │ Port 5006        │
        │                  │  │                  │
        │ Active = NO      │  │ Active = YES     │
        │ PID = 12345      │  │ PID = 12346      │
        │ Healthy = ✅     │  │ Healthy = ✅     │
        │                  │  │                  │
        │ (For rollback)   │  │ (Receiving %)    │
        └──────────────────┘  └──────────────────┘

        State stored in: .local_context/bg_state.json
```

---

## Quick Start

### 1. Initial Setup

Blue-green deployment is already integrated. Just verify:

```bash
# Check deployment status
./bin/blue_green_deploy status
```

Expected output:
```
🎯 Active Version: BLUE (port 5005)

📊 Blue Instance:
   Port: 5005
   Status: stopped
   Healthy: ❌

📊 Green Instance:
   Port: 5006
   Status: stopped
   Healthy: ❌
```

### 2. Start Initial Version

```bash
# Start blue version (active)
./bin/blue_green_deploy start blue
```

This will:
- Start Flask on port 5005
- Run health checks until ready
- Update state file

### 3. Deploy New Version

When you have code changes to deploy:

```bash
# Deploy new version to green slot
./bin/blue_green_deploy deploy
```

This will:
- Start green version on port 5006
- Wait for health checks to pass
- Switch traffic to green
- Keep blue running for rollback

### 4. Verify Deployment

```bash
# Check status
./bin/blue_green_deploy status
```

### 5. Rollback (If Needed)

```bash
# Instant rollback to previous version
./bin/blue_green_deploy rollback
```

---

## CLI Commands

### Status

Show current deployment state:

```bash
./bin/blue_green_deploy status
```

Output includes:
- Active version and port
- Health status of both instances
- Recent deployment history
- PIDs and ports

### Deploy

Deploy new version (recommended):

```bash
./bin/blue_green_deploy deploy
```

Process:
1. Start inactive version (green if blue active)
2. Health check until ready
3. Switch traffic to new version
4. Keep old version running

### Switch

Switch traffic to a specific version:

```bash
./bin/blue_green_deploy switch <blue|green>
```

Example:
```bash
./bin/blue_green_deploy switch blue  # Switch to blue
./bin/blue_green_deploy switch green # Switch to green
```

### Rollback

Instantly rollback to the previous version:

```bash
./bin/blue_green_deploy rollback
```

### Start

Start a specific version:

```bash
./bin/blue_green_deploy start blue
./bin/blue_green_deploy start green
```

### Stop

Stop a specific version:

```bash
./bin/blue_green_deploy stop blue
./bin/blue_green_deploy stop green
```

### Health Check

Check health of both versions:

```bash
./bin/blue_green_deploy health-check
```

---

## Programmatic Usage

### Python Integration

Use blue-green deployment from Python code:

```python
from pathlib import Path
from utils.blue_green import BlueGreenManager

# Initialize manager
manager = BlueGreenManager(
    app_script="app.py",
    blue_port=5005,
    green_port=5006
)

# Deploy new version
if manager.deploy_new_version():
    print("✅ Deployment successful")
    status = manager.get_status()
    print(f"Active: {status['active_version']}")
else:
    print("❌ Deployment failed")

# Check status anytime
status = manager.get_status()
print(status)

# Manual traffic switch
manager.switch_traffic("green")

# Rollback
manager.rollback()

# Health checks
blue_healthy = manager._health_check(5005)
green_healthy = manager._health_check(5006)
```

---

## Production Deployment Workflow

### Before Deployment

1. **Code changes ready**
   ```bash
   git add .
   git commit -m "feature: add new functionality"
   ```

2. **Check current status**
   ```bash
   ./bin/blue_green_deploy status
   ```

3. **Verify tests pass**
   ```bash
   pytest tests/
   ```

### During Deployment

4. **Deploy to inactive slot**
   ```bash
   ./bin/blue_green_deploy deploy
   ```

5. **Verify active version is new**
   ```bash
   ./bin/blue_green_deploy status
   ```

6. **Test in production** (optional, if new version is accessible)
   ```bash
   curl http://localhost:5005/health  # Inactive version
   curl http://localhost:5006/health  # New active version
   ```

### If Issues Found

7. **Rollback instantly**
   ```bash
   ./bin/blue_green_deploy rollback
   ```

### After Deployment

8. **Monitor metrics**
   ```bash
   # Watch error rates, latency on monitoring dashboard
   curl http://localhost:5004/metrics
   ```

---

## State Management

Deployment state is persisted to disk:

**Location:** `.local_context/bg_state.json`

**Contents:**
```json
{
  "active_version": "green",
  "blue_port": 5005,
  "green_port": 5006,
  "blue_pid": 12345,
  "green_pid": 12346,
  "blue_healthy": true,
  "green_healthy": true,
  "last_switch": "2025-10-16T18:30:00Z",
  "last_check": "2025-10-16T18:30:05Z",
  "deployment_history": [
    {
      "timestamp": "2025-10-16T18:30:00Z",
      "from": "blue",
      "to": "green",
      "status": "success"
    }
  ]
}
```

---

## Health Checks

### Health Check Endpoint

Both versions expose `/health` endpoint:

```bash
# Blue version
curl http://localhost:5005/health

# Green version
curl http://localhost:5006/health

# Active version (via proxy)
curl http://localhost:5004/health
```

Response (200 OK):
```json
{
  "ok": true,
  "app": "reflection_ui"
}
```

### Automatic Health Checking

When starting a new version, blue-green manager:
1. Polls `/health` endpoint every 1 second
2. Waits up to 30 seconds for response
3. Fails deployment if timeout
4. Stops instance on failure

---

## Configuration

### Custom Ports

By default, blue-green uses ports 5005 and 5006. To customize:

**Option 1: Environment Variables**
```bash
export BLUE_PORT=8001
export GREEN_PORT=8002
./bin/blue_green_deploy status
```

**Option 2: Python Code**
```python
from utils.blue_green import BlueGreenManager

manager = BlueGreenManager(
    app_script="app.py",
    blue_port=8001,
    green_port=8002
)
```

### Custom State File

```bash
# Change where state is saved
export BG_STATE_FILE=/var/lib/app/bg_state.json
./bin/blue_green_deploy status
```

---

## Integration with Monitoring

### Connect to Monitoring Dashboard

Blue-green deployment works seamlessly with monitoring:

```bash
# Start blue version
./bin/blue_green_deploy start blue

# Access monitoring dashboard
# http://localhost:5005/monitoring

# Deploy to green
./bin/blue_green_deploy deploy

# Monitoring shows transition
# Watch error rates, latency on both versions
```

### Metrics Collection

The monitoring system tracks:
- Error rates before/after switch
- Latency on active version
- Health check results
- Deployment timestamps

### Production Checklist

Before deploying with blue-green:

- [ ] Monitoring dashboard accessible
- [ ] `/health` endpoint responds 200 OK
- [ ] Both ports (5005, 5006) available
- [ ] Tests passing locally
- [ ] Monitoring alerts configured
- [ ] Rollback plan documented
- [ ] Team notified of deployment window

---

## Troubleshooting

### Issue: "Cannot switch to version: not healthy"

**Cause:** Health check failing on target version

**Solution:**
1. Check application logs on that port
2. Verify app started correctly
3. Ensure `/health` endpoint is working
4. Check for port conflicts

```bash
# Debug
./bin/blue_green_deploy health-check
ps aux | grep python  # Find processes
lsof -i :5005        # Check port
```

### Issue: "Process already running on port"

**Cause:** Port not freed after previous instance

**Solution:**
```bash
# Kill process on port
lsof -i :5005 | grep -v COMMAND | awk '{print $2}' | xargs kill -9

# Try again
./bin/blue_green_deploy start blue
```

### Issue: Deployment stuck on health checks

**Cause:** App taking >30 seconds to start or `/health` not responding

**Solution:**
1. Increase startup time (edit `utils/blue_green.py`, change 30 to 60 in `start_instance()`)
2. Check app.py logs for startup errors
3. Verify Flask is importing all dependencies
4. Run locally first: `python app.py` and check `/health`

### Issue: State file corruption

**Cause:** Unclean shutdown or filesystem issue

**Solution:**
```bash
# Reset state (WARNING: assumes no versions running)
rm .local_context/bg_state.json
./bin/blue_green_deploy status  # Creates fresh state

# Then restart versions
./bin/blue_green_deploy start blue
```

---

## Testing

### Run Tests

```bash
pytest tests/test_blue_green.py -v
```

**Tests cover:**
- State creation and persistence
- Port mapping
- Version switching logic
- Deployment history tracking
- Status reporting
- Configuration options

### Manual Testing

```bash
# Test deployment cycle
./bin/blue_green_deploy start blue
sleep 5
./bin/blue_green_deploy status
./bin/blue_green_deploy deploy
./bin/blue_green_deploy status
./bin/blue_green_deploy rollback
./bin/blue_green_deploy status
```

---

## Best Practices

### 1. Test Before Deploying

```bash
# Run all tests locally
pytest tests/

# Test load with current version
python tests/load_test.py

# Verify security audit passes
python tests/security_audit.py
```

### 2. Deploy During Low Traffic

- Deploy between busy periods if possible
- Monitor error rates during switch

### 3. Have Monitoring Ready

```bash
# Open monitoring dashboard before deploying
http://localhost:5004/monitoring
```

### 4. Use Deployment Windows

Document and announce:
- Deployment time
- Expected duration (usually <1 minute)
- Rollback plan

### 5. Gradual Rollout (Future)

For high-traffic systems, consider:
- Canary deployments (route 10% to new version)
- Shadow traffic (test new version without affecting users)

---

## Architecture Decisions

### Why Blue-Green Over Other Strategies?

**Canary Deployment:** Gradually shift traffic
- Pros: Risk reduction for high-traffic systems
- Cons: Complex; need request routing logic

**Rolling Deployment:** Replace instances one-by-one
- Pros: Resource efficient
- Cons: Requires multiple instances; complex rollback

**Blue-Green:** Keep two full versions, switch instantly
- ✅ Pros: Simple; atomic switch; instant rollback
- ⚠️ Cons: Need 2x resources during deployment

**For this project:** Blue-green is ideal because:
- Small to medium traffic (1000 users on 2 instances manageable)
- Instant rollback critical for education platform
- Simple implementation (easier to maintain)

---

## Next Steps

### Immediate

- ✅ Blue-green infrastructure ready
- [ ] Step 7: Route traffic to production
- [ ] Step 8: Verify production health

### Future Enhancements

- Advanced: Canary deployments
- Advanced: Load balancer integration (nginx/haproxy)
- Advanced: Automated deployment pipeline (GitHub Actions)

---

## Questions?

For detailed implementation, see:
- `utils/blue_green.py` - Core manager
- `bin/blue_green_deploy` - CLI tool
- `tests/test_blue_green.py` - Test suite

For integration, see:
- `docs/MONITORING_SETUP.md` - Monitoring integration
- `docs/SECURITY_AUDIT.md` - Security considerations
