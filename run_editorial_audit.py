#!/usr/bin/env python3
"""
Standalone editorial audit runner.

Usage:
    python run_editorial_audit.py https://www.harpersbazaar.com/fashion/a12345/article-slug/
    python run_editorial_audit.py https://www.harpersbazaar.com/

Prints a formatted report to stdout with pass/fail for each of the 10 tests.
"""

import asyncio
import json
import sys
from urllib.parse import urlparse

from patchright.async_api import async_playwright
from extractors.editorial_signals import EditorialSignalsExtractor
from extractors.base import ExtractionContext


PASS  = '✅'
FAIL  = '❌'
INFO  = '   '   # informational assertion (prefixed with ~)
SOFT  = '~'


def _render_assertion(a: dict) -> str:
    is_soft = a['label'].startswith(SOFT)
    label   = a['label'].lstrip(SOFT).strip()
    icon    = '⚬' if is_soft else (PASS if a['passed'] else FAIL)
    val     = f"  → {a['value']}" if a.get('value') is not None else ''
    return f"    {icon}  {label}{val}"


def _render_report(result: dict, url: str):
    tests   = result.get('tests', [])
    passed  = result.get('passed', 0)
    total   = result.get('total', 0)
    score   = result.get('score', 0)

    domain = urlparse(url).netloc
    print(f"\n{'═'*70}")
    print(f"  📋  Editorial Audit: {domain}")
    print(f"  URL: {url}")
    print(f"{'═'*70}")
    print(f"  Score: {score}%  ({passed}/{total} tests passed)")
    print()

    for t in tests:
        status = PASS if t['passed'] else FAIL
        note   = f"  [{t.get('note', '')}]" if t.get('note') else ''
        print(f"  {status}  {t['test_name']}{note}")
        for a in t.get('assertions', []):
            print(_render_assertion(a))
        print()

    print('─'*70)
    print('Extracted values summary:')
    for t in tests:
        ex = t.get('extracted', {})
        interesting = {k: v for k, v in ex.items()
                       if v not in (None, '', [], {}, False, 0)
                       and k != 'error'}
        if interesting:
            print(f"\n  [{t['test_id']}]")
            for k, v in interesting.items():
                val = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                if len(val) > 100:
                    val = val[:97] + '...'
                print(f"    {k}: {val}")

    print(f"\n{'═'*70}\n")


async def run_audit(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/121.0.0.0 Safari/537.36'
            )
        )
        page = await context.new_page()

        # Inject PerformanceObserver on the PAGE (not context) so it runs before
        # the first navigation. page.add_init_script() evaluates on every navigation.
        await page.add_init_script("""
            window.__lcpEntries = [];
            window.__clsValue   = 0;
            try {
                new PerformanceObserver(list => {
                    for (const e of list.getEntries()) window.__lcpEntries.push(e.startTime);
                }).observe({ type: 'largest-contentful-paint', buffered: true });
            } catch(e) {}
            try {
                new PerformanceObserver(list => {
                    for (const e of list.getEntries()) {
                        if (!e.hadRecentInput) window.__clsValue += e.value;
                    }
                }).observe({ type: 'layout-shift', buffered: true });
            } catch(e) {}
        """)

        # Capture network responses for Cache/CDN test
        net_resps = []
        async def _on_response(resp):
            try:
                hdrs = await resp.all_headers()
                net_resps.append({'url': resp.url, 'headers': hdrs, 'status': resp.status})
            except Exception:
                pass
        page.on('response', lambda r: asyncio.ensure_future(_on_response(r)))

        print(f"\n⏳ Loading {url}…")
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        # Give images time to load so LCP can fire (LCP fires on largest image paint)
        await asyncio.sleep(5)
        print("  Page loaded. Running 10 tests…\n")

        ctx = ExtractionContext(
            page=page,
            url=url,
            html_content=await page.content(),
            network_responses=net_resps,
        )
        result = await EditorialSignalsExtractor().extract(ctx)
        await browser.close()
        return result


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'https://www.harpersbazaar.com/'
    if not url.startswith('http'):
        url = 'https://' + url

    result = asyncio.run(run_audit(url))
    _render_report(result, url)

    # Optionally dump full JSON
    if '--json' in sys.argv:
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
