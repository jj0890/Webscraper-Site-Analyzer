"""
CSS Efficiency Extractor — Unused CSS detection and rule analysis.

Uses CDP CSS.startRuleUsageTracking / CSS.stopRuleUsageTracking
(the same API Chrome DevTools Coverage tab uses) to measure what
percentage of CSS rules are actually applied to the DOM.
Also audits !important usage and stylesheet count.
"""

import logging
from typing import Dict
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class CSSEfficiencyExtractor(BaseExtractor):
    name = "css_efficiency"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Analyzing CSS efficiency...")

        try:
            result = await self._analyze_via_cdp(ctx)
        except Exception as e:
            logger.warning("CDP CSS tracking failed (%s), falling back to heuristic", str(e)[:80])
            result = await self._analyze_via_heuristic(ctx)

        return result

    # ------------------------------------------------------------------
    # Primary: CDP Rule Usage Tracking (accurate)
    # ------------------------------------------------------------------

    async def _analyze_via_cdp(self, ctx: ExtractionContext) -> Dict:
        """Use Chrome DevTools Protocol for precise CSS coverage."""
        cdp = await ctx.page.context.new_cdp_session(ctx.page)

        try:
            # Enable CSS domain and start tracking
            await cdp.send('DOM.enable')
            await cdp.send('CSS.enable')
            await cdp.send('CSS.startRuleUsageTracking')

            # Trigger interactions to activate dynamic CSS rules
            # (hover states, scrolled states, focus states)
            try:
                await ctx.page.evaluate('''() => {
                    // Scroll to trigger scroll-dependent styles
                    window.scrollTo(0, document.body.scrollHeight / 3);
                    window.scrollTo(0, 0);
                }''')
            except Exception:
                pass

            # Stop tracking and collect results
            coverage_result = await cdp.send('CSS.stopRuleUsageTracking')
            rules = coverage_result.get('ruleUsage', [])

            used = sum(1 for r in rules if r.get('used', False))
            total = len(rules)
            unused = total - used
            used_pct = round((used / total * 100) if total > 0 else 100)
            unused_pct = 100 - used_pct

            # Get stylesheet info
            stylesheets = await cdp.send('CSS.getAllStyleSheetHeaders', {})
            sheets = stylesheets.get('headers', [])
            external_sheets = [s for s in sheets if s.get('sourceURL') and not s.get('isInline')]
            inline_sheets = [s for s in sheets if s.get('isInline')]

            # Count !important declarations
            important_count = await self._count_important(ctx)

            # Plain-English summary
            if unused_pct <= 10:
                efficiency_label = "Very efficient"
            elif unused_pct <= 25:
                efficiency_label = "Efficient"
            elif unused_pct <= 50:
                efficiency_label = "Some waste"
            elif unused_pct <= 75:
                efficiency_label = "Lots of unused CSS"
            else:
                efficiency_label = "Mostly unused CSS"

            return {
                'pattern': f'{efficiency_label} — {used_pct}% of CSS rules are used',
                'confidence': min(95, 40 + 25 + min(20, total // 50)),  # CDP: base 40 + method 25 + rule richness
                'used_percentage': used_pct,
                'unused_percentage': unused_pct,
                'total_rules': total,
                'used_rules': used,
                'unused_rules': unused,
                'stylesheet_count': len(external_sheets),
                'inline_stylesheet_count': len(inline_sheets),
                'important_count': important_count,
                'efficiency_label': efficiency_label,
                'method': 'cdp_coverage',
            }

        finally:
            try:
                await cdp.detach()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Fallback: Heuristic selector matching
    # ------------------------------------------------------------------

    async def _analyze_via_heuristic(self, ctx: ExtractionContext) -> Dict:
        """Fallback: cross-reference CSS selectors against live DOM."""
        try:
            result = await ctx.page.evaluate('''() => {
                let totalRules = 0;
                let usedRules = 0;
                let importantCount = 0;
                let sheetCount = 0;

                for (const sheet of document.styleSheets) {
                    try {
                        if (!sheet.cssRules) continue;
                        sheetCount++;
                        for (const rule of sheet.cssRules) {
                            if (rule.type !== 1) continue; // CSSStyleRule only
                            totalRules++;

                            // Check if selector matches any element
                            try {
                                if (document.querySelector(rule.selectorText)) {
                                    usedRules++;
                                }
                            } catch (e) {
                                // Invalid selector (e.g., pseudo-elements) — count as used
                                usedRules++;
                            }

                            // Count !important
                            const cssText = rule.cssText || '';
                            const matches = cssText.match(/!important/g);
                            if (matches) importantCount += matches.length;
                        }
                    } catch (e) {
                        // Cross-origin stylesheets throw SecurityError
                    }
                }

                const usedPct = totalRules > 0 ? Math.round(usedRules / totalRules * 100) : 100;
                return {
                    total_rules: totalRules,
                    used_rules: usedRules,
                    unused_rules: totalRules - usedRules,
                    used_pct: usedPct,
                    sheet_count: sheetCount,
                    important_count: importantCount
                };
            }''')

            used_pct = result.get('used_pct', 100)
            unused_pct = 100 - used_pct

            if unused_pct <= 10:
                efficiency_label = "Very efficient"
            elif unused_pct <= 25:
                efficiency_label = "Efficient"
            elif unused_pct <= 50:
                efficiency_label = "Some waste"
            elif unused_pct <= 75:
                efficiency_label = "Lots of unused CSS"
            else:
                efficiency_label = "Mostly unused CSS"

            return {
                'pattern': f'{efficiency_label} — {used_pct}% of CSS rules are used',
                'confidence': min(95, 40 + 10 + min(20, result.get('total_rules', 0) // 50)),  # Heuristic: base 40 + method 10 + rules
                'used_percentage': used_pct,
                'unused_percentage': unused_pct,
                'total_rules': result.get('total_rules', 0),
                'used_rules': result.get('used_rules', 0),
                'unused_rules': result.get('unused_rules', 0),
                'stylesheet_count': result.get('sheet_count', 0),
                'inline_stylesheet_count': 0,
                'important_count': result.get('important_count', 0),
                'efficiency_label': efficiency_label,
                'method': 'heuristic_selector_match',
            }

        except Exception as e:
            logger.warning("CSS heuristic analysis failed: %s", str(e)[:100])
            return {
                'pattern': 'CSS efficiency analysis unavailable',
                'confidence': 0,
                'error': str(e)[:200]
            }

    # ------------------------------------------------------------------
    # !important counter (shared helper)
    # ------------------------------------------------------------------

    @staticmethod
    async def _count_important(ctx: ExtractionContext) -> int:
        """Count !important declarations across all accessible stylesheets."""
        try:
            return await ctx.page.evaluate('''() => {
                let count = 0;
                for (const sheet of document.styleSheets) {
                    try {
                        if (!sheet.cssRules) continue;
                        for (const rule of sheet.cssRules) {
                            if (rule.type !== 1) continue;
                            const text = rule.cssText || '';
                            const matches = text.match(/!important/g);
                            if (matches) count += matches.length;
                        }
                    } catch (e) { /* cross-origin */ }
                }
                return count;
            }''')
        except Exception:
            return 0
