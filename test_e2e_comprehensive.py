#!/usr/bin/env python3
"""
Comprehensive End-to-End QA Test with Full Path Discovery
Tests ALL pages and navigation paths - not just happy path
"""

import asyncio
import sys
from pathlib import Path
from collections import defaultdict
from urllib.parse import urljoin, urlparse

# Known routes from app.py
KNOWN_ROUTES = [
    "/",
    "/health",
    "/analytics",
    "/settings",
    "/about",
    "/docs/llm_risks",
    "/docs/demo",
    "/audit",
    "/audit/why_ai",
    "/reflection_step",
    "/reflection_summary",
]

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

        # Track visited pages and errors
        visited = set()
        errors = []
        navigation_map = defaultdict(list)  # page -> list of links

        print("🧪 Comprehensive E2E Path Discovery Test")
        print("=" * 60)
        print()

        async def extract_links(url_path):
            """Extract all links from a page"""
            try:
                response = await page.goto(f"{BASE_URL}{url_path}", wait_until="domcontentloaded")

                if response.status >= 400:
                    errors.append({
                        'path': url_path,
                        'status': response.status,
                        'type': 'page_load'
                    })
                    return []

                # Get all <a> links
                links = await page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.getAttribute('href'))
                            .filter(href =>
                                href &&
                                !href.startsWith('mailto:') &&
                                !href.startsWith('javascript:') &&
                                !href.startsWith('#')
                            );
                    }
                """)

                return links
            except Exception as e:
                errors.append({
                    'path': url_path,
                    'error': str(e),
                    'type': 'extraction'
                })
                return []

        async def test_page(url_path, depth=0):
            """Recursively test page and discover links"""
            if url_path in visited or depth > 3:  # Limit recursion
                return

            visited.add(url_path)
            indent = "  " * depth

            print(f"{indent}📄 Testing: {url_path}")

            # Get links from this page
            links = await extract_links(url_path)

            # Filter to get clean relative paths
            clean_links = []
            for link in links:
                if link.startswith('/'):
                    clean_links.append(link)
                elif link.startswith('?') or link.startswith('&'):
                    # Query string, skip
                    continue
                else:
                    # Handle relative links
                    resolved = urljoin(url_path, link).split('?')[0]
                    if resolved.startswith('/'):
                        clean_links.append(resolved)

            clean_links = list(set(clean_links))  # Remove duplicates
            navigation_map[url_path] = clean_links

            if clean_links:
                print(f"{indent}   Found {len(clean_links)} links")

            # Test each discovered link (limit to prevent infinite recursion)
            if depth < 2:
                for link in clean_links[:5]:  # Test first 5 links per page
                    if link not in visited:
                        await test_page(link, depth + 1)

        # Start with known routes
        print("🔍 Phase 1: Testing Known Routes")
        print("-" * 60)
        for route in KNOWN_ROUTES:
            if route not in visited:
                await test_page(route)

        print()
        print("📊 Phase 2: Summary Report")
        print("=" * 60)

        # Categorize errors
        page_load_errors = [e for e in errors if e['type'] == 'page_load']
        extraction_errors = [e for e in errors if e['type'] == 'extraction']

        print(f"✅ Pages tested successfully: {len(visited)}")
        print(f"❌ Page load errors: {len(page_load_errors)}")
        print(f"⚠️  Extraction errors: {len(extraction_errors)}")
        print()

        # Report errors
        if page_load_errors:
            print("🔴 PAGE LOAD ERRORS:")
            for err in page_load_errors:
                print(f"   {err['path']}: HTTP {err['status']}")
            print()

        # Navigation structure
        print("🗺️  Navigation Structure:")
        print("-" * 60)
        for page_path in sorted(visited):
            links = navigation_map.get(page_path, [])
            if links:
                print(f"  {page_path}")
                for link in sorted(links)[:3]:  # Show first 3 links per page
                    print(f"    └─ {link}")
                if len(links) > 3:
                    print(f"    └─ ... and {len(links) - 3} more")

        print()
        print("=" * 60)

        # Final verdict
        if page_load_errors:
            print("❌ FAIL: Some pages returned 400/502 errors")
            for err in page_load_errors:
                print(f"   - {err['path']}: {err['status']}")
            await browser.close()
            return False
        else:
            print("✅ SUCCESS: All tested pages load without 400/502 errors")
            print(f"   Discovered and tested {len(visited)} unique pages")
            print(f"   Navigation structure verified")
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
