# Deploying ALIGN Prototype to IIS (ai2.unity.edu)

This guide covers deploying the Flask application to IIS via Waitress, supporting both modern ARR (Application Request Routing) and legacy FastCGI approaches.

## Quick Summary

```
IIS (Port 80/443)
  ↓ [Reverse Proxy via ARR]
  ↓
Waitress (localhost:8000)
  ↓
Flask App
```

## Prerequisites

- Windows Server with IIS installed
- Python 3.9+ installed on server
- IIS modules: `Application Request Routing` (ARR) - Modern approach
- Or: `CGI` module - Legacy FastCGI approach

## Setup Steps

### 1. Clone Repository

```powershell
cd C:\inetpub\wwwroot
git clone https://github.com/your-repo/align-prototype.git
cd align-prototype
```

### 2. Install Python Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Test Locally (on Windows Server)

```powershell
# Test with Waitress directly
python -m waitress --port=8000 wsgi:app

# In another PowerShell window, test it:
curl http://127.0.0.1:8000
```

If page loads → **Great!** Proceed to IIS configuration.

## Deployment Approach A: Modern (IIS + ARR)

### Install ARR Module

1. Open **IIS Manager**
2. Go to **Server** → **Get Extensions**
3. Search for **Application Request Routing**
4. Install it

### Configure ARR in IIS

1. **Create Application Pool** (optional, or use default)
   - Name: `ALIGN_Pool`
   - .NET CLR version: No Managed Code

2. **Create Website or Virtual Directory**
   - Point to `C:\inetpub\wwwroot\align-prototype`
   - Assign to app pool

3. **Configure URL Rewrite Rules**
   - Open **IIS Manager** → Select your site
   - Double-click **URL Rewrite**
   - **Add Rule** → **Reverse Proxy**
   - Inbound URL: `(.*)`
   - Rewrite URL: `http://127.0.0.1:8000/{R:1}`
   - ✅ Check "Append query string"

4. **Set Proxy Headers**
   - In URL Rewrite rule → **Edit** → **Action**
   - Server Variables:
     ```
     HTTP_X_FORWARDED_FOR = {REMOTE_ADDR}
     HTTP_X_FORWARDED_PROTO = https  (or http depending on IIS setup)
     HTTP_X_FORWARDED_HOST = {HTTP_HOST}
     ```

### Start Waitress as Windows Service

**Option A: Use NSSM (Non-Sucking Service Manager)**

```powershell
# Download NSSM: https://nssm.cc/download
# Extract to C:\tools\nssm

C:\tools\nssm\nssm.exe install ALIGNWaitress "C:\Python39\python.exe" `
  "-m waitress --host=127.0.0.1 --port=8000 wsgi:app" `
  --cwd=C:\inetpub\wwwroot\align-prototype

# Start the service
C:\tools\nssm\nssm.exe start ALIGNWaitress

# Verify it's running:
netstat -ano | findstr :8000
```

**Option B: Use Python asyncio wrapper script** (`run_waitress.bat`)

```batch
@echo off
cd C:\inetpub\wwwroot\align-prototype
python -m waitress --host=127.0.0.1 --port=8000 wsgi:app
```

Then schedule with Task Scheduler to run at startup.

## Deployment Approach B: Legacy (IIS + FastCGI)

> Note: FastCGI is outdated but may already be configured on your server.

1. **Install FastCGI for Python**
   - Download: `wfastcgi.py` (Microsoft's FastCGI adapter)
   - Copy to project root

2. **Configure IIS Handler Mapping**
   - In IIS Manager: **Handler Mappings**
   - Add: File name: `*.py`, Module: `FastCgiModule`, Executable: `C:\Python39\python.exe -m wfastcgi`
   - Note request type: `All Verbs`

3. **Update web.config**
   ```xml
   <configuration>
     <appSettings>
       <add key="PYTHONPATH" value="C:\inetpub\wwwroot\align-prototype" />
       <add key="WSGI_HANDLER" value="wsgi:app" />
     </appSettings>
   </configuration>
   ```

> ⚠️ FastCGI is less reliable than ARR. Recommend **Approach A** if possible.

## Environment Configuration

Set on your Windows Server:

```powershell
# System Environment Variables:
[Environment]::SetEnvironmentVariable("PORT", "8000", "Machine")
[Environment]::SetEnvironmentVariable("FLASK_ENV", "production", "Machine")
[Environment]::SetEnvironmentVariable("FLASK_SECRET_KEY", "<your-secure-key>", "Machine")

# Generate a secure key:
python -c "import secrets; print(secrets.token_hex(32))"
```

## Verify Deployment

### 1. Check Waitress is running:
```powershell
netstat -ano | findstr :8000
```

### 2. Test direct connection:
```powershell
curl http://127.0.0.1:8000
```

### 3. Test through IIS:
```powershell
curl http://localhost
# Or via domain:
curl http://ai2.unity.edu
```

### 4. Check app features:
- http://ai2.unity.edu/ → Home page loads
- http://ai2.unity.edu/analytics → Analytics dashboard works
- Check browser console for tracking (static/analytics.js)

## Logs & Debugging

**Waitress logs:**
```powershell
# If running as service:
Get-EventLog -LogName Application | Where-Object {$_.Source -like "*Waitress*"}

# Or check output file if redirected
Get-Content C:\inetpub\wwwroot\align-prototype\waitress.log -Tail 50
```

**Flask logs:**
- Set `FLASK_ENV=development` temporarily to see detailed errors
- Check IIS logs: `C:\inetpub\logs\LogFiles\W3SVC1\`

**IIS Failed Request Tracing:**
1. In IIS Manager → Site → Failed Request Tracing Rules
2. Add rule for status `400-599`
3. View traces at `%windir%\System32\LogFiles\FailedReqLogFiles\`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 502 Bad Gateway | Waitress not running. Check service status and port 8000 |
| 404 Not Found | URL Rewrite rule not matching. Check pattern and test rule |
| CSRF Token Missing | Verify X-Forwarded headers set in ARR rule |
| Static files 404 | IIS may not serve `/static` directly. Add static file handler or use CDN |
| Analytics not tracking | Check browser console, verify `/api/analytics/events` reachable |

## Restarts & Updates

### Restart Waitress:
```powershell
# As service:
Restart-Service ALIGNWaitress

# Manual:
Stop-Process -Name python -Force
python -m waitress --host=127.0.0.1 --port=8000 wsgi:app
```

### Update code:
```powershell
cd C:\inetpub\wwwroot\align-prototype
git pull origin main
# Restart Waitress
Restart-Service ALIGNWaitress
```

## Production Checklist

- [ ] Python 3.9+ installed
- [ ] `requirements.txt` installed
- [ ] `wsgi.py` present in project root
- [ ] Waitress running on port 8000
- [ ] IIS ARR (or FastCGI) configured
- [ ] X-Forwarded headers set
- [ ] Flask environment set to `production`
- [ ] Secret key configured
- [ ] Test app loads at ai2.unity.edu
- [ ] Analytics tracking works
- [ ] Logs monitored for errors

## Support

For Jonathan or other maintainers:
- **App Issues**: Check Flask logs and browser console
- **Deployment Issues**: Check IIS Failed Request Tracing
- **Waitress Issues**: Restart service and check netstat for port 8000
- **Questions**: See wsgi.py for WSGI entry point docs

---

**Note**: The Flask app includes ProxyFix middleware, so X-Forwarded headers from IIS ARR will be properly handled. All security configurations (CSRF, session cookies) are production-ready.
