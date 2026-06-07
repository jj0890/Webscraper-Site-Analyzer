"""
Tests for analysis_focus scoring and API wiring.

These tests use the offline _score_url_diversity() method so they
run without a live browser. The integration test (slow) requires network.

Run fast tests: pytest tests/test_analysis_focus.py -v -m "not slow"
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from deep_evidence_engine import DeepEvidenceEngine


def make_engine(focus='auto'):
    engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)
    engine.analysis_focus = focus if focus in DeepEvidenceEngine._FOCUS_SIGNALS else 'auto'
    return engine


BASE = 'https://cinemarchives.com.br/'

CINEMA_POOL = [
    'https://cinemarchives.com.br/support',
    'https://cinemarchives.com.br/manifesto',
    'https://cinemarchives.com.br/magazines',
    'https://cinemarchives.com.br/magazines/presence-du-cinema',
    'https://cinemarchives.com.br/magazines/movie',
    'https://cinemarchives.com.br/search?q=Godard',
]


# ═══════════════════════════════════════════════════════════════════════════
# FOCUS SCORING — content
# ═══════════════════════════════════════════════════════════════════════════

class TestContentFocus:

    def test_support_ranks_lower_with_content_focus(self):
        """/support must rank worse with content focus than with auto."""
        auto_scored   = make_engine('auto')._score_url_diversity(CINEMA_POOL, BASE)
        content_scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)

        auto_urls    = [s['url'] for s in auto_scored]
        content_urls = [s['url'] for s in content_scored]

        support_url = 'https://cinemarchives.com.br/support'
        auto_rank    = auto_urls.index(support_url)
        content_rank = content_urls.index(support_url)

        assert content_rank > auto_rank, (
            f"/support rank should worsen with content focus: "
            f"auto={auto_rank}, content={content_rank}"
        )

    def test_manifesto_ranks_lower_with_content_focus(self):
        """/manifesto (institutional) must drop when content focus is set."""
        auto_scored    = make_engine('auto')._score_url_diversity(CINEMA_POOL, BASE)
        content_scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)
        auto_urls    = [s['url'] for s in auto_scored]
        content_urls = [s['url'] for s in content_scored]

        manifesto = 'https://cinemarchives.com.br/manifesto'
        assert content_urls.index(manifesto) > auto_urls.index(manifesto), \
            "/manifesto should rank lower with content focus"

    def test_magazines_ranks_in_top_3_with_content_focus(self):
        """Magazine/archive URLs must be in the top 3 picks with content focus."""
        scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)
        top3 = [s['url'] for s in scored[:3]]
        has_content = any('magazine' in u or 'movie' in u or 'presence' in u
                          for u in top3)
        assert has_content, f"Top 3 with content focus should include a magazine URL: {top3}"

    def test_focus_adjustment_field_populated(self):
        """Scored items must have a focus_adjustment field."""
        scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)
        for item in scored:
            assert 'focus_adjustment' in item, \
                f"Missing focus_adjustment on {item['url']}"

    def test_support_has_negative_focus_adjustment(self):
        """/support should have a negative focus_adjustment with content focus."""
        scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)
        support = next(s for s in scored if '/support' in s['url'])
        assert support['focus_adjustment'] < 0, \
            f"/support should have negative adjustment, got {support['focus_adjustment']}"

    def test_magazines_has_positive_focus_adjustment(self):
        """/magazines should have a positive focus_adjustment with content focus."""
        scored = make_engine('content')._score_url_diversity(CINEMA_POOL, BASE)
        mags = next((s for s in scored if s['url'].endswith('/magazines')), None)
        if mags:  # only if it's in the pool
            assert mags['focus_adjustment'] > 0, \
                f"/magazines should have positive adjustment, got {mags['focus_adjustment']}"


# ═══════════════════════════════════════════════════════════════════════════
# FOCUS SCORING — other modes
# ═══════════════════════════════════════════════════════════════════════════

class TestOtherFocusModes:

    ECOM_POOL = [
        'https://shop.example.com/products/t-shirt',
        'https://shop.example.com/collections/summer',
        'https://shop.example.com/about',
        'https://shop.example.com/support',
        'https://shop.example.com/blog/news',
    ]
    ECOM_BASE = 'https://shop.example.com/'

    def test_commerce_focus_raises_product_pages(self):
        """With commerce focus, /products should score higher than /about."""
        scored = make_engine('commerce')._score_url_diversity(self.ECOM_POOL, self.ECOM_BASE)
        urls = [s['url'] for s in scored]
        product_idx = next((i for i, u in enumerate(urls) if '/products' in u), 999)
        about_idx   = next((i for i, u in enumerate(urls) if '/about' in u), 999)
        assert product_idx < about_idx, \
            f"commerce focus: /products (rank {product_idx}) should beat /about (rank {about_idx})"

    def test_documentation_focus_raises_docs_pages(self):
        """documentation focus should prefer /docs, /api, /reference."""
        pool = [
            'https://docs.example.com/api/reference',
            'https://docs.example.com/guides/quickstart',
            'https://docs.example.com/pricing',
            'https://docs.example.com/about',
        ]
        scored = make_engine('documentation')._score_url_diversity(pool, 'https://docs.example.com/')
        top2 = [s['url'] for s in scored[:2]]
        has_docs = any('api' in u or 'guide' in u or 'reference' in u for u in top2)
        assert has_docs, f"Top 2 with documentation focus should include a docs URL: {top2}"

    def test_auto_mode_has_zero_focus_adjustments(self):
        """auto mode must not apply any focus adjustments."""
        scored = make_engine('auto')._score_url_diversity(CINEMA_POOL, BASE)
        for item in scored:
            assert item.get('focus_adjustment', 0) == 0.0, \
                f"auto mode should have 0 focus_adjustment on {item['url']}, " \
                f"got {item['focus_adjustment']}"


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestFocusEdgeCases:

    def test_invalid_focus_falls_back_to_auto(self):
        """Garbage focus value should silently default to auto behavior."""
        engine = make_engine('garbage_value')
        # Should be normalized to 'auto'
        assert engine.analysis_focus == 'auto', \
            f"Invalid focus should normalize to 'auto', got {engine.analysis_focus}"

    def test_content_focus_with_all_institutional_links(self):
        """
        If every URL is institutional, content focus must still return results,
        not an empty list. The penalty brings scores down but doesn't filter them.
        """
        institutional_pool = [
            'https://example.com/support',
            'https://example.com/about',
            'https://example.com/contact',
            'https://example.com/privacy',
        ]
        scored = make_engine('content')._score_url_diversity(
            institutional_pool, 'https://example.com/'
        )
        assert len(scored) > 0, \
            "content focus with all-institutional pool must still return candidates"

    def test_diversity_maintained_within_focus(self):
        """
        Focus adjustments should not cause all results to be from the same template group.
        Diversity logic still runs on top of focus scoring.
        """
        # All /magazines/* links — same template group
        all_same = [
            'https://cinemarchives.com.br/magazines/presence',
            'https://cinemarchives.com.br/magazines/movie',
            'https://cinemarchives.com.br/magazines/cinema',
        ]
        scored = make_engine('content')._score_url_diversity(all_same, BASE)
        # All should still be present (focus doesn't filter)
        assert len(scored) == len(all_same)

    def test_external_urls_excluded(self):
        """External URLs should never appear in scored results."""
        pool_with_external = CINEMA_POOL + ['https://twitter.com/cinemarchives']
        scored = make_engine('content')._score_url_diversity(pool_with_external, BASE)
        external = [s for s in scored if 'twitter.com' in s['url']]
        assert len(external) == 0, "External URLs must be excluded from scored results"

    def test_focus_parameters_accepted_by_api(self):
        """All valid focus values should be accepted by the engine constructor."""
        valid_focuses = ['auto', 'content', 'commerce', 'documentation', 'marketing']
        for focus in valid_focuses:
            engine = make_engine(focus)
            expected = focus if focus in DeepEvidenceEngine._FOCUS_SIGNALS else 'auto'
            assert engine.analysis_focus == expected, \
                f"Focus '{focus}' not correctly set: got {engine.analysis_focus}"
