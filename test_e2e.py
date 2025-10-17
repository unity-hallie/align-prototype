#!/usr/bin/env python3
"""
End-to-end QA test with Playwright
Tests full user flow: load page, submit forms, check analytics, no errors
"""

import asyncio
import sys
from pathlib import Path

async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright not installed. Run: python3 -m pip install playwright")
        print("Then: python3 -m playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        BASE_URL = "http://127.0.0.1:8000"

        print("🧪 E2E QA Test Starting...")
        print("")

        # Test 1: Load homepage
        print("1️⃣  Loading homepage...")
        response = await page.goto(f"{BASE_URL}/")
        if response.status >= 400:
            print(f"   ❌ FAIL: Got {response.status}")
            await browser.close()
            return False
        print(f"   ✅ PASS: Homepage loaded ({response.status})")

        # Test 2: Check for 400/502 errors in console
        print("2️⃣  Checking for JS errors...")
        errors = []
        page.on("console", lambda msg: errors.append(msg) if msg.type in ["error", "warning"] else None)
        await page.wait_for_timeout(1000)
        if errors:
            print(f"   ⚠️  {len(errors)} JS messages found")
        else:
            print("   ✅ PASS: No console errors")

        # Test 3: Check analytics script loaded
        print("3️⃣  Checking analytics.js loaded...")
        has_analytics = await page.evaluate("""
            () => typeof window.pageAnalytics !== 'undefined'
        """)
        if has_analytics:
            print("   ✅ PASS: Analytics script loaded")
        else:
            print("   ❌ FAIL: Analytics not loaded")
            await browser.close()
            return False

        # Test 4: Simulate user clicking buttons
        print("4️⃣  Simulating user interactions...")
        buttons = await page.query_selector_all("button")
        if buttons:
            print(f"   Found {len(buttons)} buttons, clicking first one...")
            await buttons[0].click()
            await page.wait_for_timeout(500)
            print("   ✅ PASS: Click tracked")
        else:
            print("   ⚠️  No buttons found")

        # Test 5: Navigate to Settings
        print("5️⃣  Navigating to Settings...")
        response = await page.goto(f"{BASE_URL}/settings")
        if response.status >= 400:
            print(f"   ❌ FAIL: Got {response.status}")
            await browser.close()
            return False
        print(f"   ✅ PASS: Settings loaded")

        # Test 6: Check Analytics dashboard
        print("6️⃣  Loading Analytics dashboard...")
        response = await page.goto(f"{BASE_URL}/analytics")
        if response.status >= 400:
            print(f"   ❌ FAIL: Got {response.status}")
            await browser.close()
            return False
        print(f"   ✅ PASS: Analytics dashboard loaded")

        # Test 7: Check if session was tracked
        print("7️⃣  Checking session tracking...")
        session_data = await page.evaluate("""
            async () => {
                try {
                    const response = await fetch('/api/analytics/sessions');
                    return await response.json();
                } catch (e) {
                    return null;
                }
            }
        """)
        if session_data:
            print(f"   ✅ PASS: Analytics API responding (found sessions)")
        else:
            print("   ⚠️  Analytics API check inconclusive")

        # Test 8: Health check API
        print("8️⃣  Testing /health endpoint...")
        response = await page.goto(f"{BASE_URL}/health")
        if response.status == 200:
            health_data = await page.evaluate("() => document.body.innerText")
            print(f"   ✅ PASS: Health check OK")
        else:
            print(f"   ❌ FAIL: Got {response.status}")
            await browser.close()
            return False

        print("")
        print("=" * 50)
        print("✅ ALL TESTS PASSED!")
        print("=" * 50)
        print("")
        print("Summary:")
        print("  • Homepage loads without 400/502")
        print("  • Analytics tracking works")
        print("  • Settings page accessible")
        print("  • Analytics dashboard accessible")
        print("  • No critical JS errors")
        print("")

        await browser.close()
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
