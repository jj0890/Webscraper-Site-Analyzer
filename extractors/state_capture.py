"""
State Capture Extractor — Physical hover/focus state detection via Playwright.

Runs after InteractiveExtractor (so buttons/links are cataloged) and before
ColorExtractor (so hover colors are available for palette enrichment).

Stores results in ctx.evidence['_mcp_state_capture'] as a shared resource
consumed by:
  - ColorExtractor (hover color roles)
  - AnimationExtractor (interaction_states evidence key)
  - InteractiveExtractor (button hover/focus state deltas)

Does NOT produce its own evidence key — it's a cross-cutting concern that
enriches other extractors' outputs.
"""

import logging
from typing import Dict
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class StateCaptureExtractor(BaseExtractor):
    name = "_state_capture"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        """Run physical hover/focus capture and store for downstream extractors."""
        try:
            from extractors.interaction_state_capture import capture_interaction_states
            result = await capture_interaction_states(ctx.page)

            # Store in evidence for downstream consumers
            ctx.evidence['_mcp_state_capture'] = result

            # Also immediately enrich interactive_elements if already extracted
            interactive = ctx.evidence.get('interactive_elements')
            if interactive and interactive.get('button_styles'):
                from extractors.interactive import InteractiveExtractor
                interactive['button_styles'] = InteractiveExtractor._enrich_with_hover_states(
                    interactive['button_styles'], result
                )
                logger.info("Enriched interactive_elements button styles with hover states")

            hover_count = len(result.get('hover_deltas', []))
            focus_count = len(result.get('focus_deltas', []))
            pattern_count = len(result.get('patterns', []))

            return {
                'pattern': f'{result.get("states_detected", 0)} state changes detected ({hover_count} hover, {focus_count} focus)',
                'confidence': min(95,
                    40
                    + min(30, result.get('states_detected', 0) * 3)
                    + min(15, result.get('elements_tested', 0) // 5)
                    + min(10, len(result.get('patterns', [])) * 5)
                ),
                'elements_tested': result.get('elements_tested', 0),
                'states_detected': result.get('states_detected', 0),
                'hover_count': hover_count,
                'focus_count': focus_count,
                'pattern_count': pattern_count,
                'patterns': result.get('patterns', []),
                'hover_deltas_sample': result.get('hover_deltas', [])[:5],
                'focus_deltas_sample': result.get('focus_deltas', [])[:3],
            }

        except Exception as e:
            logger.warning(f"State capture failed: {str(e)[:100]}")
            ctx.evidence['_mcp_state_capture'] = {
                'hover_deltas': [], 'focus_deltas': [],
                'hover_colors': {}, 'patterns': [],
                'elements_tested': 0, 'states_detected': 0,
            }
            return {
                'pattern': 'State capture unavailable',
                'confidence': 0,
                'error': str(e)[:200],
            }
