"""
Design System Differ — Compare two sites' design systems and synthesize WHY they look different.

Takes two evidence objects from DeepEvidenceEngine.extract_all() and produces:
- Per-metric comparisons with design-intent interpretations
- Philosophy synthesis along 4 axes (density, posture, systematization, personality)
- Ranked key differentiators
- Shared commonalities
- Human-readable summary paragraph

Output is structured for both LLM consumption and dashboard rendering.
"""

import colorsys
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple


class DesignSystemDiffer:
    """Compare two sites' design systems and synthesize why they look different."""

    METRIC_CATEGORIES = [
        ('typography', 'Typography', '_compare_typography'),
        ('colors', 'Color System', '_compare_colors'),
        ('spacing_scale', 'Spacing System', '_compare_spacing'),
        ('shadow_system', 'Shadow & Depth', '_compare_shadows'),
        ('motion_tokens', 'Motion Design', '_compare_motion'),
        ('layout', 'Layout Architecture', '_compare_layout'),
        ('visual_hierarchy', 'Visual Hierarchy', '_compare_hierarchy'),
        ('css_analytics', 'CSS Architecture', '_compare_css_analytics'),
    ]

    # Visual impact weights for divergence ranking
    IMPACT_WEIGHTS = {
        'typography': 1.3,
        'colors': 1.3,
        'spacing_scale': 1.0,
        'shadow_system': 0.9,
        'motion_tokens': 0.8,
        'layout': 1.1,
        'visual_hierarchy': 1.0,
        'css_analytics': 1.2,
    }

    def __init__(self, evidence_a: Dict, evidence_b: Dict,
                 name_a: str = 'Site A', name_b: str = 'Site B'):
        self.a = evidence_a
        self.b = evidence_b
        self.name_a = name_a
        self.name_b = name_b

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def compare(self) -> Dict:
        """Main entry point. Returns full structured comparison."""
        metric_diffs = {}
        skipped = []
        compared = 0

        for key, label, method_name in self.METRIC_CATEGORIES:
            if not self._both_have(key):
                reason = self._skip_reason(key)
                skipped.append({'metric': label, 'reason': reason})
                continue
            comparator = getattr(self, method_name)
            data_a = self.a.get(key, {})
            data_b = self.b.get(key, {})
            result = comparator(data_a, data_b)
            if result:
                metric_diffs[key] = result
                compared += 1

        philosophy = self._synthesize_philosophy(metric_diffs)
        differentiators = self._rank_differentiators(metric_diffs)
        commonalities = self._find_commonalities(metric_diffs)
        summary = self._generate_summary(philosophy, differentiators, commonalities)

        return {
            'summary': summary,
            'philosophy_comparison': philosophy,
            'metric_comparisons': metric_diffs,
            'key_differentiators': differentiators,
            'commonalities': commonalities,
            'site_a_name': self.name_a,
            'site_b_name': self.name_b,
            'metrics_compared': compared,
            'metrics_skipped': len(skipped),
            'skipped_reasons': skipped,
        }

    # ──────────────────────────────────────────────
    # Per-metric comparators
    # ──────────────────────────────────────────────

    def _compare_typography(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        # Font families
        fonts_a = self._extract_font_names(a)
        fonts_b = self._extract_font_names(b)
        if fonts_a or fonts_b:
            pers_a = self._classify_font_personality(fonts_a[0]) if fonts_a else 'unknown'
            pers_b = self._classify_font_personality(fonts_b[0]) if fonts_b else 'unknown'
            interp = self._font_intent(pers_a, pers_b)
            diffs.append({
                'aspect': 'Font personality',
                'site_a': f"{fonts_a[0] if fonts_a else '?'} ({pers_a})",
                'site_b': f"{fonts_b[0] if fonts_b else '?'} ({pers_b})",
                'interpretation': interp,
            })

        # Scale ratio
        ratio_a = self._safe_get(a, 'type_scale', 'ratio', default=None)
        ratio_b = self._safe_get(b, 'type_scale', 'ratio', default=None)
        if isinstance(ratio_a, (int, float)) and isinstance(ratio_b, (int, float)):
            interp = self._scale_ratio_intent(ratio_a, ratio_b)
            diffs.append({
                'aspect': 'Type scale ratio',
                'site_a': f"{ratio_a:.2f}",
                'site_b': f"{ratio_b:.2f}",
                'interpretation': interp,
            })

        # Font count
        count_a = len(fonts_a)
        count_b = len(fonts_b)
        if count_a != count_b:
            interp = self._font_count_intent(count_a, count_b)
            diffs.append({
                'aspect': 'Font diversity',
                'site_a': f"{count_a} {'typeface' if count_a == 1 else 'typefaces'}",
                'site_b': f"{count_b} {'typeface' if count_b == 1 else 'typefaces'}",
                'interpretation': interp,
            })

        # Weight range
        weights_a = self._safe_get(a, 'details', 'all_weights', default=[])
        weights_b = self._safe_get(b, 'details', 'all_weights', default=[])
        w_a = self._parse_int_list(weights_a)
        w_b = self._parse_int_list(weights_b)
        if len(w_a) >= 2 and len(w_b) >= 2:
            range_a = max(w_a) - min(w_a)
            range_b = max(w_b) - min(w_b)
            if abs(range_a - range_b) > 100:
                diffs.append({
                    'aspect': 'Weight range',
                    'site_a': f"{min(w_a)}–{max(w_a)}",
                    'site_b': f"{min(w_b)}–{max(w_b)}",
                    'interpretation': f"{'Wider' if range_a > range_b else 'Narrower'} weight range on {self.name_a} suggests {'stronger typographic hierarchy' if range_a > range_b else 'more subtle weight differentiation'}.",
                })

        divergence = self._compute_typo_divergence(a, b)

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_colors(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        # Palette size
        size_a = self._palette_size(a)
        size_b = self._palette_size(b)
        if size_a > 0 or size_b > 0:
            interp = self._palette_size_intent(size_a, size_b)
            diffs.append({
                'aspect': 'Palette size',
                'site_a': f"{size_a} colors",
                'site_b': f"{size_b} colors",
                'interpretation': interp,
            })

        # Semantic roles
        roles_a = a.get('color_roles', {})
        roles_b = b.get('color_roles', {})
        ra = len(roles_a) if isinstance(roles_a, dict) else 0
        rb = len(roles_b) if isinstance(roles_b, dict) else 0
        if ra > 0 or rb > 0:
            diffs.append({
                'aspect': 'Semantic color roles',
                'site_a': f"{ra} roles" + (f" ({', '.join(list(roles_a.keys())[:3])})" if ra else ""),
                'site_b': f"{rb} roles" + (f" ({', '.join(list(roles_b.keys())[:3])})" if rb else ""),
                'interpretation': f"{'More' if ra > rb else 'Fewer'} semantic roles on {self.name_a if ra > rb else self.name_b} indicates {'a more systematic design token approach' if max(ra, rb) >= 5 else 'emerging design system usage'}.",
            })

        # Background strategy (dark vs light)
        bg_a = self._detect_bg_strategy(a)
        bg_b = self._detect_bg_strategy(b)
        if bg_a != bg_b:
            diffs.append({
                'aspect': 'Background strategy',
                'site_a': bg_a,
                'site_b': bg_b,
                'interpretation': f"{self.name_a} uses a {bg_a} foundation while {self.name_b} uses {bg_b}, creating fundamentally different visual moods.",
            })

        # Temperature
        temp_a = self._palette_temperature(a)
        temp_b = self._palette_temperature(b)
        if temp_a and temp_b and temp_a != temp_b:
            diffs.append({
                'aspect': 'Color temperature',
                'site_a': temp_a,
                'site_b': temp_b,
                'interpretation': f"{self.name_a}'s {temp_a} palette {'feels energetic and approachable' if temp_a == 'warm' else 'projects calm professionalism'}; {self.name_b}'s {temp_b} palette {'feels energetic and approachable' if temp_b == 'warm' else 'projects calm professionalism'}.",
            })

        divergence = self._clamp(min(abs(size_a - size_b) * 5, 25) + min(abs(ra - rb) * 8, 25) + (30 if bg_a != bg_b else 0) + (15 if temp_a != temp_b else 0))

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_spacing(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        base_a = self._parse_base_unit(a.get('base_unit'))
        base_b = self._parse_base_unit(b.get('base_unit'))
        scale_a = a.get('scale', a.get('values', []))
        scale_b = b.get('scale', b.get('values', []))

        if base_a and base_b:
            interp = self._spacing_intent(base_a, base_b)
            diffs.append({
                'aspect': 'Base unit',
                'site_a': f"{base_a}px",
                'site_b': f"{base_b}px",
                'interpretation': interp,
            })

        len_a = len(scale_a) if isinstance(scale_a, list) else 0
        len_b = len(scale_b) if isinstance(scale_b, list) else 0
        if len_a > 0 and len_b > 0 and abs(len_a - len_b) >= 2:
            diffs.append({
                'aspect': 'Scale granularity',
                'site_a': f"{len_a} stops",
                'site_b': f"{len_b} stops",
                'interpretation': f"{'More' if len_a > len_b else 'Fewer'} spacing stops on {self.name_a if len_a > len_b else self.name_b} allows finer spatial control.",
            })

        divergence = 0
        if base_a and base_b:
            divergence += min(abs(base_a - base_b) * 8, 50)
        divergence += min(abs(len_a - len_b) * 5, 30)
        divergence = self._clamp(divergence)

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_shadows(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        levels_a = a.get('levels', [])
        levels_b = b.get('levels', [])
        la = len(levels_a) if isinstance(levels_a, list) else 0
        lb = len(levels_b) if isinstance(levels_b, list) else 0

        depth_a = self._shadow_depth_label(la)
        depth_b = self._shadow_depth_label(lb)

        diffs.append({
            'aspect': 'Elevation system',
            'site_a': f"{la} levels ({depth_a})",
            'site_b': f"{lb} levels ({depth_b})",
            'interpretation': self._shadow_intent(la, lb, depth_a, depth_b),
        })

        divergence = self._clamp(abs(la - lb) * 15)

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_motion(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        pers_a = a.get('motion_personality', a.get('pattern', ''))
        pers_b = b.get('motion_personality', b.get('pattern', ''))
        if pers_a or pers_b:
            diffs.append({
                'aspect': 'Motion personality',
                'site_a': str(pers_a) or 'Minimal',
                'site_b': str(pers_b) or 'Minimal',
                'interpretation': f"{self.name_a} uses {'a ' + str(pers_a).lower() if pers_a else 'minimal'} motion approach while {self.name_b} uses {'a ' + str(pers_b).lower() if pers_b else 'minimal'} approach.",
            })

        # Duration
        details_a = a.get('details', {}) if isinstance(a.get('details'), dict) else {}
        details_b = b.get('details', {}) if isinstance(b.get('details'), dict) else {}
        dur_a = self._safe_get(details_a, 'duration_scale', 'median', default=None)
        dur_b = self._safe_get(details_b, 'duration_scale', 'median', default=None)
        if dur_a and dur_b:
            diffs.append({
                'aspect': 'Timing',
                'site_a': str(dur_a),
                'site_b': str(dur_b),
                'interpretation': self._motion_timing_intent(dur_a, dur_b),
            })

        # Animation count
        anims_a = details_a.get('animations', [])
        anims_b = details_b.get('animations', [])
        ca = len(anims_a) if isinstance(anims_a, list) else 0
        cb = len(anims_b) if isinstance(anims_b, list) else 0
        if ca > 0 or cb > 0:
            diffs.append({
                'aspect': 'Animation count',
                'site_a': str(ca),
                'site_b': str(cb),
                'interpretation': f"{'Richer' if ca > cb else 'Simpler'} animation repertoire on {self.name_a if ca > cb else self.name_b}.",
            })

        divergence = self._clamp(
            (25 if str(pers_a).lower() != str(pers_b).lower() else 0) +
            min(abs(ca - cb) * 5, 30)
        )

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_layout(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        details_a = a.get('details', {}) if isinstance(a.get('details'), dict) else {}
        details_b = b.get('details', {}) if isinstance(b.get('details'), dict) else {}

        flex_a = details_a.get('flex_count', 0) or 0
        grid_a = details_a.get('grid_count', 0) or 0
        flex_b = details_b.get('flex_count', 0) or 0
        grid_b = details_b.get('grid_count', 0) or 0

        strat_a = self._layout_strategy(flex_a, grid_a)
        strat_b = self._layout_strategy(flex_b, grid_b)

        diffs.append({
            'aspect': 'Layout strategy',
            'site_a': f"{strat_a} (flex:{flex_a}, grid:{grid_a})",
            'site_b': f"{strat_b} (flex:{flex_b}, grid:{grid_b})",
            'interpretation': self._layout_intent(strat_a, strat_b),
        })

        # Page structure from spatial_composition
        sc_a = self.a.get('spatial_composition', {})
        sc_b = self.b.get('spatial_composition', {})
        struct_a = self._safe_get(sc_a, 'page_structure', 'pattern_type', default='')
        struct_b = self._safe_get(sc_b, 'page_structure', 'pattern_type', default='')
        if struct_a or struct_b:
            diffs.append({
                'aspect': 'Page structure',
                'site_a': struct_a or 'Unknown',
                'site_b': struct_b or 'Unknown',
                'interpretation': f"{self.name_a} follows a {struct_a or 'undefined'} pattern; {self.name_b} follows a {struct_b or 'undefined'} pattern.",
            })

        # Content density
        density_a = self._safe_get(sc_a, 'whitespace_analysis', 'content_density_pct', default=None)
        density_b = self._safe_get(sc_b, 'whitespace_analysis', 'content_density_pct', default=None)
        if isinstance(density_a, (int, float)) and isinstance(density_b, (int, float)):
            diffs.append({
                'aspect': 'Content density',
                'site_a': f"{density_a:.0f}%",
                'site_b': f"{density_b:.0f}%",
                'interpretation': self._density_intent(density_a, density_b),
            })

        divergence = self._clamp(
            (25 if strat_a != strat_b else 0) +
            (20 if struct_a != struct_b else 0) +
            (min(abs((density_a or 50) - (density_b or 50)), 40) if isinstance(density_a, (int, float)) and isinstance(density_b, (int, float)) else 0)
        )

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_hierarchy(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        hero_a = self._safe_get(a, 'hero_section', 'detected', default=False)
        hero_b = self._safe_get(b, 'hero_section', 'detected', default=False)
        diffs.append({
            'aspect': 'Hero section',
            'site_a': 'Present' if hero_a else 'Absent',
            'site_b': 'Present' if hero_b else 'Absent',
            'interpretation': self._hero_intent(hero_a, hero_b),
        })

        cta_a = self._safe_get(a, 'primary_cta', 'detected', default=False)
        cta_b = self._safe_get(b, 'primary_cta', 'detected', default=False)
        cta_text_a = self._safe_get(a, 'primary_cta', 'text', default='')
        cta_text_b = self._safe_get(b, 'primary_cta', 'text', default='')
        diffs.append({
            'aspect': 'CTA strategy',
            'site_a': f"'{cta_text_a}'" if cta_a and cta_text_a else ('Present' if cta_a else 'None'),
            'site_b': f"'{cta_text_b}'" if cta_b and cta_text_b else ('Present' if cta_b else 'None'),
            'interpretation': self._cta_intent(cta_a, cta_b),
        })

        reading_a = a.get('reading_pattern', '')
        reading_b = b.get('reading_pattern', '')
        if reading_a or reading_b:
            diffs.append({
                'aspect': 'Reading pattern',
                'site_a': reading_a or 'Unknown',
                'site_b': reading_b or 'Unknown',
                'interpretation': f"Different reading patterns suggest different content prioritization strategies." if reading_a != reading_b else "Shared reading pattern indicates similar content flow.",
            })

        divergence = self._clamp(
            (25 if hero_a != hero_b else 0) +
            (25 if cta_a != cta_b else 0) +
            (15 if reading_a != reading_b else 0)
        )

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _compare_css_analytics(self, a: Dict, b: Dict) -> Dict:
        diffs = []
        conf_a = a.get('confidence', 0) or 0
        conf_b = b.get('confidence', 0) or 0

        # Sophistication score
        score_a = a.get('sophistication_score', 0) or 0
        score_b = b.get('sophistication_score', 0) or 0
        diffs.append({
            'aspect': 'CSS sophistication',
            'site_a': f"{score_a}/100",
            'site_b': f"{score_b}/100",
            'interpretation': self._sophistication_intent(score_a, score_b),
        })

        # Custom property adoption
        cp_a = self._safe_get(a, 'custom_property_sophistication', 'total', default=0)
        cp_b = self._safe_get(b, 'custom_property_sophistication', 'total', default=0)
        derived_a = self._safe_get(a, 'custom_property_sophistication', 'derived_count', default=0)
        derived_b = self._safe_get(b, 'custom_property_sophistication', 'derived_count', default=0)
        if cp_a > 0 or cp_b > 0:
            diffs.append({
                'aspect': 'Design token adoption',
                'site_a': f"{cp_a} custom properties ({derived_a} derived)",
                'site_b': f"{cp_b} custom properties ({derived_b} derived)",
                'interpretation': self._token_adoption_intent(cp_a, cp_b, derived_a, derived_b),
            })

        # Modern CSS features gap
        feat_a = a.get('modern_features', {})
        feat_b = b.get('modern_features', {})
        features_list = ['nesting', 'cascade_layers', 'container_queries',
                         'has_selector', 'is_where_selectors', 'color_mix',
                         'light_dark', 'subgrid']
        a_has = [f for f in features_list if feat_a.get(f)]
        b_has = [f for f in features_list if feat_b.get(f)]
        a_only = [f for f in a_has if f not in b_has]
        b_only = [f for f in b_has if f not in a_has]
        if a_only or b_only:
            diffs.append({
                'aspect': 'Modern CSS features',
                'site_a': ', '.join(a_has) if a_has else 'None',
                'site_b': ', '.join(b_has) if b_has else 'None',
                'interpretation': self._modern_features_intent(a_has, b_has, a_only, b_only),
            })

        # Uniqueness ratio
        uniq_a = self._safe_get(a, 'uniqueness', 'overall_uniqueness', default=None)
        uniq_b = self._safe_get(b, 'uniqueness', 'overall_uniqueness', default=None)
        if isinstance(uniq_a, (int, float)) and isinstance(uniq_b, (int, float)):
            diffs.append({
                'aspect': 'Value uniqueness',
                'site_a': f"{uniq_a:.1%}",
                'site_b': f"{uniq_b:.1%}",
                'interpretation': self._uniqueness_intent(uniq_a, uniq_b),
            })

        # DTCG token density
        tok_a = self._safe_get(a, 'dtcg_tokens', 'total_token_count', default=0)
        tok_b = self._safe_get(b, 'dtcg_tokens', 'total_token_count', default=0)
        if tok_a > 0 or tok_b > 0:
            diffs.append({
                'aspect': 'DTCG-classifiable tokens',
                'site_a': str(tok_a),
                'site_b': str(tok_b),
                'interpretation': f"{'More' if tok_a > tok_b else 'Fewer'} design decisions are codified as standard tokens on {self.name_a if tok_a > tok_b else self.name_b}.",
            })

        feature_gap = len(a_only) + len(b_only)
        divergence = self._clamp(
            abs(score_a - score_b) * 1.2 +
            min(abs(cp_a - cp_b) * 0.5, 20) +
            feature_gap * 8
        )

        return {
            'confidence': {'site_a': conf_a, 'site_b': conf_b},
            'differences': diffs,
            'divergence_score': divergence,
        }

    def _sophistication_intent(self, sa: int, sb: int) -> str:
        if abs(sa - sb) < 10:
            return "Similar CSS sophistication suggests comparable authoring approaches."
        more = self.name_a if sa > sb else self.name_b
        less = self.name_b if sa > sb else self.name_a
        label_more = 'hand-crafted, modern CSS' if max(sa, sb) >= 60 else 'moderately sophisticated CSS'
        label_less = 'conventional CSS' if min(sa, sb) >= 30 else 'basic/framework-generated CSS'
        return f"{more} uses {label_more} ({max(sa, sb)}/100); {less} uses {label_less} ({min(sa, sb)}/100)."

    def _token_adoption_intent(self, ca: int, cb: int, da: int, db: int) -> str:
        if ca == 0 and cb == 0:
            return "Neither site uses CSS custom properties as design tokens."
        more = self.name_a if ca > cb else self.name_b
        fewer = self.name_b if ca > cb else self.name_a
        derived_note = ""
        more_derived = da if ca > cb else db
        if more_derived > 5:
            derived_note = f" with {more_derived} derived values showing a token hierarchy"
        return f"{more} codifies {max(ca, cb)} design decisions as custom properties{derived_note}; {fewer} uses {min(ca, cb)}."

    def _modern_features_intent(self, a_has: list, b_has: list, a_only: list, b_only: list) -> str:
        if a_only and b_only:
            return f"{self.name_a} uniquely uses {', '.join(a_only[:3])}; {self.name_b} uniquely uses {', '.join(b_only[:3])}."
        if a_only:
            return f"{self.name_a} adopts modern CSS features ({', '.join(a_only[:3])}) that {self.name_b} hasn't adopted yet."
        return f"{self.name_b} adopts modern CSS features ({', '.join(b_only[:3])}) that {self.name_a} hasn't adopted yet."

    def _uniqueness_intent(self, ua: float, ub: float) -> str:
        if abs(ua - ub) < 0.1:
            return "Similar value uniqueness suggests comparable levels of design system discipline."
        more = self.name_a if ua > ub else self.name_b
        less = self.name_b if ua > ub else self.name_a
        return f"{more}'s higher uniqueness ratio ({max(ua, ub):.0%}) indicates tighter design system control; {less}'s lower ratio ({min(ua, ub):.0%}) suggests more one-off values."

    # ──────────────────────────────────────────────
    # Synthesis layer
    # ──────────────────────────────────────────────

    def _synthesize_philosophy(self, metric_diffs: Dict) -> Dict:
        """Infer higher-order design philosophy along 4 axes."""

        # Axis 1: Visual density
        density = self._axis_visual_density(metric_diffs)

        # Axis 2: Interaction posture
        posture = self._axis_interaction_posture(metric_diffs)

        # Axis 3: Systematization
        system = self._axis_systematization(metric_diffs)

        # Axis 4: Personality
        personality = self._axis_personality(metric_diffs)

        return {
            'visual_density': density,
            'interaction_posture': posture,
            'systematization': system,
            'personality': personality,
        }

    def _axis_visual_density(self, diffs: Dict) -> Dict:
        """Sparse/luxurious ↔ Dense/utilitarian."""
        # Derive from spacing base, shadow count, whitespace
        spacing = diffs.get('spacing_scale', {})
        sp_diffs = spacing.get('differences', [])
        base_a = base_b = None
        for d in sp_diffs:
            if d['aspect'] == 'Base unit':
                base_a = self._parse_px_val(d['site_a'])
                base_b = self._parse_px_val(d['site_b'])

        label_a = self._density_label(base_a, self.a)
        label_b = self._density_label(base_b, self.b)

        comparison = ""
        if label_a != label_b:
            comparison = f"{self.name_a} creates a {label_a} feel while {self.name_b} is {label_b}."
        else:
            comparison = f"Both sites share a {label_a} spatial approach."

        return {'site_a': label_a, 'site_b': label_b, 'comparison': comparison}

    def _axis_interaction_posture(self, diffs: Dict) -> Dict:
        """Passive/content ↔ Active/conversion."""
        vh = diffs.get('visual_hierarchy', {})
        vh_diffs = vh.get('differences', [])

        has_cta_a = has_cta_b = False
        has_hero_a = has_hero_b = False
        for d in vh_diffs:
            if d['aspect'] == 'CTA strategy':
                has_cta_a = 'None' not in d['site_a']
                has_cta_b = 'None' not in d['site_b']
            elif d['aspect'] == 'Hero section':
                has_hero_a = d['site_a'] == 'Present'
                has_hero_b = d['site_b'] == 'Present'

        motion = diffs.get('motion_tokens', {})
        motion_diffs = motion.get('differences', [])
        anim_a = anim_b = 0
        for d in motion_diffs:
            if d['aspect'] == 'Animation count':
                anim_a = int(d['site_a']) if d['site_a'].isdigit() else 0
                anim_b = int(d['site_b']) if d['site_b'].isdigit() else 0

        label_a = self._posture_label(has_hero_a, has_cta_a, anim_a)
        label_b = self._posture_label(has_hero_b, has_cta_b, anim_b)

        comparison = ""
        if label_a != label_b:
            comparison = f"{self.name_a} takes a {label_a} stance; {self.name_b} is {label_b}."
        else:
            comparison = f"Both sites share a {label_a} interaction posture."

        return {'site_a': label_a, 'site_b': label_b, 'comparison': comparison}

    def _axis_systematization(self, diffs: Dict) -> Dict:
        """Highly systematic ↔ Organic/editorial."""
        signals_a = 0
        signals_b = 0

        # Color roles count
        colors = diffs.get('colors', {})
        for d in colors.get('differences', []):
            if d['aspect'] == 'Semantic color roles':
                ra = int(re.search(r'(\d+)', d['site_a']).group(1)) if re.search(r'(\d+)', d['site_a']) else 0
                rb = int(re.search(r'(\d+)', d['site_b']).group(1)) if re.search(r'(\d+)', d['site_b']) else 0
                signals_a += min(ra, 5)
                signals_b += min(rb, 5)

        # Spacing scale length
        spacing = diffs.get('spacing_scale', {})
        for d in spacing.get('differences', []):
            if d['aspect'] == 'Scale granularity':
                sa = int(re.search(r'(\d+)', d['site_a']).group(1)) if re.search(r'(\d+)', d['site_a']) else 0
                sb = int(re.search(r'(\d+)', d['site_b']).group(1)) if re.search(r'(\d+)', d['site_b']) else 0
                signals_a += min(sa // 2, 4)
                signals_b += min(sb // 2, 4)

        # Shadow levels
        shadows = diffs.get('shadow_system', {})
        for d in shadows.get('differences', []):
            if d['aspect'] == 'Elevation system':
                la = int(re.search(r'(\d+)', d['site_a']).group(1)) if re.search(r'(\d+)', d['site_a']) else 0
                lb = int(re.search(r'(\d+)', d['site_b']).group(1)) if re.search(r'(\d+)', d['site_b']) else 0
                signals_a += min(la, 4)
                signals_b += min(lb, 4)

        # CSS analytics signals (custom properties, uniqueness, tokens)
        css = diffs.get('css_analytics', {})
        for d in css.get('differences', []):
            if d['aspect'] == 'Design token adoption':
                cpa = int(re.search(r'(\d+)', d['site_a']).group(1)) if re.search(r'(\d+)', d['site_a']) else 0
                cpb = int(re.search(r'(\d+)', d['site_b']).group(1)) if re.search(r'(\d+)', d['site_b']) else 0
                signals_a += min(cpa // 10, 5)
                signals_b += min(cpb // 10, 5)
            elif d['aspect'] == 'Value uniqueness':
                ua = float(re.search(r'([\d.]+)', d['site_a']).group(1)) / 100 if re.search(r'([\d.]+)', d['site_a']) else 0
                ub = float(re.search(r'([\d.]+)', d['site_b']).group(1)) / 100 if re.search(r'([\d.]+)', d['site_b']) else 0
                if ua > 0.5: signals_a += 3
                if ub > 0.5: signals_b += 3
            elif d['aspect'] == 'DTCG-classifiable tokens':
                ta = int(d['site_a']) if d['site_a'].isdigit() else 0
                tb = int(d['site_b']) if d['site_b'].isdigit() else 0
                if ta > 20: signals_a += 3
                if tb > 20: signals_b += 3

        label_a = 'highly systematic' if signals_a >= 8 else ('moderately systematic' if signals_a >= 4 else 'organic/editorial')
        label_b = 'highly systematic' if signals_b >= 8 else ('moderately systematic' if signals_b >= 4 else 'organic/editorial')

        comparison = ""
        if label_a != label_b:
            comparison = f"{self.name_a} leans {label_a} with defined design tokens; {self.name_b} is more {label_b}."
        else:
            comparison = f"Both sites operate at a {label_a} level of design systematization."

        return {'site_a': label_a, 'site_b': label_b, 'comparison': comparison}

    def _axis_personality(self, diffs: Dict) -> Dict:
        """Infer archetype from combined signals."""
        arch_a = self._infer_archetype(self.a)
        arch_b = self._infer_archetype(self.b)

        comparison = ""
        if arch_a != arch_b:
            comparison = f"{self.name_a} projects a {arch_a} identity while {self.name_b} reads as {arch_b}."
        else:
            comparison = f"Both sites share a {arch_a} design identity."

        return {
            'site_a_archetype': arch_a,
            'site_b_archetype': arch_b,
            'comparison': comparison,
        }

    def _rank_differentiators(self, metric_diffs: Dict) -> List[Dict]:
        """Rank top 5 differences by weighted divergence."""
        items = []
        for key, label, _ in self.METRIC_CATEGORIES:
            diff = metric_diffs.get(key)
            if not diff:
                continue
            raw_score = diff.get('divergence_score', 0)
            weight = self.IMPACT_WEIGHTS.get(key, 1.0)
            weighted = round(raw_score * weight)
            if weighted < 10:
                continue

            # Build insight from most meaningful difference (longest interpretation = most specific)
            all_diffs = diff.get('differences', [])
            top_diff = max(all_diffs, key=lambda d: len(d.get('interpretation', ''))) if all_diffs else None
            insight = top_diff['interpretation'] if top_diff else ''
            site_a_detail = top_diff['site_a'] if top_diff else ''
            site_b_detail = top_diff['site_b'] if top_diff else ''

            items.append({
                'area': label,
                'divergence_score': weighted,
                'insight': insight,
                'site_a_detail': site_a_detail,
                'site_b_detail': site_b_detail,
            })

        items.sort(key=lambda x: x['divergence_score'], reverse=True)

        for i, item in enumerate(items[:5]):
            item['rank'] = i + 1

        return items[:5]

    def _find_commonalities(self, metric_diffs: Dict) -> List[Dict]:
        """Find metrics where both sites converge."""
        common = []
        for key, label, _ in self.METRIC_CATEGORIES:
            diff = metric_diffs.get(key)
            if not diff:
                continue
            if diff.get('divergence_score', 100) <= 15:
                shared = diff['differences'][0] if diff.get('differences') else None
                if shared:
                    common.append({
                        'area': label,
                        'insight': f"Both sites share similar {label.lower()} characteristics.",
                        'shared_detail': shared.get('site_a', ''),
                    })
        return common

    def _generate_summary(self, philosophy: Dict, differentiators: List, commonalities: List) -> str:
        """Build a 3-5 sentence summary paragraph."""
        parts = []

        # Opening
        common_count = len(commonalities)
        if differentiators:
            top_area = differentiators[0]['area']
            parts.append(f"{self.name_a} and {self.name_b} share {common_count} design convention{'s' if common_count != 1 else ''} but diverge most sharply in {top_area}.")
        else:
            parts.append(f"{self.name_a} and {self.name_b} share broadly similar design characteristics.")

        # Personality contrast
        pers = philosophy.get('personality', {})
        arch_a = pers.get('site_a_archetype', '')
        arch_b = pers.get('site_b_archetype', '')
        if arch_a and arch_b and arch_a != arch_b:
            parts.append(f"{self.name_a} projects a {arch_a} identity while {self.name_b} reads as {arch_b}.")

        # Top differentiator evidence
        if differentiators:
            top = differentiators[0]
            parts.append(f"The most striking difference: {top['insight']}")

        # Density/posture contrast
        density = philosophy.get('visual_density', {})
        if density.get('comparison'):
            parts.append(density['comparison'])

        # Commonality note
        if commonalities:
            areas = [c['area'].lower() for c in commonalities[:2]]
            parts.append(f"They share common ground in {' and '.join(areas)}.")

        return ' '.join(parts)

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _safe_get(self, data: Any, *keys, default=None) -> Any:
        """Deep-get with type safety at each level."""
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
            if current is None:
                return default
        return current

    def _both_have(self, key: str, min_confidence: int = 30) -> bool:
        """True if both evidence dicts have the key with sufficient confidence."""
        a = self.a.get(key, {})
        b = self.b.get(key, {})
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        ca = a.get('confidence', 0) or 0
        cb = b.get('confidence', 0) or 0
        return ca >= min_confidence and cb >= min_confidence

    def _skip_reason(self, key: str) -> str:
        a = self.a.get(key, {})
        b = self.b.get(key, {})
        ca = a.get('confidence', 0) if isinstance(a, dict) else 0
        cb = b.get('confidence', 0) if isinstance(b, dict) else 0
        if (ca or 0) < 30 and (cb or 0) < 30:
            return 'Insufficient confidence on both sites'
        if (ca or 0) < 30:
            return f'Insufficient confidence on {self.name_a} ({ca}%)'
        return f'Insufficient confidence on {self.name_b} ({cb}%)'

    @staticmethod
    def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
        return max(lo, min(hi, round(value)))

    @staticmethod
    def _parse_base_unit(val) -> Optional[float]:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            m = re.match(r'([\d.]+)', val.strip())
            return float(m.group(1)) if m else None
        return None

    @staticmethod
    def _parse_px_val(s: str) -> Optional[float]:
        if not s:
            return None
        m = re.search(r'([\d.]+)', str(s))
        return float(m.group(1)) if m else None

    @staticmethod
    def _parse_int_list(vals) -> List[int]:
        result = []
        if not isinstance(vals, list):
            return result
        for v in vals:
            try:
                result.append(int(v))
            except (ValueError, TypeError):
                pass
        return result

    def _extract_font_names(self, typo: Dict) -> List[str]:
        fonts = typo.get('fonts_detected', [])
        names = []
        if isinstance(fonts, list):
            for f in fonts:
                if isinstance(f, dict):
                    name = f.get('family', '')
                elif isinstance(f, str):
                    name = f
                else:
                    continue
                clean = name.split(',')[0].strip().strip('"').strip("'")
                if clean and clean not in names:
                    names.append(clean)
        return names

    @staticmethod
    def _classify_font_personality(font_name: str) -> str:
        name = font_name.lower()
        if any(kw in name for kw in ['inter', 'roboto', 'sf pro', 'sohne', 'helvetica', 'arial', 'system-ui']):
            return 'technical/modern'
        if any(kw in name for kw in ['open sans', 'lato', 'nunito', 'poppins', 'source sans', 'work sans']):
            return 'friendly/approachable'
        if any(kw in name for kw in ['serif', 'georgia', 'times', 'merriweather', 'playfair', 'livory', 'garamond', 'palatino']):
            return 'editorial/authoritative'
        if any(kw in name for kw in ['mono', 'courier', 'code', 'consolas', 'jetbrains', 'fira code']):
            return 'developer-focused'
        if any(kw in name for kw in ['display', 'decorative', 'script', 'cursive', 'brush']):
            return 'expressive/branded'
        return 'neutral'

    def _palette_size(self, colors: Dict) -> int:
        palette = colors.get('palette', {})
        if isinstance(palette, dict):
            return sum(len(v) for v in palette.values() if isinstance(v, list))
        if isinstance(palette, list):
            return len(palette)
        return 0

    def _detect_bg_strategy(self, colors: Dict) -> str:
        roles = colors.get('color_roles', {})
        if isinstance(roles, dict):
            bg = roles.get('background', roles.get('bg', ''))
            if isinstance(bg, str) and bg.startswith('#'):
                try:
                    r, g, b_val = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                    luminance = (0.299 * r + 0.587 * g + 0.114 * b_val) / 255
                    return 'dark' if luminance < 0.4 else 'light'
                except (ValueError, IndexError):
                    pass
        return 'light'

    def _palette_temperature(self, colors: Dict) -> Optional[str]:
        palette = colors.get('palette', {})
        hex_colors = []
        if isinstance(palette, dict):
            for v in palette.values():
                if isinstance(v, list):
                    hex_colors.extend(c for c in v if isinstance(c, str) and c.startswith('#'))
        if len(hex_colors) < 2:
            return None
        hues = []
        for c in hex_colors[:10]:
            try:
                r, g, b_val = int(c[1:3], 16) / 255, int(c[3:5], 16) / 255, int(c[5:7], 16) / 255
                h, _, s = colorsys.rgb_to_hls(r, g, b_val)
                if s > 0.1:  # Skip near-grays
                    hues.append(h * 360)
            except (ValueError, IndexError):
                pass
        if not hues:
            return 'neutral'
        avg_hue = statistics.mean(hues)
        if 0 <= avg_hue < 60 or avg_hue > 300:
            return 'warm'
        if 160 <= avg_hue <= 280:
            return 'cool'
        return 'neutral'

    # ──────────────────────────────────────────────
    # Intent interpretation helpers
    # ──────────────────────────────────────────────

    def _font_intent(self, pers_a: str, pers_b: str) -> str:
        if pers_a == pers_b:
            return f"Both sites use {pers_a} typography, suggesting similar brand positioning."
        return f"{self.name_a}'s {pers_a} typography vs {self.name_b}'s {pers_b} typography signals different brand identities and target audiences."

    def _scale_ratio_intent(self, ra: float, rb: float) -> str:
        if abs(ra - rb) < 0.05:
            return "Nearly identical type scale ratios indicate similar heading-to-body contrast."
        label_a = 'dramatic' if ra >= 1.5 else ('moderate' if ra >= 1.25 else 'subtle')
        label_b = 'dramatic' if rb >= 1.5 else ('moderate' if rb >= 1.25 else 'subtle')
        if label_a == label_b:
            return f"Both use {label_a} type scale progression."
        return f"{self.name_a}'s {label_a} ratio ({ra:.2f}) creates {'strong visual drama' if ra > rb else 'understated hierarchy'} compared to {self.name_b}'s {label_b} ratio ({rb:.2f})."

    def _font_count_intent(self, ca: int, cb: int) -> str:
        more = self.name_a if ca > cb else self.name_b
        fewer = self.name_b if ca > cb else self.name_a
        return f"{more} uses more typefaces suggesting editorial diversity; {fewer}'s constrained typography indicates systematic design."

    def _palette_size_intent(self, sa: int, sb: int) -> str:
        if abs(sa - sb) <= 2:
            return "Similar palette sizes suggest comparable visual complexity."
        larger = self.name_a if sa > sb else self.name_b
        smaller = self.name_b if sa > sb else self.name_a
        return f"{larger}'s broader palette ({max(sa, sb)} colors) suggests editorial flexibility; {smaller}'s tighter palette ({min(sa, sb)} colors) indicates disciplined design system usage."

    def _spacing_intent(self, ba: float, bb: float) -> str:
        if ba == bb:
            return f"Identical {ba}px base unit suggests shared spacing conventions."
        label_a = self._spacing_label(ba)
        label_b = self._spacing_label(bb)
        return f"{self.name_a}'s {ba}px base ({label_a}) vs {self.name_b}'s {bb}px base ({label_b})."

    @staticmethod
    def _spacing_label(base: float) -> str:
        if base <= 4:
            return 'compact, information-dense'
        if base <= 8:
            return 'balanced, standard rhythm'
        return 'generous, premium breathing room'

    @staticmethod
    def _shadow_depth_label(count: int) -> str:
        if count == 0:
            return 'flat design'
        if count <= 2:
            return 'subtle depth'
        if count <= 4:
            return 'moderate elevation'
        return 'rich elevation system'

    def _shadow_intent(self, la: int, lb: int, da: str, db: str) -> str:
        if la == lb:
            return f"Both sites use {da} with {la} shadow levels."
        more = self.name_a if la > lb else self.name_b
        fewer = self.name_b if la > lb else self.name_a
        return f"{more}'s {max(la, lb)}-level elevation creates tactile depth; {fewer}'s {self._shadow_depth_label(min(la, lb))} keeps the design minimal."

    def _motion_timing_intent(self, da, db) -> str:
        def parse_ms(v):
            s = str(v)
            m = re.search(r'([\d.]+)', s)
            if not m:
                return None
            val = float(m.group(1))
            if 'ms' in s or val > 10:
                return val
            return val * 1000  # seconds to ms

        ms_a = parse_ms(da)
        ms_b = parse_ms(db)
        if ms_a and ms_b:
            if abs(ms_a - ms_b) < 50:
                return "Similar timing suggests both prioritize the same interaction speed."
            faster = self.name_a if ms_a < ms_b else self.name_b
            slower = self.name_b if ms_a < ms_b else self.name_a
            return f"{faster} uses snappier transitions for functional responsiveness; {slower} uses slower timing for cinematic effect."
        return "Different motion timing reflects different interaction philosophies."

    @staticmethod
    def _layout_strategy(flex: int, grid: int) -> str:
        total = flex + grid
        if total == 0:
            return 'Minimal'
        if grid == 0:
            return 'Flex-dominant'
        if flex == 0:
            return 'Grid-dominant'
        ratio = grid / total
        if ratio > 0.4:
            return 'Grid-heavy hybrid'
        return 'Flex-heavy hybrid'

    def _layout_intent(self, sa: str, sb: str) -> str:
        if sa == sb:
            return f"Both sites use a {sa.lower()} layout approach."
        return f"{self.name_a}'s {sa.lower()} layout vs {self.name_b}'s {sb.lower()} layout reflects different structural priorities."

    def _density_intent(self, da: float, db: float) -> str:
        if abs(da - db) < 5:
            return "Similar content density suggests comparable information priorities."
        denser = self.name_a if da > db else self.name_b
        sparser = self.name_b if da > db else self.name_a
        return f"{denser}'s higher density ({max(da, db):.0f}%) prioritizes information throughput; {sparser}'s lower density ({min(da, db):.0f}%) creates breathing room."

    def _hero_intent(self, ha: bool, hb: bool) -> str:
        if ha == hb:
            return 'Both sites use hero sections for initial impact.' if ha else 'Neither site relies on a hero section, favoring content-first layouts.'
        has = self.name_a if ha else self.name_b
        hasnt = self.name_b if ha else self.name_a
        return f"{has} leads with a hero section for visual impact; {hasnt} distributes attention more evenly across content."

    def _cta_intent(self, ca: bool, cb: bool) -> str:
        if ca == cb:
            return 'Both sites feature prominent calls-to-action, indicating conversion focus.' if ca else 'Neither site emphasizes a primary CTA, suggesting content/exploration focus.'
        has = self.name_a if ca else self.name_b
        hasnt = self.name_b if ca else self.name_a
        return f"{has} drives toward conversion with a clear CTA; {hasnt} takes a more passive, exploratory approach."

    def _density_label(self, base: Optional[float], evidence: Dict) -> str:
        sc = evidence.get('spatial_composition', {})
        density = self._safe_get(sc, 'whitespace_analysis', 'content_density_pct', default=None)
        shadow_count = len(evidence.get('shadow_system', {}).get('levels', []))

        if isinstance(density, (int, float)) and density > 60:
            return 'dense and information-rich'
        if isinstance(density, (int, float)) and density < 35:
            return 'spacious and luxurious'
        if base and base >= 12:
            return 'generous and breathing'
        if base and base <= 4:
            return 'tight and compact'
        if shadow_count >= 4:
            return 'layered and dimensional'
        return 'balanced'

    @staticmethod
    def _posture_label(has_hero: bool, has_cta: bool, anim_count: int) -> str:
        score = 0
        if has_hero:
            score += 2
        if has_cta:
            score += 3
        if anim_count > 5:
            score += 2
        elif anim_count > 0:
            score += 1

        if score >= 5:
            return 'conversion-driven'
        if score >= 3:
            return 'engagement-focused'
        return 'content-consumption oriented'

    def _infer_archetype(self, evidence: Dict) -> str:
        """Adapted from DesignBriefGenerator._infer_personality."""
        spacing = evidence.get('spacing_scale', {})
        scale = spacing.get('scale', spacing.get('values', []))
        avg_spacing = statistics.mean(scale) if isinstance(scale, list) and scale else 16

        shadow_count = len(evidence.get('shadow_system', {}).get('levels', []))

        motion = evidence.get('motion_tokens', {})
        details = motion.get('details', {}) if isinstance(motion.get('details'), dict) else {}
        anims = details.get('animations', [])
        has_animations = len(anims) if isinstance(anims, list) else 0

        fonts = self._extract_font_names(evidence.get('typography', {}))
        font_pers = self._classify_font_personality(fonts[0]) if fonts else 'neutral'

        if font_pers == 'editorial/authoritative':
            return 'refined and editorial'
        if font_pers == 'developer-focused':
            return 'technical and developer-centric'
        if avg_spacing > 24 and shadow_count >= 3:
            return 'premium and polished'
        if avg_spacing < 12 and shadow_count < 2:
            return 'compact and utilitarian'
        if has_animations > 5:
            return 'dynamic and immersive'
        if shadow_count >= 4:
            return 'layered and dimensional'
        if font_pers == 'friendly/approachable':
            return 'approachable and modern'
        return 'clean and professional'

    def _compute_typo_divergence(self, a: Dict, b: Dict) -> int:
        score = 0
        fonts_a = self._extract_font_names(a)
        fonts_b = self._extract_font_names(b)
        pers_a = self._classify_font_personality(fonts_a[0]) if fonts_a else 'unknown'
        pers_b = self._classify_font_personality(fonts_b[0]) if fonts_b else 'unknown'
        if pers_a != pers_b:
            score += 30
        ratio_a = self._safe_get(a, 'type_scale', 'ratio', default=1.2)
        ratio_b = self._safe_get(b, 'type_scale', 'ratio', default=1.2)
        if isinstance(ratio_a, (int, float)) and isinstance(ratio_b, (int, float)):
            score += min(abs(ratio_a - ratio_b) * 50, 25)
        score += min(abs(len(fonts_a) - len(fonts_b)) * 10, 20)
        return self._clamp(score)
