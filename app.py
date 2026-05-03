"""
Web Intelligence Dashboard - Final Version

Features:
- 20+ metrics extraction (layout, typography, colors, animations, accessibility, etc.)
- Article content extraction with confidence scoring
- Markdown export
- Debug view with network traces
- Analytics dashboard
- Figma-style UI
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import asyncio
from pathlib import Path
# Lazy imports — patchright hangs intermittently at import time
# These modules are imported on first use instead of at startup
_DeepEvidenceEngine = None
_ComponentRipper = None
_ComputedStyleExtractor = None

def _get_engine_class():
    global _DeepEvidenceEngine
    if _DeepEvidenceEngine is None:
        from deep_evidence_engine import DeepEvidenceEngine
        _DeepEvidenceEngine = DeepEvidenceEngine
    return _DeepEvidenceEngine

def _get_ripper_class():
    global _ComponentRipper
    if _ComponentRipper is None:
        from component_ripper import ComponentRipper
        _ComponentRipper = ComponentRipper
    return _ComponentRipper

def _get_style_extractor_class():
    global _ComputedStyleExtractor
    if _ComputedStyleExtractor is None:
        from computed_style_extractor import ComputedStyleExtractor
        _ComputedStyleExtractor = ComputedStyleExtractor
    return _ComputedStyleExtractor
import json
import os
import traceback
import logging
from datetime import datetime
from urllib.parse import urlparse
import ipaddress
import socket
# import anthropic  # hangs on this system — chat feature disabled
ANTHROPIC_AVAILABLE = False

# Wizard configuration
WIZARD_MAX_PAGES = 5  # Max pages for "Scan All" diversity selection

# Evidence cache — stores last scan per URL so compare-sites can reuse
# TTL: entries older than 10 minutes are considered stale
_evidence_cache = {}  # {url: {'evidence': {...}, 'timestamp': float}}
_CACHE_TTL = 600  # 10 minutes

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max request size

# Restrict CORS to localhost origins only
CORS(app, origins=[
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
])


# ---------------------------------------------------------------------------
# Security: URL validation to prevent SSRF
# ---------------------------------------------------------------------------
BLOCKED_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),       # Loopback
    ipaddress.ip_network('10.0.0.0/8'),         # Private A
    ipaddress.ip_network('172.16.0.0/12'),      # Private B
    ipaddress.ip_network('192.168.0.0/16'),     # Private C
    ipaddress.ip_network('169.254.0.0/16'),     # Link-local / AWS metadata
    ipaddress.ip_network('0.0.0.0/8'),          # Current network
    ipaddress.ip_network('::1/128'),            # IPv6 loopback
    ipaddress.ip_network('fc00::/7'),           # IPv6 private
    ipaddress.ip_network('fe80::/10'),          # IPv6 link-local
]


def validate_url(url):
    """
    Validate and normalize a user-supplied URL.
    Returns (normalized_url, error_message). error_message is None if valid.
    """
    if not url or not isinstance(url, str):
        return None, 'URL is required'

    url = url.strip()

    # Add protocol if missing
    if not url.startswith('http'):
        url = f'https://{url}'

    try:
        parsed = urlparse(url)
    except Exception:
        return None, 'Invalid URL format'

    # Scheme must be http or https
    if parsed.scheme not in ('http', 'https'):
        return None, f'Invalid URL scheme: {parsed.scheme}. Only http and https are allowed.'

    # Must have a hostname
    hostname = parsed.hostname
    if not hostname:
        return None, 'URL must include a hostname'

    # Block file://, data://, javascript:// etc. (already handled by scheme check)
    # Block obviously dangerous hostnames
    if hostname in ('localhost', '0.0.0.0'):
        return None, 'Scanning localhost or 0.0.0.0 is not allowed'

    # Resolve hostname and check against blocked IP ranges
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            for blocked in BLOCKED_IP_RANGES:
                if ip in blocked:
                    return None, f'URL resolves to a private/reserved IP address ({ip}). Scanning internal networks is not allowed.'
    except socket.gaierror:
        return None, f'Could not resolve hostname: {hostname}'

    return url, None


# ---------------------------------------------------------------------------
# Utility: run async coroutine in a fresh event loop
# ---------------------------------------------------------------------------
def run_async(coro):
    """Run an async coroutine in a new event loop. Returns the result."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Initialize Anthropic client (disabled if import failed — hangs on this system)
anthropic_client = None  # anthropic disabled (hangs on import on this system)


@app.route('/')
def index():
    """Main dashboard"""
    return render_template('web_dashboard.html')


@app.route('/ripper')
def ripper():
    """Component Ripper interface"""
    return render_template('component_ripper_ui.html')


@app.route('/glossary')
def glossary():
    """Glossary and metric explanations"""
    return render_template('glossary.html')


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})


@app.route('/api/deep-scan', methods=['POST'])
def deep_scan():
    """Run deep evidence extraction with 20+ metrics"""
    data = request.json
    site_url = data.get('site_url')
    analysis_mode = data.get('analysis_mode', 'single')  # 'single' | 'smart-nav' | 'multi-template'

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔍 DEEP SCAN: {site_url}")
        print(f" 📊 Mode: {analysis_mode}")
        print('='*70)

        discovery_method = data.get('discovery_method', 'auto')
        engine = _get_engine_class()(site_url, analysis_mode=analysis_mode, discovery_method=discovery_method)
        evidence = run_async(engine.extract_all())

        print("\n✅ Deep scan complete!")
        print(f"   Extracted {len(evidence)} metric categories")

        # Clean up evidence (remove None values, errors, unawaited coroutines)
        import inspect
        cleaned_evidence = {}
        for k, v in evidence.items():
            if v is None:
                continue
            if inspect.iscoroutine(v):
                print(f"   ⚠️  Skipping coroutine in evidence['{k}'] — likely missing await")
                continue
            # Check nested dicts for coroutines
            if isinstance(v, dict):
                cleaned_v = {}
                for k2, v2 in v.items():
                    if inspect.iscoroutine(v2):
                        print(f"   ⚠️  Skipping coroutine in evidence['{k}']['{k2}'] — likely missing await")
                    else:
                        cleaned_v[k2] = v2
                cleaned_evidence[k] = cleaned_v
            else:
                cleaned_evidence[k] = v

        # Cache evidence for compare-sites reuse
        import time as _time
        _evidence_cache[site_url] = {'evidence': cleaned_evidence, 'timestamp': _time.time()}

        # Persist results to ~/.webscraper/results/ for LLM retrieval
        result_file = None
        try:
            results_dir = os.path.expanduser('~/.webscraper/results')
            os.makedirs(results_dir, exist_ok=True)
            domain = urlparse(site_url).netloc.replace('.', '_').replace(':', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{domain}_{timestamp}.json"
            filepath = os.path.join(results_dir, filename)
            with open(filepath, 'w') as f:
                json.dump({'url': site_url, 'mode': analysis_mode, 'evidence': cleaned_evidence}, f, default=str)
            result_file = filepath
            print(f"   💾 Results saved to {filepath}")
        except Exception as save_err:
            print(f"   ⚠️  Could not save results: {save_err}")

        return jsonify({
            'success': True,
            'evidence': cleaned_evidence,
            'result_file': result_file
        })

    except TimeoutError as e:
        print(f"\n⚠️  Timeout error: {str(e)}")
        return jsonify({
            'error': 'Site took too long to load. Try a lighter page or increase timeout.',
            'suggestion': 'Try analyzing a specific page like /about or /contact instead of the homepage.'
        }), 408

    except Exception as e:
        logger.error(f"Error during scan: {e}", exc_info=True)
        err_type = type(e).__name__
        err_msg = str(e)[:200]
        # Give user a more specific error without leaking internal paths
        if 'timeout' in err_msg.lower() or 'Timeout' in err_type:
            hint = 'The page took too long to respond. Try a lighter page.'
        elif 'net::ERR' in err_msg or 'Navigation' in err_msg:
            hint = 'Could not reach the site. Check the URL and try again.'
        elif 'browser' in err_msg.lower() or 'chromium' in err_msg.lower():
            hint = 'Browser engine error. Try restarting the server.'
        else:
            hint = 'The site may be blocking automated access or is temporarily unavailable.'
        return jsonify({
            'error': f'Scan failed: {hint}',
            'detail': f'{err_type}: {err_msg}',
            'suggestion': 'Try a different page or check server logs for details.'
        }), 500


@app.route('/api/rip-component', methods=['POST'])
def rip_component():
    """
    Component Ripper - Extract exact blueprint of a specific component

    Request body:
    {
        "site_url": "https://ssense.com/en-us/men",
        "selector": ".product-grid",  # Optional - auto-detect if not provided
        "auth_state": null,  # Optional - path to saved auth state
        "include_states": false,  # Optional - capture hover/focus state deltas
        "output_format": "json"  # Optional - 'json' or 'figma' (Tailwind JSX markdown)
    }
    """
    data = request.json
    site_url = data.get('site_url')
    selector = data.get('selector')  # Optional — use "auto" or omit for auto-detect
    if selector and selector.lower() == 'auto':
        selector = None
    auth_state = data.get('auth_state')  # Optional
    include_states = data.get('include_states', False)
    output_format = data.get('output_format', 'json')
    pre_action = data.get('pre_action')  # Optional — interact before ripping

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔬 COMPONENT RIPPER: {site_url}")
        if selector:
            print(f"    Target: {selector}")
        else:
            print(f"    Mode: Auto-detect sections")
        if pre_action:
            print(f"    Pre-action: {pre_action.get('type','click')} → {pre_action.get('target','')}")
        if include_states:
            print(f"    States: enabled")
        if output_format == 'figma':
            print(f"    Output: Figma-compatible markdown")
        print('='*70)

        ripper = _get_ripper_class()(site_url, selector)
        blueprint = run_async(ripper.rip(auth_state, include_states=include_states,
                                         output_format=output_format, pre_action=pre_action))

        print("\n✅ Component rip complete!")

        return jsonify({
            'success': True,
            'blueprint': blueprint
        })

    except Exception as e:
        logger.error(f"Error during component rip: {e}", exc_info=True)
        return jsonify({
            'error': 'Component extraction failed. Check if the selector exists on the page.',
            'suggestion': 'Try a more specific CSS selector or use auto-detect mode.'
        }), 500


@app.route('/api/discover-components', methods=['POST'])
def discover_components():
    """
    Component Discovery — scan a page and return a visual inventory of all
    detectable components with bounding boxes, screenshots, and labels.

    Request body:
    {
        "site_url": "https://polyesterzine.com"
    }
    """
    data = request.json
    site_url = data.get('site_url')

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔍 COMPONENT DISCOVERY: {site_url}")
        print('='*70)

        ripper = _get_ripper_class()(site_url)
        result = run_async(ripper.discover_components())

        print(f"\n✅ Discovery complete: {result.get('total', 0)} components found")

        return jsonify({
            'success': True,
            **result
        })

    except Exception as e:
        logger.error(f"Error during component discovery: {e}", exc_info=True)
        return jsonify({
            'error': 'Component discovery failed.',
            'detail': str(e)
        }), 500


@app.route('/api/auto-rip', methods=['POST'])
def auto_rip():
    """
    Auto-rip top N components — discover all components, then rip the highest-priority ones.

    Request body:
    {
        "site_url": "https://stripe.com",
        "count": 5
    }
    """
    data = request.json
    site_url = data.get('site_url')
    count = min(data.get('count', 5), 10)  # Cap at 10

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" ⚡ AUTO-RIP TOP {count}: {site_url}")
        print('='*70)

        ripper = _get_ripper_class()(site_url)
        result = run_async(ripper.auto_rip_top_n(n=count))

        print(f"\n✅ Auto-rip complete: {result.get('total_ripped', 0)}/{result.get('total_discovered', 0)} components ripped")

        return jsonify({
            'success': True,
            **result
        })

    except Exception as e:
        logger.error(f"Error during auto-rip: {e}", exc_info=True)
        return jsonify({
            'error': 'Auto-rip failed.',
            'detail': str(e)
        }), 500


@app.route('/api/search-components', methods=['POST'])
def search_components():
    """
    Search for components containing specific text using CSS Custom Highlight API.

    Request body:
    {
        "site_url": "https://stripe.com",
        "search_text": "Sign up"
    }
    """
    data = request.json
    site_url = data.get('site_url')
    search_text = data.get('search_text', '').strip()

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    if not search_text:
        return jsonify({'error': 'search_text is required'}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔍 COMPONENT TEXT SEARCH: '{search_text}' on {site_url}")
        print('='*70)

        ripper = _get_ripper_class()(site_url)
        result = run_async(ripper.search_components_by_text(search_text))

        print(f"\n✅ Found {result.get('total', 0)} components matching '{search_text}'")

        return jsonify({
            'success': True,
            **result
        })

    except Exception as e:
        logger.error(f"Error during component search: {e}", exc_info=True)
        return jsonify({
            'error': 'Component search failed.',
            'detail': str(e)
        }), 500


@app.route('/api/extract-icons', methods=['POST'])
def extract_icons():
    """
    Extract all SVG icons from a site.

    Detects three patterns:
      - Symbol sprites (<symbol id="..."> + <use href="#...">)
      - Standalone inline SVGs (deduplicated by path data)
      - External SVG file references (<img src="*.svg">)

    Request body:
    {
        "site_url": "https://soundcloud.com"
    }

    Returns:
    {
        "success": true,
        "total": 42,
        "method": "symbol_sprite",
        "symbols": [{"id": "icon-play", "name": "play", "svg": "...", "usage_count": 14, "viewBox": "0 0 24 24"}],
        "inline": [...],
        "external": [...]
    }
    """
    data = request.json
    site_url = data.get('site_url')

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🎨 SVG ICON EXTRACTION: {site_url}")
        print('='*70)

        ripper = _get_ripper_class()(site_url)
        catalog = run_async(ripper.extract_svg_icons())

        print(f"\n✅ Found {catalog.get('total', 0)} icons "
              f"({len(catalog.get('symbols', []))} symbols, "
              f"{len(catalog.get('inline', []))} inline, "
              f"{len(catalog.get('external', []))} external)")
        print(f"   Method: {catalog.get('method')}")

        return jsonify({
            'success': True,
            **catalog
        })

    except Exception as e:
        logger.error(f"Error during icon extraction: {e}", exc_info=True)
        return jsonify({
            'error': 'Icon extraction failed.',
            'detail': str(e)
        }), 500


@app.route('/api/figma-html', methods=['GET'])
def figma_html():
    """
    Serve a ripped component as self-contained HTML for html.to.design import.

    Usage: http://localhost:8080/api/figma-html?url=https://pigeonsandplanes.com&selector=header

    Paste this URL directly into the html.to.design Figma plugin "Web" tab.
    """
    site_url = request.args.get('url')
    selector = request.args.get('selector', 'header')

    if not site_url:
        return '<html><body><p>Usage: /api/figma-html?url=https://example.com&selector=header</p></body></html>', 400

    site_url, url_error = validate_url(site_url)
    if url_error:
        return f'<html><body><p>Error: {url_error}</p></body></html>', 400

    try:
        ripper = _get_ripper_class()(site_url, selector)
        blueprint = run_async(ripper.rip(include_states=True, output_format='figma'))
        html = blueprint.get('figma_html', '<html><body><p>No HTML generated</p></body></html>')
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        logger.error(f"Figma HTML generation failed: {e}", exc_info=True)
        return f'<html><body><p>Error: {e}</p></body></html>', 500


@app.route('/api/rip-component/cross-site', methods=['POST'])
def rip_component_cross_site():
    """
    Cross-site component search — uses Cloudflare crawl to find a CSS selector
    pattern across multiple pages without Playwright per-page overhead.

    Request body:
    {
        "site_url": "https://stripe.com",
        "selector": "nav.site-nav"
    }
    """
    from cloudflare_crawl import CloudflareCrawler, is_cloudflare_available
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse
    import re

    if not is_cloudflare_available():
        return jsonify({
            'error': 'Cross-site search requires Cloudflare. Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.',
            'available': False
        }), 503

    data = request.json
    site_url = data.get('site_url')
    selector = data.get('selector')

    if not site_url or not selector:
        return jsonify({'error': 'site_url and selector are required'}), 400

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🌐 CROSS-SITE COMPONENT SEARCH")
        print(f"    Site: {site_url}")
        print(f"    Selector: {selector}")
        print('='*70)

        # Step 1: Crawl the site for HTML content
        crawler = CloudflareCrawler()
        result = run_async(crawler.crawl(
            site_url,
            limit=30,
            depth=2,
            formats=['html'],
            render=True,
            timeout=120
        ))

        pages = result.get('pages', [])
        if not pages:
            return jsonify({'error': 'Cloudflare crawl returned no pages', 'found_on': 0, 'total_pages': 0})

        # Step 2: Parse selector into BeautifulSoup search args
        # Convert CSS selector to BS4-compatible search
        # Supports: tag, .class, #id, tag.class, .class1.class2
        def parse_selector_for_bs4(sel):
            """Convert a CSS selector to BeautifulSoup find() arguments."""
            sel = sel.strip()
            # Extract tag
            tag_match = re.match(r'^([a-zA-Z][a-zA-Z0-9]*)', sel)
            tag = tag_match.group(1) if tag_match else None

            # Extract id
            id_match = re.search(r'#([a-zA-Z0-9_-]+)', sel)
            el_id = id_match.group(1) if id_match else None

            # Extract classes
            classes = re.findall(r'\.([a-zA-Z0-9_-]+)', sel)

            attrs = {}
            if el_id:
                attrs['id'] = el_id
            if classes:
                # For multiple classes, use a function match
                attrs['class'] = lambda x: x and all(c in (x if isinstance(x, list) else x.split()) for c in classes)

            return tag, attrs

        tag, attrs = parse_selector_for_bs4(selector)
        base_host = urlparse(site_url).hostname

        matches = []
        not_found = []

        for page in pages:
            page_url = page.get('url') or page.get('sourceURL', '')
            html_content = page.get('content') or page.get('html', '')
            if not html_content:
                continue

            # Only search pages on the same domain
            try:
                page_host = urlparse(page_url).hostname
                if page_host and base_host and page_host != base_host:
                    continue
            except Exception:
                pass

            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                found_elements = soup.find_all(tag, attrs) if tag else soup.find_all(attrs=attrs)

                page_path = urlparse(page_url).path or '/'

                if found_elements:
                    # Check for variants — are there style differences?
                    variant_note = ''
                    if len(found_elements) > 1:
                        variant_note = f'{len(found_elements)} instances'

                    matches.append({
                        'url': page_url,
                        'path': page_path,
                        'count': len(found_elements),
                        'variant_note': variant_note
                    })
                else:
                    not_found.append(page_path)
            except Exception as e:
                logger.debug(f"BS4 parse error on {page_url}: {e}")
                continue

        total_pages = len(matches) + len(not_found)
        found_on = len(matches)

        # Step 3: Classify the component
        if total_pages == 0:
            classification = 'unknown'
            classification_reason = 'No pages could be analyzed'
        elif found_on / max(total_pages, 1) >= 0.8:
            classification = 'global'
            classification_reason = f'Found on {found_on}/{total_pages} pages — likely a site-wide component (nav, footer, header)'
        elif found_on / max(total_pages, 1) >= 0.4:
            classification = 'common'
            classification_reason = f'Found on {found_on}/{total_pages} pages — shared across many but not all pages'
        elif found_on >= 2:
            classification = 'section-specific'
            classification_reason = f'Found on {found_on}/{total_pages} pages — appears in specific site sections'
        else:
            classification = 'page-specific'
            classification_reason = f'Found on {found_on}/{total_pages} pages — unique to specific page(s)'

        print(f"\n✅ Cross-site search complete: {found_on}/{total_pages} pages contain '{selector}'")
        print(f"   Classification: {classification}")

        return jsonify({
            'success': True,
            'selector': selector,
            'found_on': found_on,
            'total_pages': total_pages,
            'classification': classification,
            'classification_reason': classification_reason,
            'matches': matches,
            'not_found_sample': not_found[:10]
        })

    except Exception as e:
        logger.error(f"Cross-site search failed: {e}", exc_info=True)
        return jsonify({'error': f'Cross-site search failed: {str(e)}'}), 500


@app.route('/api/extract-styles', methods=['POST'])
def extract_styles():
    """
    Extract computed styles from live elements

    Request body:
    {
        "site_url": "https://nts.live",
        "selector": ".channel-card",  # CSS selector to target
        "mode": "critical"  # "critical" or "full"
    }

    Returns actual pixel values instead of class names:
    - padding: "24px 32px" (not "p-6")
    - background: "#f7f7f7" (not "bg-gray-100")
    """
    data = request.json
    site_url = data.get('site_url')
    selector = data.get('selector', 'nav')  # Default to nav
    mode = data.get('mode', 'critical')  # critical or full

    if not selector:
        return jsonify({'error': 'CSS selector required'}), 400

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🎨 COMPUTED STYLE EXTRACTION: {site_url}")
        print(f"    Selector: {selector}")
        print(f"    Mode: {mode}")
        print('='*70)

        async def extract():
            from patchright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                page.set_default_timeout(60000)

                # Load page
                await page.goto(site_url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)

                # Create extractor
                extractor = _get_style_extractor_class()(page)

                # Extract styles based on mode
                if mode == 'critical':
                    result = await extractor.extract_critical_values(selector)
                else:
                    result = await extractor.extract_computed_styles(selector)

                # Generate CSS if found
                if result.get('found'):
                    css = extractor.generate_copy_paste_css(result)
                    result['generated_css'] = css

                await browser.close()
                return result

        result = run_async(extract())

        print("\n✅ Style extraction complete!")

        return jsonify({
            'success': True,
            'styles': result
        })

    except Exception as e:
        logger.error(f"Error during style extraction: {e}", exc_info=True)
        return jsonify({
            'error': 'Style extraction failed. Check if the selector exists on the page.',
            'suggestion': 'Try inspecting the page first to verify the selector.'
        }), 500


@app.route('/api/cloudflare-crawl', methods=['POST'])
def cloudflare_crawl():
    """
    Crawl a website using Cloudflare Browser Rendering /crawl API.

    Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN env vars.

    Request body:
    {
        "site_url": "https://stripe.com",
        "limit": 20,        // max pages (default 10)
        "depth": 3,          // max link depth (default 2)
        "formats": ["markdown"],  // html, markdown, json
        "render": true       // use headless browser (default true)
    }

    Returns:
    {
        "success": true,
        "crawl_id": "abc123",
        "status": "completed",
        "pages": [...],
        "urls": ["https://stripe.com/docs", ...],
        "total": 20
    }
    """
    from cloudflare_crawl import CloudflareCrawler, CloudflareNotConfigured, is_cloudflare_available

    if not is_cloudflare_available():
        return jsonify({
            'error': 'Cloudflare not configured. Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN environment variables.',
            'available': False
        }), 503

    data = request.json
    site_url = data.get('site_url')
    if not site_url:
        return jsonify({'error': 'site_url required'}), 400

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    limit = min(int(data.get('limit', 10)), 1000)  # Cap at 1000 for safety
    depth = min(int(data.get('depth', 2)), 10)
    formats = data.get('formats', ['markdown'])
    render = data.get('render', True)

    try:
        crawler = CloudflareCrawler()
        result = run_async(crawler.crawl(
            site_url,
            limit=limit,
            depth=depth,
            formats=formats,
            render=render,
            timeout=300
        ))

        response = {
            'success': True,
            'crawl_id': result.get('crawl_id', ''),
            'status': result.get('status', 'unknown'),
            'pages': result.get('pages', [])[:50],  # Cap response size
            'urls': result.get('urls', []),
            'total': result.get('total', 0)
        }

        # Optional topology analysis on crawled URLs
        if data.get('analyze_topology', False) and result.get('urls'):
            from site_topology import SiteTopologyAnalyzer
            topo = SiteTopologyAnalyzer()
            response['topology'] = topo.analyze(result['urls'], site_url, url_source='cloudflare')

        return jsonify(response)

    except CloudflareNotConfigured as e:
        return jsonify({'error': str(e), 'available': False}), 503
    except Exception as e:
        logger.error(f"Cloudflare crawl failed: {e}", exc_info=True)
        return jsonify({'error': f'Cloudflare crawl failed: {str(e)[:200]}'}), 500


@app.route('/api/site-topology', methods=['POST'])
def site_topology():
    """
    Analyze site topology from discovered URLs.

    Request body:
    {
        "site_url": "https://stripe.com",
        "urls": [...],              // Optional: pre-discovered URL list
        "discovery_method": "auto"  // 'auto' | 'cloudflare' | 'nav'
    }

    If urls not provided, discovers them first via nav scraping
    (or Cloudflare if configured and discovery_method allows).
    """
    data = request.json
    site_url = data.get('site_url')
    if not site_url:
        return jsonify({'error': 'site_url required'}), 400

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    # Use pre-supplied URLs or discover them
    urls = data.get('urls', [])
    url_source = 'provided'

    if not urls:
        discovery_method = data.get('discovery_method', 'auto')

        # Try Cloudflare first
        if discovery_method in ('cloudflare', 'auto'):
            try:
                from cloudflare_crawl import CloudflareCrawler, is_cloudflare_available
                if is_cloudflare_available():
                    crawler = CloudflareCrawler()
                    urls = run_async(crawler.discover_urls(site_url, limit=100, depth=3))
                    url_source = 'cloudflare'
            except Exception as e:
                logger.warning(f"Cloudflare topology discovery failed: {e}")

        # Fall back to nav scraping
        if not urls:
            try:
                engine = _get_engine_class()(site_url, analysis_mode='single')
                result = run_async(engine._quick_discover(site_url))
                urls = result if isinstance(result, list) else result.get('all', [])
                url_source = 'nav_discovery'
            except Exception as e:
                return jsonify({'error': f'URL discovery failed: {str(e)[:200]}'}), 500

    if len(urls) < 3:
        return jsonify({
            'success': False,
            'error': f'Only {len(urls)} URLs found — need at least 3 for topology',
            'urls_found': len(urls)
        }), 400

    from site_topology import SiteTopologyAnalyzer
    topo = SiteTopologyAnalyzer()
    topology = topo.analyze(urls, site_url, url_source=url_source)

    return jsonify({
        'success': True,
        'topology': topology,
        'urls_analyzed': len(urls),
        'url_source': url_source
    })


@app.route('/api/discover-urls', methods=['POST'])
def discover_urls():
    """
    Extract all links from a page for LLM navigation planning.
    Supports interactive discovery (clicking dropdowns/menus).

    Request body:
    {
        "site_url": "https://pi.fyi",
        "interactive": true   // optional — clicks dropdowns to discover hidden links
    }

    Returns:
    {
        "base_url": "https://pi.fyi",
        "discovered_links": { navigation: [...], articles: [...], sections: [...], all: [...] },
        "interactive_discovery": {  // only when interactive: true
            "interaction_log": [...],
            "total_static": 32,
            "total_interactive": 14,
            "total_unique": 42
        }
    }
    """
    data = request.json
    site_url = data.get('site_url')
    interactive = data.get('interactive', False)

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔗 URL DISCOVERY: {site_url}")
        print(f" 🔍 Interactive: {interactive}")
        print('='*70)

        async def discover():
            from patchright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                page.set_default_timeout(60000)

                # Load page
                await page.goto(site_url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)

                # Create engine to use link discovery
                engine = _get_engine_class()(site_url)

                if interactive:
                    # Full interactive discovery — clicks dropdowns, hamburgers, etc.
                    result = await engine._discover_interactive_links(page, site_url)
                    # Re-categorize all_links into navigation/articles/sections buckets
                    static_links = await engine._discover_links(page, site_url)
                    # Merge: static_links has categorized buckets, interactive adds extra
                    interactive_urls = {l['url'] if isinstance(l, dict) else l for l in result.get('interactive_links', [])}
                    # Add interactive-only links to appropriate bucket (default: navigation)
                    for link in result.get('interactive_links', []):
                        url = link['url'] if isinstance(link, dict) else link
                        text = link.get('text', '') if isinstance(link, dict) else ''
                        if url not in {l['url'] if isinstance(l, dict) else l for l in static_links.get('all', [])}:
                            static_links.setdefault('navigation', []).append({
                                'url': url, 'text': text, 'source': 'interactive'
                            })
                            static_links.setdefault('all', []).append({
                                'url': url, 'text': text, 'source': 'interactive'
                            })

                    await browser.close()
                    return {
                        'links': static_links,
                        'interactive_discovery': {
                            'interaction_log': result.get('interaction_log', []),
                            'total_static': result.get('total_static', 0),
                            'total_interactive': result.get('total_interactive', 0),
                            'total_unique': result.get('total_unique', 0),
                        }
                    }
                else:
                    links = await engine._discover_links(page, site_url)
                    await browser.close()
                    return {'links': links, 'interactive_discovery': None}

        result = run_async(discover())
        links = result['links']
        interactive_meta = result['interactive_discovery']

        total = len(links.get('all', []))
        print(f"\n✅ Found {total} total links")
        print(f"   Navigation: {len(links.get('navigation', []))}")
        print(f"   Articles: {len(links.get('articles', []))}")
        print(f"   Sections: {len(links.get('sections', []))}")
        if interactive_meta:
            print(f"   Interactive: {interactive_meta['total_interactive']} from dropdowns")

        response = {
            'success': True,
            'base_url': site_url,
            'discovered_links': links,
        }
        if interactive_meta:
            response['interactive_discovery'] = interactive_meta

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error during URL discovery: {e}", exc_info=True)
        return jsonify({
            'error': 'URL discovery failed. The site may be blocking automated access.',
            'suggestion': 'Try a different page or check server logs.'
        }), 500


@app.route('/api/score-urls', methods=['POST'])
def score_urls():
    """
    Server-side URL diversity scoring for the wizard's "Scan All" feature.

    Request body:
    {
        "site_url": "https://stripe.com",
        "urls": ["https://stripe.com/payments", "https://stripe.com/docs", ...],
        "max_pages": 5  // optional, defaults to WIZARD_MAX_PAGES
    }

    Returns:
    {
        "success": true,
        "selected_urls": {"home": "https://stripe.com", "page_1": "...", ...}
    }
    """
    data = request.json
    site_url = data.get('site_url')
    urls = data.get('urls', [])
    max_pages = data.get('max_pages', WIZARD_MAX_PAGES)

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    if not urls or len(urls) < 2:
        return jsonify({'error': 'Need at least 2 URLs to score'}), 400

    # Cap max_pages to a reasonable limit
    max_pages = min(int(max_pages), 10)

    try:
        engine = _get_engine_class()(site_url, analysis_mode='interactive')
        selected = engine._select_diverse_pages(urls, site_url, max_pages=max_pages)
        return jsonify({'success': True, 'selected_urls': selected})
    except Exception as e:
        logger.error(f"Error during URL scoring: {e}", exc_info=True)
        return jsonify({'error': 'URL scoring failed.'}), 500


@app.route('/api/multi-scan', methods=['POST'])
def multi_scan():
    """
    Analyze user-selected pages (for Interactive Discovery mode).

    Request body:
    {
        "site_url": "https://stripe.com",
        "urls": ["https://stripe.com", "https://stripe.com/payments", ...]
    }

    Returns:
    {
        "success": true,
        "evidence": { ...multi-page synthesis... }
    }
    """
    data = request.json
    site_url = data.get('site_url')
    urls = data.get('urls', [])
    analysis_focus = data.get('analysis_focus', 'full')  # 'full'|'design'|'interaction'|'layout'

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    if not urls:
        return jsonify({'error': 'URLs array required (at least 1 URL)'}), 400

    # Validate each URL and cap at 10
    urls = urls[:10]
    validated_urls = []
    for u in urls:
        clean_url, err = validate_url(u)
        if err:
            return jsonify({'error': f'Invalid URL in list: {u} — {err}'}), 400
        validated_urls.append(clean_url)

    try:
        print(f"\n{'='*70}")
        print(f" 🎯 MULTI-SCAN: {site_url}")
        print(f" 📄 Pages: {len(validated_urls)}  Focus: {analysis_focus}")
        print('='*70)

        engine = _get_engine_class()(site_url, analysis_mode='interactive')
        evidence = run_async(engine.multi_scan(validated_urls, analysis_focus=analysis_focus))
        evidence['analysis_focus'] = analysis_focus  # Pass through to frontend

        print(f"\n✅ Multi-scan complete!")
        print(f"   Extracted {len(evidence)} evidence keys")

        cleaned_evidence = {k: v for k, v in evidence.items() if v is not None}

        return jsonify({
            'success': True,
            'evidence': cleaned_evidence
        })

    except TimeoutError as e:
        logger.error(f"Timeout during multi-scan: {e}")
        return jsonify({
            'error': 'Multi-scan timed out. Try fewer pages or simpler sites.',
        }), 504

    except Exception as e:
        logger.error(f"Error during multi-scan: {e}", exc_info=True)
        return jsonify({
            'error': 'Multi-scan failed. Check server logs for details.',
            'suggestion': 'Try fewer pages or check if the site blocks automated access.'
        }), 500


@app.route('/api/batch-analyze', methods=['POST'])
def batch_analyze():
    """
    Analyze multiple URLs in one request (for LLMs)

    Request body:
    {
        "urls": ["https://pi.fyi", "https://pi.fyi/editorial", "https://pi.fyi/p/article"]
    }

    Returns:
    {
        "results": {
            "https://pi.fyi": { ...evidence... },
            "https://pi.fyi/editorial": { ...evidence... }
        }
    }
    """
    data = request.json
    urls = data.get('urls', [])

    if not urls:
        return jsonify({'error': 'URLs array required'}), 400

    # Limit to 5 URLs to prevent overload
    urls = urls[:5]

    # Validate all URLs upfront
    validated_urls = []
    for url in urls:
        valid_url, url_error = validate_url(url)
        if url_error:
            return jsonify({'error': f'Invalid URL "{url}": {url_error}'}), 400
        validated_urls.append(valid_url)

    try:
        print(f"\n{'='*70}")
        print(f" 📊 BATCH ANALYSIS: {len(validated_urls)} URLs")
        print('='*70)

        async def analyze_batch():
            results = {}

            for i, url in enumerate(validated_urls, 1):
                print(f"\n[{i}/{len(validated_urls)}] Analyzing: {url}")

                try:
                    engine = _get_engine_class()(url)
                    evidence = await engine.extract_all()
                    results[url] = evidence
                    print(f"   ✅ Complete")
                except Exception as e:
                    print(f"   ❌ Failed: {str(e)[:100]}")
                    results[url] = {
                        'error': 'Analysis failed for this URL',
                        'success': False
                    }

            return results

        results = run_async(analyze_batch())

        print(f"\n✅ Batch analysis complete!")
        print(f"   Successful: {sum(1 for r in results.values() if not r.get('error'))}/{len(validated_urls)}")

        return jsonify({
            'success': True,
            'results': results
        })

    except Exception as e:
        logger.error(f"Error during batch analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Batch analysis failed. Check server logs for details.'
        }), 500


@app.route('/api/export-markdown', methods=['POST'])
def export_markdown():
    """Export analysis as markdown"""
    data = request.json
    evidence = data.get('evidence')

    if not evidence:
        return jsonify({'error': 'No evidence data provided'}), 400

    # Generate markdown
    markdown = generate_markdown_report(evidence)

    return jsonify({
        'success': True,
        'markdown': markdown
    })


def generate_markdown_report(evidence):
    """Generate comprehensive markdown report covering all evidence sections"""
    md = "# Website Analysis Report\n\n"
    md += f"**URL:** {evidence.get('meta_info', {}).get('url', 'Unknown')}  \n"
    md += f"**Scanned:** {evidence.get('meta_info', {}).get('timestamp', 'N/A')}  \n"
    md += f"**Access Strategy:** {evidence.get('access_strategy', 'patchright')}  \n\n"

    # --- Summary table ---
    md += "## Summary Dashboard\n\n"
    md += "| Metric | Pattern | Confidence |\n|--------|---------|------------|\n"
    summary_keys = [
        ('Typography', 'typography'), ('Colors', 'colors'), ('Spacing', 'spacing_scale'),
        ('Shadows', 'shadow_system'), ('Z-Index', 'z_index'), ('Layout', 'layout'),
        ('Visual Hierarchy', 'visual_hierarchy'), ('Motion', 'motion_tokens'),
        ('Responsive', 'responsive_breakpoints'), ('Accessibility', 'accessibility'),
        ('Performance', 'performance'), ('SEO', 'seo'), ('Security', 'security'),
    ]
    for label, key in summary_keys:
        data = evidence.get(key, {})
        if isinstance(data, dict) and 'confidence' in data:
            pat = str(data.get('pattern', '')).replace('|', '/').replace('\n', ' ')[:60]
            md += f"| {label} | {pat} | {data['confidence']}% |\n"
    md += "\n"

    # --- Typography ---
    if 'typography' in evidence:
        t = evidence['typography']
        md += "## Typography\n\n"
        md += f"**Pattern:** {t.get('pattern', 'N/A')}\n\n"
        ts = t.get('type_scale', {})
        if isinstance(ts, dict):
            if ts.get('ratio'): md += f"- **Type Scale Ratio:** {ts['ratio']}\n"
            if ts.get('sizes_px'): md += f"- **Sizes:** {', '.join(str(s) for s in ts['sizes_px'])}px\n"
            if ts.get('heading_sizes_px'): md += f"- **Heading Sizes:** {', '.join(str(s) for s in ts['heading_sizes_px'])}px\n"
        details = t.get('details', {})
        if details.get('font_stack'): md += f"- **Font Stack:** {', '.join(details['font_stack'])}\n"
        if details.get('body_size'): md += f"- **Body Size:** {details['body_size']}\n"
        md += "\n"

    # --- Colors ---
    if 'colors' in evidence:
        c = evidence['colors']
        md += "## Color Palette\n\n"
        palette = c.get('palette', {})
        if isinstance(palette, dict):
            for cat in ['primary', 'secondary', 'intentional']:
                colors = palette.get(cat, [])
                if colors:
                    md += f"### {cat.title()} Colors\n"
                    for col in colors[:8]:
                        if isinstance(col, dict):
                            hex_val = col.get('hex', col.get('color', str(col)))
                            count = col.get('count', '')
                        else:
                            hex_val = str(col)
                            count = ''
                        md += f"- `{hex_val}`{' (' + str(count) + ' uses)' if count else ''}\n"
                    md += "\n"
        if c.get('color_roles'):
            md += "### CSS Variable Roles\n"
            for role, val in list(c['color_roles'].items())[:12]:
                v = val.get('value', val) if isinstance(val, dict) else val
                md += f"- `--{role}`: {v}\n"
            md += "\n"

    # --- Spacing ---
    if 'spacing_scale' in evidence:
        sp = evidence['spacing_scale']
        md += "## Spacing Scale\n\n"
        if sp.get('base_unit'): md += f"- **Base Unit:** {sp['base_unit']}\n"
        scale = sp.get('scale', sp.get('values', []))
        if scale: md += f"- **Scale:** {', '.join(str(v) for v in scale)}\n"
        md += "\n"

    # --- Shadows ---
    if 'shadow_system' in evidence and evidence['shadow_system'].get('levels'):
        ss = evidence['shadow_system']
        md += "## Shadow System\n\n"
        md += "| Level | CSS Value | Usage |\n|-------|-----------|-------|\n"
        for lvl in ss['levels']:
            css = str(lvl.get('css', '')).replace('|', '/').replace('\n', ' ')[:50]
            md += f"| {lvl.get('name', '?')} | `{css}` | {lvl.get('count', 0)} elements |\n"
        md += "\n"

    # --- Z-Index ---
    z_data = evidence.get('z_index_stack', evidence.get('z_index', {}))
    if z_data and z_data.get('layers'):
        md += "## Z-Index Architecture\n\n"
        md += "| Layer | Z-Value | Elements |\n|-------|---------|----------|\n"
        for name, info in z_data['layers'].items():
            z = info.get('z_index', '?')
            count = info.get('visible_count', info.get('count', 0))
            label = name.split(': ')[-1] if ': ' in name else name
            md += f"| {label} | {z} | {count} |\n"
        md += "\n"

    # --- Visual Hierarchy ---
    if 'visual_hierarchy' in evidence:
        vh = evidence['visual_hierarchy']
        md += "## Visual Hierarchy\n\n"
        hero = vh.get('hero_section', {})
        if hero: md += f"- **Hero Section:** {'Detected' if hero.get('detected') else 'Not detected'}\n"
        cta = vh.get('primary_cta', {})
        if cta: md += f"- **Primary CTA:** {cta.get('text', 'Detected') if cta.get('detected') else 'Not detected'}\n"
        md += "\n"

    # --- Motion Tokens ---
    if 'motion_tokens' in evidence:
        mt = evidence['motion_tokens']
        details = mt.get('details', {})
        md += "## Motion & Animation\n\n"
        if details.get('personality'): md += f"- **Personality:** {details['personality']}\n"
        ds = details.get('duration_scale', {})
        if ds:
            md += "- **Duration Scale:**\n"
            for tier, data in ds.items():
                if isinstance(data, dict) and data.get('count', 0) > 0:
                    md += f"  - {tier}: {data.get('range_ms', '')} ({data['count']} animations)\n"
        if details.get('easing_palette'):
            md += f"- **Easing Curves:** {len(details['easing_palette'])} unique\n"
        md += "\n"

    # --- Spatial Composition ---
    if 'spatial_composition' in evidence:
        sc = evidence['spatial_composition']
        ps = sc.get('page_structure', {})
        md += "## Spatial Composition\n\n"
        if ps.get('pattern_type'): md += f"- **Page Pattern:** {ps['pattern_type']}\n"
        ws = sc.get('whitespace_analysis', {})
        if ws.get('content_density'): md += f"- **Content Density:** {ws['content_density']}%\n"
        if ws.get('interpretation'): md += f"- **Interpretation:** {ws['interpretation']}\n"
        ap = sc.get('alignment_patterns', {})
        if ap.get('dominant'): md += f"- **Alignment:** {ap['dominant']}\n"
        md += "\n"

    # --- Responsive Breakpoints ---
    if 'responsive_breakpoints' in evidence:
        bp = evidence['responsive_breakpoints']
        breakpoints = bp.get('breakpoints', bp.get('media_queries', []))
        if breakpoints:
            md += "## Responsive Breakpoints\n\n"
            md += "| Width | Media Query |\n|-------|-------------|\n"
            for b in breakpoints[:10]:
                width = b.get('width', b.get('min_width', b.get('max_width', '?')))
                query = b.get('query', b.get('media', f'{width}px'))
                md += f"| {width}px | `{str(query)[:60]}` |\n"
            md += "\n"
        elif bp.get('unique_breakpoints'):
            md += "## Responsive Breakpoints\n\n"
            md += f"- **Unique Breakpoints:** {bp['unique_breakpoints']}\n"
            md += f"- **Total Media Queries:** {bp.get('total_media_queries', 0)}\n"
            if bp.get('current_size'): md += f"- **Current Viewport:** {bp['current_size']}\n"
            md += "\n"

    # --- Site Architecture ---
    if 'site_architecture' in evidence:
        arch = evidence['site_architecture'].get('details', {})
        md += "## Site Architecture\n\n"
        if arch.get('framework'): md += f"- **Framework:** {arch['framework']}\n"
        if arch.get('css_framework'): md += f"- **CSS Framework:** {arch['css_framework']}\n"
        if arch.get('bundler'): md += f"- **Bundler:** {arch['bundler']}\n"
        if arch.get('state_mgmt'): md += f"- **State Management:** {arch['state_mgmt']}\n"
        if arch.get('router_type'): md += f"- **Router:** {arch['router_type']}\n"
        caps = arch.get('capabilities', {})
        active = [k.replace('_', ' ') for k, v in caps.items() if v]
        if active: md += f"- **Capabilities:** {', '.join(active)}\n"
        md += "\n"

    # --- Accessibility, Performance, SEO, Security (existing) ---
    if 'accessibility' in evidence:
        md += "## Accessibility\n\n"
        md += f"**Score:** {evidence['accessibility'].get('score', 0)}/100\n\n"
        for rec in evidence['accessibility'].get('recommendations', []):
            md += f"- {rec}\n"
        md += "\n"

    if 'contrast_a11y' in evidence and evidence['contrast_a11y'].get('details'):
        ca = evidence['contrast_a11y']
        md += "## Contrast Audit (WCAG AA)\n\n"
        md += f"- **Score:** {ca.get('score', '?')}/100\n"
        md += f"- **Violations:** {ca['details'].get('total_violations', 0)}\n"
        md += f"- **Passes:** {ca['details'].get('total_passes', 0)}\n\n"

    if 'performance' in evidence:
        md += "## Performance\n\n"
        md += f"**Pattern:** {evidence['performance'].get('pattern', 'N/A')}\n\n"

    if 'seo' in evidence:
        seo_details = evidence['seo'].get('details', {})
        md += "## SEO\n\n"
        md += f"**Score:** {evidence['seo'].get('score', 0)}/100\n\n"
        md += f"- **Title:** {seo_details.get('title', 'N/A')}\n"
        md += f"- **Description:** {seo_details.get('description', 'N/A')}\n\n"

    if 'security' in evidence:
        md += "## Security\n\n"
        md += f"**Score:** {evidence['security'].get('score', 0)}/100\n\n"

    # --- Content Structure ---
    if 'content_extraction' in evidence:
        ce = evidence['content_extraction']
        md += "## Content Structure\n\n"
        md += f"- **Page Type:** {ce.get('page_type', 'unknown')}\n"
        if ce.get('reasoning'): md += f"- **Reasoning:** {ce['reasoning']}\n"
        if ce.get('semantic_analysis', {}).get('score') is not None:
            md += f"- **Semantic Score:** {ce['semantic_analysis']['score']}/100\n"
        md += "\n"

    # --- Articles ---
    if 'article_content' in evidence and evidence['article_content'].get('articles'):
        md += "## Extracted Articles\n\n"
        for article in evidence['article_content']['articles']:
            md += f"### {article.get('title', 'Untitled')}\n\n"
            if article.get('author'): md += f"- **Author:** {article['author']}\n"
            if article.get('date'): md += f"- **Date:** {article['date']}\n"
            md += f"- **Confidence:** {article.get('confidence', '?')}%\n"
            if article.get('word_count'): md += f"- **Word Count:** {article['word_count']}\n"
            md += "\n"

    # --- Meta ---
    if 'meta_info' in evidence:
        md += "## Technical Summary\n\n"
        md += f"- **Total DOM Nodes:** {evidence['meta_info'].get('total_dom_nodes', 0):,}\n"
        md += f"- **Total Network Requests:** {evidence['meta_info'].get('total_requests', 0)}\n\n"

    md += "---\n\n*Report generated by Web Intelligence Scraper*\n"
    return md


@app.route('/api/export-design-md', methods=['POST'])
def export_design_md():
    """Export evidence as AI-agent-consumable DESIGN.md.

    Accepts any ONE of:
      - {"evidence": {...}}           — inline evidence (max ~16 MB)
      - {"result_file": "/path.json"} — server-side path from /api/deep-scan's response
      - {"site_url": "https://..."}   — reuses most-recent cached scan
    """
    data = request.json or {}
    evidence = data.get('evidence')

    # Gap #2: large evidence trips Flask's 16MB MAX_CONTENT_LENGTH.
    # Allow clients to reference the server-side result_file instead of
    # POSTing the full payload back.
    if not evidence and data.get('result_file'):
        fpath = data['result_file']
        # Security: restrict to the results directory only
        results_dir = os.path.realpath(os.path.expanduser('~/.webscraper/results'))
        real_path = os.path.realpath(fpath)
        if not real_path.startswith(results_dir + os.sep):
            return jsonify({'error': 'result_file must live under ~/.webscraper/results'}), 400
        try:
            with open(real_path, 'r') as f:
                evidence = json.load(f).get('evidence')
        except Exception as e:
            return jsonify({'error': f'Could not read result_file: {str(e)[:120]}'}), 400

    # Third option: reuse in-memory cache by site_url
    if not evidence and data.get('site_url'):
        cached = _evidence_cache.get(data['site_url'])
        if cached:
            evidence = cached.get('evidence')

    if not evidence:
        return jsonify({'error': 'No evidence data provided (use evidence, result_file, or site_url)'}), 400

    markdown = generate_design_md(evidence)
    return jsonify({'success': True, 'markdown': markdown})


def _resolve_design_evidence(evidence):
    """Return a flat evidence view that works for both single-page and smart-nav.

    Smart-nav stores per-page evidence under `page_results` and only exposes
    `site_patterns`, `site_architecture`, and consistency at the top level.
    Downstream design-MD consumers expect the design-system keys at the top
    level. This helper promotes the home (or first valid) page's keys to the
    top level without mutating the caller's dict.

    Also attaches `_smart_nav_meta` with cross-page context when applicable.
    """
    if not isinstance(evidence, dict):
        return evidence

    page_results = evidence.get('page_results')
    if not isinstance(page_results, dict) or not page_results:
        # Single-page mode: return as-is
        return evidence

    # Pick the home page if present, otherwise the first non-errored page
    home = page_results.get('home')
    if not isinstance(home, dict) or home.get('error'):
        home = next(
            (p for p in page_results.values()
             if isinstance(p, dict) and not p.get('error')),
            None,
        )
    if not home:
        return evidence

    # Flatten: home page keys as the base, then merge synthesis-level keys over
    # the top so smart-nav context (site_patterns, consistency) wins where it's
    # more useful than per-page data.
    flat = dict(home)
    synth_keys = (
        'site_patterns', 'design_system_consistency', 'validated_capabilities',
        'site_topology', 'site_content_profile', 'architecture_diagrams',
        'layout_synthesis', 'design_intent', 'design_playbook', 'url_patterns',
    )
    for k in synth_keys:
        if k in evidence and evidence[k] is not None:
            flat[k] = evidence[k]

    # Prefer synthesis-level site_architecture if present (first-page copy)
    if 'site_architecture' in evidence and evidence['site_architecture']:
        flat['site_architecture'] = evidence['site_architecture']

    # Expose smart-nav metadata so generators can mention it explicitly
    valid_pages = [
        (label, p) for label, p in page_results.items()
        if isinstance(p, dict) and not p.get('error')
    ]
    flat['_smart_nav_meta'] = {
        'mode': evidence.get('analysis_mode', 'smart-nav'),
        'pages_analyzed': evidence.get('pages_analyzed', len(page_results)),
        'page_labels': [label for label, _ in valid_pages],
        'home_url': (home.get('meta_info') or {}).get('url', ''),
    }
    return flat


def generate_design_md(evidence):
    """Generate concise DESIGN.md for AI coding agents.

    Format inspired by VoltAgent/awesome-design-md — optimized for dropping
    into a project so Claude Code / Cursor / GPT can generate on-brand UI.
    Typically 200-400 lines, actionable, evidence-backed.
    """
    # Resolve smart-nav (page_results) vs single-page (top-level keys) into
    # a flat view so the rest of this function is oblivious to the mode.
    evidence = _resolve_design_evidence(evidence)

    # --- Header ---
    meta = evidence.get('meta_info', {})
    url = meta.get('url', 'Unknown')
    # Extract site name from URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    site_name = parsed.hostname or 'Unknown'
    site_name = site_name.replace('www.', '').split('.')[0].title()

    brand = evidence.get('brand_personality', {})
    tone = brand.get('tone', 'Modern')
    energy = brand.get('energy', 'Balanced')
    audience = brand.get('target_audience', '')

    md = f"# {site_name} — Design System\n\n"
    md += f"> **{tone}** / **{energy}**"
    if audience:
        md += f" / {audience}"
    md += "\n"

    # Build a one-line personality summary from brand signals
    signals = brand.get('signals', [])
    if signals:
        top_signals = [s.split('→')[0].strip() for s in signals[:3]]
        md += f"> {', '.join(top_signals)}\n"
    md += "\n"

    # Architecture context
    arch = evidence.get('site_architecture', {})
    css_fw = arch.get('css_framework', '')
    framework = arch.get('framework', '')
    css_analytics = evidence.get('css_analytics', {})
    sophistication = css_analytics.get('sophistication_score', None)

    if css_fw or framework or sophistication is not None:
        md += "**Built with:**"
        parts = []
        if framework:
            parts.append(framework)
        if css_fw:
            parts.append(css_fw)
        if sophistication is not None:
            parts.append(f"CSS sophistication {sophistication}/100")
        md += " " + " · ".join(parts) + "\n\n"

    # Smart-nav context: tell the reader this synthesizes N pages
    snm = evidence.get('_smart_nav_meta')
    if snm:
        pages_n = snm.get('pages_analyzed', 0)
        labels = snm.get('page_labels', [])
        site_patterns = evidence.get('site_patterns') or {}
        dsc = evidence.get('design_system_consistency') or {}
        md += f"**Synthesized from {pages_n} page"
        md += "s" if pages_n != 1 else ""
        if labels:
            md += f":** {', '.join(labels)}\n"
        else:
            md += ":**\n"
        if site_patterns.get('typography_consistent') is not None:
            ok = 'consistent' if site_patterns['typography_consistent'] else 'varies by page'
            md += f"- Typography across pages: **{ok}**\n"
        if site_patterns.get('color_consistency'):
            md += f"- Color palette across pages: **{site_patterns['color_consistency']}**\n"
        if site_patterns.get('layout_consistency'):
            md += f"- Layout across pages: **{site_patterns['layout_consistency']}**\n"
        if isinstance(dsc, dict) and dsc.get('overall_score') is not None:
            md += f"- Design-system consistency score: **{dsc['overall_score']}/100**\n"
        md += "\n"

    # --- Color Palette ---
    colors = evidence.get('colors', {})
    md += "## Color Palette\n\n"

    color_roles = colors.get('color_roles', {})
    palette = colors.get('palette', {})

    if color_roles:
        md += "| Role | Value | Usage |\n|------|-------|-------|\n"
        for role, vals in color_roles.items():
            if isinstance(vals, list) and vals:
                for v in vals[:2]:
                    if isinstance(v, dict):
                        hex_val = v.get('hex', v.get('value', ''))
                        count = v.get('count', '')
                        md += f"| {role} | `{hex_val}` | {count} uses |\n"
                    elif isinstance(v, str):
                        md += f"| {role} | `{v}` | — |\n"
            elif isinstance(vals, str):
                md += f"| {role} | `{vals}` | — |\n"
        md += "\n"
    elif palette:
        # Fallback to palette structure
        md += "| Group | Colors |\n|-------|--------|\n"
        for group, vals in palette.items():
            if isinstance(vals, list) and vals:
                hex_list = [f"`{v}`" if isinstance(v, str) else f"`{v.get('hex', '')}`"
                            for v in vals[:5]]
                md += f"| {group} | {', '.join(hex_list)} |\n"
        md += "\n"
    else:
        md += "*No color data extracted*\n\n"

    # --- Typography ---
    typo = evidence.get('typography', {})
    md += "## Typography\n\n"

    details = typo.get('details', {})
    all_fonts = details.get('all_fonts', [])
    body = details.get('body', {})
    type_scale = typo.get('type_scale', {})

    if all_fonts:
        # Categorize fonts
        body_font = body.get('fontFamily', all_fonts[0] if all_fonts else '')
        heading_fonts = [f for f in all_fonts if f != body_font]

        md += f"- **Body:** `{body_font}`"
        if body.get('fontSize'):
            md += f" at {body['fontSize']}"
        if body.get('lineHeight'):
            md += f" / {body['lineHeight']} line-height"
        md += "\n"

        if heading_fonts:
            md += f"- **Headings:** `{heading_fonts[0]}`\n"

        # Mono fonts
        mono = [f for f in all_fonts if 'mono' in f.lower() or 'courier' in f.lower() or 'consolas' in f.lower()]
        if mono:
            md += f"- **Monospace:** `{mono[0]}`\n"

    # Type scale
    if isinstance(type_scale, dict):
        ratio = type_scale.get('ratio')
        sizes = type_scale.get('heading_sizes_px', type_scale.get('sizes_px', []))
        if ratio:
            md += f"- **Scale ratio:** {ratio}\n"
        if sizes:
            md += f"- **Heading sizes:** {', '.join(str(s) + 'px' for s in sizes[:6])}\n"

    # Font weights
    weights = details.get('weights', [])
    if weights:
        md += f"- **Weights:** {', '.join(str(w) for w in sorted(weights))}\n"

    md += "\n"

    # --- Spacing Scale ---
    spacing = evidence.get('spacing_scale', {})
    md += "## Spacing Scale\n\n"

    scale = spacing.get('scale', spacing.get('values', []))
    base = spacing.get('base_unit', '')

    # Semantic naming: map scale position to t-shirt sizes
    size_names = ['3xs', '2xs', 'xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl']

    if scale:
        sorted_scale = sorted(set(scale))[:10]
        # Center the naming around the median
        offset = max(0, (len(size_names) - len(sorted_scale)) // 2)

        md += "| Token | Value |\n|-------|-------|\n"
        for i, val in enumerate(sorted_scale):
            name_idx = min(i + offset, len(size_names) - 1)
            name = size_names[name_idx]
            md += f"| `spacing.{name}` | `{val}px` |\n"
        md += "\n"
        if base:
            md += f"**Base unit:** `{base}`\n\n"
    else:
        md += "*No spacing scale detected*\n\n"

    # --- Layout ---
    layout = evidence.get('layout', {})
    spatial = evidence.get('spatial_composition', {})
    md += "## Layout\n\n"

    page_structure = spatial.get('page_structure', {})
    pattern_type = page_structure.get('pattern_type', '')
    if pattern_type:
        md += f"- **Page pattern:** {pattern_type}\n"

    # Container / grid info
    container_hierarchy = spatial.get('container_hierarchy', {})
    layout_grid = spatial.get('layout_grid', {})

    grid_count = layout.get('grid_count', container_hierarchy.get('grid_count', 0))
    flex_count = layout.get('flex_count', container_hierarchy.get('flex_count', 0))

    if grid_count or flex_count:
        md += f"- **Layout engines:** {grid_count} CSS Grid, {flex_count} Flexbox\n"

    if layout_grid:
        cols = layout_grid.get('columns')
        if cols:
            md += f"- **Grid system:** {cols}-column\n"

    # Breakpoints
    breakpoints = evidence.get('responsive_breakpoints', {})
    bp_list = breakpoints.get('unique_breakpoints', [])
    if bp_list:
        md += f"- **Breakpoints:** {', '.join(str(b) + 'px' for b in bp_list[:6])}\n"

    # Alignment & whitespace
    alignment = spatial.get('alignment_patterns', {})
    whitespace = spatial.get('whitespace_analysis', {})
    if alignment.get('dominant'):
        md += f"- **Alignment:** {alignment['dominant']}\n"
    if whitespace.get('interpretation'):
        md += f"- **Density:** {whitespace['interpretation']}\n"

    md += "\n"

    # --- Motion & Animation ---
    motion = evidence.get('motion_tokens', {})
    md += "## Motion\n\n"

    duration_scale = motion.get('duration_scale', [])
    easing_palette = motion.get('easing_palette', [])

    if duration_scale:
        md += "**Duration scale:**\n"
        for d in duration_scale[:5]:
            if isinstance(d, dict):
                md += f"- `{d.get('value', d.get('duration', ''))}` — {d.get('role', d.get('label', ''))}\n"
            else:
                md += f"- `{d}`\n"
        md += "\n"

    if easing_palette:
        md += "**Easing palette:**\n"
        for e in easing_palette[:5]:
            if isinstance(e, dict):
                md += f"- `{e.get('value', e.get('easing', ''))}` — {e.get('role', e.get('label', ''))}\n"
            else:
                md += f"- `{e}`\n"
        md += "\n"

    # Transition patterns from CSS analytics
    transitions = css_analytics.get('transition_patterns', {})
    trans_props = transitions.get('transitioned_properties', {})
    if trans_props:
        top_trans = sorted(trans_props.items(), key=lambda x: -x[1])[:5]
        md += f"**Most animated properties:** {', '.join(f'`{p}`' for p, _ in top_trans)}\n\n"

    if not duration_scale and not easing_palette and not trans_props:
        md += "*No motion tokens detected*\n\n"

    # --- Shadows & Elevation ---
    shadows = evidence.get('shadow_system', {})
    levels = shadows.get('levels', [])
    md += "## Shadows & Elevation\n\n"

    if levels:
        md += "| Level | CSS | Usage |\n|-------|-----|-------|\n"
        for i, lvl in enumerate(levels):
            css_val = lvl.get('css', lvl.get('value', ''))
            count = lvl.get('count', lvl.get('usage', 0))
            name = lvl.get('name', f'elevation-{i+1}')
            md += f"| {name} | `{css_val[:60]}` | {count} elements |\n"
        md += "\n"
    else:
        md += "*No shadow system detected*\n\n"

    # --- Component Patterns ---
    hierarchy = evidence.get('visual_hierarchy', {})
    md += "## Component Patterns\n\n"

    hero = hierarchy.get('hero_section', {})
    if hero and hero.get('detected'):
        md += "### Hero Section\n"
        if hero.get('heading'):
            md += f"- **Heading:** \"{hero['heading'][:80]}\"\n"
        if hero.get('font_size'):
            md += f"- **Size:** {hero['font_size']}\n"
        if hero.get('has_background'):
            md += f"- **Background:** {hero.get('background_type', 'yes')}\n"
        md += "\n"

    cta = hierarchy.get('primary_cta', {})
    if cta and cta.get('detected'):
        md += "### Primary CTA\n"
        if cta.get('text'):
            md += f"- **Text:** \"{cta['text'][:50]}\"\n"
        if cta.get('background_color'):
            md += f"- **Color:** `{cta['background_color']}`\n"
        if cta.get('font_size'):
            md += f"- **Size:** {cta['font_size']}\n"
        md += "\n"

    # Zones from spatial composition
    zones = spatial.get('component_zones', [])
    if zones:
        md += "### Page Zones\n"
        for z in zones[:6]:
            if isinstance(z, dict):
                name = z.get('type', z.get('name', 'zone'))
                md += f"- **{name.title()}**"
                if z.get('bounds'):
                    b = z['bounds']
                    md += f" — {b.get('width', '?')}×{b.get('height', '?')}px"
                md += "\n"
        md += "\n"

    if not hero.get('detected') and not cta.get('detected') and not zones:
        md += "*No component patterns detected*\n\n"

    # --- Box Model Export ---
    box_model = evidence.get('box_model_export', {})
    bm_zones = box_model.get('zones', [])
    if bm_zones:
        md += "## Box Model (Key Zones)\n\n"
        md += "| Zone | Dimensions | Layout | Properties |\n|------|-----------|--------|------------|\n"
        for z in bm_zones:
            comp = z.get('computed', {})
            dims = comp.get('dimensions', {})
            zone_name = z.get('zone_type', 'unknown').title()
            dim_str = f"{dims.get('widthVw', '?')} × {dims.get('height', '?')}"
            # Layout
            display = comp.get('display', '')
            layout_parts = [display]
            if comp.get('flexDirection') and comp['flexDirection'] != 'row':
                layout_parts.append(comp['flexDirection'])
            if comp.get('justifyContent'):
                layout_parts.append(comp['justifyContent'])
            layout_str = ', '.join(layout_parts)
            # Extra props
            props = []
            if comp.get('gap'):
                props.append(f"gap: {comp['gap']}")
            if comp.get('padding'):
                props.append(f"padding: {comp['padding']}")
            if comp.get('zIndex') is not None:
                props.append(f"z-index: {comp['zIndex']}")
            if comp.get('maxWidth'):
                props.append(f"max-width: {comp['maxWidth']}")
            props_str = '; '.join(props) if props else '—'
            md += f"| {zone_name} | {dim_str} | {layout_str} | {props_str} |\n"
        md += "\n"

    # --- Component Blueprints ---
    blueprints_data = evidence.get('component_blueprints', {})
    blueprints = blueprints_data.get('blueprints', [])
    if blueprints:
        md += "## Component Blueprints\n\n"
        md += f"*{len(blueprints)} components auto-ripped by priority*\n\n"
        for bp_entry in blueprints[:5]:
            disc = bp_entry.get('discovery', {})
            bp = bp_entry.get('blueprint', {})
            label = disc.get('label', disc.get('selector', 'Unknown'))
            category = disc.get('category', '')
            selector = disc.get('selector', '')

            md += f"### {label}\n"
            md += f"- **Category:** {category}\n"
            md += f"- **Selector:** `{selector}`\n"

            # Box model from blueprint
            box = bp.get('boxModel', {})
            if box:
                w = box.get('width', '?')
                h = box.get('height', '?')
                md += f"- **Dimensions:** {w} × {h}\n"

            # Layout from blueprint
            bp_layout = bp.get('layout') or {}
            if isinstance(bp_layout, dict) and bp_layout.get('display'):
                layout_desc = bp_layout['display']
                if bp_layout.get('flexDirection'):
                    layout_desc += f", {bp_layout['flexDirection']}"
                if bp_layout.get('justifyContent'):
                    layout_desc += f", {bp_layout['justifyContent']}"
                if bp_layout.get('gap') and bp_layout['gap'] != 'normal':
                    layout_desc += f", gap: {bp_layout['gap']}"
                md += f"- **Layout:** {layout_desc}\n"

            # Typography (some blueprint shapes store this as a list of
            # per-element rules instead of a single dict — guard both)
            typo_bp = bp.get('typography') or {}
            if isinstance(typo_bp, list):
                typo_bp = typo_bp[0] if typo_bp and isinstance(typo_bp[0], dict) else {}
            if isinstance(typo_bp, dict) and typo_bp.get('fontFamily'):
                md += f"- **Font:** `{typo_bp['fontFamily'][:60]}`"
                if typo_bp.get('fontSize'):
                    md += f" at {typo_bp['fontSize']}"
                md += "\n"

            md += "\n"

    # --- Technical Notes ---
    md += "## Technical Notes\n\n"

    # Modern CSS features
    modern = css_analytics.get('modern_features', {})
    active_features = [k.replace('_', ' ') for k, v in modern.items()
                       if isinstance(v, bool) and v]
    if active_features:
        md += f"- **Modern CSS:** {', '.join(active_features)}\n"

    # DTCG tokens
    dtcg = css_analytics.get('dtcg_tokens', {})
    token_count = dtcg.get('total_token_count', 0)
    if token_count:
        md += f"- **Design tokens:** {token_count} DTCG-classifiable custom properties\n"

    # Accessibility
    a11y = evidence.get('accessibility', {})
    if a11y.get('confidence', 0) > 50:
        md += f"- **Accessibility:** {a11y.get('pattern', 'analyzed')}\n"

    contrast = evidence.get('contrast_a11y', {})
    if contrast.get('confidence', 0) > 50:
        md += f"- **Contrast:** {contrast.get('pattern', 'analyzed')}\n"

    md += f"\n---\n\n"
    md += f"*Generated from [{url}]({url}) by Web Intelligence Scraper*\n"

    return md


@app.route('/api/export-catalog', methods=['POST'])
def export_catalog():
    """Export json-render compatible component catalog.

    Accepts any ONE of:
      - {"evidence": {...}}           — inline evidence (max ~16 MB)
      - {"result_file": "/path.json"} — server-side path from /api/deep-scan response
      - {"site_url": "https://..."}   — reuses most-recent cached scan
    """
    data = request.json or {}
    evidence = data.get('evidence')

    # Accept result_file to avoid 413 on large scans
    if not evidence and data.get('result_file'):
        fpath = data['result_file']
        results_dir = os.path.realpath(os.path.expanduser('~/.webscraper/results'))
        real_path = os.path.realpath(fpath)
        if not real_path.startswith(results_dir + os.sep):
            return jsonify({'error': 'result_file must live under ~/.webscraper/results'}), 400
        try:
            with open(real_path, 'r') as f:
                evidence = json.load(f).get('evidence')
        except Exception as e:
            return jsonify({'error': f'Could not read result_file: {str(e)[:120]}'}), 400

    if not evidence and data.get('site_url'):
        cached = _evidence_cache.get(data['site_url'])
        if cached:
            evidence = cached.get('evidence')

    if not evidence:
        return jsonify({'error': 'No evidence data provided (use evidence, result_file, or site_url)'}), 400

    catalog = generate_json_render_catalog(evidence)
    return jsonify({'success': True, 'catalog': catalog})


def generate_json_render_catalog(evidence):
    """
    Generate a json-render compatible component catalog from scan evidence.

    Output format matches vercel-labs/json-render — a Catalog JSON an AI can
    use to generate new pages that precisely match the scanned site's design
    language. Includes:
      - design tokens (colors, typography, spacing, shadows, motion)
      - component definitions with inferred props + descriptions
      - an example spec showing page assembly
      - a system_prompt snippet to paste into any LLM

    See: https://github.com/vercel-labs/json-render
    """
    from urllib.parse import urlparse
    import datetime

    evidence = _resolve_design_evidence(evidence)

    meta = evidence.get('meta_info', {})
    url = meta.get('url', 'unknown')
    parsed = urlparse(url)
    site_name = (parsed.hostname or 'unknown').replace('www.', '')
    site_short = site_name.split('.')[0].title()
    today = datetime.date.today().isoformat()

    # ── 1. Design Tokens ──────────────────────────────────────────────────────
    tokens = {}

    # Colors — prefer semantic roles over raw palette
    colors_ev = evidence.get('colors', {})
    color_roles = colors_ev.get('color_roles', {})
    palette = colors_ev.get('palette', {})

    def _extract_color_value(raw):
        """Flatten a color role entry — handles str, dict {value}, or list thereof."""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            return raw.get('value') or raw.get('hex') or ''
        if isinstance(raw, list) and raw:
            return _extract_color_value(raw[0])
        return ''

    tok_colors = {}
    role_map = {
        'primary': ['primary', 'brand', 'accent'],
        'secondary': ['secondary', 'secondary_brand'],
        'background': ['background', 'bg', 'surface'],
        'text': ['text', 'foreground', 'on_background'],
        'muted': ['muted', 'subtle', 'disabled'],
        'success': ['success', 'positive'],
        'warning': ['warning', 'caution'],
        'error': ['error', 'danger', 'negative'],
        'border': ['border', 'divider', 'outline'],
    }
    for token_name, candidates in role_map.items():
        for cand in candidates:
            if cand in color_roles and color_roles[cand]:
                val = _extract_color_value(color_roles[cand])
                if val:
                    tok_colors[token_name] = val
                    break
        if token_name not in tok_colors:
            # Fall back to palette
            primary_list = palette.get('primary', palette.get('intentional', []))
            if primary_list and token_name == 'primary':
                first = primary_list[0]
                tok_colors['primary'] = first if isinstance(first, str) else first.get('value', '')

    if tok_colors:
        tokens['colors'] = tok_colors

    # Typography
    typo_ev = evidence.get('typography', {})
    typo_details = typo_ev.get('details', {})
    tok_typo = {}

    all_fonts = typo_details.get('all_fonts', typo_details.get('fonts', []))
    heading_font = typo_details.get('heading_font') or (all_fonts[0] if all_fonts else None)
    body_font = typo_details.get('body_font') or (all_fonts[1] if len(all_fonts) > 1 else heading_font)
    mono_font = typo_details.get('mono_font')

    if heading_font:
        tok_typo['headingFont'] = heading_font
    if body_font:
        tok_typo['bodyFont'] = body_font
    if mono_font:
        tok_typo['monoFont'] = mono_font

    # Type scale — heading_sizes_px can be a dict {h1: px, ...} or a list [px, ...]
    type_scale = typo_ev.get('type_scale', {})
    heading_sizes = {}
    if isinstance(type_scale, dict):
        hs = type_scale.get('heading_sizes_px', {})
        if isinstance(hs, dict):
            for tag, size in hs.items():
                heading_sizes[tag] = f"{size}px"
        elif isinstance(hs, list):
            for i, size in enumerate(hs[:6], 1):
                heading_sizes[f'h{i}'] = f"{size}px"
    if not heading_sizes and typo_details.get('heading_sizes'):
        for i, size in enumerate(typo_details['heading_sizes'][:6], 1):
            heading_sizes[f'h{i}'] = str(size)

    body_size = typo_details.get('body_size') or typo_details.get('base_size') or '16px'
    scale_entry = {}
    if heading_sizes:
        scale_entry.update(heading_sizes)
    scale_entry['body'] = str(body_size)

    weights = typo_details.get('weights', typo_details.get('font_weights', []))
    if weights:
        tok_typo['weights'] = [str(w) for w in weights[:8]]
    if scale_entry:
        tok_typo['scale'] = scale_entry

    line_heights = typo_details.get('line_heights', [])
    if line_heights:
        tok_typo['lineHeights'] = line_heights[:4]

    if tok_typo:
        tokens['typography'] = tok_typo

    # Spacing
    spacing_ev = evidence.get('spacing_scale', {})
    spacing_vals = spacing_ev.get('scale', spacing_ev.get('values', []))
    spacing_names = ['xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl']
    tok_spacing = {}
    if spacing_vals:
        # Deduplicate and sort
        deduped = sorted(set(
            v if isinstance(v, (int, float)) else
            float(v.replace('px', '').replace('rem', '').replace('em', '') or 0)
            for v in spacing_vals if v
        ))
        for i, val in enumerate(deduped[:len(spacing_names)]):
            name = spacing_names[i]
            tok_spacing[name] = f"{val}px"
    if spacing_ev.get('base_unit'):
        tok_spacing['base'] = spacing_ev['base_unit']
    if tok_spacing:
        tokens['spacing'] = tok_spacing

    # Shadows
    shadow_ev = evidence.get('shadow_system', {})
    shadow_levels = shadow_ev.get('levels', [])
    tok_shadows = {}
    elevation_names = ['sm', 'md', 'lg', 'xl', 'focus']
    for i, level in enumerate(shadow_levels[:5]):
        name = level.get('name') or elevation_names[i] if i < len(elevation_names) else f'level{i}'
        css = level.get('css') or level.get('value', '')
        if css:
            tok_shadows[name] = css
    if tok_shadows:
        tokens['shadows'] = tok_shadows

    # Motion
    motion_ev = evidence.get('motion_tokens', {})
    tok_motion = {}
    dur_scale = motion_ev.get('duration_scale', {})
    if dur_scale:
        tok_motion['durations'] = {k: v for k, v in list(dur_scale.items())[:6]}
    easing_palette = motion_ev.get('easing_palette', [])
    if easing_palette:
        tok_motion['easings'] = {
            ep.get('role', f'easing{i}'): ep.get('value', '')
            for i, ep in enumerate(easing_palette[:5])
            if ep.get('value')
        }
    if tok_motion:
        tokens['motion'] = tok_motion

    # Border radius — prefer levels[*].value (actual CSS px) over raw scale numbers
    br_ev = evidence.get('border_radius_scale', {})
    br_levels = br_ev.get('levels', [])
    if isinstance(br_levels, list) and br_levels:
        br_names = ['sm', 'md', 'lg', 'xl', 'full']
        tokens['radii'] = {}
        for i, lvl in enumerate(br_levels[:5]):
            name = br_names[i] if i < len(br_names) else f'r{i}'
            val = lvl.get('value') or lvl.get('display') or str(lvl.get('px', ''))
            if val:
                tokens['radii'][name] = val
    else:
        br_vals = br_ev.get('values', br_ev.get('scale', []))
        if br_vals:
            br_names = ['sm', 'md', 'lg', 'full']
            tokens['radii'] = {
                br_names[i] if i < len(br_names) else f'r{i}': str(v)
                for i, v in enumerate(br_vals[:4])
            }

    # ── 2. Component Definitions ───────────────────────────────────────────────
    components = {}
    bp_data = evidence.get('component_blueprints', {})
    blueprints = bp_data.get('blueprints', []) if isinstance(bp_data, dict) else []

    # Fallback: build minimal components from visual_hierarchy if no blueprints
    if not blueprints:
        vh = evidence.get('visual_hierarchy', {})
        hero = vh.get('hero_section', {})
        if hero.get('detected'):
            blueprints_synthetic = [{'_synthetic': True, 'label': 'HeroSection', 'category': 'hero', 'description': hero.get('description', 'Hero section')}]
        else:
            blueprints_synthetic = []
    else:
        blueprints_synthetic = []

    def _infer_props(disc, blue):
        """Infer json-render prop definitions from blueprint anatomy."""
        props = {}
        category = disc.get('category', '')
        label = disc.get('label', '')
        anatomy = blue.get('anatomy', {})

        # Always offer children prop
        props['children'] = {
            'type': 'node',
            'description': 'Content to render inside the component',
        }

        # Category-specific props
        if category in ('navigation', 'header'):
            props['logo'] = {'type': 'string', 'description': 'Logo image src or brand name text'}
            props['links'] = {
                'type': 'array',
                'items': {'type': 'object', 'properties': {
                    'label': {'type': 'string'},
                    'href': {'type': 'string'},
                    'active': {'type': 'boolean'},
                }},
                'description': 'Navigation link items',
            }
            props['ctaText'] = {'type': 'string', 'description': 'Primary CTA button label'}
            props['ctaHref'] = {'type': 'string', 'description': 'Primary CTA URL'}

        elif category in ('hero', 'banner'):
            props['headline'] = {'type': 'string', 'required': True, 'description': 'Main hero headline'}
            props['subtext'] = {'type': 'string', 'description': 'Supporting description below headline'}
            props['ctaText'] = {'type': 'string', 'description': 'Primary call-to-action button text'}
            props['ctaHref'] = {'type': 'string', 'description': 'CTA destination URL'}
            props['secondaryCtaText'] = {'type': 'string', 'description': 'Secondary CTA link text'}
            props['backgroundImage'] = {'type': 'string', 'description': 'Background image URL (optional)'}

        elif category in ('content_grid', 'features', 'grid'):
            props['items'] = {
                'type': 'array',
                'items': {'type': 'object', 'properties': {
                    'icon': {'type': 'string'},
                    'title': {'type': 'string', 'required': True},
                    'description': {'type': 'string'},
                    'href': {'type': 'string'},
                }},
                'description': 'Grid items (features, cards, etc.)',
            }
            props['columns'] = {'type': 'number', 'description': 'Number of columns (default: auto)'}
            props['title'] = {'type': 'string', 'description': 'Section heading (optional)'}

        elif category in ('footer',):
            props['columns'] = {
                'type': 'array',
                'items': {'type': 'object', 'properties': {
                    'heading': {'type': 'string'},
                    'links': {'type': 'array', 'items': {'type': 'object',
                              'properties': {'label': {'type': 'string'}, 'href': {'type': 'string'}}}},
                }},
                'description': 'Footer link columns',
            }
            props['copyright'] = {'type': 'string', 'description': 'Copyright line text'}
            props['socialLinks'] = {'type': 'array', 'description': 'Social media links'}

        elif category in ('form',):
            props['fields'] = {
                'type': 'array',
                'items': {'type': 'object', 'properties': {
                    'name': {'type': 'string', 'required': True},
                    'label': {'type': 'string'},
                    'type': {'type': 'string', 'default': 'text'},
                    'placeholder': {'type': 'string'},
                    'required': {'type': 'boolean'},
                }},
                'description': 'Form field definitions',
            }
            props['submitText'] = {'type': 'string', 'description': 'Submit button label'}
            props['onSubmit'] = {'type': 'action', 'description': 'Form submission action'}

        else:
            # Generic content component
            props['title'] = {'type': 'string', 'description': 'Section or card title'}
            props['description'] = {'type': 'string', 'description': 'Body text content'}
            props['image'] = {'type': 'string', 'description': 'Image URL (optional)'}
            props['href'] = {'type': 'string', 'description': 'Link destination (optional)'}

        return props

    def _build_component_description(disc, blue):
        """Build a rich natural-language description for an AI to understand the component."""
        label = disc.get('label', disc.get('category', 'Component'))
        category = disc.get('category', 'section')
        bounds = disc.get('bounds', {})
        w = bounds.get('width', 0)
        h = bounds.get('height', 0)
        selector = disc.get('selector', '')

        box = blue.get('boxModel', {})
        visual = blue.get('visual', {})
        interactivity = blue.get('interactivity', {})
        js_info = blue.get('javascript', {})
        portability = blue.get('portability', {})
        semantic_name = blue.get('semantic_name', label)

        parts = [f"{semantic_name} ({category})."]

        # Dimensions
        if w and h:
            parts.append(f"Dimensions: {w}×{h}px.")

        # Visual
        bg = visual.get('backgroundColor', '')
        if bg and bg not in ('rgba(0, 0, 0, 0)', 'transparent', 'none', ''):
            parts.append(f"Background: {bg}.")
        shadow = visual.get('boxShadow', '')
        if shadow and shadow != 'none':
            parts.append(f"Has elevation shadow.")
        br = visual.get('borderRadius', '')
        if br and br not in ('0px', 'none', ''):
            parts.append(f"Border-radius: {br}.")

        # Interactivity
        has_transition = interactivity.get('transition', 'none') not in ('none', 'all 0s', '')
        if has_transition:
            parts.append(f"Has CSS transition on hover/focus.")
        if js_info.get('requiresJavaScript'):
            behaviors = js_info.get('behaviors', {})
            beh_list = [k.replace('has', '').replace('Handlers', '').replace('Controls', '').lower()
                        for k, v in behaviors.items() if v and k.startswith('has')]
            if beh_list:
                parts.append(f"JS behaviors: {', '.join(beh_list[:4])}.")

        # Reusability
        score = portability.get('reusability_score', 0)
        if score:
            parts.append(f"Reusability: {score}/100.")

        if selector:
            parts.append(f"Selector: `{selector}`.")

        return ' '.join(parts)

    # Build from real blueprints
    for bp_entry in blueprints:
        disc = bp_entry.get('discovery', {})
        blue = bp_entry.get('blueprint', {})
        label = disc.get('label', disc.get('category', 'Component'))
        category = disc.get('category', 'section')
        selector = disc.get('selector', '')

        # Create a clean component name (PascalCase, no spaces/punctuation)
        import re
        raw_name = blue.get('semantic_name') or label.split('—')[0].strip()
        comp_name = re.sub(r'[^a-zA-Z0-9]', '', raw_name.title().replace(' ', ''))
        if not comp_name:
            comp_name = f"Component{len(components)+1}"

        # Deduplicate by semantic name — if we already have a component with the
        # same name AND same category, skip (prefer the first/largest instance).
        # Only append index if the name genuinely conflicts across categories.
        if comp_name in components:
            existing_cat = components[comp_name].get('category', '')
            if existing_cat == category:
                # Same semantic component, different selector — keep the first
                continue
            comp_name = f"{comp_name}{len(components)+1}"

        # Code snippets (trimmed for size)
        code = blue.get('code', {})
        css_snippet = code.get('css', '')[:500] if code.get('css') else ''
        react_snippet = code.get('react', '')[:800] if code.get('react') else ''

        components[comp_name] = {
            'description': _build_component_description(disc, blue),
            'category': category,
            'selector': selector,
            'props': _infer_props(disc, blue),
            'visual': {
                k: v for k, v in (blue.get('visual') or {}).items()
                if v and v not in ('none', 'normal', '0px', 'auto')
            },
            'layout': blue.get('layout') or {},
            'behavior': {
                'requiresJavaScript': bool(
                    (blue.get('javascript') or {}).get('requiresJavaScript')),
                'interactive': bool(
                    (blue.get('interactivity') or {}).get('transition', 'none') not in ('none', '')),
            },
            'codeSnippets': {
                k: v for k, v in {'css': css_snippet, 'react': react_snippet}.items() if v
            },
        }

    # Also add synthetic fallbacks if blueprints is empty
    for synth in blueprints_synthetic:
        comp_name = re.sub(r'[^a-zA-Z0-9]', '', synth['label'])
        components[comp_name] = {
            'description': synth.get('description', synth['label']),
            'category': synth.get('category', 'section'),
            'props': _infer_props({'category': synth.get('category', '')}, {}),
        }

    # ── 3. Page Patterns (spatial composition) ────────────────────────────────
    page_patterns = {}
    sc = evidence.get('spatial_composition', {})
    page_struct = sc.get('page_structure', {})
    pattern_type = page_struct.get('pattern_type', '')

    if pattern_type:
        # Derive a zone sequence from the component list + pattern type
        comp_names = list(components.keys())
        page_patterns['default'] = {
            'description': pattern_type,
            'zones': comp_names,
        }

    # Whitespace profile
    ws = sc.get('whitespace_analysis', {})
    if ws.get('interpretation'):
        page_patterns['whitespace'] = {
            'density': ws.get('interpretation', 'balanced'),
            'breathingRoom': ws.get('breathing_room_score', 0),
        }

    # ── 4. Example Spec ────────────────────────────────────────────────────────
    # Build a minimal but real flat spec using the discovered components
    example_spec = {'root': 'page', 'elements': {}}
    comp_names = list(components.keys())

    example_spec['elements']['page'] = {
        'type': 'Page',
        'props': {'className': 'page-root'},
        'children': [c[0].lower() + c[1:] for c in comp_names],
    }

    for comp_name in comp_names:
        comp_def = components[comp_name]
        element_id = comp_name[0].lower() + comp_name[1:]
        category = comp_def.get('category', 'section')

        # Build minimal example props
        ex_props = {}
        props_def = comp_def.get('props', {})
        for prop_name, prop_def in props_def.items():
            if prop_name == 'children':
                continue
            if prop_def.get('required') or prop_name in (
                'headline', 'ctaText', 'logo', 'links', 'items', 'title', 'submitText'
            ):
                if prop_def.get('type') == 'string':
                    ex_props[prop_name] = f'{{/* {prop_name} */}}'
                elif prop_def.get('type') == 'array':
                    ex_props[prop_name] = []
                elif prop_def.get('type') == 'number':
                    ex_props[prop_name] = 3
                elif prop_def.get('type') == 'boolean':
                    ex_props[prop_name] = False

        example_spec['elements'][element_id] = {
            'type': comp_name,
            'props': ex_props,
            'children': [],
        }

    # ── 5. Brand context ───────────────────────────────────────────────────────
    brand = evidence.get('brand_personality', {})
    tone = brand.get('tone', 'Professional')
    energy = brand.get('energy', 'Confident')
    audience = brand.get('target_audience', '')
    signals = brand.get('signals', [])
    signal_str = '; '.join(s.split('→')[0].strip() for s in signals[:3]) if signals else ''

    # CSS sophistication
    css_an = evidence.get('css_analytics', {})
    soph_score = css_an.get('sophistication_score', '')
    modern_features = css_an.get('modern_features', {})
    active_modern = [k for k, v in modern_features.items() if isinstance(v, bool) and v]

    # ── 6. System Prompt ───────────────────────────────────────────────────────
    color_summary = ', '.join(
        f"{k}: {v}" for k, v in list(tok_colors.items())[:4]
    ) if tok_colors else 'not extracted'

    typo_summary = f"{heading_font or 'system-ui'} (heading), {body_font or 'system-ui'} (body)" if (heading_font or body_font) else 'system-ui'

    system_prompt = (
        f"You are a UI generator for {site_name}. "
        f"Use ONLY the components defined in this catalog's `components` field. "
        f"Apply design tokens from `tokens` consistently — do not invent new colors, fonts, or spacing values. "
        f"\n\nBrand: {tone} / {energy}. "
    )
    if audience:
        system_prompt += f"Target audience: {audience}. "
    if signal_str:
        system_prompt += f"Design signals: {signal_str}. "
    system_prompt += (
        f"\n\nDesign tokens summary: colors ({color_summary}). "
        f"Typography: {typo_summary}. "
    )
    if tok_spacing:
        system_prompt += f"Spacing base: {tok_spacing.get('base', tok_spacing.get('xs', 'unknown'))}. "
    if soph_score:
        system_prompt += f"CSS sophistication: {soph_score}/100. "
    if active_modern:
        system_prompt += f"Modern CSS features in use: {', '.join(active_modern[:5])}. "
    system_prompt += (
        f"\n\nOutput a valid json-render Spec JSON with `root` and `elements` map. "
        f"Each element must reference a component from the catalog by its exact `type` name. "
        f"Validate all props against the component's `props` schema. "
        f"Do not use components not in this catalog."
    )

    # ── Assemble final catalog ─────────────────────────────────────────────────
    arch = evidence.get('site_architecture', {})
    return {
        'version': '1.0',
        'format': 'json-render-catalog',
        'site': site_name,
        'generated': today,
        'source_url': url,
        'meta': {
            'framework': arch.get('framework', ''),
            'css_framework': arch.get('css_framework', ''),
            'sophistication_score': soph_score,
            'component_count': len(components),
            'token_categories': list(tokens.keys()),
        },
        'tokens': tokens,
        'components': components,
        'page_patterns': page_patterns,
        'example_spec': example_spec,
        'system_prompt': system_prompt,
    }


@app.route('/api/export-figma-spec', methods=['POST'])
def export_figma_spec():
    """Export unified Figma Make specification — markdown with embedded JSON tokens"""
    data = request.json
    evidence = data.get('evidence')
    if not evidence:
        return jsonify({'error': 'No evidence data provided'}), 400
    result = generate_figma_spec(evidence)
    return jsonify({'success': True, 'markdown': result['markdown'], 'tokens': result['tokens']})


def generate_figma_spec(evidence):
    """Generate unified Figma Make spec: markdown brief + embedded JSON design tokens.

    Designed to be pasted directly into Figma Make as a design system prompt.
    Also produces a standalone tokens JSON for JSON Crack visualization.
    Target size: <15KB for LLM context compatibility.
    """
    import json as _json
    from urllib.parse import urlparse

    meta = evidence.get('meta_info', {})
    url = meta.get('url', 'Unknown')
    parsed = urlparse(url)
    site_name = parsed.hostname or 'Unknown'
    site_name = site_name.replace('www.', '').split('.')[0].title()

    # --- Build tokens dict ---
    tokens = {}

    # Colors
    colors_data = evidence.get('colors', {})
    palette = colors_data.get('palette', {})
    roles = colors_data.get('color_roles', {})
    color_tokens = {}
    if isinstance(palette, dict):
        for bucket in ['primary', 'secondary', 'intentional']:
            items = palette.get(bucket, [])
            if isinstance(items, list):
                hexes = []
                for c in items[:6]:
                    if isinstance(c, str):
                        hexes.append(c)
                    elif isinstance(c, dict) and c.get('hex'):
                        hexes.append(c['hex'])
                if hexes:
                    color_tokens[bucket] = hexes
    if isinstance(roles, dict):
        clean_roles = {}
        for k, v in roles.items():
            if isinstance(v, str) and (v.startswith('#') or v.startswith('rgb')):
                clean_roles[k] = v
        if clean_roles:
            color_tokens['roles'] = clean_roles
    tokens['colors'] = color_tokens

    # Typography
    typo = evidence.get('typography', {})
    details = typo.get('details', {})
    type_scale = typo.get('type_scale', {})
    typo_tokens = {}
    families = details.get('font_families', [])
    if families:
        typo_tokens['families'] = families[:4]
    if isinstance(type_scale, dict):
        if type_scale.get('sizes_px'):
            typo_tokens['sizes'] = type_scale['sizes_px'][:8]
        if type_scale.get('ratio'):
            typo_tokens['ratio'] = type_scale['ratio']
    weights = details.get('font_weights', [])
    if weights:
        typo_tokens['weights'] = weights[:5]
    body = details.get('body_text', {})
    if isinstance(body, dict):
        typo_tokens['body'] = {
            'size': body.get('size', '16px'),
            'lineHeight': body.get('line_height', '1.5'),
        }
    tokens['typography'] = typo_tokens

    # Spacing
    spacing = evidence.get('spacing_scale', {})
    spacing_tokens = {}
    scale = spacing.get('scale', spacing.get('values', []))
    if scale:
        spacing_tokens['scale'] = [str(v) if isinstance(v, (int, float)) else v for v in scale[:10]]
    if spacing.get('base_unit'):
        spacing_tokens['base'] = str(spacing['base_unit'])
    tokens['spacing'] = spacing_tokens

    # Border radius
    radius = evidence.get('border_radius_scale', {})
    radius_vals = radius.get('scale', radius.get('values', []))
    if radius_vals:
        tokens['borderRadius'] = [str(v) if isinstance(v, (int, float)) else v for v in radius_vals[:6]]

    # Shadows
    shadows = evidence.get('shadow_system', {})
    levels = shadows.get('levels', [])
    if levels:
        tokens['shadows'] = [{'name': s.get('name', f'shadow-{i}'), 'value': s.get('value', '')}
                             for i, s in enumerate(levels[:5]) if isinstance(s, dict)]

    # Motion
    motion = evidence.get('motion_tokens', {})
    motion_tokens = {}
    dur_scale = motion.get('duration_scale', {})
    if isinstance(dur_scale, dict) and dur_scale.get('values'):
        motion_tokens['durations'] = [f"{v}ms" for v in dur_scale['values'][:5]]
    easing_pal = motion.get('easing_palette', {})
    if isinstance(easing_pal, dict):
        curves = easing_pal.get('curves', [])
        if curves:
            motion_tokens['easings'] = [{'value': c.get('value', ''), 'role': c.get('role', '')}
                                        for c in curves[:4]]
    if motion_tokens:
        tokens['motion'] = motion_tokens

    # --- Build markdown ---
    md = f"# {site_name} Design System Specification\n"
    md += f"> Source: {url} | Confidence: {evidence.get('_meta', {}).get('overall_confidence', '?')}%\n\n"

    # Design brief
    playbook = evidence.get('design_playbook', {})
    brand = evidence.get('brand_personality', {})
    layout_syn = evidence.get('layout_synthesis', {})
    brief_parts = []
    if isinstance(playbook, dict):
        findings = playbook.get('findings', [])
        if isinstance(findings, list):
            for f in findings[:2]:
                if isinstance(f, dict) and f.get('summary'):
                    brief_parts.append(f['summary'])
                elif isinstance(f, str):
                    brief_parts.append(f)
    if isinstance(brand, dict) and brand.get('personality_summary'):
        brief_parts.append(brand['personality_summary'])
    if isinstance(layout_syn, dict) and layout_syn.get('layout_narrative'):
        brief_parts.append(layout_syn['layout_narrative'][:200])
    if brief_parts:
        md += "## Design Brief\n"
        md += ' '.join(brief_parts[:3]) + "\n\n"

    # Tokens as JSON blocks
    md += "## Design Tokens\n\n"

    if tokens.get('colors'):
        md += "### Colors\n```json\n"
        md += _json.dumps(tokens['colors'], indent=2) + "\n```\n\n"

    if tokens.get('typography'):
        md += "### Typography\n```json\n"
        md += _json.dumps(tokens['typography'], indent=2) + "\n```\n\n"

    if tokens.get('spacing'):
        md += "### Spacing\n```json\n"
        md += _json.dumps(tokens['spacing'], indent=2) + "\n```\n\n"

    if tokens.get('borderRadius'):
        md += "### Border Radius\n```json\n"
        md += _json.dumps(tokens['borderRadius'], indent=2) + "\n```\n\n"

    if tokens.get('shadows'):
        md += "### Shadows\n```json\n"
        md += _json.dumps(tokens['shadows'], indent=2) + "\n```\n\n"

    if tokens.get('motion'):
        md += "### Motion\n```json\n"
        md += _json.dumps(tokens['motion'], indent=2) + "\n```\n\n"

    # Layout system
    spatial = evidence.get('spatial_composition', {})
    layout = evidence.get('layout', {})
    breakpoints = evidence.get('responsive_breakpoints', {})
    md += "## Layout System\n"
    page_struct = spatial.get('page_structure', {})
    if isinstance(page_struct, dict) and page_struct.get('pattern_type'):
        md += f"- **Pattern:** {page_struct['pattern_type']}\n"
    if isinstance(layout, dict) and layout.get('pattern'):
        md += f"- **Engine:** {layout['pattern']}\n"
    ws = spatial.get('whitespace_analysis', {})
    if isinstance(ws, dict) and ws.get('interpretation'):
        md += f"- **Density:** {ws['interpretation']}\n"
    bp_details = breakpoints.get('details', breakpoints)
    if isinstance(bp_details, dict):
        bps = bp_details.get('breakpoints', [])
        if bps:
            bp_vals = [str(b.get('value', b) if isinstance(b, dict) else b) + 'px' for b in bps[:6]]
            md += f"- **Breakpoints:** {', '.join(bp_vals)}\n"
    md += "\n"

    # Component library (top 5)
    blueprints = evidence.get('component_blueprints', {})
    if isinstance(blueprints, dict):
        bps_list = blueprints.get('blueprints', [])
        if bps_list:
            md += "## Component Library\n\n"
            for bp in bps_list[:5]:
                disc = bp.get('discovery', {})
                blue = bp.get('blueprint', {})
                label = disc.get('label', disc.get('category', 'Component'))
                selector = disc.get('selector', '?')
                bounds = disc.get('bounds', {})
                w = bounds.get('width', '?')
                h = bounds.get('height', '?')
                cs = blue.get('computedStyles', {})
                display = cs.get('display', '')
                flex_dir = cs.get('flexDirection', '')
                layout_desc = display
                if flex_dir:
                    layout_desc += f', {flex_dir}'
                md += f"### {label}\n"
                md += f"- **Selector:** `{selector}`\n"
                md += f"- **Size:** {w} x {h}px\n"
                if layout_desc:
                    md += f"- **Layout:** {layout_desc}\n"
                bg = cs.get('backgroundColor', '')
                color = cs.get('color', '')
                if bg:
                    md += f"- **Background:** {bg}\n"
                if color:
                    md += f"- **Color:** {color}\n"
                md += "\n"

    # Page zones
    box_model = evidence.get('box_model_export', {})
    zones = box_model.get('zones', [])
    if zones:
        md += "## Page Zones\n\n"
        md += "| Zone | Size | Layout | Key Properties |\n"
        md += "|------|------|--------|----------------|\n"
        for z in zones[:8]:
            zone_type = z.get('type', '?')
            w_vw = z.get('widthVw', '?')
            h_px = z.get('height', '?')
            disp = z.get('display', '')
            flex_d = z.get('flexDirection', '')
            props = []
            if z.get('gap'):
                props.append(f"gap: {z['gap']}")
            if z.get('padding'):
                props.append(f"padding: {z['padding']}")
            if z.get('zIndex') and str(z.get('zIndex', '0')) != '0':
                props.append(f"z-index: {z['zIndex']}")
            layout_str = disp
            if flex_d:
                layout_str += f' {flex_d}'
            md += f"| {zone_type} | {w_vw}vw x {h_px}px | {layout_str} | {', '.join(props) or '—'} |\n"
        md += "\n"

    md += "---\n"
    md += f"*Generated by Web Intelligence Scraper for Figma Make*\n"

    return {'markdown': md, 'tokens': tokens}


@app.route('/api/generate-summary', methods=['POST'])
def generate_ai_summary():
    """
    Generate plain English summary using Claude API

    Input: Full evidence JSON from deep scan
    Output: 3-5 sentence executive summary
    """
    try:
        evidence = request.json.get('evidence')

        if not evidence:
            return jsonify({'error': 'No evidence provided'}), 400

        # Check if anthropic is available and API key is configured
        if not ANTHROPIC_AVAILABLE or not anthropic_client:
            return jsonify({
                'error': 'Anthropic client unavailable',
                'summary': '📝 AI summary unavailable on this system.',
                'generated_at': datetime.now().isoformat()
            }), 400
        if not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") == "your_api_key_here":
            return jsonify({
                'error': 'Anthropic API key not configured',
                'summary': '📝 AI summary requires an Anthropic API key. Add ANTHROPIC_API_KEY to your .env file.',
                'generated_at': datetime.now().isoformat()
            }), 400

        # Extract key metrics for summary
        summary_context = {
            'url': evidence.get('meta_info', {}).get('url', 'Unknown'),
            'colors_count': len(evidence.get('colors', {}).get('primary_colors', [])),
            'typography_families': len(evidence.get('typography', {}).get('font_families', [])),
            'typography_sizes': len(evidence.get('typography', {}).get('font_sizes', [])),
            'spacing_scale': evidence.get('spacing_scale', {}).get('scale', []),
            'breakpoints': len(evidence.get('responsive_breakpoints', {}).get('breakpoints', [])),
            'shadow_levels': len(evidence.get('shadow_system', {}).get('elevation_levels', [])),
            'layout_type': evidence.get('layout_system', {}).get('primary_layout_type', 'Unknown'),
            'hero_count': len(evidence.get('visual_hierarchy', {}).get('hero_sections', [])),
            'cta_count': len(evidence.get('visual_hierarchy', {}).get('ctas', [])),
        }

        # Use plain language summaries if available
        summaries_available = []
        if evidence.get('shadow_system', {}).get('summary'):
            summaries_available.append(f"Shadows: {evidence['shadow_system']['summary']['description']}")
        if evidence.get('colors', {}).get('summary'):
            summaries_available.append(f"Colors: {evidence['colors']['summary']['description']}")
        if evidence.get('spacing_scale', {}).get('summary'):
            summaries_available.append(f"Spacing: {evidence['spacing_scale']['summary']['description']}")

        # Build summaries section (avoid backslash in f-string)
        summaries_section = ''
        if summaries_available:
            summaries_section = 'Metric Summaries:\n' + '\n'.join(summaries_available)

        prompt = f"""You are a design system analyst explaining findings to a non-technical audience.

Based on this website analysis:

URL: {summary_context['url']}

Quick Stats:
• Colors: {summary_context['colors_count']} primary colors
• Typography: {summary_context['typography_families']} font families, {summary_context['typography_sizes']} text sizes
• Spacing: {len(summary_context['spacing_scale'])} spacing increments
• Breakpoints: {summary_context['breakpoints']} responsive breakpoints
• Shadows: {summary_context['shadow_levels']} elevation levels
• Layout: {summary_context['layout_type']}
• Visual Hierarchy: {summary_context['hero_count']} hero sections, {summary_context['cta_count']} CTAs

{summaries_section}

Generate a 3-5 sentence summary that:
1. Highlights the most important findings
2. Uses plain language (no jargon like "z-index", "DOM", "heuristics")
3. Mentions design system consistency (strict vs flexible)
4. Includes ONE actionable recommendation

Format:
📝 This site has:
• [Key finding 1]
• [Key finding 2]
• [Key finding 3]

Recommendation: [One actionable insight based on the evidence]

Keep it concise and valuable for designers/PMs."""

        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        summary_text = response.content[0].text

        return jsonify({
            'summary': summary_text,
            'generated_at': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"AI summary generation failed: {e}", exc_info=True)
        return jsonify({
            'error': 'Summary generation failed',
            'summary': '📝 AI summary could not be generated. Please check server logs for details.'
        }), 500


@app.route('/api/generate-starter-template', methods=['POST'])
def generate_starter_template():
    """
    Generate starter HTML template from deep scan evidence

    Request body:
    {
        "evidence": {...}  # Evidence from deep-scan endpoint
    }

    Returns: HTML string ready to save as starter.html
    """
    from starter_template_generator import StarterTemplateGenerator

    data = request.json
    evidence = data.get('evidence')

    if not evidence:
        return jsonify({'error': 'Evidence data required'}), 400

    try:
        generator = StarterTemplateGenerator(evidence)
        html = generator.generate()

        return jsonify({
            'success': True,
            'html': html,
            'size': len(html),
            'message': 'Starter template generated successfully'
        })

    except Exception as e:
        logger.error(f"Error generating starter template: {e}", exc_info=True)
        return jsonify({
            'error': 'Starter template generation failed. Check server logs for details.'
        }), 500


@app.route('/api/generate-design-brief', methods=['POST'])
def generate_design_brief():
    """
    Generate design brief from deep scan evidence

    Request body:
    {
        "evidence": {...}  # Evidence from deep-scan endpoint
    }

    Returns: Design brief object with sections
    """
    from design_brief_generator import DesignBriefGenerator

    data = request.json
    evidence = data.get('evidence')

    if not evidence:
        return jsonify({'error': 'Evidence data required'}), 400

    try:
        generator = DesignBriefGenerator(evidence)
        brief = generator.generate()

        return jsonify({
            'success': True,
            'brief': brief,
            'message': 'Design brief generated successfully'
        })

    except Exception as e:
        logger.error(f"Error generating design brief: {e}", exc_info=True)
        return jsonify({
            'error': 'Design brief generation failed. Check server logs for details.'
        }), 500


@app.route('/api/full-analysis', methods=['POST'])
def full_analysis():
    """
    Complete analysis workflow: deep scan + starter template + design brief

    Request body:
    {
        "site_url": "https://stripe.com",
        "analysis_mode": "single"  # or "smart-nav"
    }

    Returns: Evidence + starter HTML + design brief all in one
    """
    from starter_template_generator import StarterTemplateGenerator
    from design_brief_generator import DesignBriefGenerator

    data = request.json
    site_url = data.get('site_url')
    analysis_mode = data.get('analysis_mode', 'single')

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🎯 FULL ANALYSIS: {site_url}")
        print(f" 📊 Mode: {analysis_mode}")
        print('='*70)

        async def run_full():
            # Step 1: Deep scan
            print("\n1️⃣  Running deep scan...")
            engine = _get_engine_class()(site_url, analysis_mode=analysis_mode)
            evidence = await engine.extract_all()
            return {k: v for k, v in evidence.items() if v is not None}

        cleaned_evidence = run_async(run_full())

        # Step 2: Generate starter template
        print("2️⃣  Generating starter template...")
        template_generator = StarterTemplateGenerator(cleaned_evidence)
        starter_html = template_generator.generate()

        # Step 3: Generate design brief
        print("3️⃣  Generating design brief...")
        brief_generator = DesignBriefGenerator(cleaned_evidence)
        design_brief = brief_generator.generate()

        print("\n✅ Full analysis complete!")

        return jsonify({
            'success': True,
            'evidence': cleaned_evidence,
            'starter_html': starter_html,
            'design_brief': design_brief,
            'message': 'Complete analysis finished - evidence, starter template, and design brief ready'
        })

    except Exception as e:
        logger.error(f"Error during full analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Full analysis failed. Check server logs for details.'
        }), 500


@app.route('/api/export-dtcg-tokens', methods=['POST'])
def export_dtcg_tokens():
    """
    Export design tokens in W3C DTCG format

    Request body:
    {
        "evidence": {...}  # Evidence from deep-scan
    }

    Returns: DTCG-compliant JSON tokens
    """
    from dtcg_token_exporter import DTCGTokenExporter

    data = request.json
    evidence = data.get('evidence')

    if not evidence:
        return jsonify({'error': 'Evidence data required'}), 400

    try:
        exporter = DTCGTokenExporter(evidence)
        tokens = exporter.export()
        token_counts = exporter.get_token_count()

        return jsonify({
            'success': True,
            'tokens': tokens,
            'token_counts': token_counts,
            'message': 'DTCG tokens exported successfully'
        })

    except Exception as e:
        logger.error(f"Error exporting DTCG tokens: {e}", exc_info=True)
        return jsonify({'error': 'DTCG token export failed. Check server logs for details.'}), 500


@app.route('/api/export-tailwind-config', methods=['POST'])
def export_tailwind_config():
    """
    Export Tailwind CSS configuration

    Request body:
    {
        "evidence": {...}  # Evidence from deep-scan
    }

    Returns: tailwind.config.js as string
    """
    from tailwind_config_generator import TailwindConfigGenerator

    data = request.json
    evidence = data.get('evidence')

    if not evidence:
        return jsonify({'error': 'Evidence data required'}), 400

    try:
        generator = TailwindConfigGenerator(evidence)
        config = generator.generate()

        return jsonify({
            'success': True,
            'config': config,
            'size': len(config),
            'message': 'Tailwind config generated successfully'
        })

    except Exception as e:
        logger.error(f"Error generating Tailwind config: {e}", exc_info=True)
        return jsonify({'error': 'Tailwind config generation failed. Check server logs for details.'}), 500


@app.route('/api/compare-sites', methods=['POST'])
def compare_sites():
    """
    Compare design systems of two sites

    Request body:
    {
        "site_a": "https://stripe.com",
        "site_b": "https://tailwindcss.com",
        "site_a_name": "Stripe",  # Optional
        "site_b_name": "Tailwind"  # Optional
    }

    Returns: Detailed comparison with differences
    """
    from design_system_differ import DesignSystemDiffer

    data = request.json
    site_a_url = data.get('site_a')
    site_b_url = data.get('site_b')
    site_a_name = data.get('site_a_name', 'Site A')
    site_b_name = data.get('site_b_name', 'Site B')

    site_a_url, err_a = validate_url(site_a_url)
    if err_a:
        return jsonify({'error': f'site_a: {err_a}'}), 400

    site_b_url, err_b = validate_url(site_b_url)
    if err_b:
        return jsonify({'error': f'site_b: {err_b}'}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔍 SITE COMPARISON")
        print(f" A: {site_a_url}")
        print(f" B: {site_b_url}")
        print('='*70)

        import time as _time

        async def run_compare():
            # Check cache first — reuse recent scans
            cache_a = _evidence_cache.get(site_a_url)
            cache_b = _evidence_cache.get(site_b_url)
            now = _time.time()

            if cache_a and (now - cache_a['timestamp']) < _CACHE_TTL:
                print(f"\n1️⃣  Site A: using cached evidence ({int(now - cache_a['timestamp'])}s old)")
                ev_a = cache_a['evidence']
            else:
                print("\n1️⃣  Analyzing Site A...")
                engine_a = _get_engine_class()(site_a_url, analysis_mode='single')
                ev_a = await engine_a.extract_all()
                _evidence_cache[site_a_url] = {'evidence': ev_a, 'timestamp': now}

            if cache_b and (now - cache_b['timestamp']) < _CACHE_TTL:
                print(f"\n2️⃣  Site B: using cached evidence ({int(now - cache_b['timestamp'])}s old)")
                ev_b = cache_b['evidence']
            else:
                print("\n2️⃣  Analyzing Site B...")
                engine_b = _get_engine_class()(site_b_url, analysis_mode='single')
                ev_b = await engine_b.extract_all()
                _evidence_cache[site_b_url] = {'evidence': ev_b, 'timestamp': now}

            return ev_a, ev_b

        evidence_a, evidence_b = run_async(run_compare())

        # Compare
        print("\n3️⃣  Comparing design systems...")
        differ = DesignSystemDiffer(evidence_a, evidence_b, site_a_name, site_b_name)
        comparison = differ.compare()

        print("\n✅ Comparison complete!")

        return jsonify({
            'success': True,
            'comparison': comparison,
            'site_a_evidence': evidence_a,
            'site_b_evidence': evidence_b,
            'message': 'Design system comparison complete'
        })

    except Exception as e:
        logger.error(f"Error during comparison: {e}", exc_info=True)
        return jsonify({'error': 'Site comparison failed. Check server logs for details.'}), 500


@app.route('/api/extract-component-library', methods=['POST'])
def extract_component_library():
    """
    Extract multiple components in batch mode

    Request body:
    {
        "site_url": "https://stripe.com",
        "selectors": ["nav", ".hero", "footer", ".pricing-card"]
    }

    Returns: Dictionary of component blueprints
    """
    data = request.json
    site_url = data.get('site_url')
    selectors = data.get('selectors', [])

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    if not selectors or not isinstance(selectors, list):
        return jsonify({'error': 'selectors must be a non-empty array'}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔬 COMPONENT LIBRARY EXTRACTION")
        print(f" URL: {site_url}")
        print(f" Components: {len(selectors)}")
        print('='*70)

        ripper = _get_ripper_class()(site_url)
        components = run_async(ripper.rip_batch(selectors))

        print("\n✅ Component library extraction complete!")

        return jsonify({
            'success': True,
            'components': components,
            'count': len(components),
            'message': f'Extracted {len(components)} components'
        })

    except Exception as e:
        logger.error(f"Error during component extraction: {e}", exc_info=True)
        return jsonify({'error': 'Component library extraction failed. Check server logs for details.'}), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print(" 🔍 WEB INTELLIGENCE DASHBOARD")
    print("="*70)
    print("\n   Starting server...")
    print("\n   Open your browser and go to:")
    print("\n   👉 http://localhost:8080")
    print("\n   Features:")
    print("      • 20+ Metric Categories")
    print("      • Layout, Typography, Colors, Animations")
    print("      • Accessibility, Performance, SEO, Security")
    print("      • API Pattern Detection")
    print("      • CSS Tricks & Advanced Techniques")
    print("      • Article Content Extraction")
    print("      • Confidence Scoring")
    print("      • Markdown Export")
    print("      • Debug View with Network Traces")
    print("      • Analytics Dashboard")
    print("\n   Example Sites to Test:")
    print("      • https://nts.live")
    print("      • https://ssense.com")
    print("      • https://stripe.com/docs")
    print("      • https://css-tricks.com/article")
    print("\n" + "="*70 + "\n")

    # Kill old servers
    import subprocess

    logging.basicConfig(level=logging.INFO)

    try:
        subprocess.run(['pkill', '-f', 'web_interface'], check=False)
    except Exception as e:
        logger.debug(f"Could not kill old servers (non-critical): {e}")

    # Bind to localhost only — never expose to network with debug=True
    app.run(debug=True, port=8080, host='127.0.0.1', threaded=True)
