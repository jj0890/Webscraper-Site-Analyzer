"""
Tests for consistency metric provenance.

Verifies that "100% consistent" claims always include:
  - Which pages were compared
  - How the percentage was calculated
  - What threshold defines "consistent"

Run: pytest tests/test_consistency_provenance.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from deep_evidence_engine import DeepEvidenceEngine


def make_engine():
    e = DeepEvidenceEngine.__new__(DeepEvidenceEngine)
    return e


def make_page_results(n=3, include_font=True, include_colors=True):
    """Minimal page_results with n pages for consistency calculation."""
    pages = {}
    for i in range(n):
        label = 'home' if i == 0 else f'nav_{i}'
        pages[label] = {
            'typography': {
                'fonts': ['"Playfair Display", serif'] if include_font else [],
                'type_scale': {'ratio': 1.25, 'sizes_px': [14, 18, 22]},
            } if include_font else {},
            'colors': {
                'palette': {
                    'primary': ['rgb(0, 0, 0)'],
                    'secondary': ['rgb(44, 36, 22)'],
                }
            } if include_colors else {},
            'spacing_scale': {'base_unit': '4px'},
        }
    return pages


# ═══════════════════════════════════════════════════════════════════════════
# 1. EVERY METRIC HAS PROVENANCE
# ═══════════════════════════════════════════════════════════════════════════

class TestMetricProvenance:

    def test_every_metric_has_provenance_block(self):
        """Each consistency metric must have a _provenance dict."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            assert '_provenance' in metric_data, \
                f"Metric '{metric_key}' missing _provenance block"

    def test_every_provenance_has_methodology(self):
        """Each _provenance must have a human-readable methodology string."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            prov = metric_data.get('_provenance', {})
            assert 'methodology' in prov, \
                f"Metric '{metric_key}' provenance missing methodology"
            assert isinstance(prov['methodology'], str), \
                f"Metric '{metric_key}' methodology must be a string"
            assert len(prov['methodology']) > 20, \
                f"Metric '{metric_key}' methodology too short: '{prov['methodology']}'"

    def test_every_provenance_has_pages_compared(self):
        """Each metric must list which pages were included in the comparison."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            prov = metric_data.get('_provenance', {})
            assert 'pages_compared' in prov, \
                f"Metric '{metric_key}' missing pages_compared"
            assert isinstance(prov['pages_compared'], list), \
                f"Metric '{metric_key}' pages_compared must be a list"
            assert len(prov['pages_compared']) >= 2, \
                f"Metric '{metric_key}' must compare at least 2 pages"

    def test_pages_compared_matches_valid_pages(self):
        """pages_compared must reflect the actual pages used, not include errored pages."""
        page_results = make_page_results(3)
        page_results['broken'] = {'error': 'scan failed'}  # should be excluded
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            prov = metric_data.get('_provenance', {})
            compared = prov.get('pages_compared', [])
            assert 'broken' not in compared, \
                f"Metric '{metric_key}' should not include errored 'broken' page in compared list"

    def test_every_provenance_has_threshold(self):
        """What counts as 'consistent'? Must be documented per-metric."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            prov = metric_data.get('_provenance', {})
            assert 'consistent_threshold' in prov, \
                f"Metric '{metric_key}' missing consistent_threshold"

    def test_provenance_source_is_synthesized(self):
        """Consistency is computed, not observed — source must be 'synthesized'."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        for metric_key, metric_data in result['metrics'].items():
            prov = metric_data.get('_provenance', {})
            assert prov.get('source') == 'synthesized', \
                f"Metric '{metric_key}' source must be 'synthesized', got {prov.get('source')}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. TOP-LEVEL REPORT PROVENANCE
# ═══════════════════════════════════════════════════════════════════════════

class TestReportProvenance:

    def test_overall_provenance_exists(self):
        """The top-level consistency report must have _provenance."""
        result = make_engine()._calculate_design_system_variance(make_page_results(3))
        assert '_provenance' in result, "Consistency report missing top-level _provenance"

    def test_overall_method_documents_aggregation(self):
        """overall_method must name the aggregation strategy."""
        result = make_engine()._calculate_design_system_variance(make_page_results(3))
        prov = result.get('_provenance', {})
        assert 'overall_method' in prov, "Missing overall_method in report provenance"
        method = prov['overall_method'].lower()
        assert 'arithmetic mean' in method or 'average' in method or 'mean' in method, \
            f"overall_method should name the aggregation, got: {prov['overall_method']}"

    def test_report_provenance_lists_all_pages(self):
        """Top-level provenance must list all pages compared."""
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        prov = result.get('_provenance', {})
        assert 'pages_compared' in prov, "Top-level provenance missing pages_compared"
        assert isinstance(prov['pages_compared'], list)
        assert len(prov['pages_compared']) == 3

    def test_report_provenance_lists_metrics_checked(self):
        """Top-level provenance must name which metrics contributed to the score."""
        result = make_engine()._calculate_design_system_variance(make_page_results(3))
        prov = result.get('_provenance', {})
        assert 'metrics_checked' in prov, "Missing metrics_checked in report provenance"
        assert isinstance(prov['metrics_checked'], list)
        assert len(prov['metrics_checked']) >= 1

    def test_metrics_checked_matches_actual_metrics(self):
        """metrics_checked should match the actual keys in result['metrics']."""
        result = make_engine()._calculate_design_system_variance(make_page_results(3))
        prov = result.get('_provenance', {})
        reported = set(prov.get('metrics_checked', []))
        actual   = set(result['metrics'].keys())
        assert reported == actual, \
            f"metrics_checked {reported} doesn't match actual metrics {actual}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestConsistencyEdgeCases:

    def test_insufficient_pages_returns_graceful_message(self):
        """With only 1 valid page, consistency can't be computed — says so clearly."""
        page_results = {'home': make_page_results(1)['home']}
        result = make_engine()._calculate_design_system_variance(page_results)
        assert 'verdict' in result
        assert 'insufficient' in result['verdict'].lower() or 'need' in result['verdict'].lower(), \
            f"Should explain insufficient data, got: {result['verdict']}"

    def test_all_errored_pages_returns_graceful_message(self):
        """All pages errored — no metrics computed, graceful output."""
        page_results = {
            'home': {'error': 'scan failed'},
            'nav_1': {'error': 'bot blocked'},
        }
        result = make_engine()._calculate_design_system_variance(page_results)
        assert 'verdict' in result, "Must always return a verdict"
        # Should not crash
        assert result['overall_consistency_score'] == 0 or 'insufficient' in result['verdict'].lower()

    def test_perfect_100_score_claims_not_without_evidence(self):
        """
        100% score must be backed by real page comparison data (pages_compared list),
        not just asserted. This prevents false confidence from empty metrics dicts.
        """
        page_results = make_page_results(3)
        result = make_engine()._calculate_design_system_variance(page_results)
        if result['overall_consistency_score'] == 100.0:
            prov = result.get('_provenance', {})
            compared = prov.get('pages_compared', [])
            assert len(compared) >= 2, \
                "100% consistency must be backed by comparing at least 2 pages"

    def test_varying_fonts_reduces_consistency_score(self):
        """Different fonts across pages should produce score < 100%."""
        page_results = {
            'home': {
                'typography': {'fonts': ['"Playfair Display", serif']},
                'colors': {'palette': {'primary': ['rgb(0,0,0)']}},
                'spacing_scale': {'base_unit': '4px'},
            },
            'nav_1': {
                'typography': {'fonts': ['"Inter", sans-serif']},   # different!
                'colors': {'palette': {'primary': ['rgb(0,0,0)']}},
                'spacing_scale': {'base_unit': '4px'},
            }
        }
        result = make_engine()._calculate_design_system_variance(page_results)
        font_metric = result['metrics'].get('primary_font', {})
        if font_metric:
            assert font_metric['consistency_pct'] < 100, \
                "Different fonts should reduce font consistency below 100%"
