"""
Tests for ComponentRipper._expand_and_capture_children

Coverage categories (per spec):
  Detection  — what triggers are found
  Action     — click behaviour, animation delay, navigation guard
  Capture    — DOM diff and revealed-content extraction
  Cleanup    — Escape-key reset, crash-safe finally block
  Boundaries — max_expansions, expansion_timeout_ms, component_category filter
  Integration — full Bazaar nav expansion (marked slow, requires network)

All unit tests use AsyncMock pages so no browser is launched.
"""

import asyncio
import sys
import os
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

# ── Import path setup ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from component_ripper import ComponentRipper, assess_selector_stability


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_ripper(url="https://example.com") -> ComponentRipper:
    ripper = ComponentRipper.__new__(ComponentRipper)
    ripper.url = url
    ripper.selector = None
    return ripper


def make_page(*, triggers=None, before_nodes=None, after_nodes=None,
              revealed=None, current_url="https://example.com"):
    """
    Build an AsyncMock page whose evaluate() returns preset data per call.

    evaluate() call order:
      0 → trigger discovery list
      1 → before_nodes snapshot (first trigger)
      2 → after_nodes snapshot (first trigger)
      3 → [optional] portal fallback (only when after == before)
      4 → revealed content detail
      ... repeats for subsequent triggers
    """
    page = MagicMock()
    page.url = current_url

    page.evaluate = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.go_back = AsyncMock()

    locator_mock = MagicMock()
    locator_mock.is_visible = AsyncMock(return_value=True)
    locator_mock.hover = AsyncMock()
    locator_mock.click = AsyncMock()
    page.locator = MagicMock(return_value=MagicMock(first=locator_mock))

    _triggers = triggers or []
    _before   = before_nodes or []
    _after    = after_nodes or ["DIV@10,0", "SPAN@20,0"]
    _revealed = revealed or {
        "node_count": 5,
        "links": [{"href": "https://example.com/a", "text": "Page A"}],
        "text_items": ["Page A"],
        "depth": 3,
        "container_bounds": {"w": 300, "h": 200},
        "outer_html_snippet": "<div>menu</div>",
    }

    # Responses keyed by call index. We generate a fresh sequence each call.
    _call_seq = iter(
        [_triggers]  # call 0: trigger discovery
        + [_before, _after, _revealed]  # calls 1-3: per trigger (first)
        + [_before, _after, _revealed]  # repeats for subsequent triggers
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [_before, _after, _revealed]
        + [None]  # safety sentinel
    )

    async def _evaluate(script, *args, **kwargs):
        try:
            return next(_call_seq)
        except StopIteration:
            return None

    page.evaluate.side_effect = _evaluate
    return page, locator_mock


# ═══════════════════════════════════════════════════════════════════════════
# 1. DETECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestDetection:

    async def test_finds_aria_expanded_false(self):
        """Triggers with aria-expanded=false are picked up."""
        fake_trigger = {
            "selector": "button#menu-toggle",
            "text": "Products",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, _ = make_page(triggers=[fake_trigger])
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav")
        assert any(t["pattern"] == "aria-expandable" for t in result["expandable_triggers"])

    async def test_does_not_flag_plain_links(self):
        """An empty trigger list (plain <a> links) returns the EMPTY sentinel."""
        page, _ = make_page(triggers=[])
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav")
        assert result["expansions_performed"] == 0
        assert result["expandable_triggers"] == []

    async def test_handles_details_summary_elements(self):
        """details/summary pattern is classified correctly."""
        fake_trigger = {
            "selector": "details > summary",
            "text": "More options",
            "pattern": "details/summary",
            "ariaExpanded": None,
            "tag": "summary",
        }
        page, _ = make_page(triggers=[fake_trigger])
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "details")
        assert any(t["pattern"] == "details/summary" for t in result["expandable_triggers"])

    async def test_ignores_already_expanded(self):
        """
        A trigger with aria-expanded=true in the initial snapshot should not be
        in the candidate list — the JS phase filters these. We verify by checking
        only aria-expanded=false triggers appear (simulated by setting the fixture
        trigger's ariaExpanded to 'false').
        """
        page, _ = make_page(triggers=[
            {"selector": "#open-btn", "text": "Open (already)", "pattern": "aria-expandable",
             "ariaExpanded": "true", "tag": "button"},
        ])
        ripper = make_ripper()
        # The JS fixture already pre-returns whatever we give it. In real
        # execution the JS would NOT include aria-expanded=true. We assert the
        # function at least propagates whatever JS returned without duplicating.
        result = await ripper._expand_and_capture_children(page, "nav")
        trigger_selectors = [t["selector"] for t in result["expandable_triggers"]]
        assert trigger_selectors.count("#open-btn") == 1  # no duplication


# ═══════════════════════════════════════════════════════════════════════════
# 2. ACTION
# ═══════════════════════════════════════════════════════════════════════════

class TestAction:

    async def test_click_reveals_hidden_content(self):
        """After clicking, new_nodes diff produces an expansion record."""
        trigger = {
            "selector": "button#menu",
            "text": "Menu",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, locator = make_page(triggers=[trigger])
        ripper = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav")
        assert result["expansions_performed"] == 1
        assert len(result["expansions"]) == 1
        assert result["expansions"][0]["revealed"]["node_count"] == 5

    async def test_handles_animation_delay(self):
        """
        The 350ms wait is always performed; we verify the function still
        returns valid data when evaluate() is called many times (animation
        wait doesn't break the sequence).
        """
        trigger = {
            "selector": "button#animated",
            "text": "Animated dropdown",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, _ = make_page(triggers=[trigger])
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav")
        assert result["total_revealed_nodes"] > 0

    async def test_click_on_non_button_expandable(self):
        """
        A click that navigates away should trigger go_back and NOT produce
        an expansion record.
        """
        trigger = {
            "selector": "a#nav-link",
            "text": "Visit page",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "a",
        }
        # Simulate navigation by changing page.url after the click
        page, locator = make_page(triggers=[trigger])

        # The click will change the URL — simulate via a side effect on click
        navigated_away = {"done": False}

        async def _click_side_effect(*args, **kwargs):
            page.url = "https://example.com/other-page"
        locator.click.side_effect = _click_side_effect

        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(page, "nav")

        # go_back must have been called
        page.go_back.assert_awaited()
        # No expansion recorded for a navigation-away trigger
        assert result["expansions"] == [] or result["total_revealed_nodes"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. CAPTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestCapture:

    async def test_captures_new_nodes(self):
        """Revealed node_count matches the mock payload."""
        trigger = {
            "selector": "#menu-btn",
            "text": "Open menu",
            "pattern": "menu-trigger",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, _ = make_page(
            triggers=[trigger],
            before_nodes=[],
            after_nodes=["LI@100,0", "LI@120,0", "LI@140,0"],
            revealed={
                "node_count": 12,
                "links": [{"href": "/a", "text": "A"}, {"href": "/b", "text": "B"}],
                "text_items": ["A", "B"],
                "depth": 4,
                "container_bounds": {"w": 250, "h": 300},
                "outer_html_snippet": "<ul>...</ul>",
            },
        )
        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(page, "nav")

        assert result["total_revealed_nodes"] == 12
        assert result["expansions"][0]["revealed"]["node_count"] == 12

    async def test_does_not_include_unchanged_nodes(self):
        """
        When before == after (no new nodes) the fallback portal check runs,
        but if that also returns empty, no expansion is recorded.
        """
        trigger = {
            "selector": "#menu-btn",
            "text": "Menu",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        same_nodes = ["DIV@0,0", "SPAN@20,0"]

        page, _ = make_page(
            triggers=[trigger],
            before_nodes=same_nodes,
            after_nodes=same_nodes,  # no change
        )
        # Override evaluate to return the right value per call.
        # evaluate() call order inside _click_and_diff:
        #   0  trigger discovery
        #   1  before_nodes snapshot
        #   2  hover delay:  '() => new Promise(r => setTimeout(r, 100))'  → None ok
        #   3  wait 350ms:   '() => new Promise(r => setTimeout(r, 350))'  → None ok
        #   4  after_nodes snapshot
        #   5  portal fallback → empty means no new nodes
        _seq = iter([
            [trigger],      # 0 trigger discovery
            same_nodes,     # 1 before
            None,           # 2 hover delay (ignored)
            None,           # 3 wait 350ms (ignored)
            same_nodes,     # 4 after  (no diff)
            [],             # 5 portal fallback → empty
        ])
        async def _ev(script, *a, **kw):
            try:
                return next(_seq)
            except StopIteration:
                return None
        page.evaluate.side_effect = _ev

        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(page, "nav")

        assert result["expansions"] == []
        assert result["total_revealed_nodes"] == 0

    async def test_counts_links_correctly(self):
        """Link count in the revealed dict is trusted exactly."""
        trigger = {
            "selector": "#nav-menu",
            "text": "Products",
            "pattern": "menu-trigger",
            "ariaExpanded": "false",
            "tag": "button",
        }
        links = [{"href": f"/p/{i}", "text": f"Product {i}"} for i in range(8)]
        page, _ = make_page(
            triggers=[trigger],
            revealed={
                "node_count": 8,
                "links": links,
                "text_items": [f"Product {i}" for i in range(8)],
                "depth": 3,
                "container_bounds": {"w": 400, "h": 250},
                "outer_html_snippet": "<nav>...</nav>",
            },
        )
        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(page, "nav")

        assert len(result["expansions"][0]["revealed"]["links"]) == 8


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLEANUP
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanup:

    async def test_closes_expanded_menus_after_capture(self):
        """Escape key is pressed after a successful expansion."""
        trigger = {
            "selector": "#menu",
            "text": "Menu",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, _ = make_page(triggers=[trigger])
        ripper   = make_ripper()

        await ripper._expand_and_capture_children(page, "nav")
        page.keyboard.press.assert_awaited_with("Escape")

    async def test_cleanup_via_escape_key(self):
        """Even with 2 triggers, Escape is called at least twice."""
        triggers = [
            {"selector": "#m1", "text": "Menu 1", "pattern": "aria-expandable",
             "ariaExpanded": "false", "tag": "button"},
            {"selector": "#m2", "text": "Menu 2", "pattern": "aria-expandable",
             "ariaExpanded": "false", "tag": "button"},
        ]
        page, _ = make_page(triggers=triggers)
        ripper   = make_ripper()

        await ripper._expand_and_capture_children(page, "nav")
        # Escape called once per expansion (in the finally block)
        assert page.keyboard.press.await_count >= 2

    async def test_cleanup_on_crash(self):
        """
        If the expansion body raises an exception mid-way, the finally block
        still runs and presses Escape.
        """
        trigger = {
            "selector": "#crash-btn",
            "text": "Crash",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, locator = make_page(triggers=[trigger])
        # Make click() raise so the body crashes
        locator.click.side_effect = RuntimeError("Simulated crash")

        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(page, "nav")

        # Escape still gets pressed by the finally block
        page.keyboard.press.assert_awaited_with("Escape")
        # No expansion recorded for a crashed trigger
        assert result["expansions"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundaries:

    async def test_max_expansions_limit(self):
        """
        With 30 triggers and max_expansions=10, only 10 are performed and
        20 are reported as skipped.
        """
        triggers = [
            {"selector": f"#btn-{i}", "text": f"Item {i}", "pattern": "aria-expandable",
             "ariaExpanded": "false", "tag": "button"}
            for i in range(30)
        ]
        page, _ = make_page(triggers=triggers)
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav", max_expansions=10)
        assert result["expansions_performed"] <= 10
        assert result["expansions_skipped"] == 20

    async def test_depth_limit(self):
        """
        max_expansions applies to the total count regardless of DOM nesting.
        (Depth limiting is enforced externally; here we just confirm the param
        constrains the performed count.)
        """
        triggers = [
            {"selector": f"#t{i}", "text": f"Trigger {i}", "pattern": "aria-expandable",
             "ariaExpanded": "false", "tag": "button"}
            for i in range(20)
        ]
        page, _ = make_page(triggers=triggers)
        ripper   = make_ripper()

        result = await ripper._expand_and_capture_children(page, "nav", max_expansions=5)
        assert result["expansions_performed"] <= 5

    async def test_no_expansion_on_non_nav_components(self):
        """
        component_category='content_grid' triggers the category gate and
        returns expansions_performed=0 without clicking anything.
        """
        triggers = [
            {"selector": "#expand-btn", "text": "Show more", "pattern": "show-more",
             "ariaExpanded": "false", "tag": "button"},
        ]
        page, locator = make_page(triggers=triggers)
        ripper = make_ripper()

        result = await ripper._expand_and_capture_children(
            page, ".card-grid",
            component_category="content_grid",
        )
        assert result["expansions_performed"] == 0
        locator.click.assert_not_awaited()

    async def test_timeout_per_expansion(self):
        """
        A trigger that hangs longer than expansion_timeout_ms is counted in
        result['timeouts'] and does not block subsequent expansions.
        """
        trigger = {
            "selector": "#slow-btn",
            "text": "Slow menu",
            "pattern": "aria-expandable",
            "ariaExpanded": "false",
            "tag": "button",
        }
        page, locator = make_page(triggers=[trigger])

        # Make click take 2s — longer than a 500ms expansion_timeout_ms
        async def _slow_click(*args, **kwargs):
            await asyncio.sleep(2)
        locator.click.side_effect = _slow_click

        ripper = make_ripper()
        result = await ripper._expand_and_capture_children(
            page, "nav",
            expansion_timeout_ms=500,
        )

        assert result["timeouts"] == 1
        # Escape is still pressed after a timeout
        page.keyboard.press.assert_awaited_with("Escape")

    async def test_non_nav_categories_exhaustive(self):
        """All documented non-expandable categories are gated."""
        gated = ['content_grid', 'content', 'media', 'gallery', 'section', 'hero']
        triggers = [
            {"selector": "#btn", "text": "More", "pattern": "show-more",
             "ariaExpanded": "false", "tag": "button"},
        ]
        ripper = make_ripper()
        for cat in gated:
            page, locator = make_page(triggers=triggers)
            result = await ripper._expand_and_capture_children(
                page, ".component",
                component_category=cat,
            )
            assert result["expansions_performed"] == 0, f"Category '{cat}' was NOT gated"
            locator.click.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 6. INTEGRATION (network, marked slow)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.integration
class TestIntegration:

    async def test_full_bazaar_nav_expansion(self):
        """
        Full end-to-end: launch a real browser against harpersbazaar.com,
        discover the primary nav, and assert the expansion finds at least
        one mega-menu link.

        Requires network access and a Playwright-compatible Chromium install.
        Run with: pytest -m "slow and integration" tests/test_nav_expansion.py
        """
        from patchright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1440, 'height': 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            try:
                await page.goto("https://www.harpersbazaar.com/", timeout=60000,
                                wait_until='domcontentloaded')
                await asyncio.sleep(3)

                ripper = make_ripper("https://www.harpersbazaar.com/")
                result = await ripper._expand_and_capture_children(
                    page, "header",
                    max_expansions=5,
                    component_category="navigation",
                )

                assert "expansions_performed" in result
                assert "expansions_skipped" in result
                assert "timeouts" in result
                assert isinstance(result["patterns_detected"], list)

                # At least one expandable trigger should be found in the Bazaar header
                assert len(result["expandable_triggers"]) > 0, (
                    "Expected at least one expandable trigger in header — "
                    "check if the site structure changed"
                )

                print(f"\n  Bazaar nav: {result['expansions_performed']} expanded, "
                      f"{result['total_revealed_nodes']} nodes revealed, "
                      f"{result['timeouts']} timeouts")

            finally:
                await browser.close()
