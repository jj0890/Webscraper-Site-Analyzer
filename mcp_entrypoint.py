"""
MCP Entrypoint - Web Intelligence Scanner as an MCP Server

Exposes DeepEvidenceEngine, ComponentRipper, and DesignDebtAnalyzer
as callable MCP tools for Claude Desktop, Cursor, or any LLM agent.

Install:
    pip install mcp

Run (stdio transport for Claude Desktop):
    python mcp_entrypoint.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "web-intelligence": {
          "command": "python",
          "args": ["/path/to/Webscraper/mcp_entrypoint.py"],
          "env": { "PYTHONPATH": "/path/to/Webscraper" }
        }
      }
    }
"""

import asyncio
import json
import sys
import os

# Add project root to path so imports work when called externally
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

from deep_evidence_engine import DeepEvidenceEngine
from component_ripper import ComponentRipper
from design_debt_analyzer import DesignDebtAnalyzer

mcp = FastMCP(
    "Web Intelligence Scanner",
    instructions=(
        "Analyzes websites for design systems, component architecture, and "
        "layout patterns. Returns structured evidence with confidence scores.\n\n"
        "WORKFLOW:\n"
        "1. Pick the right URL first. Homepages are often feeds or sparse landing "
        "pages — low design signal. For marketplaces, galleries, and community "
        "sites, scan a content listing page (/explore, /releases, /products) or "
        "a detail page rather than the root URL.\n"
        "2. Call analyze_design_system. Check evidence['entry_point']['recommendation'] "
        "immediately — if it flags the page as a feed or sparse, re-scan the "
        "suggested better_entry_points before reading other metrics.\n"
        "3. Call rip_component for specific component blueprints.\n"
        "4. Call audit_design_debt to find inconsistencies.\n\n"
        "Confidence scores below 60% should not be used as ground truth."
    ),
)


@mcp.tool()
async def analyze_design_system(
    url: str,
    mode: str = "single",
) -> dict:
    """
    Perform a full design-intelligence scan of a website.

    Extracts: typography scale, color palette with roles, spacing system,
    layout patterns, component zones, motion tokens, accessibility tree,
    interaction states, API patterns, and site architecture.

    Each metric includes a confidence score (0-100) and evidence trail.

    ENTRY POINT GUIDANCE — scan the most design-rich page, not necessarily
    the homepage. Homepages are often sparse landing pages or live feeds with
    low design signal. Better choices:
      - /explore, /browse, /catalog, /products  (content grids)
      - /releases, /works, /gallery              (item listing pages)
      - A specific article, product, or profile  (template-level detail)
    The evidence includes evidence['entry_point']['recommendation'] with a
    machine-readable advisory if the scanned URL appears to be a feed or
    sparse landing page — check this first and re-scan a better URL if needed.

    Args:
        url:  Public website URL to analyze (https://...). For marketplace,
              gallery, or community sites, prefer a content listing page
              over the homepage.
        mode: 'single' for one page (default), 'smart-nav' to auto-discover
              and analyze 3 representative pages (homepage + nav + deep link),
              'multi-template' to discover all distinct page template types
              (e.g. homepage + /releases/:slug + /profiles/:slug + /explore)
              and extract the cross-page design system — what's consistent
              across every template IS the design system; what varies is
              template-specific. Best for comprehensive site understanding.

    Returns:
        evidence dict with keys: typography, colors, spacing_scale, layout,
        visual_hierarchy, spatial_composition, motion_tokens, accessibility,
        interactions, api_patterns, site_architecture, entry_point, llm_helper,
        and more. Always read entry_point.recommendation first.
    """
    engine = DeepEvidenceEngine(url, analysis_mode=mode)
    evidence = await engine.extract_all()

    # Strip non-serializable values and return clean JSON-safe dict
    return _clean_for_mcp(evidence)


@mcp.tool()
async def rip_component(
    url: str,
    selector: str,
    include_children: bool = True,
    include_states: bool = False,
    output_format: str = "json",
) -> dict:
    """
    Extract a specific UI component's HTML and computed CSS from a live page.

    Useful for: extracting a nav, card, button group, hero section, or any
    CSS-selector-targeted element as a reusable blueprint.

    Args:
        url:              Page URL containing the component
        selector:         CSS selector, e.g. 'nav', '.hero', '#pricing-table'
        include_children: If True, recursively includes child element styles
        include_states:   If True, physically hovers/focuses interactive elements
                          within the component to capture CSS state deltas
                          (hover colors, focus outlines, transitions)
        output_format:    'json' (default) or 'figma' — when 'figma', adds a
                          figma_markdown key with Tailwind JSX pseudocode,
                          interactive states table, design tokens, and anatomy

    Returns:
        blueprint dict with: html (cleaned), css (scoped), computed_styles,
        bounding_box, dependency hints, and optionally interactive_states
        and figma_markdown.
    """
    ripper = ComponentRipper(url, selector)
    blueprint = await ripper.rip(include_states=include_states, output_format=output_format)
    return _clean_for_mcp(blueprint)


@mcp.tool()
async def audit_design_debt(evidence: dict) -> dict:
    """
    Analyze evidence JSON from analyze_design_system to find design inconsistencies.

    Acts as a design linter — identifies what is WRONG, not just what IS.
    Firecrawl gives you a mirror; this gives you a linter.

    Detects:
    - Color orphans: colors used once that are close to (but not) palette colors
    - Type scale violations: font sizes that don't fit the detected scale ratio
    - Aria misses: interactive-looking elements without role/aria-label
    - Spacing deviations: spacing values that fall outside the base unit grid

    Args:
        evidence: The full evidence dict returned by analyze_design_system

    Returns:
        debt_report with: total_issues, debt_score (0-100, lower=cleaner),
        color_orphans, scale_violations, aria_misses, spacing_deviations,
        and actionable fix suggestions for each issue.
    """
    analyzer = DesignDebtAnalyzer(evidence)
    return analyzer.generate_report()


@mcp.tool()
async def get_design_brief(evidence: dict) -> str:
    """
    Generate a human-readable design brief from evidence JSON.

    Summarizes the design system in plain language suitable for sharing
    with stakeholders, writing to docs, or feeding to another LLM.

    Args:
        evidence: The full evidence dict returned by analyze_design_system

    Returns:
        Markdown-formatted design brief covering: brand personality,
        typography system, color palette, spacing, layout approach,
        and component inventory.
    """
    from design_brief_generator import DesignBriefGenerator
    generator = DesignBriefGenerator(evidence)
    return generator.generate()


@mcp.tool()
async def compare_confidence_tiers(evidence: dict) -> dict:
    """
    Split evidence metrics into high/medium/low confidence tiers.

    Useful for deciding which metrics to trust vs. which to verify manually.
    Metrics below 60% confidence should not be used as ground truth.

    Args:
        evidence: The full evidence dict returned by analyze_design_system

    Returns:
        tiered dict: {high (>=80%), medium (60-79%), low (<60%)}
        Each tier lists metric names and their confidence scores.
    """
    tiers = {"high": {}, "medium": {}, "low": {}}

    for key, value in evidence.items():
        if not isinstance(value, dict):
            continue
        conf = value.get("confidence", None)
        if conf is None:
            continue

        # Normalize 0-1 scale to 0-100
        if isinstance(conf, float) and conf <= 1.0:
            conf = round(conf * 100)
        else:
            conf = int(conf)

        entry = {"confidence": conf, "summary": value.get("pattern", value.get("summary", ""))}

        if conf >= 80:
            tiers["high"][key] = entry
        elif conf >= 60:
            tiers["medium"][key] = entry
        else:
            tiers["low"][key] = entry

    return tiers


def _clean_for_mcp(obj, depth: int = 0):
    """Recursively strip non-JSON-serializable values and cap depth."""
    if depth > 8:
        return "[truncated]"
    if isinstance(obj, dict):
        return {k: _clean_for_mcp(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_for_mcp(item, depth + 1) for item in obj[:50]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # bytes, sets, etc.
    try:
        return str(obj)
    except Exception:
        return None


@mcp.tool()
async def cloudflare_crawl(url: str, limit: int = 10, depth: int = 2) -> dict:
    """
    Crawl a website using Cloudflare Browser Rendering and return discovered pages with content.

    Uses Cloudflare's /crawl API to discover and fetch pages from a website.
    Returns page URLs and content in Markdown format.
    Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN env vars.

    Args:
        url: Starting URL to crawl (e.g., "https://stripe.com")
        limit: Maximum pages to crawl (default 10, max 1000)
        depth: Maximum link depth from starting URL (default 2)

    Returns:
        Dict with status, crawl_id, urls, pages (with content), and total count.
    """
    from cloudflare_crawl import CloudflareCrawler, CloudflareNotConfigured, is_cloudflare_available

    if not is_cloudflare_available():
        return {
            'error': 'Cloudflare not configured. Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.',
            'available': False
        }

    try:
        crawler = CloudflareCrawler()
        result = await crawler.crawl(
            url,
            limit=min(limit, 1000),
            depth=min(depth, 10),
            formats=['markdown'],
            render=True,
            timeout=300
        )
        return _clean_for_mcp(result)
    except CloudflareNotConfigured as e:
        return {'error': str(e), 'available': False}
    except Exception as e:
        return {'error': f'Cloudflare crawl failed: {str(e)[:200]}'}


@mcp.tool()
async def site_topology(url: str, discovery_method: str = 'auto') -> dict:
    """
    Analyze the topology of a website: sections, hierarchy, URL patterns,
    and content distribution.

    Args:
        url: The website URL to analyze
        discovery_method: 'auto' | 'cloudflare' | 'nav'

    Returns topology with sections, hierarchy depth, URL templates,
    and content type distribution.
    """
    urls = []
    url_source = 'nav_discovery'

    # Try Cloudflare first
    if discovery_method in ('cloudflare', 'auto'):
        try:
            from cloudflare_crawl import CloudflareCrawler, is_cloudflare_available
            if is_cloudflare_available():
                crawler = CloudflareCrawler()
                urls = await crawler.discover_urls(url, limit=100, depth=3)
                url_source = 'cloudflare'
        except Exception:
            pass

    # Fallback to nav scraping
    if not urls:
        try:
            engine = DeepEvidenceEngine(url, analysis_mode='single')
            urls = await engine._quick_discover(url)
            url_source = 'nav_discovery'
        except Exception as e:
            return {'error': f'URL discovery failed: {str(e)[:200]}'}

    if len(urls) < 3:
        return {'error': f'Only {len(urls)} URLs found — need at least 3', 'urls_found': len(urls)}

    from site_topology import SiteTopologyAnalyzer
    topo = SiteTopologyAnalyzer()
    result = topo.analyze(urls, url, url_source=url_source)
    return _clean_for_mcp(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
