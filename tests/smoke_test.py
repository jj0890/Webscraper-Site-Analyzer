"""
Smoke test — verify the tool works end-to-end.

Usage:
    python tests/smoke_test.py          # runs against example.com
    python tests/smoke_test.py <url>    # runs against a custom URL

Passes/fails with a clear message. Takes ~10-20 seconds.
Does NOT require a running server — imports the engine directly.
"""

import asyncio
import sys
import os
import time

# Ensure the project root is on the path regardless of where this is run from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def run_smoke_test(url: str = "https://example.com") -> bool:
    print(f"\n  Smoke test → {url}")
    print("  " + "─" * 50)

    try:
        from deep_evidence_engine import DeepEvidenceEngine
    except ImportError as e:
        print(f"\n  ❌ FAIL — cannot import DeepEvidenceEngine: {e}")
        print("     Try: pip install -r requirements.txt")
        return False

    start = time.time()

    try:
        engine = DeepEvidenceEngine(url, analysis_mode='single')
        evidence = await engine.extract_all()
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ❌ FAIL ({elapsed:.1f}s) — extraction raised: {type(e).__name__}: {e}")
        return False

    elapsed = time.time() - start

    # ── Required keys ─────────────────────────────────────────────────────────
    required = ['typography', 'colors', 'spacing_scale', 'layout', 'meta_info']
    missing  = [k for k in required if k not in evidence]

    if missing:
        print(f"\n  ❌ FAIL ({elapsed:.1f}s) — missing evidence keys: {missing}")
        return False

    # ── Confidence floor: at least one metric ≥ 50% ───────────────────────────
    confidences = [
        v.get('confidence', 0)
        for v in evidence.values()
        if isinstance(v, dict) and 'confidence' in v
    ]
    max_conf = max(confidences) if confidences else 0

    if max_conf < 50:
        print(f"\n  ❌ FAIL ({elapsed:.1f}s) — max confidence {max_conf}% is too low (page may have blocked access)")
        return False

    # ── Report what we found ───────────────────────────────────────────────────
    typo  = evidence.get('typography', {})
    fonts = typo.get('fonts', typo.get('ui_fonts', []))
    if isinstance(fonts, dict):
        fonts = list(fonts.values())[:3]

    colors = evidence.get('colors', {})
    palette = colors.get('palette', {})
    color_count = sum(len(v) for v in palette.values() if isinstance(v, list)) if isinstance(palette, dict) else 0

    spacing = evidence.get('spacing_scale', {})
    spacing_vals = spacing.get('scale', spacing.get('values', []))

    meta = evidence.get('meta_info', {})

    print(f"\n  ✅ PASS ({elapsed:.1f}s)")
    print(f"     URL:        {meta.get('url', url)}")
    print(f"     Page type:  {meta.get('page_type', '?')}")
    print(f"     Fonts:      {fonts[:3] or '(none detected)'}")
    print(f"     Colors:     {color_count} in palette")
    print(f"     Spacing:    {spacing_vals[:5] or '(none detected)'}")
    print(f"     Evidence:   {len(evidence)} keys")
    print(f"     Max conf:   {max_conf}%")

    # ── Optional: component blueprint check ───────────────────────────────────
    blueprints = evidence.get('component_blueprints', {})
    ripped = blueprints.get('blueprints', []) if isinstance(blueprints, dict) else []
    if ripped:
        print(f"     Blueprints: {len(ripped)} components ripped")

    return True


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    ok = asyncio.run(run_smoke_test(target))
    sys.exit(0 if ok else 1)
