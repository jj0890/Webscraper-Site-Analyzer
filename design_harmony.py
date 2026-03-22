"""
Design Harmony Analyzer — Mathematical scale detection for confidence boosting.

Reverse-engineers whether a site's typography, spacing, and color follow
consistent mathematical ratios (inspired by LiftKit's golden-ratio system).

Does NOT add a new metric card — instead returns confidence adjustments
that get folded into existing metric scores.

Known scales:
    1.067  Minor Second
    1.125  Major Second (tailwind default)
    1.200  Minor Third
    1.250  Major Third (most common on the web)
    1.333  Perfect Fourth
    1.414  Augmented Fourth
    1.500  Perfect Fifth
    1.618  Golden Ratio (LiftKit)
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Named musical/mathematical scales
KNOWN_SCALES = [
    (1.067, 'Minor Second'),
    (1.125, 'Major Second'),
    (1.200, 'Minor Third'),
    (1.250, 'Major Third'),
    (1.333, 'Perfect Fourth'),
    (1.414, 'Augmented Fourth'),
    (1.500, 'Perfect Fifth'),
    (1.618, 'Golden Ratio'),
]

# Common spacing base units (px)
COMMON_BASE_UNITS = [4, 5, 6, 8, 10]


def detect_type_scale(font_sizes_px: List[float]) -> Dict:
    """Detect the mathematical scale ratio from a list of font sizes.

    Args:
        font_sizes_px: List of font sizes in pixels (e.g. [12, 14, 16, 20, 24, 32])

    Returns:
        {
            'detected_ratio': float,
            'scale_name': str,        # e.g. 'Major Third'
            'consistency': float,      # 0-1, how well sizes fit the scale
            'confidence_boost': int,   # 0-15 points to add to typography confidence
            'base_size': float,        # detected base font size
            'sizes_on_scale': int,     # how many sizes fit the detected scale
            'total_sizes': int,
        }
    """
    if not font_sizes_px or len(font_sizes_px) < 3:
        return {'detected_ratio': None, 'scale_name': None, 'consistency': 0,
                'confidence_boost': 0, 'base_size': None,
                'sizes_on_scale': 0, 'total_sizes': len(font_sizes_px) if font_sizes_px else 0}

    # Deduplicate and sort
    sizes = sorted(set(s for s in font_sizes_px if s > 0))
    if len(sizes) < 3:
        return {'detected_ratio': None, 'scale_name': None, 'consistency': 0,
                'confidence_boost': 0, 'base_size': None,
                'sizes_on_scale': 0, 'total_sizes': len(sizes)}

    # Compute all adjacent ratios
    ratios = []
    for i in range(len(sizes) - 1):
        if sizes[i] > 0:
            ratios.append(sizes[i + 1] / sizes[i])

    if not ratios:
        return {'detected_ratio': None, 'scale_name': None, 'consistency': 0,
                'confidence_boost': 0, 'base_size': None,
                'sizes_on_scale': 0, 'total_sizes': len(sizes)}

    # Find the best matching known scale
    best_scale = None
    best_score = 0
    best_ratio = None

    for known_ratio, name in KNOWN_SCALES:
        score = _score_scale_fit(sizes, known_ratio)
        if score > best_score:
            best_score = score
            best_scale = name
            best_ratio = known_ratio

    # Also try the median ratio (site might use a custom scale)
    median_ratio = sorted(ratios)[len(ratios) // 2]
    custom_score = _score_scale_fit(sizes, median_ratio)
    if custom_score > best_score and median_ratio > 1.03:
        best_score = custom_score
        best_ratio = round(median_ratio, 3)
        # Check if it's close to a known scale
        closest_name = _closest_scale_name(median_ratio)
        best_scale = closest_name or f'Custom ({best_ratio})'

    # Detect base size (most common body text size, typically 14-18px)
    base_candidates = [s for s in sizes if 13 <= s <= 20]
    base_size = base_candidates[0] if base_candidates else sizes[0]

    # Count how many sizes fit the detected scale
    sizes_on_scale = 0
    if best_ratio and best_ratio > 1:
        for s in sizes:
            if _is_on_scale(s, base_size, best_ratio, tolerance=0.08):
                sizes_on_scale += 1

    # Calculate confidence boost (0-15)
    confidence_boost = 0
    if best_score >= 0.8 and sizes_on_scale >= 4:
        confidence_boost = 15  # Strong mathematical scale
    elif best_score >= 0.6 and sizes_on_scale >= 3:
        confidence_boost = 10  # Good scale adherence
    elif best_score >= 0.4 and sizes_on_scale >= 2:
        confidence_boost = 5   # Partial scale
    elif best_score >= 0.25:
        confidence_boost = 2   # Weak but present

    return {
        'detected_ratio': best_ratio,
        'scale_name': best_scale,
        'consistency': round(best_score, 3),
        'confidence_boost': confidence_boost,
        'base_size': base_size,
        'sizes_on_scale': sizes_on_scale,
        'total_sizes': len(sizes),
    }


def detect_spacing_scale(spacing_values_px: List[float]) -> Dict:
    """Detect base unit and progression in spacing values.

    Args:
        spacing_values_px: List of spacing values in pixels (e.g. [4, 8, 12, 16, 24, 32, 48])

    Returns:
        {
            'base_unit': int,          # e.g. 4 or 8
            'base_unit_name': str,     # e.g. '4px grid' or '8px grid'
            'adherence': float,        # 0-1, what fraction of values are multiples
            'confidence_boost': int,   # 0-15 points
            'uses_ratio': bool,        # whether spacing also follows a ratio progression
            'ratio': float or None,    # detected ratio if present
            'multiples_found': int,
            'total_values': int,
        }
    """
    if not spacing_values_px or len(spacing_values_px) < 3:
        return {'base_unit': None, 'base_unit_name': None, 'adherence': 0,
                'confidence_boost': 0, 'uses_ratio': False, 'ratio': None,
                'multiples_found': 0, 'total_values': len(spacing_values_px) if spacing_values_px else 0}

    values = sorted(set(v for v in spacing_values_px if v > 0))
    if len(values) < 3:
        return {'base_unit': None, 'base_unit_name': None, 'adherence': 0,
                'confidence_boost': 0, 'uses_ratio': False, 'ratio': None,
                'multiples_found': 0, 'total_values': len(values)}

    # Test each common base unit
    best_unit = None
    best_adherence = 0
    best_count = 0

    for unit in COMMON_BASE_UNITS:
        count = sum(1 for v in values if abs(v % unit) <= 1.5 or abs(v % unit - unit) <= 1.5)
        adherence = count / len(values)
        if adherence > best_adherence:
            best_adherence = adherence
            best_unit = unit
            best_count = count

    # Check if spacing also follows a ratio progression
    uses_ratio = False
    spacing_ratio = None
    if len(values) >= 4:
        ratios = [values[i + 1] / values[i] for i in range(len(values) - 1) if values[i] > 0]
        if ratios:
            median_r = sorted(ratios)[len(ratios) // 2]
            if 1.3 < median_r < 2.5:
                # Check consistency
                consistent = sum(1 for r in ratios if abs(r - median_r) / median_r < 0.15)
                if consistent / len(ratios) >= 0.5:
                    uses_ratio = True
                    spacing_ratio = round(median_r, 2)

    # Confidence boost
    confidence_boost = 0
    if best_adherence >= 0.85 and best_count >= 5:
        confidence_boost = 15  # Very consistent grid
    elif best_adherence >= 0.7 and best_count >= 4:
        confidence_boost = 10
    elif best_adherence >= 0.5 and best_count >= 3:
        confidence_boost = 5
    elif best_adherence >= 0.35:
        confidence_boost = 2

    unit_name = f'{best_unit}px grid' if best_unit else None

    return {
        'base_unit': best_unit,
        'base_unit_name': unit_name,
        'adherence': round(best_adherence, 3),
        'confidence_boost': confidence_boost,
        'uses_ratio': uses_ratio,
        'ratio': spacing_ratio,
        'multiples_found': best_count,
        'total_values': len(values),
    }


def detect_color_consistency(colors: List[str]) -> Dict:
    """Check if colors follow a systematic tonal progression.

    Looks for Material Design-style tonal palettes where lightness
    steps are evenly distributed.

    Args:
        colors: List of hex or rgb color strings

    Returns:
        {
            'has_tonal_system': bool,
            'tonal_groups': int,      # number of detected hue families
            'consistency': float,     # 0-1
            'confidence_boost': int,  # 0-10
        }
    """
    if not colors or len(colors) < 4:
        return {'has_tonal_system': False, 'tonal_groups': 0,
                'consistency': 0, 'confidence_boost': 0}

    # Parse colors to HSL
    hsl_colors = []
    for c in colors:
        hsl = _parse_to_hsl(c)
        if hsl:
            hsl_colors.append(hsl)

    if len(hsl_colors) < 4:
        return {'has_tonal_system': False, 'tonal_groups': 0,
                'consistency': 0, 'confidence_boost': 0}

    # Group by hue (within 25° tolerance)
    hue_groups = {}
    for h, s, l in hsl_colors:
        placed = False
        for key in hue_groups:
            if _hue_distance(h, key) < 25:
                hue_groups[key].append((h, s, l))
                placed = True
                break
        if not placed:
            hue_groups[h] = [(h, s, l)]

    # Check for tonal progressions within hue groups
    tonal_groups = 0
    total_consistency = 0

    for hue, members in hue_groups.items():
        if len(members) >= 3:
            # Sort by lightness
            lightnesses = sorted([l for _, _, l in members])
            # Check if lightness steps are roughly even
            steps = [lightnesses[i + 1] - lightnesses[i] for i in range(len(lightnesses) - 1)]
            if steps:
                avg_step = sum(steps) / len(steps)
                if avg_step > 5:  # Meaningful spread
                    variance = sum((s - avg_step) ** 2 for s in steps) / len(steps)
                    cv = math.sqrt(variance) / avg_step if avg_step > 0 else 1
                    if cv < 0.5:  # Coefficient of variation < 50% = reasonably even
                        tonal_groups += 1
                        total_consistency += max(0, 1 - cv)

    consistency = total_consistency / max(tonal_groups, 1)

    confidence_boost = 0
    if tonal_groups >= 3 and consistency > 0.6:
        confidence_boost = 10
    elif tonal_groups >= 2 and consistency > 0.4:
        confidence_boost = 5
    elif tonal_groups >= 1:
        confidence_boost = 2

    return {
        'has_tonal_system': tonal_groups > 0,
        'tonal_groups': tonal_groups,
        'consistency': round(consistency, 3),
        'confidence_boost': confidence_boost,
    }


def detect_layout_consistency(gaps: List[float], paddings: List[float],
                              spacing_result: Dict) -> Dict:
    """Check if flex/grid gaps and padding values follow the same base unit as spacing.

    Args:
        gaps: List of gap values in px from flex/grid containers
        paddings: List of padding values in px from layout containers
        spacing_result: Result from detect_spacing_scale (to get the base unit)

    Returns:
        {
            'gap_adherence': float or None,   # fraction of gaps on-grid
            'padding_adherence': float or None,
            'gaps_on_grid': int,
            'total_gaps': int,
            'paddings_on_grid': int,
            'total_paddings': int,
            'confidence_boost': int,   # 0-10 for spatial_composition
            'off_grid_gaps': list,     # gap values that break the grid
        }
    """
    base_unit = spacing_result.get('base_unit')
    if not base_unit:
        # No base unit detected — can't validate
        return {'gap_adherence': None, 'padding_adherence': None,
                'gaps_on_grid': 0, 'total_gaps': len(gaps),
                'paddings_on_grid': 0, 'total_paddings': len(paddings),
                'confidence_boost': 0, 'off_grid_gaps': []}

    # Check gaps against base unit
    unique_gaps = sorted(set(g for g in gaps if g > 0))
    gaps_on = 0
    off_grid = []
    for g in unique_gaps:
        remainder = g % base_unit
        if remainder <= 1.5 or abs(remainder - base_unit) <= 1.5:
            gaps_on += 1
        else:
            off_grid.append(g)

    gap_adherence = gaps_on / len(unique_gaps) if unique_gaps else None

    # Check paddings against base unit
    unique_pads = sorted(set(p for p in paddings if p > 0))
    pads_on = 0
    for p in unique_pads:
        remainder = p % base_unit
        if remainder <= 1.5 or abs(remainder - base_unit) <= 1.5:
            pads_on += 1

    pad_adherence = pads_on / len(unique_pads) if unique_pads else None

    # Confidence boost for spatial_composition
    boost = 0
    total_checked = len(unique_gaps) + len(unique_pads)
    total_on = gaps_on + pads_on
    if total_checked >= 5:
        overall = total_on / total_checked
        if overall >= 0.8:
            boost = 10
        elif overall >= 0.6:
            boost = 5
        elif overall >= 0.4:
            boost = 2

    return {
        'gap_adherence': round(gap_adherence, 3) if gap_adherence is not None else None,
        'padding_adherence': round(pad_adherence, 3) if pad_adherence is not None else None,
        'gaps_on_grid': gaps_on,
        'total_gaps': len(unique_gaps),
        'paddings_on_grid': pads_on,
        'total_paddings': len(unique_pads),
        'confidence_boost': boost,
        'off_grid_gaps': off_grid[:10],
    }


def analyze_harmony(evidence: Dict) -> Dict:
    """Main entry point — analyze all extracted evidence for mathematical harmony.

    Args:
        evidence: The full evidence dict from deep_evidence_engine

    Returns:
        {
            'typography': {...},   # type scale detection result
            'spacing': {...},      # spacing grid detection result
            'color': {...},        # tonal system detection result
            'confidence_adjustments': {
                'typography': int,     # points to add
                'spacing_scale': int,
                'colors': int,
            },
            'summary': str,        # human-readable summary
        }
    """
    # Extract typography sizes
    typo = evidence.get('typography', {})
    font_sizes = []
    if isinstance(typo, dict):
        # Try type_scale dict format first
        ts = typo.get('type_scale', {})
        if isinstance(ts, dict):
            sizes_px = ts.get('sizes_px') or ts.get('heading_sizes_px') or []
            if isinstance(sizes_px, list):
                font_sizes = [float(s) for s in sizes_px if s]

        # Try details.all_sizes (common format: ["16px", "14px", ...])
        if not font_sizes:
            details = typo.get('details', {})
            if isinstance(details, dict):
                all_sizes = details.get('all_sizes', [])
                if isinstance(all_sizes, list):
                    for item in all_sizes:
                        try:
                            font_sizes.append(float(str(item).replace('px', '').replace('rem', '').replace('em', '')))
                        except (ValueError, AttributeError):
                            pass

        # Try headings list
        if not font_sizes:
            details = typo.get('details', {})
            if isinstance(details, dict):
                headings = details.get('headings', [])
                if isinstance(headings, list):
                    for h in headings:
                        if isinstance(h, dict) and 'fontSize' in h:
                            try:
                                font_sizes.append(float(str(h['fontSize']).replace('px', '')))
                            except (ValueError, AttributeError):
                                pass

        # Fallback: font_sizes key
        if not font_sizes:
            raw = typo.get('font_sizes', [])
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, (int, float)):
                        font_sizes.append(float(item))
                    elif isinstance(item, dict) and 'size' in item:
                        font_sizes.append(float(item['size']))
                    elif isinstance(item, str):
                        try:
                            font_sizes.append(float(item.replace('px', '')))
                        except (ValueError, AttributeError):
                            pass

    # Extract spacing values
    spacing = evidence.get('spacing_scale', {})
    spacing_values = []
    if isinstance(spacing, dict):
        scale = spacing.get('scale') or spacing.get('values') or []
        if isinstance(scale, list):
            for item in scale:
                if isinstance(item, (int, float)):
                    spacing_values.append(float(item))
                elif isinstance(item, dict) and 'value' in item:
                    v = item['value']
                    if isinstance(v, str):
                        try:
                            spacing_values.append(float(v.replace('px', '')))
                        except (ValueError, AttributeError):
                            pass
                    elif isinstance(v, (int, float)):
                        spacing_values.append(float(v))
                elif isinstance(item, str):
                    try:
                        spacing_values.append(float(item.replace('px', '')))
                    except (ValueError, AttributeError):
                        pass

    # Extract colors
    colors_data = evidence.get('colors', {})
    color_list = []
    if isinstance(colors_data, dict):
        palette = colors_data.get('palette', {})
        if isinstance(palette, dict):
            for key in ('primary', 'secondary', 'intentional'):
                vals = palette.get(key, [])
                if isinstance(vals, list):
                    color_list.extend(str(v) for v in vals)
        elif isinstance(palette, list):
            color_list.extend(str(v) for v in palette)

    # Extract layout gaps and paddings from spatial composition
    spatial = evidence.get('spatial_composition', {})
    layout_gaps = []
    layout_paddings = []
    if isinstance(spatial, dict):
        ch = spatial.get('container_hierarchy', {})
        if isinstance(ch, dict):
            layout_gaps = ch.get('all_gaps', [])
            layout_paddings = ch.get('all_paddings', [])

    # Run detectors
    type_result = detect_type_scale(font_sizes)
    spacing_result = detect_spacing_scale(spacing_values)
    color_result = detect_color_consistency(color_list)
    layout_result = detect_layout_consistency(layout_gaps, layout_paddings, spacing_result)

    # Build summary
    parts = []
    if type_result['scale_name']:
        parts.append(f"Type scale: {type_result['scale_name']} "
                     f"(ratio {type_result['detected_ratio']}, "
                     f"{type_result['sizes_on_scale']}/{type_result['total_sizes']} sizes match)")
    if spacing_result['base_unit']:
        parts.append(f"Spacing: {spacing_result['base_unit_name']} "
                     f"({spacing_result['adherence']:.0%} adherence)")
        if spacing_result['uses_ratio']:
            parts.append(f"Spacing ratio: {spacing_result['ratio']}")
    if layout_result['gap_adherence'] is not None:
        parts.append(f"Layout gaps: {layout_result['gap_adherence']:.0%} on-grid "
                     f"({layout_result['gaps_on_grid']}/{layout_result['total_gaps']})")
    if layout_result['padding_adherence'] is not None:
        parts.append(f"Padding: {layout_result['padding_adherence']:.0%} on-grid")
    if color_result['has_tonal_system']:
        parts.append(f"Color: {color_result['tonal_groups']} tonal families detected")

    summary = '; '.join(parts) if parts else 'No mathematical scale detected'

    # Combine spacing + layout boosts (cap at 15)
    combined_spacing_boost = min(15, spacing_result['confidence_boost'] +
                                     layout_result['confidence_boost'])

    return {
        'typography': type_result,
        'spacing': spacing_result,
        'layout': layout_result,
        'color': color_result,
        'confidence_adjustments': {
            'typography': type_result['confidence_boost'],
            'spacing_scale': combined_spacing_boost,
            'colors': color_result['confidence_boost'],
            'spatial_composition': layout_result['confidence_boost'],
        },
        'summary': summary,
    }


def apply_confidence_boosts(evidence: Dict, harmony: Dict) -> None:
    """Apply harmony-derived confidence boosts to existing metrics in-place.

    Modifies evidence dict directly — adds harmony data and adjusts
    confidence scores on typography, spacing_scale, and colors.
    """
    adjustments = harmony.get('confidence_adjustments', {})

    for metric_key, boost in adjustments.items():
        if boost <= 0:
            continue
        metric = evidence.get(metric_key)
        if not isinstance(metric, dict):
            continue
        current = metric.get('confidence', 0)
        if isinstance(current, (int, float)) and current > 0:
            # Cap at 99 — never claim 100% from a boost
            new_conf = min(99, current + boost)
            metric['confidence'] = new_conf
            logger.info(f"Harmony boost: {metric_key} confidence "
                        f"{current} → {new_conf} (+{boost})")

    # Attach harmony data to evidence for dashboard display
    evidence['design_harmony'] = {
        'type_scale': harmony['typography'],
        'spacing_grid': harmony['spacing'],
        'layout_consistency': harmony['layout'],
        'color_system': harmony['color'],
        'summary': harmony['summary'],
    }


# ─── Internal helpers ─────────────────────────────────────────────────

def _score_scale_fit(sizes: List[float], ratio: float, tolerance: float = 0.08) -> float:
    """Score how well a list of sizes fits a given ratio.

    For each size, checks if it can be expressed as base × ratio^n
    for some integer n (positive or negative).
    """
    if ratio <= 1 or not sizes:
        return 0

    # Try each size as potential base
    best_score = 0
    for base in sizes:
        if base <= 0:
            continue
        on_scale = 0
        for s in sizes:
            if _is_on_scale(s, base, ratio, tolerance):
                on_scale += 1
        score = on_scale / len(sizes)
        if score > best_score:
            best_score = score

    return best_score


def _is_on_scale(size: float, base: float, ratio: float, tolerance: float = 0.08) -> bool:
    """Check if a size fits base × ratio^n for some integer n in [-5, 5]."""
    if size <= 0 or base <= 0 or ratio <= 1:
        return False
    log_ratio = math.log(ratio)
    if log_ratio == 0:
        return False
    n = math.log(size / base) / log_ratio
    n_rounded = round(n)
    if abs(n_rounded) > 6:
        return False
    expected = base * (ratio ** n_rounded)
    if expected <= 0:
        return False
    return abs(size - expected) / expected <= tolerance


def _closest_scale_name(ratio: float) -> Optional[str]:
    """Find the closest named scale, if within 5%."""
    for known_ratio, name in KNOWN_SCALES:
        if abs(ratio - known_ratio) / known_ratio < 0.05:
            return name
    return None


def _parse_to_hsl(color_str: str) -> Optional[Tuple[float, float, float]]:
    """Parse a color string to (hue, saturation, lightness)."""
    c = str(color_str).strip()

    # Hex
    if c.startswith('#'):
        hex_clean = c.lstrip('#')
        if len(hex_clean) == 3:
            hex_clean = ''.join(ch * 2 for ch in hex_clean)
        if len(hex_clean) == 6:
            try:
                r = int(hex_clean[0:2], 16) / 255
                g = int(hex_clean[2:4], 16) / 255
                b = int(hex_clean[4:6], 16) / 255
                return _rgb_to_hsl(r, g, b)
            except ValueError:
                return None

    # rgb(r, g, b) or rgba(r, g, b, a)
    import re
    m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', c)
    if m:
        r = int(m.group(1)) / 255
        g = int(m.group(2)) / 255
        b = int(m.group(3)) / 255
        return _rgb_to_hsl(r, g, b)

    return None


def _rgb_to_hsl(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Convert RGB (0-1) to HSL (degrees, percent, percent)."""
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2

    if max_c == min_c:
        h = s = 0
    else:
        d = max_c - min_c
        s = d / (2 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
        if max_c == r:
            h = ((g - b) / d + (6 if g < b else 0)) * 60
        elif max_c == g:
            h = ((b - r) / d + 2) * 60
        else:
            h = ((r - g) / d + 4) * 60

    return (h, s * 100, l * 100)


def _hue_distance(h1: float, h2: float) -> float:
    """Angular distance between two hue values (0-360)."""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)
