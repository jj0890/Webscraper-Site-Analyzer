"""
Deep Evidence Engine - Extract 20+ Metrics

Instead of just 5 basic metrics, we extract EVERYTHING:
- Layout Analysis (Grid, Flexbox, Positioning)
- Typography (Fonts, Sizes, Weights, Line Heights)
- Color Palette (Primary, Secondary, Accents)
- Animations & Transitions (CSS animations, JS libraries)
- Accessibility (ARIA, Semantic HTML, Contrast Ratios)
- Performance (Load Time, Resource Sizes, Render Blocking)
- SEO (Meta tags, Open Graph, Schema.org)
- Security (HTTPS, CSP, CORS headers)
- API Patterns (REST, GraphQL, WebSocket)
- CSS Tricks (Custom Properties, @supports, Viewport units)
- Interactive Elements (Forms, Modals, Dropdowns)
- Third-Party Integrations (Analytics, CDNs, Fonts)
- Article Content Extraction (with confidence scoring)
"""

import asyncio
import time
from playwright.async_api import async_playwright
from urllib.parse import urlparse, urljoin
import json
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from design_system_metrics import DesignSystemMetrics
from color_palette_preview import ColorPalettePreview
from api_relationship_mapper import APIRelationshipMapper
from metadata_mri import MetadataMRI
from visual_hierarchy_analyzer import VisualHierarchyAnalyzer
from screenshot_annotator import ScreenshotAnnotator
from content_extractor import IntelligentContentExtractor
from component_mapper import ComponentMapper
from spatial_composition_analyzer import SpatialCompositionAnalyzer
from extractors.base import ExtractionContext
from extractors.cdp_animation_extractor import CdpAnimationExtractor
from extractors.axe_contrast_extractor import AxeContrastExtractor
from extractors.css_efficiency import CSSEfficiencyExtractor
from extractors.css_specificity import CSSSpecificityExtractor
from extractors.security import SecurityExtractor
from extractors.performance import PerformanceExtractor

# Import stealth mode for bot-protected sites
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  playwright-stealth not installed - bot detection bypass unavailable")


# Focus-to-extractor mapping for Smart Nav focused scans.
# Each focus maps to the set of evidence keys that should be extracted.
# None = run everything (full mode).
FOCUS_EXTRACTORS = {
    'layout': {
        'layout', 'dom_depth', 'site_architecture', 'interactive_elements', 'accessibility',
        'accessibility_tree',
        'visual_hierarchy', 'spatial_composition', 'component_map', 'content_extraction',
        'responsive_breakpoints', 'z_index_stack', 'visual_patterns',
        'meta_info', 'llm_helper', 'architecture_diagrams',
    },
    'design': {
        'typography', 'colors', 'css_tricks', 'animations',
        'spacing_scale', 'responsive_breakpoints', 'shadow_system',
        'z_index_stack', 'border_radius_scale',
        'motion_tokens', 'accessibility_tree',
        'meta_info', 'llm_helper',
    },
    'interaction': {
        'animations', 'interactive_elements', 'interaction_states', 'css_tricks', 'api_patterns',
        'motion_tokens', 'cdp_animations', 'contrast_a11y', 'accessibility_tree',
        'meta_info', 'llm_helper',
    },
    'architecture': {
        'site_architecture', 'api_patterns', 'performance', 'security', 'seo', 'third_party',
        'content_extraction', 'component_map', 'architecture_diagrams', 'accessibility_tree',
        'meta_info', 'llm_helper',
    },
    'full': None,
}


class DeepEvidenceEngine:
    """
    Comprehensive evidence extraction - 20+ metrics

    Supports two analysis modes:
    - 'single': Analyze just the provided URL (fast, 60s)
    - 'smart-nav': Analyze home + 2 nav links (comprehensive, 3-4min)
    """

    def __init__(self, url: str, analysis_mode: str = 'single', discovery_method: str = 'auto'):
        """
        Args:
            url: Starting URL to analyze
            analysis_mode: 'single' or 'smart-nav'
            discovery_method: 'auto' | 'cloudflare' | 'nav' — URL discovery source
        """
        self.url = url
        self.analysis_mode = analysis_mode
        self.discovery_method = discovery_method
        self.evidence = {}
        self._cloudflare_urls = []
        self._cloudflare_pages = {}

    def _add_statistical_fields(self, evidence: Dict, sample_size: int = None,
                                variance: float = None, observed: bool = True,
                                total_population: int = None) -> Dict:
        """
        Enrich evidence object with statistical fields

        Args:
            evidence: Existing evidence dict
            sample_size: Number of instances analyzed (e.g., 40 elements with box-shadow)
            variance: Statistical variance for numeric metrics
            observed: True if directly measured from DOM, False if inferred/heuristic
            total_population: Total elements on page (for context)

        Returns:
            Evidence dict with statistical fields added
        """
        if sample_size is not None:
            evidence['sample_size'] = sample_size

        if variance is not None:
            evidence['variance'] = round(variance, 2)

        # Mark as observed (direct measurement) vs inferred (heuristic/pattern)
        evidence['observed'] = observed

        if total_population is not None:
            evidence['total_population'] = total_population
            if sample_size is not None:
                evidence['coverage_pct'] = round((sample_size / total_population) * 100, 1)

        return evidence

    async def _discover_nav_links(self, page, base_url: str) -> List[str]:
        """
        Find primary navigation links from nav/header

        Returns:
            List of URLs like ['https://site.com/products', ...]
        """
        nav_links = await page.evaluate("""
            () => {
                // Strategy 1: Find <nav> element
                let navElement = document.querySelector('nav');

                // Strategy 2: Fall back to header
                if (!navElement) {
                    navElement = document.querySelector('header');
                }

                // Strategy 3: Fall back to top 100px of page
                if (!navElement) {
                    const topElements = Array.from(document.querySelectorAll('*'))
                        .filter(el => {
                            const rect = el.getBoundingClientRect();
                            return rect.top >= 0 && rect.top <= 100;
                        });
                    navElement = topElements[0]?.parentElement;
                }

                if (!navElement) return [];

                // Extract all links from nav area
                const links = Array.from(navElement.querySelectorAll('a[href]'))
                    .map(a => ({
                        href: a.href,
                        text: a.textContent?.trim() || '',
                        score: (
                            (a.textContent?.length || 0) +
                            (a.querySelector('svg, img') ? 5 : 0) +
                            (a.classList.contains('active') ? 10 : 0)
                        )
                    }))
                    .filter(link => link.href.startsWith(window.location.origin))
                    .filter(link => {
                        const path = new URL(link.href).pathname;
                        return path !== '/' && path !== '';
                    })
                    .filter(link => {
                        const text = link.text.toLowerCase();
                        const skipTerms = ['login', 'signup', 'sign in', 'cart', 'search', 'menu'];
                        return !skipTerms.some(term => text.includes(term));
                    });

                // Deduplicate and sort by prominence
                const seen = new Set();
                const unique = links.filter(link => {
                    if (seen.has(link.href)) return false;
                    seen.add(link.href);
                    return true;
                });

                unique.sort((a, b) => b.score - a.score);
                return unique.map(link => link.href);
            }
        """)

        return nav_links[:5]  # Return top 5

    async def _discover_deep_link(self, page, from_url: str) -> Optional[str]:
        """
        From a page, find a representative deep link

        Args:
            from_url: The page we're currently on

        Returns:
            URL to a deeper page, or None
        """
        deep_link = await page.evaluate("""
            () => {
                // Find main content (not header/nav/footer)
                const main = document.querySelector('main') ||
                             document.querySelector('[role="main"]') ||
                             document.querySelector('article') ||
                             document.body;

                // Get all links in main content
                const links = Array.from(main.querySelectorAll('a[href]'))
                    .map(a => ({
                        href: a.href,
                        hasImage: !!a.querySelector('img'),
                        pathDepth: new URL(a.href).pathname.split('/').filter(Boolean).length
                    }))
                    .filter(link => link.href.startsWith(window.location.origin))
                    .filter(link => link.href !== window.location.href)
                    .filter(link => link.pathDepth >= 2);

                // Prefer links with images, then deeper paths
                links.sort((a, b) => {
                    if (a.hasImage !== b.hasImage) {
                        return b.hasImage ? 1 : -1;
                    }
                    return b.pathDepth - a.pathDepth;
                });

                return links.length > 0 ? links[0].href : null;
            }
        """)

        return deep_link

    # ── Interactive Discovery ────────────────────────────────────────────

    async def _discover_interactive_links(self, page, base_url: str) -> Dict:
        """
        Click/hover through interactive navigation triggers on the current page
        to reveal hidden links (dropdowns, hamburger menus, mega-menus).

        Returns dict with static_links, interactive_links, interaction_log, and
        a deduplicated all_links list.
        """
        from urllib.parse import urlparse
        import asyncio as _aio

        parsed_base = urlparse(base_url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

        # Phase A: static baseline
        static_result = await self._discover_links(page, base_url)
        static_urls = set()
        static_links = []
        for link in static_result.get('all', []):
            url = link.get('url', link) if isinstance(link, dict) else link
            if url and url not in static_urls:
                static_urls.add(url)
                static_links.append({'url': url, 'text': link.get('text', '') if isinstance(link, dict) else '', 'source': 'static'})

        # Phase B: find interactive triggers in nav/header
        triggers = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();
                const navAreas = document.querySelectorAll('nav, header, [role="navigation"]');
                if (navAreas.length === 0) return results;

                const selectors = [
                    // ARIA triggers
                    '[aria-haspopup="menu"]',
                    '[aria-haspopup="true"]',
                    '[aria-expanded="false"]',
                    // Semantic triggers
                    'button',
                    '[role="button"]',
                    'details > summary',
                    // Class-based triggers
                    '[class*="dropdown-toggle"]',
                    '[class*="dropdown-trigger"]',
                    '[class*="hamburger"]',
                    '[class*="mobile-nav"]',
                    '[class*="menu-toggle"]',
                    '[class*="nav-toggle"]',
                ];

                for (const area of navAreas) {
                    for (const sel of selectors) {
                        for (const el of area.querySelectorAll(sel)) {
                            // Skip <a> with real href UNLESS it also has aria-haspopup/aria-expanded
                            // (many sites use <a href="/products" aria-haspopup="menu"> for dropdown triggers)
                            if (el.tagName === 'A' && el.href && !el.href.startsWith('javascript:') && el.href !== '#') {
                                if (!el.getAttribute('aria-haspopup') && el.getAttribute('aria-expanded') === null) continue;
                            }
                            // Skip invisible elements
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 && rect.height === 0) continue;

                            // Build a unique CSS selector for this element
                            let uid = '';
                            const nthIdx = Array.from(el.parentNode.children).indexOf(el) + 1;
                            if (el.id) {
                                uid = '#' + el.id;
                            } else if (el.getAttribute('aria-label')) {
                                uid = `[aria-label="${el.getAttribute('aria-label')}"]`;
                            } else {
                                // Use nth-child for uniqueness since class alone may match siblings
                                const parent = el.parentNode;
                                const parentSel = parent.id ? '#' + parent.id
                                    : parent.tagName.toLowerCase() + ':nth-child(' + (Array.from(parent.parentNode?.children || []).indexOf(parent) + 1) + ')';
                                uid = parentSel + ' > ' + el.tagName.toLowerCase() + ':nth-child(' + nthIdx + ')';
                            }

                            if (seen.has(uid)) continue;
                            seen.add(uid);

                            results.push({
                                selector: uid,
                                text: (el.textContent || '').trim().substring(0, 50),
                                tagName: el.tagName,
                                hasPopup: el.getAttribute('aria-haspopup') || null,
                                expanded: el.getAttribute('aria-expanded') || null
                            });
                        }
                    }
                }
                return results.slice(0, 20);  // Cap at 20 triggers
            }
        """)

        print(f"   🔍 Found {len(triggers)} interactive navigation triggers")

        interactive_links = []
        interaction_log = []

        # Phase C: click each trigger and collect newly-visible links
        async def _click_and_collect():
            for trigger in triggers:
                sel = trigger['selector']
                label = trigger['text'] or sel
                try:
                    # Snapshot current VISIBLE hrefs (checks offsetParent + visibility)
                    before = set(await page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .filter(a => {
                                const r = a.getBoundingClientRect();
                                const s = getComputedStyle(a);
                                return r.width > 0 && r.height > 0 &&
                                       s.visibility !== 'hidden' && s.opacity !== '0';
                            })
                            .map(a => a.href)
                            .filter(h => h.startsWith(window.location.origin))
                    """))

                    # Try hover first (many mega-menus are hover-triggered), then click
                    try:
                        await page.hover(sel, timeout=2000)
                    except Exception:
                        try:
                            await page.click(sel, timeout=2000)
                        except Exception:
                            continue

                    # Wait for CSS transition / menu reveal
                    await _aio.sleep(0.4)

                    # Optionally wait for aria-expanded="true"
                    try:
                        await page.wait_for_selector('[aria-expanded="true"]', timeout=300)
                    except Exception:
                        pass

                    # Snapshot VISIBLE hrefs again and diff (catches CSS-hidden→visible)
                    after = set(await page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .filter(a => {
                                const r = a.getBoundingClientRect();
                                const s = getComputedStyle(a);
                                return r.width > 0 && r.height > 0 &&
                                       s.visibility !== 'hidden' && s.opacity !== '0';
                            })
                            .map(a => a.href)
                            .filter(h => h.startsWith(window.location.origin))
                    """))

                    new_urls = after - before
                    if new_urls:
                        # Get text labels for new links
                        link_texts = await page.evaluate("""
                            (urls) => {
                                const map = {};
                                for (const a of document.querySelectorAll('a[href]')) {
                                    if (urls.includes(a.href)) {
                                        map[a.href] = (a.textContent || '').trim().substring(0, 80);
                                    }
                                }
                                return map;
                            }
                        """, list(new_urls))

                        for url in new_urls:
                            if url not in static_urls:
                                interactive_links.append({
                                    'url': url,
                                    'text': (link_texts or {}).get(url, ''),
                                    'source': f'dropdown:{label[:30]}'
                                })
                        interaction_log.append({
                            'trigger': sel,
                            'label': label[:50],
                            'action': 'hover',
                            'links_found': len(new_urls)
                        })
                        print(f"      ▸ {label[:30]}: {len(new_urls)} new links")

                    # Close the revealed menu
                    try:
                        await page.keyboard.press('Escape')
                        await _aio.sleep(0.15)
                    except Exception:
                        pass

                except Exception as e:
                    print(f"      ⚠ Trigger {sel[:40]} failed: {str(e)[:40]}")
                    continue

        # Wrap in 30s timeout
        try:
            await _aio.wait_for(_click_and_collect(), timeout=30)
        except _aio.TimeoutError:
            print("   ⏱  Interactive discovery hit 30s timeout")

        # Deduplicate all links
        all_urls = set()
        all_links = []
        for link in static_links + interactive_links:
            if link['url'] not in all_urls:
                all_urls.add(link['url'])
                all_links.append(link)

        print(f"   📊 Discovery: {len(static_links)} static + {len(interactive_links)} interactive = {len(all_links)} unique")

        return {
            'static_links': static_links,
            'interactive_links': interactive_links,
            'interaction_log': interaction_log,
            'all_links': all_links,
            'total_static': len(static_links),
            'total_interactive': len(interactive_links),
            'total_unique': len(all_links)
        }

    # ── URL Diversity Scoring ────────────────────────────────────────────

    def _score_url_diversity(self, urls: List[str], base_url: str) -> List[Dict]:
        """
        Score URLs by path diversity to enable intelligent page selection.
        Returns list sorted by diversity_score descending.
        """
        from urllib.parse import urlparse
        import re

        parsed_base = urlparse(base_url)
        scored = []

        # Group by first path segment
        segment_counts = {}
        for url in urls:
            parsed = urlparse(url)
            segments = [s for s in parsed.path.split('/') if s]
            first_seg = segments[0] if segments else '_root'
            segment_counts[first_seg] = segment_counts.get(first_seg, 0) + 1

        total_urls = len(urls)

        for url in urls:
            parsed = urlparse(url)
            if parsed.netloc != parsed_base.netloc:
                continue  # Skip external

            segments = [s for s in parsed.path.split('/') if s]
            first_seg = segments[0] if segments else '_root'
            depth = len(segments)

            # Score components
            # 1. Segment uniqueness: fewer URLs sharing this first segment = higher score
            group_size = segment_counts.get(first_seg, 1)
            uniqueness = 1.0 - (group_size / max(total_urls, 1))

            # 2. Depth bonus: deeper pages are more interesting (but diminishing returns)
            depth_score = min(depth / 4.0, 1.0)

            # 3. Pattern distinctness: slug-like final segments = instance page
            is_instance = bool(segments and re.search(r'[-_\d]', segments[-1]))
            is_listing = depth <= 2 and not is_instance

            # Prefer a mix: both listing and instance pages
            pattern_bonus = 0.1 if is_listing else 0.0

            diversity_score = (uniqueness * 0.5) + (depth_score * 0.3) + (pattern_bonus * 0.2)

            scored.append({
                'url': url,
                'path_segments': segments,
                'depth': depth,
                'template_group': first_seg,
                'is_instance': is_instance,
                'diversity_score': round(diversity_score, 3)
            })

        scored.sort(key=lambda x: x['diversity_score'], reverse=True)
        return scored

    def _select_diverse_pages(self, urls: List[str], base_url: str, max_pages: int = 5) -> Dict[str, str]:
        """
        Pick max_pages diverse URLs from the pool using greedy set-cover.
        Always includes base_url as 'home'.
        """
        result = {'home': base_url}
        remaining = [u for u in urls if u.rstrip('/') != base_url.rstrip('/')]

        if not remaining:
            return result

        scored = self._score_url_diversity(remaining, base_url)
        if not scored:
            return result

        selected_groups = set()
        page_num = 1

        for candidate in scored:
            if page_num >= max_pages:
                break

            # Penalize candidates whose template_group is already represented
            group = candidate['template_group']
            if group in selected_groups:
                # Still allow if nothing else is left, but skip if we have options
                remaining_unique = [s for s in scored
                                   if s['template_group'] not in selected_groups
                                   and s['url'] not in result.values()]
                if remaining_unique:
                    continue

            if candidate['url'] not in result.values():
                result[f'page_{page_num}'] = candidate['url']
                selected_groups.add(group)
                page_num += 1

        return result

    async def _smart_nav_sample(self, page, base_url: str) -> Dict[str, str]:
        """
        Diversity-based 3-point sampling via navigation.

        Discovers nav links (with optional lightweight interactive discovery),
        then selects the 3 most diverse pages by URL path structure.

        When Cloudflare is available and discovery_method permits, uses crawl
        data for a richer URL pool before falling through to nav discovery.

        Returns:
            {
                'home': 'https://site.com',
                'nav_1': 'https://site.com/products',
                'nav_2': 'https://site.com/docs'
            }
        """
        # ── Try Cloudflare discovery first (if configured) ──
        if self.discovery_method in ('cloudflare', 'auto'):
            cf_urls = await self._discover_via_cloudflare(base_url, limit=50)
            if cf_urls and len(cf_urls) > 5:
                print(f"   ☁️  Cloudflare discovered {len(cf_urls)} URLs")
                selected = self._select_diverse_pages(cf_urls, base_url, max_pages=3)
                result = {'home': base_url}
                for key, url in selected.items():
                    if key == 'home':
                        continue
                    result[f'nav_{len(result)}'] = url
                for label, url in result.items():
                    if label != 'home':
                        print(f"   📍 {label}: {url}")
                # Store crawled URLs for topology analysis later
                self._cloudflare_urls = cf_urls
                return result

        print("   🧭 Discovering navigation structure...")

        # Load home page
        await page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Discover visible nav links
        nav_links = await self._discover_nav_links(page, base_url)

        # Lightweight interactive pass: click up to 5 nav triggers to augment pool
        try:
            quick_triggers = await page.evaluate("""
                () => {
                    const navArea = document.querySelector('nav') || document.querySelector('header');
                    if (!navArea) return [];
                    const triggers = navArea.querySelectorAll(
                        '[aria-haspopup="menu"], [aria-haspopup="true"], [aria-expanded="false"], ' +
                        'button[class*="dropdown"], [class*="dropdown-toggle"]'
                    );
                    return Array.from(triggers).slice(0, 5).map(el => {
                        if (el.id) return '#' + el.id;
                        if (el.getAttribute('aria-label')) return '[aria-label="' + el.getAttribute('aria-label') + '"]';
                        if (el.className && typeof el.className === 'string')
                            return el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.');
                        return null;
                    }).filter(Boolean);
                }
            """)

            if quick_triggers:
                print(f"   🔍 Quick interactive pass: {len(quick_triggers)} triggers")
                for sel in quick_triggers[:5]:
                    try:
                        before = set(await page.evaluate(
                            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h.startsWith(window.location.origin))"
                        ))
                        await page.click(sel, timeout=2000)
                        await asyncio.sleep(0.3)
                        after = set(await page.evaluate(
                            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h.startsWith(window.location.origin))"
                        ))
                        new_urls = after - before - set(nav_links)
                        nav_links.extend(list(new_urls))
                        if new_urls:
                            print(f"      ▸ +{len(new_urls)} links from dropdown")
                        await page.keyboard.press('Escape')
                        await asyncio.sleep(0.15)
                    except Exception:
                        pass
        except Exception:
            pass  # Non-fatal — proceed with static nav links

        if not nav_links:
            print("   ⚠️  No nav links found, using home page only")
            return {'home': base_url}

        # Use diversity scoring to pick 3 best pages
        selected = self._select_diverse_pages(nav_links, base_url, max_pages=3)

        # Rename keys to nav_1/nav_2 for backward compatibility
        result = {'home': base_url}
        for key, url in selected.items():
            if key == 'home':
                continue
            idx = len(result)
            result[f'nav_{idx}'] = url

        for label, url in result.items():
            if label != 'home':
                print(f"   📍 {label}: {url}")

        return result

    async def _quick_discover(self, url: str) -> List[str]:
        """
        Lightweight URL discovery: open page, scrape all links, return list.
        Used by /api/site-topology when no URLs are pre-supplied.
        """
        from patchright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(2)
                links = await self._discover_links(page, url)
                raw_all = links.get('all', []) if isinstance(links, dict) else []
                # _discover_links().all contains {url, text, path} objects — extract URLs
                result = []
                for item in raw_all:
                    if isinstance(item, dict):
                        result.append(item.get('url', ''))
                    elif isinstance(item, str):
                        result.append(item)
                return [u for u in result if u]
            finally:
                await browser.close()

    async def _discover_via_cloudflare(self, url: str, limit: int = 50) -> List[str]:
        """Try Cloudflare crawl for URL discovery; returns [] if unavailable.

        Now does a FULL crawl (URLs + page content) and caches the content
        in self._cloudflare_pages for downstream use (topology, content
        classification, cross-site component detection).
        """
        try:
            from cloudflare_crawl import CloudflareCrawler, is_cloudflare_available
            if not is_cloudflare_available():
                return []
            print("   ☁️  Attempting Cloudflare URL discovery (full crawl)...")
            crawler = CloudflareCrawler()
            result = await crawler.crawl(url, limit=limit, depth=2,
                                         formats=['markdown', 'html'], render=False)
            urls = result.get('urls', [])
            # Cache page content for downstream enrichment
            pages = result.get('pages', [])
            self._cloudflare_pages = {}
            for p in pages:
                page_url = p.get('url') or p.get('sourceURL', '')
                if page_url:
                    self._cloudflare_pages[page_url] = {
                        'markdown': p.get('markdown', p.get('content', '')),
                        'html': p.get('html', ''),
                        'title': p.get('title', ''),
                    }
            print(f"   ☁️  Cloudflare: {len(urls)} URLs, {len(self._cloudflare_pages)} pages with content")
            return urls or []
        except Exception as e:
            print(f"   ⚠️  Cloudflare discovery unavailable: {str(e)[:100]}")
            return []

    def _build_url_inventory(self, urls: List[str], base_url: str,
                              sources: Dict[str, List[str]] = None) -> Dict:
        """
        Build a structured URL inventory for the user — surfaces the full
        pool of discovered URLs with categorization and source attribution.

        This is the "why didn't we show the user all the URLs?" fix:
        previously Cloudflare discovered 200+ URLs but only the 3-5
        selected pages were visible in evidence.

        Returns:
            {
                total: int,
                by_section: { '/products': [...], '/docs': [...], ... },
                by_source: { 'cloudflare': 150, 'interactive': 67 },
                urls: [ { url, section, depth, source } ],
                coverage_note: str
            }
        """
        from urllib.parse import urlparse

        parsed_base = urlparse(base_url)
        sources = sources or {}

        # Build source lookup: which source discovered each URL
        url_sources = {}
        for source_name, source_urls in sources.items():
            for u in source_urls:
                if u not in url_sources:
                    url_sources[u] = source_name
                else:
                    url_sources[u] += f'+{source_name}'  # found by both

        # Categorize URLs by first path segment
        by_section = {}
        inventory_items = []

        for url in sorted(set(urls)):
            try:
                parsed = urlparse(url)
                if parsed.netloc != parsed_base.netloc:
                    continue  # Skip external URLs
                segments = [s for s in parsed.path.split('/') if s]
                section = f'/{segments[0]}' if segments else '/'
                depth = len(segments)

                by_section.setdefault(section, []).append(url)
                inventory_items.append({
                    'url': url,
                    'section': section,
                    'depth': depth,
                    'source': url_sources.get(url, 'unknown'),
                })
            except Exception:
                continue

        # Source counts
        by_source = {}
        for item in inventory_items:
            src = item['source'].split('+')[0]  # primary source
            by_source[src] = by_source.get(src, 0) + 1

        # Section summary (top 10 sections by count)
        section_summary = sorted(
            [(section, len(urls_list)) for section, urls_list in by_section.items()],
            key=lambda x: x[1], reverse=True
        )[:10]

        total = len(inventory_items)
        sections_count = len(by_section)

        return {
            'total': total,
            'sections_count': sections_count,
            'section_summary': [{'section': s, 'count': c} for s, c in section_summary],
            'by_source': by_source,
            'urls': inventory_items[:500],  # Cap at 500 to avoid payload bloat
            'coverage_note': (
                f"{total} URLs across {sections_count} sections. "
                f"Sources: {', '.join(f'{k}({v})' for k, v in by_source.items())}."
            ),
        }

    def _classify_cloudflare_pages(self, cf_pages: Dict[str, Dict], base_url: str) -> Dict:
        """
        Lightweight content classification on Cloudflare-fetched page content.

        Doesn't need Playwright — just parses markdown/HTML for structural signals
        (headings, product selectors, article tags, form elements).

        Returns:
            {
                total_pages: int,
                page_types: { 'product': 12, 'article': 8, 'docs': 15, ... },
                distribution_pct: { 'product': '24%', ... },
                samples: { 'product': ['url1', 'url2'], ... },
                pattern: str
            }
        """
        import re
        from urllib.parse import urlparse

        type_counts = {}
        type_samples = {}
        total = 0

        for url, content_data in cf_pages.items():
            md = content_data.get('markdown', '') or ''
            html = content_data.get('html', '') or ''
            combined = md + html
            if len(combined) < 50:
                continue  # Skip empty/error pages

            total += 1
            page_type = self._classify_page_content_lightweight(url, md, html)
            type_counts[page_type] = type_counts.get(page_type, 0) + 1
            type_samples.setdefault(page_type, [])
            if len(type_samples[page_type]) < 3:
                type_samples[page_type].append(url)

        if total == 0:
            return {'total_pages': 0, 'page_types': {}, 'pattern': 'No content available'}

        # Distribution percentages
        distribution = {
            ptype: f"{round(count / total * 100)}%"
            for ptype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        }

        # Top type
        top_type = max(type_counts, key=type_counts.get) if type_counts else 'unknown'

        return {
            'total_pages': total,
            'page_types': type_counts,
            'distribution_pct': distribution,
            'samples': type_samples,
            'pattern': f"{total} pages classified — {top_type} dominant ({distribution.get(top_type, '?')})",
            'confidence': min(90, 50 + total),  # More pages = higher confidence
        }

    def _classify_page_content_lightweight(self, url: str, markdown: str, html: str) -> str:
        """
        Classify a single page by type using URL path + content signals.
        Lightweight — no Playwright, just text/pattern matching.
        """
        import re
        from urllib.parse import urlparse

        path = urlparse(url).path.lower()
        md_lower = markdown.lower()
        html_lower = html.lower()

        # URL path signals (strongest)
        if re.search(r'/blog/|/posts?/|/articles?/', path):
            return 'article'
        if re.search(r'/docs?/|/documentation/|/guide/', path):
            return 'documentation'
        if re.search(r'/products?/|/shop/|/store/', path):
            return 'product'
        if re.search(r'/pricing/', path):
            return 'pricing'
        if re.search(r'/about/', path):
            return 'about'
        if re.search(r'/contact/', path):
            return 'contact'
        if re.search(r'/faq/', path):
            return 'faq'
        if re.search(r'/careers?|/jobs?/', path):
            return 'careers'
        if re.search(r'/legal|/privacy|/terms/', path):
            return 'legal'

        # Content signals (when path is ambiguous)
        # Product: price indicators, add-to-cart
        if re.search(r'\$\d+|\bprice\b|add.to.cart|buy.now', md_lower):
            return 'product'

        # Article: long-form text with headings
        heading_count = len(re.findall(r'^#{1,3}\s', markdown, re.MULTILINE))
        word_count = len(markdown.split())
        if heading_count >= 3 and word_count > 500:
            return 'article'

        # Documentation: code blocks, API references
        code_blocks = len(re.findall(r'```', markdown))
        if code_blocks >= 2 or re.search(r'api.reference|code.example|endpoint', md_lower):
            return 'documentation'

        # Landing: hero patterns, CTAs
        if re.search(r'get.started|sign.up|learn.more|free.trial', md_lower):
            return 'landing'

        # Form-heavy
        if html_lower.count('<form') >= 1 or html_lower.count('<input') >= 3:
            return 'form'

        # Default by content length
        if word_count > 300:
            return 'content'
        elif word_count < 50:
            return 'minimal'

        return 'other'

    async def multi_scan(self, urls: List[str], analysis_focus: str = 'full') -> Dict:
        """
        Analyze an explicit list of URLs (for /api/multi-scan endpoint).
        Uses one browser session, analyzes each page, then synthesizes.

        Args:
            urls: List of URLs to analyze
            analysis_focus: 'full'|'layout'|'design'|'interaction'|'architecture' — controls which extractors run
        """
        from patchright.async_api import async_playwright

        print(f"\n{'='*70}")
        print(f" 🔍 MULTI-SCAN: {len(urls)} pages")
        print('='*70)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            page.set_default_timeout(60000)

            # Initialize network monitoring (required by _analyze_api_patterns, _extract_performance, etc.)
            self.network_requests = []
            self.network_responses = []
            page.on('request', lambda req: self.network_requests.append({
                'url': req.url,
                'method': req.method,
                'resource_type': req.resource_type,
                'headers': dict(req.headers)
            }))
            page.on('response', lambda resp: self.network_responses.append({
                'url': resp.url,
                'status': resp.status,
                'headers': dict(resp.headers)
            }))

            page_results = {}
            for idx, url in enumerate(urls):
                label = 'home' if idx == 0 else f'page_{idx}'
                print(f"\n   📄 [{idx + 1}/{len(urls)}] Analyzing: {url}")

                # Reset network tracking per page
                self.network_requests = []
                self.network_responses = []

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(2)
                    html_content = await page.content()
                    page_results[label] = await self._analyze_single_page(page, url, html_content, analysis_focus=analysis_focus)
                    print(f"   ✅ {label} complete — {len(page_results[label])} evidence keys (focus: {analysis_focus})")
                except Exception as e:
                    print(f"   ❌ {label} failed: {str(e)[:60]}")
                    page_results[label] = {
                        'error': str(e)[:200],
                        'meta_info': {'url': url, 'access_strategy': 'failed'}
                    }

            await browser.close()

        # Synthesize cross-page patterns
        synthesis = self._synthesize_multi_page(page_results, mode='interactive')
        synthesis['urls_discovered'] = {label: url for label, url in zip(page_results.keys(), urls)}
        return synthesis

    async def _analyze_single_page(self, page, url: str, html_content: str, analysis_focus: str = 'full') -> Dict:
        """
        Analyze a single page (core extraction logic)

        Args:
            page: Playwright page object
            url: URL being analyzed
            html_content: HTML content of the page
            analysis_focus: 'full'|'layout'|'design'|'interaction'|'architecture' — controls which extractors run

        Returns:
            Dict with all metrics for this page
        """
        # Setup BeautifulSoup
        self.soup = BeautifulSoup(html_content, 'lxml')

        # Extract all metrics with error handling
        evidence = {}
        _extractor_timings = {}  # Track per-extractor duration
        _extraction_start = time.perf_counter()

        # Helper function to safely extract metrics (with timing)
        async def safe_extract(name, coro_or_func, *args):
            t0 = time.perf_counter()
            try:
                if asyncio.iscoroutinefunction(coro_or_func):
                    result = await coro_or_func(*args)
                else:
                    result = coro_or_func(*args)
                return result
            except Exception as e:
                print(f"   ⚠️  Warning: {name} extraction failed: {str(e)[:100]}")
                return {
                    'pattern': 'Analysis Failed',
                    'confidence': 0,
                    'error': str(e)[:200]
                }
            finally:
                _extractor_timings[name] = round(time.perf_counter() - t0, 3)

        # Focus gating: skip extractors not relevant to the selected focus
        _focus_keys = FOCUS_EXTRACTORS.get(analysis_focus)
        def _should_extract(key):
            return _focus_keys is None or key in _focus_keys

        # Extract each metric safely — gated by focus
        if _should_extract('layout'):
            evidence['layout'] = await safe_extract('Layout', self._extract_layout, page)
        if _should_extract('typography'):
            evidence['typography'] = await safe_extract('Typography', self._extract_typography, page)
        if _should_extract('colors'):
            evidence['colors'] = await safe_extract('Colors', self._extract_colors, page)
        if _should_extract('animations'):
            evidence['animations'] = await safe_extract('Animations', self._extract_animations, page)
        if _should_extract('accessibility'):
            evidence['accessibility'] = await safe_extract('Accessibility', self._extract_accessibility, page)
        if _should_extract('accessibility_tree'):
            print("   🏗 Capturing page blueprint (accessibility tree)...")
            from extractors.accessibility_tree import AccessibilityTreeExtractor
            _a11y_ctx = ExtractionContext(page=page, url=url, html_content=html_content, network_requests=self.network_requests, network_responses=self.network_responses, evidence=evidence)
            evidence['accessibility_tree'] = await safe_extract('Accessibility Tree', AccessibilityTreeExtractor().extract, _a11y_ctx)
        if _should_extract('performance'):
            print("   ⚡ Measuring performance...")
            _perf_ctx = ExtractionContext(page=page, url=url, html_content=html_content, network_requests=self.network_requests, network_responses=self.network_responses, evidence=evidence)
            evidence['performance'] = await safe_extract('Performance', PerformanceExtractor().extract, _perf_ctx)
        if _should_extract('dom_depth'):
            evidence['dom_depth'] = await safe_extract('DOM Depth', self._extract_dom_depth, page)
        if _should_extract('seo'):
            evidence['seo'] = await safe_extract('SEO', self._extract_seo, page)
        if _should_extract('security'):
            print("   🔒 Checking security...")
            _sec_ctx = ExtractionContext(page=page, url=url, html_content=html_content, network_requests=self.network_requests, network_responses=self.network_responses, evidence=evidence)
            evidence['security'] = await safe_extract('Security', SecurityExtractor().extract, _sec_ctx)
        if _should_extract('api_patterns'):
            evidence['api_patterns'] = await safe_extract('API Patterns', self._analyze_api_patterns)
        if _should_extract('site_architecture'):
            evidence['site_architecture'] = await safe_extract('Site Architecture', self._extract_site_architecture, page)
        if _should_extract('css_tricks'):
            evidence['css_tricks'] = await safe_extract('CSS Tricks', self._extract_css_tricks, page)
        if _should_extract('interactive_elements'):
            evidence['interactive_elements'] = await safe_extract('Interactive', self._extract_interactive_elements, page)
        if _should_extract('interaction_states'):
            evidence['interaction_states'] = await safe_extract('Interaction States', self._extract_interaction_states, page)
        if _should_extract('third_party'):
            evidence['third_party'] = await safe_extract('Third Party', self._analyze_third_party)
        # article_content is lightweight — always extract
        evidence['article_content'] = await safe_extract('Articles', self._extract_article_content, page)

        # Intelligent Content Extraction
        if _should_extract('content_extraction'):
            print("   📄 Extracting content with classification...")
            content_extractor = IntelligentContentExtractor(page)
            extraction_result = await safe_extract('Content Extraction', content_extractor.extract)

            if extraction_result and isinstance(extraction_result, dict) and extraction_result.get('error'):
                evidence['content_extraction'] = extraction_result
            elif extraction_result and hasattr(extraction_result, 'page_type'):
                evidence['content_extraction'] = {
                    'page_type': extraction_result.page_type.value if hasattr(extraction_result.page_type, 'value') else str(extraction_result.page_type),
                    'confidence': extraction_result.confidence,
                    'reasoning': extraction_result.reasoning,
                    'content_inventory': extraction_result.content_inventory,
                    'samples': extraction_result.samples,
                    'extraction_strategy': extraction_result.extraction_strategy,
                    'excluded_elements': extraction_result.excluded_elements,
                    'semantic_analysis': extraction_result.semantic_analysis
                }
            else:
                evidence['content_extraction'] = {
                    'error': 'Content extraction returned unexpected result',
                    'result': str(extraction_result)
                }

        # ── Content Layout Analysis ──
        # When content type is article/blog/landing, analyze HOW content is displayed:
        # card grid dimensions, reading width, article card styling, list vs grid vs masonry
        _content_type = (evidence.get('content_extraction') or {}).get('page_type', '')
        # Always run content layout — card grids, reading width, and section flow
        # are valuable regardless of page classification
        if _content_type:
            print(f"   📰 Analyzing content layout ({_content_type})...")
            evidence['content_layout'] = await safe_extract(
                'Content Layout',
                self._analyze_content_layout, page, _content_type
            )
        elif _should_extract('content_extraction'):
            # Even if content extraction failed, try with generic type
            print(f"   📰 Analyzing content layout (generic)...")
            evidence['content_layout'] = await safe_extract(
                'Content Layout',
                self._analyze_content_layout, page, 'generic'
            )

        # Design System Metrics — gate each sub-metric individually
        _any_design = any(_should_extract(k) for k in ('spacing_scale', 'responsive_breakpoints', 'shadow_system', 'z_index_stack', 'border_radius_scale'))
        if _any_design:
            print("\n🎨 Extracting Design System Metrics...")
            design_metrics = DesignSystemMetrics(page)
            if _should_extract('spacing_scale'):
                evidence['spacing_scale'] = await safe_extract('Spacing Scale', design_metrics.extract_spacing_scale)
            if _should_extract('responsive_breakpoints'):
                evidence['responsive_breakpoints'] = await safe_extract('Breakpoints', design_metrics.extract_responsive_breakpoints)
            if _should_extract('shadow_system'):
                evidence['shadow_system'] = await safe_extract('Shadow System', design_metrics.extract_shadow_system)
            if _should_extract('z_index_stack'):
                evidence['z_index_stack'] = await safe_extract('Z-Index Stack', design_metrics.extract_z_index_stack)
            if _should_extract('border_radius_scale'):
                evidence['border_radius_scale'] = await safe_extract('Border Radius', design_metrics.extract_border_radius_scale)

        # Enrich with statistical fields
        print("\n📊 Enriching evidence with statistical fields...")
        self._enrich_evidence_with_statistics(evidence)

        # Add plain language summaries
        print("\n💬 Adding plain language summaries...")
        for metric_name in ['shadow_system', 'typography', 'colors', 'spacing_scale',
                           'responsive_breakpoints', 'z_index_stack', 'visual_hierarchy',
                           'layout_system', 'interaction_states']:
            if metric_name in evidence and evidence[metric_name]:
                evidence[metric_name] = self._add_plain_language_summary(
                    metric_name,
                    evidence[metric_name]
                )

        # Visual Hierarchy Analysis
        if _should_extract('visual_hierarchy'):
            print("\n👁️  Analyzing Visual Hierarchy...")
            hierarchy_analyzer = VisualHierarchyAnalyzer()
            evidence['visual_hierarchy'] = await safe_extract('Visual Hierarchy', hierarchy_analyzer.analyze, page)

            # Capture interactive states for top VH regions
            if evidence.get('visual_hierarchy') and evidence['visual_hierarchy'].get('visual_weight_map'):
                print("   ⚡ Capturing VH region interactive states...")
                evidence['visual_hierarchy']['region_states'] = await self._capture_vh_region_states(
                    page, evidence['visual_hierarchy']['visual_weight_map'][:5]
                )

        # Spatial Composition Analysis (fills the 50-60% gap)
        if _should_extract('spatial_composition'):
            print("\n🗺️  Analyzing Spatial Composition...")
            spatial_analyzer = SpatialCompositionAnalyzer()
            evidence['spatial_composition'] = await safe_extract('Spatial Composition', spatial_analyzer.analyze, page)

        # Motion Token Synthesis (transforms raw animations + interaction_states into reusable tokens)
        if _should_extract('motion_tokens'):
            print("\n🎬 Synthesizing Motion Tokens...")
            from motion_token_synthesizer import MotionTokenSynthesizer
            motion_synth = MotionTokenSynthesizer()
            raw_keyframes = evidence.get('animations', {}).get('details', {}).get('keyframes', [])
            evidence['motion_tokens'] = motion_synth.synthesize(
                evidence.get('animations', {}),
                evidence.get('interaction_states', {}),
                raw_keyframes=raw_keyframes
            )

        # CDP Animation Capture (runtime JS-driven animations — fills gap left by CSS-only extractor)
        if _should_extract('cdp_animations'):
            print("\n🎭 Capturing runtime animations via CDP...")
            _cdp_ctx = ExtractionContext(page=page, url=url, html_content=html_content, evidence=evidence)
            evidence['cdp_animations'] = await safe_extract('CDP Animations', CdpAnimationExtractor().extract, _cdp_ctx)

        # Axe-core Contrast Audit (WCAG AA colour-contrast via injected axe)
        if _should_extract('contrast_a11y'):
            print("\n♿ Running axe-core contrast audit...")
            _axe_ctx = ExtractionContext(page=page, url=url, html_content=html_content, evidence=evidence)
            evidence['contrast_a11y'] = await safe_extract('Axe Contrast', AxeContrastExtractor().extract, _axe_ctx)

        # CSS Efficiency (unused CSS detection via CDP Coverage)
        if _should_extract('css_efficiency'):
            print("\n📊 Analyzing CSS efficiency...")
            _css_eff_ctx = ExtractionContext(page=page, url=url, html_content=html_content, evidence=evidence)
            evidence['css_efficiency'] = await safe_extract('CSS Efficiency', CSSEfficiencyExtractor().extract, _css_eff_ctx)

        # CSS Specificity (cascade health + methodology detection)
        if _should_extract('css_specificity'):
            print("\n🎯 Analyzing CSS specificity...")
            _css_spec_ctx = ExtractionContext(page=page, url=url, html_content=html_content, evidence=evidence)
            evidence['css_specificity'] = await safe_extract('CSS Specificity', CSSSpecificityExtractor().extract, _css_spec_ctx)

        # Screenshot with Annotations — only if visual_hierarchy was extracted
        if _should_extract('visual_hierarchy') and evidence.get('visual_hierarchy') and evidence['visual_hierarchy'].get('pattern'):
            print("\n📸 Capturing annotated screenshot...")
            screenshot_annotator = ScreenshotAnnotator()
            evidence['screenshot'] = await safe_extract(
                'Screenshot',
                screenshot_annotator.capture_and_annotate,
                page,
                evidence['visual_hierarchy'],
                url
            )

        # Component Map (SDK integration)
        if _should_extract('component_map'):
            print("\n🗺️  Analyzing component structure...")
            component_mapper = ComponentMapper()
            evidence['component_map'] = component_mapper.analyze_page(html_content)

        # Visual Pattern Discovery (lightweight, no screenshots — runs on already-open page)
        if _should_extract('visual_patterns'):
            print("\n🎨 Discovering visual patterns...")
            try:
                from component_discovery_js import COMPONENT_DISCOVERY_JS
                raw_patterns = await page.evaluate(COMPONENT_DISCOVERY_JS)
                component_list = raw_patterns.get('components', [])
                viewport = raw_patterns.get('viewport', {'width': 1920, 'height': 1080})

                # Generate human-readable descriptions from preview data
                for comp in component_list:
                    p = comp.get('preview', {})
                    parts = []
                    if p.get('headings', 0) > 0:
                        parts.append(f"{p['headings']} heading{'s' if p['headings'] > 1 else ''}")
                    if p.get('imgs', 0) > 0:
                        parts.append(f"{p['imgs']} image{'s' if p['imgs'] > 1 else ''}")
                    if p.get('links', 0) > 0:
                        parts.append(f"{p['links']} link{'s' if p['links'] > 1 else ''}")
                    if p.get('buttons', 0) > 0:
                        parts.append(f"{p['buttons']} button{'s' if p['buttons'] > 1 else ''}")
                    if p.get('inputs', 0) > 0:
                        parts.append(f"{p['inputs']} input{'s' if p['inputs'] > 1 else ''}")
                    comp['description'] = ', '.join(parts) if parts else f"{p.get('children', 0)} child elements"
                    comp['layout_label'] = comp.get('layout', 'block').capitalize()

                # Build category summary
                categories = {}
                for comp in component_list:
                    cat = comp['category']
                    categories[cat] = categories.get(cat, 0) + 1

                cat_labels = {
                    'navigation': 'navigation bar', 'hero': 'hero section',
                    'content_grid': 'content grid', 'footer': 'footer',
                    'section': 'content section', 'sidebar': 'sidebar',
                    'form': 'form', 'media': 'media player', 'block': 'content block',
                    'accordion': 'accordion', 'tabs': 'tab group', 'modal': 'modal',
                    'breadcrumb': 'breadcrumb', 'table': 'data table',
                    'carousel': 'carousel', 'pricing': 'pricing section',
                    'timeline': 'timeline', 'alert': 'alert', 'stepper': 'stepper',
                    'marquee': 'marquee', 'testimonial': 'testimonial',
                    'cta': 'call-to-action', 'split_content': 'split content',
                    'newsletter': 'newsletter signup', 'social_proof': 'social proof'
                }
                summary_parts = []
                for cat, count in categories.items():
                    label = cat_labels.get(cat, cat)
                    summary_parts.append(f"{count} {label}{'s' if count > 1 else ''}")

                evidence['visual_patterns'] = {
                    'components': component_list,
                    'viewport': viewport,
                    'total': len(component_list),
                    'summary': f"Found {len(component_list)} patterns: " + ", ".join(summary_parts),
                    'confidence': min(95, 50 + len(component_list) * 5),
                    'pattern': f"{len(component_list)} visual patterns discovered"
                }
                print(f"   Found {len(component_list)} visual patterns")
            except Exception as e:
                print(f"   ⚠️ Visual pattern discovery failed: {e}")
                evidence['visual_patterns'] = {
                    'components': [], 'viewport': {}, 'total': 0,
                    'summary': 'Discovery failed', 'confidence': 0,
                    'pattern': 'Visual pattern discovery failed'
                }

        # Extract all links for LLM guidance
        print("\n🔗 Discovering navigation links...")
        discovered_links = await self._discover_links(page, url)

        # ── Site Topology (information architecture from discovered URLs) ──
        # _discover_links().all contains objects {url, text, path} — extract URL strings
        _raw_all = discovered_links.get('all', []) if isinstance(discovered_links, dict) else []
        all_discovered = []
        for item in _raw_all:
            if isinstance(item, dict):
                all_discovered.append(item.get('url', ''))
            elif isinstance(item, str):
                all_discovered.append(item)
        all_discovered = [u for u in all_discovered if u]
        # Include any Cloudflare-discovered URLs if available
        if hasattr(self, '_cloudflare_urls') and self._cloudflare_urls:
            all_discovered = list(set(all_discovered + self._cloudflare_urls))
            _topo_source = 'cloudflare'
        else:
            _topo_source = 'nav_discovery'

        if len(all_discovered) >= 5:
            from site_topology import SiteTopologyAnalyzer
            print(f"\n🗺️  Analyzing site topology ({len(all_discovered)} URLs)...")
            _topo_analyzer = SiteTopologyAnalyzer()
            evidence['site_topology'] = await safe_extract(
                'Site Topology',
                lambda: _topo_analyzer.analyze(all_discovered, url, url_source=_topo_source)
            )

        # Meta info
        try:
            total_nodes = await page.evaluate('document.querySelectorAll("*").length')
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Could not count DOM nodes (non-critical): {e}")
            total_nodes = 0

        # Scan timing summary
        _extraction_elapsed = round(time.perf_counter() - _extraction_start, 2)
        _sorted_timings = sorted(_extractor_timings.items(), key=lambda x: x[1], reverse=True)
        _slowest = _sorted_timings[0] if _sorted_timings else ('none', 0)

        evidence['scan_timing'] = {
            'pattern': f'Scan completed in {_extraction_elapsed}s — slowest: {_slowest[0]} ({_slowest[1]}s)',
            'confidence': 100,
            'total_extraction_seconds': _extraction_elapsed,
            'per_extractor': {name: secs for name, secs in _sorted_timings},
            'slowest_extractor': _slowest[0],
            'slowest_seconds': _slowest[1],
            'extractor_count': len(_extractor_timings),
        }

        evidence['meta_info'] = {
            'url': url,
            'access_strategy': 'playwright_full',
            'total_requests': len(self.network_requests),
            'total_dom_nodes': total_nodes,
            'bot_protection_detected': False,
            'full_analysis_available': True
        }

        # Architecture diagrams (Mermaid) — built from site_architecture evidence
        if _should_extract('architecture_diagrams'):
            evidence['architecture_diagrams'] = self._generate_architecture_diagrams(url, evidence)

        # Design Harmony — detect mathematical scales, boost confidence
        try:
            from design_harmony import analyze_harmony, apply_confidence_boosts
            harmony = analyze_harmony(evidence)
            apply_confidence_boosts(evidence, harmony)
            print(f"   🎵 Design harmony: {harmony.get('summary', 'none')}")
        except Exception as e:
            print(f"   ⚠️  Design harmony analysis failed: {e}")

        # LLM Helper - Suggest next steps for deeper analysis
        evidence['llm_helper'] = self._generate_llm_suggestions(
            url,
            discovered_links,
            evidence.get('content_extraction', {}),
            evidence.get('component_map', {})
        )

        return evidence

    def _synthesize_multi_page(self, page_results: Dict[str, Dict], mode: str = 'smart-nav') -> Dict:
        """
        Combine insights from multiple pages into site-level understanding

        Args:
            page_results: {
                'home': {...evidence...},
                'nav_1': {...evidence...},
                'nav_2': {...evidence...}
            }
            mode: 'smart-nav' or 'interactive'

        Returns:
            Synthesized evidence with patterns
        """
        synthesis = {
            'analysis_mode': mode,
            'pages_analyzed': len(page_results),
            'page_results': page_results,
            'site_patterns': {}
        }

        # Safe nested get: handles None values at any level in the chain
        def _sg(d, *keys, default=None):
            """Safe get through nested dicts — returns default if any level is None."""
            for k in keys:
                if not isinstance(d, dict):
                    return default
                d = d.get(k)
                if d is None:
                    return default
            return d

        # Pattern 1: Layout consistency
        layouts = [_sg(p, 'layout', 'pattern', default='unknown') for p in page_results.values() if not p.get('error')]
        if layouts:
            all_same = len(set(layouts)) == 1
            synthesis['site_patterns']['layout_consistency'] = 'consistent' if all_same else 'varies by page'
            synthesis['site_patterns']['layout_types'] = list(set(layouts))

        # Pattern 2: API usage across pages
        api_counts = {
            label: len(_sg(p, 'api_patterns', 'details', 'rest_apis', default=[]) or [])
            for label, p in page_results.items()
            if not p.get('error')
        }
        synthesis['site_patterns']['api_usage'] = api_counts

        # Pattern 3: Detect SPA vs. MPA
        if api_counts:
            avg_api_count = sum(api_counts.values()) / len(api_counts)
            if avg_api_count > 10:
                synthesis['site_patterns']['architecture'] = 'SPA (high API usage across all pages)'
            elif api_counts.get('home', 0) > 10:
                synthesis['site_patterns']['architecture'] = 'Hybrid (API-heavy home, lighter subpages)'
            else:
                synthesis['site_patterns']['architecture'] = 'Traditional (low API usage)'
        else:
            synthesis['site_patterns']['architecture'] = 'Unknown'

        # Pattern 4: Typography consistency
        fonts_by_page = {}
        for label, p in page_results.items():
            if not p.get('error') and p.get('typography'):
                fonts_by_page[label] = set(p['typography'].get('fonts', []))

        if len(fonts_by_page) > 1:
            all_fonts = list(fonts_by_page.values())
            consistent = all(fonts == all_fonts[0] for fonts in all_fonts)
            synthesis['site_patterns']['typography_consistent'] = consistent

        # Pattern 5: Color palette consistency
        colors_by_page = {}
        for label, p in page_results.items():
            if not p.get('error') and p.get('colors'):
                colors_by_page[label] = p['colors'].get('pattern', 'unknown')

        if colors_by_page:
            all_same_colors = len(set(colors_by_page.values())) == 1
            synthesis['site_patterns']['color_consistency'] = 'consistent' if all_same_colors else 'varies'

        # Pattern 6: Design system usage
        has_spacing = any(
            (p.get('spacing_scale') or {}).get('confidence', 0) > 70
            for p in page_results.values()
            if not p.get('error')
        )
        synthesis['site_patterns']['design_system_detected'] = has_spacing

        # Pattern 6.5: Design System Consistency Report (Variance Quantification)
        synthesis['design_system_consistency'] = self._calculate_design_system_variance(page_results)

        # Pattern 7: Cross-page capability validation
        # Each capability is checked across all successfully-analyzed pages.
        # pages_seen = how many pages showed the signal.
        # confirmed = seen on majority of pages (> half).
        valid_pages = {label: p for label, p in page_results.items() if not p.get('error')}
        total = len(valid_pages)

        def _seen_on(check_fn):
            """Count how many pages satisfy check_fn(page_evidence)"""
            return sum(1 for p in valid_pages.values() if check_fn(p))

        validated = {}
        if total > 0:
            # Has a database — any REST or GraphQL API calls
            n = _seen_on(lambda p: bool(
                (_sg(p, 'api_patterns', 'details', 'rest_apis', default=[]) or []) or
                (_sg(p, 'api_patterns', 'details', 'graphql', default=[]) or [])
            ))
            validated['has_database'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Updates live — websockets or GraphQL subscriptions
            n = _seen_on(lambda p:
                _sg(p, 'site_architecture', 'details', 'capabilities', 'websockets', default=False) or
                bool((_sg(p, 'api_patterns', 'details', 'graphql', default=[]) or []))
            )
            validated['updates_live'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Has user accounts — auth signals
            n = _seen_on(lambda p:
                (p.get('site_architecture') or {}).get('details', {}).get('auth_detected', False) or
                any(
                    any(kw in (ep.get('path') or '').lower() for kw in ['/auth', '/login', '/token', '/session', '/oauth'])
                    for ep in ((p.get('api_patterns') or {}).get('relationship_map') or {}).get('endpoints') or []
                )
            )
            validated['has_user_accounts'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Tracks visitors — analytics third-party scripts
            n = _seen_on(lambda p: bool(_sg(p, 'third_party', 'details', 'analytics')))
            validated['tracks_visitors'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Loads fast globally — CDN
            n = _seen_on(lambda p: bool(_sg(p, 'third_party', 'details', 'cdns')))
            validated['loads_fast_globally'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Works offline — service worker
            n = _seen_on(lambda p:
                _sg(p, 'site_architecture', 'details', 'capabilities', 'service_worker', default=False)
            )
            validated['works_offline'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Multiple languages — i18n
            n = _seen_on(lambda p:
                _sg(p, 'site_architecture', 'details', 'capabilities', 'i18n', default=False)
            )
            validated['multiple_languages'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Tests features — feature flags
            n = _seen_on(lambda p:
                _sg(p, 'site_architecture', 'details', 'capabilities', 'feature_flags', default=False)
            )
            validated['tests_features'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Publishes content — articles found
            n = _seen_on(lambda p: bool(_sg(p, 'article_content', 'articles')))
            validated['publishes_content'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Collects input — forms or inputs detected
            n = _seen_on(lambda p: (
                (_sg(p, 'interactive_elements', 'counts', 'forms', default=0) or 0) > 0 or
                (_sg(p, 'interactive_elements', 'counts', 'inputs', default=0) or 0) > 0
            ))
            validated['collects_input'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Shows ads — advertising scripts
            n = _seen_on(lambda p: bool(_sg(p, 'third_party', 'details', 'advertising')))
            validated['shows_ads'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

            # Prefetches pages
            n = _seen_on(lambda p:
                _sg(p, 'site_architecture', 'details', 'capabilities', 'prefetching', default=False)
            )
            validated['prefetches_pages'] = {'pages_seen': n, 'of': total, 'confirmed': n > total / 2}

        synthesis['validated_capabilities'] = validated

        # Also surface the first page's site_architecture details for the ERD row
        first_page = next(iter(valid_pages.values()), {})
        synthesis['site_architecture'] = first_page.get('site_architecture', {})

        # ── Site Topology (cross-page URL analysis) ──
        # Collect all discovered URLs across every analyzed page
        all_cross_urls = set()
        for label, result in page_results.items():
            if result.get('error'):
                continue
            url_pats = result.get('url_patterns', {})
            details = url_pats.get('details', {}) if isinstance(url_pats, dict) else {}
            all_links = details.get('all', []) if isinstance(details, dict) else []
            all_cross_urls.update(all_links)
            meta_url = (result.get('meta_info') or {}).get('url', '')
            if meta_url:
                all_cross_urls.add(meta_url)

        # Include any per-page topology data (each page may have nav-discovered URLs)
        for label, result in page_results.items():
            topo = result.get('site_topology')
            if topo and isinstance(topo, dict):
                # Merge sections count for richer data
                pass  # Individual topologies are per-page; cross-page is richer

        # Include Cloudflare URLs if they were captured during discovery
        if hasattr(self, '_cloudflare_urls') and self._cloudflare_urls:
            all_cross_urls.update(self._cloudflare_urls)
            _topo_source = 'cloudflare'
        else:
            _topo_source = 'multi_page'

        base_url = page_results.get('home', {}).get('meta_info', {}).get('url', self.url)
        if len(all_cross_urls) >= 5:
            from site_topology import SiteTopologyAnalyzer
            topo = SiteTopologyAnalyzer()
            synthesis['site_topology'] = topo.analyze(
                list(all_cross_urls), base_url, url_source=_topo_source
            )

        # ── Site Content Profile (from Cloudflare page content) ──
        # When Cloudflare cached page content, classify pages by type to give
        # a site-level content breakdown (e.g., "45% product, 30% docs, 25% other")
        if hasattr(self, '_cloudflare_pages') and self._cloudflare_pages:
            synthesis['site_content_profile'] = self._classify_cloudflare_pages(
                self._cloudflare_pages, base_url
            )

        return synthesis

    def _enrich_evidence_with_statistics(self, evidence: Dict) -> None:
        """
        Add statistical fields (sample_size, variance, observed) to all evidence objects

        This addresses external LLM feedback: "Evidence needs statistical grounding"
        """
        import statistics

        # Shadow System
        if 'shadow_system' in evidence and evidence['shadow_system']:
            shadow = evidence['shadow_system']
            if 'total_instances' in shadow:
                shadow['sample_size'] = shadow['total_instances']
            if 'levels' in shadow and len(shadow['levels']) > 1:
                blur_radii = [lvl['blur_radius'] for lvl in shadow['levels']]
                if len(blur_radii) > 1:
                    shadow['variance'] = round(statistics.variance(blur_radii), 2)
            shadow['observed'] = True  # Directly measured from computed styles

        # Z-Index Stack
        if 'z_index_stack' in evidence and evidence['z_index_stack']:
            zindex = evidence['z_index_stack']
            if 'layers' in zindex:
                zindex['sample_size'] = len(zindex['layers'])
                # Handle both dict and string layers
                z_values = []
                for layer in zindex['layers']:
                    if isinstance(layer, dict) and 'z_index' in layer:
                        if isinstance(layer['z_index'], (int, float)):
                            z_values.append(layer['z_index'])
                if len(z_values) > 1:
                    zindex['variance'] = round(statistics.variance(z_values), 2)
            zindex['observed'] = True

        # Typography
        if 'typography' in evidence and evidence['typography']:
            typo = evidence['typography']
            if 'sizes' in typo and len(typo['sizes']) > 0:
                typo['sample_size'] = len(typo['sizes'])
                # Extract numeric sizes for variance calculation
                numeric_sizes = []
                for size in typo['sizes']:
                    if isinstance(size, dict) and 'value' in size:
                        val = size['value']
                        if isinstance(val, str) and 'px' in val:
                            try:
                                numeric_sizes.append(float(val.replace('px', '')))
                            except (ValueError, AttributeError):
                                pass
                if len(numeric_sizes) > 1:
                    typo['variance'] = round(statistics.variance(numeric_sizes), 2)
            typo['observed'] = True

        # Spacing Scale
        if 'spacing_scale' in evidence and evidence['spacing_scale']:
            spacing = evidence['spacing_scale']
            if 'scale' in spacing and len(spacing['scale']) > 0:
                spacing['sample_size'] = len(spacing['scale'])
                # Extract numeric spacing values
                numeric_spacing = []
                for item in spacing['scale']:
                    val = item.get('value', item) if isinstance(item, dict) else item
                    if isinstance(val, str) and 'px' in val:
                        try:
                            numeric_spacing.append(float(val.replace('px', '')))
                        except (ValueError, AttributeError):
                            pass
                    elif isinstance(val, (int, float)):
                        numeric_spacing.append(float(val))

                if len(numeric_spacing) > 1:
                    spacing['variance'] = round(statistics.variance(numeric_spacing), 2)
            spacing['observed'] = True

        # Colors
        if 'colors' in evidence and evidence['colors']:
            colors = evidence['colors']
            if 'palette' in colors and 'primary' in colors['palette']:
                primary_count = len(colors['palette']['primary'])
                colors['sample_size'] = primary_count
            colors['observed'] = True

        # Visual Hierarchy (partially inferred)
        if 'visual_hierarchy' in evidence and evidence['visual_hierarchy']:
            vh = evidence['visual_hierarchy']
            vh['observed'] = False  # Uses heuristics (top 40%, >200px tall)
            if 'hero' in vh:
                vh['inference_method'] = 'heuristic_position_and_size'

        # Responsive Breakpoints
        if 'responsive_breakpoints' in evidence and evidence['responsive_breakpoints']:
            breakpoints = evidence['responsive_breakpoints']
            if 'breakpoints' in breakpoints:
                breakpoints['sample_size'] = len(breakpoints['breakpoints'])
                # Extract numeric breakpoint values
                numeric_bp = []
                for bp in breakpoints['breakpoints']:
                    if isinstance(bp, dict) and 'width' in bp:
                        try:
                            val = bp['width'].replace('px', '').strip()
                            numeric_bp.append(float(val))
                        except (ValueError, AttributeError):
                            pass

                if len(numeric_bp) > 1:
                    breakpoints['variance'] = round(statistics.variance(numeric_bp), 2)
            breakpoints['observed'] = True  # Directly from CSS media queries

        # Interaction States
        if 'interaction_states' in evidence and evidence['interaction_states']:
            states = evidence['interaction_states']
            if 'by_selector' in states:
                states['sample_size'] = len(states['by_selector'])
            states['observed'] = True  # Directly from stylesheet rules

        # Border Radius
        if 'border_radius_scale' in evidence and evidence['border_radius_scale']:
            border = evidence['border_radius_scale']
            if 'scale' in border:
                border['sample_size'] = len(border['scale'])
                numeric_radii = [r.get('value', 0) if isinstance(r, dict) else r for r in border['scale']]
                numeric_radii = [float(str(r).replace('px', '')) for r in numeric_radii if isinstance(r, (int, float, str))]
                if len(numeric_radii) > 1:
                    border['variance'] = round(statistics.variance(numeric_radii), 2)
            border['observed'] = True

    def _calculate_design_system_variance(self, page_results: Dict[str, Dict]) -> Dict:
        """
        Calculate variance and consistency scores for design system metrics across pages

        Returns consistency report with variance quantification
        Example: "button padding 85% consistent, varies 12px ±2px"
        """
        import statistics

        consistency_report = {
            'overall_consistency_score': 0,
            'metrics': {},
            'verdict': ''
        }

        valid_pages = {label: p for label, p in page_results.items() if not p.get('error')}
        if len(valid_pages) < 2:
            consistency_report['verdict'] = 'Insufficient data (need 2+ pages)'
            return consistency_report

        metric_scores = []

        # 1. Primary Color Consistency
        primary_colors = []
        for label, page in valid_pages.items():
            colors = page.get('colors', {}).get('palette', {}).get('primary', [])
            if colors and len(colors) > 0:
                # Use first primary color as representative
                primary_colors.append(colors[0])

        if len(primary_colors) >= 2:
            unique_colors = len(set(primary_colors))
            consistency_pct = (1 - (unique_colors - 1) / len(primary_colors)) * 100
            metric_scores.append(consistency_pct)

            consistency_report['metrics']['primary_color'] = {
                'values': primary_colors,
                'unique_count': unique_colors,
                'total_pages': len(primary_colors),
                'consistency_pct': round(consistency_pct, 1),
                'verdict': f"{round(consistency_pct)}% consistent" if consistency_pct >= 90 else f"Varies across pages ({unique_colors} different colors)"
            }

        # 2. Spacing Base Unit Consistency
        spacing_units = []
        for label, page in valid_pages.items():
            spacing = page.get('spacing_scale', {})
            base_unit = spacing.get('base_unit', None)
            if base_unit is not None:
                # Handle both string "4px" and int 4 formats
                try:
                    if isinstance(base_unit, (int, float)):
                        spacing_units.append(int(base_unit))
                    elif isinstance(base_unit, str) and 'px' in base_unit:
                        spacing_units.append(int(base_unit.replace('px', '').strip()))
                except (ValueError, AttributeError, TypeError):
                    pass

        if len(spacing_units) >= 2:
            mean_spacing = statistics.mean(spacing_units)
            std_dev = statistics.stdev(spacing_units) if len(spacing_units) > 1 else 0
            consistency_pct = max(0, (1 - (std_dev / mean_spacing)) * 100) if mean_spacing > 0 else 0
            metric_scores.append(consistency_pct)

            consistency_report['metrics']['spacing_base_unit'] = {
                'values': spacing_units,
                'mean': f'{round(mean_spacing, 1)}px',
                'std_dev': f'±{round(std_dev, 2)}px',
                'consistency_pct': round(consistency_pct, 1),
                'verdict': f"{round(consistency_pct)}% consistent (varies {round(mean_spacing, 1)}px ±{round(std_dev, 2)}px)" if std_dev > 0 else f"Perfect consistency ({int(mean_spacing)}px)"
            }

        # 3. Typography Font Family Consistency
        font_families = []
        for label, page in valid_pages.items():
            typo = page.get('typography', {})
            fonts = typo.get('fonts', [])
            if fonts and len(fonts) > 0:
                font_families.append(fonts[0])  # Primary font

        if len(font_families) >= 2:
            unique_fonts = len(set(font_families))
            consistency_pct = (1 - (unique_fonts - 1) / len(font_families)) * 100
            metric_scores.append(consistency_pct)

            consistency_report['metrics']['primary_font'] = {
                'values': font_families,
                'unique_count': unique_fonts,
                'total_pages': len(font_families),
                'consistency_pct': round(consistency_pct, 1),
                'verdict': f"{round(consistency_pct)}% consistent" if consistency_pct >= 90 else f"Varies across pages ({unique_fonts} different fonts)"
            }

        # 4. Shadow System Consistency (number of levels)
        shadow_levels = []
        for label, page in valid_pages.items():
            shadows = page.get('shadow_system', {})
            levels = shadows.get('levels', [])
            if levels:
                shadow_levels.append(len(levels))

        if len(shadow_levels) >= 2:
            mean_levels = statistics.mean(shadow_levels)
            std_dev = statistics.stdev(shadow_levels) if len(shadow_levels) > 1 else 0
            consistency_pct = max(0, (1 - (std_dev / mean_levels)) * 100) if mean_levels > 0 else 0
            metric_scores.append(consistency_pct)

            consistency_report['metrics']['shadow_levels'] = {
                'values': shadow_levels,
                'mean': round(mean_levels, 1),
                'std_dev': round(std_dev, 2),
                'consistency_pct': round(consistency_pct, 1),
                'verdict': f"{round(consistency_pct)}% consistent" if consistency_pct >= 90 else f"Varies by page (avg {round(mean_levels, 1)} levels)"
            }

        # 5. Responsive Breakpoints Consistency (number of breakpoints)
        breakpoint_counts = []
        for label, page in valid_pages.items():
            breakpoints = page.get('responsive_breakpoints', {}).get('breakpoints', [])
            if breakpoints:
                breakpoint_counts.append(len(breakpoints))

        if len(breakpoint_counts) >= 2:
            mean_bp = statistics.mean(breakpoint_counts)
            std_dev = statistics.stdev(breakpoint_counts) if len(breakpoint_counts) > 1 else 0
            consistency_pct = max(0, (1 - (std_dev / mean_bp)) * 100) if mean_bp > 0 else 0
            metric_scores.append(consistency_pct)

            consistency_report['metrics']['breakpoint_count'] = {
                'values': breakpoint_counts,
                'mean': round(mean_bp, 1),
                'std_dev': round(std_dev, 2),
                'consistency_pct': round(consistency_pct, 1),
                'verdict': f"{round(consistency_pct)}% consistent" if consistency_pct >= 90 else f"Varies by page"
            }

        # Calculate overall consistency score
        if metric_scores:
            overall = statistics.mean(metric_scores)
            consistency_report['overall_consistency_score'] = round(overall, 1)

            # Verdict based on overall score
            if overall >= 95:
                consistency_report['verdict'] = 'Highly Consistent Design System'
            elif overall >= 85:
                consistency_report['verdict'] = 'Mostly Consistent Design System'
            elif overall >= 70:
                consistency_report['verdict'] = 'Moderately Consistent Design System'
            elif overall >= 50:
                consistency_report['verdict'] = 'Inconsistent Design System'
            else:
                consistency_report['verdict'] = 'No Consistent Design System Detected'
        else:
            consistency_report['verdict'] = 'Insufficient metrics for consistency analysis'

        return consistency_report

    def _add_plain_language_summary(self, metric_name: str, evidence: Dict) -> Dict:
        """
        Add human-readable summary for non-technical users
        Does NOT modify technical fields - purely additive

        Based on Phase 3 accessibility requirements
        """
        summaries = {
            'shadow_system': self._summarize_shadows,
            'typography': self._summarize_typography,
            'colors': self._summarize_colors,
            'spacing_scale': self._summarize_spacing,
            'responsive_breakpoints': self._summarize_breakpoints,
            'z_index_stack': self._summarize_layering,
            'visual_hierarchy': self._summarize_hierarchy,
            'layout_system': self._summarize_layout,
            'interaction_states': self._summarize_interactions,
        }

        if metric_name in summaries:
            evidence['summary'] = {
                'title': self._translate_title(metric_name),
                'description': summaries[metric_name](evidence),
                'icon': self._get_icon(metric_name)
            }

        return evidence

    def _translate_title(self, metric_name: str) -> str:
        """Convert technical term to plain language"""
        translations = {
            'shadow_system': 'How This Site Creates Depth',
            'typography': 'Text Styles & Readability',
            'colors': 'Color Palette',
            'spacing_scale': 'White Space & Rhythm',
            'responsive_breakpoints': 'Screen Size Strategy',
            'z_index_stack': 'Layering Priority',
            'visual_hierarchy': 'Where Your Eyes Go',
            'layout_system': 'Structure & Organization',
            'interaction_states': 'Interactive Feedback',
            'content_structure': 'Page Types',
            'component_patterns': 'Reusable Components',
        }
        return translations.get(metric_name, metric_name.replace('_', ' ').title())

    def _get_icon(self, metric_name: str) -> str:
        """Return emoji icon for metric"""
        icons = {
            'shadow_system': '🎨',
            'typography': '📝',
            'colors': '🎨',
            'spacing_scale': '📐',
            'responsive_breakpoints': '📱',
            'z_index_stack': '📚',
            'visual_hierarchy': '👁️',
            'layout_system': '🏗️',
            'interaction_states': '⚡',
            'content_structure': '📄',
            'component_patterns': '🧩',
        }
        return icons.get(metric_name, '📊')

    def _summarize_shadows(self, evidence: Dict) -> str:
        """Generate plain English summary for shadow system"""
        levels = len(evidence.get('elevation_levels', []))
        if levels == 0:
            return "This site doesn't use shadows for depth."

        primary_level = evidence.get('elevation_levels', [{}])[0]
        primary_name = primary_level.get('name', 'Unknown')
        primary_pct = primary_level.get('percentage', 0)

        if levels == 1:
            return "This site uses a single shadow style for all elevated elements."

        return f"This site uses {levels} levels of shadow to create visual depth. " \
               f"Most elements ({primary_pct}%) use '{primary_name}' shadows, " \
               f"creating a layered, professional interface."

    def _summarize_typography(self, evidence: Dict) -> str:
        """Generate plain English summary for typography"""
        typo = evidence.get('typography', {})
        if not isinstance(typo, dict):
            return "Typography analysis incomplete."

        families = typo.get('font_families', typo.get('details', {}).get('all_fonts', []))
        sizes = typo.get('font_sizes', typo.get('details', {}).get('all_sizes', []))

        if not families:
            return "Typography analysis incomplete."

        # font_families can be list of strings or list of dicts
        if isinstance(families[0], dict):
            primary_family = families[0].get('name', 'Unknown')
        else:
            # Raw CSS font-family string — extract first font name
            primary_family = str(families[0]).split(',')[0].strip().replace('"', '').replace("'", '')

        size_count = len(sizes)
        if size_count <= 3:
            size_desc = "limited text sizes (may feel monotonous)"
        elif size_count <= 6:
            size_desc = "a balanced range of text sizes"
        else:
            size_desc = "many text sizes (may feel inconsistent)"

        return f"This site uses {len(families)} font family/families with {size_desc}. " \
               f"Primary font: {primary_family}."

    def _summarize_colors(self, evidence: Dict) -> str:
        """Generate plain English summary for colors"""
        primary_colors = len(evidence.get('primary_colors', []))
        total_colors = evidence.get('total_unique_colors', 0)

        if primary_colors <= 3:
            palette_desc = "minimal, focused palette"
        elif primary_colors <= 5:
            palette_desc = "balanced color system"
        else:
            palette_desc = "diverse color palette"

        return f"This site uses a {palette_desc} with {primary_colors} primary colors " \
               f"and {total_colors} total shades. This suggests {'a strict design system' if total_colors < 20 else 'flexible color usage'}."

    def _summarize_spacing(self, evidence: Dict) -> str:
        """Generate plain English summary for spacing"""
        scale = evidence.get('scale', [])
        base_unit = evidence.get('base_unit')

        if not scale:
            return "No consistent spacing system detected."

        if base_unit:
            return f"This site uses a strict {base_unit} spacing system with {len(scale)} increments. " \
                   f"This creates consistent rhythm and visual alignment."

        return f"This site uses {len(scale)} distinct spacing values. " \
               f"Range: {min(scale)}px to {max(scale)}px."

    def _summarize_breakpoints(self, evidence: Dict) -> str:
        """Generate plain English summary for responsive breakpoints"""
        breakpoints = evidence.get('breakpoints', [])

        if not breakpoints:
            return "No responsive breakpoints detected (site may not be mobile-friendly)."

        if len(breakpoints) <= 2:
            responsive_desc = "basic responsive design (desktop + mobile)"
        elif len(breakpoints) <= 4:
            responsive_desc = "comprehensive responsive design"
        else:
            responsive_desc = "highly adaptive design with many breakpoints"

        return f"This site uses {responsive_desc} with {len(breakpoints)} breakpoints. " \
               f"Supports screen sizes from mobile to large desktop."

    def _summarize_layering(self, evidence: Dict) -> str:
        """Generate plain English summary for z-index stack"""
        layers = evidence.get('layers', [])

        if not layers:
            return "No layering detected (all elements on same plane)."

        # Handle both dict and string layers (same fix as in _enrich_evidence_with_statistics)
        z_values = []
        for layer in layers:
            if isinstance(layer, dict) and 'z_index' in layer:
                z_val = layer['z_index']
                if isinstance(z_val, (int, float)):
                    z_values.append(z_val)

        max_z = max(z_values) if z_values else 0

        return f"This site uses {len(layers)} distinct layers with z-index up to {max_z}. " \
               f"This controls which elements appear on top (modals, dropdowns, tooltips)."

    def _summarize_hierarchy(self, evidence: Dict) -> str:
        """Generate plain English summary for visual hierarchy"""
        heroes = evidence.get('hero_sections', [])
        ctas = evidence.get('ctas', [])

        hero_count = len(heroes)
        cta_count = len(ctas)

        if hero_count == 0:
            hero_desc = "No clear hero section detected"
        elif hero_count == 1:
            hero_desc = "Single clear hero section draws attention"
        else:
            hero_desc = f"{hero_count} hero sections compete for attention"

        return f"{hero_desc}. Found {cta_count} call-to-action buttons. " \
               f"Visual flow guides users {'clearly' if hero_count <= 1 else 'with multiple focal points'}."

    def _summarize_layout(self, evidence: Dict) -> str:
        """Generate plain English summary for layout system"""
        primary_layout = evidence.get('primary_layout_type', 'Unknown')
        grid_detected = evidence.get('uses_css_grid', False)
        flexbox_detected = evidence.get('uses_flexbox', False)

        tech = []
        if grid_detected:
            tech.append('CSS Grid')
        if flexbox_detected:
            tech.append('Flexbox')

        tech_str = ' + '.join(tech) if tech else 'traditional CSS'

        return f"This site uses {primary_layout} layout built with {tech_str}. " \
               f"Modern layout system suggests recent development."

    def _summarize_interactions(self, evidence: Dict) -> str:
        """Generate plain English summary for interaction states"""
        hover_count = evidence.get('hover_count', 0)
        focus_count = evidence.get('focus_count', 0)

        if hover_count == 0 and focus_count == 0:
            return "No interactive states detected (may lack user feedback)."

        return f"Found {hover_count} hover effects and {focus_count} focus states. " \
               f"This provides {'good' if hover_count > 5 else 'basic'} interactive feedback to users."

    async def extract_all(self):
        """Run full deep extraction with robust error handling"""
        async with async_playwright() as p:
            # Launch browser with stealth args
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                ] if STEALTH_AVAILABLE else []
            )

            # Create context with realistic settings
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                } if STEALTH_AVAILABLE else {}
            )
            page = await context.new_page()
            page.set_default_timeout(60000)  # 60s default timeout

            # Apply stealth patches if available
            if STEALTH_AVAILABLE:
                print("   🥷 Stealth mode enabled - bot detection bypass active")
                await stealth_async(page)

            # Network monitoring
            self.network_requests = []
            page.on('request', lambda req: self.network_requests.append({
                'url': req.url,
                'method': req.method,
                'resource_type': req.resource_type,
                'headers': dict(req.headers)
            }))

            self.network_responses = []
            page.on('response', lambda resp: self.network_responses.append({
                'url': resp.url,
                'status': resp.status,
                'headers': dict(resp.headers)
            }))

            # Load page with increased timeout and better wait strategy
            print(f"\n🌐 Loading {self.url}...")
            access_strategy = 'playwright_full'
            degraded_mode = False
            _page_load_start = time.perf_counter()

            try:
                # Try networkidle first (best for SPAs)
                response = await page.goto(self.url, wait_until='networkidle', timeout=60000)

                # Check for bot protection
                if response and response.status in [403, 401]:
                    print(f"   🚫 {response.status} detected - Entering degraded mode (MRI scan)")
                    degraded_mode = True

            except Exception as e:
                print(f"   ⚠️  NetworkIdle timeout, trying domcontentloaded...")
                try:
                    # Fallback to domcontentloaded (faster, works for heavy sites)
                    response = await page.goto(self.url, wait_until='domcontentloaded', timeout=30000)

                    # Check for bot protection
                    if response and response.status in [403, 401]:
                        print(f"   🚫 {response.status} detected - Entering degraded mode (MRI scan)")
                        degraded_mode = True

                except Exception as e2:
                    print(f"   ❌ Page load failed: {str(e2)[:100]}")
                    degraded_mode = True

            # Check for challenge pages (Cloudflare, etc.)
            if not degraded_mode:
                try:
                    html_content = await page.content()
                    if self._is_challenge_page(html_content):
                        print(f"   🛡️  Bot protection challenge detected - Entering degraded mode (MRI scan)")
                        degraded_mode = True
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"Challenge page check failed (continuing): {e}")
                    pass

            # Bug 4 Fix: Check for auth wall / login page
            if not degraded_mode:
                try:
                    page_title = (await page.title()).lower()
                    page_content_sample = html_content[:3000].lower()  # First 3000 chars

                    auth_indicators = [
                        'log in', 'login', 'sign in', 'signin',
                        'password', 'enter password', 'email required',
                        'create account', 'authentication required'
                    ]

                    is_auth_page = any(indicator in page_title or indicator in page_content_sample
                                       for indicator in auth_indicators)

                    # Additional check: look for password input fields
                    password_inputs = await page.query_selector_all('input[type="password"]')
                    has_password_field = len(password_inputs) > 0

                    # Check for login form elements
                    login_forms = await page.query_selector_all('form[action*="login"], form[action*="signin"], form[id*="login"], form[class*="login"]')
                    has_login_form = len(login_forms) > 0

                    if (is_auth_page and has_password_field) or (has_login_form and has_password_field):
                        print(f"   🔒 Auth wall detected (login/signup page) - Entering degraded mode (MRI scan)")
                        access_strategy = 'mri_mode_auth_wall'
                        degraded_mode = True
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"Auth wall check failed (continuing): {e}")
                    pass

            # Bug 5 Fix: Wait for web fonts to load
            if not degraded_mode:
                try:
                    # Wait for document.fonts.ready (all web fonts loaded)
                    await page.wait_for_function('() => document.fonts.ready', timeout=5000)
                    print(f"   ✅ Web fonts loaded")
                except Exception as e:
                    # Timeout is fine - some sites don't use web fonts
                    print(f"   ⏭️  Web font wait timed out (no web fonts or slow loading)")
                    pass

            # DEGRADED MODE: Try Scrapling stealth before falling back to MRI
            if degraded_mode:
                await browser.close()

                # Phase 2: Try Scrapling StealthyFetcher (stealth browser with anti-detection)
                try:
                    from scrapling import StealthyFetcher
                    print(f"   🥷 Patchright blocked — trying Scrapling stealth browser...")

                    async def _scrapling_page_action(page):
                        """Run inside Scrapling's stealth browser — extract full evidence"""
                        await page.wait_for_load_state('domcontentloaded')
                        await asyncio.sleep(3)  # Let JS render

                        # Check if we actually got the real page
                        _html = await page.content()
                        if self._is_challenge_page(_html):
                            print(f"   🛡️  Scrapling also blocked by challenge page")
                            return None

                        print(f"   ✅ Scrapling stealth access succeeded!")
                        # Run full single-page analysis inside the stealth browser
                        self.evidence = await self._analyze_single_page(page, self.url, _html)
                        self.evidence['access_strategy'] = 'scrapling_stealth'
                        return True

                    _result_holder = [None]

                    async def _page_action_wrapper(page):
                        _result_holder[0] = await _scrapling_page_action(page)

                    fetcher = StealthyFetcher()
                    await fetcher.async_fetch(
                        self.url,
                        headless=True,
                        page_action=_page_action_wrapper,
                        timeout=90000,  # 90s — sacurrent etc. are slow behind bot walls
                    )

                    if _result_holder[0] and self.evidence:
                        return self.evidence

                except ImportError:
                    print(f"   ⚠️  Scrapling not installed — falling back to MRI")
                except Exception as e:
                    print(f"   ⚠️  Scrapling stealth failed: {str(e)[:100]} — falling back to MRI")

                # Final fallback: MRI metadata-only scan
                print(f"   🔬 Running Metadata MRI scan...")
                return await self._mri_scan()

            # FULL ACCESS MODE: Continue with normal extraction
            await asyncio.sleep(3)  # Let JS render
            _page_load_seconds = round(time.perf_counter() - _page_load_start, 2)
            print(f"   ⏱️  Page loaded in {_page_load_seconds}s")

            # Get page HTML
            html_content = await page.content()

            # MODE BRANCHING
            if self.analysis_mode == 'single':
                # Single page analysis (original behavior)
                print(f"   🔍 Single page analysis mode")
                self.evidence = await self._analyze_single_page(page, self.url, html_content)
                # Inject page load timing into scan_timing
                if 'scan_timing' in self.evidence:
                    self.evidence['scan_timing']['page_load_seconds'] = _page_load_seconds
                    total = _page_load_seconds + self.evidence['scan_timing'].get('total_extraction_seconds', 0)
                    self.evidence['scan_timing']['total_seconds'] = round(total, 2)
                    self.evidence['scan_timing']['pattern'] = (
                        f"Total {total:.1f}s — page load {_page_load_seconds:.1f}s, "
                        f"extraction {self.evidence['scan_timing'].get('total_extraction_seconds', 0):.1f}s"
                    )

            elif self.analysis_mode == 'smart-nav':
                # Multi-page analysis via navigation
                print(f"   🧭 Smart nav sampling mode - analyzing 3 pages")

                # Discover URLs to analyze
                urls_to_analyze = await self._smart_nav_sample(page, self.url)

                # Analyze each URL
                page_results = {}
                for idx, (label, url) in enumerate(urls_to_analyze.items(), 1):
                    print(f"\n{'='*60}")
                    print(f"📄 [{idx}/{len(urls_to_analyze)}] Analyzing {label}")
                    print(f"{'='*60}")

                    # Reset network tracking for each page
                    self.network_requests = []
                    self.network_responses = []

                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(3)
                        html_content = await page.content()

                        page_results[label] = await self._analyze_single_page(page, url, html_content)
                        print(f"   ✅ {label} analysis complete")
                    except Exception as e:
                        error_msg = str(e)[:200]
                        print(f"   ❌ Failed to analyze {label}: {error_msg}")
                        # Provide minimal valid structure so synthesis doesn't break
                        page_results[label] = {
                            'error': error_msg,
                            'url': url,
                            'layout': {'pattern': 'Analysis Failed', 'confidence': 0},
                            'meta_info': {'url': url, 'error': error_msg}
                        }

                # Synthesize multi-page insights
                self.evidence = self._synthesize_multi_page(page_results, mode='smart-nav')
                self.evidence['urls_discovered'] = urls_to_analyze
                # Surface full URL inventory (Cloudflare pool or nav-discovered URLs)
                _cf_pool = self._cloudflare_urls if hasattr(self, '_cloudflare_urls') and self._cloudflare_urls else []
                if _cf_pool:
                    self.evidence['url_inventory'] = self._build_url_inventory(
                        _cf_pool, self.url,
                        sources={'cloudflare': _cf_pool, 'nav': list(urls_to_analyze.values())}
                    )
                    self.evidence['discovery_metadata'] = {
                        'total_discovered': len(_cf_pool),
                        'cloudflare_amplified': True,
                        'cloudflare_urls': len(_cf_pool),
                        'pages_analyzed': len(urls_to_analyze),
                    }

            elif self.analysis_mode == 'interactive':
                # Interactive discovery: click menus, discover pages, select diverse subset, analyze
                print(f"   🔍 Interactive discovery mode")

                # Navigate to base URL first
                await page.goto(self.url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)

                # Phase 1: Discover all links (static + interactive)
                discovery = await self._discover_interactive_links(page, self.url)

                # Phase 1.5: Amplify with Cloudflare (if available)
                # Interactive discovery finds 20-60 URLs from clicking menus on one page.
                # Cloudflare can find 200-1000+ URLs across the whole site in ~10 seconds.
                # Merge both pools so _select_diverse_pages picks from the richest set.
                all_urls = [l['url'] if isinstance(l, dict) else l for l in discovery['all_links']]
                _cf_amplified = False
                if self.discovery_method in ('cloudflare', 'auto'):
                    cf_urls = await self._discover_via_cloudflare(self.url, limit=100)
                    if cf_urls and len(cf_urls) > 0:
                        _pre_merge = len(set(all_urls))
                        all_urls = list(set(all_urls + cf_urls))
                        _post_merge = len(all_urls)
                        _cf_new = _post_merge - _pre_merge
                        print(f"   ☁️  Cloudflare amplified: {_pre_merge} interactive → {_post_merge} total (+{_cf_new} new)")
                        self._cloudflare_urls = cf_urls
                        _cf_amplified = True

                # Phase 2: Select diverse subset from the merged pool
                selected = self._select_diverse_pages(all_urls, self.url, max_pages=5)

                # Phase 3: Analyze each selected page
                page_results = {}
                for idx, (label, url) in enumerate(selected.items(), 1):
                    print(f"\n{'='*60}")
                    print(f"📄 [{idx}/{len(selected)}] Analyzing {label}")
                    print(f"{'='*60}")

                    self.network_requests = []
                    self.network_responses = []

                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(3)
                        html_content = await page.content()

                        page_results[label] = await self._analyze_single_page(page, url, html_content)
                        print(f"   ✅ {label} analysis complete")
                    except Exception as e:
                        error_msg = str(e)[:200]
                        print(f"   ❌ Failed to analyze {label}: {error_msg}")
                        page_results[label] = {
                            'error': error_msg,
                            'url': url,
                            'layout': {'pattern': 'Analysis Failed', 'confidence': 0},
                            'meta_info': {'url': url, 'error': error_msg}
                        }

                # Phase 4: Synthesize
                self.evidence = self._synthesize_multi_page(page_results, mode='interactive')
                self.evidence['urls_discovered'] = selected
                self.evidence['discovery_metadata'] = {
                    'total_discovered': len(all_urls),
                    'static_count': discovery['total_static'],
                    'interactive_count': discovery['total_interactive'],
                    'cloudflare_amplified': _cf_amplified,
                    'cloudflare_urls': len(self._cloudflare_urls) if hasattr(self, '_cloudflare_urls') and self._cloudflare_urls else 0,
                    'interaction_log': discovery['interaction_log'],
                }
                # Surface full URL inventory for user visibility
                self.evidence['url_inventory'] = self._build_url_inventory(
                    all_urls, self.url,
                    sources={
                        'interactive': [l['url'] if isinstance(l, dict) else l for l in discovery['all_links']],
                        'cloudflare': self._cloudflare_urls if hasattr(self, '_cloudflare_urls') and self._cloudflare_urls else [],
                    }
                )

            await browser.close()

        return self.evidence

    async def _extract_layout(self, page):
        """Extract layout patterns - Grid, Flexbox, Positioning"""
        print("   📐 Analyzing layout...")

        layout_data = await page.evaluate('''() => {
            const elements = document.querySelectorAll('*');
            const layouts = {
                grid_count: 0,
                flex_count: 0,
                absolute_count: 0,
                fixed_count: 0,
                sticky_count: 0,
                grid_examples: [],
                flex_examples: []
            };

            for (const el of elements) {
                const styles = window.getComputedStyle(el);
                const display = styles.display;
                const position = styles.position;
                // SVG elements have className as SVGAnimatedString — use baseVal fallback
                const safeClass = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const selector = el.id ? '#' + el.id : (safeClass ? '.' + safeClass.split(' ')[0] : el.tagName.toLowerCase());

                // Detect child tags for pattern annotation
                const childTags = Array.from(el.children).slice(0, 10).map(c => c.tagName.toLowerCase());
                const childCount = el.children.length;

                if (display === 'grid') {
                    layouts.grid_count++;
                    if (layouts.grid_examples.length < 3) {
                        const cols = styles.gridTemplateColumns || '';
                        const colParts = cols.split(' ').filter(Boolean);
                        const uniqueCols = [...new Set(colParts)];
                        // Pattern detection for grid
                        let pattern = 'Grid layout';
                        if (cols.includes('auto-fit') || cols.includes('auto-fill'))
                            pattern = 'Responsive card grid';
                        else if (uniqueCols.length === 1 && colParts.length >= 3)
                            pattern = colParts.length + '-column card grid';
                        else if (colParts.length === 2)
                            pattern = '2-column layout (content + sidebar)';
                        else if (colParts.length >= 4)
                            pattern = colParts.length + '-column grid';

                        layouts.grid_examples.push({
                            selector: selector,
                            columns: cols,
                            rows: styles.gridTemplateRows,
                            gap: styles.gap,
                            pattern: pattern,
                            child_count: childCount
                        });
                    }
                }

                if (display === 'flex') {
                    layouts.flex_count++;
                    if (layouts.flex_examples.length < 3) {
                        const dir = styles.flexDirection || 'row';
                        const justify = styles.justifyContent || 'normal';
                        const align = styles.alignItems || 'normal';
                        // Pattern detection for flex
                        let pattern = 'Flex container';
                        const hasButtons = childTags.some(t => t === 'button' || t === 'a');
                        const hasInputs = childTags.some(t => t === 'input' || t === 'textarea');
                        if (dir === 'row' && justify === 'space-between')
                            pattern = 'Spaced row (nav bar / header)';
                        else if (dir === 'row' && hasButtons && childCount <= 6)
                            pattern = 'Button row / toolbar';
                        else if (dir === 'row' && align === 'center' && childCount <= 4)
                            pattern = 'Centered row (icon + label)';
                        else if (dir === 'column' && childCount >= 3)
                            pattern = 'Vertical stack / card list';
                        else if (dir === 'row' && hasInputs)
                            pattern = 'Form row (input + button)';
                        else if (dir === 'row' && childCount >= 3)
                            pattern = 'Horizontal group (' + childCount + ' items)';

                        layouts.flex_examples.push({
                            selector: selector,
                            direction: dir,
                            wrap: styles.flexWrap,
                            justify: justify,
                            align: align,
                            pattern: pattern,
                            child_count: childCount
                        });
                    }
                }

                if (position === 'absolute') layouts.absolute_count++;
                if (position === 'fixed') layouts.fixed_count++;
                if (position === 'sticky') layouts.sticky_count++;
            }

            return layouts;
        }''')

        return {
            'pattern': self._determine_layout_pattern(layout_data),
            'confidence': self._calculate_layout_confidence(layout_data),
            'details': layout_data,
            'code_snippets': self._generate_layout_snippets(layout_data)
        }

    async def _extract_typography(self, page):
        """Extract typography system with intelligent scale detection"""
        print("   🖋️  Analyzing typography...")

        typo_data = await page.evaluate('''() => {
            const headings = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].map(tag => {
                const el = document.querySelector(tag);
                if (!el) return null;
                const styles = window.getComputedStyle(el);
                return {
                    tag,
                    fontFamily: styles.fontFamily,
                    fontSize: styles.fontSize,
                    fontWeight: styles.fontWeight,
                    lineHeight: styles.lineHeight,
                    letterSpacing: styles.letterSpacing
                };
            }).filter(Boolean);

            const body = window.getComputedStyle(document.body);
            const paragraph = document.querySelector('p');
            const pStyles = paragraph ? window.getComputedStyle(paragraph) : body;

            // NEW: Collect ALL unique fonts, sizes, and weights across the page
            const allFonts = new Set();
            const allSizes = new Set();
            const allWeights = new Set();

            // Sample a reasonable number of elements (not all, for performance)
            const elements = document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, a, button, li');
            for (const el of elements) {
                const styles = window.getComputedStyle(el);
                if (styles.fontFamily) allFonts.add(styles.fontFamily);
                if (styles.fontSize) allSizes.add(styles.fontSize);
                if (styles.fontWeight) allWeights.add(styles.fontWeight);
            }

            return {
                headings,
                body: {
                    fontFamily: body.fontFamily,
                    fontSize: body.fontSize,
                    fontWeight: body.fontWeight,
                    lineHeight: body.lineHeight
                },
                paragraph: {
                    fontSize: pStyles.fontSize,
                    lineHeight: pStyles.lineHeight,
                    color: pStyles.color
                },
                // NEW: Comprehensive data for intelligent analysis
                all_fonts: Array.from(allFonts),
                all_sizes: Array.from(allSizes),
                all_weights: Array.from(allWeights)
            };
        }''')

        # Get stylesheet URLs for web font detection
        stylesheet_urls = await page.evaluate('''() => {
            const stylesheets = Array.from(document.styleSheets);
            return stylesheets.map(s => s.href).filter(Boolean);
        }''')

        # NEW: Intelligent typography analysis
        typography_intelligence = None
        try:
            from typography_intelligence import extract_typography_intelligence
            typography_intelligence = extract_typography_intelligence(typo_data, stylesheet_urls)
            print(f"      ✅ Type scale: {typography_intelligence['type_scale']['pattern']} ({typography_intelligence['confidence']}%)")
        except Exception as e:
            print(f"      ⚠️  Typography intelligence failed: {str(e)[:100]}")

        # OLD: Keep for backwards compatibility
        type_scale = self._calculate_type_scale(typo_data)

        # Fix key name: JS returns 'all_fonts', not 'font_families'
        all_fonts = typo_data.get('all_fonts', [])
        all_sizes = typo_data.get('all_sizes', [])
        all_weights = typo_data.get('all_weights', [])

        # Build enriched type_scale dict (was bare float)
        type_scale_dict = None
        if type_scale is not None:
            heading_sizes = []
            for h in typo_data.get('headings', []):
                try:
                    heading_sizes.append(float(h['fontSize'].replace('px', '')))
                except (ValueError, KeyError, TypeError):
                    pass
            size_floats = []
            for s in all_sizes:
                try:
                    size_floats.append(float(str(s).replace('px', '')))
                except (ValueError, TypeError):
                    pass
            type_scale_dict = {
                'ratio': type_scale,
                'sizes_px': sorted(set(size_floats)),
                'heading_sizes_px': sorted(set(heading_sizes), reverse=True),
            }

        # Confidence: based on actual data found
        font_bonus = min(30, len(all_fonts) * 10)
        size_bonus = min(15, len(all_sizes) * 2)
        scale_bonus = 15 if type_scale else 0

        result = {
            'pattern': self._determine_typo_pattern(typo_data),
            'confidence': min(95, 40 + font_bonus + size_bonus + scale_bonus),
            'details': typo_data,
            'type_scale': type_scale_dict if type_scale_dict else type_scale,
            'font_families': all_fonts,
            'font_sizes': all_sizes,
            'font_weights': all_weights,
            'code_snippets': self._generate_typo_snippets(typo_data)
        }

        # Add intelligent analysis if available
        if typography_intelligence:
            result['intelligent_typography'] = typography_intelligence

        return result

    async def _extract_colors(self, page):
        """Extract color palette from CSS and computed styles with intelligent classification"""
        print("   🎨 Extracting color palette...")

        color_data = await page.evaluate('''() => {
            const colorCounts = {};

            // Get all elements with usage counts
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                const styles = window.getComputedStyle(el);

                // Count color usage
                [styles.color, styles.backgroundColor, styles.borderColor].forEach(color => {
                    if (color && color !== 'rgba(0, 0, 0, 0)') {
                        colorCounts[color] = (colorCounts[color] || 0) + 1;
                    }
                });
            }

            // Also check CSS variables
            const rootStyles = window.getComputedStyle(document.documentElement);
            const cssVars = {};
            for (let i = 0; i < rootStyles.length; i++) {
                const prop = rootStyles[i];
                if (prop.startsWith('--') && prop.includes('color')) {
                    cssVars[prop] = rootStyles.getPropertyValue(prop);
                }
            }

            return {
                color_counts: colorCounts,
                css_variables: cssVars
            };
        }''')

        # Convert RGB/RGBA to hex for clustering
        hex_color_counts = self._convert_to_hex_counts(color_data['color_counts'])

        # NEW: Intelligent color analysis with clustering
        color_intelligence = None
        try:
            from color_intelligence import extract_color_intelligence
            color_intelligence = extract_color_intelligence(hex_color_counts)
            print(f"      ✅ Classified {len(color_intelligence.get('color_palette', {}))} color roles")
        except Exception as e:
            print(f"      ⚠️  Color intelligence failed: {str(e)[:100]}")

        # OLD: Basic palette analysis (keep for backwards compatibility)
        all_colors = list(color_data['color_counts'].keys())
        palette = self._analyze_color_palette(all_colors)

        # Visual preview (keep existing functionality for UI)
        hex_colors = self._extract_hex_colors(palette['primary'])
        preview_analysis = None
        if hex_colors:
            try:
                preview_gen = ColorPalettePreview(hex_colors[:10])  # Limit to 10 colors
                preview_analysis = preview_gen.analyze_palette()
            except Exception as e:
                print(f"      ⚠️  Preview generation failed: {str(e)[:100]}")

        # Combine old and new analysis
        result = {
            'pattern': f"{len(palette['primary'])} primary colors detected",
            'confidence': color_intelligence.get('confidence', 80) if color_intelligence else 80,
            'palette': palette,  # OLD: For backwards compatibility
            'css_variables': color_data['css_variables'],
            'code_snippets': self._generate_color_snippets(palette),
            'preview': preview_analysis  # Keep for UI visual display
        }

        # Add intelligent analysis if available
        if color_intelligence:
            result['intelligent_palette'] = color_intelligence.get('color_palette', {})
            result['evidence_trail'] = color_intelligence.get('evidence_trail', {})
            result['total_colors_analyzed'] = color_intelligence.get('total_colors_analyzed', 0)

        # Store for accessibility contrast checking
        self._last_color_analysis = result

        return result

    async def _extract_animations(self, page):
        """Detect CSS animations, transitions, and JS animation libraries"""
        print("   ✨ Analyzing animations...")

        anim_data = await page.evaluate('''() => {
            const animated = {
                transitions: [],
                animations: [],
                keyframes: [],
                libraries: {
                    gsap: !!window.gsap,
                    anime: !!window.anime,
                    threejs: !!window.THREE,
                    lottie: !!window.lottie
                }
            };

            // Defaults that mean "no animation/transition active"
            // "all" alone = global catch-all set by frameworks like Squarespace — not a specific transition
            const defaultTrans = ['none 0s ease 0s', 'all 0s ease 0s', 'none', '', 'all'];
            const defaultAnim = 'none 0s ease 0s 1 normal none running';

            const elements = document.querySelectorAll('*');
            const seenTrans = new Set();
            const seenAnim = new Set();
            for (const el of elements) {
                const styles = window.getComputedStyle(el);
                const safeClass = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const cls = safeClass.split(/\\s+/).filter(Boolean);
                const selector = el.id ? '#' + el.id : (cls[0] ? '.' + cls[0] : el.tagName.toLowerCase());

                const trans = styles.transition;
                if (trans && !defaultTrans.includes(trans)) {
                    const tKey = selector + '|' + trans;
                    if (!seenTrans.has(tKey)) {
                        seenTrans.add(tKey);
                        animated.transitions.push({ selector: selector, transition: trans });
                    }
                }

                const anim = styles.animation;
                if (anim && anim !== defaultAnim && !anim.startsWith('none')) {
                    const aKey = selector + '|' + anim;
                    if (!seenAnim.has(aKey)) {
                        seenAnim.add(aKey);
                        animated.animations.push({ selector: selector, animation: anim });
                    }
                }
            }

            // Extract @keyframes from stylesheets
            try {
                for (const sheet of document.styleSheets) {
                    try {
                        for (const rule of sheet.cssRules) {
                            if (rule.type === CSSRule.KEYFRAMES_RULE) {
                                animated.keyframes.push({
                                    name: rule.name,
                                    cssText: rule.cssText.substring(0, 500)
                                });
                            }
                        }
                    } catch(e) { /* cross-origin sheet */ }
                }
            } catch(e) {}

            return animated;
        }''')

        return {
            'pattern': self._determine_animation_pattern(anim_data),
            'confidence': min(90, 40 + len(anim_data.get('animations', [])) * 5),
            'details': anim_data,
            'code_snippets': self._generate_animation_snippets(anim_data)
        }

    async def _extract_accessibility(self, page):
        """Check ARIA attributes, semantic HTML, contrast ratios"""
        print("   ♿ Checking accessibility...")

        a11y_data = await page.evaluate('''() => {
            return {
                aria_labels: document.querySelectorAll('[aria-label]').length,
                aria_roles: document.querySelectorAll('[role]').length,
                alt_tags: document.querySelectorAll('img[alt]').length,
                total_images: document.querySelectorAll('img').length,
                semantic_html: {
                    header: document.querySelectorAll('header').length,
                    nav: document.querySelectorAll('nav').length,
                    main: document.querySelectorAll('main').length,
                    footer: document.querySelectorAll('footer').length,
                    article: document.querySelectorAll('article').length
                },
                lang_attribute: document.documentElement.lang || 'missing'
            };
        }''')

        # Add contrast checking if color analysis is available
        contrast_analysis = None
        if hasattr(self, '_last_color_analysis') and self._last_color_analysis:
            from contrast_checker import analyze_color_palette_contrast
            color_palette = self._last_color_analysis.get('intelligent_palette', {})
            if color_palette:
                contrast_analysis = analyze_color_palette_contrast(color_palette)

        score = self._calculate_a11y_score(a11y_data, contrast_analysis)

        result = {
            'pattern': f"Accessibility Score: {score}/100",
            'confidence': score,
            'score': score,
            'details': a11y_data,
            'recommendations': self._generate_a11y_recommendations(a11y_data, contrast_analysis)
        }

        # Add contrast analysis if available
        if contrast_analysis:
            result['contrast_analysis'] = contrast_analysis

        return result

    async def _extract_performance(self, page):
        """Measure performance metrics including Core Web Vitals"""
        print("   ⚡ Measuring performance...")

        perf_data = await page.evaluate('''() => {
            const perf = performance.getEntriesByType('navigation')[0];

            // Core Web Vitals - LCP, FID, CLS
            let lcp = 0;
            let fid = 0;
            let cls = 0;
            let inp = 0;

            // LCP (Largest Contentful Paint)
            const lcpEntry = performance.getEntriesByType('largest-contentful-paint');
            if (lcpEntry.length > 0) {
                lcp = lcpEntry[lcpEntry.length - 1].renderTime || lcpEntry[lcpEntry.length - 1].loadTime;
            }

            // FID (First Input Delay) - requires user interaction, may be 0
            const fidEntry = performance.getEntriesByType('first-input');
            if (fidEntry.length > 0) {
                fid = fidEntry[0].processingStart - fidEntry[0].startTime;
            }

            // CLS (Cumulative Layout Shift)
            const clsEntries = performance.getEntriesByType('layout-shift');
            clsEntries.forEach(entry => {
                if (!entry.hadRecentInput) {
                    cls += entry.value;
                }
            });

            // INP (Interaction to Next Paint) - approximate from event timing
            const eventEntries = performance.getEntriesByType('event');
            if (eventEntries.length > 0) {
                const durations = eventEntries.map(e => e.duration);
                inp = Math.max(...durations);
            }

            return {
                dom_content_loaded: perf?.domContentLoadedEventEnd - perf?.domContentLoadedEventStart,
                load_complete: perf?.loadEventEnd - perf?.loadEventStart,
                dom_interactive: perf?.domInteractive - perf?.fetchStart,
                total_resources: performance.getEntriesByType('resource').length,
                // Core Web Vitals
                lcp: lcp,
                fid: fid,
                inp: inp,
                cls: cls,
                // Supporting metrics
                ttfb: perf?.responseStart - perf?.requestStart,
                fcp: performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint')?.startTime || 0
            };
        }''')

        # Analyze resource sizes
        resource_summary = self._analyze_resources()

        # Analyze Core Web Vitals
        core_web_vitals = None
        try:
            from core_web_vitals import analyze_core_web_vitals
            vitals_data = {
                'lcp': perf_data.get('lcp', 0),
                'fid': perf_data.get('fid', 0),
                'inp': perf_data.get('inp', 0),
                'cls': perf_data.get('cls', 0),
                'ttfb': perf_data.get('ttfb', 0),
                'fcp': perf_data.get('fcp', 0)
            }
            core_web_vitals = analyze_core_web_vitals(vitals_data)
            print(f"      ✅ Core Web Vitals: {core_web_vitals['summary']['overall_rating']}")
        except Exception as e:
            print(f"      ⚠️  Core Web Vitals failed: {str(e)[:100]}")

        result = {
            'pattern': f"Load time: {perf_data.get('load_complete', 0):.0f}ms",
            'confidence': 95,
            'timings': perf_data,
            'resources': resource_summary,
            'recommendations': self._generate_perf_recommendations(perf_data, resource_summary)
        }

        # Add Core Web Vitals if available
        if core_web_vitals:
            result['core_web_vitals'] = core_web_vitals

        return result

    async def _extract_dom_depth(self, page):
        """Calculate DOM nesting depth for performance analysis"""
        print("   🌳 Analyzing DOM depth...")

        dom_data = await page.evaluate('''() => {
            function getMaxDepth(element, currentDepth = 1) {
                if (!element.children || element.children.length === 0) {
                    return currentDepth;
                }

                let maxChildDepth = currentDepth;
                for (let child of element.children) {
                    const childDepth = getMaxDepth(child, currentDepth + 1);
                    maxChildDepth = Math.max(maxChildDepth, childDepth);
                }
                return maxChildDepth;
            }

            const maxDepth = getMaxDepth(document.body);
            const totalElements = document.querySelectorAll('*').length;

            // Find deepest paths
            const deepPaths = [];
            function findDeepPaths(element, depth, path = []) {
                if (depth > maxDepth - 3) {
                    const tagPath = path.map(el => {
                        const id = el.id ? `#${el.id}` : '';
                        const classes = el.className && typeof el.className === 'string' ?
                            `.${el.className.split(' ').filter(c => c).slice(0, 2).join('.')}` : '';
                        return el.tagName.toLowerCase() + id + classes;
                    }).join(' > ');
                    deepPaths.push(tagPath);
                }

                for (let child of (element.children || [])) {
                    findDeepPaths(child, depth + 1, [...path, child]);
                }
            }
            findDeepPaths(document.body, 1, [document.body]);

            return {
                max_depth: maxDepth,
                total_elements: totalElements,
                average_depth: Math.round(totalElements / maxDepth),
                deep_paths: deepPaths.slice(0, 3)
            };
        }''')

        max_depth = dom_data.get('max_depth', 0)

        # Determine complexity level
        if max_depth <= 10:
            complexity = 'Low (Optimal)'
            health = 'excellent'
        elif max_depth <= 15:
            complexity = 'Medium (Good)'
            health = 'good'
        elif max_depth <= 20:
            complexity = 'High (Acceptable)'
            health = 'acceptable'
        else:
            complexity = 'Very High (Performance Risk)'
            health = 'poor'

        return {
            'pattern': f"Max depth: {max_depth} levels",
            'confidence': 100,
            'max_depth': max_depth,
            'total_elements': dom_data.get('total_elements', 0),
            'average_depth': dom_data.get('average_depth', 0),
            'complexity': complexity,
            'health': health,
            'deep_paths': dom_data.get('deep_paths', []),
            'recommendation': 'Typical depth is 10-15 levels. Deeper nesting can impact rendering performance.' if max_depth > 15 else 'DOM depth is within optimal range.'
        }

    async def _analyze_content_layout(self, page, page_type: str) -> Dict:
        """
        Analyze HOW content is displayed — not just what's there, but the reading experience.

        For article/blog pages: card grid dimensions, reading width, card styling, list vs grid
        For landing pages: section layout, hero sizing, CTA placement

        This bridges the gap between "55 flexbox containers" (layout extractor)
        and "how do they actually show articles when you read?" (user intent).
        """
        result = await page.evaluate("""(pageType) => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;

            // ── 1. Find the content container ──
            const main = document.querySelector('main') || document.querySelector('[role="main"]') ||
                         document.querySelector('article') || document.querySelector('.content') ||
                         document.querySelector('#content') || document.body;

            // ── 2. Reading Width Detection ──
            // Find the narrowest max-width container that wraps main content
            let readingContainer = main;
            let el = main;
            let containerMaxWidth = vw;
            while (el && el !== document.body) {
                const s = getComputedStyle(el);
                const mw = parseFloat(s.maxWidth);
                if (!isNaN(mw) && mw < vw && mw > 300) {
                    if (mw < containerMaxWidth) {
                        containerMaxWidth = mw;
                        readingContainer = el;
                    }
                }
                el = el.parentElement;
            }

            // Compute character width at reading container
            const containerStyles = getComputedStyle(readingContainer);
            const fontSize = parseFloat(containerStyles.fontSize) || 16;
            const charsPerLine = Math.round(containerMaxWidth / (fontSize * 0.5));
            const readingWidthVerdict = charsPerLine >= 45 && charsPerLine <= 75 ? 'optimal' :
                                        charsPerLine < 45 ? 'too narrow' : 'too wide';

            // ── 3. Card/Article Grid Detection ──
            // Find repeating content items (articles, cards, products)
            const cardSelectors = [
                'article', '.card', '[class*="card"]', '.post', '[class*="post"]',
                '.item', '[class*="item"]', '.product', '[class*="product"]',
                '.episode', '.show', '.mix'
            ];
            let cards = [];
            let cardSelector = '';
            for (const sel of cardSelectors) {
                const found = main.querySelectorAll(sel);
                if (found.length >= 3 && found.length > cards.length) {
                    cards = Array.from(found);
                    cardSelector = sel;
                }
            }

            let cardLayout = { type: 'none', cards_found: 0 };

            if (cards.length >= 3) {
                // Measure card dimensions
                const rects = cards.slice(0, 20).map(c => {
                    const r = c.getBoundingClientRect();
                    const s = getComputedStyle(c);
                    return {
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                        top: Math.round(r.top),
                        left: Math.round(r.left),
                        borderRadius: s.borderRadius,
                        boxShadow: s.boxShadow,
                        background: s.backgroundColor,
                        border: s.border,
                        padding: s.padding,
                        aspectRatio: r.width > 0 ? Math.round((r.height / r.width) * 100) / 100 : 0
                    };
                });

                // Determine layout type by analyzing card positions
                const uniqueTops = [...new Set(rects.map(r => Math.round(r.top / 20) * 20))];
                const uniqueLefts = [...new Set(rects.map(r => Math.round(r.left / 20) * 20))];

                // Cards per row
                const firstRowTop = rects[0].top;
                const firstRowCards = rects.filter(r => Math.abs(r.top - firstRowTop) < 40);
                const cardsPerRow = firstRowCards.length;

                let layoutType = 'list';  // default: single column
                if (cardsPerRow >= 3) layoutType = 'grid';
                else if (cardsPerRow === 2) layoutType = 'two-column';

                // Check for masonry (varying heights in same row)
                if (cardsPerRow >= 2) {
                    const heights = firstRowCards.map(r => r.height);
                    const heightVariance = Math.max(...heights) - Math.min(...heights);
                    if (heightVariance > 50) layoutType = 'masonry';
                }

                // Gap between cards
                let horizontalGap = 0;
                let verticalGap = 0;
                if (firstRowCards.length >= 2) {
                    horizontalGap = Math.round(firstRowCards[1].left - (firstRowCards[0].left + firstRowCards[0].width));
                }
                if (uniqueTops.length >= 2) {
                    const row1 = rects.filter(r => Math.abs(r.top - rects[0].top) < 40);
                    const row2 = rects.filter(r => Math.abs(r.top - uniqueTops[1] * 1) < 40 && Math.abs(r.top - rects[0].top) > 40);
                    if (row1.length && row2.length) {
                        verticalGap = Math.round(row2[0].top - (row1[0].top + row1[0].height));
                    }
                }

                // Average card dimensions
                const avgWidth = Math.round(rects.reduce((s, r) => s + r.width, 0) / rects.length);
                const avgHeight = Math.round(rects.reduce((s, r) => s + r.height, 0) / rects.length);
                const avgAspectRatio = Math.round(rects.reduce((s, r) => s + r.aspectRatio, 0) / rects.length * 100) / 100;

                // Card has image?
                const cardsWithImages = cards.slice(0, 10).filter(c => c.querySelector('img, picture, video')).length;
                const imageRatio = cardsWithImages / Math.min(cards.length, 10);

                // Card content structure
                const sampleCard = cards[0];
                const cardAnatomy = {
                    has_image: !!sampleCard.querySelector('img, picture, video'),
                    has_heading: !!sampleCard.querySelector('h1, h2, h3, h4'),
                    has_text: !!sampleCard.querySelector('p, .excerpt, .description, .summary'),
                    has_meta: !!sampleCard.querySelector('time, .date, .author, .category, .tag'),
                    has_cta: !!sampleCard.querySelector('a[class*="btn"], a[class*="button"], button'),
                    has_badge: !!sampleCard.querySelector('.badge, .tag, .label, .category, [class*="badge"]')
                };

                // Card styling
                const firstStyle = rects[0];
                const cardStyling = {
                    border_radius: firstStyle.borderRadius,
                    has_shadow: firstStyle.boxShadow !== 'none',
                    has_border: firstStyle.border !== 'none' && firstStyle.border !== '',
                    background: firstStyle.background,
                    padding: firstStyle.padding
                };

                cardLayout = {
                    type: layoutType,
                    cards_found: cards.length,
                    cards_per_row: cardsPerRow,
                    selector: cardSelector,
                    avg_width: avgWidth,
                    avg_height: avgHeight,
                    avg_aspect_ratio: avgAspectRatio,
                    horizontal_gap: Math.max(0, horizontalGap),
                    vertical_gap: Math.max(0, verticalGap),
                    image_ratio: Math.round(imageRatio * 100),
                    card_anatomy: cardAnatomy,
                    card_styling: cardStyling,
                    dimensions_note: `${avgWidth}×${avgHeight}px cards in ${layoutType} layout (${cardsPerRow} per row)`
                };
            }

            // ── 4. Article Reading View (for single articles) ──
            let readingView = null;
            if (pageType === 'singleArticle') {
                const article = document.querySelector('article') || main;
                const articleRect = article.getBoundingClientRect();
                const articleStyle = getComputedStyle(article);

                // Text metrics
                const paragraphs = article.querySelectorAll('p');
                const lineHeights = Array.from(paragraphs).slice(0, 5).map(p => {
                    const s = getComputedStyle(p);
                    return parseFloat(s.lineHeight) / parseFloat(s.fontSize);
                }).filter(v => !isNaN(v));

                const avgLineHeight = lineHeights.length ?
                    Math.round(lineHeights.reduce((a, b) => a + b, 0) / lineHeights.length * 100) / 100 : 0;

                // Pull quotes, blockquotes, code blocks
                const pullQuotes = article.querySelectorAll('blockquote, .pullquote, .highlight-quote').length;
                const codeBlocks = article.querySelectorAll('pre, code, .code-block').length;
                const inlineImages = article.querySelectorAll('img, figure').length;

                readingView = {
                    content_width: Math.round(articleRect.width),
                    font_size: Math.round(fontSize),
                    line_height_ratio: avgLineHeight,
                    chars_per_line: charsPerLine,
                    pull_quotes: pullQuotes,
                    code_blocks: codeBlocks,
                    inline_images: inlineImages,
                    paragraph_count: paragraphs.length,
                    reading_comfort: readingWidthVerdict
                };
            }

            // ── 5. Section Layout (for landing pages) ──
            let sectionLayout = null;
            if (pageType === 'landingPage') {
                const sections = Array.from(main.querySelectorAll('section, [class*="section"]')).slice(0, 10);
                sectionLayout = sections.map((s, i) => {
                    const r = s.getBoundingClientRect();
                    const st = getComputedStyle(s);
                    const heading = s.querySelector('h1, h2, h3');
                    const bg = st.backgroundColor;
                    return {
                        index: i,
                        heading: heading?.innerText?.trim()?.substring(0, 60) || null,
                        height: Math.round(r.height),
                        width: Math.round(r.width),
                        background: bg,
                        has_cta: !!s.querySelector('a[class*="btn"], a[class*="button"], button'),
                        children_count: s.children.length,
                        spans_viewport: r.width >= vw * 0.95,
                        type: r.height > vh * 0.8 ? 'hero' : r.height > 200 ? 'content' : 'compact'
                    };
                });
            }

            return {
                reading_width: {
                    container_max_width: Math.round(containerMaxWidth),
                    font_size: Math.round(fontSize),
                    chars_per_line: charsPerLine,
                    verdict: readingWidthVerdict,
                    container_selector: readingContainer.tagName.toLowerCase() +
                        (readingContainer.className ? '.' + readingContainer.className.split(' ')[0] : '')
                },
                card_layout: cardLayout,
                reading_view: readingView,
                section_layout: sectionLayout,
                viewport: { width: vw, height: vh }
            };
        }""", page_type)

        # Add confidence and pattern summary
        cl = result.get('card_layout', {})
        rw = result.get('reading_width', {})
        rv = result.get('reading_view')

        parts = []
        if cl.get('type') != 'none':
            parts.append(f"{cl.get('cards_found', 0)} cards in {cl.get('type')} layout ({cl.get('cards_per_row', 1)}/row)")
        if rw.get('verdict'):
            parts.append(f"Reading width: {rw.get('chars_per_line', 0)} chars/line ({rw.get('verdict')})")
        if rv:
            parts.append(f"Article: {rv.get('paragraph_count', 0)} paragraphs, {rv.get('font_size', 16)}px font")

        result['pattern'] = ' · '.join(parts) if parts else 'Content layout analyzed'
        result['confidence'] = 75 if cl.get('type') != 'none' else 50

        return result

    async def _extract_seo(self, page):
        """Extract SEO-related metadata"""
        print("   🔍 Analyzing SEO...")

        seo_data = await page.evaluate('''() => {
            const getMeta = (name) => {
                const meta = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
                return meta ? meta.content : null;
            };

            return {
                title: document.title,
                description: getMeta('description'),
                og_title: getMeta('og:title'),
                og_description: getMeta('og:description'),
                og_image: getMeta('og:image'),
                twitter_card: getMeta('twitter:card'),
                canonical: document.querySelector('link[rel="canonical"]')?.href,
                h1_count: document.querySelectorAll('h1').length,
                h1_text: document.querySelector('h1')?.innerText
            };
        }''')

        score = self._calculate_seo_score(seo_data)

        return {
            'pattern': f"SEO Score: {score}/100",
            'confidence': score,  # confidence tracks score — all checks are deterministic
            'score': score,
            'details': seo_data,
            'recommendations': self._generate_seo_recommendations(seo_data)
        }

    async def _extract_security(self, page):
        """Check security headers and HTTPS"""
        print("   🔒 Checking security...")

        security_data = {
            'https': self.url.startswith('https'),
            'csp_header': None,
            'cors_headers': [],
            'security_headers': {}
        }

        # Check response headers
        for resp in self.network_responses:
            if resp['url'] == self.url:
                headers = resp['headers']
                security_data['csp_header'] = headers.get('content-security-policy')
                security_data['security_headers'] = {
                    'x-frame-options': headers.get('x-frame-options'),
                    'x-content-type-options': headers.get('x-content-type-options'),
                    'strict-transport-security': headers.get('strict-transport-security')
                }
                break

        score = self._calculate_security_score(security_data)

        return {
            'pattern': f"Security Score: {score}/100",
            'confidence': score,
            'score': score,
            'details': security_data,
            'recommendations': self._generate_security_recommendations(security_data)
        }

    def _analyze_api_patterns(self):
        """Analyze API request patterns with relationship mapping"""
        print("   📡 Analyzing API patterns...")

        api_requests = [r for r in self.network_requests if r['resource_type'] in ['xhr', 'fetch']]

        patterns = {
            'rest_apis': [],
            'graphql': [],
            'websockets': [],
            'total_api_calls': len(api_requests)
        }

        for req in api_requests:
            url = req['url']
            if 'graphql' in url.lower():
                patterns['graphql'].append(url)
            elif 'ws://' in url or 'wss://' in url:
                patterns['websockets'].append(url)
            else:
                patterns['rest_apis'].append(url)

        # Generate API relationship map
        relationship_map = None
        if api_requests:
            try:
                mapper = APIRelationshipMapper(api_requests)
                relationship_map = mapper.analyze_relationships()
            except Exception as e:
                print(f"      ⚠️  Relationship mapping failed: {str(e)[:100]}")

        return {
            'pattern': self._determine_api_pattern(patterns),
            'confidence': min(90, 40 + len((relationship_map or {}).get('endpoints', [])) * 5),
            'details': patterns,
            'code_snippets': self._generate_api_snippets(patterns),
            'relationship_map': relationship_map  # NEW: API relationships
        }

    async def _extract_site_architecture(self, page):
        """
        Detect site architecture from window globals, script tags, and DOM signals.
        Returns an ERD-style map: what the site IS and what it DOES or DOES NOT do.
        No network capture changes needed — all evidence is on the rendered page.
        """
        print("   🏗️  Detecting site architecture...")

        arch_data = await page.evaluate('''() => {
            const result = {
                // --- Entity detection ---
                framework: null,          // Next.js | Nuxt | React | Vue | Angular | Svelte | vanilla
                state_mgmt: null,         // Redux | Vuex | Zustand | Jotai | Context | MobX | none
                router_type: null,        // client-side | server-rendered | hash-based
                data_layer: null,         // apollo | relay | swr | react-query | tpc | none
                auth_detected: false,     // user object or auth token signal present

                // --- Capability flags (does / does not) ---
                capabilities: {
                    client_side_routing: false,
                    server_side_rendering: false,
                    hydration: false,
                    graphql: false,
                    feature_flags: false,
                    prefetching: false,
                    websockets: false,
                    service_worker: false,
                    i18n: false
                },

                // --- Evidence trail (what proved each conclusion) ---
                evidence: [],

                // --- Hydration payload snapshot (shape only, no sensitive values) ---
                hydration_keys: [],

                // --- Route templates detected ---
                routes: []
            };

            // ── 1. Framework detection via window globals + meta ──
            if (window.__NEXT_DATA__) {
                result.framework = 'Next.js';
                result.evidence.push('window.__NEXT_DATA__ present');

                // Next.js gives us route templates for free
                const nd = window.__NEXT_DATA__;
                if (nd.page) result.routes.push(nd.page);
                if (nd.props && nd.props.pageProps) {
                    result.hydration_keys = Object.keys(nd.props.pageProps).slice(0, 12);
                }
                // SSR + hydration are inherent to Next.js
                result.capabilities.server_side_rendering = true;
                result.capabilities.hydration = true;
                result.evidence.push('Next.js: SSR + hydration by default');

                // Prefetch: Next.js prefetches by default in production
                result.capabilities.prefetching = true;
                result.evidence.push('Next.js: route prefetching enabled by default');

                // Auth signal: pageProps.user or pageProps.session or similar
                const pp = nd.props && nd.props.pageProps || {};
                if (pp.user || pp.session || pp.currentUser || pp.me || pp.account) {
                    result.auth_detected = true;
                    const key = pp.user ? 'user' : pp.session ? 'session' : pp.currentUser ? 'currentUser' : pp.me ? 'me' : 'account';
                    result.evidence.push('Auth: pageProps.' + key + ' present');
                }
            } else if (window.__NUXT__) {
                result.framework = 'Nuxt';
                result.evidence.push('window.__NUXT__ present');
                result.capabilities.server_side_rendering = true;
                result.capabilities.hydration = true;
                if (window.__NUXT__.state) {
                    result.hydration_keys = Object.keys(window.__NUXT__.state).slice(0, 12);
                }
            } else if (window.__APOLLO_STATE__ || window.__APOLLO_CLIENT__) {
                result.evidence.push('Apollo client detected');
                result.capabilities.graphql = true;
            }

            // React detection (even without Next.js)
            if (!result.framework) {
                // React DevTools hook or _reactRootContainer
                const rootEl = document.getElementById('root') || document.getElementById('app') || document.getElementById('__next');
                if (rootEl && rootEl._reactRootContainer) {
                    result.framework = 'React';
                    result.evidence.push('_reactRootContainer on #root');
                } else if (rootEl && rootEl.__vue_app__) {
                    result.framework = 'Vue';
                    result.evidence.push('__vue_app__ on #app');
                } else if (window.ng) {
                    result.framework = 'Angular';
                    result.evidence.push('window.ng present');
                }
            }

            // ── 2. State management detection ──
            if (window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__ || window.__REDUX_DEVTOOLS_EXTENSION__) {
                result.state_mgmt = 'Redux';
                result.evidence.push('Redux DevTools extension hook detected');
            } else if (window.__APOLLO_STATE__) {
                result.state_mgmt = 'Apollo';
                result.evidence.push('Apollo state cache present');
            } else if (window.__NUXT__ && window.__NUXT__.state) {
                result.state_mgmt = 'Vuex/Pinia';
                result.evidence.push('Nuxt state present (Vuex or Pinia)');
            }

            // ── 3. Router type detection ──
            if (window.location.hash && window.location.hash.length > 2) {
                result.router_type = 'hash-based';
                result.evidence.push('Hash fragment in URL: ' + window.location.hash.substring(0, 40));
            } else if (result.framework === 'Next.js' || result.framework === 'Nuxt') {
                result.router_type = 'client-side';
                result.capabilities.client_side_routing = true;
                result.evidence.push(result.framework + ' uses client-side routing');
            } else if (result.framework === 'React' || result.framework === 'Vue') {
                // Likely has client-side router but we can't be 100% sure without nav
                result.router_type = 'client-side (probable)';
                result.capabilities.client_side_routing = true;
                result.evidence.push(result.framework + ' detected — client-side routing probable');
            } else {
                result.router_type = 'server-rendered';
                result.evidence.push('No SPA framework globals — assuming server-rendered');
            }

            // ── 4. GraphQL detection ──
            // Already set above if Apollo, also check for other signals
            if (!result.capabilities.graphql) {
                // Relay, urql, or vanilla fetch to /graphql
                if (window.__RELAY_STORE__ || window.relay) {
                    result.capabilities.graphql = true;
                    result.data_layer = 'Relay';
                    result.evidence.push('Relay store detected');
                }
            }
            if (result.capabilities.graphql && !result.data_layer) {
                result.data_layer = 'Apollo';
            }

            // ── 5. Data layer detection (non-GraphQL) ──
            if (!result.data_layer) {
                // SWR sets window.__SWR_CACHE__ in dev
                if (window.__SWR_CACHE__) {
                    result.data_layer = 'SWR';
                    result.evidence.push('SWR cache present');
                }
                // React Query devtools
                else if (window.__REACT_QUERY_DEVTOOLS__) {
                    result.data_layer = 'React Query';
                    result.evidence.push('React Query devtools hook present');
                }
            }

            // ── 6. Feature flags ──
            if (window.__FEATURE_FLAGS__ || window.__FLAGS__ || window.featureFlags) {
                result.capabilities.feature_flags = true;
                const flags = window.__FEATURE_FLAGS__ || window.__FLAGS__ || window.featureFlags;
                result.evidence.push('Feature flags object: ' + Object.keys(flags).slice(0, 5).join(', '));
            }
            // LaunchDarkly, Unleash, etc. inject global references
            if (window.LDClient || window.ldClient) {
                result.capabilities.feature_flags = true;
                result.evidence.push('LaunchDarkly client detected');
            }

            // ── 7. Service worker ──
            if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
                result.capabilities.service_worker = true;
                result.evidence.push('Active service worker registered');
            }

            // ── 8. WebSocket detection ──
            // Check if any WebSocket connections exist via performance entries
            try {
                const resources = performance.getEntriesByType('resource');
                const wsLike = resources.filter(r => r.name.startsWith('ws://') || r.name.startsWith('wss://'));
                if (wsLike.length > 0) {
                    result.capabilities.websockets = true;
                    result.evidence.push('WebSocket resource entries found');
                }
            } catch(e) {}

            // ── 9. i18n detection ──
            if (window.i18n || window.__i18n__ || window.I18n || window.intl) {
                result.capabilities.i18n = true;
                result.evidence.push('i18n global detected');
            }
            // next-i18next injects locale into __NEXT_DATA__
            if (window.__NEXT_DATA__ && window.__NEXT_DATA__.props && window.__NEXT_DATA__.props.pageProps && window.__NEXT_DATA__.props.pageProps.locale) {
                result.capabilities.i18n = true;
                result.evidence.push('Locale in Next.js pageProps');
            }

            // ── 10. Script tag analysis — bundler + chunk strategy ──
            const scripts = Array.from(document.querySelectorAll('script[src]'));
            const scriptUrls = scripts.map(s => s.src);
            const bundlerSignals = { webpack: false, vite: false, parcel: false, rollup: false };
            scriptUrls.forEach(function(url) {
                if (url.includes('webpack') || url.includes('chunk')) bundlerSignals.webpack = true;
                if (url.includes('/@vite/') || url.includes('/src/') || url.includes('.module.')) bundlerSignals.vite = true;
                if (url.includes('parcel')) bundlerSignals.parcel = true;
            });
            result.bundler = bundlerSignals.vite ? 'Vite' : bundlerSignals.webpack ? 'Webpack' : bundlerSignals.parcel ? 'Parcel' : null;
            if (result.bundler) result.evidence.push('Bundler: ' + result.bundler + ' (from script src patterns)');

            // Prefetch links (framework or manual)
            const prefetchLinks = document.querySelectorAll('link[rel="prefetch"], link[rel="preload"]');
            if (prefetchLinks.length > 0) {
                result.capabilities.prefetching = true;
                if (!result.evidence.some(function(e) { return e.includes('prefetch'); })) {
                    result.evidence.push(prefetchLinks.length + ' prefetch/preload link tags');
                }
            }

            return result;
        }''')

        # Compute confidence: more evidence = higher confidence
        evidence_count = len(arch_data.get('evidence', []))
        confidence = min(40 + evidence_count * 12, 95)  # 40 base + 12 per signal, cap 95

        # If literally nothing was detected, still return a useful "vanilla" result
        if not arch_data.get('framework'):
            arch_data['framework'] = 'vanilla / unknown'

        return {
            'pattern': arch_data.get('framework', 'unknown'),
            'confidence': confidence,
            'details': arch_data
        }

    async def _extract_css_tricks(self, page):
        """Detect advanced CSS techniques"""
        print("   🎯 Detecting CSS tricks...")

        css_data = await page.evaluate('''() => {
            const root = window.getComputedStyle(document.documentElement);
            const tricks = {
                custom_properties: [],
                supports_rules: [],
                viewport_units: false,
                css_grid_advanced: false,
                blend_modes: false,
                clip_path: false
            };

            // Check for CSS variables
            for (let i = 0; i < root.length; i++) {
                const prop = root[i];
                if (prop.startsWith('--')) {
                    tricks.custom_properties.push({
                        name: prop,
                        value: root.getPropertyValue(prop)
                    });
                }
            }

            // Check elements for advanced features
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                const styles = window.getComputedStyle(el);

                if (styles.width.includes('vw') || styles.height.includes('vh')) {
                    tricks.viewport_units = true;
                }
                if (styles.mixBlendMode !== 'normal') {
                    tricks.blend_modes = true;
                }
                if (styles.clipPath !== 'none') {
                    tricks.clip_path = true;
                }
            }

            return tricks;
        }''')

        return {
            'pattern': f"{len(css_data['custom_properties'])} CSS variables detected",
            'confidence': min(90, 50 + len(css_data.get('custom_properties', [])) * 2),
            'details': css_data,
            'code_snippets': self._generate_css_tricks_snippets(css_data)
        }

    async def _extract_interactive_elements(self, page):
        """Deep inspection of interactive elements: buttons, inputs, forms, links-as-buttons.
        Captures visual style, groups by appearance, and surfaces selectors + counts."""
        print("   🎮 Analyzing interactive elements...")

        # Execute in small, focused evaluations to avoid any string-length
        # or context issues with a single giant page.evaluate call.

        # 1. Buttons
        _buttons = await page.evaluate('''() => {
            const out = [];
            document.querySelectorAll("button").forEach(el => {
                const s = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const cls = (typeof el.className === "string" ? el.className : (el.className.baseVal || "")).split(/\\s+/).filter(Boolean);
                const sel = el.id ? "#" + el.id : (cls[0] ? "." + cls[0] : "button");
                out.push({
                    text: (el.textContent || "").replace(/\\s+/g, " ").trim().substring(0, 40),
                    selector: sel,
                    bg: s.backgroundColor,
                    color: s.color,
                    borderRadius: s.borderRadius,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    type: el.getAttribute("type") || "button"
                });
            });
            return out;
        }''')

        # 2. Links styled as buttons
        _linkButtons = await page.evaluate('''() => {
            const out = [];
            document.querySelectorAll("a").forEach(el => {
                const cls = (typeof el.className === "string" ? el.className : (el.className.baseVal || "")).toLowerCase();
                const s = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const hasBtnClass = /btn|button/.test(cls);
                const hasBg = s.backgroundColor && s.backgroundColor !== "rgba(0, 0, 0, 0)" && s.backgroundColor !== "transparent";
                if (hasBtnClass || hasBg) {
                    const classes = cls.split(/\\s+/).filter(Boolean);
                    const sel = el.id ? "#" + el.id : (classes[0] ? "." + classes[0] : "a");
                    out.push({
                        text: (el.textContent || "").replace(/\\s+/g, " ").trim().substring(0, 40),
                        selector: sel,
                        href: el.getAttribute("href") || "",
                        bg: s.backgroundColor,
                        color: s.color,
                        borderRadius: s.borderRadius,
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    });
                }
            });
            return out;
        }''')

        # 3. Inputs
        _inputs = await page.evaluate('''() => {
            const out = [];
            document.querySelectorAll("input, select, textarea").forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const s = window.getComputedStyle(el);
                let labelText = "";
                if (el.id) {
                    try {
                        const lbl = document.querySelector("label[for=\\"" + CSS.escape(el.id) + "\\"]");
                        if (lbl) labelText = lbl.textContent.trim();
                    } catch(e) {}
                }
                if (!labelText && el.closest("label")) {
                    labelText = el.closest("label").textContent.replace(el.value || "", "").trim();
                }
                const cls = (typeof el.className === "string" ? el.className : (el.className.baseVal || "")).split(/\\s+/).filter(Boolean);
                const sel = el.id ? "#" + CSS.escape(el.id) : (cls[0] ? "." + CSS.escape(cls[0]) : el.tagName.toLowerCase());
                out.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute("type") || (el.tagName === "SELECT" ? "select" : "textarea"),
                    placeholder: el.getAttribute("placeholder") || "",
                    name: el.getAttribute("name") || "",
                    label: labelText.substring(0, 40),
                    selector: sel,
                    required: el.required || false,
                    bg: s.backgroundColor,
                    borderRadius: s.borderRadius,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                });
            });
            return out;
        }''')

        # 4. Forms
        _forms = await page.evaluate('''() => {
            const out = [];
            document.querySelectorAll("form").forEach(el => {
                const rect = el.getBoundingClientRect();
                const cls = (typeof el.className === "string" ? el.className : (el.className.baseVal || "")).split(/\\s+/).filter(Boolean);
                const sel = el.id ? "#" + el.id : (cls[0] ? "." + cls[0] : "form");
                out.push({
                    selector: sel,
                    action: el.getAttribute("action") || "",
                    method: (el.getAttribute("method") || "get").toUpperCase(),
                    inputCount: el.querySelectorAll("input, select, textarea").length,
                    buttonCount: el.querySelectorAll("button, input[type=submit], input[type=button]").length,
                    visible: rect.width > 0 && rect.height > 0
                });
            });
            return out;
        }''')

        # 5. Counts (modals, dropdowns)
        _counts = await page.evaluate('''() => ({
            modals: document.querySelectorAll("[role=\\"dialog\\"], .modal, [class*=\\"modal\\"]").length,
            dropdowns: document.querySelectorAll("select, [role=\\"listbox\\"], [class*=\\"dropdown\\"]").length
        })''')

        # Assemble + group button styles
        _allBtns = _buttons + _linkButtons
        _styleMap = {}
        for btn in _allBtns:
            key = btn['bg'] + '|' + btn['borderRadius']
            if key not in _styleMap:
                _styleMap[key] = {'bg': btn['bg'], 'color': btn['color'], 'borderRadius': btn['borderRadius'], 'count': 0, 'examples': []}
            _styleMap[key]['count'] += 1
            if len(_styleMap[key]['examples']) < 3:
                _styleMap[key]['examples'].append({'text': btn['text'], 'selector': btn['selector'], 'width': btn.get('width', 0), 'height': btn.get('height', 0)})
        _buttonStyles = sorted(_styleMap.values(), key=lambda s: -s['count'])

        interactive_data = {
            'buttons': _buttons,
            'linkButtons': _linkButtons,
            'inputs': _inputs,
            'forms': _forms,
            'buttonStyles': _buttonStyles,
            'counts': {
                'buttons': len(_buttons),
                'linkButtons': len(_linkButtons),
                'inputs': len(_inputs),
                'forms': len(_forms),
                'modals': _counts.get('modals', 0),
                'dropdowns': _counts.get('dropdowns', 0)
            }
        }

        # Build a summary pattern string
        counts = interactive_data.get('counts', {})
        parts = []
        if counts.get('buttons', 0) + counts.get('linkButtons', 0) > 0:
            parts.append(f"{counts['buttons'] + counts.get('linkButtons', 0)} buttons")
        if counts.get('inputs', 0) > 0:
            parts.append(f"{counts['inputs']} inputs")
        if counts.get('forms', 0) > 0:
            parts.append(f"{counts['forms']} forms")

        return {
            'pattern': ', '.join(parts) if parts else 'No interactive elements',
            'confidence': min(95, 50 + sum(counts.values()) * 2),
            'counts': counts,
            'button_styles': interactive_data.get('buttonStyles', []),
            'buttons': interactive_data.get('buttons', []),
            'link_buttons': interactive_data.get('linkButtons', []),
            'inputs': interactive_data.get('inputs', []),
            'forms': interactive_data.get('forms', [])
        }

    def _analyze_third_party(self):
        """Detect third-party services"""
        print("   🔌 Detecting third-party integrations...")

        third_party = {
            'analytics': [],
            'fonts': [],
            'cdns': [],
            'advertising': []
        }

        for req in self.network_requests:
            url = req['url']

            # Analytics
            if any(x in url for x in ['google-analytics', 'gtag', 'segment.', 'mixpanel']):
                third_party['analytics'].append(url)

            # Fonts
            if any(x in url for x in ['fonts.googleapis', 'typekit', 'fonts.gstatic']):
                third_party['fonts'].append(url)

            # CDNs
            if any(x in url for x in ['cloudflare', 'fastly', 'cloudfront', 'jsdelivr', 'unpkg']):
                third_party['cdns'].append(url)

        return {
            'pattern': f"{len(third_party['analytics'])} analytics services detected",
            'confidence': min(90, 40 + sum(len(v) for v in third_party.values()) * 10),
            'details': third_party
        }

    async def _extract_interaction_states(self, page):
        """Extract hover/focus/active style deltas from modern CSS approaches.

        Modern sites use three approaches for interaction states:
        1. Traditional :hover/:focus CSS rules in stylesheets
        2. Tailwind/utility classes (hover:bg-blue-500)
        3. CSS-in-JS libraries (styled-components, emotion)

        This method detects all three and combines results.
        """
        print("   🎮 Extracting interaction states...")

        from collections import defaultdict

        # Strategy 1: Traditional CSS pseudo-class rules
        traditional_rules = await page.evaluate('''() => {
            const results = [];
            const pseudos = [':hover', ':focus', ':active', ':focus-within', ':focus-visible'];
            try {
                for (const sheet of document.styleSheets) {
                    let rules;
                    try { rules = sheet.cssRules || sheet.rules; }
                    catch(e) { continue; } // cross-origin stylesheet
                    if (!rules) continue;
                    for (const rule of rules) {
                        if (!rule.selectorText) continue;
                        const sel = rule.selectorText;
                        const matchedPseudo = pseudos.find(p => sel.includes(p));
                        if (!matchedPseudo) continue;
                        const base = sel.replace(matchedPseudo, '').replace(/::before|::after/g, '').trim();
                        if (!base || base.length > 120) continue;
                        const props = {};
                        for (let i = 0; i < rule.style.length; i++) {
                            const prop = rule.style[i];
                            props[prop] = rule.style.getPropertyValue(prop);
                        }
                        if (Object.keys(props).length === 0) continue;
                        results.push({ base, pseudo: matchedPseudo, props });
                    }
                }
            } catch(e) {}
            return results;
        }''')

        # Strategy 2: Extract Tailwind/utility interaction classes from DOM
        utility_classes = await page.evaluate('''() => {
            const allElements = document.querySelectorAll('*');
            const interactionClasses = {
                hover: [],
                focus: [],
                active: [],
                disabled: []
            };

            allElements.forEach(el => {
                if (!el.className || typeof el.className !== 'string') return;

                const classes = el.className.split(' ').filter(c => c.trim());

                classes.forEach(c => {
                    if (c.startsWith('hover:')) interactionClasses.hover.push(c);
                    else if (c.startsWith('focus:')) interactionClasses.focus.push(c);
                    else if (c.startsWith('active:')) interactionClasses.active.push(c);
                    else if (c.startsWith('disabled:')) interactionClasses.disabled.push(c);
                });
            });

            // Deduplicate and count
            return {
                hover: [...new Set(interactionClasses.hover)],
                focus: [...new Set(interactionClasses.focus)],
                active: [...new Set(interactionClasses.active)],
                disabled: [...new Set(interactionClasses.disabled)]
            };
        }''')

        # Strategy 3: Check <style> tags for hover rules (CSS-in-JS)
        style_tag_rules = await page.evaluate('''() => {
            const allStyleTags = document.querySelectorAll('style');
            let hoverRules = [];

            allStyleTags.forEach(tag => {
                const content = tag.textContent;
                // Find hover rules
                const hoverRegex = /([^{}]+):hover\s*{([^}]*)}/g;
                let match;
                while ((match = hoverRegex.exec(content)) !== null && hoverRules.length < 20) {
                    hoverRules.push({
                        selector: match[1].trim(),
                        styles: match[2].trim()
                    });
                }
            });

            return hoverRules;
        }''')

        # Strategy 4: Programmatically trigger hover on interactive elements and detect changes
        computed_hover_states = await page.evaluate('''() => {
            const interactiveSelectors = ['button', 'a', '[role="button"]', 'input', 'select'];
            const detectedStates = [];

            for (const selector of interactiveSelectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length === 0) continue;

                // Sample first 3 of each type
                for (let i = 0; i < Math.min(3, elements.length); i++) {
                    const el = elements[i];
                    const normalBg = window.getComputedStyle(el).backgroundColor;
                    const normalColor = window.getComputedStyle(el).color;

                    // Trigger hover state
                    el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

                    const hoverBg = window.getComputedStyle(el).backgroundColor;
                    const hoverColor = window.getComputedStyle(el).color;

                    // Cleanup
                    el.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));

                    // Check if anything changed
                    if (normalBg !== hoverBg || normalColor !== hoverColor) {
                        detectedStates.push({
                            tag: el.tagName.toLowerCase(),
                            type: 'hover',
                            changes: {
                                bgChanged: normalBg !== hoverBg,
                                colorChanged: normalColor !== hoverColor
                            }
                        });
                    }
                }
            }

            return detectedStates;
        }''')

        # Combine all four strategies
        total_traditional = len(traditional_rules) if traditional_rules else 0
        total_utility = sum(len(v) for v in utility_classes.values())
        total_style_tags = len(style_tag_rules) if style_tag_rules else 0
        total_computed = len(computed_hover_states) if computed_hover_states else 0
        total_detections = total_traditional + total_utility + total_style_tags + total_computed

        if total_detections == 0:
            return {
                'pattern': 'No interaction state styles detected',
                'confidence': 30,
                'state_deltas': {},
                'utility_classes': {},
                'computed_states': {},
                'evidence_trail': {
                    'found': [
                        '0 traditional CSS pseudo-class rules',
                        '0 utility interaction classes',
                        '0 hover rules in <style> tags',
                        '0 computed hover state changes'
                    ],
                    'concluded': 'No hover/focus/active styles found across 4 detection strategies'
                }
            }

        # Process traditional CSS rules
        grouped_traditional = defaultdict(lambda: defaultdict(dict))
        for rule in (traditional_rules or []):
            base = rule['base']
            pseudo = rule['pseudo'].lstrip(':')
            for prop, val in rule['props'].items():
                grouped_traditional[base][pseudo][prop] = val

        # Classify selectors by type
        type_buckets = defaultdict(list)
        for sel in grouped_traditional:
            sel_lower = sel.lower().strip()
            if 'button' in sel_lower or 'btn' in sel_lower:
                type_buckets['buttons'].append(sel)
            elif sel_lower.startswith('a') or 'link' in sel_lower:
                type_buckets['links'].append(sel)
            elif 'input' in sel_lower or 'select' in sel_lower or 'textarea' in sel_lower or 'form' in sel_lower:
                type_buckets['inputs'].append(sel)
            elif 'nav' in sel_lower or 'menu' in sel_lower or 'tab' in sel_lower:
                type_buckets['navigation'].append(sel)
            else:
                type_buckets['other'].append(sel)

        # Build state_deltas for traditional CSS
        state_deltas = {}
        for sel, states in sorted(grouped_traditional.items(), key=lambda x: -sum(len(v) for v in x[1].values()))[:15]:
            state_deltas[sel] = {pseudo: dict(props) for pseudo, props in states.items()}

        # Count coverage
        pseudo_counts = defaultdict(int)
        for sel, states in grouped_traditional.items():
            for pseudo in states.keys():
                pseudo_counts[pseudo] += 1

        # Add all strategy counts together
        hover_count = (pseudo_counts.get('hover', 0) +
                       len(utility_classes.get('hover', [])) +
                       total_style_tags +
                       len([s for s in computed_hover_states if s.get('type') == 'hover']))
        focus_count = (pseudo_counts.get('focus', 0) +
                       pseudo_counts.get('focus-visible', 0) +
                       pseudo_counts.get('focus-within', 0) +
                       len(utility_classes.get('focus', [])))
        active_count = pseudo_counts.get('active', 0) + len(utility_classes.get('active', []))
        disabled_count = len(utility_classes.get('disabled', []))

        # Calculate confidence based on total coverage and detection diversity
        confidence = 40
        if hover_count > 3: confidence += 20
        if focus_count > 2: confidence += 15
        if active_count > 1: confidence += 10
        if total_detections > 10: confidence += 15
        # Bonus for using multiple detection strategies
        strategies_used = sum([total_traditional > 0, total_utility > 0, total_style_tags > 0, total_computed > 0])
        if strategies_used >= 2: confidence += 5
        confidence = min(confidence, 95)

        # Build pattern description
        pattern_parts = []
        if hover_count: pattern_parts.append(f'{hover_count} hover')
        if focus_count: pattern_parts.append(f'{focus_count} focus')
        if active_count: pattern_parts.append(f'{active_count} active')
        if disabled_count: pattern_parts.append(f'{disabled_count} disabled')

        detection_method = []
        if total_traditional > 0: detection_method.append('CSS pseudo-classes')
        if total_utility > 0: detection_method.append('utility classes')
        if total_style_tags > 0: detection_method.append('<style> tags')
        if total_computed > 0: detection_method.append('computed states')

        # Prepare computed states summary
        computed_summary = {}
        for state in computed_hover_states:
            tag = state.get('tag', 'unknown')
            if tag not in computed_summary:
                computed_summary[tag] = 0
            computed_summary[tag] += 1

        return {
            'pattern': f'{total_detections} interaction states detected ({", ".join(pattern_parts)}) via {" + ".join(detection_method)}',
            'confidence': confidence,
            'state_deltas': state_deltas,
            'utility_classes': utility_classes,
            'computed_states': computed_summary,
            'style_tag_rules_sample': style_tag_rules[:5] if style_tag_rules else [],
            'type_summary': {k: len(v) for k, v in type_buckets.items()},
            'detection_breakdown': {
                'traditional_css': total_traditional,
                'utility_classes': total_utility,
                'style_tags': total_style_tags,
                'computed_hover': total_computed
            },
            'evidence_trail': {
                'found': [
                    f'{total_traditional} traditional CSS pseudo-class rules',
                    f'{total_utility} utility interaction classes (Tailwind/etc)',
                    f'{total_style_tags} hover rules in <style> tags (CSS-in-JS)',
                    f'{total_computed} computed hover state changes',
                    f'{hover_count} hover states, {focus_count} focus states, {active_count} active states'
                ],
                'analyzed': [
                    'Scanned document.styleSheets for :hover/:focus/:active selectors',
                    'Extracted hover:*/focus:*/active:*/disabled:* utility classes from DOM',
                    'Searched <style> tags for CSS-in-JS hover rules',
                    'Programmatically triggered hover on buttons/links and detected style changes',
                    f'Combined all 4 detection strategies ({strategies_used} strategies had results)'
                ],
                'concluded': f'Site uses {", ".join(detection_method)} for {len(pattern_parts)} interaction state types'
            }
        }

    async def _extract_article_content(self, page):
        """Extract article content with confidence scoring"""
        print("   📄 Extracting article content...")

        # Try multiple strategies
        articles = []

        # Strategy 1: Look for <article> tags
        article_tags = self.soup.find_all('article')
        for article in article_tags[:5]:
            content = self._extract_article_from_element(article)
            if content:
                articles.append(content)

        # Strategy 2: Look for common article patterns
        if len(articles) == 0:
            for selector in ['.article', '.post', '.entry-content', 'main']:
                elements = self.soup.select(selector)
                for el in elements[:3]:
                    content = self._extract_article_from_element(el)
                    if content:
                        articles.append(content)
                        break

        return {
            'pattern': f"{len(articles)} articles found",
            'confidence': self._calculate_article_confidence(articles),
            'articles': articles
        }

    def _extract_article_from_element(self, element):
        """Extract article data from a DOM element"""
        title = element.find(['h1', 'h2', 'h3'])
        paragraphs = element.find_all('p')

        if not paragraphs or len(paragraphs) < 2:
            return None

        # Calculate confidence
        word_count = sum(len(p.get_text().split()) for p in paragraphs)
        has_title = title is not None
        has_date = element.find(['time', '.date', '.published']) is not None
        has_author = element.find(['.author', '.by-author']) is not None

        confidence = 50
        if has_title: confidence += 15
        if has_date: confidence += 10
        if has_author: confidence += 10
        if word_count > 100: confidence += 15

        return {
            'title': title.get_text().strip() if title else 'Untitled',
            'author': element.find(['.author', '.by-author']).get_text().strip() if element.find(['.author', '.by-author']) else 'Unknown',
            'date': element.find(['time', '.date']).get_text().strip() if element.find(['time', '.date']) else None,
            'preview': ' '.join([p.get_text() for p in paragraphs[:2]])[:200] + '...',
            'word_count': word_count,
            'confidence': min(confidence, 100),
            'status': 'Success' if confidence >= 70 else 'Warning' if confidence >= 50 else 'Failed'
        }

    # Helper methods for pattern determination and scoring
    def _determine_layout_pattern(self, data):
        if data['grid_count'] > data['flex_count']:
            return f"CSS Grid ({data['grid_count']} containers)"
        elif data['flex_count'] > 0:
            return f"Flexbox ({data['flex_count']} containers)"
        else:
            return "Traditional Layout"

    def _calculate_layout_confidence(self, data):
        if data['grid_count'] > 5 or data['flex_count'] > 5:
            return 95
        elif data['grid_count'] > 0 or data['flex_count'] > 0:
            return 80
        else:
            return 60

    def _determine_typo_pattern(self, data):
        body = data.get('body', {})
        font_family = body.get('fontFamily') or ''
        if not font_family:
            # Fallback: try first font from all_fonts
            all_fonts = data.get('all_fonts', [])
            font_family = all_fonts[0] if all_fonts else 'Unknown'
        primary_font = font_family.split(',')[0].strip().replace('"', '').replace("'", '')
        return primary_font or 'Unknown'

    def _calculate_type_scale(self, data):
        if not data['headings'] or len(data['headings']) < 2:
            return None

        sizes = [float(h['fontSize'].replace('px', '')) for h in data['headings']]
        if len(sizes) < 2:
            return None

        ratio = sizes[0] / sizes[1] if sizes[1] > 0 else 1
        return round(ratio, 2)

    def _analyze_color_palette(self, colors):
        # Simple color grouping - would need more sophisticated color analysis
        return {
            'primary': colors[:5],
            'secondary': colors[5:10] if len(colors) > 5 else []
        }

    def _extract_hex_colors(self, color_list):
        """Extract hex colors from rgb/rgba strings"""
        import re
        hex_colors = []

        for color_str in color_list:
            if not color_str:
                continue

            # If already hex
            if color_str.startswith('#'):
                hex_colors.append(color_str)
                continue

            # Convert rgb/rgba to hex
            rgb_match = re.search(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', color_str)
            if rgb_match:
                r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
                hex_color = f'#{r:02x}{g:02x}{b:02x}'
                hex_colors.append(hex_color)

        return list(set(hex_colors))  # Remove duplicates

    def _convert_to_hex_counts(self, color_counts):
        """Convert RGB/RGBA color counts to hex color counts"""
        import re
        hex_counts = {}

        for color_str, count in color_counts.items():
            if not color_str:
                continue

            # If already hex
            if color_str.startswith('#'):
                hex_counts[color_str] = hex_counts.get(color_str, 0) + count
                continue

            # Convert rgb/rgba to hex
            rgb_match = re.search(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', color_str)
            if rgb_match:
                r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
                hex_color = f'#{r:02x}{g:02x}{b:02x}'
                hex_counts[hex_color] = hex_counts.get(hex_color, 0) + count

        return hex_counts

    def _determine_animation_pattern(self, data):
        libs = [k for k, v in data['libraries'].items() if v]
        if libs:
            return f"JS Libraries: {', '.join(libs)}"

        parts = []
        if data.get('keyframes'):
            parts.append(f"{len(data['keyframes'])} @keyframes")
        if data['animations']:
            parts.append(f"{len(data['animations'])} animated elements")
        if data['transitions']:
            parts.append(f"{len(data['transitions'])} transitions")

        return ', '.join(parts) if parts else "No animations detected"

    def _calculate_a11y_score(self, data, contrast_analysis=None):
        score = 50
        if data['lang_attribute'] != 'missing': score += 10
        if data['aria_labels'] > 5: score += 15
        if data['semantic_html']['main'] > 0: score += 10
        if data['total_images'] > 0 and data['alt_tags'] / data['total_images'] > 0.8: score += 15

        # Contrast penalty: deduct for failing pairs (up to -20 points)
        if contrast_analysis:
            summary = contrast_analysis.get('summary', {})
            aa_pass_rate = summary.get('aa_pass_rate', 1.0)
            total_pairs = summary.get('total_pairs', 0)
            if total_pairs > 0 and aa_pass_rate < 1.0:
                # Scale penalty: 0% pass = -20, 50% pass = -10, 100% pass = 0
                penalty = int((1.0 - aa_pass_rate) * 20)
                score -= penalty

        return max(0, min(score, 100))

    def _calculate_seo_score(self, data):
        score = 0
        if data['title']: score += 20
        if data['description']: score += 20
        if data['og_title']: score += 15
        if data['canonical']: score += 15
        if data['h1_count'] == 1: score += 15
        if data['og_image']: score += 15
        return score

    def _calculate_security_score(self, data):
        score = 0
        if data['https']: score += 40
        if data['csp_header']: score += 20
        if data['security_headers'].get('x-frame-options'): score += 15
        if data['security_headers'].get('strict-transport-security'): score += 25
        return score

    def _determine_api_pattern(self, patterns):
        if len(patterns['graphql']) > 0:
            return f"GraphQL API ({len(patterns['graphql'])} queries)"
        elif len(patterns['rest_apis']) > 5:
            return f"REST API ({len(patterns['rest_apis'])} endpoints)"
        elif len(patterns['websockets']) > 0:
            return "WebSocket Real-time"
        else:
            return "Static Content"

    def _calculate_article_confidence(self, articles):
        if not articles:
            return 0
        avg_confidence = sum(a['confidence'] for a in articles) / len(articles)
        return int(avg_confidence)

    def _analyze_resources(self):
        by_type = {}
        for req in self.network_requests:
            rt = req['resource_type']
            if rt not in by_type:
                by_type[rt] = 0
            by_type[rt] += 1
        return by_type

    # Code snippet generators
    def _generate_layout_snippets(self, data):
        if data['grid_examples']:
            ex = data['grid_examples'][0]
            return f"{ex['selector']} {{\n  display: grid;\n  grid-template-columns: {ex['columns']};\n  gap: {ex['gap']};\n}}"
        return None

    def _generate_typo_snippets(self, data):
        body = data.get('body', {})
        font_family = body.get('fontFamily', 'system-ui') or 'system-ui'
        font_size = body.get('fontSize', '16px') or '16px'
        line_height = body.get('lineHeight', '1.5') or '1.5'
        return f"body {{\n  font-family: {font_family};\n  font-size: {font_size};\n  line-height: {line_height};\n}}"

    def _generate_color_snippets(self, palette):
        return ":root {\n  " + "\n  ".join([f"--color-{i}: {c};" for i, c in enumerate(palette['primary'][:3])]) + "\n}"

    def _generate_animation_snippets(self, data):
        parts = []
        # Keyframes first — most informative
        for kf in data.get('keyframes', [])[:2]:
            parts.append(kf['cssText'])
        # Then a transition example
        if data['transitions'] and len(parts) < 2:
            ex = data['transitions'][0]
            parts.append(f"{ex['selector']} {{\n  transition: {ex['transition']};\n}}")
        # Then an animation example
        if data['animations'] and len(parts) < 2:
            ex = data['animations'][0]
            parts.append(f"{ex['selector']} {{\n  animation: {ex['animation']};\n}}")
        return '\n\n'.join(parts) if parts else None

    def _generate_api_snippets(self, patterns):
        if patterns['graphql']:
            return "// GraphQL Query\nfetch('/graphql', {\n  method: 'POST',\n  body: JSON.stringify({ query: '...' })\n})"
        elif patterns['rest_apis']:
            return f"// REST API\nfetch('{patterns['rest_apis'][0]}')\n  .then(r => r.json())"
        return None

    def _generate_css_tricks_snippets(self, data):
        if data['custom_properties']:
            vars = data['custom_properties'][:3]
            return ":root {\n  " + "\n  ".join([f"{v['name']}: {v['value']};" for v in vars]) + "\n}"
        return None

    def _generate_a11y_recommendations(self, data, contrast_analysis=None):
        recs = []
        if data['lang_attribute'] == 'missing':
            recs.append("Add lang attribute to <html> tag")
        if data['total_images'] > 0 and data['alt_tags'] < data['total_images']:
            recs.append(f"Add alt text to {data['total_images'] - data['alt_tags']} images")

        # Add contrast recommendations (new)
        if contrast_analysis:
            summary = contrast_analysis.get('summary', {})
            aa_fails = summary.get('total_pairs', 0) - summary.get('aa_pass', 0)
            if aa_fails > 0:
                worst = summary.get('worst_contrast', {})
                recs.append(f"Fix {aa_fails} color pairs failing WCAG AA (worst: {worst.get('foreground')} on {worst.get('background')}, {worst.get('contrast_ratio')}:1)")

        return recs

    def _generate_seo_recommendations(self, data):
        recs = []
        if not data['description']:
            recs.append("Add meta description")
        if data['h1_count'] != 1:
            recs.append(f"Use exactly one H1 tag (currently: {data['h1_count']})")
        return recs

    def _generate_security_recommendations(self, data):
        recs = []
        if not data['https']:
            recs.append("Enable HTTPS")
        if not data['csp_header']:
            recs.append("Add Content-Security-Policy header")
        return recs

    def _generate_perf_recommendations(self, perf, resources):
        recs = []
        if perf.get('load_complete', 0) > 3000:
            recs.append("Optimize load time (currently > 3s)")
        if resources.get('image', 0) > 50:
            recs.append(f"Consider lazy loading images ({resources['image']} images)")
        return recs

    def _is_challenge_page(self, html: str) -> bool:
        """
        Detect bot protection challenge pages
        (Cloudflare, PerimeterX, Akamai, etc.)
        """
        challenge_indicators = [
            'cloudflare',
            'cf-browser-verification',
            'challenge-platform',
            'perimeterx',
            'px-captcha',
            'distil',
            'datadome',
            'just a moment',
            'checking your browser',
            'please wait while we verify',
            'enable javascript and cookies'
        ]

        html_lower = html.lower()
        return any(indicator in html_lower for indicator in challenge_indicators)

    async def _mri_scan(self) -> Dict:
        """
        Run Metadata MRI scan when full access is blocked

        Returns evidence dict with MRI results
        """
        scanner = MetadataMRI(self.url)
        mri_result = scanner.scan()

        # Convert MRI results to evidence format
        evidence = {
            'access_strategy': 'metadata_mri',
            'success': mri_result['success'],
            'confidence': mri_result['confidence'],
            'limitations': mri_result['limitations']
        }

        # Map MRI data to evidence structure
        if mri_result['success']:
            # Layout hints from structural analysis
            hints = mri_result['structural_hints']
            evidence['layout'] = {
                'pattern': hints.get('grid_system', 'Unknown (MRI mode)'),
                'confidence': 40,
                'access_limited': True,
                'details': {
                    'semantic_html': hints.get('semantic_html', False),
                    'has_header': hints.get('has_header', False),
                    'has_nav': hints.get('has_nav', False),
                    'has_main': hints.get('has_main', False),
                    'has_footer': hints.get('has_footer', False)
                }
            }

            # Typography — pull font stacks + size scale from CSS variables if available
            meta = mri_result['meta_tags']
            css_vars = mri_result.get('css_variables', {})
            css_fonts = css_vars.get('fonts', [])  # [{name, value}, ...]
            css_font_sizes = css_vars.get('font_sizes', [])
            if css_fonts or css_font_sizes:
                # Pick heading vs body font by variable name
                heading_font = next((f['value'] for f in css_fonts if 'heading' in f['name'].lower()), None)
                body_font = next((f['value'] for f in css_fonts if 'body' in f['name'].lower()), None)
                if not heading_font and css_fonts:
                    heading_font = css_fonts[0]['value']
                if not body_font and len(css_fonts) > 1:
                    body_font = css_fonts[1]['value']
                elif not body_font and css_fonts:
                    body_font = css_fonts[0]['value']

                # Map size tokens to pseudo-heading scale (largest → h1)
                size_labels = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
                def _parse_size(s):
                    import re as _re
                    m = _re.match(r'([\d.]+)(px|rem|em)', s)
                    if not m: return 0
                    val, unit = float(m.group(1)), m.group(2)
                    return val * 16 if unit == 'rem' else val if unit == 'px' else val * 16
                sorted_sizes = sorted(css_font_sizes, key=lambda x: _parse_size(x['value']), reverse=True)
                headings = []
                for i, size_item in enumerate(sorted_sizes[:6]):
                    headings.append({
                        'tag': size_labels[i] if i < len(size_labels) else 'span',
                        'fontSize': size_item['value'],
                        'fontWeight': 'bold' if i < 3 else '400',
                        'fontFamily': heading_font or 'sans-serif'
                    })
                token_label = css_vars.get('token_system') or 'CSS variables'
                evidence['typography'] = {
                    'pattern': f'{token_label} type system ({len(css_fonts)} font stacks)',
                    'confidence': 60,
                    'access_limited': True,
                    'details': {
                        'headings': headings,
                        'body': {
                            'fontFamily': body_font or 'sans-serif',
                            'fontSize': sorted_sizes[-1]['value'] if sorted_sizes else '16px'
                        }
                    }
                }
            else:
                evidence['typography'] = {
                    'pattern': 'Limited (MRI mode)',
                    'confidence': 20,
                    'access_limited': True,
                    'details': {
                        'title': meta.get('title', 'Unknown')
                    }
                }

            # Colors — extract from CSS custom properties in <style> blocks if available
            css_vars = mri_result.get('css_variables', {})
            css_colors = css_vars.get('colors', {})  # {value: var_name}
            if css_colors:
                # Categorize: primary = named tokens (primary/main/brand), secondary = everything else
                primary_colors = []
                secondary_colors = []
                primary_keywords = ('primary', 'main', 'brand', 'cta', 'accent', 'link')
                for color_val, var_name in css_colors.items():
                    if any(kw in var_name.lower() for kw in primary_keywords):
                        primary_colors.append(color_val)
                    else:
                        secondary_colors.append(color_val)
                token_label = css_vars.get('token_system') or 'CSS variables'
                evidence['colors'] = {
                    'pattern': f'{token_label} design tokens ({len(css_colors)} colors)',
                    'confidence': 65,
                    'access_limited': True,
                    'palette': {
                        'primary': primary_colors[:5],
                        'secondary': secondary_colors[:8],
                        'accent': []
                    }
                }
            else:
                evidence['colors'] = {
                    'pattern': 'Not available (MRI mode)',
                    'confidence': 0,
                    'access_limited': True,
                    'palette': {'primary': [], 'secondary': [], 'accent': []}
                }

            # Frameworks detected
            frameworks = mri_result['frameworks']
            evidence['frameworks'] = {
                'pattern': ', '.join(frameworks) if frameworks else 'Unknown (MRI mode)',
                'confidence': 60 if frameworks else 20,
                'access_limited': True,
                'detected': frameworks
            }

            # SEO - full access via meta tags; compute score from what's present
            seo_details = {
                'title': meta.get('title'),
                'description': meta.get('description'),
                'og_title': meta.get('title'),  # best guess from meta title
                'og_image': meta.get('image'),
                'og_type': meta.get('type'),
                'twitter_card': meta.get('twitter_card'),
                'schema_org': len(meta.get('schema_org', []))
            }
            # Score mirrors frontend createSEOCard weights:
            # title(20), description(20), og_title(15), canonical(15), h1===1(15), og_image(15)
            # MRI can't see canonical or h1 — those stay 0
            seo_score = 0
            if seo_details['title']:        seo_score += 20
            if seo_details['description']:  seo_score += 20
            if seo_details['og_title']:     seo_score += 15
            if seo_details['og_image']:     seo_score += 15

            evidence['seo'] = {
                'pattern': 'Meta tags available',
                'confidence': 80,
                'score': seo_score,
                'access_limited': False,
                'details': seo_details
            }

            # CDN info
            cdn_providers = mri_result['cdn_providers']
            evidence['cdn'] = {
                'pattern': ', '.join(cdn_providers) if cdn_providers else 'None detected',
                'confidence': 70,
                'providers': cdn_providers
            }

            # Stylesheets
            stylesheets = mri_result['stylesheets']
            evidence['stylesheets'] = {
                'pattern': f"{len(stylesheets)} stylesheets detected",
                'confidence': 60,
                'details': stylesheets
            }

            # Responsive breakpoints — from @media queries in <style> blocks
            css_breakpoints = css_vars.get('breakpoints', [])
            if css_breakpoints:
                # Map to named slots based on common thresholds
                bp_map = {}
                for bp in css_breakpoints:
                    if bp <= 600:
                        bp_map.setdefault('MOBILE', f'{bp}px')
                    elif bp <= 800:
                        bp_map.setdefault('TABLET', f'{bp}px')
                    elif bp <= 1000:
                        bp_map.setdefault('DESKTOP', f'{bp}px')
                    else:
                        bp_map.setdefault('WIDE', f'{bp}px')
                media_query_strs = [f"(min-width: {bp}px)" if i > 0 else f"(max-width: {bp}px)"
                                    for i, bp in enumerate(css_breakpoints)]
                evidence['responsive_breakpoints'] = {
                    'pattern': 'Custom breakpoints',
                    'confidence': 70,
                    'access_limited': True,
                    'breakpoints': bp_map,
                    'media_queries': media_query_strs
                }

            # Spacing scale — from CSS spacing tokens
            css_spacing = css_vars.get('spacing', [])
            if css_spacing:
                token_label = css_vars.get('token_system') or 'CSS variables'
                base_unit_label = 'rem' if any('rem' in s['value'] for s in css_spacing) else 'px'
                evidence['spacing_scale'] = {
                    'pattern': f'{token_label} spacing scale ({len(css_spacing)} steps)',
                    'confidence': 60,
                    'access_limited': True,
                    'base_unit': base_unit_label,
                    'scale': [{'value': s['value'], 'name': s['name']} for s in css_spacing],
                    'details': {
                        'scale': [{'value': s['value'], 'name': s['name']} for s in css_spacing],
                        'base_unit': base_unit_label
                    }
                }

            # Third-party services — CDNs and stylesheet domains we can see
            tp_cdns = [f"https://{p.lower()}.com" for p in cdn_providers] if cdn_providers else []
            from urllib.parse import urlparse as _urlparse
            _target_host = _urlparse(self.url).hostname or ''
            tp_fonts = [s['url'] for s in stylesheets if s.get('is_cdn') and any(f in s.get('url', '').lower() for f in ['font', 'google'])]
            evidence['third_party'] = {
                'pattern': f"{len(cdn_providers)} CDN provider(s) detected" if cdn_providers else 'No third-party CDNs detected',
                'confidence': 60,
                'access_limited': True,
                'details': {
                    'analytics': [],   # can't see without network intercept
                    'fonts': tp_fonts,
                    'cdns': tp_cdns,
                    'advertising': []  # can't see without network intercept
                }
            }

            # Security — bot protection itself signals HTTPS; we can't check headers directly
            evidence['security'] = {
                'pattern': 'Bot protection detected (implies HTTPS)',
                'confidence': 50,
                'access_limited': True,
                'score': 40,  # HTTPS confirmed via 403 from Cloudflare; headers unknown
                'details': {
                    'https': True,
                    'csp_header': None,
                    'security_headers': {}
                },
                'recommendations': [
                    'Full header analysis requires bypassing bot protection'
                ]
            }

            # Site Architecture — framework + routing + structural skeleton
            detected_frameworks = mri_result['frameworks']
            primary_fw = detected_frameworks[0] if detected_frameworks else 'vanilla'
            is_nextjs = 'Next.js' in detected_frameworks
            router_type = 'client-side (Next.js)' if is_nextjs else ('client-side (probable)' if 'React' in detected_frameworks or 'Vue.js' in detected_frameworks else 'traditional')
            evidence['site_architecture'] = {
                'pattern': f"Built with {primary_fw}",
                'confidence': 55,
                'access_limited': True,
                'details': {
                    'framework': primary_fw,
                    'router_type': router_type,
                    'data_layer': 'none detected',
                    'bundler': 'webpack' if is_nextjs else None,
                    'capabilities': {},
                    'evidence': [
                        f"Framework detected via HTML markers: {', '.join(detected_frameworks)}" if detected_frameworks else "No framework markers found",
                        f"Semantic structure: {'header, nav, main, footer' if hints.get('semantic_html') else 'minimal'}",
                        f"Grid system: {hints.get('grid_system', 'unknown')}"
                    ]
                }
            }

            # Meta info
            evidence['meta_info'] = {
                'access_strategy': 'metadata_mri',
                'bot_protection_detected': True,
                'full_analysis_unavailable': True,
                'what_we_can_see': [
                    'Meta tags (Open Graph, Twitter Cards)',
                    'External stylesheet references',
                    'Framework signatures',
                    'Structural HTML skeleton',
                    'CDN providers'
                ],
                'what_we_cannot_see': mri_result['limitations']
            }

        return evidence

    async def _capture_vh_region_states(self, page, top_regions: list) -> list:
        """
        Hover/focus the top VH-weighted regions to detect interactive states.

        Returns list of {region_index, selector, tag, hover_delta, focus_delta,
        transition, has_state_change} for each region.
        """
        from extractors.interaction_state_capture import STATE_PROPERTIES, _compute_delta

        results = []
        for idx, region in enumerate(top_regions):
            # Build CSS selector from region data
            sel = None
            if region.get('id'):
                sel = f"#{region['id']}"
            elif region.get('className'):
                first_cls = region['className'].strip().split()[0] if region['className'].strip() else None
                if first_cls:
                    sel = f"{region.get('tag', 'div')}.{first_cls}"
            if not sel:
                # Skip regions we can't reliably target
                results.append({
                    'region_index': idx, 'selector': None, 'tag': region.get('tag'),
                    'hover_delta': {}, 'focus_delta': {}, 'transition': 'none',
                    'has_state_change': False,
                })
                continue

            hover_delta = {}
            focus_delta = {}
            transition = 'none'

            try:
                locator = page.locator(sel).first
                if not await locator.is_visible(timeout=1000):
                    results.append({
                        'region_index': idx, 'selector': sel, 'tag': region.get('tag'),
                        'hover_delta': {}, 'focus_delta': {}, 'transition': 'none',
                        'has_state_change': False,
                    })
                    continue

                # Read resting styles
                resting = await page.evaluate('''(args) => {
                    const el = document.querySelector(args.sel);
                    if (!el) return null;
                    const s = window.getComputedStyle(el);
                    const out = {};
                    for (const p of args.props) out[p] = s[p] || '';
                    out._transition = s.transition || 'none';
                    return out;
                }''', {'sel': sel, 'props': STATE_PROPERTIES})

                if not resting:
                    results.append({
                        'region_index': idx, 'selector': sel, 'tag': region.get('tag'),
                        'hover_delta': {}, 'focus_delta': {}, 'transition': 'none',
                        'has_state_change': False,
                    })
                    continue

                transition = resting.pop('_transition', 'none')

                # Hover
                try:
                    await locator.hover(timeout=2000)
                    await page.wait_for_timeout(150)
                    hover_styles = await page.evaluate('''(args) => {
                        const el = document.querySelector(args.sel);
                        if (!el) return null;
                        const s = window.getComputedStyle(el);
                        const out = {};
                        for (const p of args.props) out[p] = s[p] || '';
                        return out;
                    }''', {'sel': sel, 'props': STATE_PROPERTIES})
                    if hover_styles:
                        hover_delta = _compute_delta(resting, hover_styles)
                except Exception:
                    pass

                # Focus
                try:
                    await page.mouse.move(0, 0)
                    await page.wait_for_timeout(100)
                    await locator.focus(timeout=2000)
                    await page.wait_for_timeout(100)
                    focus_styles = await page.evaluate('''(args) => {
                        const el = document.querySelector(args.sel);
                        if (!el) return null;
                        const s = window.getComputedStyle(el);
                        const out = {};
                        for (const p of args.props) out[p] = s[p] || '';
                        return out;
                    }''', {'sel': sel, 'props': STATE_PROPERTIES})
                    if focus_styles:
                        focus_delta = _compute_delta(resting, focus_styles)
                    await page.evaluate('(sel) => { const el = document.querySelector(sel); if (el && el.blur) el.blur(); }', sel)
                except Exception:
                    pass

            except Exception:
                pass

            results.append({
                'region_index': idx,
                'selector': sel,
                'tag': region.get('tag'),
                'hover_delta': hover_delta,
                'focus_delta': focus_delta,
                'transition': transition,
                'has_state_change': bool(hover_delta or focus_delta),
            })

        # Reset mouse
        try:
            await page.mouse.move(0, 0)
        except Exception:
            pass

        return results

    async def _discover_links(self, page, base_url: str) -> Dict:
        """
        Extract all links from the page and categorize them

        Returns:
            {
                'navigation': [...],  # Nav menu links
                'articles': [...],    # Article/content links
                'sections': [...],    # Section/category links
                'external': [...],    # External links
                'all': [...]          # All links
            }
        """
        links_data = await page.evaluate('''(baseUrl) => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const base = new URL(baseUrl);

            const categorized = {
                navigation: [],
                articles: [],
                sections: [],
                external: [],
                all: []
            };

            links.forEach(link => {
                const href = link.href;
                if (!href) return;

                try {
                    const url = new URL(href);
                    const path = url.pathname;

                    // Store all links
                    categorized.all.push({
                        url: href,
                        text: link.innerText.trim().substring(0, 100),
                        path: path
                    });

                    // External links
                    if (url.host !== base.host) {
                        categorized.external.push(href);
                        return;
                    }

                    // Navigation links (in nav, header, menu)
                    const parent = link.closest('nav, header, [role="navigation"], [class*="menu"], [class*="nav"]');
                    if (parent) {
                        categorized.navigation.push(href);
                        return;
                    }

                    // Article links (common patterns)
                    if (path.match(/\/(p|post|article|blog|read|editorial|story|interview)\//) ||
                        link.closest('article, [class*="article"], [class*="post"]')) {
                        categorized.articles.push(href);
                        return;
                    }

                    // Section links (shorter paths, category-like)
                    if (path.split('/').filter(p => p).length <= 2) {
                        categorized.sections.push(href);
                    }

                } catch (e) {
                    // Invalid URL, skip
                }
            });

            // Deduplicate
            Object.keys(categorized).forEach(key => {
                if (Array.isArray(categorized[key])) {
                    categorized[key] = [...new Set(categorized[key])];
                }
            });

            return categorized;
        }''', base_url)

        return links_data

    def _generate_architecture_diagrams(self, url: str, evidence: Dict) -> Dict:
        """
        Generate Mermaid diagram strings from site_architecture evidence.
        Returns dict with 'site_structure' and optionally 'url_patterns' Mermaid source.
        """
        arch = evidence.get('site_architecture', {})
        details = arch.get('details', {})

        if not details:
            return None

        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.hostname or url

        # Escape Mermaid special chars in labels
        def esc(s):
            return str(s).replace('"', "'").replace('[', '(').replace(']', ')')

        # ── Site Structure Diagram ──
        lines = ['graph TD']
        site_id = 'Site'
        lines.append(f'    {site_id}["{esc(domain)}"]')

        node_idx = 0
        def nid():
            nonlocal node_idx
            node_idx += 1
            return f'N{node_idx}'

        # Framework
        fw = details.get('framework')
        if fw and fw != 'vanilla / unknown':
            n = nid()
            lines.append(f'    {site_id} --> {n}["{esc(fw)}"]')
            lines.append(f'    style {n} fill:#1a73e8,stroke:#fff,color:#fff')

        # CSS Framework
        css_fw = details.get('css_framework')
        if css_fw:
            n = nid()
            lines.append(f'    {site_id} --> {n}["{esc(css_fw)}"]')
            lines.append(f'    style {n} fill:#06b6d4,stroke:#fff,color:#fff')

        # Bundler
        bundler = details.get('bundler')
        if bundler:
            n = nid()
            lines.append(f'    {site_id} --> {n}["{esc(bundler)}"]')
            lines.append(f'    style {n} fill:#f59e0b,stroke:#fff,color:#000')

        # State Management
        state = details.get('state_mgmt')
        if state:
            n = nid()
            lines.append(f'    {site_id} --> {n}["{esc(state)}"]')
            lines.append(f'    style {n} fill:#8b5cf6,stroke:#fff,color:#fff')

        # Router Type
        router = details.get('router_type')
        if router:
            n = nid()
            lines.append(f'    {site_id} --> {n}["Router: {esc(router)}"]')

        # Capabilities as a subgroup
        caps = details.get('capabilities', {})
        active_caps = [k.replace('_', ' ').title() for k, v in caps.items() if v]
        if active_caps:
            cap_id = nid()
            lines.append(f'    {site_id} --> {cap_id}["Capabilities"]')
            lines.append(f'    style {cap_id} fill:#10b981,stroke:#fff,color:#fff')
            for cap in active_caps[:6]:
                cn = nid()
                lines.append(f'    {cap_id} --> {cn}["{esc(cap)}"]')

        site_structure = '\n'.join(lines)

        # ── URL Pattern Diagram (from url_patterns evidence if available) ──
        url_patterns_mermaid = None
        url_pats = evidence.get('url_patterns', {})
        pat_details = url_pats.get('details', {}) if isinstance(url_pats, dict) else {}
        all_urls = pat_details.get('all', []) if isinstance(pat_details, dict) else []

        if all_urls and len(all_urls) > 1:
            url_lines = ['graph LR']
            root_id = 'ROOT'
            url_lines.append(f'    {root_id}["/"]')

            # Build path tree from URL paths
            path_tree = {}
            for u in all_urls[:30]:  # Cap at 30 to keep diagram readable
                try:
                    p = urlparse(u) if u.startswith('http') else urlparse(url + u)
                    path = p.path.strip('/')
                    if not path:
                        continue
                    segments = path.split('/')
                    node = path_tree
                    for seg in segments[:4]:  # Max depth 4
                        if seg not in node:
                            node[seg] = {}
                        node = node[seg]
                except Exception:
                    continue

            # Convert tree to Mermaid edges
            def tree_to_mermaid(tree, parent_id, depth=0):
                for seg, children in tree.items():
                    n = nid()
                    url_lines.append(f'    {parent_id} --> {n}["/{esc(seg)}"]')
                    if depth < 3:
                        tree_to_mermaid(children, n, depth + 1)

            tree_to_mermaid(path_tree, root_id)

            if len(url_lines) > 2:
                url_patterns_mermaid = '\n'.join(url_lines)

        result = {'site_structure': site_structure}
        if url_patterns_mermaid:
            result['url_patterns'] = url_patterns_mermaid

        # ── Site Topology Diagram (from site_topology evidence) ──
        topo = evidence.get('site_topology')
        if topo and isinstance(topo, dict) and topo.get('sections'):
            content_type_colors = {
                'documentation': '#1a73e8',
                'blog': '#10b981',
                'product': '#f59e0b',
                'developer': '#8b5cf6',
                'corporate': '#6b7280',
                'community': '#06b6d4',
                'media': '#ec4899',
                'other': '#64748b',
            }
            topo_lines = ['graph TD']
            topo_lines.append(f'    ROOT["{esc(domain)}"]')
            topo_lines.append(f'    style ROOT fill:#1e293b,stroke:#7c3aed,color:#fff')

            for section in topo['sections'][:10]:
                n = nid()
                s_path = section.get('path', '/')
                s_count = section.get('page_count', 0)
                s_type = section.get('type', 'other')
                label = f"{esc(s_path)} ({s_count} pages)"
                color = content_type_colors.get(s_type, '#64748b')
                topo_lines.append(f'    ROOT --> {n}["{label}"]')
                topo_lines.append(f'    style {n} fill:{color},stroke:#fff,color:#fff')

                # Show templates as children
                tmpl = section.get('template')
                if tmpl:
                    tn = nid()
                    topo_lines.append(f'    {n} -.-> {tn}["{esc(tmpl)}"]')
                    topo_lines.append(f'    style {tn} fill:#0f172a,stroke:#475569,color:#94a3b8')

            result['site_topology'] = '\n'.join(topo_lines)

        return result

    def _generate_llm_suggestions(self, url: str, links: Dict, content: Dict, components: Dict) -> Dict:
        """
        Generate suggestions for LLMs on what to analyze next

        Args:
            url: Current URL being analyzed
            links: Discovered links from _discover_links
            content: Content extraction results
            components: Component map results

        Returns:
            {
                'discovered_links': {...},
                'suggested_next_steps': [...],
                'url_patterns': {...},
                'analysis_tips': [...]
            }
        """
        from urllib.parse import urlparse

        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Detect URL patterns
        all_paths = [link.get('path', '') for link in links.get('all', [])]
        url_patterns = self._detect_url_patterns(all_paths)

        # Generate next step suggestions
        suggestions = []

        # Suggest navigation links
        nav_links = links.get('navigation', [])[:3]
        for nav_link in nav_links:
            suggestions.append({
                'url': nav_link,
                'reason': 'Main navigation link - likely a key section of the site',
                'priority': 'high',
                'category': 'navigation'
            })

        # Suggest article/content pages
        article_links = links.get('articles', [])[:3]
        for article_link in article_links:
            suggestions.append({
                'url': article_link,
                'reason': 'Content page - analyze to understand article/post template structure',
                'priority': 'medium',
                'category': 'content'
            })

        # Suggest section pages
        section_links = links.get('sections', [])[:2]
        for section_link in section_links:
            if section_link not in nav_links:  # Don't duplicate nav links
                suggestions.append({
                    'url': section_link,
                    'reason': 'Section/category page - compare list vs detail page layouts',
                    'priority': 'medium',
                    'category': 'section'
                })

        # Analysis tips based on what was found
        tips = []

        page_type = content.get('page_type', 'unknown')
        if page_type == 'home':
            tips.append("This is a homepage - good starting point. Next, analyze navigation links to understand site structure.")
        elif page_type == 'article':
            tips.append("This is an article page - compare with other articles to identify consistent patterns.")
        elif page_type == 'list':
            tips.append("This is a list/directory page - analyze individual items to understand content templates.")

        sections = components.get('sections', [])
        if len(sections) > 0:
            tips.append(f"Found {len(sections)} page sections with CSS selectors - use component_map for targeted extraction.")

        total_links = len(links.get('all', []))
        if total_links > 50:
            tips.append(f"Site has {total_links}+ links - use batch analysis with filtered URLs to avoid overload.")

        return {
            'discovered_links': {
                'navigation': links.get('navigation', []),
                'articles': links.get('articles', [])[:10],  # Limit to first 10
                'sections': links.get('sections', [])[:10],
                'external': links.get('external', [])[:5],
                'total_internal': len(links.get('all', [])) - len(links.get('external', []))
            },
            'suggested_next_steps': suggestions[:8],  # Top 8 suggestions
            'url_patterns': url_patterns,
            'analysis_tips': tips,
            'current_page_type': page_type,
            'base_url': base_url
        }

    def _detect_url_patterns(self, paths: List[str]) -> Dict:
        """
        Detect common URL patterns from a list of paths

        Returns:
            {
                'articles': '/p/{slug}',
                'sections': '/{name}',
                ...
            }
        """
        patterns = {}

        # Common article patterns
        article_patterns = ['/p/', '/post/', '/article/', '/blog/', '/read/', '/editorial/', '/story/']
        for pattern in article_patterns:
            if any(pattern in path for path in paths):
                patterns['articles'] = f"{pattern}{{slug}}"
                break

        # Section patterns (single-level paths)
        single_level = [p for p in paths if p and p.count('/') == 2 and p.startswith('/') and p.endswith('/')]
        if single_level:
            patterns['sections'] = '/{section-name}'

        # Tag patterns
        if any('/tag/' in path or '/tags/' in path for path in paths):
            patterns['tags'] = '/tag/{tag-name}'

        # Category patterns
        if any('/category/' in path or '/categories/' in path for path in paths):
            patterns['categories'] = '/category/{category-name}'

        return patterns


async def test_deep_engine():
    """Test deep extraction"""
    engine = DeepEvidenceEngine('https://nts.live')
    evidence = await engine.extract_all()

    print("\n" + "="*70)
    print(" DEEP EVIDENCE EXTRACTION COMPLETE")
    print("="*70)
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(test_deep_engine())
