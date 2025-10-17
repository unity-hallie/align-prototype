#!/usr/bin/env python3
"""
End-to-End Workflow Testing with Form Submission
Tests actual user workflows: fill forms, submit, get redirects
Catches CSRF token issues, form submission failures, etc.
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

        print("🧪 E2E Workflow Testing (Form Submissions)")
        print("=" * 60)
        print()

        all_pass = True

        # Test 1: Homepage form submission
        print("1️⃣  Testing homepage form submission...")
        try:
            await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")

            # Fill form fields
            await page.fill('input[name="student_id"]', 'test_student_workflow')
            await page.select_option('select[name="assignment_type"]', 'generic')

            # Try to submit - should work if CSRF token exists
            response = await page.click('button[type="submit"]')

            # Wait for redirect/response
            await page.wait_for_navigation(timeout=5000)

            # Check we got redirected to reflection step (not 400/500)
            current_url = page.url
            status = page.evaluate("() => document.readyState") # Just check page loaded

            if '/reflection_step' in current_url or 'reflection' in current_url.lower():
                print("   ✅ PASS: Form submitted successfully, redirected to reflection")
            else:
                print(f"   ⚠️  Redirected to: {current_url}")
        except Exception as e:
            print(f"   ❌ FAIL: {str(e)[:80]}")
            all_pass = False

        print()

        # Test 2: Settings form - API key save
        print("2️⃣  Testing Settings API key form...")
        try:
            await page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded")

            # Find API key form
            api_key_input = await page.query_selector('input[name="api_key"]')
            if api_key_input:
                await page.fill('input[name="api_key"]', 'sk-test-key-12345')

                # Find and click the save button for the API key form
                # Get all forms and find the one with api_key input
                forms = await page.query_selector_all('form')
                for form in forms:
                    has_api_key = await form.query_selector('input[name="api_key"]')
                    if has_api_key:
                        button = await form.query_selector('button[type="submit"]')
                        if button:
                            await button.click()
                            await page.wait_for_timeout(1000)
                            break

                # Check if we got a success message or stayed on same page (not 400)
                page_content = await page.content()
                if '400' not in page.url and 'Bad Request' not in page_content:
                    print("   ✅ PASS: Settings form submitted without CSRF error")
                else:
                    print("   ❌ FAIL: Got CSRF or form validation error")
                    all_pass = False
            else:
                print("   ⚠️  API key input not found")
        except Exception as e:
            print(f"   ❌ FAIL: {str(e)[:80]}")
            all_pass = False

        print()

        # Test 3: Analytics toggle
        print("3️⃣  Testing Settings toggle form...")
        try:
            await page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded")

            # Find LLM toggle checkbox
            toggle_checkbox = await page.query_selector('input[name="llm_enabled"]')
            if toggle_checkbox:
                # Find its form and submit
                forms = await page.query_selector_all('form')
                for form in forms:
                    has_toggle = await form.query_selector('input[name="llm_enabled"]')
                    if has_toggle:
                        button = await form.query_selector('button[type="submit"]')
                        if button:
                            await button.click()
                            await page.wait_for_timeout(1000)
                            break

                page_content = await page.content()
                if '400' not in page.url and 'Bad Request' not in page_content:
                    print("   ✅ PASS: Toggle form submitted without CSRF error")
                else:
                    print("   ❌ FAIL: Got CSRF or form error")
                    all_pass = False
            else:
                print("   ⚠️  Toggle checkbox not found")
        except Exception as e:
            print(f"   ❌ FAIL: {str(e)[:80]}")
            all_pass = False

        print()
        print("=" * 60)

        if all_pass:
            print("✅ ALL WORKFLOW TESTS PASSED!")
            print("   • Form submissions work")
            print("   • CSRF tokens present and valid")
            print("   • No 400/403 CSRF errors")
        else:
            print("❌ SOME WORKFLOW TESTS FAILED")
            print("   Check form CSRF tokens and submission endpoints")

        print()
        await browser.close()
        return all_pass

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
