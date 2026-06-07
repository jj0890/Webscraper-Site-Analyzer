"""
Motion detection verification tests.

Tests three things:
  1. _synthesize_motion_narrative — the new explanation layer
  2. multi_template_discover — the two-pass split Phase 1
  3. Motion extractor accuracy against known CSS (using mock motion data)

Run: pytest tests/test_motion_detection.py -v -m "not slow"
"""

import asyncio
import sys
import os
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from deep_evidence_engine import DeepEvidenceEngine, multi_template_discover


def make_engine():
    e = DeepEvidenceEngine.__new__(DeepEvidenceEngine)
    return e


# ═══════════════════════════════════════════════════════════════════════════
# 1. _synthesize_motion_narrative
# ═══════════════════════════════════════════════════════════════════════════

class TestMotionNarrativeSynthesis:

    def _make_motion(self, values_ms, patterns=None, libraries=None, kf_anims=None, easing='ease-in-out'):
        """Build a minimal motion_tokens dict."""
        tiers = {}
        for ms in values_ms:
            if ms <= 150:    name = 'fast'
            elif ms <= 350:  name = 'normal'
            elif ms <= 700:  name = 'slow'
            else:             name = 'dramatic'
            tiers[name] = {'ms': ms, 'count': 5, 'usage': 'test'}

        return {
            'details': {
                'duration_scale': {
                    'values_ms': values_ms,
                    'tiers':     tiers,
                },
                'easing_palette': {
                    'primary': easing,
                    'curves':  [],
                    'roles':   {},
                },
                'motion_patterns': patterns or [],
                'keyframe_animations': kf_anims or [],
                'libraries': libraries or [],
            },
            'choreography': [],
        }

    # ── Strategy classification ──────────────────────────────────────────────

    def test_single_duration_is_minimal(self):
        """One duration, no library → minimal strategy."""
        motion = self._make_motion([150])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['strategy'] == 'minimal', f"Got: {result['strategy']}"

    def test_multiple_durations_with_fast_hover_is_performance_conscious(self):
        """3+ durations, hover ≤ 150ms, no library → performance-conscious."""
        motion = self._make_motion(
            [100, 250, 400, 600],
            patterns=[
                {'name': 'hover_feedback', 'duration_ms': 100, 'easing': 'ease-in-out', 'element_count': 15, 'properties': ['opacity']},
                {'name': 'state_change',   'duration_ms': 250, 'easing': 'ease',        'element_count': 20, 'properties': ['transform']},
            ]
        )
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['strategy'] == 'performance-conscious', f"Got: {result['strategy']}"

    def test_spring_easing_is_expressive(self):
        """Spring/overshoot curve → expressive strategy."""
        motion = self._make_motion([300, 500])
        motion['details']['easing_palette']['curves'] = [
            {'value': 'cubic-bezier(0.34, 1.56, 0.64, 1)', 'role': 'spring', 'count': 8}
        ]
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['strategy'] == 'expressive', f"Got: {result['strategy']}"

    def test_js_library_detected_is_layered(self):
        """JS animation library detected → layered strategy."""
        motion = self._make_motion([300, 500], libraries=['GSAP'])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['strategy'] == 'layered', f"Got: {result['strategy']}"

    # ── Context grouping ─────────────────────────────────────────────────────

    def test_hover_pattern_goes_into_hover_context(self):
        """hover_feedback pattern maps to 'hover' context."""
        motion = self._make_motion(
            [100, 300],
            patterns=[{'name': 'hover_feedback', 'duration_ms': 100, 'easing': 'ease-in-out', 'element_count': 10, 'properties': ['opacity']}]
        )
        result = make_engine()._synthesize_motion_narrative(motion)
        assert 'hover' in result['context_groups'], "hover context missing"
        assert result['context_groups']['hover']['ms'] == 100

    def test_state_change_goes_into_reveal_context(self):
        """state_change pattern maps to 'reveal' context."""
        motion = self._make_motion(
            [250],
            patterns=[{'name': 'state_change', 'duration_ms': 250, 'easing': 'ease', 'element_count': 20, 'properties': ['transform']}]
        )
        result = make_engine()._synthesize_motion_narrative(motion)
        assert 'reveal' in result['context_groups']

    # ── Anomaly detection ────────────────────────────────────────────────────

    def test_outlier_duration_flagged_as_anomaly(self):
        """A duration that's 4× the median should be flagged."""
        motion = self._make_motion([150, 200, 800])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert any('800' in a or 'outlier' in a.lower() for a in result['anomalies']), \
            f"800ms outlier not flagged. Anomalies: {result['anomalies']}"

    def test_infinite_keyframe_flagged_as_anomaly(self):
        """An infinite-loop keyframe > 500ms should be flagged."""
        motion = self._make_motion(
            [150, 250],
            kf_anims=[{'name': 'spin', 'duration_ms': 1000, 'iteration': 'infinite', 'easing': 'linear', 'direction': 'normal'}]
        )
        result = make_engine()._synthesize_motion_narrative(motion)
        assert any('infinite' in a.lower() or 'spin' in a.lower() for a in result['anomalies']), \
            f"Infinite keyframe not flagged. Anomalies: {result['anomalies']}"

    def test_js_library_flagged_as_anomaly(self):
        """Detected JS library means CSS tokens are incomplete."""
        motion = self._make_motion([300], libraries=['GSAP', 'Framer Motion'])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert any('GSAP' in a or 'javascript' in a.lower() for a in result['anomalies']), \
            f"JS library anomaly not flagged. Anomalies: {result['anomalies']}"

    def test_sub_50ms_duration_flagged(self):
        """Durations below 50ms are below human perception threshold."""
        motion = self._make_motion([30, 150])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert any('30' in a or 'perception' in a.lower() or 'threshold' in a.lower()
                   for a in result['anomalies']), \
            f"30ms sub-perception not flagged. Anomalies: {result['anomalies']}"

    # ── Summary output ───────────────────────────────────────────────────────

    def test_summary_is_non_empty_string(self):
        """Summary must be a non-empty human-readable string."""
        motion = self._make_motion([100, 250, 400])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert isinstance(result.get('summary'), str)
        assert len(result['summary']) > 30

    def test_summary_mentions_strategy(self):
        """Summary should reference the classified strategy."""
        motion = self._make_motion([150])
        result = make_engine()._synthesize_motion_narrative(motion)
        assert any(word in result['summary'].lower()
                   for word in ['minimal', 'performance', 'layered', 'expressive']), \
            f"Strategy not in summary: {result['summary']}"

    def test_dominant_easing_present(self):
        """dominant_easing field must be present and non-empty."""
        motion = self._make_motion([150, 300], easing='ease-out')
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result.get('dominant_easing') == 'ease-out'

    # ── Polyester data regression ────────────────────────────────────────────

    def test_polyester_homepage_is_performance_conscious(self):
        """
        Polyester homepage motion: 100ms hover, 250ms reveals, 400ms slow, 600ms dramatic.
        With JS animation library absent and fast hover → performance-conscious.
        """
        motion = self._make_motion(
            [100, 250, 400, 600],
            patterns=[
                {'name': 'hover_feedback', 'duration_ms': 100, 'easing': 'ease-in-out', 'element_count': 15, 'properties': ['opacity', 'background-color']},
                {'name': 'state_change',   'duration_ms': 250, 'easing': 'ease',        'element_count': 20, 'properties': ['opacity', 'transform']},
            ]
        )
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['strategy'] == 'performance-conscious'
        assert 'hover' in result['context_groups']
        assert result['context_groups']['hover']['ms'] == 100

    def test_cross_page_variance_is_not_anomaly_when_contextual(self):
        """
        Homepage 100ms hover vs article 170ms hover is NOT an anomaly in the
        narrative — each page's motion is evaluated independently.
        The cross-page comparison note is set externally.
        """
        motion_homepage = self._make_motion([100, 250, 400, 600])
        motion_article  = self._make_motion([170, 200, 400, 600])

        home_result    = make_engine()._synthesize_motion_narrative(motion_homepage)
        article_result = make_engine()._synthesize_motion_narrative(motion_article)

        # Neither should flag the other's durations as anomalies
        assert not any('170' in a for a in home_result['anomalies']), \
            "Homepage narrative shouldn't reference article's 170ms"
        assert not any('100' in a for a in article_result['anomalies']), \
            "Article narrative shouldn't reference homepage's 100ms"


# ═══════════════════════════════════════════════════════════════════════════
# 2. multi_template_discover — the Phase 1 two-pass split
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiTemplateDiscover:

    def _make_mock_response(self, links):
        """Build a mock requests.Response with link HTML."""
        html = '<html><body>' + ''.join(f'<a href="{l}">{l}</a>' for l in links) + '</body></html>'
        mock = MagicMock()
        mock.status_code = 200
        mock.text = html
        return mock

    async def test_returns_required_keys(self):
        """Result must have patterns, total_urls_found, discovery_time_s, url."""
        links = [
            'https://example.com/blog/post-one',
            'https://example.com/blog/post-two',
            'https://example.com/shop/item-a',
        ]
        with patch('requests.get', return_value=self._make_mock_response(links)):
            result = await multi_template_discover('https://example.com/')

        assert 'patterns' in result
        assert 'total_urls_found' in result
        assert 'discovery_time_s' in result
        assert 'url' in result

    async def test_clusters_blog_urls_into_one_pattern(self):
        """Multiple /blog/:slug URLs should cluster into one template."""
        links = [
            'https://example.com/blog/post-one',
            'https://example.com/blog/post-two',
            'https://example.com/blog/post-three',
            'https://example.com/about',
        ]
        with patch('requests.get', return_value=self._make_mock_response(links)):
            result = await multi_template_discover('https://example.com/')

        patterns = result['patterns']
        blog_pats = [p for p in patterns if 'blog' in p['template']]
        assert len(blog_pats) == 1, f"Expected 1 blog pattern, got {blog_pats}"
        assert blog_pats[0]['count'] == 3

    async def test_pattern_has_required_fields(self):
        """Each pattern must have template, count, examples, depth, label."""
        links = ['https://example.com/features/interview-one']
        with patch('requests.get', return_value=self._make_mock_response(links)):
            result = await multi_template_discover('https://example.com/')

        for p in result['patterns']:
            assert 'template' in p,  f"Pattern missing template: {p}"
            assert 'count' in p,     f"Pattern missing count: {p}"
            assert 'examples' in p,  f"Pattern missing examples: {p}"
            assert 'depth' in p,     f"Pattern missing depth: {p}"
            assert 'label' in p,     f"Pattern missing label: {p}"

    async def test_external_urls_excluded(self):
        """External links (different domain) must not appear in patterns."""
        links = [
            'https://example.com/blog/post',
            'https://twitter.com/example',        # external
            'https://instagram.com/example_ig',   # external
        ]
        with patch('requests.get', return_value=self._make_mock_response(links)):
            result = await multi_template_discover('https://example.com/')

        all_examples = [e for p in result['patterns'] for e in p['examples']]
        assert not any('twitter.com' in e for e in all_examples)
        assert not any('instagram.com' in e for e in all_examples)

    async def test_returns_when_site_unreachable(self):
        """Network error should return empty patterns, not raise."""
        import requests as _r
        with patch('requests.get', side_effect=_r.exceptions.ConnectionError("timeout")):
            result = await multi_template_discover('https://example.com/')

        assert 'patterns' in result
        assert isinstance(result['patterns'], list)

    async def test_depth_1_only_fetches_homepage(self):
        """max_depth=1 should only fetch the homepage, not follow links."""
        call_count = {'n': 0}
        def _mock_get(url, **kwargs):
            call_count['n'] += 1
            return self._make_mock_response(['https://example.com/page-a', 'https://example.com/page-b'])

        with patch('requests.get', side_effect=_mock_get):
            await multi_template_discover('https://example.com/', max_depth=1)

        assert call_count['n'] == 1, f"Expected 1 HTTP call (homepage only), got {call_count['n']}"

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_completes_in_under_15_seconds_real_site(self):
        """
        Phase 1 contract test — must complete in < 15s against a real site.
        This is THE test that proves the two-pass split solves the timeout.
        """
        start = time.time()
        result = await multi_template_discover('https://www.polyesterzine.com/')
        elapsed = time.time() - start

        assert elapsed < 15.0, (
            f"Discovery took {elapsed:.1f}s — must be < 15s. "
            "Phase 1 must NOT run deep Playwright extraction."
        )
        assert len(result['patterns']) > 0, "Should find at least one URL pattern"
        print(f"\n  Polyester: {elapsed:.1f}s, {len(result['patterns'])} patterns, "
              f"{result['total_urls_found']} URLs found")
        for p in result['patterns'][:5]:
            print(f"    {p['template']} ({p['count']} URLs) — e.g. {p['examples'][0] if p['examples'] else '?'}")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Motion extractor verification against known CSS data
# ═══════════════════════════════════════════════════════════════════════════

class TestMotionExtractorAccuracy:
    """
    These tests verify that the motion token synthesis correctly interprets
    specific values — using pre-computed evidence that matches what the
    extractor would produce for given CSS.
    """

    def test_100ms_hover_classified_as_fast_tier(self):
        """100ms should land in the 'fast' or 'micro' tier for hover."""
        motion = {
            'details': {
                'duration_scale': {
                    'values_ms': [100],
                    'tiers': {'fast': {'ms': 100, 'count': 1, 'usage': 'hover states, button feedback'}}
                },
                'easing_palette': {'primary': 'ease-in-out', 'curves': [], 'roles': {}},
                'motion_patterns': [{'name': 'hover_feedback', 'duration_ms': 100, 'easing': 'ease-in-out', 'element_count': 5, 'properties': ['opacity']}],
                'keyframe_animations': [],
                'libraries': [],
            },
            'choreography': [],
        }
        result = make_engine()._synthesize_motion_narrative(motion)
        # hover context should have 100ms
        hover = result['context_groups'].get('hover', {})
        assert hover.get('ms') == 100, f"Expected hover at 100ms, got {hover}"

    def test_standard_easing_labeled_correctly(self):
        """cubic-bezier(0.4, 0, 0.2, 1) is Material Design's standard ease-in-out."""
        motion = {
            'details': {
                'duration_scale': {'values_ms': [200], 'tiers': {}},
                'easing_palette': {
                    'primary': 'cubic-bezier(0.4, 0, 0.2, 1)',
                    'curves':  [],
                    'roles':   {'default': 'cubic-bezier(0.4, 0, 0.2, 1)'},
                },
                'motion_patterns': [],
                'keyframe_animations': [],
                'libraries': [],
            },
            'choreography': [],
        }
        result = make_engine()._synthesize_motion_narrative(motion)
        assert result['dominant_easing'] == 'cubic-bezier(0.4, 0, 0.2, 1)'
        # The summary should mention the easing
        assert 'cubic-bezier' in result['summary'] or 'Custom easing' in result['summary']

    def test_no_motion_data_returns_gracefully(self):
        """Empty motion dict should not crash synthesis."""
        result = make_engine()._synthesize_motion_narrative({})
        assert isinstance(result, dict)
        assert 'strategy' in result
        assert 'summary' in result

    def test_missing_details_key_handled(self):
        """motion_tokens without 'details' key — common on MRI/degraded scans."""
        motion = {'pattern': 'No motion detected', 'confidence': 0}
        result = make_engine()._synthesize_motion_narrative(motion)
        assert isinstance(result, dict)
        assert result.get('strategy') is not None
