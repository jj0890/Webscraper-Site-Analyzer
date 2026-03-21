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
from deep_evidence_engine import DeepEvidenceEngine
from component_ripper import ComponentRipper
from computed_style_extractor import ComputedStyleExtractor
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
    analysis_mode = data.get('analysis_mode', 'single')  # 'single' or 'smart-nav'

    site_url, url_error = validate_url(site_url)
    if url_error:
        return jsonify({'error': url_error}), 400

    try:
        print(f"\n{'='*70}")
        print(f" 🔍 DEEP SCAN: {site_url}")
        print(f" 📊 Mode: {analysis_mode}")
        print('='*70)

        discovery_method = data.get('discovery_method', 'auto')
        engine = DeepEvidenceEngine(site_url, analysis_mode=analysis_mode, discovery_method=discovery_method)
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

        return jsonify({
            'success': True,
            'evidence': cleaned_evidence
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
        if include_states:
            print(f"    States: enabled")
        if output_format == 'figma':
            print(f"    Output: Figma-compatible markdown")
        print('='*70)

        ripper = ComponentRipper(site_url, selector)
        blueprint = run_async(ripper.rip(auth_state, include_states=include_states, output_format=output_format))

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

        ripper = ComponentRipper(site_url)
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
        ripper = ComponentRipper(site_url, selector)
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
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                page.set_default_timeout(60000)

                # Load page
                await page.goto(site_url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)

                # Create extractor
                extractor = ComputedStyleExtractor(page)

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
                engine = DeepEvidenceEngine(site_url, analysis_mode='single')
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
                engine = DeepEvidenceEngine(site_url)

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
        engine = DeepEvidenceEngine(site_url, analysis_mode='interactive')
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

        engine = DeepEvidenceEngine(site_url, analysis_mode='interactive')
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
                    engine = DeepEvidenceEngine(url)
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
            engine = DeepEvidenceEngine(site_url, analysis_mode=analysis_mode)
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

        async def run_compare():
            # Analyze both sites
            print("\n1️⃣  Analyzing Site A...")
            engine_a = DeepEvidenceEngine(site_a_url, analysis_mode='single')
            evidence_a = await engine_a.extract_all()

            print("\n2️⃣  Analyzing Site B...")
            engine_b = DeepEvidenceEngine(site_b_url, analysis_mode='single')
            evidence_b = await engine_b.extract_all()

            return evidence_a, evidence_b

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

        ripper = ComponentRipper(site_url)
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
    app.run(debug=True, port=8080, host='127.0.0.1')
