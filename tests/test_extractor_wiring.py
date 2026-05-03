"""
Extractor Wiring Regression Tests
===================================
Prevents the class of bug where an extractor is added to ALL_EXTRACTORS
(or any registration list) but is never actually invoked during analysis.

Test history:
  BrandPersonalityExtractor — was in ALL_EXTRACTORS since Apr 2026 but
  DeepEvidenceEngine never called it. Caught manually during Dazed scan.
  This test suite would have caught it immediately.
"""

import ast
import sys
import os
import inspect
import pytest

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Architecture note
# -----------------
# DeepEvidenceEngine has TWO tiers of extractors:
#
#   TIER 1 — Inline DEE methods (_extract_typography, _extract_colors, etc.)
#            These are the core extractors implemented directly in DEE.
#            ALL_EXTRACTORS contains class-based equivalents that exist as
#            standalone modules but are NOT the ones DEE calls. DEE's inline
#            versions are the live implementation.
#
#   TIER 2 — Specialist extractor classes explicitly imported and called in
#            DEE (BrandPersonalityExtractor, CSSAnalyticsExtractor, etc.).
#            These MUST be explicitly invoked in _analyze_single_page().
#            This is where the BrandPersonalityExtractor bug lived.
#
# The wiring tests below guard Tier 2.
# ---------------------------------------------------------------------------

# Extractors that DEE must explicitly import + instantiate.
# Add to this list whenever you create a new Tier-2 extractor class.
TIER2_EXTRACTORS = [
    'BrandPersonalityExtractor',  # cross-dep: needs colors, typography, motion
    'CSSAnalyticsExtractor',      # CSS authoring patterns + DTCG tokens
    'CSSEfficiencyExtractor',     # CDP rule coverage
    'CSSSpecificityExtractor',    # cascade health
    'CdpAnimationExtractor',      # runtime JS animations via CDP
    'AxeContrastExtractor',       # WCAG AA contrast via axe-core
    'AccessibilityTreeExtractor', # ARIA tree, landmarks, headings
]


def _get_dee_source() -> str:
    import deep_evidence_engine
    return inspect.getsource(deep_evidence_engine)


def test_tier2_extractors_imported_in_dee():
    """
    Every Tier-2 extractor class must be referenced (imported) in DEE.

    This catches the BrandPersonalityExtractor pattern: class existed,
    was in ALL_EXTRACTORS, but DEE never imported or called it.
    """
    dee_source = _get_dee_source()
    missing = [name for name in TIER2_EXTRACTORS if name not in dee_source]
    assert not missing, (
        f"These Tier-2 extractors are not referenced in deep_evidence_engine.py:\n"
        + "\n".join(f"  - {name}" for name in missing)
        + "\n\nThey will silently never run. Add an explicit call in "
        "_analyze_single_page(), or remove from TIER2_EXTRACTORS if retired."
    )


def test_tier2_extractors_instantiated_in_dee():
    """
    Every Tier-2 extractor must be INSTANTIATED (ClassName()) in DEE,
    not just imported. Import without instantiation = still dead.
    """
    dee_source = _get_dee_source()
    missing = [name for name in TIER2_EXTRACTORS if f'{name}()' not in dee_source]
    assert not missing, (
        f"These Tier-2 extractors are imported but never instantiated in DEE:\n"
        + "\n".join(f"  - {name}()" for name in missing)
    )


# ---------------------------------------------------------------------------
# 2. Static check: every extractor class in ALL_EXTRACTORS has a unique
#    .name attribute so evidence keys don't collide
# ---------------------------------------------------------------------------

def test_all_extractor_names_are_unique():
    """No two extractors should write to the same evidence key."""
    from extractors import ALL_EXTRACTORS
    names = [cls.name for cls in ALL_EXTRACTORS if hasattr(cls, 'name')]
    duplicates = [n for n in set(names) if names.count(n) > 1]
    assert not duplicates, (
        f"Duplicate extractor evidence keys: {duplicates}. "
        "Two extractors writing to the same key will silently overwrite each other."
    )


# ---------------------------------------------------------------------------
# 3. Static check: SpatialZone dict emits both the canonical keys
#    (name, element_count) that all consumers expect
# ---------------------------------------------------------------------------

def test_spatial_zone_emits_canonical_keys():
    """
    _detect_component_zones() must return dicts with both 'name' and
    'element_count' keys. Callers (dashboard, API, DESIGN.md export) rely
    on these. The internal 'type' / 'elements_inside' aliases are fine to
    keep for backward compat but the canonical keys must be present.
    """
    import inspect
    from spatial_composition_analyzer import SpatialCompositionAnalyzer

    src = inspect.getsource(SpatialCompositionAnalyzer._detect_component_zones)
    assert "'name'" in src or '"name"' in src, (
        "_detect_component_zones() must include a 'name' key in zone dicts"
    )
    assert "'element_count'" in src or '"element_count"' in src, (
        "_detect_component_zones() must include an 'element_count' key in zone dicts"
    )


# ---------------------------------------------------------------------------
# 4. Static check: color helper in BrandPersonalityExtractor supports rgb()
#    (regression for the hex-only parser that broke Dazed's dark bg detection)
# ---------------------------------------------------------------------------

def test_brand_personality_color_parser_handles_rgb():
    """_parse_color() must handle rgb() strings, not just hex."""
    from extractors.brand_personality import BrandPersonalityExtractor
    bp = BrandPersonalityExtractor()

    # Pure black as rgb() — what browsers return
    assert bp._parse_color('rgb(0, 0, 0)') == (0, 0, 0)
    # Pure white
    assert bp._parse_color('rgb(255, 255, 255)') == (255, 255, 255)
    # Hex still works
    assert bp._parse_color('#000000') == (0, 0, 0)
    # rgba()
    r, g, b = bp._parse_color('rgba(33, 41, 52, 0.75)')
    assert (r, g, b) == (33, 41, 52)
    # Dark color detection on rgb() input (was the actual bug)
    assert bp._is_dark_color('rgb(0, 0, 0)') is True
    assert bp._is_dark_color('rgb(255, 255, 255)') is False


# ---------------------------------------------------------------------------
# 5. Static check: brand_personality extractor is imported and called
#    in deep_evidence_engine.py (specific regression for the wiring miss)
# ---------------------------------------------------------------------------

def test_brand_personality_extractor_is_called_in_dee():
    """
    Regression test for the specific BrandPersonalityExtractor miss.
    Ensures future refactors don't silently drop the brand personality call.
    """
    dee_source = _get_dee_source()
    assert 'BrandPersonalityExtractor' in dee_source, (
        "BrandPersonalityExtractor is not referenced in deep_evidence_engine.py. "
        "Brand personality will silently return None for all sites."
    )
    # And it must actually be instantiated/called, not just imported
    assert 'BrandPersonalityExtractor()' in dee_source, (
        "BrandPersonalityExtractor is imported but never instantiated. "
        "It must be called in _analyze_single_page()."
    )


# ---------------------------------------------------------------------------
# 6. Vulture-style check: confirm no obvious unused imports in core files
#    (runs vulture programmatically so it's part of the test suite)
# ---------------------------------------------------------------------------

def test_no_dead_code_in_core_files():
    """
    Run vulture on core files and fail if any high-confidence (≥80%) dead
    code is found. Excludes test files and examples.
    """
    try:
        import vulture as vlt
    except ImportError:
        pytest.skip("vulture not installed — run: pip install vulture")

    import subprocess, json
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = [
        'deep_evidence_engine.py',
        'app.py',
        'extractors/brand_personality.py',
        'extractors/typography.py',
        'spatial_composition_analyzer.py',
        'mcp_entrypoint.py',
    ]
    targets = [os.path.join(project_root, t) for t in targets]

    result = subprocess.run(
        [sys.executable, '-m', 'vulture'] + targets + ['--min-confidence', '80'],
        capture_output=True, text=True, cwd=project_root
    )

    issues = [line for line in result.stdout.splitlines() if line.strip()]
    # Exit code 0 = no issues, 1 = error, 3 = dead code found
    if result.returncode == 3 and issues:
        pytest.fail(
            f"Vulture found {len(issues)} dead code issue(s) in core files:\n"
            + "\n".join(f"  {i}" for i in issues)
        )
