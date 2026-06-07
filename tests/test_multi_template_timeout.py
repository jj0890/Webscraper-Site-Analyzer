"""
Tests for multi-template two-pass split.

The failing test (test_multi_template_discover_is_fast) defines the contract
for Phase 1 of the two-pass split — a lightweight discovery function that
clusters URL patterns in < 15 seconds without running any deep extraction.

Currently FAILS because multi_template_discover() doesn't exist in
deep_evidence_engine.py — only the single-shot analysis_mode='multi-template'
exists, which runs full extraction on every representative (takes 5-8 min).

When this test passes, the timeout problem is solved.

Run: pytest tests/test_multi_template_timeout.py -v
     (the slow/integration tests need -m "slow" flag)
"""

import asyncio
import sys
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ═══════════════════════════════════════════════════════════════════════════
# 1. THE CONTRACT-DEFINING FAILING TEST
#    This test specifies exactly what multi_template_discover() must do.
#    It fails right now — that is intentional.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.integration
async def test_multi_template_discover_is_fast():
    """
    Phase 1 discovery must complete in < 15 seconds.

    This test FAILS until two-pass split is implemented:
        deep_evidence_engine.multi_template_discover(url) -> Dict

    The function must:
    - Crawl the homepage link graph (no deep Playwright extraction)
    - Cluster URLs into template patterns (/article/:slug, /product/:id, etc.)
    - Return 'patterns' list with counts and example URLs
    - Complete in < 15s even on large sites

    SUCCESS CRITERION: When this test goes green, the timeout is fixed.
    """
    try:
        from deep_evidence_engine import multi_template_discover
    except ImportError:
        pytest.fail(
            "multi_template_discover() does not exist in deep_evidence_engine.py.\n"
            "Implement the two-pass split:\n"
            "  Phase 1: async def multi_template_discover(url) -> Dict\n"
            "    - Fast link crawl (HTML fetch only, no Playwright extraction)\n"
            "    - URL pattern clustering\n"
            "    - Returns in < 15s\n"
            "  Phase 2: async def multi_template_analyze(url, patterns) -> Dict\n"
            "    - Deep Playwright analysis on user-selected patterns only"
        )

    start = time.time()
    result = await multi_template_discover("https://www.harpersbazaar.com/")
    elapsed = time.time() - start

    assert elapsed < 15.0, (
        f"Discovery took {elapsed:.1f}s — must be < 15s.\n"
        f"Phase 1 must NOT run deep Playwright extraction. "
        f"Use lightweight HTML fetch + URL pattern clustering only."
    )
    assert 'patterns' in result, (
        "Result must contain 'patterns' key with URL template clusters"
    )
    assert isinstance(result['patterns'], list), (
        "'patterns' must be a list of pattern dicts"
    )
    assert len(result['patterns']) > 0, (
        "Expected at least one URL pattern on harpersbazaar.com "
        "(e.g. /fashion/:slug, /beauty/:slug)"
    )

    # Pattern dict structure
    first = result['patterns'][0]
    assert 'template' in first, "Each pattern needs a 'template' field (e.g. '/:section/:slug')"
    assert 'count' in first,    "Each pattern needs a 'count' field"
    assert 'examples' in first, "Each pattern needs an 'examples' list"

    print(f"\n  ✅ Discovery: {elapsed:.1f}s, {len(result['patterns'])} patterns found")
    for p in result['patterns'][:3]:
        print(f"     {p['template']} ({p['count']} URLs) — e.g. {p['examples'][0]}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. UNIT TESTS FOR _check_page_stability
#    These pass right now — they test the method we just implemented.
# ═══════════════════════════════════════════════════════════════════════════

def make_stable_page():
    """Mock page that returns identical snapshots — stable."""
    page = MagicMock()
    snapshot = {
        'totalVisible': 150,
        'textNodeCount': 80,
        'headingCount': 6,
        'imageCount': 12,
        'buttonCount': 8,
    }
    page.evaluate = AsyncMock(return_value=snapshot)
    return page


def make_unstable_page(delta_elements=40, delta_text=30, delta_headings=2):
    """Mock page that returns different snapshots — unstable."""
    page = MagicMock()
    snap_a = {
        'totalVisible': 150,
        'textNodeCount': 80,
        'headingCount': 6,
        'imageCount': 12,
        'buttonCount': 8,
    }
    snap_b = {
        'totalVisible': 150 + delta_elements,
        'textNodeCount': 80 + delta_text,
        'headingCount': 6 + delta_headings,
        'imageCount': 12,
        'buttonCount': 8,
    }
    call_count = {'n': 0}

    async def _evaluate(script, *args, **kwargs):
        call_count['n'] += 1
        return snap_a if call_count['n'] == 1 else snap_b

    page.evaluate = AsyncMock(side_effect=_evaluate)
    return page


class TestPageStabilityCheck:

    async def test_stable_page_returns_stable_true(self):
        """Identical snapshots → stable=True, ratio=1.0."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        page = make_stable_page()
        with patch('asyncio.sleep', new=AsyncMock()):  # skip the 2s wait
            result = await engine._check_page_stability(page)

        assert result['stable'] is True
        assert result['ratio'] == 1.0
        assert result['signals'] == []
        assert result['checked'] is True

    async def test_large_element_delta_is_unstable(self):
        """A 27% element count change (150 → 190) should be flagged as unstable."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        page = make_unstable_page(delta_elements=40, delta_text=0, delta_headings=0)
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await engine._check_page_stability(page)

        assert result['stable'] is False
        assert result['ratio'] < 0.90
        assert any('element' in s for s in result['signals'])

    async def test_heading_change_signals_ab_test(self):
        """Heading count changing between snapshots is flagged specifically."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        page = make_unstable_page(delta_elements=0, delta_text=0, delta_headings=3)
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await engine._check_page_stability(page)

        assert any('heading' in s.lower() for s in result['signals'])

    async def test_snapshots_present_in_result(self):
        """Both snapshot_a and snapshot_b are present in the return value."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        page = make_stable_page()
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await engine._check_page_stability(page)

        assert 'snapshot_a' in result
        assert 'snapshot_b' in result
        assert result['snapshot_a']['visible_elements'] == 150

    async def test_evaluate_failure_returns_safe_default(self):
        """If page.evaluate() throws, returns stable=True (fail-safe)."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=RuntimeError("CDP error"))

        with patch('asyncio.sleep', new=AsyncMock()):
            result = await engine._check_page_stability(page)

        assert result['checked'] is False
        assert result['stable'] is True   # fail-safe: don't downgrade on error
        assert 'error' in result


class TestStabilityDowngrade:

    def test_stable_page_no_downgrade(self):
        """_apply_stability_downgrade is a no-op when stable=True."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {
            'typography': {'confidence': 90, 'pattern': 'Inter'},
            'colors':     {'confidence': 75, 'palette': {}},
        }
        stability = {'stable': True, 'ratio': 1.0, 'signals': [], 'checked': True}

        result = engine._apply_stability_downgrade(evidence, stability)
        assert result['typography']['confidence'] == 90
        assert result['colors']['confidence'] == 75

    def test_unchecked_stability_no_downgrade(self):
        """If checked=False (evaluation failed), no downgrade is applied."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {'typography': {'confidence': 90, 'pattern': 'Inter'}}
        stability = {'stable': False, 'ratio': 0.70, 'signals': ['x'], 'checked': False}

        result = engine._apply_stability_downgrade(evidence, stability)
        assert result['typography']['confidence'] == 90

    def test_unstable_page_reduces_confidence(self):
        """ratio=0.80 → 20pt downgrade on all metrics."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {
            'typography': {'confidence': 90, 'pattern': 'Inter'},
            'colors':     {'confidence': 70, 'palette': {}},
        }
        stability = {
            'stable': False, 'ratio': 0.80,
            'signals': ['element count shifted'], 'checked': True,
        }

        result = engine._apply_stability_downgrade(evidence, stability)
        # ratio 0.80 → (1-0.80)*100 = 20 pts
        assert result['typography']['confidence'] == 70
        assert result['colors']['confidence'] == 50

    def test_downgrade_annotates_provenance(self):
        """Each downgraded metric gets a _provenance.stability_downgrade annotation."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {'typography': {'confidence': 80, 'pattern': 'Inter'}}
        stability = {
            'stable': False, 'ratio': 0.85,
            'signals': ['rotating banner'], 'checked': True,
        }

        result = engine._apply_stability_downgrade(evidence, stability)
        prov = result['typography'].get('_provenance', {})
        assert 'stability_downgrade' in prov
        assert prov['stability_downgrade']['ratio'] == 0.85

    def test_confidence_never_goes_below_zero(self):
        """Downgrade is capped so confidence doesn't go negative."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {'colors': {'confidence': 10, 'palette': {}}}
        stability = {
            'stable': False, 'ratio': 0.50,
            'signals': ['everything changed'], 'checked': True,
        }

        result = engine._apply_stability_downgrade(evidence, stability)
        assert result['colors']['confidence'] >= 0

    def test_non_metric_keys_are_skipped(self):
        """Keys without 'confidence' (meta_info, scan_timing) are not touched."""
        from deep_evidence_engine import DeepEvidenceEngine
        engine = DeepEvidenceEngine.__new__(DeepEvidenceEngine)

        evidence = {
            'typography': {'confidence': 80, 'pattern': 'Inter'},
            'meta_info':  {'url': 'https://example.com', 'page_type': 'landing'},
            'scan_timing': {'total_seconds': 42.1},
        }
        stability = {
            'stable': False, 'ratio': 0.80,
            'signals': ['text changed'], 'checked': True,
        }

        result = engine._apply_stability_downgrade(evidence, stability)
        assert result['meta_info'] == {'url': 'https://example.com', 'page_type': 'landing'}
        assert result['scan_timing'] == {'total_seconds': 42.1}


# ═══════════════════════════════════════════════════════════════════════════
# 3. UNIT TESTS FOR PROVENANCE MODULE
# ═══════════════════════════════════════════════════════════════════════════

class TestProvenanceModule:

    def test_tag_attaches_provenance_block(self):
        from extractors.provenance import tag, Source
        result = tag({'confidence': 85, 'pattern': 'Inter'}, source=Source.COMPUTED_STYLE)
        assert '_provenance' in result
        assert result['_provenance']['source'] == Source.COMPUTED_STYLE
        assert result['_provenance']['verified'] is False

    def test_tag_extra_fields_pass_through(self):
        from extractors.provenance import tag, Source
        result = tag({}, source=Source.CSS_VAR, method='--font-family', token_count=12)
        assert result['_provenance']['method'] == '--font-family'
        assert result['_provenance']['token_count'] == 12

    def test_mark_inferred_sets_source(self):
        from extractors.provenance import mark_inferred, Source
        result = mark_inferred({'confidence': 40}, "No font-face found, guessed from stack")
        assert result['_provenance']['source'] == Source.INFERRED
        assert 'inferred_reason' in result['_provenance']

    def test_mark_validated_sets_verified(self):
        from extractors.provenance import mark_validated
        result = mark_validated(
            {'confidence': 85},
            method='style_override_pixel_compare',
            original_confidence=60,
        )
        assert result['_provenance']['verified'] is True
        assert result['_provenance']['pre_validation_confidence'] == 60

    def test_get_source_label_computed(self):
        from extractors.provenance import tag, Source, get_source_label
        result = tag({}, source=Source.COMPUTED_STYLE)
        assert get_source_label(result) == 'computed'

    def test_get_source_label_verified(self):
        from extractors.provenance import tag, Source, get_source_label
        result = tag({}, source=Source.DOM_EXTRACTION, verified=True)
        assert '✓' in get_source_label(result)

    def test_get_source_label_empty_if_no_provenance(self):
        from extractors.provenance import get_source_label
        assert get_source_label({'confidence': 80}) == ''
