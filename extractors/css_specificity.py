"""
CSS Specificity Extractor — Cascade health and methodology detection.

Parses all accessible stylesheets to calculate specificity scores
using the standard (a, b, c) formula:
  a = ID selectors (#)
  b = class, attribute, pseudo-class selectors (., [], :)
  c = element, pseudo-element selectors (tag, ::)

Classifies selector methodology (BEM, utility-first, module, mixed)
and assesses cascade health (Healthy / Warning / Chaotic).
"""

import logging
import re
from typing import Dict, List, Tuple
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class CSSSpecificityExtractor(BaseExtractor):
    name = "css_specificity"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Analyzing CSS specificity...")

        try:
            raw = await ctx.page.evaluate('''() => {
                const selectors = [];
                let importantCount = 0;

                for (const sheet of document.styleSheets) {
                    try {
                        if (!sheet.cssRules) continue;
                        for (const rule of sheet.cssRules) {
                            if (rule.type !== 1) continue;  // CSSStyleRule
                            const sel = rule.selectorText;
                            if (!sel) continue;

                            // Split comma-separated selectors
                            sel.split(',').forEach(s => {
                                selectors.push(s.trim());
                            });

                            // Count !important
                            const text = rule.cssText || '';
                            const matches = text.match(/!important/g);
                            if (matches) importantCount += matches.length;
                        }
                    } catch (e) { /* cross-origin */ }
                }

                return { selectors: selectors.slice(0, 5000), importantCount };
            }''')

            selectors = raw.get('selectors', [])
            important_count = raw.get('importantCount', 0)

            if not selectors:
                return {
                    'pattern': 'No accessible CSS selectors found',
                    'confidence': 35,
                    'details': {}
                }

            # Calculate specificity for each selector
            specs = []
            for sel in selectors:
                spec = self._calculate_specificity(sel)
                specs.append((sel, spec))

            # Distribution
            low = sum(1 for _, s in specs if s[0] == 0 and s[1] == 0)  # (0,0,c)
            medium = sum(1 for _, s in specs if s[0] == 0 and s[1] > 0)  # (0,b,c)
            high = sum(1 for _, s in specs if s[0] > 0)  # (a,b,c) with IDs

            # Average specificity
            total = len(specs)
            avg_a = round(sum(s[0] for _, s in specs) / total, 2)
            avg_b = round(sum(s[1] for _, s in specs) / total, 2)
            avg_c = round(sum(s[2] for _, s in specs) / total, 2)

            # Max specificity
            max_spec = max(specs, key=lambda x: (x[1][0], x[1][1], x[1][2]))
            max_selector = max_spec[0][:120]
            max_values = list(max_spec[1])

            # Top !important selectors (sample)
            important_selectors = []
            for sel in selectors[:500]:
                if '!important' in sel.lower():
                    important_selectors.append(sel[:100])

            # Cascade health assessment
            id_pct = (high / total * 100) if total > 0 else 0
            imp_ratio = (important_count / total * 100) if total > 0 else 0

            if id_pct < 5 and imp_ratio < 2:
                cascade_health = 'Healthy'
                health_detail = 'Low specificity, minimal !important — clean cascade'
            elif id_pct < 15 and imp_ratio < 8:
                cascade_health = 'Warning'
                health_detail = 'Some ID selectors or !important usage — review needed'
            else:
                cascade_health = 'Chaotic'
                health_detail = 'Heavy ID selectors or !important — specificity wars likely'

            # Methodology detection
            methodology = self._detect_methodology(selectors[:2000])

            return {
                'pattern': f'Specificity: {cascade_health} — avg ({avg_a},{avg_b},{avg_c}), {total} selectors',
                'confidence': min(95,
                    30
                    + min(30, total // 20)            # +1 per 20 selectors, max 30
                    + (15 if methodology else 0)       # Methodology detected
                    + min(10, len([x for x in [low, medium, high] if x > 0]) * 5)
                    + (10 if cascade_health == 'Healthy' else 0)
                ),
                'average_specificity': [avg_a, avg_b, avg_c],
                'max_specificity': max_values,
                'max_specificity_selector': max_selector,
                'specificity_distribution': {
                    'low_element_only': low,
                    'medium_class_based': medium,
                    'high_id_based': high,
                },
                'important_count': important_count,
                'cascade_health': cascade_health,
                'cascade_health_detail': health_detail,
                'methodology': methodology,
                'total_selectors': total,
            }

        except Exception as e:
            logger.warning("CSS specificity analysis failed: %s", str(e)[:100])
            return {
                'pattern': 'CSS specificity analysis unavailable',
                'confidence': 0,
                'error': str(e)[:200]
            }

    # ------------------------------------------------------------------
    # Specificity calculator (a, b, c)
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_specificity(selector: str) -> Tuple[int, int, int]:
        """
        Calculate CSS specificity as (a, b, c) tuple.
        a = ID selectors
        b = class, attribute, pseudo-class selectors
        c = element, pseudo-element selectors
        """
        # Remove :not() content but keep inner selectors
        sel = re.sub(r':not\(([^)]*)\)', r' \1', selector)

        # Remove everything inside [] for counting
        attr_matches = re.findall(r'\[.*?\]', sel)
        sel_clean = re.sub(r'\[.*?\]', '', sel)

        a = len(re.findall(r'#[a-zA-Z_][\w-]*', sel_clean))
        b = (
            len(re.findall(r'\.[a-zA-Z_][\w-]*', sel_clean)) +  # classes
            len(attr_matches) +  # attribute selectors
            len(re.findall(r':(hover|focus|active|visited|first-child|last-child|nth-child|'
                          r'nth-of-type|first-of-type|last-of-type|empty|checked|disabled|'
                          r'enabled|required|optional|read-only|read-write|placeholder-shown|'
                          r'focus-within|focus-visible|is|where|has|any-link|link)',
                          sel_clean))
        )
        c = (
            len(re.findall(r'(?:^|[\s>+~])([a-zA-Z][a-zA-Z0-9]*)', sel_clean)) +  # elements
            len(re.findall(r'::(before|after|first-line|first-letter|placeholder|selection|'
                          r'marker|backdrop|scrollbar)', sel_clean))
        )

        return (a, b, c)

    # ------------------------------------------------------------------
    # Methodology detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_methodology(selectors: List[str]) -> str:
        """
        Classify CSS methodology based on selector patterns.
        Returns: 'BEM', 'Utility-first', 'Module', 'Semantic', or 'Mixed'
        """
        total = len(selectors)
        if total == 0:
            return 'Unknown'

        # BEM indicators: block__element--modifier
        bem_count = sum(1 for s in selectors if re.search(r'__\w+|--\w+', s))

        # Utility-first indicators: single-purpose classes like .text-lg, .flex, .p-4
        utility_patterns = re.compile(
            r'\.(text-|font-|bg-|p-|px-|py-|m-|mx-|my-|flex|grid|block|inline|hidden|'
            r'w-|h-|max-|min-|rounded|border|shadow|opacity|z-|gap-|space-|items-|'
            r'justify-|overflow-|relative|absolute|fixed|sticky)',
            re.IGNORECASE
        )
        utility_count = sum(1 for s in selectors if utility_patterns.search(s))

        # Module indicators: [class*="module"], [data-v-], auto-generated hashes
        module_count = sum(1 for s in selectors if re.search(r'_[a-f0-9]{5,8}|__\w+_\w{5}', s))

        bem_pct = bem_count / total * 100
        utility_pct = utility_count / total * 100
        module_pct = module_count / total * 100

        if utility_pct > 40:
            return 'Utility-first'
        if bem_pct > 20:
            return 'BEM'
        if module_pct > 15:
            return 'Module'
        if bem_pct < 5 and utility_pct < 10 and module_pct < 5:
            return 'Semantic'
        return 'Mixed'
