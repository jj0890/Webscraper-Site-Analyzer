"""
CSS Analytics Extractor — Raw CSS authoring pattern analysis.

Project Wallace-style CSS analytics + DTCG token extraction.
Captures how the CSS is *written*, not just what it *computes*.

Does NOT duplicate:
- css_efficiency.py (rule usage/coverage)
- css_specificity.py (selector specificity, methodology)
- css_tricks (custom property names from getComputedStyle)
- animations.py (@keyframes content, computed transitions)

Instead captures: stylesheet stats, at-rule breakdown, value uniqueness
ratios, modern CSS feature detection, custom property sophistication,
DTCG-classifiable design tokens, transition source patterns, pseudo-elements.
"""

import logging
import re
from typing import Dict, List, Any
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)

# Color value patterns for DTCG classification
_COLOR_RE = re.compile(
    r'^#[0-9a-fA-F]{3,8}$|^rgba?\(|^hsla?\(|^oklch\(|^oklab\(|^lch\(|^lab\('
    r'|^color\(|^color-mix\(|^light-dark\(',
)
_DIMENSION_RE = re.compile(r'^-?[\d.]+(?:px|rem|em|vw|vh|vmin|vmax|%)$')
_DURATION_RE = re.compile(r'^[\d.]+(?:ms|s)$')
_CUBIC_BEZIER_RE = re.compile(r'^cubic-bezier\(')
_SHADOW_RE = re.compile(r'^\d.*px.*(?:rgb|#|hsl|oklch)')
_FONT_WEIGHT_RE = re.compile(r'^(?:100|200|300|400|500|600|700|800|900|950|'
                              r'thin|hairline|extra-?light|ultra-?light|light|'
                              r'normal|medium|semi-?bold|demi-?bold|bold|'
                              r'extra-?bold|ultra-?bold|black|heavy)$', re.I)
_FONT_FAMILY_RE = re.compile(
    r'(?:sans-serif|serif|monospace|cursive|fantasy|system-ui|ui-\w+|'
    r'["\'][^"\']+["\'](?:\s*,\s*["\'][^"\']+["\'])*)',
    re.I,
)


class CSSAnalyticsExtractor(BaseExtractor):
    name = "css_analytics"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Analyzing CSS architecture...")

        try:
            raw = await ctx.page.evaluate('''() => {
                const stats = {
                    totalSheets: 0,
                    inaccessible: 0,
                    totalRules: 0,
                    totalDeclarations: 0,
                    maxDeclsPerRule: 0,
                    sourceLines: 0,
                    truncated: false,

                    atRules: {media:0, keyframes:0, fontFace:0, supports:0, layer:0, container:0, import:0},

                    properties: new Map(),      // propName → count
                    customProps: [],             // {name, value, scope, isDerived}
                    prefixedCount: 0,

                    colorValues: new Map(),      // normalized → count
                    fontSizeValues: new Map(),
                    spacingValues: new Map(),

                    modernFeatures: {
                        nesting: false, nestingDepthMax: 0,
                        cascadeLayers: false, containerQueries: false,
                        hasSelector: false, hasSelectorCount: 0,
                        isWhereSelectors: false,
                        colorMix: false, lightDark: false, subgrid: false,
                        viewTransitions: false, viewTransitionNames: [],
                        linearEasing: false,
                    },

                    transitionProps: new Map(),  // property → count
                    transitionDurations: {fast: 0, medium: 0, slow: 0},
                    transitionTotal: 0,

                    pseudoBefore: 0, pseudoAfter: 0, pseudoOther: 0,
                };

                let ruleCount = 0;
                const MAX_RULES = 10000;

                function normalizeColor(v) {
                    v = v.trim().toLowerCase();
                    if (v.startsWith('#')) {
                        if (v.length === 4) return '#' + v[1]+v[1] + v[2]+v[2] + v[3]+v[3];
                        return v.slice(0, 7);
                    }
                    return v;
                }

                function checkModernValue(val) {
                    if (val.includes('color-mix(')) stats.modernFeatures.colorMix = true;
                    if (val.includes('light-dark(')) stats.modernFeatures.lightDark = true;
                    if (val.includes('subgrid')) stats.modernFeatures.subgrid = true;
                    if (/\blinear\(/.test(val)) stats.modernFeatures.linearEasing = true;
                }

                function checkModernSelector(sel) {
                    if (sel.includes(':has(')) {
                        stats.modernFeatures.hasSelector = true;
                        stats.modernFeatures.hasSelectorCount++;
                    }
                    if (sel.includes(':is(') || sel.includes(':where('))
                        stats.modernFeatures.isWhereSelectors = true;
                    if (sel.includes('&')) stats.modernFeatures.nesting = true;
                    if (sel.includes('::view-transition') || sel.includes(':active-view-transition'))
                        stats.modernFeatures.viewTransitions = true;
                }

                function checkViewTransitionName(prop, val) {
                    if (prop === 'view-transition-name' && val && val !== 'none') {
                        if (stats.modernFeatures.viewTransitionNames.length < 30)
                            stats.modernFeatures.viewTransitionNames.push(val);
                        stats.modernFeatures.viewTransitions = true;
                    }
                }

                function parseDurationMs(val) {
                    val = val.trim();
                    if (val.endsWith('ms')) return parseFloat(val);
                    if (val.endsWith('s')) return parseFloat(val) * 1000;
                    return null;
                }

                function walkRules(rules, depth, parentSelector) {
                    if (!rules) return;
                    for (let i = 0; i < rules.length; i++) {
                        if (ruleCount >= MAX_RULES) { stats.truncated = true; return; }
                        const rule = rules[i];
                        ruleCount++;

                        const ctorName = rule.constructor?.name || '';

                        // CSSStyleRule
                        if (rule instanceof CSSStyleRule) {
                            const sel = rule.selectorText || '';
                            const style = rule.style;
                            const declCount = style.length;
                            stats.totalDeclarations += declCount;
                            if (declCount > stats.maxDeclsPerRule) stats.maxDeclsPerRule = declCount;

                            // Check selector for modern features + pseudo-elements
                            checkModernSelector(sel);
                            if (sel.includes('::before')) stats.pseudoBefore++;
                            else if (sel.includes('::after')) stats.pseudoAfter++;
                            else if (sel.match(/::(marker|placeholder|selection|scrollbar|backdrop|first-line|first-letter)/))
                                stats.pseudoOther++;

                            // Walk declarations
                            for (let j = 0; j < declCount; j++) {
                                const prop = style[j];
                                const val = style.getPropertyValue(prop).trim();

                                // Property tracking
                                stats.properties.set(prop, (stats.properties.get(prop) || 0) + 1);

                                if (prop.startsWith('--')) {
                                    const scope = parentSelector || sel;
                                    const isDerived = val.includes('var(--');
                                    stats.customProps.push({
                                        name: prop, value: val,
                                        scope: scope.includes(':root') ? ':root' : scope.slice(0, 60),
                                        isDerived
                                    });
                                } else if (prop.startsWith('-webkit-') || prop.startsWith('-moz-') ||
                                           prop.startsWith('-ms-') || prop.startsWith('-o-')) {
                                    stats.prefixedCount++;
                                }

                                // Value type tracking for uniqueness
                                checkModernValue(val);
                                checkViewTransitionName(prop, val);

                                if (['color','background-color','border-color','outline-color',
                                     'fill','stroke','text-decoration-color','accent-color',
                                     'caret-color','column-rule-color'].includes(prop)) {
                                    if (val && val !== 'inherit' && val !== 'initial' &&
                                        val !== 'currentcolor' && val !== 'transparent') {
                                        const norm = normalizeColor(val);
                                        stats.colorValues.set(norm, (stats.colorValues.get(norm) || 0) + 1);
                                    }
                                }

                                if (prop === 'font-size' && val) {
                                    stats.fontSizeValues.set(val, (stats.fontSizeValues.get(val) || 0) + 1);
                                }

                                if (['margin','margin-top','margin-right','margin-bottom','margin-left',
                                     'padding','padding-top','padding-right','padding-bottom','padding-left',
                                     'gap','row-gap','column-gap'].includes(prop) && val && val !== '0') {
                                    stats.spacingValues.set(val, (stats.spacingValues.get(val) || 0) + 1);
                                }

                                // Transition parsing
                                if (prop === 'transition' || prop === 'transition-property') {
                                    stats.transitionTotal++;
                                    const parts = val.split(',');
                                    parts.forEach(p => {
                                        const name = p.trim().split(/\s+/)[0];
                                        if (name && name !== 'none' && name !== 'all') {
                                            stats.transitionProps.set(name, (stats.transitionProps.get(name) || 0) + 1);
                                        }
                                    });
                                }
                                if (prop === 'transition-duration' || prop === 'transition') {
                                    const durMatch = val.match(/([\d.]+(?:ms|s))/g);
                                    if (durMatch) {
                                        durMatch.forEach(d => {
                                            const ms = parseDurationMs(d);
                                            if (ms !== null) {
                                                if (ms < 200) stats.transitionDurations.fast++;
                                                else if (ms <= 500) stats.transitionDurations.medium++;
                                                else stats.transitionDurations.slow++;
                                            }
                                        });
                                    }
                                }
                            }

                            // Check for nested rules (native CSS nesting)
                            if (rule.cssRules && rule.cssRules.length > 0) {
                                stats.modernFeatures.nesting = true;
                                const nestDepth = depth + 1;
                                if (nestDepth > stats.modernFeatures.nestingDepthMax)
                                    stats.modernFeatures.nestingDepthMax = nestDepth;
                                walkRules(rule.cssRules, nestDepth, sel);
                            }
                        }
                        // At-rules
                        else if (rule instanceof CSSMediaRule) {
                            stats.atRules.media++;
                            walkRules(rule.cssRules, depth, parentSelector);
                        }
                        else if (ctorName === 'CSSKeyframesRule' || rule.type === 7) {
                            stats.atRules.keyframes++;
                        }
                        else if (ctorName === 'CSSFontFaceRule' || rule.type === 5) {
                            stats.atRules.fontFace++;
                        }
                        else if (rule instanceof CSSSupportsRule) {
                            stats.atRules.supports++;
                            walkRules(rule.cssRules, depth, parentSelector);
                        }
                        else if (ctorName === 'CSSLayerBlockRule' || ctorName === 'CSSLayerStatementRule') {
                            stats.atRules.layer++;
                            stats.modernFeatures.cascadeLayers = true;
                            if (rule.cssRules) walkRules(rule.cssRules, depth, parentSelector);
                        }
                        else if (ctorName === 'CSSContainerRule') {
                            stats.atRules.container++;
                            stats.modernFeatures.containerQueries = true;
                            if (rule.cssRules) walkRules(rule.cssRules, depth, parentSelector);
                        }
                        else if (rule.type === 3) { // CSSImportRule
                            stats.atRules.import++;
                        }
                    }
                }

                // Walk all stylesheets
                for (const sheet of document.styleSheets) {
                    stats.totalSheets++;
                    try {
                        if (!sheet.cssRules) continue;
                        walkRules(sheet.cssRules, 0, '');
                    } catch (e) {
                        stats.inaccessible++;
                    }
                }

                stats.totalRules = ruleCount;

                // Approximate source lines from rule count + declarations
                stats.sourceLines = Math.round(ruleCount * 2.5 + stats.totalDeclarations * 1.2);

                // Convert Maps to plain objects for JSON transfer
                const propsObj = {};
                stats.properties.forEach((v, k) => { propsObj[k] = v; });

                const colorObj = {};
                stats.colorValues.forEach((v, k) => { colorObj[k] = v; });

                const fontSizeObj = {};
                stats.fontSizeValues.forEach((v, k) => { fontSizeObj[k] = v; });

                const spacingObj = {};
                stats.spacingValues.forEach((v, k) => { spacingObj[k] = v; });

                const transPropsObj = {};
                stats.transitionProps.forEach((v, k) => { transPropsObj[k] = v; });

                return {
                    totalSheets: stats.totalSheets,
                    inaccessible: stats.inaccessible,
                    totalRules: stats.totalRules,
                    totalDeclarations: stats.totalDeclarations,
                    maxDeclsPerRule: stats.maxDeclsPerRule,
                    sourceLines: stats.sourceLines,
                    truncated: stats.truncated,
                    atRules: stats.atRules,
                    properties: propsObj,
                    customProps: stats.customProps.slice(0, 500),
                    prefixedCount: stats.prefixedCount,
                    colorValues: colorObj,
                    fontSizeValues: fontSizeObj,
                    spacingValues: spacingObj,
                    modernFeatures: stats.modernFeatures,
                    transitionProps: transPropsObj,
                    transitionDurations: stats.transitionDurations,
                    transitionTotal: stats.transitionTotal,
                    pseudoBefore: stats.pseudoBefore,
                    pseudoAfter: stats.pseudoAfter,
                    pseudoOther: stats.pseudoOther,
                };
            }''')

            # If all sheets are cross-origin, try CDP fallback
            inaccessible = raw.get('inaccessible', 0)
            total_rules = raw.get('totalRules', 0)
            if inaccessible > 0 and total_rules == 0:
                logger.info("All %d stylesheets cross-origin — trying CDP fallback", inaccessible)
                cdp_data = await self._cdp_fallback(ctx)
                if cdp_data:
                    # Merge CDP data into raw
                    raw = self._merge_cdp_data(raw, cdp_data)

            return self._build_result(raw)

        except Exception as e:
            logger.warning("CSS analytics extraction failed: %s", str(e)[:200])
            return {
                'pattern': 'CSS analytics unavailable',
                'confidence': 0,
                'error': str(e)[:200],
            }

    async def _cdp_fallback(self, ctx: ExtractionContext) -> dict:
        """Fetch cross-origin stylesheet text via in-page fetch() calls."""
        try:
            # Get all inaccessible stylesheet URLs from the page
            sheet_urls = await ctx.page.evaluate('''() => {
                const urls = [];
                for (const sheet of document.styleSheets) {
                    try {
                        // Try to access rules — if it throws, it's cross-origin
                        const _ = sheet.cssRules;
                    } catch (e) {
                        if (sheet.href) urls.push(sheet.href);
                    }
                }
                return urls;
            }''')

            if not sheet_urls:
                logger.info("No cross-origin stylesheet URLs found")
                return None

            logger.info("Fetching %d cross-origin stylesheets via fetch()", len(sheet_urls))

            # Fetch each stylesheet using in-page fetch() (uses browser cache + cookies)
            all_css = await ctx.page.evaluate('''async (urls) => {
                const results = [];
                for (const url of urls) {
                    try {
                        const resp = await fetch(url, {mode: 'cors'});
                        if (resp.ok) {
                            const text = await resp.text();
                            if (text) results.push(text);
                        }
                    } catch (e) {
                        // CORS blocked — try no-cors (won't get body, skip)
                    }
                }
                return results;
            }''', sheet_urls)

            if not all_css:
                # Fallback: use Playwright request API (server-side, no CORS)
                logger.info("In-page fetch failed for all sheets, trying Playwright request API")
                all_css = []
                for url in sheet_urls[:20]:  # Cap at 20 sheets
                    try:
                        response = await ctx.page.context.request.get(url)
                        if response.ok:
                            text = await response.text()
                            if text and len(text) > 50:
                                all_css.append(text)
                    except Exception:
                        pass

            if not all_css:
                return None

            logger.info("Successfully fetched %d stylesheets (%d chars total)",
                       len(all_css), sum(len(c) for c in all_css))
            combined = '\n'.join(all_css)
            return self._parse_css_text(combined)

        except Exception as e:
            logger.warning("CSS fetch fallback failed: %s", str(e)[:100])
            return None

    def _parse_css_text(self, css: str) -> dict:
        """Lightweight regex-based CSS text parser for CDP fallback."""
        result = {
            'totalRules': 0,
            'totalDeclarations': 0,
            'maxDeclsPerRule': 0,
            'sourceLines': 0,  # Calculated after rule/decl counting
            'atRules': {'media': 0, 'keyframes': 0, 'fontFace': 0,
                        'supports': 0, 'layer': 0, 'container': 0, 'import': 0},
            'properties': {},
            'customProps': [],
            'prefixedCount': 0,
            'colorValues': {},
            'fontSizeValues': {},
            'spacingValues': {},
            'modernFeatures': {
                'nesting': False, 'nestingDepthMax': 0,
                'cascadeLayers': False, 'containerQueries': False,
                'hasSelector': False, 'isWhereSelectors': False,
                'colorMix': False, 'lightDark': False, 'subgrid': False,
            },
            'transitionProps': {},
            'transitionDurations': {'fast': 0, 'medium': 0, 'slow': 0},
            'transitionTotal': 0,
            'pseudoBefore': 0, 'pseudoAfter': 0, 'pseudoOther': 0,
        }

        # At-rule counts
        result['atRules']['media'] = len(re.findall(r'@media\b', css))
        result['atRules']['keyframes'] = len(re.findall(r'@keyframes\b', css))
        result['atRules']['fontFace'] = len(re.findall(r'@font-face\b', css))
        result['atRules']['supports'] = len(re.findall(r'@supports\b', css))
        result['atRules']['layer'] = len(re.findall(r'@layer\b', css))
        result['atRules']['container'] = len(re.findall(r'@container\b', css))
        result['atRules']['import'] = len(re.findall(r'@import\b', css))

        # Modern features
        if '&' in css and re.search(r'[{;]\s*&', css):
            result['modernFeatures']['nesting'] = True
        if '@layer' in css:
            result['modernFeatures']['cascadeLayers'] = True
        if '@container' in css:
            result['modernFeatures']['containerQueries'] = True
        if ':has(' in css:
            result['modernFeatures']['hasSelector'] = True
        if ':is(' in css or ':where(' in css:
            result['modernFeatures']['isWhereSelectors'] = True
        if 'color-mix(' in css:
            result['modernFeatures']['colorMix'] = True
        if 'light-dark(' in css:
            result['modernFeatures']['lightDark'] = True
        if 'subgrid' in css:
            result['modernFeatures']['subgrid'] = True

        # Custom properties
        for m in re.finditer(r'(--[\w-]+)\s*:\s*([^;}{]+)', css):
            name, value = m.group(1), m.group(2).strip()
            is_derived = 'var(--' in value
            # Determine scope: check if inside :root
            pre = css[:m.start()]
            scope = ':root' if ':root' in pre[max(0, pre.rfind('{')-30):] else 'element'
            result['customProps'].append({
                'name': name, 'value': value,
                'scope': scope, 'isDerived': is_derived,
            })
            result['properties'][name] = result['properties'].get(name, 0) + 1

        # Rule blocks (rough count)
        blocks = re.findall(r'\{([^{}]*)\}', css)
        result['totalRules'] = len(blocks)
        for block in blocks:
            decls = [d.strip() for d in block.split(';') if ':' in d]
            n = len(decls)
            result['totalDeclarations'] += n
            if n > result['maxDeclsPerRule']:
                result['maxDeclsPerRule'] = n

            for decl in decls:
                parts = decl.split(':', 1)
                if len(parts) != 2:
                    continue
                prop = parts[0].strip()
                val = parts[1].strip()

                if prop and not prop.startswith('--'):
                    result['properties'][prop] = result['properties'].get(prop, 0) + 1
                    if prop.startswith(('-webkit-', '-moz-', '-ms-', '-o-')):
                        result['prefixedCount'] += 1

                # Color values
                if prop in ('color', 'background-color', 'border-color', 'fill', 'stroke'):
                    if val and val not in ('inherit', 'initial', 'currentcolor', 'transparent'):
                        result['colorValues'][val.lower()] = result['colorValues'].get(val.lower(), 0) + 1

                # Font sizes
                if prop == 'font-size' and val:
                    result['fontSizeValues'][val] = result['fontSizeValues'].get(val, 0) + 1

                # Spacing
                if prop in ('margin', 'padding', 'gap', 'margin-top', 'margin-bottom',
                            'padding-top', 'padding-bottom', 'row-gap', 'column-gap'):
                    if val and val != '0':
                        result['spacingValues'][val] = result['spacingValues'].get(val, 0) + 1

                # Transitions
                if prop in ('transition', 'transition-property'):
                    result['transitionTotal'] += 1
                    # Parse transitioned property names from shorthand
                    parts = val.split(',')
                    for p in parts:
                        tokens = p.strip().split()
                        # First token that looks like a CSS property name (not a number/timing)
                        for tok in tokens:
                            if (tok and not tok[0].isdigit() and tok[0] != '.'
                                    and tok not in ('none', 'all', 'ease', 'ease-in',
                                                    'ease-out', 'ease-in-out', 'linear',
                                                    'step-start', 'step-end')
                                    and not tok.startswith('cubic-bezier')
                                    and 'ms' not in tok and not tok.endswith('s')):
                                result['transitionProps'][tok] = result['transitionProps'].get(tok, 0) + 1
                                break

                # Transition durations
                if prop in ('transition', 'transition-duration'):
                    for dur_match in re.findall(r'([\d.]+)(ms|s)', val):
                        ms = float(dur_match[0])
                        if dur_match[1] == 's':
                            ms *= 1000
                        if ms < 200:
                            result['transitionDurations']['fast'] += 1
                        elif ms <= 500:
                            result['transitionDurations']['medium'] += 1
                        else:
                            result['transitionDurations']['slow'] += 1

        # Pseudo-element counts from selectors in raw CSS
        result['pseudoBefore'] = len(re.findall(r'::before', css))
        result['pseudoAfter'] = len(re.findall(r'::after', css))
        result['pseudoOther'] = len(re.findall(
            r'::(?:marker|placeholder|selection|scrollbar|backdrop|first-line|first-letter)', css))

        # Source lines: approximate from rules + declarations (minified CSS has few newlines)
        result['sourceLines'] = round(
            result['totalRules'] * 2.5 + result['totalDeclarations'] * 1.2)

        # Trim custom props to 500
        result['customProps'] = result['customProps'][:500]

        return result

    @staticmethod
    def _merge_cdp_data(raw: dict, cdp: dict) -> dict:
        """Merge CDP fallback data into the original (empty) raw result."""
        # Keep the original sheet counts, replace everything else
        cdp['totalSheets'] = raw.get('totalSheets', 0)
        cdp['inaccessible'] = raw.get('inaccessible', 0)
        cdp['truncated'] = raw.get('truncated', False)
        return cdp

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_result(self, raw: Dict) -> Dict:
        total_rules = raw.get('totalRules', 0)
        total_decls = raw.get('totalDeclarations', 0)
        properties = raw.get('properties', {})
        custom_props = raw.get('customProps', [])
        color_values = raw.get('colorValues', {})
        font_size_values = raw.get('fontSizeValues', {})
        spacing_values = raw.get('spacingValues', {})
        modern = raw.get('modernFeatures', {})

        # Property stats
        unique_props = len(properties)
        custom_count = len(custom_props)
        prefixed_count = raw.get('prefixedCount', 0)
        standard_count = unique_props - sum(
            1 for p in properties if p.startswith('--') or p.startswith('-')
        )

        # Uniqueness ratios
        color_unique = self._uniqueness_ratio(color_values)
        font_unique = self._uniqueness_ratio(font_size_values)
        spacing_unique = self._uniqueness_ratio(spacing_values)
        ratios = [r for r in [color_unique, font_unique, spacing_unique] if r is not None]
        overall_unique = round(sum(ratios) / len(ratios), 3) if ratios else None

        # Custom property sophistication
        root_scoped = sum(1 for p in custom_props if p.get('scope') == ':root')
        element_scoped = custom_count - root_scoped
        derived_count = sum(1 for p in custom_props if p.get('isDerived'))
        derived_ratio = round(derived_count / custom_count, 3) if custom_count else 0.0

        # Declarations per rule
        avg_decls = round(total_decls / total_rules, 1) if total_rules else 0
        max_decls = raw.get('maxDeclsPerRule', 0)

        # DTCG tokens
        dtcg = self._extract_dtcg_tokens(custom_props)

        # Sophistication score + breakdown
        score, sophistication_breakdown = self._calculate_sophistication(
            custom_count, derived_count, element_scoped > 0,
            modern, overall_unique, avg_decls,
            raw.get('atRules', {}),
        )

        # Transition patterns
        trans_props = raw.get('transitionProps', {})
        trans_durations = raw.get('transitionDurations', {})

        # Build pattern string
        features = []
        if modern.get('nesting'):
            features.append('native nesting')
        if modern.get('cascadeLayers'):
            features.append('cascade layers')
        if modern.get('containerQueries'):
            features.append('container queries')
        if modern.get('hasSelector'):
            features.append(':has()')
        if modern.get('viewTransitions'):
            features.append('view transitions')
        if modern.get('colorMix'):
            features.append('color-mix()')
        if modern.get('subgrid'):
            features.append('subgrid')
        feature_str = ', '.join(features) if features else 'no modern features'

        pattern = (f"{total_rules} rules, {custom_count} custom properties, "
                   f"{feature_str} — sophistication {score}/100")

        return {
            'pattern': pattern,
            'confidence': self._calculate_confidence(
                total_rules, custom_count, modern, raw.get('inaccessible', 0)),
            'stylesheet_stats': {
                'total_stylesheets': raw.get('totalSheets', 0),
                'total_rules': total_rules,
                'total_declarations': total_decls,
                'source_lines_approx': raw.get('sourceLines', 0),
                'declarations_per_rule': {'avg': avg_decls, 'max': max_decls},
                'inaccessible_sheets': raw.get('inaccessible', 0),
                'truncated': raw.get('truncated', False),
            },
            'at_rules': raw.get('atRules', {}),
            'property_stats': {
                'total_unique_properties': unique_props,
                'custom_property_count': custom_count,
                'prefixed_property_count': prefixed_count,
                'standard_property_count': max(0, standard_count),
            },
            'uniqueness': {
                'color_unique_ratio': color_unique,
                'font_size_unique_ratio': font_unique,
                'spacing_unique_ratio': spacing_unique,
                'overall_uniqueness': overall_unique,
            },
            'modern_features': {
                'nesting': modern.get('nesting', False),
                'nesting_depth_max': modern.get('nestingDepthMax', 0),
                'cascade_layers': modern.get('cascadeLayers', False),
                'container_queries': modern.get('containerQueries', False),
                'has_selector': modern.get('hasSelector', False),
                'has_selector_count': modern.get('hasSelectorCount', 0),
                'is_where_selectors': modern.get('isWhereSelectors', False),
                'color_mix': modern.get('colorMix', False),
                'light_dark': modern.get('lightDark', False),
                'subgrid': modern.get('subgrid', False),
                'view_transitions': modern.get('viewTransitions', False),
                'view_transition_names': list(set(modern.get('viewTransitionNames', [])))[:20],
                'linear_easing': modern.get('linearEasing', False),
            },
            'custom_property_sophistication': {
                'total': custom_count,
                'root_scoped': root_scoped,
                'element_scoped': element_scoped,
                'derived_count': derived_count,
                'derived_ratio': derived_ratio,
            },
            'sophistication_score': score,
            'sophistication_breakdown': sophistication_breakdown,
            'dtcg_tokens': dtcg,
            'transition_patterns': {
                'total_with_transitions': raw.get('transitionTotal', 0),
                'transitioned_properties': trans_props,
                'duration_distribution': {
                    'fast_under_200ms': trans_durations.get('fast', 0),
                    'medium_200_500ms': trans_durations.get('medium', 0),
                    'slow_over_500ms': trans_durations.get('slow', 0),
                },
            },
            'pseudo_elements': {
                'before_count': raw.get('pseudoBefore', 0),
                'after_count': raw.get('pseudoAfter', 0),
                'other_count': raw.get('pseudoOther', 0),
            },
        }

    # ------------------------------------------------------------------
    # Sophistication scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_sophistication(
        custom_count: int, derived_count: int, has_scoped: bool,
        modern: Dict, uniqueness: float, avg_decls: float,
        at_rules: Dict,
    ):
        """Return (score: int, breakdown: list[dict]) where each entry shows
        what was earned and why — so the number is self-explanatory."""
        breakdown = []
        score = 0

        def _add(key: str, earned: int, cap: int, signal: str, note: str = ''):
            nonlocal score
            score += earned
            breakdown.append({
                'key': key,
                'earned': earned,
                'cap': cap,
                'signal': signal,
                'note': note,
            })

        # Custom property count (max 20)
        if custom_count >= 50:
            pts = 20
        elif custom_count >= 30:
            pts = 15
        elif custom_count >= 10:
            pts = 10
        else:
            pts = 0
        _add('custom_properties', pts, 20,
             f'{custom_count} CSS custom properties',
             '50+ → 20pts, 30+ → 15pts, 10+ → 10pts')

        # Derived vars (max 10)
        if derived_count >= 15:
            pts = 10
        elif derived_count >= 5:
            pts = 5
        else:
            pts = 0
        _add('derived_vars', pts, 10,
             f'{derived_count} derived vars (var() referencing another var)',
             '15+ → 10pts, 5+ → 5pts')

        # Scoped vars (max 5)
        pts = 5 if has_scoped else 0
        _add('scoped_vars', pts, 5,
             'element-scoped custom properties' if has_scoped else 'no element-scoped vars',
             'vars scoped to a selector, not just :root')

        # Native CSS nesting (max 10)
        if modern.get('nesting'):
            depth = modern.get('nestingDepthMax', 0)
            pts = 10 if depth >= 2 else 5
            note = f'max nesting depth: {depth}'
        else:
            pts = 0
            note = 'not detected'
        _add('css_nesting', pts, 10, 'native CSS nesting (&)', note)

        # Cascade layers (max 10)
        pts = 10 if modern.get('cascadeLayers') else 0
        _add('cascade_layers', pts, 10, '@layer detected' if pts else '@layer not used',
             'explicit cascade management (Baseline 2022)')

        # Container queries (max 8)
        pts = 8 if modern.get('containerQueries') else 0
        _add('container_queries', pts, 8, '@container detected' if pts else '@container not used',
             'component-level responsive design (Baseline 2023)')

        # Modern selectors (max 7)
        modern_sel = 0
        sel_found = []
        if modern.get('hasSelector'):
            modern_sel += 1
            sel_found.append(':has()')
        if modern.get('isWhereSelectors'):
            modern_sel += 1
            sel_found.append(':is()/:where()')
        pts = 7 if modern_sel >= 2 else (4 if modern_sel == 1 else 0)
        _add('modern_selectors', pts, 7,
             ', '.join(sel_found) if sel_found else ':has()/:is()/:where() not detected',
             'both :has() and :is()/:where() → 7pts, one → 4pts')

        # Modern color functions (max 5)
        color_fn = 0
        color_found = []
        if modern.get('colorMix'):
            color_fn += 1
            color_found.append('color-mix()')
        if modern.get('lightDark'):
            color_fn += 1
            color_found.append('light-dark()')
        pts = 5 if color_fn >= 2 else (3 if color_fn == 1 else 0)
        _add('modern_color', pts, 5,
             ', '.join(color_found) if color_found else 'color-mix()/light-dark() not used',
             'modern color functions (Baseline 2023-2024)')

        # Subgrid (max 5)
        pts = 5 if modern.get('subgrid') else 0
        _add('subgrid', pts, 5, 'grid-template: subgrid detected' if pts else 'subgrid not used',
             'Baseline 2023')

        # View Transition API (max 4) — Baseline 2025
        pts = 4 if modern.get('viewTransitions') else 0
        _add('view_transitions', pts, 4, '@view-transition / view-transition-name detected' if pts else 'view transitions not used',
             'Baseline 2025, very modern signal')

        # CSS linear() easing (max 3) — Baseline 2024
        pts = 3 if modern.get('linearEasing') else 0
        _add('linear_easing', pts, 3, 'linear() easing detected' if pts else 'linear() easing not used',
             'Baseline 2024')

        # Uniqueness ratio (max 10)
        if uniqueness is not None:
            if uniqueness > 0.5:
                pts = 10
            elif uniqueness > 0.3:
                pts = 5
            else:
                pts = 0
            note = (f'ratio {uniqueness:.2f} — unique values ÷ total declarations. '
                    '>0.5 → 10pts, >0.3 → 5pts. '
                    'High = many distinct values (thorough system). '
                    'Low = heavy repetition.')
        else:
            pts = 0
            note = 'insufficient data'
        _add('uniqueness_ratio', pts, 10,
             f'uniqueness ratio {uniqueness:.2f}' if uniqueness is not None else 'n/a',
             note)

        # Declarations per rule (max 5)
        if avg_decls > 0:
            if avg_decls < 5:
                pts = 5
            elif avg_decls < 8:
                pts = 2
            else:
                pts = 0
        else:
            pts = 0
        _add('declarations_per_rule', pts, 5,
             f'{avg_decls:.1f} avg declarations/rule',
             '<5 → 5pts, <8 → 2pts. Focused rules score higher.')

        # @supports (max 5)
        supports_count = at_rules.get('supports', 0)
        pts = 5 if supports_count > 0 else 0
        _add('at_supports', pts, 5,
             f'{supports_count} @supports block{"s" if supports_count != 1 else ""}' if supports_count else '@supports not used',
             'progressive enhancement signal')

        return min(100, score), breakdown

    @staticmethod
    def _calculate_confidence(
        total_rules: int, custom_count: int, modern: Dict, inaccessible: int
    ) -> int:
        """Formula-based confidence: graded by extraction richness."""
        confidence = 30  # Base: extraction attempted
        confidence += min(25, total_rules // 50)       # +1 per 50 rules, max 25
        confidence += min(15, custom_count // 10)       # +1 per 10 custom props, max 15
        modern_count = sum(1 for k, v in modern.items()
                          if isinstance(v, bool) and v)
        confidence += min(15, modern_count * 3)          # +3 per modern feature, max 15
        if inaccessible == 0:
            confidence += 10                             # Full access bonus
        return min(95, confidence)

    # ------------------------------------------------------------------
    # DTCG token extraction
    # ------------------------------------------------------------------

    def _extract_dtcg_tokens(self, custom_props: List[Dict]) -> Dict:
        tokens = {
            'color': [], 'dimension': [], 'duration': [],
            'cubicBezier': [], 'shadow': [], 'fontFamily': [],
            'fontWeight': [], 'total_token_count': 0,
        }

        seen = set()  # Deduplicate by name
        for prop in custom_props:
            name = prop.get('name', '')
            value = prop.get('value', '').strip()
            if not name or not value or name in seen:
                continue
            # Skip derived vars for classification (they reference other vars)
            if prop.get('isDerived'):
                continue
            seen.add(name)

            token_type = self._classify_dtcg_type(name, value)
            if token_type and token_type in tokens:
                tokens[token_type].append({
                    'name': name,
                    '$value': value,
                    '$type': token_type,
                    'scope': prop.get('scope', ':root'),
                })

        tokens['total_token_count'] = sum(
            len(v) for k, v in tokens.items() if isinstance(v, list)
        )
        return tokens

    @staticmethod
    def _classify_dtcg_type(name: str, value: str) -> str:
        """Classify a CSS custom property value into a DTCG token type."""
        v = value.strip().lower()

        if _COLOR_RE.match(v):
            return 'color'
        if _DURATION_RE.match(v):
            return 'duration'
        if _CUBIC_BEZIER_RE.match(v):
            return 'cubicBezier'
        if _FONT_WEIGHT_RE.match(v):
            return 'fontWeight'
        if _DIMENSION_RE.match(v):
            return 'dimension'
        if _SHADOW_RE.match(v):
            return 'shadow'
        # Font family: check name hint + value content
        name_lower = name.lower()
        if ('font' in name_lower and 'size' not in name_lower and
                'weight' not in name_lower):
            if _FONT_FAMILY_RE.search(value):
                return 'fontFamily'

        return ''  # Unclassifiable

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _uniqueness_ratio(value_map: Dict) -> float:
        """Compute unique values / total occurrences."""
        if not value_map:
            return None
        unique = len(value_map)
        total = sum(value_map.values())
        if total == 0:
            return None
        return round(unique / total, 3)
