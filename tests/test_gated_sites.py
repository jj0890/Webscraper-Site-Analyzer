#!/usr/bin/env python3
"""
Test Suite: Modal Gates, Infinite Scroll, and API Discovery
============================================================
Addresses three challenges identified in the pi.fyi / social-feed analysis:

  1. Email gates / overlay modals (client-side, not server-side restrictions)
  2. Infinite scroll / virtualized lists (IntersectionObserver-driven)
  3. Inconsistent DOM structures across content types (Q&A, events, editorial)

Strategy hierarchy (clean → hacky, as recommended):
  A. Network-first — intercept XHR/fetch calls, replay the API directly
  B. DOM mutation  — remove modal elements, reset body overflow
  C. Script abort  — block specific scripts before they render
  D. CV / visual   — last resort, skip entirely here

Usage:
    cd ~/Desktop/Webscraper
    python3 tests/test_gated_sites.py
    python3 tests/test_gated_sites.py --site pi.fyi
    python3 tests/test_gated_sites.py --suite api_discovery
"""

import asyncio
import requests
import json
import time
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

SERVER = 'http://localhost:8080'

# ──────────────────────────────────────────────────────────────────────────────
# SITE CONFIG — gated / infinite-scroll / inconsistent sites
# ──────────────────────────────────────────────────────────────────────────────

GATED_SITE_CONFIGS = {

    # ── PI.FYI ────────────────────────────────────────────────────────────────
    # Social recommendation feed. Email-gate modal on landing, infinite scroll,
    # heterogeneous post types (rec, ask, event, editorial). No public API.
    "pi.fyi": {
        "url": "https://pi.fyi",
        # Modal dismissal: remove by DOM mutation, then unblock body scroll
        "modal_selectors": [
            "[role='dialog']",
            "form[method='post'][action*='join']",
            "[class*='modal']",
            "[class*='overlay']",
            "[class*='gate']",
            "[class*='paywall']",
            "[class*='signup']",
        ],
        "unblock_scroll": True,
        # Feed container + per-post type classifiers
        "feed_container": "[class*='feed'], [class*='timeline'], main",
        "post_selectors": {
            "rec":       "[class*='rec'], [data-type='rec']",
            "ask":       "[class*='ask'], [data-type='ask']",
            "event":     "[class*='event'], [data-type='event']",
            "editorial": "article, [class*='editorial']",
        },
        # Infinite scroll: scroll N times and capture new items
        "infinite_scroll": {
            "enabled": True,
            "scroll_steps": 3,
            "wait_ms": 1500,
        },
        # Known API patterns discovered via network tab
        "api_hints": [
            "/api/",
            "/graphql",
            "/_next/data/",
            "/feed",
        ],
        "design_goal": "Understand card UI, Q&A layout, amber/brown accent, infinite feed UX",
    },

    # ── SOUNDCLOUD ────────────────────────────────────────────────────────────
    # Public API exists (api.soundcloud.com + api-v2.soundcloud.com).
    # Feed is JS-rendered, requires client_id token (embeds in page JS).
    "soundcloud.com": {
        "url": "https://soundcloud.com",
        "modal_selectors": [
            "[class*='CookieBanner']",
            "[id*='cookie']",
            "[class*='consent']",
        ],
        "unblock_scroll": False,
        "api_hints": [
            "api-v2.soundcloud.com",
            "api.soundcloud.com",
        ],
        "pagination": {
            "type": "cursor",
            "param": "linked_partitioning",
            "limit_param": "limit",
            "default_limit": 20,
        },
        "design_goal": "Track card layout, waveform component, player bar positioning",
    },

    # ── NTS.LIVE ──────────────────────────────────────────────────────────────
    # Open undocumented JSON API (nts.live/api/v2/). Infinite scroll on /shows.
    # Already well-scanned; this config tests pagination specifically.
    "nts.live": {
        "url": "https://www.nts.live",
        "modal_selectors": [],
        "api_hints": [
            "nts.live/api/v2/live",
            "nts.live/api/v2/shows",
            "nts.live/api/v2/episodes",
        ],
        "pagination": {
            "type": "offset",
            "offset_param": "offset",
            "limit_param": "limit",
            "default_limit": 50,
        },
        "design_goal": "Condensed typography density, schedule grid, live indicator UX",
    },

    # ── PI.FYI EVENTS SUBPAGE ─────────────────────────────────────────────────
    # Specific subpage — events section. More consistent schema than main feed.
    "pi.fyi/events": {
        "url": "https://pi.fyi/events",
        "modal_selectors": [
            "[role='dialog']",
            "[class*='signup']",
        ],
        "unblock_scroll": True,
        "feed_container": "[class*='events'], [class*='list'], main",
        "post_selectors": {
            "event": "[class*='event-card'], article, li",
        },
        "infinite_scroll": {
            "enabled": True,
            "scroll_steps": 2,
            "wait_ms": 2000,
        },
        "design_goal": "Event card layout, date formatting, location display",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# NORMALIZED OUTPUT SCHEMA
# ──────────────────────────────────────────────────────────────────────────────

NORMALIZED_SCHEMA = {
    "id":        "string — unique (source:internal_id or url hash)",
    "type":      "string — rec | ask | event | track | article | playlist",
    "title":     "string | null",
    "url":       "string — canonical link",
    "timestamp": "ISO8601 | null",
    "author":    "string | null",
    "source":    "string — domain of origin",
    "content":   "string — text body or excerpt",
    "media": {
        "image":  "url | null",
        "audio":  "url | null",
        "video":  "url | null",
        "embed":  "iframe src | null",
    },
    "meta": {
        "tags":     "string[]",
        "genres":   "string[]",
        "location": "string | null",
        "platform": "string | null — soundcloud | spotify | mixcloud etc",
        "reply_to": "id | null — for Q&A asks",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# CONTENT CLASSIFIER HEURISTICS
# ──────────────────────────────────────────────────────────────────────────────

CONTENT_CLASSIFIERS = {
    "track": [
        "contains audio element or iframe",
        "soundcloud.com, spotify.com, mixcloud.com in src",
        "waveform img present",
    ],
    "event": [
        "contains date + location strings",
        "contains venue, ticket, RSVP text",
        "datetime attribute on a time element",
    ],
    "editorial": [
        "long-form text > 200 words",
        "byline present",
        "no audio/video embed",
    ],
    "ask": [
        "contains '?' in title",
        "parent element has ask/question class",
        "reply thread structure",
    ],
    "rec": [
        "short text < 200 words",
        "external link present",
        "no question mark in heading",
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# INFINITE SCROLL DETECTION HEURISTICS
# ──────────────────────────────────────────────────────────────────────────────

SCROLL_DETECTION_HINTS = {
    "intersection_observer": {
        "js_check": "typeof window.IntersectionObserver !== 'undefined'",
        "implication": "lazy-load on scroll — simulate scrolling to trigger",
    },
    "virtualized_list": {
        "symptoms": [
            "item count stays constant on scroll (old nodes removed)",
            "container has overflow:hidden + fixed height",
            "CSS transforms on list items",
        ],
        "libraries": ["react-window", "react-virtualized", "tanstack-virtual"],
        "implication": "DOM is NOT a full dataset — must use network API layer",
    },
    "simple_pagination": {
        "symptoms": [
            "explicit 'Load more' button",
            "page= or offset= in URL",
            "next href in <a> tag",
        ],
        "implication": "click button or increment offset param",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# TEST FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def test_modal_bypass(site_key: str) -> dict:
    """
    Test whether the deep-scan can get past a modal gate.

    Strategy:
      1. Run deep-scan (Patchright stealth browser — should auto-dismiss some)
      2. Check attention_flow for modal-trapped content (e.g. sign-up form weight > feed weight)
      3. Report whether useful content was extracted or if modal blocked
    """
    config = GATED_SITE_CONFIGS.get(site_key)
    if not config:
        print(f"  ❌ No config for {site_key}")
        return {"success": False}

    print(f"\n{'─'*60}")
    print(f"  MODAL BYPASS TEST: {config['url']}")
    print(f"{'─'*60}")
    print(f"  Scanning with smart-nav mode (Patchright stealth)...")
    start = time.time()

    try:
        resp = requests.post(
            f"{SERVER}/api/deep-scan",
            json={"site_url": config["url"], "analysis_mode": "smart-nav"},
            timeout=180,
        )
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return {"success": False}

        data = resp.json()
        ev = data.get("evidence", {})
        pages = ev.get("page_results", {})
        home = pages.get("home", {})

        # Analyse attention flow — is modal or feed on top?
        vh = home.get("visual_hierarchy", {}) if isinstance(home, dict) else {}
        flow = vh.get("attention_flow", [])

        print(f"\n  ⏱  {elapsed:.1f}s")
        print(f"  Attention flow (top 5):")
        modal_indicators = ["modal", "dialog", "signup", "email", "join", "overlay"]
        modal_detected = False
        feed_detected = False

        for item in flow[:5]:
            text_lower = str(item).lower()
            is_modal = any(kw in text_lower for kw in modal_indicators)
            is_feed  = any(kw in text_lower for kw in ["rec", "ask", "post", "feed", "article"])

            marker = "🚨 MODAL" if is_modal else ("✅ FEED" if is_feed else "   ")
            print(f"    {marker} {item}")

            if is_modal: modal_detected = True
            if is_feed:  feed_detected  = True

        # Typography — did we get actual site fonts or default browser fonts?
        typo = home.get("typography", {}) if isinstance(home, dict) else {}
        fonts = typo.get("details", {}).get("all_fonts", [])
        print(f"\n  Fonts extracted: {fonts[:3]}")

        modal_blocked = modal_detected and not feed_detected
        print(f"\n  Result: {'❌ MODAL BLOCKED extraction' if modal_blocked else '✅ Extracted past modal'}")
        print(f"  Design goal: {config.get('design_goal', '')}")

        return {
            "success": not modal_blocked,
            "modal_detected": modal_detected,
            "feed_detected": feed_detected,
            "fonts": fonts,
            "elapsed": elapsed,
            "flow": flow[:5],
        }

    except requests.exceptions.Timeout:
        print(f"  ❌ Timeout after {time.time()-start:.0f}s")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {"success": False, "error": str(e)}


def test_api_discovery(site_key: str) -> dict:
    """
    Test the network-interception approach for API discovery.

    Looks for XHR/fetch calls during page load using the scraper's
    network capture capability. Reports discovered endpoints.
    """
    config = GATED_SITE_CONFIGS.get(site_key)
    if not config:
        return {"success": False}

    print(f"\n{'─'*60}")
    print(f"  API DISCOVERY TEST: {config['url']}")
    print(f"{'─'*60}")

    api_hints = config.get("api_hints", [])
    pagination = config.get("pagination", {})

    print(f"  Known API hints: {api_hints}")
    print(f"  Pagination type: {pagination.get('type', 'unknown')}")

    # Use discover-urls to map the site topology
    try:
        resp = requests.post(
            f"{SERVER}/api/discover-urls",
            json={"site_url": config["url"], "max_urls": 20},
            timeout=60,
        )

        if resp.status_code == 200:
            data = resp.json()
            urls = data.get("urls", data.get("discovered_urls", []))
            print(f"\n  Discovered {len(urls)} URLs")

            # Flag any that look like API endpoints
            api_urls = [u for u in urls if any(h in str(u) for h in api_hints + ["/api/", "/graphql", "/_data", ".json"])]
            feed_urls = [u for u in urls if any(kw in str(u).lower() for kw in ["feed", "explore", "discover", "stream"])]

            print(f"  Potential API endpoints: {len(api_urls)}")
            for u in api_urls[:5]: print(f"    → {u}")

            print(f"  Feed-type URLs: {len(feed_urls)}")
            for u in feed_urls[:3]: print(f"    → {u}")

            return {"success": True, "api_urls": api_urls, "feed_urls": feed_urls}
        else:
            print(f"  ❌ discover-urls: HTTP {resp.status_code}")
            return {"success": False}

    except Exception as e:
        print(f"  ❌ {e}")
        return {"success": False, "error": str(e)}


def test_design_extraction(site_key: str) -> dict:
    """
    Full design extraction test — validate that we can extract
    typography, color system, and layout from a gated/complex site.

    Reports extraction confidence and gaps.
    """
    config = GATED_SITE_CONFIGS.get(site_key)
    if not config:
        return {"success": False}

    print(f"\n{'─'*60}")
    print(f"  DESIGN EXTRACTION TEST: {config['url']}")
    print(f"{'─'*60}")

    try:
        resp = requests.post(
            f"{SERVER}/api/deep-scan",
            json={"site_url": config["url"], "analysis_mode": "single"},
            timeout=120,
        )

        if resp.status_code != 200:
            return {"success": False}

        data = resp.json()
        ev = data.get("evidence", {})
        pages = ev.get("page_results", {})
        home = pages.get("home", {})

        if not isinstance(home, dict):
            print("  ❌ No home page data")
            return {"success": False}

        results = {}

        # ── Typography
        typo = home.get("typography", {})
        fonts = typo.get("details", {}).get("all_fonts", [])
        typo_conf = typo.get("confidence", 0)
        print(f"\n  Typography ({typo_conf}% confidence)")
        print(f"    Fonts: {fonts[:4]}")
        print(f"    CSS: {typo.get('code_snippets','')[:150]}")
        results["typography"] = {"fonts": fonts, "confidence": typo_conf}

        # ── Colors
        colors = home.get("colors", {})
        color_conf = colors.get("confidence", 0)
        print(f"\n  Colors ({color_conf}% confidence)")
        print(f"    CSS: {colors.get('code_snippets','')[:200]}")
        results["colors"] = {"confidence": color_conf}

        # ── Layout
        layout = home.get("layout", {})
        layout_conf = layout.get("confidence", 0)
        layout_det = layout.get("details", {})
        print(f"\n  Layout ({layout_conf}% confidence)")
        print(f"    Flex: {layout_det.get('flex_count',0)}, Grid: {layout_det.get('grid_count',0)}")
        results["layout"] = {"confidence": layout_conf}

        # ── Overall
        gaps = [k for k, v in results.items() if v.get("confidence", 0) < 50]
        print(f"\n  Gaps (< 50% confidence): {gaps if gaps else 'none'}")
        print(f"  Design goal: {config.get('design_goal','')}")

        return {"success": True, "results": results, "gaps": gaps}

    except Exception as e:
        print(f"  ❌ {e}")
        return {"success": False, "error": str(e)}


def print_content_classifier_reference():
    """Print the content classifier heuristics as a reference."""
    print("\n" + "═"*60)
    print("  CONTENT CLASSIFIER HEURISTICS (reference)")
    print("═"*60)
    for content_type, rules in CONTENT_CLASSIFIERS.items():
        print(f"\n  {content_type.upper()}")
        for rule in rules:
            print(f"    • {rule}")

    print("\n" + "═"*60)
    print("  INFINITE SCROLL DETECTION PATTERNS (reference)")
    print("═"*60)
    for pattern, info in SCROLL_DETECTION_HINTS.items():
        print(f"\n  {pattern.upper()}")
        if "symptoms" in info:
            for s in info["symptoms"]:
                print(f"    • {s}")
        print(f"    → {info['implication']}")

    print("\n" + "═"*60)
    print("  NORMALIZED OUTPUT SCHEMA")
    print("═"*60)
    print(json.dumps(NORMALIZED_SCHEMA, indent=2))


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test gated/scroll/inconsistent sites")
    parser.add_argument("--site",  default="pi.fyi", choices=list(GATED_SITE_CONFIGS.keys()),
                        help="Which site to test")
    parser.add_argument("--suite", default="all",
                        choices=["all", "modal", "api_discovery", "design", "reference"],
                        help="Which test suite to run")
    args = parser.parse_args()

    print("\n" + "═"*60)
    print(f"  GATED SITE TEST SUITE")
    print(f"  Site: {args.site}  |  Suite: {args.suite}")
    print("═"*60)

    if args.suite == "reference":
        print_content_classifier_reference()
        return

    results = {}

    if args.suite in ("all", "modal"):
        results["modal"] = test_modal_bypass(args.site)

    if args.suite in ("all", "api_discovery"):
        results["api_discovery"] = test_api_discovery(args.site)

    if args.suite in ("all", "design"):
        results["design"] = test_design_extraction(args.site)

    # ── Summary
    print("\n" + "═"*60)
    print("  SUMMARY")
    print("═"*60)
    for test_name, result in results.items():
        status = "✅ PASS" if result.get("success") else "❌ FAIL"
        print(f"  {status}  {test_name}")
        if result.get("error"):
            print(f"         Error: {result['error'][:80]}")

    print("\n  Config keys available:", list(GATED_SITE_CONFIGS.keys()))


if __name__ == "__main__":
    main()
