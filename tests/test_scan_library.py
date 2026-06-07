"""
Tests for scan_library.py

Focus areas:
  1. _flatten_evidence — single-page passthrough, smart-nav merge, empty home guard
  2. _index_evidence   — flat evidence, smart-nav evidence, motion_narrative pick-up
  3. save_scan / list_scans — round-trip with smart-nav evidence (uses a tmp DB)
  4. reindex_all_scans — backfills smart-nav rows correctly
  5. search_scans       — finds rows by font, motion_strategy, confidence range
"""

import json
import os
import sys
import tempfile
import pytest

# ── Ensure repo root is on path ───────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import scan_library as lib


# ── Fixtures ──────────────────────────────────────────────────────────────────

FLAT_EVIDENCE = {
    'typography': {
        'fonts': ['Playfair Display, serif'],
    },
    'colors': {
        'palette': {
            'intentional': ['#1A1A1A'],
            'primary':     ['#FF6B35'],
            'secondary':   [],
        }
    },
    'spacing_scale': {'base_unit': '4px'},
    'motion_tokens': {
        'narrative': {
            'strategy': 'performance-conscious',
            'summary':  'Restrained motion focused on hover feedback.',
        },
        'details': {
            'duration_scale': {'values_ms': [100, 200, 300]},
        },
    },
    'spatial_composition': {
        'whitespace_analysis': {'content_density_pct': 62.5},
    },
    '_meta': {'overall_confidence': 78},
    'access_strategy': 'patchright',
    'meta_info': {'page_type': 'contentGrid'},
    'layout': {'pattern': 'multi-column'},
    'css_analytics': {'sophistication_score': 71},
}

SMART_NAV_EVIDENCE = {
    'analysis_mode': 'smart-nav',
    'access_strategy': 'patchright',
    '_meta': {'overall_confidence': 81},
    'design_system_consistency': {'overall_consistency_score': 0.87},
    'page_results': {
        'home': {
            'typography': {
                'fonts': ['Inter, sans-serif'],
            },
            'colors': {
                'palette': {
                    'intentional': ['#000000'],
                    'primary':     ['#0055FF'],
                    'secondary':   [],
                }
            },
            'spacing_scale': {'base_unit': '8px'},
            'motion_tokens': {
                'narrative': {
                    'strategy': 'minimal',
                    'summary':  'No detectable motion.',
                },
                'details': {'duration_scale': {'values_ms': []}},
            },
            'spatial_composition': {
                'whitespace_analysis': {'content_density_pct': 48.0},
            },
            '_meta': {'overall_confidence': 79},   # overridden by top-level
            'meta_info': {'page_type': 'landingPage'},
            'layout': {'pattern': 'hero-first'},
            'css_analytics': {'sophistication_score': 84},
        },
        'nav_1': {
            'typography': {'fonts': ['Inter, sans-serif']},
        },
    },
}


# ── Redirect DB to a temp file for isolation ──────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Point scan_library at a fresh temp DB for every test."""
    db_path = str(tmp_path / 'test_lib.db')
    monkeypatch.setattr(lib, '_DB_PATH', db_path)
    yield db_path


# ── 1. _flatten_evidence ──────────────────────────────────────────────────────

class TestFlattenEvidence:
    def test_single_page_passthrough(self):
        result = lib._flatten_evidence(FLAT_EVIDENCE)
        assert result is FLAT_EVIDENCE        # identical object, no copy

    def test_smart_nav_exposes_home_fonts(self):
        result = lib._flatten_evidence(SMART_NAV_EVIDENCE)
        assert 'typography' in result
        assert result['typography']['fonts'] == ['Inter, sans-serif']

    def test_smart_nav_top_level_overrides_home(self):
        """Top-level _meta (overall_confidence=81) must win over home _meta (79)."""
        result = lib._flatten_evidence(SMART_NAV_EVIDENCE)
        assert result['_meta']['overall_confidence'] == 81

    def test_smart_nav_top_level_access_strategy(self):
        result = lib._flatten_evidence(SMART_NAV_EVIDENCE)
        assert result['access_strategy'] == 'patchright'

    def test_smart_nav_excludes_page_results_key(self):
        result = lib._flatten_evidence(SMART_NAV_EVIDENCE)
        assert 'page_results' not in result

    def test_smart_nav_consistency_present(self):
        result = lib._flatten_evidence(SMART_NAV_EVIDENCE)
        assert 'design_system_consistency' in result

    def test_empty_home_returns_original(self):
        evidence = {'page_results': {'home': {}}, 'analysis_mode': 'smart-nav'}
        result = lib._flatten_evidence(evidence)
        # home is empty → can't merge, return original
        assert result is evidence

    def test_missing_home_returns_original(self):
        evidence = {'page_results': {}, 'analysis_mode': 'smart-nav'}
        result = lib._flatten_evidence(evidence)
        assert result is evidence


# ── 2. _index_evidence ────────────────────────────────────────────────────────

class TestIndexEvidence:
    def test_flat_font_extraction(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['primary_font'] == 'Playfair Display'

    def test_flat_color_extraction(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['primary_color'] == '#1A1A1A'

    def test_flat_spacing_extraction(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['spacing_base_unit'] == '4px'

    def test_flat_motion_strategy(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['motion_strategy'] == 'performance-conscious'

    def test_flat_density(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['content_density_pct'] == pytest.approx(62.5)

    def test_flat_page_type(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['page_type'] == 'contentGrid'

    def test_flat_css_sophistication(self):
        idx = lib._index_evidence(FLAT_EVIDENCE)
        assert idx['css_sophistication'] == 71

    # Smart-nav tests
    def test_smart_nav_font(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['primary_font'] == 'Inter'

    def test_smart_nav_color(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['primary_color'] == '#000000'

    def test_smart_nav_motion_strategy(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['motion_strategy'] == 'minimal'

    def test_smart_nav_spacing(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['spacing_base_unit'] == '8px'

    def test_smart_nav_page_type(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['page_type'] == 'landingPage'

    def test_smart_nav_consistency_score(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['consistency_score'] == pytest.approx(0.87)

    def test_smart_nav_css_sophistication(self):
        idx = lib._index_evidence(SMART_NAV_EVIDENCE)
        assert idx['css_sophistication'] == 84

    def test_no_motion_narrative_falls_back_to_inferred(self):
        # No narrative → _infer_motion_strategy is called.
        # Empty duration_scale means 'minimal' (no motion detected).
        ev = {**FLAT_EVIDENCE, 'motion_tokens': {'details': {}}}
        idx = lib._index_evidence(ev)
        assert idx['motion_strategy'] == 'minimal'

    def test_inferred_strategy_layered_from_durations(self):
        ev = {**FLAT_EVIDENCE, 'motion_tokens': {
            'details': {'duration_scale': {'values_ms': [100, 200, 400, 600]}}
        }}
        idx = lib._index_evidence(ev)
        assert idx['motion_strategy'] == 'layered'

    def test_empty_evidence_no_crash(self):
        idx = lib._index_evidence({})
        assert idx['primary_font'] is None
        assert idx['primary_color'] is None
        # Empty evidence → no motion → 'minimal' via _infer_motion_strategy
        assert idx['motion_strategy'] == 'minimal'


# ── 3. save_scan / list_scans round-trip ─────────────────────────────────────

class TestSaveScan:
    def test_flat_scan_saves_and_lists(self):
        scan_id = lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        rows = lib.list_scans()
        assert len(rows) == 1
        assert rows[0]['id'] == scan_id
        assert rows[0]['primary_font'] == 'Playfair Display'
        assert rows[0]['motion_strategy'] == 'performance-conscious'
        assert rows[0]['overall_confidence'] == 78

    def test_smart_nav_scan_saves_correctly(self):
        scan_id = lib.save_scan(
            'https://cinemarchives.com.br/',
            SMART_NAV_EVIDENCE,
            'smart-nav',
        )
        rows = lib.list_scans()
        assert len(rows) == 1
        r = rows[0]
        assert r['primary_font'] == 'Inter'          # from home
        assert r['motion_strategy'] == 'minimal'      # from home narrative
        assert r['overall_confidence'] == 81          # from top-level _meta
        assert r['spacing_base_unit'] == '8px'

    def test_smart_nav_domain_correctly_extracted(self):
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        rows = lib.list_scans(domain='cinemarchives.com.br')
        assert len(rows) == 1

    def test_multiple_scans_accumulate(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        rows = lib.list_scans()
        assert len(rows) == 2


# ── 4. reindex_all_scans ──────────────────────────────────────────────────────

class TestReindex:
    def _save_raw(self, tmp_db_path, scan_id, url, evidence):
        """Insert a scan row with NULL indexed columns (simulates pre-fix state)."""
        import sqlite3, time, json
        conn = sqlite3.connect(tmp_db_path)
        conn.executescript("PRAGMA foreign_keys=ON;" + lib._SCHEMA)
        conn.execute("""
            INSERT INTO scans (id, url, domain, scanned_at, analysis_mode,
                               access_strategy, overall_confidence,
                               primary_font, all_fonts, primary_color, color_palette,
                               spacing_base_unit, motion_strategy, motion_durations,
                               content_density_pct, brand_personality, consistency_score,
                               page_type, layout_pattern, css_sophistication,
                               evidence_json, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, '[]', NULL, '[]',
                    NULL, NULL, '[]', NULL, NULL, NULL, NULL, NULL, NULL, ?, '')
        """, [scan_id, url, 'cinemarchives.com.br', time.time(), 'smart-nav',
              'patchright', None, json.dumps(evidence)])
        conn.commit()
        conn.close()

    def test_reindex_fixes_smart_nav(self, tmp_db):
        scan_id = 'test-reindex-001'
        self._save_raw(tmp_db, scan_id, 'https://cinemarchives.com.br/', SMART_NAV_EVIDENCE)

        result = lib.reindex_all_scans()
        assert result['updated'] == 1
        assert result['errors'] == 0

        rows = lib.list_scans()
        r = rows[0]
        assert r['primary_font'] == 'Inter'
        assert r['motion_strategy'] == 'minimal'
        assert r['overall_confidence'] == 81

    def test_reindex_returns_updated_count(self, tmp_db):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        result = lib.reindex_all_scans()
        assert result['updated'] == 2
        assert result['errors'] == 0

    def test_reindex_handles_corrupt_json(self, tmp_db):
        import sqlite3, time
        # Insert a row with bad JSON
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(lib._SCHEMA)
        conn.execute("""
            INSERT INTO scans (id, url, domain, scanned_at, analysis_mode,
                               access_strategy, overall_confidence,
                               primary_font, all_fonts, primary_color, color_palette,
                               spacing_base_unit, motion_strategy, motion_durations,
                               content_density_pct, brand_personality, consistency_score,
                               page_type, layout_pattern, css_sophistication,
                               evidence_json, notes)
            VALUES ('bad-row', 'https://broken.com', 'broken.com', ?, 'single',
                    NULL, NULL, NULL, '[]', NULL, '[]',
                    NULL, NULL, '[]', NULL, NULL, NULL, NULL, NULL, NULL,
                    'NOT_JSON', '')
        """, [time.time()])
        conn.commit()
        conn.close()

        result = lib.reindex_all_scans()
        assert result['errors'] == 1   # one bad row counted, others unaffected


# ── 5. search_scans ───────────────────────────────────────────────────────────

class TestSearchScans:
    def test_search_by_font(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        results = lib.search_scans({'primary_font': 'Inter'})
        assert len(results) == 1
        assert 'cinemarchives' in results[0]['url']

    def test_search_by_motion_strategy(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        results = lib.search_scans({'motion_strategy': 'minimal'})
        assert len(results) == 1

    def test_search_by_confidence_range(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')       # conf=78
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')  # conf=81
        results = lib.search_scans({'min_confidence': 80})
        assert all(r['overall_confidence'] >= 80 for r in results)
        assert len(results) == 1

    def test_search_by_domain(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        lib.save_scan('https://cinemarchives.com.br/', SMART_NAV_EVIDENCE, 'smart-nav')
        results = lib.search_scans({'domain': 'example.com'})
        assert len(results) == 1
        assert results[0]['domain'] == 'example.com'

    def test_search_no_matches(self):
        lib.save_scan('https://example.com/', FLAT_EVIDENCE, 'single')
        results = lib.search_scans({'motion_strategy': 'expressive'})
        assert results == []
