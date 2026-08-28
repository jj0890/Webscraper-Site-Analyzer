"""
WaterCrawl Scout — lightweight pre-pass for Smart Nav page selection.

Crawls a site's surface (12 pages, depth 1) via the WaterCrawl API,
classifies each page by structural type, then selects the most diverse
set for deep-scanning. Falls back gracefully when the key is absent.

Usage:
    from scout import smart_nav_urls
    urls = await smart_nav_urls('https://stripe.com', max_pages=5)
    # → ['https://stripe.com', 'https://stripe.com/docs', ...]

Requires: WATERCRAWL_API_KEY in environment or .env file.
"""

import asyncio
import json
import os
import re
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse

import requests

_API_BASE = 'https://app.watercrawl.dev/api/v1/core'
_DEFAULT_LIMIT = 12          # pages to scout (keeps cost + latency low)
_DEFAULT_MAX_PAGES = 5       # pages returned for deep-scan
_POLL_TIMEOUT = 90           # seconds before we give up and return what we have
_POLL_INTERVAL = 3


# ── Page type classifier ──────────────────────────────────────────────────────

_TYPE_SIGNALS: Dict[str, list] = {
    'docs':      ['api/', 'docs/', 'reference/', 'guide/', 'sdk/', 'developer',
                  'getting started', 'quickstart', 'code block', '```', 'parameter',
                  'endpoint', 'request', 'response', 'authentication'],
    'blog':      ['blog/', '/articles/', '/news/', '/post/', '/stories/',
                  'min read', 'published', 'author:', 'by ', 'posted'],
    'product':   ['pricing', '/product/', '/features/', 'get started',
                  'sign up', 'try for free', 'per month', 'per seat'],
    'ecommerce': ['/shop/', '/store/', '/cart', '/checkout', 'add to bag',
                  'add to cart', '$', '£', '€', 'in stock'],
    'press':     ['press/', '/media/', 'press release', 'newsroom', 'announcement'],
    'search':    ['/search/', '?q=', '?query=', 'search results'],
    'landing':   ['hero', 'trusted by', 'enterprise', 'platform', 'solutions',
                  'how it works', 'get started for free'],
}

_PATH_TYPE_HINTS: Dict[str, str] = {
    r'/docs?/':    'docs',
    r'/blog/':     'blog',
    r'/news/':     'blog',
    r'/articles?/':'blog',
    r'/press/':    'press',
    r'/shop/':     'ecommerce',
    r'/store/':    'ecommerce',
    r'/search/':   'search',
    r'/pricing':   'product',
    r'/features?': 'product',
    r'/about':     'landing',
    r'/lp/':       'landing',
}


def _classify(url: str, title: str, markdown: str) -> str:
    path = urlparse(url).path.lower()
    text = (title + ' ' + markdown[:1500]).lower()

    # Path-first: most reliable signal
    for pattern, ptype in _PATH_TYPE_HINTS.items():
        if re.search(pattern, path):
            return ptype

    # Score against keyword buckets
    scores: Dict[str, int] = {}
    for ptype, signals in _TYPE_SIGNALS.items():
        score = sum(1 for s in signals if s in text or s in path)
        if score:
            scores[ptype] = score

    if scores:
        return max(scores, key=scores.get)

    # Root or very short path → landing
    if path in ('', '/', ) or len(path.strip('/').split('/')) == 1:
        return 'landing'

    return 'other'


# ── API helpers ───────────────────────────────────────────────────────────────

def _api_key() -> Optional[str]:
    key = os.environ.get('WATERCRAWL_API_KEY', '').strip()
    if not key:
        # Try loading from .env in the project root (same dir as this file)
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith('WATERCRAWL_API_KEY=') and not line.startswith('#'):
                    key = line.split('=', 1)[1].strip()
                    break
    return key or None


def _headers(key: str) -> dict:
    return {
        'X-API-Key': key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def _start_crawl(base_url: str, key: str, limit: int) -> Optional[str]:
    """Creates a WaterCrawl crawl request. Returns UUID or None on error."""
    payload = {
        'url': base_url,
        'options': {
            'spider_options': {
                'max_depth': 1,
                'page_limit': limit,
                'exclude_paths': [],
                'include_paths': [],
            },
            'page_options': {
                'only_main_content': True,
                'include_links': False,
                'wait_time': 500,
                'include_html': False,
                'timeout': 15000,
            },
        }
    }
    try:
        r = requests.post(
            f'{_API_BASE}/crawl-requests/',
            headers=_headers(key),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get('uuid')
    except Exception as e:
        print(f'   ⚠️  WaterCrawl: failed to start crawl — {e}')
        return None


def _stream_results(uuid: str, key: str) -> List[Dict]:
    """
    Streams SSE events from the WaterCrawl monitor endpoint.
    Returns a list of {url, metadata, markdown} dicts as they arrive.
    Stops when the crawl finishes or _POLL_TIMEOUT is exceeded.
    """
    pages = []
    deadline = time.time() + _POLL_TIMEOUT
    try:
        with requests.get(
            f'{_API_BASE}/crawl-requests/{uuid}/status/',
            headers=_headers(key),
            params={'prefetched': 'true'},
            stream=True,
            timeout=_POLL_TIMEOUT + 5,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if time.time() > deadline:
                    break
                if not raw:
                    continue
                line = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                if not line.startswith('data:'):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except (json.JSONDecodeError, ValueError):
                    continue

                etype = event.get('type')
                if etype == 'state':
                    status = event.get('data', {}).get('status', '')
                    if status in ('finished', 'failed', 'stopped'):
                        break
                elif etype == 'result':
                    data = event.get('data', {})
                    page_url = data.get('url', '')
                    result = data.get('result')
                    if isinstance(result, str):
                        # Not prefetched inline — fetch the GCS URL
                        try:
                            result = requests.get(result, timeout=10).json()
                        except Exception:
                            result = {}
                    if page_url and isinstance(result, dict):
                        pages.append({
                            'url':      page_url,
                            'metadata': result.get('metadata', {}),
                            'markdown': result.get('markdown', ''),
                        })
    except Exception as e:
        print(f'   ⚠️  WaterCrawl: stream error — {e}')
    return pages


def _select_diverse(pages: List[Dict], base_url: str, max_pages: int) -> List[str]:
    """
    Classifies each page, then picks one representative per type cluster.
    Within a type, prefers pages with more content.
    Always includes base_url as first entry.
    """
    if not pages:
        return [base_url]

    # Classify and score
    typed: Dict[str, list] = {}
    for p in pages:
        url   = p['url']
        title = p['metadata'].get('title', '') or p['metadata'].get('og:title', '')
        md    = p['markdown']
        ptype = _classify(url, title, md)
        content_score = len(md)
        typed.setdefault(ptype, []).append((content_score, url))

    # Sort each bucket by content length descending
    for bucket in typed.values():
        bucket.sort(reverse=True)

    # Interleave: one from each type in round-robin until we have max_pages
    type_order = ['docs', 'blog', 'product', 'ecommerce', 'press', 'landing', 'other']
    # Ensure types present in results come before absent types
    present = [t for t in type_order if t in typed] + [t for t in typed if t not in type_order]

    selected = [base_url]
    seen = {base_url}
    while len(selected) < max_pages:
        added = False
        for ptype in present:
            if len(selected) >= max_pages:
                break
            bucket = typed.get(ptype, [])
            for _, url in bucket:
                if url not in seen:
                    selected.append(url)
                    seen.add(url)
                    added = True
                    break
        if not added:
            break

    return selected


# ── Public async interface ────────────────────────────────────────────────────

async def smart_nav_urls(
    base_url: str,
    limit: int = _DEFAULT_LIMIT,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> Optional[List[str]]:
    """
    Returns a diversity-optimised list of URLs to deep-scan, or None if
    WaterCrawl is unavailable (caller falls back to nav-link discovery).

    Args:
        base_url:  Root URL of the site to scout.
        limit:     How many pages WaterCrawl crawls (default 12).
        max_pages: How many URLs to return (default 5).
    """
    key = _api_key()
    if not key:
        return None

    print(f'   🌊 WaterCrawl scout: crawling {limit} pages…')

    # Run blocking I/O in a thread so the async loop stays free
    uuid = await asyncio.to_thread(_start_crawl, base_url, key, limit)
    if not uuid:
        return None

    pages = await asyncio.to_thread(_stream_results, uuid, key)
    if not pages:
        print('   ⚠️  WaterCrawl: no pages returned, falling back')
        return None

    selected = _select_diverse(pages, base_url, max_pages)

    # Log what we found
    type_summary: Dict[str, int] = {}
    for p in pages:
        title = p['metadata'].get('title', '') or ''
        md    = p['markdown']
        ptype = _classify(p['url'], title, md)
        type_summary[ptype] = type_summary.get(ptype, 0) + 1

    summary_str = ', '.join(f'{v}× {k}' for k, v in sorted(type_summary.items()))
    print(f'   🌊 WaterCrawl: {len(pages)} pages — {summary_str}')
    for url in selected:
        print(f'   📍 scout → {url}')

    return selected
