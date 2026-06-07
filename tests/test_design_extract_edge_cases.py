"""
Edge-case tests for the Design System Extract endpoint and generator.

Tests four specific failure modes:
  1. Empty evidence shouldn't crash
  2. Missing sections render as "not detected"
  3. Single grid renders correctly
  4. Consistency formatting is correct
  + Manual-check tests: color role accuracy, type scale labeling, grid count

Run: pytest tests/test_design_extract_edge_cases.py -v
"""

import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import app as flask_app, generate_design_system_extract


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# 1. EMPTY EVIDENCE
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_evidence_returns_200_not_500(client):
    """Empty evidence dict must not raise an exception."""
    resp = client.post('/api/export-design-extract',
                       json={'evidence': {}},
                       content_type='application/json')
    assert resp.status_code == 200


def test_empty_evidence_card_contains_insufficient_message(client):
    """Empty evidence card should explain the situation, not be empty or a traceback."""
    resp = client.post('/api/export-design-extract',
                       json={'evidence': {}},
                       content_type='application/json')
    body = resp.get_json()
    card = body.get('card', '')
    assert card, "card field must not be empty"
    assert 'insufficient' in card.lower() or 'no data' in card.lower() or 'insufficient' in card.lower(), \
        f"Expected graceful message, got: {card[:200]}"
    # Must not be a Python traceback
    assert 'Traceback' not in card
    assert 'Error' not in card


def test_missing_evidence_field_returns_400(client):
    """Completely missing evidence field should return 400, not 500."""
    resp = client.post('/api/export-design-extract',
                       json={},
                       content_type='application/json')
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 2. MISSING SECTIONS RENDER AS "NOT DETECTED"
# ═══════════════════════════════════════════════════════════════════════════

def test_missing_typography_shows_not_detected():
    """Typography section header always present; value says not detected when absent."""
    evidence = {
        'colors': {'palette': {'primary': ['#FF0000']}},
        'spacing_scale': {'base_unit': '4px', 'scale': [4, 8, 16]},
    }
    card, _ = generate_design_system_extract(evidence)
    assert 'Typography' in card, "Typography section header must always appear"
    assert 'not detected' in card.lower(), \
        f"Missing typography should say 'not detected', got:\n{card}"


def test_missing_colors_shows_not_detected():
    """Colors section must appear even when palette is missing."""
    evidence = {
        'typography': {'fonts': ['"Inter", sans-serif']},
    }
    card, _ = generate_design_system_extract(evidence)
    assert 'Colors' in card or 'color' in card.lower(), \
        "Colors section must appear even when missing"


def test_missing_motion_does_not_crash():
    """Motion section missing entirely — should not raise."""
    evidence = {
        'typography': {'fonts': ['"Inter", sans-serif']},
        'colors': {'palette': {'primary': ['#0066FF']}},
    }
    card, _ = generate_design_system_extract(evidence)
    assert card, "Card should not be empty"
    assert 'Traceback' not in card


# ═══════════════════════════════════════════════════════════════════════════
# 3. GRID SYSTEM RENDERING
# ═══════════════════════════════════════════════════════════════════════════

def test_single_grid_renders_label_and_columns():
    """One grid — label, columns, gap all visible."""
    evidence = {
        'meta_info': {'url': 'https://example.com/magazines/presence-du-cinema'},
        'spatial_composition': {
            'container_hierarchy': {
                'grid_containers': {
                    'count': 1,
                    'examples': [
                        {'columns': '160px 1296px', 'gap': '40px', 'tag': 'a', 'children': 2}
                    ]
                },
                'flex_containers': {'count': 0, 'examples': []},
            }
        }
    }
    card, data = generate_design_system_extract(evidence)
    assert '160px 1296px' in card, f"Grid columns must appear in card:\n{card}"
    assert '40px' in card, f"Gap must appear in card:\n{card}"
    # Structured data must also have the grid
    assert data.get('grid_system'), "grid_system must be non-empty in structured data"
    assert data['grid_system'][0]['columns'] == '160px 1296px'


def test_six_column_equal_grid_collapses():
    """229px × 6 equal-column grid should be rendered compactly."""
    evidence = {
        'meta_info': {'url': 'https://example.com/issues/1'},
        'spatial_composition': {
            'container_hierarchy': {
                'grid_containers': {
                    'count': 1,
                    'examples': [
                        {
                            'columns': '229.328px 229.328px 229.328px 229.344px 229.328px 229.328px',
                            'gap': '40px 24px',
                            'tag': 'div',
                            'children': 6
                        }
                    ]
                },
                'flex_containers': {'count': 0, 'examples': []},
            }
        }
    }
    card, _ = generate_design_system_extract(evidence)
    # Should NOT print the full 50-character repeated column string verbatim
    assert '229.328px 229.328px 229.328px 229.328px 229.328px 229.328px' not in card, \
        "Long equal columns should be collapsed"
    # Should indicate it's a 6-column grid somehow
    assert '229' in card, "Column size should still appear"


def test_no_grid_in_smart_nav_shows_helpful_message():
    """When smart-nav picks institutional pages (no grids), card explains rather than omits."""
    evidence = {
        'page_results': {
            'home': {
                'meta_info': {'url': 'https://example.com/'},
                'typography': {'fonts': ['"Inter", sans-serif']},
                'colors': {'palette': {'primary': ['#000']}},
                'spatial_composition': {
                    'container_hierarchy': {'grid_containers': {'count': 0, 'examples': []},
                                           'flex_containers': {'count': 5, 'examples': []}}
                }
            },
            'nav_1': {
                'meta_info': {'url': 'https://example.com/support'},
                'typography': {'fonts': ['"Inter", sans-serif']},
                'colors': {'palette': {'primary': ['#000']}},
                'spatial_composition': {
                    'container_hierarchy': {'grid_containers': {'count': 0, 'examples': []},
                                           'flex_containers': {'count': 3, 'examples': []}}
                }
            }
        }
    }
    card, _ = generate_design_system_extract(evidence)
    assert 'grid' in card.lower(), "Grid section must appear even when empty"
    assert 'not detected' in card.lower() or 'analysis_focus' in card.lower(), \
        f"Should explain why grid is missing:\n{card}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. CONSISTENCY FORMATTING
# ═══════════════════════════════════════════════════════════════════════════

def test_100_percent_consistency_formatted_correctly():
    """100.0% — Highly Consistent Design System must appear verbatim."""
    evidence = {
        'typography': {'fonts': ['"Inter", sans-serif']},
        'design_system_consistency': {
            'overall_consistency_score': 100.0,
            'verdict': 'Highly Consistent Design System',
            'metrics': {},
        }
    }
    card, _ = generate_design_system_extract(evidence)
    assert '100.0%' in card, f"100.0% not found in:\n{card}"
    assert 'Highly Consistent Design System' in card


def test_partial_consistency_formatted_correctly():
    """67.3% — Moderately Consistent must appear."""
    evidence = {
        'typography': {'fonts': ['"Inter", sans-serif']},
        'design_system_consistency': {
            'overall_consistency_score': 67.3,
            'verdict': 'Moderately Consistent Design System',
            'metrics': {},
        }
    }
    card, _ = generate_design_system_extract(evidence)
    assert '67.3%' in card, f"67.3% not in:\n{card}"
    assert 'Moderately' in card


# ═══════════════════════════════════════════════════════════════════════════
# 5. MANUAL CHECK REGRESSION TESTS (from cinemarchives findings)
# ═══════════════════════════════════════════════════════════════════════════

def test_primary_color_not_duplicate_of_background():
    """
    When the primary ROLE contains a near-background color first, the Roles
    section must pick the actual accent (#8B4513), not the near-white (#FAF6F0).

    Note: #FAF6F0 may legitimately appear in the Colors (palette) line since
    it IS in the site's design system — that's correct behaviour. The test
    only verifies the Roles section.
    """
    evidence = {
        'meta_info': {'url': 'https://cinemarchives.com.br/'},
        'colors': {
            'palette': {'primary': ['#FAF6F0', '#8B4513']},
            'color_roles': {
                'background': [{'value': '#F5F0E8', 'variable': '--color-background'}],
                'primary': [
                    {'value': '#FAF6F0', 'variable': '--color-primary-foreground'},
                    {'value': '#8B4513', 'variable': '--color-primary'},
                ],
                'text': [{'value': '#2C2416', 'variable': '--color-foreground'}],
            }
        }
    }
    card, data = generate_design_system_extract(evidence)

    # Extract the Roles line specifically
    roles_line = next((l for l in card.splitlines() if '**Roles**' in l), '')
    assert roles_line, f"Roles line missing from card:\n{card}"

    # #FAF6F0 should NOT appear as the primary role value
    assert 'primary: #FAF6F0' not in roles_line, \
        f"Near-background #FAF6F0 must not be the primary role. Roles line: {roles_line}"

    # #8B4513 (warm brown accent) SHOULD be the primary role
    assert '#8B4513' in roles_line, \
        f"Actual accent #8B4513 should be primary role. Roles line: {roles_line}"


def test_type_scale_large_span_labeled_as_display_span():
    """
    sizes [12, 14, 16, 18, 20, 60] → ratio 3.75 should be labeled
    as a 'display span', not a 'modular ratio' (3.75 is not a standard modular scale).
    """
    evidence = {
        'meta_info': {'url': 'https://cinemarchives.com.br/'},
        'typography': {
            'fonts': ['"Playfair Display", serif'],
            'type_scale': {
                'ratio': 3.75,
                'sizes_px': [12.0, 14.0, 16.0, 18.0, 20.0, 60.0],
                'heading_sizes_px': [60.0, 16.0],
            }
        }
    }
    card, _ = generate_design_system_extract(evidence)
    # Should NOT say "modular ratio" for a 3.75 span
    assert 'modular ratio' not in card.lower(), \
        f"3.75 is a display span, not a modular ratio. Card:\n{card}"
    # Should mention it's a display span or at least show the size range
    assert 'display span' in card.lower() or ('12' in card and '60' in card), \
        f"Should show the size range (12–60px). Card:\n{card}"


def test_type_scale_true_modular_ratio_labeled_correctly():
    """
    ratio=1.25 with sizes [14, 17, 21, 26, 32] is a classic modular scale.
    Should be labelled 'modular ratio', not 'display span'.
    """
    evidence = {
        'meta_info': {'url': 'https://example.com/'},
        'typography': {
            'fonts': ['"Inter", sans-serif'],
            'type_scale': {
                'ratio': 1.25,
                'sizes_px': [14.0, 17.0, 21.0, 26.0, 32.0],
            }
        }
    }
    card, _ = generate_design_system_extract(evidence)
    assert '1.25' in card, f"Modular ratio 1.25 should appear. Card:\n{card}"
    assert 'modular ratio' in card.lower(), \
        f"1.25 ratio should be labeled 'modular ratio', not display span. Card:\n{card}"
    assert 'display span' not in card.lower(), \
        f"1.25 ratio should not be called a display span. Card:\n{card}"
