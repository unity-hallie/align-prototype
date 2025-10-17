# ALIGN Prototype → Jonathan Handoff

**Status:** ✅ **READY FOR DEPLOYMENT**

---

## Executive Summary

The ALIGN prototype is production-ready for IIS deployment. All pages navigate without errors, forms submit successfully with CSRF protection, and the codebase now supports both **subprocess mode** (default, simple) and **microservice mode** (new, for your auth-enabled reflection-mcp).

**What Changed:** Decoupled reflection-mcp, fixed CSRF tokens, added microservice support.

**Your Options:**
1. **Keep it simple:** Use subprocess mode (auto-detects sibling repo)
2. **Use your auth:** Use microservice mode (call reflection-mcp as separate service with tokens)

---

## Current State (from Testing)

### Navigation ✅
- All 14 pages load without 400/502 errors
- See `QA_AUDIT_REPORT.md` for full audit

### Forms ✅
- CSRF tokens auto-injected by base.html JavaScript
- Form submission works (tested in user session)
- No manual template hacks needed

### Architecture ✅
- reflection-mcp decoupled to sibling repo (`../reflection-mcp/bin/reflection-mcp`)
- App auto-detects sibling or allows override
- Ready for multi-server deployment

---

## Deployment Options

### Option 1: Subprocess Mode (Default, Simplest)

**Use this if:** You want to keep things simple or integrate reflection-mcp into ALIGN's lifecycle.

**Setup:**
```bash
# .env or environment variables
REFLECTION_MCP_MODE=subprocess
# (optional) REFLECTION_MCP_CMD=../reflection-mcp/bin/reflection-mcp
```

**How it works:**
- ALIGN spawns reflection-mcp as subprocess on each request
- Auto-detects sibling repo or uses explicit command
- No auth needed; same process lifecycle

**Deploy:**
1. Clone both repos side-by-side on IIS:
   ```
   C:\inetpub\wwwroot\
     ├── align-prototype\
     └── reflection-mcp\
   ```
2. Restart ALIGN (Waitress or IIS app pool)
3. Test form at http://localhost:8000

---

### Option 2: Microservice Mode (For Your Auth System)

**Use this if:** You're running reflection-mcp separately with authentication and want to decouple the services.

**Setup:**
```bash
# .env or environment variables
REFLECTION_MCP_MODE=service
REFLECTION_MCP_SERVICE_URL=http://localhost:3000
REFLECTION_MCP_AUTH_TOKEN=your-bearer-token-here
```

**How it works:**
- reflection-mcp runs as separate HTTP service (you control it)
- ALIGN calls via HTTP POST with auth token
- Services can be updated/restarted independently
- Multiple ALIGN instances can share one MCP service

**Deploy:**

*Step 1: Start reflection-mcp as service* (on same or different server)
```bash
# reflection-mcp repo
python mcp_server.py --mode service --port 3000 --auth-token your-bearer-token-here
```

*Step 2: Configure ALIGN to use it*
```bash
# .env
REFLECTION_MCP_MODE=service
REFLECTION_MCP_SERVICE_URL=http://localhost:3000
REFLECTION_MCP_AUTH_TOKEN=your-bearer-token-here
```

*Step 3: Restart ALIGN*
```bash
# IIS app pool recycle or Waitress restart
python wsgi.py
```

*Step 4: Test*
- Navigate to http://localhost:8000
- Fill form, submit
- Should NOT see "Invalid MCP response"
- Should see reflection step page

---

## Configuration Reference

### All MCP Environment Variables

```bash
# Mode: 'subprocess' (default) or 'service'
REFLECTION_MCP_MODE=subprocess

# For subprocess mode (optional):
REFLECTION_MCP_CMD=../reflection-mcp/bin/reflection-mcp
# or on Windows:
REFLECTION_MCP_CMD=python ../reflection-mcp/mcp_server.py

# For service mode (required):
REFLECTION_MCP_SERVICE_URL=http://localhost:3000

# For service mode (optional, if your service requires auth):
REFLECTION_MCP_AUTH_TOKEN=sk-your-secret-token

# Both modes (optional):
REFLECTION_MCP_TIMEOUT=60          # seconds
REFLECTION_MCP_RETRIES=2           # retry count (1-5)
```

### See Also
- `.env.example` — template with all options documented
- `docs/MICROSERVICE_MODE.md` — detailed microservice setup guide
- `DEPLOY_IIS.md` — IIS-specific deployment steps

---

## Testing (Before Deploy)

### Quick Local Test

```bash
# Terminal 1: Start ALIGN
python -m waitress --port=8000 wsgi:app

# Terminal 2: Test navigation
python test_e2e.py              # All pages load
python test_e2e_comprehensive.py # Full path discovery

# Terminal 3: Test forms
python tests/test_mcp_modes.py   # Subprocess + service modes
```

### Run Full Test Suite

```bash
pytest tests/ -v
```

Tests cover:
- ✅ Subprocess mode (default)
- ✅ Service mode with/without auth
- ✅ Timeout/retry logic
- ✅ Error handling (connection errors, auth failures, etc.)
- ✅ Mode selection logic

### Manual Form Test

1. http://localhost:8000 → Click "Create New Reflection Session"
2. Fill out form (student name, assignment type, response)
3. Click "Start Reflection Session"
4. Should see reflection step (not error page)

---

## Troubleshooting

### "Invalid MCP response format"
- **Cause:** reflection-mcp service not running or wrong URL
- **Fix (subprocess):** Verify `../reflection-mcp/bin/reflection-mcp` exists and is executable
- **Fix (service):** Check `REFLECTION_MCP_SERVICE_URL` is correct; test with curl:
  ```bash
  curl -X POST http://localhost:3000 \
    -H "Authorization: Bearer your-token" \
    -H "Content-Type: application/json" \
    -d '{"method":"health"}'
  ```

### "MCP service unreachable"
- **Cause:** Service URL is wrong or service is down
- **Fix:**
  - Verify `REFLECTION_MCP_SERVICE_URL` in `.env`
  - Check reflection-mcp service is running
  - Check firewall/network connectivity

### "MCP service error 401"
- **Cause:** Auth token missing or invalid
- **Fix:**
  - Verify `REFLECTION_MCP_AUTH_TOKEN` is set
  - Verify token matches what reflection-mcp expects
  - Check token hasn't expired

### Form doesn't submit (stays on page)
- **Cause:** CSRF validation or JavaScript error
- **Fix:**
  - Check browser console for errors (F12 → Console)
  - Verify `base.html` is being served (view source should show CSRF auto-inject script)
  - Clear browser cache and reload

### "CSRF token is missing"
- **Cause:** Old version of templates or caching issue
- **Fix:**
  - Hard refresh (Ctrl+Shift+R on Windows, Cmd+Shift+R on Mac)
  - Verify `templates/base.html` has the DOMContentLoaded script (lines 151-168)
  - Restart web server

---

## Files Changed (Recent Commits)

### Commit 1: Decouple reflection-mcp
- Removed local reflection_mcp/ directory (now at sibling repo)
- Removed local bin/reflection-mcp symlink
- app.py already detects sibling repo

### Commit 2: Add microservice mode
- Split `call_reflection_mcp()` into:
  - `_call_reflection_mcp_subprocess()` — original behavior
  - `_call_reflection_mcp_service()` — new HTTP mode
- Added config options: `REFLECTION_MCP_MODE`, `REFLECTION_MCP_SERVICE_URL`, `REFLECTION_MCP_AUTH_TOKEN`
- Updated `.env.example` with examples
- Created `docs/MICROSERVICE_MODE.md`
- Added `tests/test_mcp_modes.py` (30+ tests)

### Commit 3: CSRF Fix (Earlier)
- Modified `templates/base.html` to auto-inject CSRF tokens via JavaScript
- No manual template edits needed; one change covers all forms

---

## Key Files to Understand

```
align-prototype/
├── app.py                       # Main Flask app
│   ├── call_reflection_mcp()    # Entry point for MCP calls
│   ├── _call_reflection_mcp_subprocess()  # Subprocess mode
│   └── _call_reflection_mcp_service()     # Service mode
├── .env.example                 # Config template (with all options)
├── templates/
│   └── base.html                # Master template (CSRF auto-inject here)
├── docs/
│   ├── MICROSERVICE_MODE.md     # Detailed setup guide
│   └── DEPLOY_IIS.md            # IIS-specific steps
├── tests/
│   ├── test_mcp_modes.py        # Mode selection tests
│   ├── test_e2e.py              # Navigation tests
│   └── test_e2e_comprehensive.py # Full path discovery
└── wsgi.py                      # Entry point for IIS/Waitress
```

---

## Decision Tree

**Choose subprocess mode if:**
- ✅ You want everything in one place
- ✅ You don't need separate auth on reflection-mcp
- ✅ You want to keep deployment simple
- ✅ First-time setup

**Choose microservice mode if:**
- ✅ You're running reflection-mcp separately
- ✅ You have auth tokens on the reflection-mcp service
- ✅ You want to scale/restart services independently
- ✅ Multiple ALIGN instances need to share one MCP
- ✅ You need advanced monitoring/logging on the MCP side

---

## Next Steps

### Immediate (Before Deploy)
1. ✅ Read this document
2. ✅ Decide: subprocess or microservice mode?
3. ✅ Run tests locally: `pytest tests/ -v`
4. ✅ Test form submission manually

### Deploy to IIS
1. Clone both repos side-by-side (if subprocess mode)
2. Set environment variables (or edit `.env`)
3. Restart Waitress / IIS app pool
4. Test http://localhost:8000

### If Using Microservice Mode
1. Start reflection-mcp service separately
2. Configure `REFLECTION_MCP_SERVICE_URL` and auth token
3. Restart ALIGN
4. Test form submission

---

## Questions or Issues?

See:
- `docs/MICROSERVICE_MODE.md` — detailed microservice setup
- `DEPLOY_IIS.md` — IIS deployment steps
- `QA_AUDIT_REPORT.md` — navigation verification
- Test files in `tests/` for examples

---

**Version:** Oct 17, 2025
**Tested:** All 14 pages ✅ | Forms ✅ | Subprocess mode ✅ | Service mode ✅ (mocked)
**Status:** Ready for deployment
**Next Owner:** Jonathan

Good luck! 🚀
