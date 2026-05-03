"""
Component Translator — CSS Computed Values to Tailwind v4 Semantic Classes

Converts raw computed CSS values (from window.getComputedStyle) to their nearest
Tailwind v4 utility classes. Uses pure lookup tables — no Node.js, no external deps.

Three matching strategies:
  1. Exact match   — font-size 14px → text-sm
  2. Computed match — padding 16px → p-4 (16/4 = 4 on Tailwind's scale)
  3. Perceptual match — rgb(83,58,253) → indigo-600 (ΔE < 5.0 via CIE76)

Usage:
    from component_translator import TailwindTranslator
    t = TailwindTranslator()
    t.spacing_to_tw('16px')          # → 'p-4'
    t.color_to_tw('rgb(83, 58, 253)')  # → 'indigo-600'
    t.translate({'fontSize': '14px', 'fontWeight': '700'})  # → {'fontSize': 'text-sm', 'fontWeight': 'font-bold'}
"""

import re
from typing import Dict, Optional

from design_debt_analyzer import _hex_to_rgb, _rgb_to_lab, _delta_e, _normalize_color


# ---------------------------------------------------------------------------
# Exact-match lookup tables
# ---------------------------------------------------------------------------

FONT_SIZE_MAP = {
    '12px': 'text-xs',
    '14px': 'text-sm',
    '16px': 'text-base',
    '18px': 'text-lg',
    '20px': 'text-xl',
    '24px': 'text-2xl',
    '30px': 'text-3xl',
    '36px': 'text-4xl',
    '48px': 'text-5xl',
    '60px': 'text-6xl',
    '72px': 'text-7xl',
    '96px': 'text-8xl',
    '128px': 'text-9xl',
}

FONT_WEIGHT_MAP = {
    '100': 'font-thin',
    '200': 'font-extralight',
    '300': 'font-light',
    '400': 'font-normal',
    '500': 'font-medium',
    '600': 'font-semibold',
    '700': 'font-bold',
    '800': 'font-extrabold',
    '900': 'font-black',
}

LINE_HEIGHT_MAP = {
    '1':    'leading-none',
    '1.25': 'leading-tight',
    '1.375': 'leading-snug',
    '1.5':  'leading-normal',
    '1.625': 'leading-relaxed',
    '2':    'leading-loose',
}

LETTER_SPACING_MAP = {
    '-0.05em': 'tracking-tighter',
    '-0.025em': 'tracking-tight',
    '0em':     'tracking-normal',
    '0.025em': 'tracking-wide',
    '0.05em':  'tracking-wider',
    '0.1em':   'tracking-widest',
}

BORDER_RADIUS_MAP = {
    '0px':    'rounded-none',
    '2px':    'rounded-sm',
    '4px':    'rounded',
    '6px':    'rounded-md',
    '8px':    'rounded-lg',
    '12px':   'rounded-xl',
    '16px':   'rounded-2xl',
    '24px':   'rounded-3xl',
    '9999px': 'rounded-full',
}

OPACITY_MAP = {
    '0':    'opacity-0',
    '0.05': 'opacity-5',
    '0.1':  'opacity-10',
    '0.15': 'opacity-15',
    '0.2':  'opacity-20',
    '0.25': 'opacity-25',
    '0.3':  'opacity-30',
    '0.35': 'opacity-35',
    '0.4':  'opacity-40',
    '0.45': 'opacity-45',
    '0.5':  'opacity-50',
    '0.55': 'opacity-55',
    '0.6':  'opacity-60',
    '0.65': 'opacity-65',
    '0.7':  'opacity-70',
    '0.75': 'opacity-75',
    '0.8':  'opacity-80',
    '0.85': 'opacity-85',
    '0.9':  'opacity-90',
    '0.95': 'opacity-95',
    '1':    'opacity-100',
}

# Shadow matching by blur radius ranges (from parsed box-shadow)
# Format: (max_blur_px, tailwind_class)
SHADOW_TIERS = [
    (0,   'shadow-none'),
    (2,   'shadow-xs'),
    (4,   'shadow-sm'),
    (8,   'shadow'),
    (15,  'shadow-md'),
    (25,  'shadow-lg'),
    (50,  'shadow-xl'),
    (999, 'shadow-2xl'),
]


# ---------------------------------------------------------------------------
# Tailwind v4 default color palette — hex values
# 22 color families × 11 shades = 242 entries
# ---------------------------------------------------------------------------

TAILWIND_V4_COLORS = {
    # Slate
    'slate-50': '#f8fafc', 'slate-100': '#f1f5f9', 'slate-200': '#e2e8f0',
    'slate-300': '#cbd5e1', 'slate-400': '#94a3b8', 'slate-500': '#64748b',
    'slate-600': '#475569', 'slate-700': '#334155', 'slate-800': '#1e293b',
    'slate-900': '#0f172a', 'slate-950': '#020617',
    # Gray
    'gray-50': '#f9fafb', 'gray-100': '#f3f4f6', 'gray-200': '#e5e7eb',
    'gray-300': '#d1d5db', 'gray-400': '#9ca3af', 'gray-500': '#6b7280',
    'gray-600': '#4b5563', 'gray-700': '#374151', 'gray-800': '#1f2937',
    'gray-900': '#111827', 'gray-950': '#030712',
    # Zinc
    'zinc-50': '#fafafa', 'zinc-100': '#f4f4f5', 'zinc-200': '#e4e4e7',
    'zinc-300': '#d4d4d8', 'zinc-400': '#a1a1aa', 'zinc-500': '#71717a',
    'zinc-600': '#52525b', 'zinc-700': '#3f3f46', 'zinc-800': '#27272a',
    'zinc-900': '#18181b', 'zinc-950': '#09090b',
    # Neutral
    'neutral-50': '#fafafa', 'neutral-100': '#f5f5f5', 'neutral-200': '#e5e5e5',
    'neutral-300': '#d4d4d4', 'neutral-400': '#a3a3a3', 'neutral-500': '#737373',
    'neutral-600': '#525252', 'neutral-700': '#404040', 'neutral-800': '#262626',
    'neutral-900': '#171717', 'neutral-950': '#0a0a0a',
    # Stone
    'stone-50': '#fafaf9', 'stone-100': '#f5f5f4', 'stone-200': '#e7e5e4',
    'stone-300': '#d6d3d1', 'stone-400': '#a8a29e', 'stone-500': '#78716c',
    'stone-600': '#57534e', 'stone-700': '#44403c', 'stone-800': '#292524',
    'stone-900': '#1c1917', 'stone-950': '#0c0a09',
    # Red
    'red-50': '#fef2f2', 'red-100': '#fee2e2', 'red-200': '#fecaca',
    'red-300': '#fca5a5', 'red-400': '#f87171', 'red-500': '#ef4444',
    'red-600': '#dc2626', 'red-700': '#b91c1c', 'red-800': '#991b1b',
    'red-900': '#7f1d1d', 'red-950': '#450a0a',
    # Orange
    'orange-50': '#fff7ed', 'orange-100': '#ffedd5', 'orange-200': '#fed7aa',
    'orange-300': '#fdba74', 'orange-400': '#fb923c', 'orange-500': '#f97316',
    'orange-600': '#ea580c', 'orange-700': '#c2410c', 'orange-800': '#9a3412',
    'orange-900': '#7c2d12', 'orange-950': '#431407',
    # Amber
    'amber-50': '#fffbeb', 'amber-100': '#fef3c7', 'amber-200': '#fde68a',
    'amber-300': '#fcd34d', 'amber-400': '#fbbf24', 'amber-500': '#f59e0b',
    'amber-600': '#d97706', 'amber-700': '#b45309', 'amber-800': '#92400e',
    'amber-900': '#78350f', 'amber-950': '#451a03',
    # Yellow
    'yellow-50': '#fefce8', 'yellow-100': '#fef9c3', 'yellow-200': '#fef08a',
    'yellow-300': '#fde047', 'yellow-400': '#facc15', 'yellow-500': '#eab308',
    'yellow-600': '#ca8a04', 'yellow-700': '#a16207', 'yellow-800': '#854d0e',
    'yellow-900': '#713f12', 'yellow-950': '#422006',
    # Lime
    'lime-50': '#f7fee7', 'lime-100': '#ecfccb', 'lime-200': '#d9f99d',
    'lime-300': '#bef264', 'lime-400': '#a3e635', 'lime-500': '#84cc16',
    'lime-600': '#65a30d', 'lime-700': '#4d7c0f', 'lime-800': '#3f6212',
    'lime-900': '#365314', 'lime-950': '#1a2e05',
    # Green
    'green-50': '#f0fdf4', 'green-100': '#dcfce7', 'green-200': '#bbf7d0',
    'green-300': '#86efac', 'green-400': '#4ade80', 'green-500': '#22c55e',
    'green-600': '#16a34a', 'green-700': '#15803d', 'green-800': '#166534',
    'green-900': '#14532d', 'green-950': '#052e16',
    # Emerald
    'emerald-50': '#ecfdf5', 'emerald-100': '#d1fae5', 'emerald-200': '#a7f3d0',
    'emerald-300': '#6ee7b7', 'emerald-400': '#34d399', 'emerald-500': '#10b981',
    'emerald-600': '#059669', 'emerald-700': '#047857', 'emerald-800': '#065f46',
    'emerald-900': '#064e3b', 'emerald-950': '#022c22',
    # Teal
    'teal-50': '#f0fdfa', 'teal-100': '#ccfbf1', 'teal-200': '#99f6e4',
    'teal-300': '#5eead4', 'teal-400': '#2dd4bf', 'teal-500': '#14b8a6',
    'teal-600': '#0d9488', 'teal-700': '#0f766e', 'teal-800': '#115e59',
    'teal-900': '#134e4a', 'teal-950': '#042f2e',
    # Cyan
    'cyan-50': '#ecfeff', 'cyan-100': '#cffafe', 'cyan-200': '#a5f3fc',
    'cyan-300': '#67e8f9', 'cyan-400': '#22d3ee', 'cyan-500': '#06b6d4',
    'cyan-600': '#0891b2', 'cyan-700': '#0e7490', 'cyan-800': '#155e75',
    'cyan-900': '#164e63', 'cyan-950': '#083344',
    # Sky
    'sky-50': '#f0f9ff', 'sky-100': '#e0f2fe', 'sky-200': '#bae6fd',
    'sky-300': '#7dd3fc', 'sky-400': '#38bdf8', 'sky-500': '#0ea5e9',
    'sky-600': '#0284c7', 'sky-700': '#0369a1', 'sky-800': '#075985',
    'sky-900': '#0c4a6e', 'sky-950': '#082f49',
    # Blue
    'blue-50': '#eff6ff', 'blue-100': '#dbeafe', 'blue-200': '#bfdbfe',
    'blue-300': '#93c5fd', 'blue-400': '#60a5fa', 'blue-500': '#3b82f6',
    'blue-600': '#2563eb', 'blue-700': '#1d4ed8', 'blue-800': '#1e40af',
    'blue-900': '#1e3a8a', 'blue-950': '#172554',
    # Indigo
    'indigo-50': '#eef2ff', 'indigo-100': '#e0e7ff', 'indigo-200': '#c7d2fe',
    'indigo-300': '#a5b4fc', 'indigo-400': '#818cf8', 'indigo-500': '#6366f1',
    'indigo-600': '#4f46e5', 'indigo-700': '#4338ca', 'indigo-800': '#3730a3',
    'indigo-900': '#312e81', 'indigo-950': '#1e1b4b',
    # Violet
    'violet-50': '#f5f3ff', 'violet-100': '#ede9fe', 'violet-200': '#ddd6fe',
    'violet-300': '#c4b5fd', 'violet-400': '#a78bfa', 'violet-500': '#8b5cf6',
    'violet-600': '#7c3aed', 'violet-700': '#6d28d9', 'violet-800': '#5b21b6',
    'violet-900': '#4c1d95', 'violet-950': '#2e1065',
    # Purple
    'purple-50': '#faf5ff', 'purple-100': '#f3e8ff', 'purple-200': '#e9d5ff',
    'purple-300': '#d8b4fe', 'purple-400': '#c084fc', 'purple-500': '#a855f7',
    'purple-600': '#9333ea', 'purple-700': '#7e22ce', 'purple-800': '#6b21a8',
    'purple-900': '#581c87', 'purple-950': '#3b0764',
    # Fuchsia
    'fuchsia-50': '#fdf4ff', 'fuchsia-100': '#fae8ff', 'fuchsia-200': '#f5d0fe',
    'fuchsia-300': '#f0abfc', 'fuchsia-400': '#e879f9', 'fuchsia-500': '#d946ef',
    'fuchsia-600': '#c026d3', 'fuchsia-700': '#a21caf', 'fuchsia-800': '#86198f',
    'fuchsia-900': '#701a75', 'fuchsia-950': '#4a044e',
    # Pink
    'pink-50': '#fdf2f8', 'pink-100': '#fce7f3', 'pink-200': '#fbcfe8',
    'pink-300': '#f9a8d4', 'pink-400': '#f472b6', 'pink-500': '#ec4899',
    'pink-600': '#db2777', 'pink-700': '#be185d', 'pink-800': '#9d174d',
    'pink-900': '#831843', 'pink-950': '#500724',
    # Rose
    'rose-50': '#fff1f2', 'rose-100': '#ffe4e6', 'rose-200': '#fecdd3',
    'rose-300': '#fda4af', 'rose-400': '#fb7185', 'rose-500': '#f43f5e',
    'rose-600': '#e11d48', 'rose-700': '#be123c', 'rose-800': '#9f1239',
    'rose-900': '#881337', 'rose-950': '#4c0519',
    # Black & White
    'black': '#000000',
    'white': '#ffffff',
}

# Pre-compute LAB values for fast perceptual matching
_COLOR_LAB_CACHE: Dict[str, tuple] = {}


def _get_color_lab(hex_val: str) -> Optional[tuple]:
    """Get CIELAB values for a hex color, with caching."""
    if hex_val in _COLOR_LAB_CACHE:
        return _COLOR_LAB_CACHE[hex_val]
    rgb = _hex_to_rgb(hex_val)
    if rgb is None:
        return None
    lab = _rgb_to_lab(*rgb)
    _COLOR_LAB_CACHE[hex_val] = lab
    return lab


# ---------------------------------------------------------------------------
# Tailwind spacing scale (value in px → multiplier label)
# ---------------------------------------------------------------------------

# Tailwind's spacing scale: multiplier → px value (base = 4px)
SPACING_SCALE = {
    0: '0', 0.5: '0.5', 1: '1', 1.5: '1.5', 2: '2', 2.5: '2.5',
    3: '3', 3.5: '3.5', 4: '4', 5: '5', 6: '6', 7: '7',
    8: '8', 9: '9', 10: '10', 11: '11', 12: '12',
    14: '14', 16: '16', 20: '20', 24: '24', 28: '28',
    32: '32', 36: '36', 40: '40', 44: '44', 48: '48',
    52: '52', 56: '56', 60: '60', 64: '64', 72: '72',
    80: '80', 96: '96',
}

# Build reverse: px → tailwind label
_PX_TO_SPACING = {round(mult * 4): label for mult, label in SPACING_SCALE.items()}
# Also add 'px' (1px) and 'auto'
_PX_TO_SPACING[1] = 'px'


# ---------------------------------------------------------------------------
# TailwindTranslator class
# ---------------------------------------------------------------------------

class TailwindTranslator:
    """Converts computed CSS values to Tailwind v4 utility classes."""

    _EXACT_THRESHOLD = 5.0       # ΔE below this = near-identical
    _CLOSE_THRESHOLD = 15.0      # ΔE below this = same visual family

    def __init__(self):
        # Pre-warm color LAB cache
        for name, hex_val in TAILWIND_V4_COLORS.items():
            _get_color_lab(hex_val)

    # --- Spacing (padding, margin, gap, width, height) ---

    def spacing_to_tw(self, px_value: str) -> Optional[str]:
        """Convert a px value to Tailwind spacing multiplier.

        '16px' → '4'  (16/4 = 4, on scale)
        '13px' → None  (not on scale, caller should use arbitrary)
        '0px'  → '0'
        """
        px = self._parse_px(px_value)
        if px is None:
            return None
        px_int = round(px)
        if px_int in _PX_TO_SPACING:
            return _PX_TO_SPACING[px_int]
        # Check non-integer (e.g., 2px → 0.5 multiplier)
        if px == 2 and 0.5 in SPACING_SCALE:
            return '0.5'
        return None

    # --- Color matching ---

    def color_to_tw(self, color_str: str, loose: bool = False) -> Optional[str]:
        """Convert a CSS color (rgb, rgba, hex) to nearest Tailwind color name.

        Returns the Tailwind name (e.g., 'indigo-600') or None if no close match.

        Args:
            color_str: CSS color string (rgb, rgba, hex)
            loose:     If True, use _CLOSE_THRESHOLD (ΔE<15, same visual family).
                       If False (default), use _EXACT_THRESHOLD (ΔE<5, near-identical).
        """
        normalized = _normalize_color(color_str)
        if not normalized.startswith('#'):
            return None

        # Tier 1: exact hex match
        for name, hex_val in TAILWIND_V4_COLORS.items():
            if hex_val == normalized:
                return name

        # Tier 2: perceptual match via CIE76 ΔE
        input_rgb = _hex_to_rgb(normalized)
        if input_rgb is None:
            return None
        input_lab = _rgb_to_lab(*input_rgb)

        threshold = self._CLOSE_THRESHOLD if loose else self._EXACT_THRESHOLD
        best_name = None
        best_de = threshold

        for name, hex_val in TAILWIND_V4_COLORS.items():
            lab = _get_color_lab(hex_val)
            if lab is None:
                continue
            de = ((input_lab[0] - lab[0]) ** 2 +
                  (input_lab[1] - lab[1]) ** 2 +
                  (input_lab[2] - lab[2]) ** 2) ** 0.5
            if de < best_de:
                best_de = de
                best_name = name

        return best_name  # None if nothing below threshold

    # --- Font size ---

    def font_size_to_tw(self, value: str) -> Optional[str]:
        """Convert font-size px value to Tailwind class."""
        # Normalize: '14.4px' → try closest
        px = self._parse_px(value)
        if px is None:
            return None
        # Try exact match first
        key = f'{int(px)}px' if px == int(px) else f'{px}px'
        if key in FONT_SIZE_MAP:
            return FONT_SIZE_MAP[key]
        # Try nearest integer
        rounded = f'{round(px)}px'
        return FONT_SIZE_MAP.get(rounded)

    # --- Font weight ---

    def font_weight_to_tw(self, value: str) -> Optional[str]:
        """Convert font-weight numeric value to Tailwind class."""
        val = str(value).strip()
        # Handle 'normal' / 'bold' keywords
        if val == 'normal':
            val = '400'
        elif val == 'bold':
            val = '700'
        return FONT_WEIGHT_MAP.get(val)

    # --- Border radius ---

    def border_radius_to_tw(self, value: str) -> Optional[str]:
        """Convert border-radius to Tailwind class."""
        px = self._parse_px(value)
        if px is None:
            return None
        key = f'{int(px)}px' if px == int(px) else f'{px}px'
        if key in BORDER_RADIUS_MAP:
            return BORDER_RADIUS_MAP[key]
        # Try nearest known value
        rounded = f'{round(px)}px'
        return BORDER_RADIUS_MAP.get(rounded)

    # --- Box shadow ---

    def shadow_to_tw(self, value: str) -> Optional[str]:
        """Convert box-shadow to Tailwind shadow class by blur radius."""
        if not value or value == 'none':
            return 'shadow-none'
        # Parse blur radius from box-shadow: offsetX offsetY blur spread color
        # e.g., 'rgb(0, 0, 0) 0px 1px 3px 0px'  or  '0px 1px 3px 0px rgba(0,0,0,0.1)'
        # Find all px numbers
        nums = re.findall(r'(-?\d+(?:\.\d+)?)px', value)
        if len(nums) >= 3:
            blur = abs(float(nums[2]))
        elif len(nums) >= 1:
            blur = abs(float(nums[0]))
        else:
            return None
        for max_blur, tw_class in SHADOW_TIERS:
            if blur <= max_blur:
                return tw_class
        return 'shadow-2xl'

    # --- Opacity ---

    def opacity_to_tw(self, value: str) -> Optional[str]:
        """Convert opacity value to Tailwind class."""
        try:
            val = str(float(value))
            # Round to 2 decimal places
            rounded = str(round(float(value), 2))
            return OPACITY_MAP.get(val) or OPACITY_MAP.get(rounded)
        except (ValueError, TypeError):
            return None

    # --- Main translate method ---

    def translate(self, computed_styles: dict) -> Dict[str, str]:
        """Translate a dict of computed CSS properties to Tailwind classes.

        Input:  {'fontSize': '14px', 'fontWeight': '700', 'backgroundColor': 'rgb(83, 58, 253)', ...}
        Output: {'fontSize': 'text-sm', 'fontWeight': 'font-bold', 'backgroundColor': 'bg-indigo-600', ...}

        Only returns properties that have a Tailwind match. Properties without
        a match are omitted (caller can use arbitrary values for those).
        """
        result = {}

        # Typography
        if 'fontSize' in computed_styles:
            tw = self.font_size_to_tw(computed_styles['fontSize'])
            if tw:
                result['fontSize'] = tw

        if 'fontWeight' in computed_styles:
            tw = self.font_weight_to_tw(computed_styles['fontWeight'])
            if tw:
                result['fontWeight'] = tw

        if 'lineHeight' in computed_styles:
            val = computed_styles['lineHeight']
            if val in LINE_HEIGHT_MAP:
                result['lineHeight'] = LINE_HEIGHT_MAP[val]

        if 'letterSpacing' in computed_styles:
            val = computed_styles['letterSpacing']
            if val in LETTER_SPACING_MAP:
                result['letterSpacing'] = LETTER_SPACING_MAP[val]

        # Colors (use loose matching for better design-level mapping)
        for prop, prefix in [
            ('backgroundColor', 'bg'),
            ('color', 'text'),
            ('borderColor', 'border'),
        ]:
            if prop in computed_styles:
                tw_name = self.color_to_tw(computed_styles[prop], loose=True)
                if tw_name:
                    result[prop] = f'{prefix}-{tw_name}'

        # Spacing — padding
        for prop, prefix in [
            ('padding', 'p'), ('paddingTop', 'pt'), ('paddingRight', 'pr'),
            ('paddingBottom', 'pb'), ('paddingLeft', 'pl'),
        ]:
            if prop in computed_styles:
                mult = self.spacing_to_tw(computed_styles[prop])
                if mult is not None:
                    result[prop] = f'{prefix}-{mult}'

        # Spacing — margin
        for prop, prefix in [
            ('margin', 'm'), ('marginTop', 'mt'), ('marginRight', 'mr'),
            ('marginBottom', 'mb'), ('marginLeft', 'ml'),
        ]:
            if prop in computed_styles:
                mult = self.spacing_to_tw(computed_styles[prop])
                if mult is not None:
                    result[prop] = f'{prefix}-{mult}'

        # Gap
        if 'gap' in computed_styles:
            mult = self.spacing_to_tw(computed_styles['gap'])
            if mult is not None:
                result['gap'] = f'gap-{mult}'

        # Sizing
        for prop, prefix in [('width', 'w'), ('height', 'h'), ('maxWidth', 'max-w')]:
            if prop in computed_styles:
                mult = self.spacing_to_tw(computed_styles[prop])
                if mult is not None:
                    result[prop] = f'{prefix}-{mult}'

        # Border radius
        if 'borderRadius' in computed_styles:
            tw = self.border_radius_to_tw(computed_styles['borderRadius'])
            if tw:
                result['borderRadius'] = tw

        # Box shadow
        if 'boxShadow' in computed_styles:
            tw = self.shadow_to_tw(computed_styles['boxShadow'])
            if tw:
                result['boxShadow'] = tw

        # Opacity
        if 'opacity' in computed_styles:
            tw = self.opacity_to_tw(computed_styles['opacity'])
            if tw:
                result['opacity'] = tw

        return result

    # --- Helpers ---

    @staticmethod
    def _parse_px(value: str) -> Optional[float]:
        """Extract numeric px value from a CSS string like '16px' or '0'."""
        if not value:
            return None
        value = str(value).strip()
        if value == '0':
            return 0.0
        m = re.match(r'^(-?\d+(?:\.\d+)?)px$', value)
        if m:
            return float(m.group(1))
        return None

    def to_arbitrary(self, prop: str, value: str) -> str:
        """Generate Tailwind arbitrary value syntax for unmapped properties.

        '16px' for padding → 'p-[16px]'
        '#533afd' for bg  → 'bg-[#533afd]'
        """
        prefix_map = {
            'padding': 'p', 'paddingTop': 'pt', 'paddingRight': 'pr',
            'paddingBottom': 'pb', 'paddingLeft': 'pl',
            'margin': 'm', 'marginTop': 'mt', 'marginRight': 'mr',
            'marginBottom': 'mb', 'marginLeft': 'ml',
            'gap': 'gap', 'width': 'w', 'height': 'h', 'maxWidth': 'max-w',
            'fontSize': 'text', 'fontWeight': 'font',
            'backgroundColor': 'bg', 'color': 'text', 'borderColor': 'border',
            'borderRadius': 'rounded', 'boxShadow': 'shadow', 'opacity': 'opacity',
        }
        prefix = prefix_map.get(prop, prop)
        return f'{prefix}-[{value}]'


# ---------------------------------------------------------------------------
# Figma-compatible output generator (Module 3)
# ---------------------------------------------------------------------------

def generate_figma_markdown(
    blueprint: dict,
    states: dict,
    translator: TailwindTranslator,
) -> str:
    """Generate Figma-compatible React+Tailwind JSX markdown from a component blueprint.

    Args:
        blueprint: From ComponentRipper._rip_component()
        states:    From ComponentRipper._extract_component_states() (or empty dict)
        translator: TailwindTranslator instance for CSS→Tailwind conversion

    Returns:
        Markdown string matching Figma MCP's get_design_context format.
    """
    name = blueprint.get('semantic_name', 'Component')
    url = blueprint.get('metadata', {}).get('url', '')
    selector = blueprint.get('selector', '')
    tag = blueprint.get('boxModel', {}).get('display', 'div')
    root_tag = _infer_tag(blueprint)
    confidence = blueprint.get('portability', {}).get('reusability_score', 0)

    # --- Translate computed styles ---
    computed = blueprint.get('computedStyles', {})
    translated = translator.translate(computed)

    # --- Build className from translated values ---
    class_parts = []
    layout = blueprint.get('layout', {})  # captured by ripper: type, columns, direction, etc.

    # Layout — read blueprint['layout'] for full fidelity (computed styles alone miss
    # grid-template-columns, flex-wrap, etc.)
    display = computed.get('display', '')
    if display == 'flex' or display == 'inline-flex':
        class_parts.append('flex' if display == 'flex' else 'inline-flex')

        direction = computed.get('flexDirection', layout.get('direction', ''))
        dir_map = {'column': 'flex-col', 'row-reverse': 'flex-row-reverse',
                   'column-reverse': 'flex-col-reverse'}
        if direction in dir_map:
            class_parts.append(dir_map[direction])

        align = computed.get('alignItems', layout.get('align', ''))
        align_map = {'center': 'items-center', 'flex-start': 'items-start',
                     'flex-end': 'items-end', 'stretch': 'items-stretch',
                     'baseline': 'items-baseline'}
        if align in align_map:
            class_parts.append(align_map[align])

        justify = computed.get('justifyContent', layout.get('justify', ''))
        justify_map = {'center': 'justify-center', 'space-between': 'justify-between',
                       'space-around': 'justify-around', 'space-evenly': 'justify-evenly',
                       'flex-end': 'justify-end', 'flex-start': 'justify-start'}
        if justify in justify_map:
            class_parts.append(justify_map[justify])

        wrap = computed.get('flexWrap', layout.get('wrap', ''))
        if wrap == 'wrap':
            class_parts.append('flex-wrap')
        elif wrap == 'wrap-reverse':
            class_parts.append('flex-wrap-reverse')
        elif wrap == 'nowrap':
            class_parts.append('flex-nowrap')

    elif display == 'grid' or display == 'inline-grid':
        class_parts.append('grid' if display == 'grid' else 'inline-grid')

        # Column count — the most important grid property
        cols_tw = _gridcols_to_tw(layout.get('columns', ''))
        if cols_tw:
            class_parts.append(cols_tw)

        # Auto-flow direction
        auto_flow = (layout.get('autoFlow') or '').strip()
        flow_map = {'column': 'grid-flow-col', 'dense': 'grid-flow-dense',
                    'row dense': 'grid-flow-row-dense', 'column dense': 'grid-flow-col-dense'}
        if auto_flow in flow_map:
            class_parts.append(flow_map[auto_flow])

    # Add translated properties (skip layout props we already handled above)
    skip_in_class = {'display', 'flexDirection', 'alignItems', 'justifyContent', 'flexWrap'}
    for prop, tw_class in translated.items():
        if prop not in skip_in_class:
            class_parts.append(tw_class)

    # --- Add hover/focus variants from states ---
    hover_classes = []
    focus_classes = []
    root_states = states.get('root') or {}

    if root_states.get('hover_delta'):
        hover_translated = translator.translate(root_states['hover_delta'])
        for prop, tw_class in hover_translated.items():
            hover_classes.append(f'hover:{tw_class}')

    if root_states.get('focus_delta'):
        focus_translated = translator.translate(root_states['focus_delta'])
        for prop, tw_class in focus_translated.items():
            focus_classes.append(f'focus:{tw_class}')

    # --- Add transition if present ---
    transition = root_states.get('transition', computed.get('transition', ''))
    if transition and transition != 'none' and transition != 'all 0s ease 0s':
        class_parts.append('transition')
        # Try to extract duration
        dur_match = re.search(r'(\d+(?:\.\d+)?)m?s', transition)
        if dur_match:
            dur_val = float(dur_match.group(1))
            if 'ms' not in dur_match.group(0) and dur_val < 10:
                dur_val *= 1000  # Convert seconds to ms
            dur_ms = int(dur_val)
            dur_map = {75: '75', 100: '100', 150: '150', 200: '200',
                       300: '300', 500: '500', 700: '700', 1000: '1000'}
            closest = min(dur_map.keys(), key=lambda d: abs(d - dur_ms))
            if abs(closest - dur_ms) <= 50:
                class_parts.append(f'duration-{dur_map[closest]}')

    all_classes = class_parts + hover_classes + focus_classes
    class_string = ' '.join(all_classes)

    # --- Build anatomy ---
    anatomy = blueprint.get('anatomy', {})
    anatomy_text = _build_anatomy_text(blueprint, anatomy)

    # --- Build states table ---
    states_table = _build_states_table(states, translator)

    # --- Build tokens section ---
    tokens_text = _build_tokens_section(blueprint, translated, computed)

    # --- Dimensions ---
    box = blueprint.get('boxModel', {})
    width = box.get('width', computed.get('width', ''))
    height = box.get('height', computed.get('height', ''))
    dims_line = ''
    if width or height:
        dims_line = f'\nsize: {width} × {height}'

    # --- Build nested JSX from actual source HTML ---
    children_jsx = _build_children_jsx(blueprint)

    # --- Assemble markdown ---
    md = f"""---
component: {name}
source: {url}
selector: {selector}
semantic: {root_tag} / {_infer_role(blueprint)}
confidence: {confidence}{dims_line}
---

## {name}

### Structure
```jsx
<{root_tag} className="{class_string}">
{children_jsx}
</{root_tag}>
```

### Interactive States
{states_table}

### Design Tokens Used
{tokens_text}

### Anatomy
{anatomy_text}
"""
    return md.strip()


# ---------------------------------------------------------------------------
# Figma AI Prompt Generator (for Figma Make / AI)
# ---------------------------------------------------------------------------

def generate_figma_prompt(blueprint: dict, states: dict, translator: TailwindTranslator) -> str:
    """Generate a natural-language prompt for Figma AI to build the component.

    Describes the component visually: layout, dimensions, colors, typography,
    spacing, children, and interactions — in terms a designer would use.
    """
    name = blueprint.get('semantic_name', 'Component')
    box = blueprint.get('boxModel', {})
    computed = blueprint.get('computedStyles', {})
    layout = blueprint.get('layout', {})
    source_html = blueprint.get('source', {}).get('sourceHTML', '')

    # Dimensions
    width = box.get('width', computed.get('width', 'auto'))
    height = box.get('height', computed.get('height', 'auto'))

    # Layout type
    display = computed.get('display', layout.get('type', 'block'))
    direction = layout.get('direction', computed.get('flexDirection', ''))
    gap = layout.get('gap', computed.get('gap', ''))
    columns = layout.get('columns', '')
    align = computed.get('alignItems', '')
    justify = computed.get('justifyContent', '')

    layout_desc = ''
    if 'flex' in display:
        dir_word = 'horizontal' if direction != 'column' else 'vertical'
        layout_desc = f'{dir_word} flex layout'
        if gap:
            layout_desc += f', {gap} gap'
        if align:
            layout_desc += f', items {align}'
        if justify:
            layout_desc += f', {justify}'
    elif 'grid' in display:
        if columns:
            col_count = len(columns.split()) if columns else 1
            layout_desc = f'{col_count}-column grid layout'
        else:
            layout_desc = 'grid layout'
        if gap:
            layout_desc += f', {gap} gap'
    else:
        layout_desc = 'block layout'

    # Colors
    bg = computed.get('backgroundColor', '')
    fg = computed.get('color', '')
    color_desc = ''
    if bg and bg not in ('rgba(0, 0, 0, 0)', 'transparent'):
        color_desc += f'Background: {bg}. '
    if fg:
        color_desc += f'Text: {fg}. '

    # Typography
    font_size = computed.get('fontSize', '')
    font_weight = computed.get('fontWeight', '')
    font_family = computed.get('fontFamily', '')
    typo_desc = ''
    if font_family:
        typo_desc += font_family.split(',')[0].strip().strip('"\'') + ', '
    if font_size:
        typo_desc += f'{font_size}, '
    if font_weight and font_weight not in ('400', 'normal'):
        weight_names = {'100': 'thin', '200': 'extra-light', '300': 'light',
                        '500': 'medium', '600': 'semibold', '700': 'bold',
                        '800': 'extra-bold', '900': 'black'}
        typo_desc += weight_names.get(font_weight, f'weight {font_weight}') + ', '
    typo_desc = typo_desc.rstrip(', ')

    # Spacing
    padding = computed.get('padding', '')
    if not padding:
        pt = computed.get('paddingTop', '0')
        pr = computed.get('paddingRight', '0')
        pb = computed.get('paddingBottom', '0')
        pl = computed.get('paddingLeft', '0')
        if pt == pr == pb == pl and pt != '0':
            padding = pt
        elif pt != '0' or pr != '0' or pb != '0' or pl != '0':
            padding = f'{pt} {pr} {pb} {pl}'

    # Border / radius
    radius = computed.get('borderRadius', '')
    border = computed.get('borderWidth', '')

    # Parse children from HTML
    children_desc = _describe_children_for_prompt(source_html)

    # Interactive states
    hover_desc = ''
    root_states = (states or {}).get('root') or {}
    if root_states.get('hover_delta'):
        changes = []
        for prop, val in root_states['hover_delta'].items():
            prop_name = re.sub(r'([A-Z])', r' \1', prop).lower().strip()
            changes.append(f'{prop_name} changes to {val}')
        hover_desc = 'On hover: ' + '; '.join(changes[:4]) + '.'

    child_states = (states or {}).get('children', [])
    child_hover_desc = ''
    if child_states:
        for cs in child_states[:3]:
            text = cs.get('text', cs.get('selector', ''))[:20]
            if cs.get('hover_delta'):
                n = len(cs['hover_delta'])
                child_hover_desc += f' "{text}" has {n} hover changes.'

    # Assemble the prompt
    lines = [f'Create a {name} component.']
    lines.append(f'Size: {width} wide × {height} tall.')
    lines.append(f'Layout: {layout_desc}.')

    if color_desc:
        lines.append(color_desc.strip())
    if typo_desc:
        lines.append(f'Typography: {typo_desc}.')
    if padding and padding != '0':
        lines.append(f'Padding: {padding}.')
    if radius and radius != '0px':
        lines.append(f'Border radius: {radius}.')

    lines.append('')
    lines.append('Contents:')
    lines.append(children_desc)

    if hover_desc or child_hover_desc:
        lines.append('')
        lines.append('Interactions:')
        if hover_desc:
            lines.append(hover_desc)
        if child_hover_desc:
            lines.append(child_hover_desc.strip())

    # Network activity (data fetching)
    net = blueprint.get('network_activity', {})
    api_calls = net.get('api_calls', [])
    if api_calls:
        lines.append('')
        lines.append('This component fetches data from:')
        for call in api_calls[:5]:
            method = call.get('method', 'GET')
            url = call.get('url', '')
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                display = parsed.path + ('?' + parsed.query if parsed.query else '')
            except Exception:
                display = url
            lines.append(f'  {method} {display}')

    return '\n'.join(lines)


def _describe_children_for_prompt(html: str) -> str:
    """Parse HTML and describe children in natural language for Figma AI."""
    if not html:
        return '(empty)'
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        root = soup.find()
        if not root:
            return '(empty)'
        lines = []
        _describe_element(root, lines, depth=0, max_depth=3)
        return '\n'.join(lines) if lines else '(empty)'
    except Exception:
        return '(could not parse children)'


def _extract_style_hints(classes: str) -> list:
    """Extract visual styling hints from CSS class names."""
    hints = []
    # Background color
    bg = re.search(r'bg-(\S+)', classes)
    if bg and bg.group(1) not in ('transparent',):
        hints.append(f'bg: {bg.group(1)}')
    # Text color
    tc = re.search(r'(?:^|\s)text-((?:pp-|zinc-|gray-|slate-|neutral-|stone-|red-|orange-|amber-|yellow-|lime-|green-|emerald-|teal-|cyan-|sky-|blue-|indigo-|violet-|purple-|fuchsia-|pink-|rose-|white|black)\S*)', classes)
    if tc:
        hints.append(f'text: {tc.group(1)}')
    # Sizing
    w = re.search(r'w-\[?(\d+(?:px|rem)?)\]?', classes)
    h = re.search(r'h-\[?(\d+(?:px|rem)?)\]?', classes)
    if w:
        hints.append(f'w: {w.group(1)}')
    if h:
        hints.append(f'h: {h.group(1)}')
    # Hover
    hover = re.search(r'hover:(\S+)', classes)
    if hover:
        hints.append(f'hover: {hover.group(1)}')
    # Uppercase
    if 'uppercase' in classes:
        hints.append('uppercase')
    # Rounded
    if 'rounded-full' in classes:
        hints.append('pill shape')
    elif 'rounded' in classes:
        hints.append('rounded')
    return hints


def _describe_element(el, lines, depth, max_depth):
    """Recursively describe an element in natural language."""
    indent = '  ' * depth
    tag = el.name
    if not tag or tag in ('script', 'style', 'noscript', 'template', 'link', 'meta'):
        return

    classes = ' '.join(el.get('class', []))
    children = [c for c in el.children if getattr(c, 'name', None)]
    text = el.get_text(strip=True)[:60]

    # Describe the element visually
    desc = ''
    if tag == 'img':
        alt = el.get('alt', 'image')
        w_cls = re.search(r'w-\[?(\d+(?:px)?)\]?', classes)
        h_cls = re.search(r'h-\[?(\d+(?:px)?)\]?', classes)
        size = ''
        if w_cls and h_cls:
            size = f' ({w_cls.group(1)}×{h_cls.group(1)})'
        desc = f'Image: "{alt}"{size}'
    elif tag == 'svg':
        label = el.get('aria-label', '')
        desc = f'Icon: {label}' if label else 'Icon (SVG)'
    elif tag == 'a':
        href = el.get('href', '')
        link_text = text[:30] if text else href[:30]
        # Extract visual styling
        style_parts = _extract_style_hints(classes)
        style_hint = f' [{", ".join(style_parts)}]' if style_parts else ''
        desc = f'Link: "{link_text}"{style_hint}'
    elif tag == 'button':
        label = el.get('aria-label', text[:30])
        style_parts = _extract_style_hints(classes)
        style_hint = f' [{", ".join(style_parts)}]' if style_parts else ''
        desc = f'Button: "{label}"{style_hint}'
    elif tag == 'input':
        input_type = el.get('type', 'text')
        placeholder = el.get('placeholder', '')
        desc = f'Input ({input_type}): "{placeholder}"'
    elif tag == 'nav':
        link_count = len(el.find_all('a'))
        desc = f'Navigation bar with {link_count} links'
    elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        desc = f'Heading ({tag}): "{text[:50]}"'
    elif tag == 'p':
        desc = f'Paragraph: "{text[:50]}"'
    elif tag in ('ul', 'ol'):
        items = len(el.find_all('li', recursive=False))
        desc = f'List with {items} items'
    elif tag == 'span' and text and not children:
        desc = f'Text: "{text[:40]}"'
    elif tag in ('div', 'section', 'header', 'footer', 'main', 'aside'):
        # Describe by layout classes
        layout = ''
        if 'flex' in classes:
            if 'flex-col' in classes:
                layout = 'vertical flex container'
            else:
                layout = 'horizontal flex container'
        elif 'grid' in classes:
            col_match = re.search(r'grid-cols-(\d+)', classes)
            if col_match:
                layout = f'{col_match.group(1)}-column grid'
            else:
                layout = 'grid container'
        else:
            layout = 'container'

        style_hints = _extract_style_hints(classes)
        hint = f' [{", ".join(style_hints)}]' if style_hints else ''
        n_kids = len(children)
        desc = f'{layout}{hint}'
        if not children and text:
            desc += f' — "{text[:30]}"'
        elif n_kids > 0:
            desc += f' with {n_kids} children'
    else:
        if text and not children:
            desc = f'<{tag}>: "{text[:40]}"'
        elif children:
            desc = f'<{tag}> with {len(children)} children'
        else:
            return

    if not desc:
        return

    if depth == 0:
        # Skip describing the root — caller handles that
        for child in children:
            _describe_element(child, lines, depth + 1, max_depth)
        return

    lines.append(f'{indent}- {desc}')

    if depth < max_depth and children:
        for child in children[:8]:
            _describe_element(child, lines, depth + 1, max_depth)


# ---------------------------------------------------------------------------
# Self-contained HTML Generator (for html.to.design Figma plugin)
# ---------------------------------------------------------------------------

def generate_figma_html(blueprint: dict) -> str:
    """Generate a self-contained HTML file from a component blueprint.

    The HTML includes inline styles extracted from computedStyles, making it
    importable via the html.to.design Figma plugin. Uses the actual source
    HTML but adds computed styles as inline style attributes for elements
    that rely on external stylesheets.
    """
    source_html = blueprint.get('source', {}).get('sourceHTML', '')
    computed = blueprint.get('computedStyles', {})
    name = blueprint.get('semantic_name', 'Component')
    url = blueprint.get('metadata', {}).get('url', '')
    box = blueprint.get('boxModel', {})
    width = box.get('width', computed.get('width', '1920px'))
    height = box.get('height', computed.get('height', 'auto'))

    if not source_html:
        return '<html><body><p>No source HTML available</p></body></html>'

    # Build inline root styles from computed values
    root_styles = []
    style_props = [
        ('display', 'display'), ('flex-direction', 'flexDirection'),
        ('align-items', 'alignItems'), ('justify-content', 'justifyContent'),
        ('gap', 'gap'), ('padding', 'padding'),
        ('padding-top', 'paddingTop'), ('padding-right', 'paddingRight'),
        ('padding-bottom', 'paddingBottom'), ('padding-left', 'paddingLeft'),
        ('background-color', 'backgroundColor'), ('color', 'color'),
        ('font-family', 'fontFamily'), ('font-size', 'fontSize'),
        ('font-weight', 'fontWeight'), ('line-height', 'lineHeight'),
        ('letter-spacing', 'letterSpacing'), ('border-radius', 'borderRadius'),
        ('border', 'border'), ('box-shadow', 'boxShadow'),
    ]
    for css_prop, js_prop in style_props:
        val = computed.get(js_prop, '')
        if val and val not in ('none', 'normal', '0px', 'rgba(0, 0, 0, 0)', 'transparent', '0'):
            root_styles.append(f'{css_prop}: {val}')

    root_style_str = '; '.join(root_styles)

    # Inject inline style on root element
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(source_html, 'html.parser')
        root = soup.find()
        if root:
            existing = root.get('style', '')
            root['style'] = (existing + '; ' + root_style_str).strip('; ')
            source_html = str(root)
    except Exception:
        pass

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — ripped from {url}</title>
<style>
  /* Reset */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }}

  /* Component container */
  .ripped-component {{
    width: {width};
    max-width: 100vw;
    min-height: {height};
    overflow: hidden;
    position: relative;
  }}

  /* Preserve Tailwind utility classes commonly used */
  .flex {{ display: flex; }}
  .flex-col {{ flex-direction: column; }}
  .flex-row {{ flex-direction: row; }}
  .items-center {{ align-items: center; }}
  .justify-center {{ justify-content: center; }}
  .justify-between {{ justify-content: space-between; }}
  .justify-end {{ justify-content: flex-end; }}
  .hidden {{ display: none; }}
  .relative {{ position: relative; }}
  .absolute {{ position: absolute; }}
  .w-full {{ width: 100%; }}
  .h-full {{ height: 100%; }}
  .grid {{ display: grid; }}
  .uppercase {{ text-transform: uppercase; }}
  .transition {{ transition: all 0.2s ease; }}
  .transition-colors {{ transition: color 0.2s ease, background-color 0.2s ease; }}
  .overflow-hidden {{ overflow: hidden; }}
  .text-center {{ text-align: center; }}
  .font-bold {{ font-weight: 700; }}
  .font-semibold {{ font-weight: 600; }}
  .font-medium {{ font-weight: 500; }}
  .cursor-pointer {{ cursor: pointer; }}
  .rounded {{ border-radius: 0.25rem; }}
  .rounded-full {{ border-radius: 9999px; }}

  /* Spacing utilities */
  .p-1 {{ padding: 0.25rem; }} .p-2 {{ padding: 0.5rem; }} .p-3 {{ padding: 0.75rem; }}
  .p-4 {{ padding: 1rem; }} .p-6 {{ padding: 1.5rem; }} .p-8 {{ padding: 2rem; }}
  .px-3 {{ padding-left: 0.75rem; padding-right: 0.75rem; }}
  .px-4 {{ padding-left: 1rem; padding-right: 1rem; }}
  .px-6 {{ padding-left: 1.5rem; padding-right: 1.5rem; }}
  .py-2 {{ padding-top: 0.5rem; padding-bottom: 0.5rem; }}
  .py-3 {{ padding-top: 0.75rem; padding-bottom: 0.75rem; }}
  .py-6 {{ padding-top: 1.5rem; padding-bottom: 1.5rem; }}
  .m-0 {{ margin: 0; }}
  .mx-auto {{ margin-left: auto; margin-right: auto; }}
  .gap-1 {{ gap: 0.25rem; }} .gap-2 {{ gap: 0.5rem; }} .gap-3 {{ gap: 0.75rem; }}
  .gap-4 {{ gap: 1rem; }} .gap-6 {{ gap: 1.5rem; }}
  .space-x-3 > * + * {{ margin-left: 0.75rem; }}
  .space-x-6 > * + * {{ margin-left: 1.5rem; }}

  /* Size utilities */
  .w-6 {{ width: 1.5rem; }} .h-6 {{ height: 1.5rem; }}
  .w-8 {{ width: 2rem; }} .h-8 {{ height: 2rem; }}
  .h-16 {{ height: 4rem; }}

  /* Images */
  img {{ max-width: 100%; height: auto; display: block; }}
  svg {{ display: inline-block; }}
</style>
</head>
<body>
<div class="ripped-component">
{source_html}
</div>
<!-- Ripped from {url} by Web Intelligence Scanner -->
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Figma output helpers
# ---------------------------------------------------------------------------

def _gridcols_to_tw(cols: str) -> str:
    """Convert a gridTemplateColumns value to a Tailwind grid-cols-* class.

    Handles:
      repeat(3, 1fr)                     → grid-cols-3
      repeat(3, minmax(0, 1fr))          → grid-cols-3
      88px 88px 88px ... (N equal)       → grid-cols-N
      repeat(auto-fill, minmax(250px,1fr))→ grid-cols-[repeat(auto-fill,minmax(250px,1fr))]
    """
    if not cols or cols in ('none', 'normal'):
        return ''
    cols = cols.strip()

    # repeat(N, 1fr) or repeat(N, minmax(...))
    m = re.match(r'repeat\((\d+),\s*(?:1fr|minmax\([^)]+\))\)', cols)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return f'grid-cols-{n}'

    # repeat(auto-fill/auto-fit, ...) → arbitrary value
    if 'auto-fill' in cols or 'auto-fit' in cols:
        safe = cols.replace(' ', '_')
        return f'grid-cols-[{safe}]'

    # N equal values: "88px 88px 88px" or "1fr 1fr 1fr"
    parts = cols.split()
    if len(parts) >= 2 and len(set(parts)) == 1:
        n = len(parts)
        if 1 <= n <= 12:
            return f'grid-cols-{n}'

    return ''


def _infer_tag(blueprint: dict) -> str:
    """Infer the HTML tag from the blueprint source."""
    source_html = blueprint.get('source', {}).get('sourceHTML', '')
    if source_html:
        m = re.match(r'<(\w+)', source_html)
        if m:
            return m.group(1)
    return 'div'


def _infer_role(blueprint: dict) -> str:
    """Infer a semantic role from the blueprint."""
    name = blueprint.get('semantic_name', '').lower()
    if 'nav' in name:
        return 'navigation'
    if 'hero' in name:
        return 'hero-section'
    if 'footer' in name:
        return 'contentinfo'
    if 'header' in name:
        return 'banner'
    if 'button' in name or 'cta' in name:
        return 'call-to-action'
    if 'card' in name:
        return 'content-card'
    return 'component'


def _build_children_jsx(blueprint: dict) -> str:
    """Build nested JSX using a two-source hybrid:

    1. Anatomy elements (level 1 + 2): have computed styles → accurate Tailwind classes
       via TailwindTranslator. Inspired by json-render's flat element registry pattern:
       each element is a known node with props, not just a raw HTML string.

    2. BeautifulSoup HTML (level 3+): raw HTML class names preserved for depth
       that anatomy doesn't cover.

    For grids: shows one representative item template + item count hint.
    For navs: shows left/center/right zone structure.
    """
    anatomy = blueprint.get('anatomy', {})
    zones = anatomy.get('zones', [])
    layout = blueprint.get('layout', {})
    is_grid = layout.get('type') == 'grid'

    # Flatten anatomy zones into an ordered element list
    anatomy_elements = []
    for zone in zones:
        for el in zone.get('elements', []):
            if el:
                anatomy_elements.append(el)

    if anatomy_elements:
        try:
            translator = TailwindTranslator()
            lines = []
            _render_anatomy_jsx(anatomy_elements, lines, depth=1,
                                translator=translator, is_grid=is_grid,
                                blueprint=blueprint)
            if lines:
                return '\n'.join(lines)
        except Exception:
            pass  # fall through to HTML-based approach

    # Fallback: BeautifulSoup raw HTML walk
    source_html = blueprint.get('source', {}).get('sourceHTML', '')
    if not source_html:
        return '{children}'

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(source_html, 'html.parser')
        root = soup.find()
        if not root:
            return '{children}'
        lines = []
        _render_jsx_children(root, lines, depth=1, max_depth=4, max_siblings=8)
        return '\n'.join(lines) if lines else '{children}'
    except Exception:
        return '{children}'


def _anatomy_styles_to_tw(styles: dict, translator: 'TailwindTranslator') -> str:
    """Translate an anatomy element's computed styles dict to a Tailwind className string."""
    if not styles:
        return ''

    tw = translator.translate(styles)
    parts = []

    # Layout first
    display = styles.get('display', '')
    if display == 'flex':
        parts.append('flex')
        dir_map = {'column': 'flex-col', 'row-reverse': 'flex-row-reverse',
                   'column-reverse': 'flex-col-reverse'}
        fd = styles.get('flexDirection', '')
        if fd in dir_map:
            parts.append(dir_map[fd])
        align_map = {'center': 'items-center', 'flex-start': 'items-start',
                     'flex-end': 'items-end', 'stretch': 'items-stretch'}
        if styles.get('alignItems') in align_map:
            parts.append(align_map[styles['alignItems']])
        justify_map = {'center': 'justify-center', 'space-between': 'justify-between',
                       'space-around': 'justify-around', 'flex-end': 'justify-end'}
        if styles.get('justifyContent') in justify_map:
            parts.append(justify_map[styles['justifyContent']])
    elif display == 'grid':
        parts.append('grid')
        cols_tw = _gridcols_to_tw(styles.get('gridTemplateColumns', ''))
        if cols_tw:
            parts.append(cols_tw)

    # Remaining translated props (skip layout ones already handled)
    skip = {'display', 'flexDirection', 'alignItems', 'justifyContent', 'flexWrap'}
    parts += [v for k, v in tw.items() if k not in skip]

    return ' '.join(parts)


def _render_anatomy_jsx(elements: list, lines: list, depth: int,
                        translator: 'TailwindTranslator', is_grid: bool,
                        blueprint: dict, max_items: int = 8):
    """Render JSX from anatomy element nodes (each has computed styles).

    Grid mode: renders the first item as a full template, then a count hint.
    Nav/flex mode: renders all direct children with their Tailwind classes.
    """
    indent = '  ' * depth
    total = len(elements)

    for i, el in enumerate(elements):
        if i >= max_items:
            lines.append(f'{indent}{{/* +{total - max_items} more */}}')
            break

        tag = (el.get('tag') or 'div').lower()
        if tag in ('script', 'style', 'noscript', 'template', 'link', 'meta', 'svg'):
            # Collapse SVGs to single line
            if tag == 'svg':
                label = el.get('ariaLabel') or 'icon'
                lines.append(f'{indent}<svg aria-label="{label}" /> {{/* icon */}}')
            continue

        styles = el.get('styles') or {}
        tw_classes = _anatomy_styles_to_tw(styles, translator)
        class_attr = f' className="{tw_classes}"' if tw_classes else ''

        # Supplemental props
        extra = ''
        href = el.get('href')
        if href and tag == 'a':
            short_href = href if len(href) <= 50 else href[:47] + '...'
            extra += f' href="{short_href}"'
        src = el.get('src')
        if src and tag == 'img':
            alt = el.get('ariaLabel') or el.get('text') or ''
            extra += f' alt="{alt[:40]}"'
            lines.append(f'{indent}<img{class_attr}{extra} />')
            continue
        aria = el.get('ariaLabel')
        if aria:
            extra += f' aria-label="{aria[:40]}"'

        children = el.get('children') or []
        text = (el.get('text') or '').strip()[:60]

        if not children and text:
            lines.append(f'{indent}<{tag}{class_attr}{extra}>{text}</{tag}>')
        elif children:
            lines.append(f'{indent}<{tag}{class_attr}{extra}>')
            if depth < 3:
                _render_anatomy_jsx(children, lines, depth + 1,
                                    translator, is_grid=False,
                                    blueprint=blueprint, max_items=6)
            else:
                # Max depth — summarise with source HTML fallback
                try:
                    src_html = blueprint.get('source', {}).get('sourceHTML', '')
                    if src_html and el.get('text'):
                        lines.append(f'{indent}  {el["text"][:60]}')
                    else:
                        lines.append(f'{indent}  {{/* {len(children)} children */}}')
                except Exception:
                    lines.append(f'{indent}  {{/* {len(children)} children */}}')
            lines.append(f'{indent}</{tag}>')
        else:
            lines.append(f'{indent}<{tag}{class_attr}{extra} />')

        # Grid pattern: show one template item, then a repeat count
        if is_grid and total >= 3 and i == 0:
            lines.append(f'{indent}{{/* × {total - 1} more items */}}')
            break


def _render_jsx_children(el, lines, depth, max_depth, max_siblings):
    """Recursively render child elements as JSX with className props."""
    indent = '  ' * depth
    children = [c for c in el.children if getattr(c, 'name', None)]

    if not children:
        # Leaf node — show text content
        text = el.get_text(strip=True)[:60]
        if text:
            lines.append(f'{indent}{text}')
        return

    rendered = 0
    for child in children:
        if rendered >= max_siblings:
            remaining = len(children) - rendered
            lines.append(f'{indent}{{/* +{remaining} more elements */}}')
            break

        tag = child.name
        # Skip script, style, noscript, template
        if tag in ('script', 'style', 'noscript', 'template', 'link', 'meta'):
            continue

        # Build props
        props = []
        classes = child.get('class', [])
        if classes:
            class_str = ' '.join(classes)
            # Truncate very long class lists but keep meaningful ones
            if len(class_str) > 120:
                # Keep first ~100 chars worth of classes
                kept = []
                length = 0
                for cls in classes:
                    if length + len(cls) > 100:
                        kept.append('...')
                        break
                    kept.append(cls)
                    length += len(cls) + 1
                class_str = ' '.join(kept)
            props.append(f'className="{class_str}"')

        # Meaningful attributes
        href = child.get('href')
        if href and tag == 'a':
            href_short = href if len(href) <= 50 else href[:47] + '...'
            props.append(f'href="{href_short}"')

        src = child.get('src') or child.get('srcset', '').split(' ')[0] if child.get('srcset') else child.get('src')
        if src and tag == 'img':
            alt = child.get('alt', '')
            props.append(f'alt="{alt[:40]}"')

        aria_label = child.get('aria-label')
        if aria_label:
            props.append(f'aria-label="{aria_label[:30]}"')

        role = child.get('role')
        if role:
            props.append(f'role="{role}"')

        prop_str = ' ' + ' '.join(props) if props else ''

        # Check if this is a leaf or has children
        child_elements = [c for c in child.children if getattr(c, 'name', None)]
        text = child.get_text(strip=True)[:50]

        if tag == 'img':
            lines.append(f'{indent}<img{prop_str} />')
        elif tag == 'svg':
            lines.append(f'{indent}<svg{prop_str} /> {{/* icon */}}')
        elif not child_elements and text:
            lines.append(f'{indent}<{tag}{prop_str}>{text}</{tag}>')
        elif not child_elements:
            lines.append(f'{indent}<{tag}{prop_str} />')
        elif depth < max_depth:
            lines.append(f'{indent}<{tag}{prop_str}>')
            _render_jsx_children(child, lines, depth + 1, max_depth, max_siblings)
            lines.append(f'{indent}</{tag}>')
        else:
            # Max depth — summarize
            n_children = len(child_elements)
            summary = f'{text[:30]}' if text else f'{n_children} children'
            lines.append(f'{indent}<{tag}{prop_str}>{summary}</{tag}>')

        rendered += 1


def _build_states_table(states: dict, translator: TailwindTranslator) -> str:
    """Build markdown table of interactive state changes."""
    root = (states or {}).get('root') or {}
    if not states or (not root.get('hover_delta') and not root.get('focus_delta')):
        return '| State | Changes |\n|-------|--------|\n| _(no interactive states detected)_ | — |'

    rows = ['| State | Changes |', '|-------|---------|']

    if root.get('hover_delta'):
        changes = []
        translated = translator.translate(root['hover_delta'])
        for prop, tw in translated.items():
            # Try to describe the change
            changes.append(f'`{tw}`')
        if not changes:
            # Fall back to raw property names
            changes = [f'`{k}` changes' for k in list(root['hover_delta'].keys())[:3]]
        rows.append(f'| hover | {", ".join(changes)} |')

    if root.get('focus_delta'):
        changes = []
        translated = translator.translate(root['focus_delta'])
        for prop, tw in translated.items():
            changes.append(f'`{tw}`')
        if not changes:
            changes = [f'`{k}` changes' for k in list(root['focus_delta'].keys())[:3]]
        rows.append(f'| focus | {", ".join(changes)} |')

    # Children with state changes
    for child in states.get('children', [])[:3]:
        if child.get('hover_delta'):
            text = child.get('text', child.get('selector', ''))[:20]
            n_changes = len(child['hover_delta'])
            rows.append(f'| hover ({text}) | {n_changes} properties change |')

    return '\n'.join(rows)


def _build_tokens_section(blueprint: dict, translated: dict, computed: dict) -> str:
    """Build design tokens section grouped by category."""
    lines = []

    # Colors
    color_tokens = []
    for prop in ['backgroundColor', 'color', 'borderColor']:
        if prop in translated:
            raw = computed.get(prop, '')
            color_tokens.append(f'`{translated[prop]}` ({raw})')
    if color_tokens:
        lines.append(f'- **Color:** {", ".join(color_tokens)}')

    # Typography
    typo_tokens = []
    for prop in ['fontSize', 'fontWeight', 'lineHeight', 'letterSpacing']:
        if prop in translated:
            typo_tokens.append(f'`{translated[prop]}`')
    if typo_tokens:
        lines.append(f'- **Typography:** {" / ".join(typo_tokens)}')

    # Spacing
    spacing_tokens = []
    for prop in ['padding', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                 'margin', 'marginTop', 'gap']:
        if prop in translated:
            raw = computed.get(prop, '')
            spacing_tokens.append(f'`{translated[prop]}` ({raw})')
    if spacing_tokens:
        lines.append(f'- **Spacing:** {", ".join(spacing_tokens[:4])}')

    # Border
    if 'borderRadius' in translated:
        raw = computed.get('borderRadius', '')
        lines.append(f'- **Border:** `{translated["borderRadius"]}` ({raw})')

    # Shadow
    if 'boxShadow' in translated:
        lines.append(f'- **Shadow:** `{translated["boxShadow"]}`')

    # Motion (from transition property)
    transition = computed.get('transition', '')
    if transition and transition not in ('none', 'all 0s ease 0s'):
        lines.append(f'- **Motion:** `{transition[:60]}`')

    return '\n'.join(lines) if lines else '_(no design tokens mapped)_'


def _build_anatomy_text(blueprint: dict, anatomy: dict) -> str:
    """Build anatomy tree from component blueprint."""
    root_tag = _infer_tag(blueprint)
    layout = anatomy.get('layout_system', blueprint.get('layout', {}).get('type', 'block'))
    direction = blueprint.get('layout', {}).get('direction', '')

    lines = [f'- **Root:** `<{root_tag}>` ({layout}{", " + direction if direction else ""})']

    children = anatomy.get('child_summary', [])
    if not isinstance(children, list):
        children = []
    for child in children[:8]:
        role = child.get('role', 'element')
        tag = child.get('tag', '?')
        text = child.get('text', '')[:30]
        font = child.get('font', '')
        color = child.get('color', '')

        details = []
        if text:
            details.append(f'"{text}"')
        if font:
            details.append(font)
        if color:
            details.append(color)

        detail_str = f' ({", ".join(details)})' if details else ''
        lines.append(f'  - **{role}:** `<{tag}>`{detail_str}')

    return '\n'.join(lines) if lines else f'- **Root:** `<{root_tag}>`'
