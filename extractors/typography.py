"""
Typography Extractor — Font families, sizes, weights, type scale detection.

Extracts heading hierarchy, body typography, and optionally runs
intelligent type scale analysis via typography_intelligence module.
"""

import logging
from typing import Dict
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class TypographyExtractor(BaseExtractor):
    name = "typography"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Analyzing typography...")

        typo_data = await ctx.page.evaluate('''() => {
            const headings = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].map(tag => {
                const el = document.querySelector(tag);
                if (!el) return null;
                const styles = window.getComputedStyle(el);
                return {
                    tag,
                    fontFamily: styles.fontFamily,
                    fontSize: styles.fontSize,
                    fontWeight: styles.fontWeight,
                    lineHeight: styles.lineHeight,
                    letterSpacing: styles.letterSpacing
                };
            }).filter(Boolean);

            const body = window.getComputedStyle(document.body);
            const paragraph = document.querySelector('p');
            const pStyles = paragraph ? window.getComputedStyle(paragraph) : body;

            // Collect ALL unique fonts, sizes, and weights across the page
            const allFonts = new Set();
            const allSizes = new Set();
            const allWeights = new Set();

            // Track fonts per role bucket for classification
            const headingFontCounts = {};   // fonts seen on h1–h3
            const bodyFontCounts   = {};   // fonts seen on p, article, .body-like
            const uiFontCounts     = {};   // fonts seen on nav, button, label

            const normFont = ff => ff.split(',')[0].trim().replace(/['"]/g, '');

            // Heading bucket
            for (const el of document.querySelectorAll('h1, h2, h3, [class*="headline"], [class*="title"], [class*="display"]')) {
                const ff = window.getComputedStyle(el).fontFamily;
                if (!ff) continue;
                allFonts.add(ff);
                const key = normFont(ff);
                headingFontCounts[key] = (headingFontCounts[key] || 0) + 1;
            }
            // Body bucket
            for (const el of document.querySelectorAll('p, article, [class*="body"], [class*="content"], [class*="description"], [class*="summary"]')) {
                const ff = window.getComputedStyle(el).fontFamily;
                if (!ff) continue;
                allFonts.add(ff);
                const key = normFont(ff);
                bodyFontCounts[key] = (bodyFontCounts[key] || 0) + 1;
            }
            // UI bucket
            for (const el of document.querySelectorAll('nav, button, label, [class*="nav"], [class*="menu"], [class*="caption"]')) {
                const ff = window.getComputedStyle(el).fontFamily;
                if (!ff) continue;
                allFonts.add(ff);
                const key = normFont(ff);
                uiFontCounts[key] = (uiFontCounts[key] || 0) + 1;
            }

            // Sizes and weights from broader set
            for (const el of document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, a, button, li')) {
                const styles = window.getComputedStyle(el);
                if (styles.fontSize)  allSizes.add(styles.fontSize);
                if (styles.fontWeight) allWeights.add(styles.fontWeight);
            }

            // Classify: a font is "heading" if heading_count > body_count * 2
            //           "body" if body_count > heading_count * 2
            //           "ui" if mostly in ui bucket
            const allBucketFonts = new Set([
                ...Object.keys(headingFontCounts),
                ...Object.keys(bodyFontCounts),
                ...Object.keys(uiFontCounts)
            ]);
            const classifiedHeading = [], classifiedBody = [], classifiedUI = [];
            for (const font of allBucketFonts) {
                const h = headingFontCounts[font] || 0;
                const b = bodyFontCounts[font] || 0;
                const u = uiFontCounts[font] || 0;
                const total = h + b + u;
                if (total === 0) continue;
                const hRatio = h / total, bRatio = b / total, uRatio = u / total;
                if (hRatio >= 0.5 && h >= b)       classifiedHeading.push(font);
                else if (bRatio >= 0.5 && b >= h)   classifiedBody.push(font);
                else if (uRatio >= 0.5)              classifiedUI.push(font);
                else if (h >= b)                     classifiedHeading.push(font);
                else                                 classifiedBody.push(font);
            }

            return {
                headings,
                body: {
                    fontFamily: body.fontFamily,
                    fontSize: body.fontSize,
                    fontWeight: body.fontWeight,
                    lineHeight: body.lineHeight
                },
                paragraph: {
                    fontSize: pStyles.fontSize,
                    lineHeight: pStyles.lineHeight,
                    color: pStyles.color
                },
                all_fonts: Array.from(allFonts),
                all_sizes: Array.from(allSizes),
                all_weights: Array.from(allWeights),
                heading_fonts: classifiedHeading,
                body_fonts: classifiedBody,
                ui_fonts: classifiedUI,
            };
        }''')

        # Get stylesheet URLs for web font detection
        stylesheet_urls = await ctx.page.evaluate('''() => {
            const stylesheets = Array.from(document.styleSheets);
            return stylesheets.map(s => s.href).filter(Boolean);
        }''')

        # Intelligent typography analysis
        typography_intelligence = None
        try:
            from typography_intelligence import extract_typography_intelligence
            typography_intelligence = extract_typography_intelligence(typo_data, stylesheet_urls)
            logger.info(
                "Type scale: %s (%d%%)",
                typography_intelligence['type_scale']['pattern'],
                typography_intelligence['confidence']
            )
        except Exception as e:
            logger.warning("Typography intelligence failed: %s", str(e)[:100])

        # Backwards-compatible type scale
        type_scale = self._calculate_type_scale(typo_data)

        # Promote role-classified fonts into top-level details keys
        typo_data['heading_fonts'] = typo_data.get('heading_fonts') or []
        typo_data['body_fonts']    = typo_data.get('body_fonts') or []
        typo_data['ui_fonts']      = typo_data.get('ui_fonts') or []

        # Calculate typography confidence from actual evidence
        confidence = 40  # Base: extraction ran
        if typo_data.get('all_fonts'):
            confidence += 15
        if typo_data.get('headings'):
            confidence += 15
        if typo_data.get('body', {}).get('lineHeight') and typo_data['body']['lineHeight'] != 'normal':
            confidence += 10
        if typo_data.get('heading_fonts'):   # Bonus for successful role classification
            confidence += 10
        if typography_intelligence and typography_intelligence.get('type_scale', {}).get('ratio'):
            confidence += 5
        confidence = min(confidence, 95)

        result = {
            'pattern': self._determine_typo_pattern(typo_data),
            'confidence': confidence,
            'details': typo_data,
            'heading_fonts': typo_data['heading_fonts'],
            'body_fonts':    typo_data['body_fonts'],
            'ui_fonts':      typo_data['ui_fonts'],
            'type_scale': type_scale,
            'code_snippets': self._generate_typo_snippets(typo_data)
        }

        if typography_intelligence:
            result['intelligent_typography'] = typography_intelligence

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_typo_pattern(data: Dict) -> str:
        primary_font = data['body']['fontFamily'].split(',')[0].strip().replace('"', '')
        return primary_font

    @staticmethod
    def _calculate_type_scale(data: Dict):
        """Calculate modular type scale from heading sizes.

        Returns a dict with both the ratio and the raw size array so
        consumers can use either.  For backward compatibility, the
        'ratio' value is the same float previously returned bare.
        """
        all_sizes_raw = sorted(
            list(set(data.get('all_sizes', []))),
            key=lambda s: float(s.replace('px', '').replace('rem', '').replace('em', '') or '0'),
            reverse=True
        )

        if not data.get('headings') or len(data['headings']) < 2:
            return {
                'ratio': None,
                'sizes_px': [s for s in all_sizes_raw if s.endswith('px')][:12],
            }

        sizes = [float(h['fontSize'].replace('px', '')) for h in data['headings']]
        if len(sizes) < 2:
            return {
                'ratio': None,
                'sizes_px': [s for s in all_sizes_raw if s.endswith('px')][:12],
            }

        ratio = sizes[0] / sizes[1] if sizes[1] > 0 else 1

        return {
            'ratio': round(ratio, 2),
            'sizes_px': [s for s in all_sizes_raw if s.endswith('px')][:12],
            'heading_sizes_px': [f"{s}px" for s in sizes],
        }

    @staticmethod
    def _generate_typo_snippets(data: Dict) -> str:
        return (
            f"body {{\n"
            f"  font-family: {data['body']['fontFamily']};\n"
            f"  font-size: {data['body']['fontSize']};\n"
            f"  line-height: {data['body']['lineHeight']};\n"
            f"}}"
        )
