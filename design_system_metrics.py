"""
Design System Metrics - The Missing Pieces

Extracts system-wide design patterns that are critical for implementation:
1. Spacing Scale Detection - All padding/margin/gap values + pattern detection
2. Responsive Breakpoints - Media queries + layout changes
3. Shadow System - box-shadow scale categorization
4. Z-Index Stack - Stacking context visualization
5. Border Radius Scale - All border-radius values + pattern

These metrics answer: "What design system are they using?"
"""

import asyncio
from patchright.async_api import Page
from typing import Dict, List, Tuple
from collections import Counter
import re


class DesignSystemMetrics:
    """
    Extract design system patterns from live sites
    """

    def __init__(self, page: Page):
        self.page = page

    async def extract_spacing_scale(self) -> Dict:
        """
        Extract all spacing values and detect the scale pattern

        Returns system-wide spacing like:
        - 4px, 8px, 16px, 24px, 32px (powers of 2)
        - 0.25rem, 0.5rem, 1rem, 1.5rem (Tailwind-style)
        """
        print("\n📏 Extracting spacing scale...")

        result = await self.page.evaluate('''() => {
            const spacingValues = {
                padding: [],
                margin: [],
                gap: []
            };

            // Get all elements
            const elements = document.querySelectorAll('*');

            for (const el of elements) {
                const styles = window.getComputedStyle(el);

                // Extract padding values
                const padding = styles.padding;
                if (padding && padding !== '0px') {
                    spacingValues.padding.push(padding);
                }

                // Extract margin values
                const margin = styles.margin;
                if (margin && margin !== '0px') {
                    spacingValues.margin.push(margin);
                }

                // Extract gap values (flexbox/grid)
                const gap = styles.gap;
                if (gap && gap !== 'normal' && gap !== '0px') {
                    spacingValues.gap.push(gap);
                }
            }

            return spacingValues;
        }''')

        # Parse spacing values into pixels
        all_spacing_px = []

        for prop_type, values in result.items():
            for value_str in values:
                # Parse compound values like "16px 24px"
                px_values = re.findall(r'(\d+(?:\.\d+)?)px', value_str)
                all_spacing_px.extend([float(v) for v in px_values])

        # Count occurrences
        spacing_counter = Counter(all_spacing_px)

        # Detect pattern (powers of 2, multiples of 4, etc.)
        pattern = self._detect_spacing_pattern(spacing_counter)

        # Get top values
        top_values = spacing_counter.most_common(10)

        # Calculate detailed confidence
        base_confidence = 40  # Pattern detected
        instance_bonus = min(len(all_spacing_px) // 10, 30)  # Up to +30 for high usage
        pattern_bonus = 15 if pattern['base'] else 0  # +15 if matches known system
        total_confidence = min(base_confidence + instance_bonus + pattern_bonus, 95)

        return {
            'confidence': total_confidence,
            'pattern': pattern['type'],
            'base_unit': pattern['base'],
            'scale': pattern['scale'],
            'most_common': {f'{int(v)}px': count for v, count in top_values},
            'total_instances': len(all_spacing_px),
            'unique_values': len(spacing_counter),
            'evidence': {
                'padding_samples': result['padding'][:5],
                'margin_samples': result['margin'][:5],
                'gap_samples': result['gap'][:5]
            },
            'evidence_trail': {
                'found': [
                    f"{len(all_spacing_px)} total spacing values across padding/margin/gap",
                    f"{len(spacing_counter)} unique values",
                    f"Most common: {', '.join(f'{int(v)}px ({c}×)' for v, c in top_values[:3])}"
                ],
                'analyzed': [
                    f"Checked for powers of 2 pattern",
                    f"Checked for multiples of 8 (Material Design)",
                    f"Checked for multiples of 4 (common systems)"
                ],
                'concluded': f"Pattern identified as '{pattern['type']}' with base unit {pattern['base']}px" if pattern['base'] else f"Custom spacing pattern detected",
                'confidence_breakdown': {
                    'base_detection': base_confidence,
                    'usage_frequency': instance_bonus,
                    'system_match': pattern_bonus,
                    'total': total_confidence
                }
            }
        }

    def _detect_spacing_pattern(self, counter: Counter) -> Dict:
        """
        Detect spacing pattern from observed values

        Heuristic: Checks for common design system patterns:
        1. Powers of 2 (4, 8, 16, 32...) - Common in Tailwind, Bootstrap
        2. Multiples of 8 (8, 16, 24, 32...) - Material Design baseline
        3. Multiples of 4 (4, 8, 12, 16...) - Most design systems

        Confidence calculation:
        - Base 40: Pattern detected
        - +2 per value matching pattern (capped at 95)

        Returns pattern type and base unit for scale generation.
        """
        values = sorted([v for v in counter.keys() if v > 0])

        if not values:
            return {'type': 'No spacing detected', 'base': 0, 'scale': []}

        # Check for powers of 2
        powers_of_2 = [4, 8, 16, 24, 32, 48, 64, 96, 128]
        matches = sum(1 for v in values if v in powers_of_2)
        if matches >= 4:
            scale = [v for v in powers_of_2 if v in values]
            return {
                'type': 'Powers of 2 (Tailwind-style)',
                'base': 4,
                'scale': scale
            }

        # Check for multiples of 8
        multiples_of_8 = all(v % 8 == 0 for v in values[:5])
        if multiples_of_8:
            return {
                'type': '8pt grid system',
                'base': 8,
                'scale': [v for v in values if v % 8 == 0][:8]
            }

        # Check for multiples of 4
        multiples_of_4 = all(v % 4 == 0 for v in values[:5])
        if multiples_of_4:
            return {
                'type': '4pt grid system',
                'base': 4,
                'scale': [v for v in values if v % 4 == 0][:8]
            }

        # Default: custom scale
        return {
            'type': 'Custom spacing (no clear pattern)',
            'base': min(values) if values else 0,
            'scale': values[:8]
        }

    async def extract_responsive_breakpoints(self) -> Dict:
        """
        Extract media query breakpoints and detect responsive strategy
        """
        print("\n📱 Extracting responsive breakpoints...")

        result = await self.page.evaluate('''() => {
            const breakpoints = [];

            // Get all stylesheets
            for (const sheet of document.styleSheets) {
                try {
                    const rules = sheet.cssRules || sheet.rules;
                    for (const rule of rules) {
                        if (rule.type === CSSRule.MEDIA_RULE) {
                            const mediaText = rule.media.mediaText;
                            breakpoints.push(mediaText);
                        }
                    }
                } catch (e) {
                    // CORS or other issues
                }
            }

            // Also check viewport meta tag
            const viewport = document.querySelector('meta[name="viewport"]');
            const viewportContent = viewport ? viewport.content : null;

            return {
                breakpoints: breakpoints,
                viewport: viewportContent,
                current_width: window.innerWidth,
                current_height: window.innerHeight
            };
        }''')

        # Parse breakpoints and preserve media query text
        breakpoint_values = []
        media_queries = []
        for bp in result['breakpoints']:
            # Store the full media query text
            media_queries.append(bp)
            # Extract pixel values from media queries
            matches = re.findall(r'(\d+)px', bp)
            breakpoint_values.extend([int(m) for m in matches])

        # Count and categorize
        bp_counter = Counter(breakpoint_values)
        unique_breakpoints = sorted(set(breakpoint_values))

        # Detect breakpoint strategy
        strategy = self._detect_breakpoint_strategy(unique_breakpoints)

        return {
            'confidence': self._calculate_breakpoint_confidence(
                breakpoint_values, unique_breakpoints, strategy, result),
            'pattern': strategy['type'],
            'breakpoints': strategy['breakpoints'],
            'total_media_queries': len(result['breakpoints']),
            'unique_breakpoints': unique_breakpoints[:10],
            'media_queries': media_queries[:20],  # Keep first 20 actual media queries
            'viewport_meta': result['viewport'],
            'current_size': {
                'width': result['current_width'],
                'height': result['current_height']
            },
            'evidence': {
                'samples': result['breakpoints'][:5]
            }
        }

    @staticmethod
    def _calculate_breakpoint_confidence(bp_values, unique_bps, strategy, result):
        """Formula-based confidence for responsive breakpoints."""
        if not bp_values:
            return 40  # No breakpoints found but extraction ran
        confidence = 40
        confidence += min(30, len(unique_bps) * 8)          # +8 per unique BP, max 30
        if strategy.get('type', '').lower() not in ('custom', 'unknown', ''):
            confidence += 15                                  # Known framework match
        confidence += min(10, len(result.get('breakpoints', [])) * 2)  # Query count
        return min(95, confidence)

    def _detect_breakpoint_strategy(self, breakpoints: List[int]) -> Dict:
        """
        Detect if breakpoints match common frameworks

        Heuristic: Matches observed breakpoints against known framework patterns
        - Tailwind: [640, 768, 1024, 1280, 1536]
        - Bootstrap: [576, 768, 992, 1200, 1400]
        - Material: [600, 960, 1280, 1920]
        - Foundation: [640, 1024, 1200, 1440]

        Confidence: Requires 3+ matching breakpoints to classify as framework
        Rationale: 3 matches indicates intentional pattern, not coincidence

        Failure modes:
        - Custom breakpoints won't match any framework
        - Hybrid systems using multiple frameworks may match incorrectly
        """
        if not breakpoints:
            return {
                'type': 'No responsive design detected',
                'breakpoints': {}
            }

        # Tailwind breakpoints
        tailwind_bp = [640, 768, 1024, 1280, 1536]
        tailwind_matches = sum(1 for bp in breakpoints if bp in tailwind_bp)

        if tailwind_matches >= 3:
            return {
                'type': 'Tailwind CSS breakpoints',
                'breakpoints': {
                    'sm': '640px',
                    'md': '768px',
                    'lg': '1024px',
                    'xl': '1280px',
                    '2xl': '1536px'
                }
            }

        # Bootstrap breakpoints
        bootstrap_bp = [576, 768, 992, 1200, 1400]
        bootstrap_matches = sum(1 for bp in breakpoints if bp in bootstrap_bp)

        if bootstrap_matches >= 3:
            return {
                'type': 'Bootstrap breakpoints',
                'breakpoints': {
                    'sm': '576px',
                    'md': '768px',
                    'lg': '992px',
                    'xl': '1200px',
                    'xxl': '1400px'
                }
            }

        # Custom breakpoints
        labels = ['mobile', 'tablet', 'desktop', 'wide', 'ultra-wide']
        custom_bp = {}
        for i, bp in enumerate(sorted(breakpoints)[:5]):
            custom_bp[labels[i]] = f'{bp}px'

        return {
            'type': 'Custom breakpoints',
            'breakpoints': custom_bp
        }

    async def extract_shadow_system(self) -> Dict:
        """
        Extract box-shadow values with usage counts and element context.

        Returns each unique shadow with:
        - The actual CSS value (copy/paste ready)
        - How many elements use it
        - Sample selectors so you know WHERE it lives
        - A semantic name (Subtle / Elevated / Floating) based on blur
        """
        print("\n☁️  Extracting shadow system...")

        result = await self.page.evaluate("""
            () => {
                const shadowMap = {};
                const elements = document.querySelectorAll('*');

                for (const el of elements) {
                    const styles = window.getComputedStyle(el);
                    const shadow = styles.boxShadow;

                    if (shadow && shadow !== 'none') {
                        if (!shadowMap[shadow]) {
                            shadowMap[shadow] = { count: 0, selectors: [] };
                        }
                        shadowMap[shadow].count += 1;

                        // Grab up to 3 selector examples per shadow
                        if (shadowMap[shadow].selectors.length < 3) {
                            let sel = '';
                            if (el.id) {
                                sel = '#' + el.id;
                            } else if (el.className && typeof el.className === 'string') {
                                sel = '.' + el.className.trim().split(/\\s+/)[0];
                            } else {
                                sel = el.tagName.toLowerCase();
                            }
                            if (sel && !shadowMap[shadow].selectors.includes(sel)) {
                                shadowMap[shadow].selectors.push(sel);
                            }
                        }
                    }
                }

                return shadowMap;
            }
        """)

        if not result:
            return {
                'confidence': 85,
                'pattern': 'No shadows detected',
                'scale': {},
                'levels': [],
                'total_instances': 0,
                'unique_shadows': 0,
                'evidence_trail': {
                    'found': ['No box-shadow values found on any element'],
                    'analyzed': [],
                    'concluded': 'Site uses a flat design with no elevation'
                }
            }

        # Build levelled output: sort by usage, assign semantic names
        total_instances = sum(entry['count'] for entry in result.values())

        # Collect all blur radii for relative naming
        all_blurs = [self._extract_blur(css) for css in result.keys()]

        levels = []
        for css_value, entry in sorted(result.items(), key=lambda x: x[1]['count'], reverse=True):
            blur = self._extract_blur(css_value)
            levels.append({
                'css': css_value,
                'count': entry['count'],
                'usage_pct': round((entry['count'] / total_instances) * 100, 1),
                'selectors': entry['selectors'],
                'blur_radius': blur,
                'name': self._shadow_semantic_name(blur, all_blurs)
            })

        # Build the scale dict keyed by semantic name for the dashboard card
        # (dashboard's createShadowCard iterates scale entries)
        scale = {}
        for lvl in levels:
            name = lvl['name']
            if name not in scale:
                scale[name] = []
            scale[name].append({'shadow': lvl['css'], 'count': lvl['count']})

        unique_count = len(levels)
        confidence = min(40 + (total_instances // 5) + (unique_count * 5), 95)

        return {
            'confidence': confidence,
            'pattern': f'{unique_count} unique shadow{"s" if unique_count != 1 else ""} across {total_instances} elements',
            'scale': scale,
            'levels': levels,          # ← new: ordered list with full context
            'total_instances': total_instances,
            'unique_shadows': unique_count,
            'evidence_trail': {
                'found': [
                    f'{total_instances} elements with box-shadow',
                    f'{unique_count} unique shadow values',
                    f'Most used: {levels[0]["css"][:60]}... ({levels[0]["count"]} uses)' if levels else 'None'
                ],
                'analyzed': [
                    f'Blur radii range: {min(l["blur_radius"] for l in levels)}px – {max(l["blur_radius"] for l in levels)}px' if levels else '',
                    f'Semantic levels detected: {", ".join(set(l["name"] for l in levels))}' if levels else ''
                ],
                'concluded': f'Elevation system with {len(set(l["name"] for l in levels))} distinct levels' if levels else 'No shadows'
            }
        }

    def _extract_blur(self, shadow_css: str) -> int:
        """Pull the blur radius out of a box-shadow string."""
        match = re.search(r'(\d+)px\s+(\d+)px\s+(\d+)px', shadow_css)
        return int(match.group(3)) if match else 0

    def _shadow_semantic_name(self, blur: int, all_blurs: list = None) -> str:
        """Map blur radius → human-readable elevation name.
        Uses relative distribution when multiple shadows exist,
        falls back to absolute thresholds for ≤2 shadows."""
        if all_blurs and len(all_blurs) > 2:
            return self._shadow_name_relative(blur, all_blurs)
        # Absolute fallback for sites with very few shadows
        if blur <= 2:
            return 'Subtle'
        elif blur <= 6:
            return 'Card'
        elif blur <= 15:
            return 'Elevated'
        elif blur <= 30:
            return 'Floating'
        else:
            return 'Deep'

    def _shadow_name_relative(self, blur: int, all_blurs: list) -> str:
        """Assign name based on position within the site's own shadow range.
        Ensures each tier gets a distinct label even when blur values cluster."""
        unique_sorted = sorted(set(all_blurs))
        if len(unique_sorted) <= 1:
            return 'Default'
        rank = unique_sorted.index(blur)
        pct = rank / (len(unique_sorted) - 1)  # 0.0 to 1.0
        if pct <= 0.2:
            return 'Subtle'
        elif pct <= 0.4:
            return 'Card'
        elif pct <= 0.6:
            return 'Elevated'
        elif pct <= 0.8:
            return 'Heavy'
        else:
            return 'Deep'

    async def extract_z_index_stack(self) -> Dict:
        """
        Extract all z-index values and visualize stacking context
        """
        print("\n📚 Extracting z-index stack...")

        result = await self.page.evaluate('''() => {
            const zIndexes = [];
            const elements = document.querySelectorAll('*');

            for (const el of elements) {
                const styles = window.getComputedStyle(el);
                const zIndex = styles.zIndex;

                if (zIndex && zIndex !== 'auto') {
                    const z = parseInt(zIndex);
                    if (isNaN(z)) continue;
                    // SVG elements have className as SVGAnimatedString
                    const safeClass = (typeof el.className === 'string')
                        ? el.className : (el.className?.baseVal || '');
                    const bounds = el.getBoundingClientRect();
                    const isVisible = bounds.width > 0 && bounds.height > 0
                        && styles.visibility !== 'hidden'
                        && styles.display !== 'none';
                    const isFixed = styles.position === 'fixed';
                    const isSticky = styles.position === 'sticky';
                    const isInteractive = ['A','BUTTON','INPUT','SELECT','TEXTAREA'].includes(el.tagName)
                        || el.getAttribute('role') === 'button'
                        || el.getAttribute('tabindex') !== null;
                    const textPreview = el.textContent?.trim()?.substring(0, 40) || '';
                    // Build a CSS selector for isolation screenshots
                    let selector = '';
                    if (el.id) {
                        selector = '#' + CSS.escape(el.id);
                    } else {
                        const tag = el.tagName.toLowerCase();
                        const meaningful = Array.from(el.classList)
                            .filter(c => !c.match(/^(js-|is-|has-|active|open|show|hide)/))
                            .slice(0, 2)
                            .map(c => '.' + CSS.escape(c))
                            .join('');
                        selector = tag + meaningful;
                        // Disambiguate if not unique
                        try {
                            if (selector && document.querySelectorAll(selector).length > 1) {
                                const parent = el.parentElement;
                                if (parent) {
                                    const sameTag = Array.from(parent.children)
                                        .filter(s => s.tagName === el.tagName);
                                    const idx = sameTag.indexOf(el) + 1;
                                    if (idx > 0) selector += ':nth-of-type(' + idx + ')';
                                }
                            }
                        } catch(e) { /* CSS.escape edge case */ }
                    }

                    zIndexes.push({
                        z: z,
                        tag: el.tagName.toLowerCase(),
                        classes: safeClass,
                        id: el.id || '',
                        role: el.getAttribute('role') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        selector: selector,
                        position: styles.position,
                        isFixed: isFixed,
                        isSticky: isSticky,
                        isVisible: isVisible,
                        isInteractive: isInteractive,
                        textPreview: textPreview,
                        bounds: {
                            x: Math.round(bounds.left),
                            y: Math.round(bounds.top),
                            width: Math.round(bounds.width),
                            height: Math.round(bounds.height)
                        }
                    });
                }
            }

            return zIndexes;
        }''')

        # ── Authoring-level layer info: CSS cascade layers + nested-rule z-index ──
        # The computed-style walk above tells us what each element renders as.
        # This walks the CSSOM to tell us what the author *wrote*:
        #   - @layer blocks give named cascade priority (not z-index, but the
        #     higher-level stacking system — modals-layer > components-layer > base)
        #   - Nested rules containing z-index show which parent selector the
        #     z-index was authored against, revealing component-scoped layering
        authoring = await self._extract_authoring_layers()

        # Categorize z-indexes into semantic tiers
        layers = self._categorize_z_indexes(result)

        # Detect conflicts
        conflicts = self._detect_z_conflicts(result)

        # Health summary
        health = self._z_index_health(result)

        # Count visible vs ghost
        visible_count = sum(1 for d in result if d.get('isVisible', True))
        ghost_count = sum(1 for d in result if not d.get('isVisible', True))
        # Count tiers (exclude ghost tier from count)
        tier_count = sum(1 for v in layers.values() if v.get('tier') != 'Ghost')

        # Richer pattern line when authoring layers were found
        pattern_bits = [f'{tier_count} semantic tier{"s" if tier_count != 1 else ""} detected']
        cascade_names = [L.get('name') for L in authoring.get('cascade_layers', []) if L.get('name')]
        if cascade_names:
            pattern_bits.append(f'{len(cascade_names)} cascade layer{"s" if len(cascade_names) != 1 else ""}')
        if authoring.get('scoped_z_rules'):
            pattern_bits.append(f"{len(authoring['scoped_z_rules'])} scoped z-index rule{'s' if len(authoring['scoped_z_rules']) != 1 else ''}")

        return {
            'confidence': 90 if result else 60,
            'pattern': ', '.join(pattern_bits),
            'layers': layers,
            'health': health,
            'total_elements': len(result),
            'visible_elements': visible_count,
            'ghost_elements': ghost_count,
            'conflicts': conflicts,
            'authoring_layers': authoring,
            'evidence': {
                'samples': result[:10]
            }
        }

    async def _extract_authoring_layers(self) -> Dict:
        """Walk document.styleSheets for @layer blocks and nested z-index rules.

        Returns:
            {
                'cascade_layers': [{name, order, rule_count, z_declarations}, ...],
                'scoped_z_rules': [{parent_selector, z_index, context}, ...],
                'nesting_used': bool,
                'cascade_layers_used': bool,
            }

        Walking the CSSOM lets us see layering as authored (not just computed):
        - @layer reset, base, components, utilities; — the declaration order IS
          the cascade priority. Higher layer wins regardless of specificity.
        - .modal { z-index: 100; &.open { z-index: 101; } } — CSSStyleRule now
          exposes .cssRules for nested rules in browsers that support CSS Nesting,
          so we can see "z-index 101 was authored inside .modal.open".
        """
        try:
            return await self.page.evaluate('''() => {
                const result = {
                    cascade_layers: [],
                    scoped_z_rules: [],
                    nesting_used: false,
                    cascade_layers_used: false,
                };

                // Order of layer declarations (from @layer statements) — this
                // IS the z-priority at the cascade level.
                const layerOrderMap = new Map(); // name -> order index
                let nextLayerOrder = 0;
                const layerStats = new Map();    // name -> {rules, z_declarations[]}

                const ensureLayer = (name) => {
                    if (!layerStats.has(name)) {
                        layerStats.set(name, { rule_count: 0, z_declarations: [] });
                    }
                    if (!layerOrderMap.has(name)) {
                        layerOrderMap.set(name, nextLayerOrder++);
                    }
                    return layerStats.get(name);
                };

                // Walk a rule list — recurses into grouping rules, captures
                // @layer names and z-index declarations scoped by their
                // current layer + parent selector context.
                const walk = (rules, ctx) => {
                    if (!rules) return;
                    for (let i = 0; i < rules.length; i++) {
                        let rule;
                        try { rule = rules[i]; } catch(e) { continue; }
                        if (!rule) continue;
                        const ctorName = rule.constructor && rule.constructor.name;

                        // @layer block: { name, cssRules }
                        if (ctorName === 'CSSLayerBlockRule') {
                            result.cascade_layers_used = true;
                            const name = rule.name || '(anonymous)';
                            ensureLayer(name);
                            walk(rule.cssRules, { ...ctx, layer: name });
                            continue;
                        }
                        // @layer statement (no block): @layer reset, base, components;
                        if (ctorName === 'CSSLayerStatementRule') {
                            result.cascade_layers_used = true;
                            const names = rule.nameList || [];
                            names.forEach(n => ensureLayer(n));
                            continue;
                        }

                        // @media / @supports / @scope — walk through
                        if (rule.cssRules && ctorName !== 'CSSStyleRule') {
                            walk(rule.cssRules, ctx);
                            continue;
                        }

                        if (ctorName === 'CSSStyleRule') {
                            const sel = rule.selectorText || '';
                            if (ctx.layer) {
                                const stats = layerStats.get(ctx.layer);
                                if (stats) stats.rule_count++;
                            }

                            // Z-index declaration? Capture the authoring context.
                            const style = rule.style;
                            if (style) {
                                const z = style.getPropertyValue('z-index');
                                if (z && z.trim() && z !== 'auto') {
                                    const parentSel = ctx.parentSelector || '';
                                    const fullSel = parentSel ? parentSel + ' → ' + sel : sel;
                                    result.scoped_z_rules.push({
                                        parent_selector: parentSel || null,
                                        selector: sel,
                                        full_context: fullSel,
                                        z_index: z.trim(),
                                        layer: ctx.layer || null,
                                        nested: !!parentSel,
                                    });
                                    if (ctx.layer) {
                                        const stats = layerStats.get(ctx.layer);
                                        if (stats) stats.z_declarations.push({
                                            selector: fullSel, z_index: z.trim()
                                        });
                                    }
                                }
                            }

                            // CSS Nesting: CSSStyleRule may have cssRules for
                            // nested children. Recurse with this rule as parent.
                            if (rule.cssRules && rule.cssRules.length > 0) {
                                result.nesting_used = true;
                                const nextParent = ctx.parentSelector
                                    ? ctx.parentSelector + ' → ' + sel
                                    : sel;
                                walk(rule.cssRules, { ...ctx, parentSelector: nextParent });
                            }
                        }
                    }
                };

                // Walk every reachable stylesheet
                for (const sheet of Array.from(document.styleSheets)) {
                    let rules;
                    try { rules = sheet.cssRules || sheet.rules; }
                    catch (e) { continue; } // cross-origin, skip
                    if (!rules) continue;
                    walk(rules, { layer: null, parentSelector: null });
                }

                // Serialize cascade layers in declaration order
                const sortedNames = Array.from(layerOrderMap.keys())
                    .sort((a, b) => layerOrderMap.get(a) - layerOrderMap.get(b));
                result.cascade_layers = sortedNames.map((name) => {
                    const stats = layerStats.get(name) || { rule_count: 0, z_declarations: [] };
                    return {
                        name,
                        order: layerOrderMap.get(name),
                        rule_count: stats.rule_count,
                        z_declaration_count: stats.z_declarations.length,
                        z_declarations: stats.z_declarations.slice(0, 10),
                    };
                });

                // Cap scoped_z_rules to keep payload sane
                if (result.scoped_z_rules.length > 50) {
                    result.scoped_z_rules = result.scoped_z_rules.slice(0, 50);
                }
                return result;
            }''')
        except Exception as exc:
            print(f"   ⚠️  Authoring-layer extraction failed: {exc}")
            return {
                'cascade_layers': [],
                'scoped_z_rules': [],
                'nesting_used': False,
                'cascade_layers_used': False,
                'error': str(exc)[:120],
            }

    # Common CSS framework prefixes that obscure meaning
    _FRAMEWORK_PREFIXES = (
        'Mui', 'mui-', 'css-', 'tw-', 'sc-', 'chakra-', 'ant-',
        'v-', 'el-', 'bp3-', 'bp4-', 'mantine-', 'rs-', 'semi-',
    )

    @staticmethod
    def _smart_label(el: Dict) -> str:
        """Generate a human-readable label for a z-index element.
        Priority: aria-label > id > role > first meaningful class > tag.
        Strips common framework prefixes from class names."""
        if el.get('ariaLabel'):
            label = el['ariaLabel']
            return label[:40] if len(label) > 40 else label
        if el.get('id'):
            return f"#{el['id'][:35]}"
        if el.get('role'):
            return f"{el['tag']}[role={el['role']}]"
        classes = el.get('classes', '')
        if classes:
            first_class = classes.split()[0] if isinstance(classes, str) else ''
            if first_class:
                # Strip framework prefixes for cleaner labels
                for prefix in DesignSystemMetrics._FRAMEWORK_PREFIXES:
                    if first_class.startswith(prefix):
                        remainder = first_class[len(prefix):]
                        if remainder:
                            first_class = remainder
                            break
                return f"{el['tag']}.{first_class[:30]}"
        return el.get('tag', 'div')

    # ── Tier definitions for z-index grouping ──
    _Z_TIERS = [
        ('Below',    lambda z: z < 0,                'Background decorations'),
        ('Base',     lambda z: 0 <= z <= 1,          'Default stacking'),
        ('Elevated', lambda z: 2 <= z <= 99,         'Sticky headers, dropdowns, cards'),
        ('Overlay',  lambda z: 100 <= z <= 999,      'Modals, drawers, overlays'),
        ('Critical', lambda z: 1000 <= z <= 9999,    'System UI, notifications'),
        ('Extreme',  lambda z: z >= 10000,           'Z-index wars / framework overrides'),
    ]

    @staticmethod
    def _infer_purpose(elements: List[Dict]) -> str:
        """Infer semantic purpose of a group of z-index elements from their DOM."""
        purposes = set()
        for el in elements:
            tag = el.get('tag', '')
            role = el.get('role', '')
            classes = el.get('classes', '').lower()
            pos = el.get('position', '')

            if tag == 'nav' or role == 'navigation' or 'nav' in classes:
                purposes.add('Navigation')
            elif role == 'dialog' or 'modal' in classes or 'dialog' in classes:
                purposes.add('Modal')
            elif 'overlay' in classes or 'backdrop' in classes:
                purposes.add('Overlay')
            elif 'tooltip' in classes or role == 'tooltip':
                purposes.add('Tooltip')
            elif 'dropdown' in classes or 'menu' in classes or role == 'menu':
                purposes.add('Dropdown')
            elif 'toast' in classes or 'snackbar' in classes or 'notification' in classes:
                purposes.add('Notification')
            elif tag == 'header' or role == 'banner' or 'header' in classes:
                purposes.add('Header')
            elif tag == 'footer' or role == 'contentinfo':
                purposes.add('Footer')
            elif 'player' in classes or 'audio' in classes or 'video' in classes:
                purposes.add('Media Player')
            elif pos == 'fixed':
                purposes.add('Fixed UI')
            elif pos == 'sticky':
                purposes.add('Sticky')

        return ' / '.join(sorted(purposes)) if purposes else 'Content'

    def _categorize_z_indexes(self, z_data: List[Dict]) -> Dict:
        """
        Categorize z-indexes into semantic tiers with purpose inference.
        Groups related z-values instead of creating one layer per value.
        """
        if not z_data:
            return {}

        # Separate visible from ghost elements
        visible_data = [d for d in z_data if d.get('isVisible', True)]
        ghost_data = [d for d in z_data if not d.get('isVisible', True)]

        layers = {}
        for tier_name, tier_test, tier_desc in self._Z_TIERS:
            tier_elements = [d for d in visible_data if tier_test(d['z'])]
            if not tier_elements:
                continue

            z_values_in_tier = sorted(set(d['z'] for d in tier_elements))
            purpose = self._infer_purpose(tier_elements)

            # Collect ALL selectors for this tier (used by screenshot isolation)
            tier_selectors = [el.get('selector', '') for el in tier_elements if el.get('selector')]

            # Build enriched element list with labels, bounds, position
            enriched = []
            for el in tier_elements[:8]:
                enriched.append({
                    'label': self._smart_label(el),
                    'z': el['z'],
                    'selector': el.get('selector', ''),
                    'position': el.get('position', 'static'),
                    'isInteractive': el.get('isInteractive', False),
                    'isVisible': True,
                    'bounds': el.get('bounds', {}),
                    'textPreview': el.get('textPreview', ''),
                })

            layers[f'{tier_name}: {purpose}'] = {
                'z_index': z_values_in_tier[0],  # lowest in tier
                'z_max': z_values_in_tier[-1],
                'z_values': z_values_in_tier,
                'count': len(tier_elements),
                'visible_count': len(tier_elements),
                'interactive_count': sum(1 for d in tier_elements if d.get('isInteractive')),
                'ghost_count': 0,
                'tier': tier_name,
                'tier_desc': tier_desc,
                'purpose': purpose,
                'elements': enriched,
                'all_selectors': tier_selectors,  # for screenshot isolation
            }

        # Ghost tier (zero-size elements)
        if ghost_data:
            layers['Ghost: Tracking / Hidden'] = {
                'z_index': min(d['z'] for d in ghost_data),
                'z_max': max(d['z'] for d in ghost_data),
                'z_values': sorted(set(d['z'] for d in ghost_data)),
                'count': len(ghost_data),
                'visible_count': 0,
                'interactive_count': 0,
                'ghost_count': len(ghost_data),
                'tier': 'Ghost',
                'tier_desc': 'Zero-size or hidden elements',
                'purpose': 'Tracking / Hidden',
                'elements': [{'label': self._smart_label(e), 'z': e['z'],
                              'isVisible': False, 'bounds': e.get('bounds', {})}
                             for e in ghost_data[:5]],
            }

        return layers

    def _z_index_health(self, z_data: List[Dict]) -> Dict:
        """Compute z-index health: Clean / Complex / Chaotic, with system analysis."""
        if not z_data:
            return {'level': 'Clean', 'detail': 'No z-index values detected'}

        visible = [d for d in z_data if d.get('isVisible', True)]
        unique_z = sorted(set(d['z'] for d in visible))
        num_unique = len(unique_z)
        max_z = max(unique_z) if unique_z else 0

        # Detect intentionality: powers of 10, multiples of 100/10
        intentional_values = [z for z in unique_z if z == 0 or z == 1 or (z > 0 and (z % 10 == 0 or z % 100 == 0))]
        intentional_ratio = len(intentional_values) / max(1, num_unique)
        is_intentional = intentional_ratio >= 0.6

        # Spread ratio: high with few values = intentional spacing
        spread_ratio = max_z / max(1, num_unique) if max_z > 0 else 0

        # Fixed/sticky count
        fixed_count = sum(1 for d in visible if d.get('isFixed'))
        sticky_count = sum(1 for d in visible if d.get('isSticky'))

        # Determine level
        if num_unique <= 5 and max_z <= 1000:
            level = 'Clean'
            detail = f'{num_unique} intentional tiers' if is_intentional else f'{num_unique} values, max {max_z}'
        elif num_unique <= 10 and max_z <= 10000:
            level = 'Complex'
            detail = f'{num_unique} values (max {max_z})'
            if not is_intentional:
                detail += ' — ad-hoc values detected'
        else:
            level = 'Chaotic'
            detail = f'{num_unique} values, max {max_z} — consider consolidating to 5 tiers'

        return {
            'level': level,
            'detail': detail,
            'unique_count': num_unique,
            'max_z': max_z,
            'is_intentional': is_intentional,
            'intentional_ratio': round(intentional_ratio, 2),
            'fixed_count': fixed_count,
            'sticky_count': sticky_count,
        }

    def _detect_z_conflicts(self, z_data: List[Dict]) -> List[str]:
        """
        Detect z-index anti-patterns with actionable, specific messages.
        """
        conflicts = []
        visible = [d for d in z_data if d.get('isVisible', True)]
        z_values = [d['z'] for d in visible]
        if not z_values:
            return ['✅ No z-index values detected']

        unique_z = sorted(set(z_values))

        # Z-index wars: multiple values above 10000
        extreme = [z for z in unique_z if z >= 10000]
        if len(extreme) >= 2:
            conflicts.append(f'⚠️  Z-index war: {len(extreme)} values above 10000 ({", ".join(str(z) for z in extreme[:4])}). Consider consolidating to a single overlay tier.')
        elif len(extreme) == 1:
            conflicts.append(f'⚠️  Extreme z-index ({extreme[0]}) — may indicate framework override or escalation.')

        # Crowded tier: many values in a small range
        elevated = [z for z in unique_z if 2 <= z <= 99]
        if len(elevated) > 5:
            conflicts.append(f'⚠️  Crowded elevated tier: {len(elevated)} values between 2-99 — these may visually conflict.')

        # Orphan values that don't fit tier patterns
        orphans = [z for z in unique_z if z > 1 and z not in [10, 50, 100, 200, 500, 1000, 2000, 5000, 9999]
                    and z % 10 not in [0, 5] and z < 10000]
        if orphans:
            conflicts.append(f'⚠️  Orphan values: {", ".join(str(z) for z in orphans[:5])} — likely ad-hoc fixes.')

        if not conflicts:
            clean_msg = f'✅ Clean system: {len(unique_z)} intentional tier{"s" if len(unique_z) != 1 else ""}'
            if len(unique_z) <= 5:
                clean_msg += f' at {", ".join(str(z) for z in unique_z)}'
            conflicts.append(clean_msg)

        return conflicts

    async def extract_border_radius_scale(self) -> Dict:
        """
        Extract border-radius values with usage counts and element context.

        Returns each unique radius with:
        - The pixel value
        - How many elements use it
        - Sample selectors (where it lives)
        - A semantic name (Sharp / Subtle / Medium / Pill / Circular)
        """
        print("\n🔘 Extracting border radius scale...")

        result = await self.page.evaluate("""
            () => {
                const radiusMap = {};
                const elements = document.querySelectorAll('*');

                for (const el of elements) {
                    const styles = window.getComputedStyle(el);
                    const radius = styles.borderRadius;

                    if (radius && radius !== '0px') {
                        if (!radiusMap[radius]) {
                            radiusMap[radius] = { count: 0, selectors: [] };
                        }
                        radiusMap[radius].count += 1;

                        if (radiusMap[radius].selectors.length < 3) {
                            let sel = '';
                            if (el.id) {
                                sel = '#' + el.id;
                            } else if (el.className && typeof el.className === 'string') {
                                sel = '.' + el.className.trim().split(/\\s+/)[0];
                            } else {
                                sel = el.tagName.toLowerCase();
                            }
                            if (sel && !radiusMap[radius].selectors.includes(sel)) {
                                radiusMap[radius].selectors.push(sel);
                            }
                        }
                    }
                }

                return radiusMap;
            }
        """)

        if not result:
            return {
                'confidence': 50,
                'pattern': 'No border radius detected',
                'scale': [],
                'levels': [],
                'special_cases': {'circular': 0, 'pill': 0},
                'total_instances': 0,
                'unique_values': 0,
                'evidence_trail': {
                    'found': ['No border-radius found — site uses sharp corners everywhere'],
                    'analyzed': [],
                    'concluded': 'Flat / sharp design language'
                }
            }

        # Parse into structured levels
        total_instances = sum(entry['count'] for entry in result.values())
        levels = []
        special_cases = {'circular': 0, 'pill': 0}
        scale_values = []  # raw px numbers for the old scale field

        for raw_value, entry in result.items():
            # Detect specials
            if '50%' in raw_value:
                special_cases['circular'] += entry['count']
                levels.append({
                    'value': '50%',
                    'display': '50% (Circular)',
                    'count': entry['count'],
                    'usage_pct': round((entry['count'] / total_instances) * 100, 1),
                    'selectors': entry['selectors'],
                    'name': 'Circular'
                })
                continue

            # Extract first numeric px value for classification
            px_match = re.findall(r'(\d+(?:\.\d+)?)px', raw_value)
            if not px_match:
                continue

            first_px = float(px_match[0])

            if first_px >= 999:
                special_cases['pill'] += entry['count']
                name = 'Pill'
                display = f'{int(first_px)}px (Pill)'
            else:
                name = self._radius_semantic_name(first_px)
                display = f'{int(first_px)}px'
                scale_values.append(int(first_px))

            levels.append({
                'value': raw_value,
                'display': display,
                'px': first_px,
                'count': entry['count'],
                'usage_pct': round((entry['count'] / total_instances) * 100, 1),
                'selectors': entry['selectors'],
                'name': name
            })

        # Sort by usage (most common first)
        levels.sort(key=lambda x: x['count'], reverse=True)
        scale_values = sorted(set(scale_values))

        # Detect base pattern
        pattern_type = self._detect_radius_pattern_from_values(scale_values)

        unique_count = len(levels)
        confidence = min(40 + (total_instances // 8) + (unique_count * 4), 95)

        return {
            'confidence': confidence,
            'pattern': f'{unique_count} radius value{"s" if unique_count != 1 else ""} · {pattern_type}',
            'scale': scale_values,           # keep for backwards compat
            'levels': levels,                # ← new: ordered list with context
            'special_cases': special_cases,
            'total_instances': total_instances,
            'unique_values': unique_count,
            'evidence_trail': {
                'found': [
                    f'{total_instances} elements with border-radius',
                    f'{unique_count} unique radius values',
                    f'Most used: {levels[0]["display"]} ({levels[0]["count"]} uses)' if levels else 'None'
                ],
                'analyzed': [
                    f'Scale values: {scale_values}',
                    f'Special cases: {special_cases["pill"]} pills, {special_cases["circular"]} circles'
                ],
                'concluded': f'{pattern_type} — {", ".join(set(l["name"] for l in levels))}' if levels else 'No radius data'
            }
        }

    def _radius_semantic_name(self, px: float) -> str:
        """Map a border-radius pixel value to a human-readable style name."""
        if px == 0:
            return 'Sharp'
        elif px <= 4:
            return 'Subtle'
        elif px <= 8:
            return 'Medium'
        elif px <= 16:
            return 'Rounded'
        else:
            return 'Large'

    def _detect_radius_pattern_from_values(self, values: List[int]) -> str:
        """Classify the radius scale into a human-readable pattern string."""
        if not values:
            return 'No radius scale'
        if all(v % 4 == 0 for v in values[:5]):
            return '4px base system'
        if all(v % 2 == 0 for v in values[:5]):
            return '2px base system'
        return 'Custom scale'


async def demo_design_system_metrics():
    """
    Demo: Extract design system metrics from real sites
    """
    from patchright.async_api import async_playwright

    print("\n" + "="*70)
    print(" 🎨 DESIGN SYSTEM METRICS DEMO")
    print("="*70)

    test_sites = [
        ('https://stripe.com/docs', 'Stripe Docs'),
        ('https://tailwindcss.com', 'Tailwind CSS')
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for url, name in test_sites:
            print(f"\n{'='*70}")
            print(f" Analyzing: {name}")
            print(f" URL: {url}")
            print('='*70)

            page = await browser.new_page()
            page.set_default_timeout(60000)

            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)

                metrics = DesignSystemMetrics(page)

                # Extract all metrics
                spacing = await metrics.extract_spacing_scale()
                print(f"\n📏 Spacing: {spacing['pattern']} (base: {spacing['base_unit']}px)")
                print(f"   Scale: {spacing['scale']}")

                breakpoints = await metrics.extract_responsive_breakpoints()
                print(f"\n📱 Breakpoints: {breakpoints['pattern']}")
                print(f"   {breakpoints['breakpoints']}")

                shadows = await metrics.extract_shadow_system()
                print(f"\n☁️  Shadows: {shadows['pattern']}")

                z_index = await metrics.extract_z_index_stack()
                print(f"\n📚 Z-Index: {z_index['pattern']}")
                print(f"   {z_index['conflicts'][0]}")

                radius = await metrics.extract_border_radius_scale()
                print(f"\n🔘 Border Radius: {radius['pattern']}")
                print(f"   Scale: {radius['scale']}")

            except Exception as e:
                print(f"   ❌ Error: {str(e)[:100]}")

            await page.close()

        await browser.close()


if __name__ == '__main__':
    asyncio.run(demo_design_system_metrics())
