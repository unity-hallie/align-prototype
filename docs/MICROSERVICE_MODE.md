# Reflection MCP Microservice Mode

## Overview

By default, ALIGN calls `reflection-mcp` as a subprocess on each request. For advanced deployments (especially with authentication), you can run `reflection-mcp` as a separate HTTP microservice and connect to it via network requests.

**When to use microservice mode:**
- reflection-mcp is running on a different server/port
- Jonathan (or another team) maintains reflection-mcp with its own auth system
- You want to decouple ALIGN from the MCP lifecycle
- Multiple ALIGN instances need to share a single reflection-mcp service

## Configuration

### Step 1: Set Microservice Mode

In `.env` or as an environment variable:

```bash
REFLECTION_MCP_MODE=service
```

(Default is `subprocess` if not set)

### Step 2: Provide Service URL

Tell ALIGN where reflection-mcp is listening:

```bash
REFLECTION_MCP_SERVICE_URL=http://localhost:3000
```

Examples:
- Local testing: `http://localhost:3000`
- IIS server: `http://reflection-mcp.example.com:3000`
- Windows (local): `http://127.0.0.1:3000`

### Step 3: (Optional) Add Authentication

If your reflection-mcp service requires a token:

```bash
REFLECTION_MCP_AUTH_TOKEN=your-secret-bearer-token
```

The token will be sent as:
```
Authorization: Bearer your-secret-bearer-token
```

### Full Example .env

```bash
# Use microservice instead of subprocess
REFLECTION_MCP_MODE=service

# Connect to reflection-mcp running on Jonathan's auth-enabled server
REFLECTION_MCP_SERVICE_URL=http://localhost:3000

# Authentication token if reflection-mcp requires it
REFLECTION_MCP_AUTH_TOKEN=sk-reflection-secret-xyz

# Timeouts still apply (seconds)
REFLECTION_MCP_TIMEOUT=60
REFLECTION_MCP_RETRIES=2
```

## How It Works

When `REFLECTION_MCP_MODE=service`:

1. ALIGN receives a form submission
2. Instead of spawning a subprocess, it makes an HTTP POST to `REFLECTION_MCP_SERVICE_URL`
3. Request body: JSON payload (same format as subprocess stdin)
4. Auth header: `Authorization: Bearer {REFLECTION_MCP_AUTH_TOKEN}` (if token set)
5. Response: JSON parsed and returned to user

### Request Example

```json
POST http://localhost:3000
Authorization: Bearer token-xyz
Content-Type: application/json

{
  "method": "reflect_assignment",
  "params": {
    "assignment_id": "12345",
    "student_id": "alice",
    "student_response": "...",
    ...
  }
}
```

### Response Handling

The service can respond in two ways:

**MCP-style (wrapped):**
```json
{
  "result": {
    "content": [
      {
        "text": "{...actual response...}"
      }
    ]
  }
}
```

**Direct response:**
```json
{
  "insights": [...],
  "readiness_assessment": {...},
  ...
}
```

Both are supported; ALIGN will unwrap if needed.

## Fallback Behavior

- If `REFLECTION_MCP_MODE=subprocess` (default), uses subprocess (no URL needed)
- If `REFLECTION_MCP_MODE=service` but `REFLECTION_MCP_SERVICE_URL` is missing, returns error
- If `REFLECTION_MCP_SERVICE_URL` is unreachable, retries 1–5 times (configurable)

## Debugging

### Check if service is running

```bash
curl -X POST http://localhost:3000 \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"method":"health_check"}'
```

### Check ALIGN logs

ALIGN will report:
- `MCP service unreachable` → service is down or wrong URL
- `MCP service error 401` → auth token missing or invalid
- `MCP service timeout` → service is slow or hanging
- `Service response parse error` → service returned invalid JSON

### Test locally

Run reflection-mcp as a service:

```bash
# In reflection-mcp repo
python mcp_server.py --mode service --port 3000 --require-auth "your-token"
```

Then in align-prototype `.env`:

```bash
REFLECTION_MCP_MODE=service
REFLECTION_MCP_SERVICE_URL=http://localhost:3000
REFLECTION_MCP_AUTH_TOKEN=your-token
```

Restart ALIGN and test the form.

## For Jonathan (IIS Setup)

If Jonathan is running reflection-mcp as a separate service:

1. **Start reflection-mcp service** (separate from ALIGN)
   ```powershell
   # On reflection-mcp server
   python mcp_server.py --mode service --port 3000
   ```

2. **Configure ALIGN to use it**
   ```
   REFLECTION_MCP_MODE=service
   REFLECTION_MCP_SERVICE_URL=http://reflection-mcp-server.internal:3000
   REFLECTION_MCP_AUTH_TOKEN=<his-secret-token>
   ```

3. **Restart ALIGN**
   - IIS app pool recycle or Waitress restart

4. **Test**
   - Submit form at http://localhost:8000
   - Should see reflection step (not "Invalid MCP response")

## Switching Back to Subprocess Mode

If you want to revert:

```bash
# Option 1: Delete/comment out REFLECTION_MCP_MODE
# (defaults to subprocess)

# Option 2: Explicit subprocess
REFLECTION_MCP_MODE=subprocess
```

The app will auto-detect the sibling `../reflection-mcp/bin/reflection-mcp` or use the `REFLECTION_MCP_CMD` override.

## Advantages & Trade-offs

### Advantages
- ✅ Decoupled lifecycle (restart either service independently)
- ✅ Auth control on reflection-mcp side
- ✅ Multiple ALIGN instances can share one MCP
- ✅ Easier to monitor/scale reflection-mcp separately

### Trade-offs
- ❌ Network latency (POST + JSON serialization)
- ❌ Service must be kept running (separate uptime concern)
- ❌ Additional debugging (two services instead of one)

Choose subprocess for simplicity; choose service for advanced setups.
