"""
Layout Extractor — Grid, Flexbox, and positioning pattern detection.

Counts layout containers across the page and captures representative
examples of grid and flex usage.
"""

import logging
from typing import Dict
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class LayoutExtractor(BaseExtractor):
    name = "layout"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Analyzing layout...")

        layout_data = await ctx.page.evaluate('''() => {
            const elements = document.querySelectorAll('*');
            const layouts = {
                grid_count: 0,
                flex_count: 0,
                absolute_count: 0,
                fixed_count: 0,
                sticky_count: 0,
                grid_examples: [],
                flex_examples: []
            };

            for (const el of elements) {
                const styles = window.getComputedStyle(el);
                const display = styles.display;
                const position = styles.position;
                // SVG elements have className as SVGAnimatedString — use baseVal fallback
                const safeClass = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const selector = el.id ? '#' + el.id : (safeClass ? '.' + safeClass.split(' ')[0] : el.tagName.toLowerCase());

                if (display === 'grid') {
                    layouts.grid_count++;
                    if (layouts.grid_examples.length < 3) {
                        layouts.grid_examples.push({
                            selector: selector,
                            columns: styles.gridTemplateColumns,
                            rows: styles.gridTemplateRows,
                            gap: styles.gap
                        });
                    }
                }

                if (display === 'flex') {
                    layouts.flex_count++;
                    if (layouts.flex_examples.length < 3) {
                        layouts.flex_examples.push({
                            selector: selector,
                            direction: styles.flexDirection,
                            wrap: styles.flexWrap,
                            justify: styles.justifyContent,
                            align: styles.alignItems
                        });
                    }
                }

                if (position === 'absolute') layouts.absolute_count++;
                if (position === 'fixed') layouts.fixed_count++;
                if (position === 'sticky') layouts.sticky_count++;
            }

            return layouts;
        }''')

        return {
            'pattern': self._determine_layout_pattern(layout_data),
            'confidence': self._calculate_layout_confidence(layout_data),
            'details': layout_data,
            'code_snippets': self._generate_layout_snippets(layout_data)
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_layout_pattern(data):
        if data['grid_count'] > data['flex_count']:
            return f"CSS Grid ({data['grid_count']} containers)"
        elif data['flex_count'] > 0:
            return f"Flexbox ({data['flex_count']} containers)"
        else:
            return "Traditional Layout"

    @staticmethod
    def _calculate_layout_confidence(data):
        grid = data.get('grid_count', 0)
        flex = data.get('flex_count', 0)
        # Graded formula: base 40, +4 per grid container (max 25),
        # +4 per flex container (max 25), +5 if any nesting detected
        confidence = 40
        confidence += min(25, grid * 4)
        confidence += min(25, flex * 4)
        if grid > 0 and flex > 0:
            confidence += 5  # Mixed layout = more sophisticated
        return min(95, confidence)

    @staticmethod
    def _generate_layout_snippets(data):
        if data['grid_examples']:
            ex = data['grid_examples'][0]
            return (
                f"{ex['selector']} {{\n"
                f"  display: grid;\n"
                f"  grid-template-columns: {ex['columns']};\n"
                f"  gap: {ex['gap']};\n"
                f"}}"
            )
        return None
