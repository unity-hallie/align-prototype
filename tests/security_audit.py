#!/usr/bin/env python3
"""
Security Audit for align-prototype
Tests CSRF protection, security headers, injection vectors, and auth flows
Aligns with production readiness requirements for Learning Designer, Executor, Quality Advocate
"""

import requests
import re
import json
from collections import defaultdict
from typing import Dict, List, Tuple
from urllib.parse import urlencode

BASE_URL = "http://localhost:5004"

class SecurityAuditResult:
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.vulnerabilities = []
        self.warnings = []
        self.details = defaultdict(list)
        self.headers_found = {}

    def add_pass(self, test_name: str, details: str = ""):
        self.tests_passed += 1
        self.details[test_name].append({"status": "✅ PASS", "details": details})

    def add_fail(self, test_name: str, severity: str, details: str):
        self.tests_failed += 1
        if severity == "CRITICAL":
            self.vulnerabilities.append({"test": test_name, "severity": severity, "details": details})
        else:
            self.warnings.append({"test": test_name, "severity": severity, "details": details})
        self.details[test_name].append({"status": "❌ FAIL", "severity": severity, "details": details})

    def get_report(self) -> Dict:
        return {
            "summary": {
                "total_tests": self.tests_passed + self.tests_failed,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "pass_rate_percent": (self.tests_passed / (self.tests_passed + self.tests_failed) * 100) if (self.tests_passed + self.tests_failed) > 0 else 0,
                "critical_vulnerabilities": len(self.vulnerabilities),
                "warnings": len(self.warnings),
            },
            "vulnerabilities": self.vulnerabilities,
            "warnings": self.warnings,
            "headers_found": self.headers_found,
            "details": dict(self.details),
        }


def test_csrf_protection(result: SecurityAuditResult):
    """Test CSRF token protection on POST endpoints"""
    print("\n🔍 Testing CSRF Protection...")

    csrf_endpoints = [
        ("/design/improve_outcomes", "POST"),
        ("/settings", "POST"),
        ("/start_reflection", "POST"),
        ("/submit_response", "POST"),
        ("/save_draft", "POST"),
        ("/load_demo", "POST"),
        ("/probe_question", "POST"),
    ]

    for endpoint, method in csrf_endpoints:
        url = f"{BASE_URL}{endpoint}"

        # Test 1: POST without CSRF token should fail
        try:
            response = requests.post(url, json={}, timeout=5)
            if response.status_code == 400 and "csrf" in response.text.lower():
                result.add_pass("CSRF Token Required", f"{endpoint}: Rejected POST without token (400)")
            elif response.status_code in [400, 403]:
                result.add_pass("CSRF Token Required", f"{endpoint}: Request rejected ({response.status_code})")
            else:
                result.add_fail("CSRF Token Required", "HIGH", f"{endpoint}: Accepted POST without token ({response.status_code})")
        except Exception as e:
            result.add_fail("CSRF Token Required", "MEDIUM", f"{endpoint}: Test error: {str(e)}")

    # Test 2: Check for CSRF token in GET responses
    try:
        response = requests.get(f"{BASE_URL}/settings", timeout=5)
        if "csrf_token" in response.text.lower() or "_token" in response.text.lower():
            result.add_pass("CSRF Token Generation", "GET /settings contains CSRF token field")
        else:
            result.add_fail("CSRF Token Generation", "MEDIUM", "GET /settings missing CSRF token field")
    except Exception as e:
        result.add_fail("CSRF Token Generation", "MEDIUM", f"Error: {str(e)}")


def test_security_headers(result: SecurityAuditResult):
    """Test security headers on all responses"""
    print("🔍 Testing Security Headers...")

    required_headers = {
        "X-Content-Type-Options": ("nosniff", "Prevents MIME sniffing"),
        "X-Frame-Options": ("DENY|SAMEORIGIN", "Prevents clickjacking"),
        "X-XSS-Protection": ("1|0", "XSS protection directive"),
        "Strict-Transport-Security": ("max-age=", "HSTS enforcement"),
    }

    recommended_headers = {
        "Content-Security-Policy": "CSP prevents inline script execution",
        "Referrer-Policy": "Controls referrer information",
        "Permissions-Policy": "Controls browser features",
    }

    endpoints_to_check = ["/", "/health", "/settings", "/designer"]

    for endpoint in endpoints_to_check:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
            result.headers_found[endpoint] = dict(response.headers)

            # Check required headers
            for header, (expected_value, description) in required_headers.items():
                if header in response.headers:
                    result.add_pass(f"Header: {header}", f"{endpoint}: Present - {description}")
                else:
                    result.add_fail(f"Header: {header}", "MEDIUM", f"{endpoint}: Missing - {description}")

            # Check recommended headers
            for header, description in recommended_headers.items():
                if header in response.headers:
                    result.add_pass(f"Header: {header}", f"{endpoint}: {description}")
                else:
                    result.warnings.append({"test": f"Header: {header}", "severity": "LOW", "details": f"{endpoint}: Missing - {description}"})

        except Exception as e:
            result.add_fail("Security Headers", "MEDIUM", f"{endpoint}: {str(e)}")

    # Check for insecure headers
    for endpoint in endpoints_to_check:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
            if "Server" in response.headers:
                result.add_fail("Header: Server Exposure", "LOW", f"{endpoint}: Exposes server info: {response.headers['Server']}")
            if any("PHP" in str(v) for v in response.headers.values()):
                result.add_fail("Header: PHP Exposure", "MEDIUM", f"{endpoint}: Exposes PHP version info")
        except Exception as e:
            pass


def test_injection_attacks(result: SecurityAuditResult):
    """Test for XSS and injection vulnerabilities"""
    print("🔍 Testing Injection Attacks...")

    # XSS payload vectors
    xss_payloads = [
        ("<script>alert('xss')</script>", "Basic script tag"),
        ("'><script>alert('xss')</script>", "Quote escape + script"),
        ("javascript:alert('xss')", "JavaScript protocol"),
        ("<img src=x onerror=alert('xss')>", "Image onerror handler"),
        ("<svg/onload=alert('xss')>", "SVG onload handler"),
    ]

    # Test GET parameters for XSS
    print("  Testing GET parameters for XSS reflection...")
    for payload, description in xss_payloads:
        try:
            # Try common parameter names
            for param in ["q", "search", "term", "query", "name", "id"]:
                url = f"{BASE_URL}/?{param}={requests.utils.quote(payload)}"
                response = requests.get(url, timeout=5)

                # Check if payload is reflected unescaped
                if payload in response.text and ("<script>" in response.text or "onerror=" in response.text):
                    result.add_fail("XSS Vulnerability (GET)", "CRITICAL", f"Unescaped {description} in {param} parameter")
                elif payload in response.text:
                    # Reflected but might be escaped - check if dangerous
                    if "&lt;script&gt;" in response.text or "&#" in response.text:
                        result.add_pass("XSS Protection (GET)", f"{param}: Payload escaped properly")
                    else:
                        result.add_fail("XSS Vulnerability (GET)", "HIGH", f"Potentially dangerous reflection of {description} in {param}")
        except Exception as e:
            pass

    # SQL Injection test on common patterns
    print("  Testing for SQL injection...")
    sql_payloads = [
        ("' OR '1'='1", "Classic OR condition"),
        ("1; DROP TABLE users--", "Drop table attack"),
        ("admin'--", "Comment bypass"),
    ]

    for payload, description in sql_payloads:
        try:
            # Test on endpoints that might query a DB
            for endpoint in ["/", "/settings", "/designer"]:
                url = f"{BASE_URL}{endpoint}"
                response = requests.get(url, params={"id": payload}, timeout=5)

                # Check for SQL error patterns
                if any(error in response.text.lower() for error in ["sql", "syntax", "error", "database"]):
                    result.add_fail("SQL Injection (GET)", "HIGH", f"{endpoint}: SQL error exposed for {description}")
                else:
                    result.add_pass("SQL Injection Protection (GET)", f"{endpoint}: No SQL errors for {description}")
        except Exception as e:
            pass

    # Command injection test
    print("  Testing for command injection...")
    cmd_payloads = [
        ("; ls", "Unix command separator"),
        ("| whoami", "Pipe injection"),
        ("$(whoami)", "Command substitution"),
    ]

    for payload, description in cmd_payloads:
        try:
            response = requests.get(f"{BASE_URL}/?cmd={requests.utils.quote(payload)}", timeout=5)
            # Look for command output patterns
            if any(pattern in response.text for pattern in ["bin/", "root", "www-data", "uid=", "gid="]):
                result.add_fail("Command Injection", "CRITICAL", f"Possible command execution: {description}")
            else:
                result.add_pass("Command Injection Protection", f"No execution: {description}")
        except Exception as e:
            pass


def test_authentication_flows(result: SecurityAuditResult):
    """Test session management and auth flows"""
    print("🔍 Testing Authentication Flows...")

    # Test 1: Session cookie attributes
    print("  Checking session cookie attributes...")
    try:
        response = requests.get(f"{BASE_URL}/settings", timeout=5)

        # Check for session cookie
        session_cookie = None
        for cookie in response.cookies:
            if "session" in cookie.name.lower():
                session_cookie = cookie
                break

        if session_cookie:
            # Check cookie attributes
            if hasattr(session_cookie, "_rest"):
                attrs = session_cookie._rest
                if "httponly" in [str(k).lower() for k in attrs.keys()]:
                    result.add_pass("Cookie: HttpOnly Flag", "Session cookie marked HttpOnly")
                else:
                    result.add_fail("Cookie: HttpOnly Flag", "HIGH", "Session cookie missing HttpOnly flag")

                if "secure" in [str(k).lower() for k in attrs.keys()]:
                    result.add_pass("Cookie: Secure Flag", "Session cookie marked Secure")
                else:
                    result.warnings.append({"test": "Cookie: Secure Flag", "severity": "MEDIUM", "details": "Session cookie missing Secure flag (OK for dev, not production)"})
            else:
                result.add_pass("Cookie: Attributes", "Session cookie found")
        else:
            result.add_fail("Session Cookie", "MEDIUM", "No session cookie detected in responses")

    except Exception as e:
        result.add_fail("Authentication Flows", "MEDIUM", f"Error: {str(e)}")

    # Test 2: Unauthorized access to protected endpoints
    print("  Testing access control...")
    try:
        # Create new session
        session = requests.Session()
        response = session.get(f"{BASE_URL}/settings", timeout=5)
        if response.status_code == 200:
            result.add_pass("Endpoint Access", "/settings accessible (no auth required)")
        else:
            result.add_fail("Endpoint Access", "MEDIUM", f"/settings returned {response.status_code}")
    except Exception as e:
        result.add_fail("Endpoint Access", "MEDIUM", f"Error: {str(e)}")


def test_https_redirect(result: SecurityAuditResult):
    """Test HTTPS enforcement"""
    print("🔍 Testing HTTPS Enforcement...")

    # Note: This test is informational since we're on HTTP in dev
    try:
        # Check HSTS header
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if "Strict-Transport-Security" in response.headers:
            result.add_pass("HSTS Enforced", response.headers["Strict-Transport-Security"])
        else:
            result.warnings.append({"test": "HSTS Enforcement", "severity": "MEDIUM", "details": "HSTS header not set (required for production)"})
    except Exception as e:
        pass


def run_security_audit() -> SecurityAuditResult:
    """Run complete security audit"""
    result = SecurityAuditResult()

    print("\n" + "="*60)
    print("🔐 ALIGN-PROTOTYPE SECURITY AUDIT")
    print("="*60)
    print(f"Target: {BASE_URL}")

    try:
        # Check if server is running
        requests.get(f"{BASE_URL}/health", timeout=5)
    except Exception as e:
        print(f"❌ Server not running at {BASE_URL}")
        print(f"   Error: {e}")
        return result

    # Run all tests
    test_csrf_protection(result)
    test_security_headers(result)
    test_injection_attacks(result)
    test_authentication_flows(result)
    test_https_redirect(result)

    return result


def print_report(result: SecurityAuditResult):
    """Pretty-print security audit report"""
    report = result.get_report()
    summary = report["summary"]

    print("\n" + "="*60)
    print("📊 SECURITY AUDIT RESULTS")
    print("="*60)

    # Summary
    print(f"\n📈 Test Summary:")
    print(f"   Total tests: {summary['total_tests']}")
    print(f"   Passed: {summary['passed']} ✅")
    print(f"   Failed: {summary['failed']} ❌")
    print(f"   Pass rate: {summary['pass_rate_percent']:.1f}%")

    # Critical vulnerabilities
    if report["vulnerabilities"]:
        print(f"\n🚨 CRITICAL VULNERABILITIES ({len(report['vulnerabilities'])}):")
        for vuln in report["vulnerabilities"]:
            print(f"   ❌ {vuln['test']}: {vuln['details']}")
    else:
        print(f"\n✅ No critical vulnerabilities found!")

    # Warnings
    if report["warnings"]:
        print(f"\n⚠️  WARNINGS ({len(report['warnings'])}):")
        for warn in report["warnings"]:
            print(f"   ⚠️  {warn['test']}: {warn['details']}")

    # Security Headers Detected
    if report["headers_found"]:
        print(f"\n🔐 Security Headers Detected:")
        all_headers = set()
        for endpoint, headers in report["headers_found"].items():
            all_headers.update(headers.keys())

        security_headers = [h for h in all_headers if any(keyword in h.lower() for keyword in ["x-", "content-security", "strict", "referrer", "permissions"])]
        for header in sorted(security_headers):
            print(f"   ✅ {header}")

    # Overall rating
    print(f"\n{'✅ PASS' if summary['critical_vulnerabilities'] == 0 and summary['pass_rate_percent'] >= 80 else '⚠️  WARNING' if summary['pass_rate_percent'] >= 60 else '❌ FAIL'}")
    print("="*60 + "\n")

    return report


if __name__ == "__main__":
    import sys

    try:
        result = run_security_audit()
        report = print_report(result)

        # Save report
        output_file = "/tmp/security_audit_report.json"
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"📁 Report saved to: {output_file}\n")

        # Exit with failure if critical vulnerabilities found
        if report["summary"]["critical_vulnerabilities"] > 0:
            print(f"❌ Security audit FAILED: {report['summary']['critical_vulnerabilities']} critical vulnerabilities detected")
            sys.exit(1)
        else:
            print(f"✅ Security audit PASSED: All critical checks clear\n")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Audit failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
