"""
Editorial Signals Extractor

Runs 10 editorial-industry standard checks against a live page.
Designed for publishing sites (magazines, newspapers, editorial brands).

Tests:
  1. JSON-LD Structured Data       — @type, datePublished, author, headline, keywords
  2. Open Graph & Twitter Cards    — og:type, og:image, article:tag, twitter:card
  3. RSS Feed Discovery            — <head> link + path probe
  4. Pagination / Infinite Scroll  — next link, load-more button, page param
  5. Web Vitals (Navigation APIs)  — FCP, LCP, CLS, TTFB (no Lighthouse required)
  6. Accessibility                 — H1 presence, image alt coverage, heading sequence
  7. Internal Linking Patterns     — related articles, author archive URL
  8. Newsletter Signup             — form, inline link, popup trigger
  9. Ad / Affiliate Markers        — sponsored classes, rel=sponsored, affiliate networks
 10. Cache Headers & CDN           — CSS cache-control, CDN fingerprint

Each test returns a result dict:
  {
    'test_id':    str,
    'test_name':  str,
    'passed':     bool,          # all hard assertions passed
    'assertions': [              # individual claim → passed/failed
        {'label': str, 'passed': bool, 'value': any}
    ],
    'extracted':  dict           # raw values for downstream use
  }

Evidence key: 'editorial_signals'
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _a(label: str, passed: bool, value: Any = None) -> Dict:
    """Build a single assertion dict."""
    r = {'label': label, 'passed': bool(passed)}
    if value is not None:
        r['value'] = value
    return r


def _result(test_id: str, test_name: str,
            assertions: List[Dict], extracted: Dict) -> Dict:
    """Build a test result; overall passes iff ALL hard assertions pass."""
    hard = [a for a in assertions if not a['label'].startswith('~')]
    passed = all(a['passed'] for a in hard) if hard else False
    return {
        'test_id':    test_id,
        'test_name':  test_name,
        'passed':     passed,
        'assertions': assertions,
        'extracted':  extracted,
    }


class EditorialSignalsExtractor(BaseExtractor):
    name = 'editorial_signals'

    async def extract(self, ctx: ExtractionContext) -> Dict:
        page      = ctx.page
        url       = ctx.url
        net_resps = ctx.network_responses or []

        tests = []
        for fn in [
            self._test_json_ld,
            self._test_social_meta,
            self._test_rss,
            self._test_pagination,
            self._test_web_vitals,
            self._test_accessibility,
            self._test_internal_links,
            self._test_newsletter,
            self._test_ads_affiliates,
            self._test_cdn_cache,
        ]:
            try:
                tests.append(await fn(page, url, net_resps))
            except Exception as exc:
                logger.warning(f"editorial_signals test {fn.__name__} failed: {exc}")
                tests.append({
                    'test_id':    fn.__name__.replace('_test_', ''),
                    'test_name':  fn.__name__.replace('_test_', '').replace('_', ' ').title(),
                    'passed':     False,
                    'assertions': [_a('extractor did not crash', False, str(exc))],
                    'extracted':  {'error': str(exc)},
                })

        passed_count = sum(1 for t in tests if t['passed'])
        total        = len(tests)
        score        = round(passed_count / total * 100) if total else 0
        confidence   = 40 + min(50, passed_count * 5) if tests else 0

        return {
            'pattern':    f"Editorial audit: {passed_count}/{total} tests passed",
            'confidence': confidence,
            'score':      score,
            'passed':     passed_count,
            'total':      total,
            'tests':      tests,
        }

    # ── Test 1: JSON-LD ───────────────────────────────────────────────────────

    async def _test_json_ld(self, page, url, _net) -> Dict:
        data = await page.evaluate("""
            () => {
                const scripts = Array.from(
                    document.querySelectorAll('script[type="application/ld+json"]')
                );
                return scripts.map(s => {
                    try { return JSON.parse(s.textContent); }
                    catch(e) { return null; }
                }).filter(Boolean);
            }
        """)

        editorial_types = {'NewsArticle', 'Article', 'MagazineIssue', 'WebPage'}

        # Flatten any @graph arrays (LD objects can contain @graph: [...])
        flat_data = []
        for item in data:
            if isinstance(item, dict) and '@graph' in item:
                flat_data.extend(g for g in item['@graph'] if isinstance(g, dict))
            elif isinstance(item, dict):
                flat_data.append(item)
        data = flat_data
        found = bool(data)

        # Find the most-relevant LD object (article > sitelinks)
        def _priority(d):
            if not isinstance(d, dict):
                return 2
            t = d.get('@type', '')
            if isinstance(t, list): t = t[0] if t else ''
            return 0 if t in editorial_types else 1

        ld = sorted(data, key=_priority)[0] if data else {}
        ld_type  = ld.get('@type', '')
        if isinstance(ld_type, list): ld_type = ld_type[0] if ld_type else ''

        author_raw  = ld.get('author')
        if isinstance(author_raw, dict): author_raw = [author_raw]
        author_names = [a.get('name') for a in (author_raw or []) if isinstance(a, dict) and a.get('name')]
        keywords_raw = ld.get('keywords', '')
        keywords     = [k.strip() for k in keywords_raw.split(',')] if isinstance(keywords_raw, str) else (keywords_raw or [])

        assertions = [
            _a('JSON-LD present',                 found),
            _a('@type is editorial',               ld_type in editorial_types, ld_type or None),
            _a('Has datePublished',                bool(ld.get('datePublished')), ld.get('datePublished')),
            _a('Has author',                       bool(author_names), author_names or None),
            _a('Has headline',                     bool(ld.get('headline')), (ld.get('headline') or '')[:80] or None),
            _a('~Has image',                       bool(ld.get('image'))),
            _a('~Has articleSection / keywords',   bool(ld.get('articleSection') or keywords)),
        ]
        return _result('json_ld', 'JSON-LD Structured Data', assertions, {
            '@type':          ld_type,
            'datePublished':  ld.get('datePublished'),
            'author_names':   author_names,
            'headline':       (ld.get('headline') or '')[:120],
            'articleSection': ld.get('articleSection'),
            'keywords':       keywords[:10],
            'total_ld_blocks': len(data),
        })

    # ── Test 2: Open Graph & Twitter Cards ────────────────────────────────────

    async def _test_social_meta(self, page, _url, _net) -> Dict:
        meta = await page.evaluate("""
            () => {
                const get = sel => document.querySelector(sel)?.content || null;
                const getAll = sel => Array.from(document.querySelectorAll(sel))
                                      .map(e => e.content).filter(Boolean);
                return {
                    og_title:      get('meta[property="og:title"]'),
                    og_type:       get('meta[property="og:type"]'),
                    og_image:      get('meta[property="og:image"]'),
                    og_desc:       get('meta[property="og:description"]'),
                    og_published:  get('meta[property="article:published_time"]'),
                    og_modified:   get('meta[property="article:modified_time"]'),
                    og_tags:       getAll('meta[property="article:tag"]'),
                    og_author:     get('meta[property="article:author"]'),
                    twitter_card:  get('meta[name="twitter:card"]'),
                    twitter_site:  get('meta[name="twitter:site"]'),
                    twitter_image: get('meta[name="twitter:image"]'),
                };
            }
        """)

        valid_twitter = {'summary', 'summary_large_image', 'app', 'player'}
        assertions = [
            _a('og:type = article',              meta.get('og_type') == 'article', meta.get('og_type')),
            _a('article:published_time present', bool(meta.get('og_published')),   meta.get('og_published')),
            _a('≥1 article:tag',                 len(meta.get('og_tags', [])) >= 1, len(meta.get('og_tags', []))),
            _a('twitter:card is valid',          meta.get('twitter_card') in valid_twitter, meta.get('twitter_card')),
            _a('~og:image present',              bool(meta.get('og_image'))),
            _a('~og:description present',        bool(meta.get('og_desc'))),
        ]
        return _result('social_meta', 'Open Graph & Twitter Cards', assertions, meta)

    # ── Test 3: RSS Feed Discovery ────────────────────────────────────────────

    async def _test_rss(self, page, url, _net) -> Dict:
        result = await page.evaluate("""
            async (base) => {
                // 1. Check <head> link tags
                const headRss = document.querySelector(
                    'link[type="application/rss+xml"], link[rel="alternate"][type="application/rss+xml"]'
                );
                if (headRss) return { found: true, url: headRss.href, method: 'head_link' };

                // 2. Probe common paths
                const probes = ['/rss.xml', '/feed', '/feed.xml', '/rss', '/rss/feed.xml',
                                '/feeds/posts/default', '/index.xml'];
                for (const path of probes) {
                    try {
                        const r = await fetch(base + path, { method: 'HEAD', signal: AbortSignal.timeout(3000) });
                        const ct = r.headers.get('content-type') || '';
                        if (r.ok && (ct.includes('rss') || ct.includes('xml') || ct.includes('atom'))) {
                            return { found: true, url: base + path, method: 'probe' };
                        }
                    } catch(e) {}
                }
                return { found: false, url: null, method: null };
            }
        """, urlparse(url)._replace(path='', query='', fragment='').geturl())

        assertions = [
            _a('RSS feed discoverable', result.get('found', False), result.get('url')),
        ]
        return _result('rss', 'RSS Feed Discovery', assertions, result)

    # ── Test 4: Pagination / Infinite Scroll ─────────────────────────────────

    async def _test_pagination(self, page, _url, _net) -> Dict:
        result = await page.evaluate("""
            () => {
                const nextLink   = document.querySelector('a[rel="next"]')?.href || null;
                const loadMore   = !!document.querySelector(
                    '.load-more, .load-more-button, .infinite-scroll-trigger, ' +
                    '[data-infinite-scroll], [data-load-more], button[class*="load-more"]'
                );
                const prevLink   = document.querySelector('a[rel="prev"]')?.href || null;
                const pageParam  = (window.location.search.match(/[?&]page=(\d+)/) || [])[1] || null;
                const paginationEl = document.querySelector(
                    '.pagination, nav[aria-label*="pagination" i], [class*="paginator"]'
                );
                const pageNums = paginationEl
                    ? Array.from(paginationEl.querySelectorAll('a'))
                           .map(a => parseInt(a.textContent.trim()))
                           .filter(n => !isNaN(n) && n > 0)
                    : [];
                const maxPage = pageNums.length ? Math.max(...pageNums) : null;

                let paginationType = null;
                if (loadMore)        paginationType = 'load_more_button';
                else if (nextLink)   paginationType = 'next_link';
                else if (pageParam)  paginationType = 'url_param';
                else if (paginationEl) paginationType = 'numbered';

                return { nextLink, prevLink, loadMore, pageParam, paginationType, maxPage };
            }
        """)

        found = bool(result.get('nextLink') or result.get('loadMore') or
                     result.get('pageParam') or result.get('paginationType'))
        assertions = [
            _a('Pagination pattern exists', found, result.get('paginationType')),
        ]
        return _result('pagination', 'Pagination / Infinite Scroll', assertions, result)

    # ── Test 5: Web Vitals ────────────────────────────────────────────────────

    async def _test_web_vitals(self, page, _url, _net) -> Dict:
        vitals = await page.evaluate("""
            () => {
                const nav = performance.getEntriesByType('navigation')[0] || {};
                const paintEntries = performance.getEntriesByType('paint');
                const fcpEntry = paintEntries.find(e => e.name === 'first-contentful-paint');

                // LCP — prefer pre-navigation observer globals, fall back to API
                let lcp = null;
                if (window.__lcpEntries && window.__lcpEntries.length) {
                    lcp = Math.round(window.__lcpEntries[window.__lcpEntries.length - 1]);
                } else {
                    const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                    if (lcpEntries.length)
                        lcp = Math.round(lcpEntries[lcpEntries.length - 1].startTime);
                }

                // CLS — prefer pre-navigation observer global
                let cls = null;
                if (window.__clsValue !== undefined && window.__clsValue !== null) {
                    cls = parseFloat(window.__clsValue.toFixed(4));
                } else {
                    const clsEntries = performance.getEntriesByType('layout-shift');
                    if (clsEntries.length)
                        cls = parseFloat(clsEntries
                            .filter(e => !e.hadRecentInput)
                            .reduce((s, e) => s + e.value, 0)
                            .toFixed(4));
                }

                return {
                    ttfb:   nav.responseStart ? Math.round(nav.responseStart) : null,
                    fcp:    fcpEntry ? Math.round(fcpEntry.startTime) : null,
                    lcp:    lcp,
                    cls:    cls,
                    dom_interactive: nav.domInteractive ? Math.round(nav.domInteractive) : null,
                    dom_complete:    nav.domComplete    ? Math.round(nav.domComplete)    : null,
                };
            }
        """)

        fcp = vitals.get('fcp')
        lcp = vitals.get('lcp')
        cls = vitals.get('cls')

        assertions = [
            _a('FCP < 1800ms',  fcp is not None and fcp < 1800, f"{fcp}ms" if fcp else None),
            # LCP/CLS: if null, patchright isolated-world limitation (not a site failure)
            _a('~LCP < 2500ms', lcp is None or lcp < 2500,  f"{lcp}ms" if lcp is not None else 'not measured'),
            _a('~CLS < 0.1',    cls is None or cls < 0.1,   cls if cls is not None else 'not measured'),
        ]
        return _result('web_vitals', 'Web Vitals', assertions, vitals)

    # ── Test 6: Accessibility ─────────────────────────────────────────────────

    async def _test_accessibility(self, page, _url, _net) -> Dict:
        result = await page.evaluate("""
            () => {
                // H1 presence
                const h1s = document.querySelectorAll('h1');

                // Image alt coverage
                const imgs = Array.from(document.querySelectorAll('img'));
                const decorativeOk = i => i.getAttribute('alt') === '' && i.getAttribute('role') === 'presentation';
                const missingAlt   = imgs.filter(i => !i.hasAttribute('alt') && !decorativeOk(i));

                // Heading hierarchy — find skipped levels
                const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
                    .map(h => parseInt(h.tagName[1]));
                let skips = [];
                for (let i = 1; i < headings.length; i++) {
                    if (headings[i] - headings[i-1] > 1) {
                        skips.push(`h${headings[i-1]}→h${headings[i]}`);
                    }
                }

                // Skip links
                const skipLink = document.querySelector('a[href="#main"], a[href="#content"], a.skip-link, a.skip-to-main');

                // ARIA landmarks
                const landmarks = {
                    main:    !!document.querySelector('main, [role="main"]'),
                    nav:     !!document.querySelector('nav, [role="navigation"]'),
                    banner:  !!document.querySelector('header, [role="banner"]'),
                    footer:  !!document.querySelector('footer, [role="contentinfo"]'),
                };

                return {
                    h1_count:       h1s.length,
                    h1_text:        h1s[0]?.textContent?.trim()?.slice(0, 120) || null,
                    total_images:   imgs.length,
                    missing_alt:    missingAlt.length,
                    alt_coverage:   imgs.length
                        ? Math.round((imgs.length - missingAlt.length) / imgs.length * 100)
                        : 100,
                    heading_levels: headings,
                    heading_skips:  skips,
                    has_skip_link:  !!skipLink,
                    landmarks:      landmarks,
                };
            }
        """)

        assertions = [
            _a('Page has exactly one H1',           result.get('h1_count') == 1,     result.get('h1_count')),
            _a('Image alt coverage ≥ 80%',          result.get('alt_coverage', 0) >= 80, f"{result.get('alt_coverage')}%"),
            _a('No heading level skips',            len(result.get('heading_skips', [])) == 0,
                                                    result.get('heading_skips') or None),
            _a('~Has ARIA main landmark',           (result.get('landmarks') or {}).get('main', False)),
            _a('~Has skip link',                    result.get('has_skip_link', False)),
        ]
        return _result('accessibility', 'Accessibility', assertions, result)

    # ── Test 7: Internal Linking Patterns ────────────────────────────────────

    async def _test_internal_links(self, page, url, _net) -> Dict:
        base_host = urlparse(url).netloc

        result = await page.evaluate("""
            (baseHost) => {
                // Related articles section
                const relatedSelectors = [
                    '.related-articles', '.related', '.recommended', '.more-stories',
                    '[data-related]', '[class*="related"]', '[class*="recommended"]',
                    '[aria-label*="related" i]', '[aria-label*="more stories" i]',
                ];
                let relatedSection = null;
                for (const sel of relatedSelectors) {
                    relatedSection = document.querySelector(sel);
                    if (relatedSection) break;
                }
                // Collect links: href anchors, data-href anchors (lazy-hydrated React/SSR), or
                // anchors with article-like paths in onclick/data attributes
                const relatedLinks = relatedSection
                    ? Array.from(relatedSection.querySelectorAll('a'))
                           .filter(a => {
                               const href = a.href || a.dataset.href || a.getAttribute('data-url') || '';
                               if (!href || href === window.location.href) return false;
                               try {
                                   const h = new URL(href);
                                   return h.hostname === baseHost || h.pathname.length > 1;
                               } catch(e) {
                                   // relative path or fragment
                                   return href.length > 1 && !href.startsWith('javascript');
                               }
                           })
                    : [];

                // Author link
                const authorSelectors = [
                    'a[rel="author"]', '.byline a', '.author-name a', '.author a',
                    '[class*="author"] a', '[itemprop="author"] a',
                    'a[href*="/author/"]', 'a[href*="/contributor/"]',
                    'a[href*="/writers/"]', 'a[href*="/staff/"]',
                ];
                let authorLink = null;
                for (const sel of authorSelectors) {
                    authorLink = document.querySelector(sel);
                    if (authorLink) break;
                }
                const authorHref = authorLink?.href || null;
                const authorPatterns = ['/author/', '/contributor/', '/writers/', '/staff/', '/people/'];
                const authorArchive = authorHref
                    ? authorPatterns.some(p => authorHref.includes(p))
                    : false;

                return {
                    related_section_found: !!relatedSection,
                    related_link_count:    relatedLinks.length,
                    related_selector:      relatedSection?.className?.slice(0, 80) || null,
                    related_link_sample:   relatedLinks.slice(0, 3).map(a => a.href || a.dataset.href || ''),
                    author_link_href:      authorHref,
                    author_archive_pattern: authorArchive,
                };
            }
        """, base_host)

        assertions = [
            _a('Related articles section exists', result.get('related_section_found'), result.get('related_selector')),
            # link count is 0 when section is React-hydrated placeholder (headless limitation)
            _a('~≥3 related article links',       result.get('related_link_count', 0) >= 3, result.get('related_link_count')),
            _a('Author link present',             bool(result.get('author_link_href'))),
            _a('Author link → archive URL',       result.get('author_archive_pattern', False), result.get('author_link_href')),
        ]
        return _result('internal_links', 'Internal Linking Patterns', assertions, result)

    # ── Test 8: Newsletter Signup ─────────────────────────────────────────────

    async def _test_newsletter(self, page, _url, _net) -> Dict:
        result = await page.evaluate("""
            () => {
                const formSelectors = [
                    'form[action*="newsletter"]', 'form[action*="mailchimp"]',
                    'form[action*="klaviyo"]',    'form[action*="subscribe"]',
                    '.newsletter-signup',          '.newsletter-form',
                    '[class*="newsletter"]',       '[id*="newsletter"]',
                    '[data-popup="newsletter"]',
                ];
                let form = null, placement = null;
                for (const sel of formSelectors) {
                    form = document.querySelector(sel);
                    if (form) { placement = sel; break; }
                }

                // Where on page?
                let location = 'unknown';
                if (form) {
                    const rect  = form.getBoundingClientRect();
                    const vh    = window.innerHeight;
                    const inHeader = !!form.closest('header, nav');
                    const inFooter = !!form.closest('footer');
                    if (inHeader)          location = 'header';
                    else if (inFooter)     location = 'footer';
                    else if (rect.top < vh) location = 'inline_above_fold';
                    else                   location = 'inline_below_fold';
                }

                // Newsletter link (popups)
                const linkSels = [
                    'a[href*="newsletter"]', 'a[href*="subscribe"]',
                    'button[data-popup*="newsletter"]',
                ];
                let nLink = null;
                for (const sel of linkSels) {
                    nLink = document.querySelector(sel);
                    if (nLink) break;
                }

                // Field count inside form
                const fields = form
                    ? form.querySelectorAll('input:not([type="hidden"]):not([type="submit"])').length
                    : 0;

                return {
                    form_found:    !!form,
                    link_found:    !!nLink,
                    placement:     form ? location : (nLink ? 'link' : null),
                    field_count:   fields,
                    form_selector: placement,
                };
            }
        """)

        found = result.get('form_found') or result.get('link_found')
        assertions = [
            _a('Newsletter signup present', found, result.get('placement')),
        ]
        return _result('newsletter', 'Newsletter Signup', assertions, result)

    # ── Test 9: Ad / Affiliate Markers ───────────────────────────────────────

    async def _test_ads_affiliates(self, page, _url, _net) -> Dict:
        result = await page.evaluate("""
            () => {
                // Sponsored content markers
                const sponsoredEl = document.querySelector(
                    '[class*="sponsored"], [class*="advertisement"], [class*="advertorial"], ' +
                    '[data-sponsored], [data-ad-unit], [id*="sponsor"]'
                );

                // Affiliate link patterns
                const affiliatePatterns = [
                    'skimlinks', 'rewardstyle', 'rstyle.me', 'shareasale',
                    'linksynergy', 'awin.com', 'pepperjam', 'cj.com',
                    'amazon.com/tag', 'amzn.to', 'ltk.co', 'shopstyle',
                ];
                const allLinks = Array.from(document.querySelectorAll('a[href]'));
                const affiliateLinks = allLinks.filter(a => {
                    const href = a.href.toLowerCase();
                    return affiliatePatterns.some(p => href.includes(p));
                });
                const relSponsored = document.querySelectorAll('a[rel*="sponsored"]');

                // Ad slots
                const adSlots = document.querySelectorAll(
                    '[class*="ad-slot"], [class*="ad-unit"], [id*="ad-slot"], ' +
                    'ins.adsbygoogle, [data-ad-slot], iframe[id*="google_ads"]'
                );

                return {
                    sponsored_marker:     sponsoredEl?.className?.slice(0, 80) || null,
                    affiliate_link_count: affiliateLinks.length,
                    affiliate_networks: (() => {
                        const nets = new Set();
                        const netNames = ['skimlinks','rewardstyle','rstyle.me','shareasale',
                                          'linksynergy','awin.com','pepperjam','cj.com',
                                          'amazon.com/tag','amzn.to','ltk.co','shopstyle'];
                        affiliateLinks.forEach(a => {
                            const href = a.href.toLowerCase();
                            for (const p of netNames) {
                                if (href.includes(p)) { nets.add(p); break; }
                            }
                        });
                        return [...nets];
                    })(),
                    rel_sponsored_count:  relSponsored.length,
                    ad_slot_count:        adSlots.length,
                };
            }
        """)

        # Test 9 is purely informational — never fails
        assertions = [
            _a('~Sponsored content marker',    bool(result.get('sponsored_marker'))),
            _a('~Affiliate links present',     result.get('affiliate_link_count', 0) > 0,
                                               result.get('affiliate_link_count')),
            _a('~Ad slots present',            result.get('ad_slot_count', 0) > 0,
                                               result.get('ad_slot_count')),
        ]
        # Override passed — informational test always reports True
        r = _result('ads_affiliates', 'Ad / Affiliate Markers', assertions, result)
        r['passed'] = True
        r['note']   = 'Informational — presence of ads/affiliates does not fail the audit'
        return r

    # ── Test 10: Cache Headers & CDN ─────────────────────────────────────────

    async def _test_cdn_cache(self, page, url, net_resps) -> Dict:
        # Try from captured network responses first
        css_resp = next(
            (r for r in net_resps if r.get('url', '').endswith('.css') and r.get('headers')), None
        )

        if css_resp:
            headers       = {k.lower(): v for k, v in (css_resp.get('headers') or {}).items()}
            cache_control = headers.get('cache-control', '')
            cdnInfo       = _detect_cdn(headers)
            source        = 'network_capture'
        else:
            # Probe via fetch() inside the page
            probe = await page.evaluate("""
                async () => {
                    const cssLink = document.querySelector('link[rel="stylesheet"]')?.href;
                    if (!cssLink) return null;
                    try {
                        const r = await fetch(cssLink, { method: 'HEAD', signal: AbortSignal.timeout(5000) });
                        const h = {};
                        r.headers.forEach((v, k) => { h[k.toLowerCase()] = v; });
                        return { url: cssLink, headers: h };
                    } catch(e) { return { error: e.message }; }
                }
            """)
            if probe and probe.get('headers'):
                headers       = probe['headers']
                cache_control = headers.get('cache-control', '')
                cdnInfo       = _detect_cdn(headers)
                source        = 'fetch_probe'
            else:
                headers = {}; cache_control = ''; cdnInfo = {}; source = 'unavailable'

        has_max_age  = bool(re.search(r'max-age=\d+', cache_control))
        cdn_detected = bool(cdnInfo.get('provider'))

        # Asset versioning — check CSS URLs for hash/query params
        versioning = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
                return links.map(l => l.href).filter(h => /\?v=|\?hash=|\.[\da-f]{8,}\.|ver=/.test(h));
            }
        """)

        assertions = [
            _a('CSS has cache max-age',   has_max_age,   cache_control or None),
            _a('CDN cache header present', cdn_detected, cdnInfo.get('provider')),
        ]
        return _result('cdn_cache', 'Cache Headers & CDN', assertions, {
            'cache_control':     cache_control,
            'cdn_provider':      cdnInfo.get('provider'),
            'cdn_evidence':      cdnInfo.get('evidence'),
            'versioned_assets':  len(versioning),
            'source':            source,
        })


def _detect_cdn(headers: Dict) -> Dict:
    """Identify CDN from response headers."""
    signatures = [
        ('cf-cache-status',    'Cloudflare'),
        ('x-fastly-request-id', 'Fastly'),
        ('x-amz-cf-id',         'CloudFront'),
        ('x-azure-ref',         'Azure CDN'),
        ('x-goog-resource-type', 'Google Cloud CDN'),
        ('x-akamai-request-id', 'Akamai'),
        ('x-served-by',         'Fastly'),       # Fastly also uses this
        ('server',              None),            # checked below
    ]
    for header_key, provider in signatures:
        val = headers.get(header_key, '')
        if val and provider:
            return {'provider': provider, 'evidence': f'{header_key}: {val[:60]}'}
    # Server header fallbacks
    server = headers.get('server', '').lower()
    if 'cloudflare' in server:
        return {'provider': 'Cloudflare', 'evidence': f'server: {server}'}
    if 'nginx' in server or 'apache' in server:
        return {'provider': None, 'evidence': f'server: {server}'}
    return {}
