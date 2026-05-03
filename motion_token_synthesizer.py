"""
Motion Token Synthesizer

Transforms raw CSS transition/animation data into structured, reusable motion tokens.
Grounded in patterns from 13 major design systems (Material, Carbon, Primer, Polaris,
Spectrum, Chakra, Open Props, Atlassian, Ant Design, Fluent UI, Salesforce, Radix, DTCG).

Input: raw animations evidence + interaction_states evidence from deep_evidence_engine
Output: structured motion_tokens evidence dict with duration scale, easing palette,
        motion patterns, keyframe animations, choreography descriptions, and motion personality

Note on scope: This module describes what a site's CSS is *configured* to animate, not what
was visually observed at runtime. JS-driven class toggles, scroll-triggered reveals, and
DOM mutations are outside our detection scope (static CSS inspection, Mode A).
"""

import re
from typing import Dict, List, Optional, Tuple
from collections import Counter
from math import gcd
from functools import reduce


class MotionTokenSynthesizer:
    """Synthesize raw CSS transition/animation strings into reusable motion tokens."""

    # Known easing curves from major design systems (for recognition)
    # Values are [x1, y1, x2, y2] control points
    KNOWN_CURVES = {
        # Material Design 3
        'material-standard': [0.2, 0, 0, 1],
        'material-standard-decel': [0, 0, 0, 1],
        'material-standard-accel': [0.3, 0, 1, 1],
        'material-emphasized-decel': [0.05, 0.7, 0.1, 1],
        'material-emphasized-accel': [0.3, 0, 0.8, 0.15],
        # Carbon (IBM)
        'carbon-productive-standard': [0.2, 0, 0.38, 0.9],
        'carbon-productive-entrance': [0, 0, 0.38, 0.9],
        'carbon-productive-exit': [0.2, 0, 1, 0.9],
        'carbon-expressive-standard': [0.4, 0.14, 0.3, 1],
        'carbon-expressive-entrance': [0, 0, 0.3, 1],
        'carbon-expressive-exit': [0.4, 0.14, 1, 1],
        # CSS standard keywords (their actual cubic-bezier equivalents)
        'css-ease': [0.25, 0.1, 0.25, 1],
        'css-ease-in': [0.42, 0, 1, 1],
        'css-ease-out': [0, 0, 0.58, 1],
        'css-ease-in-out': [0.42, 0, 0.58, 1],
        # Spectrum (Adobe)
        'spectrum-ease-out': [0, 0, 0.40, 1],
        'spectrum-ease-in': [0.50, 0, 1, 1],
        'spectrum-ease-in-out': [0.45, 0, 0.40, 1],
        # Fluent UI (Microsoft)
        'fluent-decelerate-mid': [0, 0, 0, 1],
        'fluent-accelerate-mid': [1, 0, 1, 1],
        'fluent-easy-ease': [0.33, 0, 0.67, 1],
        # Atlassian
        'atlassian-ease-out': [0, 0.4, 0, 1],
        'atlassian-ease-in-out': [0.4, 0, 0, 1],
        'atlassian-spring': [0.34, 1.56, 0.64, 1],
        # Polaris (Shopify)
        'polaris-ease': [0.25, 0.1, 0.25, 1],
        'polaris-ease-out': [0.19, 0.91, 0.38, 1],
        # Ant Design
        'antd-ease-out-circ': [0.08, 0.82, 0.17, 1],
        'antd-ease-in-out-circ': [0.78, 0.14, 0.15, 0.86],
        'antd-ease-out-back': [0.12, 0.4, 0.29, 1.46],
    }

    # CSS easing keywords
    EASING_KEYWORDS = {'ease', 'ease-in', 'ease-out', 'ease-in-out', 'linear', 'step-start', 'step-end'}

    # CSS animatable properties (for pattern classification)
    COLOR_PROPERTIES = {'color', 'background-color', 'backgroundColor', 'border-color', 'borderColor',
                        'outline-color', 'outlineColor', 'fill', 'stroke', 'box-shadow', 'boxShadow'}
    TRANSFORM_PROPERTIES = {'transform', 'opacity', 'scale', 'rotate', 'translate'}
    LAYOUT_PROPERTIES = {'width', 'height', 'max-height', 'maxHeight', 'max-width', 'maxWidth',
                         'padding', 'margin', 'top', 'left', 'right', 'bottom', 'gap'}
    FOCUS_PROPERTIES = {'outline', 'outline-color', 'outlineColor', 'outline-offset', 'outlineOffset',
                        'box-shadow', 'boxShadow'}

    # Duration tier boundaries (ms)
    TIER_BOUNDARIES = {
        'micro': (0, 99),
        'fast': (100, 199),
        'normal': (200, 349),
        'slow': (350, 599),
        'dramatic': (600, float('inf'))
    }

    TIER_USAGE = {
        'micro': 'instant feedback, focus rings',
        'fast': 'hover states, button feedback',
        'normal': 'state transitions, toggles',
        'slow': 'reveals, dropdowns, modals',
        'dramatic': 'page transitions, loading'
    }

    # Map selector substrings to human-readable element types (for choreography narrator)
    SELECTOR_ELEMENT_MAP = [
        ('carousel', 'carousel'), ('slick', 'carousel'), ('swiper', 'carousel'), ('slider', 'slider'),
        ('gallery', 'gallery'), ('lightbox', 'lightbox'), ('pswp', 'lightbox'),
        ('nav', 'navigation'), ('menu', 'menu'), ('sidebar', 'sidebar'),
        ('hero', 'hero section'), ('banner', 'banner'),
        ('modal', 'modal'), ('dialog', 'dialog'), ('popup', 'popup'), ('overlay', 'overlay'),
        ('card', 'card'), ('tile', 'tile'),
        ('btn', 'button'), ('button', 'button'), ('cta', 'call-to-action'),
        ('tab', 'tab'), ('accordion', 'accordion'), ('collapse', 'collapsible'),
        ('tooltip', 'tooltip'), ('popover', 'popover'),
        ('loader', 'loader'), ('loading', 'loader'), ('spinner', 'spinner'),
        ('header', 'header'), ('footer', 'footer'),
        ('form', 'form'), ('input', 'form field'), ('search', 'search'),
        ('img', 'image'), ('image', 'image'), ('photo', 'image'), ('thumb', 'thumbnail'),
        ('icon', 'icon'), ('svg', 'icon'),
        ('link', 'link'), ('dropdown', 'dropdown'),
        ('video', 'video'), ('audio', 'audio'),
        ('toast', 'notification'), ('alert', 'alert'), ('notification', 'notification'),
    ]

    # Property descriptions for plain-English narration
    PROPERTY_VERBS = {
        'transform': 'transforms',
        'opacity': 'fades',
        'color': 'changes color',
        'background-color': 'changes background color',
        'backgroundColor': 'changes background color',
        'border-color': 'changes border color',
        'borderColor': 'changes border color',
        'border': 'changes border',
        'box-shadow': 'changes shadow',
        'boxShadow': 'changes shadow',
        'width': 'resizes width',
        'height': 'resizes height',
        'max-height': 'expands/collapses',
        'maxHeight': 'expands/collapses',
        'scale': 'scales',
        'rotate': 'rotates',
        'translate': 'moves',
        'filter': 'applies visual filter',
        'clip-path': 'clips/reveals',
        'outline': 'changes outline',
    }

    # Properties to skip in descriptions (noise)
    SKIP_PROPERTIES = {'z-index', 'zIndex', 'visibility', 'pointer-events', 'cursor'}

    DURATION_ADJECTIVES = {
        'micro': 'instant',
        'fast': 'quick',
        'normal': 'smooth',
        'slow': 'deliberate',
        'dramatic': 'dramatic',
    }

    def synthesize(self, animations_evidence: Dict, interaction_states_evidence: Dict,
                   raw_keyframes: Optional[List[Dict]] = None) -> Dict:
        """Main entry point. Parse raw evidence, detect patterns, return motion_tokens dict."""
        details = animations_evidence.get('details', {})
        raw_transitions = details.get('transitions', [])
        raw_animations = details.get('animations', [])
        raw_keyframes = details.get('keyframes', [])
        libraries = details.get('libraries', {})

        state_deltas = interaction_states_evidence.get('state_deltas', {})

        # Phase 1: Parse all raw strings
        parsed_transitions = []
        for item in raw_transitions:
            raw = item.get('transition', '')
            selector = item.get('selector', '')
            parsed = self._parse_transition_string(raw)
            for p in parsed:
                p['selector'] = selector
            parsed_transitions.extend(parsed)

        parsed_animations = []
        for item in raw_animations:
            raw = item.get('animation', '')
            selector = item.get('selector', '')
            parsed = self._parse_animation_string(raw)
            if parsed:
                parsed['selector'] = selector
                parsed_animations.append(parsed)

        parsed_keyframes = []
        for kf in raw_keyframes:
            parsed_keyframes.append({
                'name': kf.get('name', ''),
                'css_text': kf.get('cssText', '')
            })

        # Phase 2: Extract all durations and easings
        all_durations = [p['duration_ms'] for p in parsed_transitions if p.get('duration_ms', 0) > 0]
        all_durations.extend([p['duration_ms'] for p in parsed_animations if p.get('duration_ms', 0) > 0])

        all_easings = [p['easing'] for p in parsed_transitions if p.get('easing')]
        all_easings.extend([p['easing'] for p in parsed_animations if p.get('easing')])

        # Phase 3: Detect patterns
        duration_scale = self._detect_duration_scale(all_durations)
        easing_palette = self._detect_easing_palette(all_easings)
        motion_patterns = self._classify_motion_patterns(parsed_transitions, state_deltas)

        # Phase 4: Process keyframe animations
        keyframe_tokens = self._process_keyframes(parsed_animations, parsed_keyframes)

        # Phase 5: Detect libraries
        detected_libs = [k for k, v in libraries.items() if v]

        # Phase 6: Build pattern string and confidence
        confidence = self._calculate_confidence(
            parsed_transitions, all_durations, all_easings,
            motion_patterns, easing_palette, keyframe_tokens
        )

        pattern_parts = []
        if duration_scale.get('values_ms'):
            n = len(duration_scale['values_ms'])
            low = min(duration_scale['values_ms'])
            high = max(duration_scale['values_ms'])
            pattern_parts.append(f"{n}-step duration scale ({low}-{high}ms)")
        if easing_palette.get('curves'):
            pattern_parts.append(f"{len(easing_palette['curves'])} easing curves")
        if motion_patterns:
            pattern_parts.append(f"{len(motion_patterns)} motion patterns")
        if keyframe_tokens:
            pattern_parts.append(f"{len(keyframe_tokens)} keyframe animations")
        if detected_libs:
            pattern_parts.append(f"Libraries: {', '.join(detected_libs)}")

        pattern = ', '.join(pattern_parts) if pattern_parts else 'No motion tokens detected'

        # Phase 7: Generate choreography narration
        # Use raw_keyframes passed from engine if available, else use parsed_keyframes
        kf_for_narration = []
        if raw_keyframes:
            for kf in raw_keyframes:
                kf_for_narration.append({
                    'name': kf.get('name', ''),
                    'css_text': kf.get('cssText', kf.get('css_text', ''))
                })
        else:
            kf_for_narration = parsed_keyframes

        choreography = self._generate_choreography(
            motion_patterns, keyframe_tokens, kf_for_narration, easing_palette
        )
        motion_personality = self._generate_personality(
            choreography, duration_scale, easing_palette, detected_libs
        )

        return {
            'pattern': pattern,
            'confidence': confidence,
            'choreography': choreography,
            'motion_personality': motion_personality,
            'details': {
                'duration_scale': duration_scale,
                'easing_palette': easing_palette,
                'motion_patterns': motion_patterns,
                'keyframe_animations': keyframe_tokens,
                'libraries': detected_libs
            }
        }

    def _parse_transition_string(self, raw: str) -> List[Dict]:
        """Parse a CSS transition shorthand into structured components.

        Handles: 'color 0.2s ease, background 0.3s ease-in-out'
        Also handles: 'all 0.3s ease', '0.3s' (duration only), cubic-bezier(), steps()
        """
        if not raw or raw in ('none', 'none 0s ease 0s', 'all 0s ease 0s', ''):
            return []

        results = []
        # Smart comma splitting: don't split inside parentheses
        segments = self._split_transition_segments(raw)

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            parsed = self._parse_single_transition(segment)
            if parsed and parsed.get('duration_ms', 0) > 0:
                results.append(parsed)

        return results

    def _split_transition_segments(self, raw: str) -> List[str]:
        """Split transition string on commas, but not inside parentheses."""
        segments = []
        depth = 0
        current = []
        for ch in raw:
            if ch == '(':
                depth += 1
                current.append(ch)
            elif ch == ')':
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                segments.append(''.join(current))
                current = []
            else:
                current.append(ch)
        if current:
            segments.append(''.join(current))
        return segments

    def _parse_single_transition(self, segment: str) -> Optional[Dict]:
        """Parse a single transition segment like 'color 0.2s ease 0.1s'."""
        tokens = self._tokenize_transition(segment)
        if not tokens:
            return None

        result = {
            'property': 'all',
            'duration_ms': 0,
            'easing': 'ease',
            'delay_ms': 0
        }

        durations_found = []
        easing_found = None
        property_found = None

        for token in tokens:
            # Check for cubic-bezier, steps, or linear() function
            if token.startswith('cubic-bezier(') or token.startswith('steps(') or token.startswith('linear('):
                easing_found = token
            elif token in self.EASING_KEYWORDS:
                easing_found = token
            elif self._is_duration(token):
                durations_found.append(self._normalize_duration(token))
            else:
                # Assume it's a property name
                if not property_found:
                    property_found = token

        if property_found:
            result['property'] = property_found
        if durations_found:
            result['duration_ms'] = durations_found[0]
        if len(durations_found) > 1:
            result['delay_ms'] = durations_found[1]
        if easing_found:
            result['easing'] = easing_found

        return result

    def _tokenize_transition(self, segment: str) -> List[str]:
        """Tokenize a transition segment, keeping cubic-bezier() and steps() intact."""
        tokens = []
        i = 0
        s = segment.strip()
        while i < len(s):
            if s[i].isspace():
                i += 1
                continue
            # Check for function-like tokens (cubic-bezier, steps)
            if s[i:].startswith('cubic-bezier(') or s[i:].startswith('steps('):
                end = s.index(')', i) + 1
                tokens.append(s[i:end])
                i = end
            else:
                # Regular token (property name, duration, easing keyword)
                end = i
                while end < len(s) and not s[end].isspace():
                    end += 1
                tokens.append(s[i:end])
                i = end
        return tokens

    def _is_duration(self, token: str) -> bool:
        """Check if a token looks like a CSS duration (e.g., '0.3s', '300ms')."""
        if token.endswith('ms'):
            try:
                float(token[:-2])
                return True
            except ValueError:
                return False
        if token.endswith('s') and not token.endswith('teps'):
            try:
                float(token[:-1])
                return True
            except ValueError:
                return False
        return False

    def _normalize_duration(self, value: str) -> int:
        """Convert CSS duration to milliseconds integer. '0.3s' → 300, '300ms' → 300."""
        if value.endswith('ms'):
            return int(round(float(value[:-2])))
        if value.endswith('s'):
            return int(round(float(value[:-1]) * 1000))
        return 0

    def _parse_animation_string(self, raw: str) -> Optional[Dict]:
        """Parse CSS animation shorthand like 'spin 1s linear infinite'.

        CSS animation shorthand order: name duration timing-function delay iteration-count
                                       direction fill-mode play-state
        """
        if not raw or raw in ('none', 'none 0s ease 0s 1 normal none running'):
            return None

        tokens = self._tokenize_transition(raw)
        if not tokens:
            return None

        result = {
            'name': None,
            'duration_ms': 0,
            'easing': 'ease',
            'delay_ms': 0,
            'iteration': '1',
            'direction': 'normal',
            'fill_mode': 'none'
        }

        durations_found = []
        direction_keywords = {'normal', 'reverse', 'alternate', 'alternate-reverse'}
        fill_keywords = {'none', 'forwards', 'backwards', 'both'}
        iteration_keywords = {'infinite'}

        for token in tokens:
            if token.startswith('cubic-bezier(') or token.startswith('steps('):
                result['easing'] = token
            elif token in self.EASING_KEYWORDS:
                result['easing'] = token
            elif self._is_duration(token):
                durations_found.append(self._normalize_duration(token))
            elif token in iteration_keywords:
                result['iteration'] = token
            elif token in direction_keywords and result['name'] is not None:
                result['direction'] = token
            elif token in fill_keywords and result['name'] is not None:
                result['fill_mode'] = token
            elif token.isdigit():
                result['iteration'] = token
            elif result['name'] is None:
                result['name'] = token

        if durations_found:
            result['duration_ms'] = durations_found[0]
        if len(durations_found) > 1:
            result['delay_ms'] = durations_found[1]

        if not result['name']:
            return None

        return result

    def _detect_duration_scale(self, all_durations_ms: List[int]) -> Dict:
        """Cluster durations into semantic tiers and detect scale pattern."""
        if not all_durations_ms:
            return {'values_ms': [], 'tiers': {}, 'total_parsed': 0}

        # Deduplicate and sort unique values
        counter = Counter(all_durations_ms)
        unique_sorted = sorted(counter.keys())

        # Assign each unique duration to a tier
        tiers = {}
        for tier_name, (low, high) in self.TIER_BOUNDARIES.items():
            tier_values = [d for d in unique_sorted if low <= d <= high]
            if tier_values:
                # Pick the most common value in this tier as the representative
                best = max(tier_values, key=lambda d: counter[d])
                total_count = sum(counter[d] for d in tier_values)
                tiers[tier_name] = {
                    'ms': best,
                    'count': total_count,
                    'usage': self.TIER_USAGE[tier_name]
                }

        # Scale values are the representative from each tier
        scale_values = sorted([t['ms'] for t in tiers.values()])

        return {
            'values_ms': scale_values,
            'tiers': tiers,
            'total_parsed': len(all_durations_ms)
        }

    def _detect_easing_palette(self, all_easings: List[str]) -> Dict:
        """Count easings, match against known curves, assign roles."""
        if not all_easings:
            return {'primary': None, 'curves': [], 'roles': {}}

        counter = Counter(all_easings)
        # Sort by count descending
        sorted_easings = counter.most_common()

        curves = []
        for easing_str, count in sorted_easings:
            entry = {
                'value': easing_str,
                'count': count,
                'role': None,
                'known_as': None
            }
            # Try to match against known curves
            bezier = self._parse_cubic_bezier(easing_str)
            if bezier:
                match = self._match_known_curve(bezier)
                if match:
                    entry['known_as'] = match
            curves.append(entry)

        # Assign roles based on curve characteristics
        self._assign_easing_roles(curves)

        primary = curves[0]['value'] if curves else None
        roles = {}
        for c in curves:
            if c['role'] and c['role'] not in roles:
                roles[c['role']] = c['value']

        return {
            'primary': primary,
            'curves': curves,
            'roles': roles
        }

    def _parse_cubic_bezier(self, easing_str: str) -> Optional[List[float]]:
        """Extract control points from a cubic-bezier() string or keyword."""
        keyword_map = {
            'ease': [0.25, 0.1, 0.25, 1],
            'ease-in': [0.42, 0, 1, 1],
            'ease-out': [0, 0, 0.58, 1],
            'ease-in-out': [0.42, 0, 0.58, 1],
            'linear': [0, 0, 1, 1],
        }
        if easing_str in keyword_map:
            return keyword_map[easing_str]

        match = re.match(r'cubic-bezier\(\s*([\d.e-]+)\s*,\s*([\d.e-]+)\s*,\s*([\d.e-]+)\s*,\s*([\d.e-]+)\s*\)', easing_str)
        if match:
            try:
                return [float(match.group(i)) for i in range(1, 5)]
            except ValueError:
                return None
        return None

    def _match_known_curve(self, bezier_values: List[float], tolerance: float = 0.06) -> Optional[str]:
        """Compare control points against KNOWN_CURVES with tolerance."""
        best_match = None
        best_distance = float('inf')

        for name, known in self.KNOWN_CURVES.items():
            distance = sum(abs(a - b) for a, b in zip(bezier_values, known))
            if distance < tolerance * 4 and distance < best_distance:
                best_distance = distance
                best_match = name

        return best_match

    def _is_spring_linear(self, easing_str: str) -> bool:
        """Detect if a CSS linear() function approximates spring physics.

        Spring-like linear() functions have values that overshoot (>1) or undershoot (<0),
        or oscillate (change direction multiple times) — hallmarks of spring bounce.
        """
        match = re.match(r'linear\((.+)\)', easing_str)
        if not match:
            return False
        try:
            # Parse the stop values, ignoring percentages
            parts = match.group(1).split(',')
            values = []
            for part in parts:
                nums = re.findall(r'-?[\d.]+', part.strip())
                if nums:
                    values.append(float(nums[0]))
            if len(values) < 3:
                return False
            # Check for overshoot/undershoot
            has_overshoot = any(v > 1.02 or v < -0.02 for v in values)
            # Check for oscillation (direction changes)
            direction_changes = 0
            for i in range(2, len(values)):
                prev_dir = values[i-1] - values[i-2]
                curr_dir = values[i] - values[i-1]
                if prev_dir * curr_dir < 0:  # sign change
                    direction_changes += 1
            # Spring = overshoot OR 2+ direction changes (bounce)
            return has_overshoot or direction_changes >= 2
        except (ValueError, IndexError):
            return False

    def _assign_easing_roles(self, curves: List[Dict]):
        """Assign purpose-based roles (default, entrance, exit, continuous) to curves."""
        if not curves:
            return

        # Most common = default
        curves[0]['role'] = 'default'

        for c in curves:
            if c['role']:
                continue
            easing = c['value']
            bezier = self._parse_cubic_bezier(easing)

            # Keyword shortcuts
            if easing == 'linear':
                c['role'] = 'continuous'
            elif easing == 'ease-out':
                c['role'] = 'entrance'
            elif easing == 'ease-in':
                c['role'] = 'exit'
            elif easing.startswith('linear('):
                # CSS linear() with oscillation = spring approximation
                if self._is_spring_linear(easing):
                    c['role'] = 'spring'
                    c['spring_like'] = True
                else:
                    c['role'] = 'custom'
            elif bezier:
                # Overshoot (y values > 1 or < 0) = spring — check first
                if bezier[1] > 1 or bezier[1] < 0 or bezier[3] > 1.1:
                    c['role'] = 'spring'
                    c['spring_like'] = True
                # Decelerate-heavy = entrance
                # Low initial acceleration (x1 < 0.3) + high final value (y2 > 0.9)
                # OR y1 > 0.7 (strong early pull toward end state)
                elif (bezier[0] < 0.3 and bezier[3] > 0.9) or bezier[1] > 0.7:
                    c['role'] = 'entrance'
                # Accelerate-heavy = exit
                # High x2 (> 0.7) with low y2 (< 0.6), or known exit pattern
                elif bezier[2] > 0.7 and bezier[3] < 0.6:
                    c['role'] = 'exit'

    def _classify_motion_patterns(self, parsed_transitions: List[Dict], state_deltas: Dict) -> List[Dict]:
        """Group transitions by purpose into named motion patterns."""
        if not parsed_transitions:
            return []

        # Collect transitions by pattern category
        categories = {
            'hover_feedback': [],
            'focus_ring': [],
            'state_change': [],
            'entrance': [],
            'emphasis': [],
        }

        # Extract selectors that have hover/focus states
        hover_selectors = set()
        focus_selectors = set()
        for selector, states in state_deltas.items():
            if isinstance(states, dict):
                if 'hover' in states:
                    hover_selectors.add(selector)
                if 'focus' in states:
                    focus_selectors.add(selector)

        for t in parsed_transitions:
            dur = t.get('duration_ms', 0)
            prop = t.get('property', 'all')
            easing = t.get('easing', '')
            selector = t.get('selector', '')

            # Classify by duration + property combination
            if dur <= 200 and prop in self.FOCUS_PROPERTIES:
                categories['focus_ring'].append(t)
            elif dur <= 200 and (prop in self.COLOR_PROPERTIES or prop == 'all'):
                categories['hover_feedback'].append(t)
            elif 200 < dur <= 400 and (prop in self.TRANSFORM_PROPERTIES or prop in self.LAYOUT_PROPERTIES or prop == 'all'):
                categories['state_change'].append(t)
            elif 300 <= dur <= 600 and (prop in self.TRANSFORM_PROPERTIES or prop == 'all'):
                bezier = self._parse_cubic_bezier(easing)
                if bezier and bezier[0] < 0.15:
                    categories['entrance'].append(t)
                else:
                    categories['state_change'].append(t)
            elif dur > 500:
                categories['emphasis'].append(t)
            elif dur <= 200:
                # Default short transitions to hover_feedback
                categories['hover_feedback'].append(t)
            else:
                categories['state_change'].append(t)

        # Build pattern output
        patterns = []
        for name, items in categories.items():
            if not items:
                continue

            # Find most common duration and easing in this category
            dur_counter = Counter(i['duration_ms'] for i in items)
            easing_counter = Counter(i['easing'] for i in items)
            prop_counter = Counter(i['property'] for i in items)

            # Get unique selectors
            selectors = list(set(i.get('selector', '') for i in items if i.get('selector')))[:5]

            patterns.append({
                'name': name,
                'duration_ms': dur_counter.most_common(1)[0][0],
                'easing': easing_counter.most_common(1)[0][0],
                'properties': [p for p, _ in prop_counter.most_common(5) if p != 'all'],
                'element_count': len(items),
                'selectors_sample': selectors
            })

        # Sort by element_count descending
        patterns.sort(key=lambda p: p['element_count'], reverse=True)

        return patterns

    def _process_keyframes(self, parsed_animations: List[Dict], parsed_keyframes: List[Dict]) -> List[Dict]:
        """Build keyframe animation token entries."""
        tokens = []
        seen_names = set()

        for anim in parsed_animations:
            name = anim.get('name')
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            tokens.append({
                'name': name,
                'duration_ms': anim.get('duration_ms', 0),
                'easing': anim.get('easing', 'ease'),
                'iteration': anim.get('iteration', '1'),
                'direction': anim.get('direction', 'normal')
            })

        # Add any keyframes not referenced by animations
        for kf in parsed_keyframes:
            name = kf.get('name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                tokens.append({
                    'name': name,
                    'duration_ms': 0,
                    'easing': 'ease',
                    'iteration': '1',
                    'direction': 'normal'
                })

        return tokens

    def _calculate_confidence(self, parsed_transitions: List, all_durations: List,
                              all_easings: List, motion_patterns: List,
                              easing_palette: Dict, keyframe_tokens: List) -> int:
        """Calculate confidence score for motion token synthesis."""
        score = 30  # Base

        if len(parsed_transitions) >= 5:
            score += 15
        elif len(parsed_transitions) >= 2:
            score += 8

        unique_durations = len(set(all_durations))
        if unique_durations >= 3:
            score += 15
        elif unique_durations >= 2:
            score += 8

        unique_easings = len(set(all_easings))
        if unique_easings >= 2:
            score += 10

        if motion_patterns:
            score += 10

        # Bonus for known curve matches
        curves = easing_palette.get('curves', [])
        known_matches = sum(1 for c in curves if c.get('known_as'))
        if known_matches > 0:
            score += 10

        if keyframe_tokens:
            score += 10

        return min(score, 95)

    # ──────────────────────────────────────────────
    # Choreography Narrator (human-readable motion descriptions)
    # ──────────────────────────────────────────────

    def _classify_selector(self, selector: str) -> str:
        """Map a CSS selector to a human-readable element type.
        '.gallery_card_image' → 'gallery image', '.slick-prev' → 'carousel control'
        """
        sel_lower = selector.lower()
        for pattern, element_type in self.SELECTOR_ELEMENT_MAP:
            if pattern in sel_lower:
                return element_type

        # BEM decomposition: .component__element → "component"
        bem_match = re.search(r'\.([a-zA-Z][\w-]*?)(?:__|\-\-)', selector)
        if bem_match:
            name = bem_match.group(1).replace('-', ' ').replace('_', ' ')
            if len(name) > 2 and name not in ('sc', 'css', 'js'):
                return name

        # Strip punctuation and return cleaned selector
        clean = re.sub(r'[.#\[\]:>+~="\'\s]', ' ', selector).strip()
        # Remove single-char fragments
        words = [w for w in clean.split() if len(w) > 1 and not w.startswith('0x')]
        if words:
            return ' '.join(words[:2])

        return 'element'

    def _classify_selectors(self, selectors: List[str]) -> str:
        """Classify a list of selectors into a combined human-readable name."""
        if not selectors:
            return 'elements'
        types = []
        seen = set()
        for s in selectors[:5]:
            t = self._classify_selector(s)
            if t not in seen:
                seen.add(t)
                types.append(t)
        if len(types) == 1:
            t = types[0]
            # Pluralize simple nouns
            if not t.endswith('s') and not t.endswith('tion'):
                return t + 's'
            return t
        return ' / '.join(types[:3])

    def _duration_tier_name(self, duration_ms: int) -> str:
        """Return the tier name for a duration value."""
        for tier, (low, high) in self.TIER_BOUNDARIES.items():
            if low <= duration_ms <= high:
                return tier
        return 'normal'

    def _parse_keyframe_steps(self, css_text: str) -> List[Dict]:
        """Parse @keyframes cssText into structured steps.
        Input: '@keyframes fade { 0% { opacity: 0; } 100% { opacity: 1; } }'
        Output: [{'pct': 0, 'properties': {'opacity': '0'}}, {'pct': 100, 'properties': {'opacity': '1'}}]
        """
        if not css_text:
            return []

        # Strip outer @keyframes wrapper
        inner = re.sub(r'@-?(?:webkit-)?keyframes\s+[\w-]+\s*\{', '', css_text, count=1)
        # Remove trailing }
        if inner.rstrip().endswith('}'):
            inner = inner.rstrip()[:-1]

        steps = []
        # Find all percentage steps: "0% { ... }" or "from { ... }" or "to { ... }"
        step_pattern = re.finditer(r'(from|to|\d+%)\s*\{([^}]*)\}', inner)
        for match in step_pattern:
            pct_str = match.group(1)
            props_str = match.group(2)

            if pct_str == 'from':
                pct = 0
            elif pct_str == 'to':
                pct = 100
            else:
                pct = int(pct_str.replace('%', ''))

            properties = {}
            for decl in props_str.split(';'):
                decl = decl.strip()
                if ':' in decl:
                    prop, val = decl.split(':', 1)
                    properties[prop.strip()] = val.strip()

            if properties:
                steps.append({'pct': pct, 'properties': properties})

        return steps

    def _describe_keyframe_motion(self, steps: List[Dict]) -> str:
        """Describe what a keyframe animation does based on its steps.
        Returns plain English like 'slides horizontally' or 'fades in while scaling up'.
        """
        if not steps:
            return 'animates'

        all_props = {}
        for step in steps:
            for prop, val in step.get('properties', {}).items():
                if prop not in all_props:
                    all_props[prop] = []
                all_props[prop].append(val)

        descriptions = []

        # Transform analysis
        if 'transform' in all_props:
            transforms = ' '.join(all_props['transform'])
            if 'translateX' in transforms:
                descriptions.append('slides horizontally')
            elif 'translateY' in transforms:
                descriptions.append('slides vertically')
            elif 'translate' in transforms:
                descriptions.append('moves position')
            if 'scale' in transforms:
                descriptions.append('scales')
            if 'rotate' in transforms:
                if '360' in transforms or '1050' in transforms:
                    descriptions.append('spins')
                else:
                    descriptions.append('rotates')

        # Opacity analysis
        if 'opacity' in all_props:
            vals = all_props['opacity']
            try:
                numeric = [float(v) for v in vals]
                if len(numeric) >= 2:
                    if numeric[0] < numeric[-1]:
                        descriptions.append('fades in')
                    elif numeric[0] > numeric[-1]:
                        descriptions.append('fades out')
                    elif len(numeric) >= 3:
                        descriptions.append('pulses opacity')
                else:
                    descriptions.append('changes opacity')
            except (ValueError, TypeError):
                descriptions.append('changes opacity')

        # Color/background
        for prop in ['color', 'background-color', 'backgroundColor', 'background']:
            if prop in all_props:
                descriptions.append('shifts color')
                break

        # Filter
        if 'filter' in all_props:
            descriptions.append('applies visual filter')

        if not descriptions:
            descriptions.append('animates')

        return ' and '.join(descriptions[:3])

    def _describe_motion_pattern(self, pattern: Dict, easing_palette: Dict) -> Dict:
        """Generate a human-readable choreography entry from a motion pattern."""
        name = pattern.get('name', '')
        properties = pattern.get('properties', [])
        selectors = pattern.get('selectors_sample', [])
        duration = pattern.get('duration_ms', 0)
        easing = pattern.get('easing', '')
        count = pattern.get('element_count', 0)

        # Classify elements
        elements = self._classify_selectors(selectors)

        # Describe what properties do in plain English (filter noise)
        prop_descriptions = []
        for prop in properties[:5]:
            if prop in self.SKIP_PROPERTIES or prop.startswith('--'):
                continue
            verb = self.PROPERTY_VERBS.get(prop, prop)
            prop_descriptions.append(verb)
        if not prop_descriptions:
            prop_descriptions = ['transitions']

        prop_text = ' and '.join(prop_descriptions[:3])

        # Duration adjective
        tier = self._duration_tier_name(duration)
        adj = self.DURATION_ADJECTIVES.get(tier, 'smooth')

        # Easing attribution
        easing_attr = ''
        curves = easing_palette.get('curves', [])
        for c in curves:
            if c.get('value') == easing and c.get('known_as'):
                known = c['known_as'].replace('-', ' ').replace('_', ' ')
                if not known.startswith('css'):
                    easing_attr = f" ({known} curve)"
                break

        # Trigger inference
        trigger_map = {
            'hover_feedback': 'hover (CSS)',
            'focus_ring': 'focus (CSS)',
            'state_change': 'interaction',
            'entrance': 'page load / scroll',
            'emphasis': 'hover or continuous',
        }
        trigger = trigger_map.get(name, 'interaction')

        # Build description sentence
        description = f"{elements.capitalize()}: {adj} {prop_text} ({duration}ms {easing}){easing_attr}"
        if count > 5:
            description += f" — {count} elements"

        return {
            'description': description,
            'elements': elements,
            'trigger': trigger,
            'properties': properties,
            'timing': f"{duration}ms {easing}",
            'source': 'transition'
        }

    def _narrate_keyframe(self, keyframe_token: Dict, parsed_steps: List[Dict]) -> Optional[Dict]:
        """Generate a choreography entry from a keyframe animation."""
        name = keyframe_token.get('name', '')
        duration = keyframe_token.get('duration_ms', 0)
        easing = keyframe_token.get('easing', 'ease')
        iteration = keyframe_token.get('iteration', '1')
        direction = keyframe_token.get('direction', 'normal')

        if not name:
            return None

        # Skip generic/artifact keyframe names that aren't real animations
        skip_names = {'normal', 'none', 'initial', 'inherit', 'unset', 'revert'}
        if name.lower() in skip_names:
            return None

        # Describe the motion from parsed steps
        motion_desc = self._describe_keyframe_motion(parsed_steps)

        # Iteration qualifier
        loop_text = ''
        if iteration == 'infinite':
            loop_text = ' continuously'
        elif direction == 'alternate':
            loop_text = ' back and forth'

        # Clean up animation name for display
        display_name = name.replace('-', ' ').replace('_', ' ')

        # Duration text
        if duration > 0:
            tier = self._duration_tier_name(duration)
            adj = self.DURATION_ADJECTIVES.get(tier, '')
            dur_text = f" over {adj} {duration}ms" if adj else f" over {duration}ms"
        else:
            dur_text = ''

        description = f"Keyframe '{display_name}': {motion_desc}{loop_text}{dur_text}"

        # Infer properties from steps
        properties = []
        for step in parsed_steps:
            for prop in step.get('properties', {}):
                if prop not in properties:
                    properties.append(prop)

        return {
            'description': description,
            'elements': display_name,
            'trigger': 'JS-controlled',
            'properties': properties[:5],
            'timing': f"{duration}ms {easing}" if duration else easing,
            'source': 'keyframe'
        }

    def _generate_choreography(self, motion_patterns: List[Dict],
                                keyframe_tokens: List[Dict],
                                parsed_keyframes: List[Dict],
                                easing_palette: Dict) -> List[Dict]:
        """Orchestrate: build list of human-readable choreography entries."""
        entries = []

        # 1. Describe each motion pattern
        for pattern in motion_patterns:
            entry = self._describe_motion_pattern(pattern, easing_palette)
            entries.append(entry)

        # 2. Narrate keyframe animations
        kf_by_name = {kf.get('name', ''): kf for kf in parsed_keyframes}
        for token in keyframe_tokens:
            name = token.get('name', '')
            css_text = kf_by_name.get(name, {}).get('css_text', '')
            parsed_steps = self._parse_keyframe_steps(css_text)
            entry = self._narrate_keyframe(token, parsed_steps)
            if entry:
                entries.append(entry)

        # 3. Sort: transition patterns by duration desc, then keyframes
        transition_entries = [e for e in entries if e['source'] == 'transition']
        keyframe_entries = [e for e in entries if e['source'] == 'keyframe']
        transition_entries.sort(key=lambda e: int(e['timing'].split('ms')[0]) if 'ms' in e['timing'] else 0, reverse=True)

        return transition_entries + keyframe_entries

    def _generate_personality(self, choreography: List[Dict],
                               duration_scale: Dict, easing_palette: Dict,
                               libraries: List[str]) -> str:
        """Generate a 1-3 sentence motion personality summary."""
        tiers = duration_scale.get('tiers', {})
        total = duration_scale.get('total_parsed', 0)

        if total == 0 and not choreography:
            return 'Static — no CSS transitions or animations detected.'

        parts = []

        # Personality archetype from tier distribution
        fast_count = sum(t.get('count', 0) for name, t in tiers.items() if name in ('micro', 'fast'))
        slow_count = sum(t.get('count', 0) for name, t in tiers.items() if name in ('slow', 'dramatic'))

        if total <= 3:
            parts.append('Minimal motion')
        elif fast_count > slow_count * 2:
            parts.append('Snappy and responsive')
        elif slow_count > fast_count:
            parts.append('Cinematic and deliberate')
        else:
            parts.append('Balanced motion')

        # Notable easing attribution
        curves = easing_palette.get('curves', [])
        notable_curves = [c for c in curves if c.get('known_as') and not c['known_as'].startswith('css-')]
        if notable_curves:
            best = notable_curves[0]
            system_name = best['known_as'].split('-')[0].capitalize()
            parts.append(f"uses {system_name} design system easing")

        # Keyframe personality
        kf_entries = [e for e in choreography if e['source'] == 'keyframe']
        looping = [e for e in kf_entries if 'continuously' in e.get('description', '')]
        if looping:
            parts.append('has ambient looping animations')
        elif len(kf_entries) >= 3:
            parts.append(f'{len(kf_entries)} distinct keyframe animations')

        # Libraries
        if libraries:
            parts.append(f"powered by {', '.join(libraries)}")

        # Total coverage
        if total > 50:
            parts.append(f'{total} total transitions detected')

        if not parts:
            return 'Minimal motion detected.'
        # Capitalize first letter of each sentence fragment
        sentences = [p[0].upper() + p[1:] for p in parts]
        return '. '.join(sentences) + '.'
