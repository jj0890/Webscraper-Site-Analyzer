"""
Tests for Guided Tour synthesis — _classify_stop_type, _extract_tour_typography,
and _synthesize_tour_bundle.  All purely unit tests; no network calls.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from app import _classify_stop_type, _extract_tour_typography, _synthesize_tour_bundle

BASE = 'https://cinemarchives.com.br'

# ── _classify_stop_type ───────────────────────────────────────────────────────

class TestClassifyStopType:
    def _ev(self, page_type='', density=None):
        ev = {}
        if page_type:
            ev['meta_info'] = {'page_type': page_type}
        if density is not None:
            ev['spatial_composition'] = {
                'whitespace_analysis': {'content_density_pct': density}
            }
        return ev

    def test_home_label_is_homepage(self):
        assert _classify_stop_type('home', BASE, {}, BASE) == 'homepage'

    def test_home_url_path_is_homepage(self):
        assert _classify_stop_type('nav_1', BASE + '/', {}, BASE) == 'homepage'

    def test_single_article_page_type(self):
        ev = self._ev(page_type='singleArticle')
        assert _classify_stop_type('nav_1', BASE + '/some-article', ev, BASE) == 'reading'

    def test_pages_url_segment(self):
        url = BASE + '/magazines/presence/issues/n-1/pages/1'
        assert _classify_stop_type('nav_1', url, {}, BASE) == 'reading'

    def test_article_url_segment(self):
        url = BASE + '/article/my-essay'
        assert _classify_stop_type('nav_1', url, {}, BASE) == 'reading'

    def test_magazines_url_segment(self):
        url = BASE + '/magazines/presence-du-cinema'
        assert _classify_stop_type('nav_1', url, {}, BASE) == 'listing'

    def test_issues_url_segment(self):
        url = BASE + '/magazines/presence/issues/n-1'
        assert _classify_stop_type('nav_1', url, {}, BASE) == 'listing'

    def test_category_url_segment(self):
        url = BASE + '/category/editorial'
        assert _classify_stop_type('nav_1', url, {}, BASE) == 'listing'

    def test_high_density_falls_back_to_reading(self):
        ev = self._ev(density=62.0)
        url = BASE + '/unknown-path'
        assert _classify_stop_type('nav_1', url, ev, BASE) == 'reading'

    def test_low_density_stays_surface(self):
        ev = self._ev(density=28.0)
        url = BASE + '/about'
        assert _classify_stop_type('nav_1', url, ev, BASE) == 'surface'

    def test_no_evidence_unknown_url(self):
        # Should not crash — return 'surface' as safe default
        result = _classify_stop_type('nav_1', BASE + '/contact', {}, BASE)
        assert result in ('surface', 'listing', 'reading', 'homepage')


# ── _extract_tour_typography ──────────────────────────────────────────────────

READING_EV = {
    'typography': {
        'body_fonts':    ['Crimson Pro, serif'],
        'display_fonts': ['Playfair Display, serif'],
        'fonts':         ['Crimson Pro, serif', 'Playfair Display, serif'],
        'type_scale': {
            'ratio': 1.333,
            'sizes_px': [14.0, 18.0, 24.0, 32.0],
            'heading_sizes_px': [32.0, 24.0],
        },
        'details': {'line_height_ratio': 1.6},
    }
}

SURFACE_EV = {
    'typography': {
        'body_fonts':    ['Inter, sans-serif'],
        'display_fonts': ['Playfair Display, serif'],
        'heading_fonts': ['Playfair Display, serif'],
        'fonts':         ['Playfair Display, serif', 'Inter, sans-serif'],
        'type_scale': {
            'ratio': 1.414,
            'sizes_px': [16.0, 24.0, 48.0, 72.0],
            'heading_sizes_px': [72.0, 48.0],
        },
    }
}

class TestExtractTourTypography:
    def test_reading_prefers_body_fonts(self):
        typo = _extract_tour_typography(READING_EV, 'reading')
        assert 'Crimson Pro' in (typo['font'] or '')

    def test_surface_prefers_display_fonts(self):
        typo = _extract_tour_typography(SURFACE_EV, 'surface')
        assert 'Playfair Display' in (typo['font'] or '')

    def test_body_size_is_smallest_above_12(self):
        typo = _extract_tour_typography(READING_EV, 'reading')
        assert typo['body_size_px'] == 14.0

    def test_display_size_is_max_heading(self):
        typo = _extract_tour_typography(SURFACE_EV, 'surface')
        assert typo['display_size_px'] == 72.0

    def test_type_scale_ratio_extracted(self):
        typo = _extract_tour_typography(READING_EV, 'reading')
        assert typo['type_scale_ratio'] == pytest.approx(1.333, rel=1e-3)

    def test_line_height_extracted(self):
        typo = _extract_tour_typography(READING_EV, 'reading')
        assert typo['line_height'] == pytest.approx(1.6)

    def test_empty_evidence_no_crash(self):
        typo = _extract_tour_typography({}, 'reading')
        assert typo['font'] is None
        assert typo['body_size_px'] is None

    def test_all_fonts_capped_at_4(self):
        ev = {'typography': {'fonts': ['A', 'B', 'C', 'D', 'E', 'F']}}
        typo = _extract_tour_typography(ev, 'surface')
        assert len(typo['all_fonts']) <= 4


# ── _synthesize_tour_bundle ───────────────────────────────────────────────────

def _make_stop(url, page_type, density, fonts, body_fonts=None):
    return {
        'meta_info': {'url': url, 'page_type': page_type},
        'spatial_composition': {'whitespace_analysis': {'content_density_pct': density}},
        'typography': {
            'fonts': fonts,
            'body_fonts': body_fonts or fonts,
            'type_scale': {'ratio': 1.25, 'sizes_px': [14.0, 18.0, 24.0], 'heading_sizes_px': [24.0]},
        },
        '_meta': {'overall_confidence': 78},
    }

SMART_NAV_EVIDENCE = {
    'page_results': {
        'home':  _make_stop(BASE + '/',
                            'landingPage', 24.4,
                            ['Playfair Display, serif'], body_fonts=['Playfair Display, serif']),
        'nav_1': _make_stop(BASE + '/magazines/presence-du-cinema',
                            'contentGrid',  73.3,
                            ['Playfair Display, serif']),
        'nav_2': _make_stop(BASE + '/magazines/presence/issues/n-1/pages/1',
                            'singleArticle', 35.1,
                            ['Crimson Pro, serif'], body_fonts=['Crimson Pro, serif']),
    },
    'design_system_consistency': {'overall_consistency_score': 0.85},
}

class TestSynthesizeTourBundle:
    def test_returns_site_domain(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        assert bundle['site'] == 'cinemarchives.com.br'

    def test_three_tour_stops(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        assert len(bundle['tour_stops']) == 3

    def test_home_stop_classified_homepage(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        home = next(s for s in bundle['tour_stops'] if s['label'] == 'home')
        assert home['type'] == 'homepage'

    def test_pages_url_classified_reading(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        reading = next((s for s in bundle['tour_stops'] if s['type'] == 'reading'), None)
        assert reading is not None
        assert 'pages' in reading['url']

    def test_magazines_url_classified_listing(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        listing = next((s for s in bundle['tour_stops'] if s['type'] == 'listing'), None)
        assert listing is not None

    def test_reading_typography_uses_article_stop(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        rt = bundle['reading_typography']
        assert rt is not None
        assert 'Crimson Pro' in (rt['font'] or '')

    def test_surface_typography_uses_homepage_stop(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        st = bundle['surface_typography']
        assert st is not None
        assert 'Playfair' in (st['font'] or '')

    def test_density_shift_computed(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        ds = bundle['density_shift']
        assert ds is not None
        # Home=24.4 and listing=73.3 → surface_avg; article=35.1 → reading_avg
        # Surface stops: home(24.4) + listing(73.3) → avg 48.85
        # Reading stop: 35.1
        assert ds['surface_avg'] is not None
        assert ds['reading_avg'] is not None

    def test_density_shift_has_interpretation(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        assert bundle['density_shift']['interpretation'] is not None

    def test_design_system_present(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        ds = bundle['design_system']
        assert 'colors' in ds
        assert 'spacing' in ds
        assert 'motion' in ds

    def test_consistency_included(self):
        bundle = _synthesize_tour_bundle(SMART_NAV_EVIDENCE, BASE)
        assert bundle['design_system']['consistency'] is not None

    def test_empty_page_results_no_crash(self):
        bundle = _synthesize_tour_bundle({'page_results': {}}, BASE)
        assert bundle['tour_stops'] == []
        assert bundle['reading_typography'] is None
        assert bundle['surface_typography'] is None
