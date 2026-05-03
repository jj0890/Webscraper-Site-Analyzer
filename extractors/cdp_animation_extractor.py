"""
CDP Animation Extractor

Captures JS-driven animations via the Chrome DevTools Protocol Animation domain.

The existing AnimationExtractor reads static CSS declarations — it can't see
transitions triggered by React/Vue class swaps, scroll-reveal libraries, or Web
Animation API calls because those never appear in the stylesheet.

This extractor attaches a CDP session, enables the Animation domain, then
triggers light interactions (hover, scroll) to provoke those transitions and
records every animation event as it fires at runtime.

Evidence key: 'cdp_animations'
"""

import asyncio
import logging
from typing import Dict, List

from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class CdpAnimationExtractor(BaseExtractor):
    name = "cdp_animations"

    _OBSERVE_SECS = 2.0    # observation window after interactions
    _MAX_EVENTS   = 100    # cap to avoid bloat on animation-heavy pages
    _HOVER_LIMIT  = 15     # max elements to hover

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("CDP: attaching Animation domain...")

        try:
            client = await ctx.page.context.new_cdp_session(ctx.page)
        except Exception as e:
            logger.warning("CDP Animation: session attach failed — %s: %s", type(e).__name__, e)
            return self._empty(f"CDP session unavailable: {e}")

        animations: List[Dict] = []
        seen: set = set()

        def _on_started(event: dict) -> None:
            if len(animations) >= self._MAX_EVENTS:
                return
            anim   = event.get("animation", {})
            source = anim.get("source", {})
            name   = anim.get("displayName") or source.get("animationName", "")
            entry  = {
                "name":            name,
                "type":            anim.get("type", "CSSTransition"),
                # type values: CSSAnimation | CSSTransition | WebAnimation
                "duration_ms":     source.get("duration", 0),
                "delay_ms":        source.get("delay", 0),
                "easing":          source.get("easing", "ease"),
                "iterations":      source.get("iterations", 1),
                "fill":            source.get("fill", "none"),
                "direction":       source.get("direction", "normal"),
            }
            key = f"{entry['type']}:{entry['name']}:{entry['duration_ms']}"
            if key not in seen:
                seen.add(key)
                animations.append(entry)

        try:
            await client.send("Animation.enable")
            client.on("Animation.animationStarted", _on_started)

            # Phase 1 — capture load / auto-play animations
            await asyncio.sleep(1.0)

            # Phase 2 — hover interactive elements to trigger hover transitions
            try:
                selectors = (
                    "button, a, [role='button'], input, select, "
                    "[class*='btn'], [class*='button'], nav a"
                )
                els = await ctx.page.query_selector_all(selectors)
                for el in els[: self._HOVER_LIMIT]:
                    try:
                        await el.hover(timeout=400)
                        await asyncio.sleep(0.12)
                    except Exception:
                        pass
            except Exception:
                pass

            # Phase 3 — light scroll to trigger scroll-reveal animations
            try:
                await ctx.page.evaluate(
                    "window.scrollTo({top: 500, behavior: 'smooth'})"
                )
                await asyncio.sleep(0.6)
                await ctx.page.evaluate(
                    "window.scrollTo({top: 0, behavior: 'smooth'})"
                )
                await asyncio.sleep(0.4)
            except Exception:
                pass

            await asyncio.sleep(self._OBSERVE_SECS)

        finally:
            try:
                await client.send("Animation.disable")
                await client.detach()
            except Exception:
                pass

        if not animations:
            return {
                "pattern": "No runtime animations observed",
                "confidence": 75,
                "details": {
                    "count": 0,
                    "animations": [],
                    "note": (
                        "Page may be static, or animations require deeper "
                        "interaction (auth, user gesture, video playback)."
                    ),
                },
            }

        transitions = [a for a in animations if a["type"] == "CSSTransition"]
        keyframes   = [a for a in animations if a["type"] == "CSSAnimation"]
        waapi       = [a for a in animations if a["type"] == "WebAnimation"]

        durations = sorted(
            set(a["duration_ms"] for a in animations if a["duration_ms"] > 0)
        )
        easings = list(
            set(a["easing"] for a in animations if a["easing"] and a["easing"] != "ease")
        )

        confidence = min(95, 50 + len(animations) * 2)

        return {
            "pattern": (
                f"{len(animations)} runtime animations captured — "
                f"{len(transitions)} transitions, {len(keyframes)} keyframes, "
                f"{len(waapi)} WAAPI"
            ),
            "confidence": confidence,
            "details": {
                "count":               len(animations),
                "animations":          animations,
                "css_transitions":     len(transitions),
                "css_keyframes":       len(keyframes),
                "web_animation_api":   len(waapi),
                "unique_durations_ms": durations,
                "unique_easings":      easings,
            },
        }

    @staticmethod
    def _empty(reason: str) -> Dict:
        return {
            "pattern": reason,
            "confidence": 0,
            "details": {"count": 0, "animations": []},
        }
