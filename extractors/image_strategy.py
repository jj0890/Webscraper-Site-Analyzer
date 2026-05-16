"""
Image Strategy Extractor

Extracts how a site handles images as a design system decision:
  - Aspect ratios per context (hero, grid, thumbnail, background)
  - object-fit / object-position treatment (crop vs letterbox)
  - Lazy loading strategy
  - Srcset breakpoints (reveals CDN/image service config)
  - Blur-up / LQIP placeholder patterns

Ecommerce, editorial, and media sites have very different image strategies.
This extractor makes that legible.
"""

import logging
from typing import Dict
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class ImageStrategyExtractor(BaseExtractor):
    name = "image_strategy"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        try:
            result = await ctx.page.evaluate("""() => {
                const imgs = Array.from(document.querySelectorAll('img'))
                    .filter(img => {
                        const r = img.getBoundingClientRect();
                        return r.width > 60 && r.height > 60;  // skip icons/avatars
                    });

                if (!imgs.length) return { images: [], summary: null };

                const gcd = (a, b) => b === 0 ? a : gcd(b, a % b);
                const aspectRatio = (w, h) => {
                    if (!w || !h) return null;
                    const pw = Math.round(w);
                    const ph = Math.round(h);
                    const d = gcd(pw, ph);
                    return `${pw/d}:${ph/d}`;
                };
                const roundAspect = (w, h) => {
                    if (!w || !h) return null;
                    return Math.round((w / h) * 100) / 100;
                };

                const data = imgs.slice(0, 60).map(img => {
                    const rect   = img.getBoundingClientRect();
                    const cs     = window.getComputedStyle(img);
                    const parent = img.parentElement;
                    const pcs    = parent ? window.getComputedStyle(parent) : null;

                    // Rendered aspect ratio
                    const rw = rect.width;
                    const rh = rect.height;
                    const renderedRatio = roundAspect(rw, rh);

                    // Natural aspect ratio
                    const nw = img.naturalWidth;
                    const nh = img.naturalHeight;
                    const naturalRatio = roundAspect(nw, nh);

                    // Srcset breakpoints
                    const srcset = img.srcset || img.getAttribute('srcset') || '';
                    const srcsetWidths = [...srcset.matchAll(/(\\d+)w/g)]
                        .map(m => parseInt(m[1]))
                        .sort((a, b) => a - b);

                    // Context signal from position in viewport
                    const viewportH = window.innerHeight;
                    const isAboveFold = rect.top < viewportH;
                    const isHero = isAboveFold && rw > window.innerWidth * 0.5 && rh > 200;
                    const isGrid = !isHero && rw < window.innerWidth * 0.5;

                    // Placeholder / blur-up patterns
                    const hasLqip = !!(
                        img.getAttribute('data-src') ||
                        img.getAttribute('data-lazy') ||
                        img.getAttribute('data-original') ||
                        cs.filter.includes('blur') ||
                        (pcs && pcs.backgroundImage !== 'none' && pcs.backgroundSize === 'cover')
                    );

                    return {
                        renderedW:       Math.round(rw),
                        renderedH:       Math.round(rh),
                        renderedRatio,
                        naturalW:        nw || null,
                        naturalH:        nh || null,
                        naturalRatio:    naturalRatio || renderedRatio,
                        objectFit:       cs.objectFit     || 'fill',
                        objectPosition:  cs.objectPosition || 'center',
                        loading:         img.loading       || 'auto',
                        decoding:        img.decoding      || 'auto',
                        hasSrcset:       srcsetWidths.length > 0,
                        srcsetWidths,
                        hasSizes:        !!img.sizes,
                        hasLqip,
                        alt:             img.alt ? 'present' : 'missing',
                        context:         isHero ? 'hero' : (isGrid ? 'grid' : 'inline'),
                        isAboveFold,
                    };
                });

                // ── Cluster by rendered aspect ratio ──────────────────────────
                const ratioGroups = {};
                data.forEach(img => {
                    const key = img.renderedRatio ? img.renderedRatio.toFixed(2) : 'unknown';
                    if (!ratioGroups[key]) ratioGroups[key] = { ratio: img.renderedRatio, count: 0, contexts: [] };
                    ratioGroups[key].count++;
                    if (!ratioGroups[key].contexts.includes(img.context))
                        ratioGroups[key].contexts.push(img.context);
                });
                const clusters = Object.values(ratioGroups)
                    .sort((a, b) => b.count - a.count)
                    .slice(0, 6)
                    .map(g => ({
                        ratio:    g.ratio,
                        label:    g.ratio < 0.8  ? 'portrait' :
                                  g.ratio < 1.15 ? 'square'   :
                                  g.ratio < 1.8  ? 'landscape' : 'widescreen',
                        count:    g.count,
                        contexts: g.contexts,
                    }));

                // ── Srcset analysis ───────────────────────────────────────────
                const allSrcsetWidths = data.flatMap(d => d.srcsetWidths);
                const uniqueSrcsetWidths = [...new Set(allSrcsetWidths)].sort((a, b) => a - b);
                const imgsWithSrcset = data.filter(d => d.hasSrcset).length;

                // ── Loading strategy ──────────────────────────────────────────
                const lazyCount  = data.filter(d => d.loading === 'lazy').length;
                const eagerCount = data.filter(d => d.loading === 'eager').length;
                const lqipCount  = data.filter(d => d.hasLqip).length;

                // ── object-fit breakdown ──────────────────────────────────────
                const fitCounts = {};
                data.forEach(d => { fitCounts[d.objectFit] = (fitCounts[d.objectFit] || 0) + 1; });
                const dominantFit = Object.entries(fitCounts)
                    .sort((a, b) => b[1] - a[1])[0]?.[0] || 'fill';

                // ── Hero image specifics ──────────────────────────────────────
                const heroImgs = data.filter(d => d.context === 'hero');
                const gridImgs = data.filter(d => d.context === 'grid');

                // ── Alt text audit ────────────────────────────────────────────
                const missingAlt = data.filter(d => d.alt === 'missing').length;

                return {
                    total_analyzed:    data.length,
                    ratio_clusters:    clusters,
                    loading_strategy: {
                        lazy:  lazyCount,
                        eager: eagerCount,
                        auto:  data.length - lazyCount - eagerCount,
                        lqip_count: lqipCount,
                        lazy_ratio: Math.round(lazyCount / data.length * 100),
                    },
                    srcset: {
                        images_with_srcset: imgsWithSrcset,
                        coverage_pct: Math.round(imgsWithSrcset / data.length * 100),
                        breakpoint_widths: uniqueSrcsetWidths,
                        image_service_hint: uniqueSrcsetWidths.length > 3
                            ? (uniqueSrcsetWidths.some(w => w === 1280 || w === 1920) ? 'CDN-optimized' : 'custom sizes')
                            : 'minimal',
                    },
                    object_fit: {
                        dominant: dominantFit,
                        breakdown: fitCounts,
                    },
                    context_breakdown: {
                        hero:   heroImgs.length,
                        grid:   gridImgs.length,
                        inline: data.length - heroImgs.length - gridImgs.length,
                    },
                    hero_aspect_ratio:  heroImgs[0]?.renderedRatio || null,
                    grid_aspect_ratio:  gridImgs.length
                        ? (gridImgs.reduce((s, d) => s + (d.renderedRatio || 1), 0) / gridImgs.length).toFixed(2) * 1
                        : null,
                    alt_text_issues: missingAlt,
                };
            }""")

            if not result or not result.get('total_analyzed'):
                return {
                    'pattern': 'No significant images detected',
                    'confidence': 30,
                }

            total = result['total_analyzed']
            clusters = result.get('ratio_clusters', [])
            srcset = result.get('srcset', {})
            loading = result.get('loading_strategy', {})
            fit = result.get('object_fit', {})

            # Build human-readable pattern summary
            dominant_cluster = clusters[0] if clusters else {}
            fit_desc = fit.get('dominant', 'fill')
            lazy_pct = loading.get('lazy_ratio', 0)
            srcset_pct = srcset.get('coverage_pct', 0)

            pattern_parts = []
            if dominant_cluster:
                pattern_parts.append(
                    f"Dominant image ratio {dominant_cluster.get('ratio')} "
                    f"({dominant_cluster.get('label')}, {dominant_cluster.get('count')} images)"
                )
            if fit_desc != 'fill':
                pattern_parts.append(f"object-fit: {fit_desc}")
            if lazy_pct > 50:
                pattern_parts.append(f"{lazy_pct}% lazy-loaded")
            if srcset_pct > 50:
                widths = srcset.get('breakpoint_widths', [])
                pattern_parts.append(
                    f"srcset on {srcset_pct}% of images "
                    f"({len(widths)} widths: {widths[:4]})"
                )

            # Confidence: more images analyzed + richer srcset/lazy data = higher
            confidence = min(95, 40 + min(total, 30) + (10 if srcset_pct > 50 else 0) + (5 if lazy_pct > 0 else 0))

            return {
                'pattern': '; '.join(pattern_parts) or f'{total} images analyzed',
                'confidence': confidence,
                'total_analyzed': total,
                'ratio_clusters': clusters,
                'loading_strategy': loading,
                'srcset': srcset,
                'object_fit': fit,
                'context_breakdown': result.get('context_breakdown', {}),
                'hero_aspect_ratio': result.get('hero_aspect_ratio'),
                'grid_aspect_ratio': result.get('grid_aspect_ratio'),
                'alt_text_issues': result.get('alt_text_issues', 0),
            }

        except Exception as e:
            logger.warning(f"ImageStrategyExtractor failed: {e}")
            return {
                'pattern': 'Image strategy extraction failed',
                'confidence': 0,
                'error': str(e),
            }
