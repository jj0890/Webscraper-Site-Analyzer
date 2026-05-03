"""
Brand Personality Extractor — Heuristic inference of tone, energy, and target audience.

Cross-dependency extractor that reads upstream evidence (colors, typography,
animations, interactive elements, site architecture) to classify the brand's
personality without LLM API calls. All classifications are backed by a
verifiable signals[] array.

Runs in Batch 3 (after all primary extractors have populated evidence).
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


# ── Tone classification thresholds ──
# Each tone is a weighted sum of design signals

TONE_PROFILES = {
    'Minimal / Technical': {
        'description': 'Clean lines, monochrome or muted palette, system fonts or monospace, flat design',
    },
    'Playful / Friendly': {
        'description': 'Rounded corners, warm/bright colors, casual fonts, bouncy animations',
    },
    'Premium / Editorial': {
        'description': 'Serif fonts, restrained palette, generous whitespace, subtle shadows',
    },
    'Dark / Avant-Garde': {
        'description': 'Dark backgrounds, high-contrast type, editorial/display fonts, subculture aesthetic',
    },
    'Modern / Polished': {
        'description': 'Sans-serif, accent colors, smooth transitions, card-based layouts',
    },
    'Clean / Professional': {
        'description': 'Standard sans-serif, blue/gray palette, functional layout, minimal animation',
    },
}

ENERGY_LEVELS = [
    ('Static', 0, 2),
    ('Restrained', 3, 10),
    ('Subtle', 11, 30),
    ('Dynamic', 31, 80),
    ('High energy', 81, 9999),
]

AUDIENCE_SIGNALS = {
    'Developers': ['monospace', 'code', 'api', 'docs', 'github', 'terminal', 'sdk', 'cli'],
    'Business / Enterprise': ['enterprise', 'solution', 'platform', 'dashboard', 'analytics', 'pricing'],
    'Consumers': ['shop', 'cart', 'buy', 'price', 'product', 'store', 'sale'],
    'Readers / Content': ['article', 'blog', 'story', 'read', 'author', 'publish', 'editorial'],
}


class BrandPersonalityExtractor(BaseExtractor):
    name = "brand_personality"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Inferring brand personality...")

        signals = []

        # ── Gather upstream evidence ──
        colors = ctx.evidence.get('colors', {})
        typography = ctx.evidence.get('typography', {})
        animations = ctx.evidence.get('animations', {}) or ctx.evidence.get('motion_tokens', {})
        interactive = ctx.evidence.get('interactive_elements', {})
        architecture = ctx.evidence.get('site_architecture', {})
        shadows = ctx.evidence.get('shadow_system', {})
        spacing = ctx.evidence.get('spacing_scale', {})
        borders = ctx.evidence.get('border_radius_scale', {})

        # ── Tone scoring ──
        tone, tone_signals = self._classify_tone(
            colors, typography, shadows, borders, animations, architecture
        )
        signals.extend(tone_signals)

        # ── Energy level ──
        energy, energy_signals = self._classify_energy(animations)
        signals.extend(energy_signals)

        # ── Target audience ──
        target_audience, audience_signals = self._classify_audience(
            typography, architecture, interactive, ctx.html_content, ctx.url
        )
        signals.extend(audience_signals)

        # Confidence: based on how many signals contributed
        confidence = min(40 + len(signals) * 5, 95)

        return {
            'pattern': f"{tone} / {energy} / {target_audience}",
            'confidence': confidence,
            'tone': tone,
            'energy': energy,
            'target_audience': target_audience,
            'signals': signals
        }

    # ------------------------------------------------------------------
    # Tone classification
    # ------------------------------------------------------------------

    def _classify_tone(
        self, colors: Dict, typography: Dict, shadows: Dict,
        borders: Dict, animations: Dict, architecture: Dict
    ) -> Tuple[str, List[str]]:
        """Score each tone profile and return the best match."""
        scores = {tone: 0 for tone in TONE_PROFILES}
        signals = []

        # ── Font signals ──
        typo_details = typography.get('details', {})
        body_font = typo_details.get('body', {}).get('fontFamily', '').lower()
        # Pull from role-classified lists first, then fall back to all_fonts
        heading_fonts = [f.lower() for f in (
            typography.get('heading_fonts') or typo_details.get('heading_fonts', [])
        )]
        body_fonts_list = [f.lower() for f in (
            typography.get('body_fonts') or typo_details.get('body_fonts', [])
        )]
        all_fonts = [f.lower() for f in typo_details.get('all_fonts', [])]
        all_fonts_str = ' '.join(all_fonts + heading_fonts + body_fonts_list)

        has_serif = any(f for f in all_fonts if 'serif' in f and 'sans' not in f)
        has_monospace = any(f for f in all_fonts if 'mono' in f or 'courier' in f or 'consolas' in f)
        has_system = 'system-ui' in body_font or 'sf pro' in body_font or '-apple-system' in body_font

        # Editorial/display fonts (Druk, Univers, Haas, Neue Haas, GT, Canela, etc.)
        editorial_fonts = ['druk', 'univers', 'haas', 'neue haas', 'gt walsheim', 'canela',
                           'portrait', 'tiempos', 'domaine', 'financier', 'publico', 'brunel',
                           'graphik', 'founders grotesk', 'acumin', 'dharma', 'knockout',
                           'tungsten', 'gotham', 'vitesse']
        has_editorial = any(ef in all_fonts_str for ef in editorial_fonts)

        if has_serif:
            scores['Premium / Editorial'] += 3
            signals.append('Serif font detected → Premium/Editorial')
        if has_editorial:
            scores['Dark / Avant-Garde'] += 2
            scores['Premium / Editorial'] += 2
            signals.append(f'Editorial/display typeface detected → Dark/Avant-Garde + Premium/Editorial')
        if has_monospace:
            scores['Minimal / Technical'] += 3
            signals.append('Monospace font detected → Minimal/Technical')
        if has_system:
            scores['Clean / Professional'] += 2
            signals.append('System font stack → Clean/Professional')

        # Decorative/rounded fonts suggest playful
        playful_fonts = ['comic', 'fredoka', 'bubblegum', 'patrick', 'baloo', 'nunito', 'quicksand', 'poppins']
        if any(pf in all_fonts_str for pf in playful_fonts):
            scores['Playful / Friendly'] += 3
            signals.append('Playful/rounded font detected → Playful/Friendly')

        # ── Color signals ──
        color_roles = colors.get('color_roles', {})
        palette = colors.get('palette', {})
        primary_colors = palette.get('primary', [])

        # color_roles values are either plain strings OR [{variable, value}] lists
        # Normalise to a single color string for comparison
        def _role_color(role_key: str) -> str:
            raw = color_roles.get(role_key, '')
            if isinstance(raw, list) and raw:
                # [{variable: '--bg', value: 'rgb(0,0,0)'}]
                first = raw[0]
                return first.get('value', '') if isinstance(first, dict) else str(first)
            return str(raw) if raw else ''

        if color_roles:
            bg     = _role_color('background')
            accent = _role_color('accent')

            # Dark background = avant-garde / technical
            if bg and self._is_dark_color(bg):
                scores['Dark / Avant-Garde'] += 3
                scores['Minimal / Technical'] += 1
                signals.append(f'Dark background ({bg}) → Dark/Avant-Garde')

            # Bright accent colors
            if accent and self._is_vivid_color(accent):
                scores['Modern / Polished'] += 2
                signals.append(f'Vivid accent ({accent}) → Modern/Polished')

            # Blue/gray accent = professional
            if accent and self._is_blue_gray(accent):
                scores['Clean / Professional'] += 2
                signals.append('Blue/gray accent → Clean/Professional')

        # Compute palette darkness from primary colors directly when no bg role
        if not color_roles.get('background') and primary_colors:
            dark_primary = sum(1 for c in primary_colors[:5] if self._is_dark_color(c))
            if dark_primary >= 2:
                scores['Dark / Avant-Garde'] += 2
                signals.append(f'{dark_primary} dark primary colors → Dark/Avant-Garde')

        # Few total colors = minimal
        total_colors = colors.get('total_unique_colors', len(primary_colors))
        if total_colors <= 5:
            scores['Minimal / Technical'] += 2
            signals.append(f'{total_colors} total colors → Minimal')
        elif total_colors >= 15:
            scores['Playful / Friendly'] += 1
            signals.append(f'{total_colors} total colors → Playful/varied')

        # ── Shadow signals ──
        shadow_levels = shadows.get('levels', [])
        if not shadow_levels:
            scores['Minimal / Technical'] += 2
            signals.append('No shadows (flat design) → Minimal/Technical')
        elif len(shadow_levels) >= 3:
            scores['Modern / Polished'] += 2
            signals.append(f'{len(shadow_levels)} shadow levels → Modern/Polished (elevation system)')

        # ── Border radius signals ──
        border_levels = borders.get('levels', []) if borders else []
        max_radius = 0
        for level in border_levels:
            px = level.get('px', 0) or 0
            if isinstance(px, (int, float)) and px > max_radius:
                max_radius = px

        if max_radius >= 20:
            scores['Playful / Friendly'] += 2
            signals.append(f'Large border radius ({max_radius}px) → Playful/Friendly')
        elif max_radius <= 4 and border_levels:
            scores['Minimal / Technical'] += 1
            signals.append(f'Small border radius ({max_radius}px) → Minimal/Technical')

        # ── Architecture signals ──
        arch_details = architecture.get('details', {})
        css_framework = arch_details.get('css_framework', '')

        if css_framework == 'Tailwind CSS':
            scores['Modern / Polished'] += 1
            signals.append('Tailwind CSS → Modern/Polished')
        elif css_framework == 'Bootstrap':
            scores['Clean / Professional'] += 1
            signals.append('Bootstrap → Clean/Professional')

        # Pick highest-scoring tone
        best_tone = max(scores, key=scores.get)

        # If tied or all zero, default to Clean / Professional
        if scores[best_tone] == 0:
            best_tone = 'Clean / Professional'
            signals.append('No strong tone signals → defaulting to Clean/Professional')

        return best_tone, signals

    # ------------------------------------------------------------------
    # Energy classification
    # ------------------------------------------------------------------

    def _classify_energy(self, animations: Dict) -> Tuple[str, List[str]]:
        """Classify energy level from animation/transition counts."""
        signals = []

        # Count animations and transitions
        details = animations.get('details', {})
        keyframe_count = len(details.get('keyframe_animations', details.get('animations', [])))
        transition_count = len(details.get('transitions', []))

        # Also check motion_tokens structure
        if not keyframe_count and not transition_count:
            motion_details = animations.get('details', {})
            keyframe_count = len(motion_details.get('keyframe_animations', []))
            transition_count = len(motion_details.get('motion_patterns', []))

        total_motion = keyframe_count + transition_count
        signals.append(f'{keyframe_count} keyframes + {transition_count} transitions = {total_motion} motion elements')

        # Map to energy level
        energy = 'Static'
        for level_name, low, high in ENERGY_LEVELS:
            if low <= total_motion <= high:
                energy = level_name
                break

        return energy, signals

    # ------------------------------------------------------------------
    # Audience classification
    # ------------------------------------------------------------------

    def _classify_audience(
        self, typography: Dict, architecture: Dict,
        interactive: Dict, html_content: str, url: str
    ) -> Tuple[str, List[str]]:
        """Classify target audience from content and architecture signals."""
        scores = {audience: 0 for audience in AUDIENCE_SIGNALS}
        signals = []

        # Check URL
        url_lower = url.lower()
        for audience, keywords in AUDIENCE_SIGNALS.items():
            for kw in keywords:
                if kw in url_lower:
                    scores[audience] += 2
                    signals.append(f'URL contains "{kw}" → {audience}')

        # Check page content (sample first 5000 chars for performance)
        content_sample = html_content[:5000].lower() if html_content else ''
        for audience, keywords in AUDIENCE_SIGNALS.items():
            for kw in keywords:
                count = content_sample.count(kw)
                if count >= 2:
                    scores[audience] += min(count, 5)
                    signals.append(f'Content mentions "{kw}" {count}x → {audience}')

        # Architecture signals
        arch_details = architecture.get('details', {})
        framework = arch_details.get('framework', '')
        capabilities = arch_details.get('capabilities', {})

        # Developer-oriented frameworks
        if framework in ('Next.js', 'Nuxt', 'SvelteKit'):
            scores['Developers'] += 1

        # E-commerce signals
        counts = interactive.get('counts', {})
        form_count = counts.get('forms', 0)
        if form_count >= 3:
            scores['Business / Enterprise'] += 2
            signals.append(f'{form_count} forms → Business/Enterprise')

        # Font signals
        typo_details = typography.get('details', {})
        all_fonts = [f.lower() for f in typo_details.get('all_fonts', [])]
        if any('mono' in f or 'code' in f for f in all_fonts):
            scores['Developers'] += 2
            signals.append('Monospace font → Developers')

        # Pick highest-scoring audience
        best_audience = max(scores, key=scores.get)

        if scores[best_audience] == 0:
            best_audience = 'General'
            signals.append('No strong audience signals → General')

        return best_audience, signals

    # ------------------------------------------------------------------
    # Color helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_color(color_str: str) -> Optional[Tuple[int, int, int]]:
        """Parse any CSS color string to an (R, G, B) tuple.

        Handles: #rgb, #rrggbb, rgb(...), rgba(...).
        Returns None for unparseable values.
        """
        if not color_str or not isinstance(color_str, str):
            return None
        s = color_str.strip()

        # rgb() / rgba() — handles both comma and space syntax
        m = re.search(r'rgba?\(\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)', s)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

        # Hex
        s = s.lstrip('#')
        if len(s) == 3:
            s = ''.join(c * 2 for c in s)
        if len(s) == 6:
            try:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except ValueError:
                pass
        return None

    # Keep old name as alias for any callers that might use it directly
    @classmethod
    def _hex_to_rgb(cls, color: str) -> Optional[Tuple[int, int, int]]:
        return cls._parse_color(color)

    @classmethod
    def _is_dark_color(cls, color: str) -> bool:
        """True when perceived luminance < 0.3 (dark backgrounds, blacks, deep navies)."""
        rgb = cls._parse_color(color)
        if not rgb:
            return False
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return luminance < 0.3

    @classmethod
    def _is_vivid_color(cls, color: str) -> bool:
        """True when HSL saturation > 0.5 (bright, saturated accent colors)."""
        rgb = cls._parse_color(color)
        if not rgb:
            return False
        r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
        max_c, min_c = max(r, g, b), min(r, g, b)
        if max_c == min_c:
            return False
        l = (max_c + min_c) / 2
        s = (max_c - min_c) / (max_c + min_c) if l <= 0.5 else (max_c - min_c) / (2.0 - max_c - min_c)
        return s > 0.5

    @classmethod
    def _is_blue_gray(cls, color: str) -> bool:
        """True for colors in the blue/gray family (low saturation, or blue-dominant)."""
        rgb = cls._parse_color(color)
        if not rgb:
            return False
        r, g, b = rgb
        spread = max(r, g, b) - min(r, g, b)
        if spread < 30:
            return True  # Near-gray
        if b > r and b > g and b > (r + g) / 2:
            return True  # Blue-dominant
        return False
