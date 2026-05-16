"""
Extractors Package — Focused metric extraction modules

Each extractor handles one domain (typography, colors, layout, etc.)
and follows the BaseExtractor interface. The DeepEvidenceEngine
orchestrates them via ExtractionContext.
"""

from extractors.base import BaseExtractor, ExtractionContext
from extractors.accessibility_tree import AccessibilityTreeExtractor
from extractors.typography import TypographyExtractor
from extractors.colors import ColorExtractor
from extractors.layout import LayoutExtractor
from extractors.animations import AnimationExtractor
from extractors.accessibility import AccessibilityExtractor
from extractors.performance import PerformanceExtractor
from extractors.seo import SEOExtractor
from extractors.security import SecurityExtractor
from extractors.dom_analysis import DOMAnalysisExtractor
from extractors.interactive import InteractiveExtractor
from extractors.state_capture import StateCaptureExtractor
from extractors.api_patterns import APIPatternExtractor
from extractors.site_architecture import SiteArchitectureExtractor
from extractors.article_content import ArticleContentExtractor
from extractors.network import NetworkExtractor
from extractors.enrichment import EnrichmentExtractor
from extractors.brand_personality import BrandPersonalityExtractor
from extractors.cdp_animation_extractor import CdpAnimationExtractor
from extractors.axe_contrast_extractor import AxeContrastExtractor
from extractors.css_efficiency import CSSEfficiencyExtractor
from extractors.css_specificity import CSSSpecificityExtractor
from extractors.css_analytics import CSSAnalyticsExtractor
from extractors.image_strategy import ImageStrategyExtractor

# Ordered list: independent extractors first, then state capture, then cross-dependency
ALL_EXTRACTORS = [
    # Batch 1a: Independent (no cross-dependencies)
    AccessibilityTreeExtractor,  # runs first — feeds downstream post-processors
    TypographyExtractor,
    LayoutExtractor,
    PerformanceExtractor,
    SEOExtractor,
    SecurityExtractor,
    DOMAnalysisExtractor,
    InteractiveExtractor,
    SiteArchitectureExtractor,
    ArticleContentExtractor,
    # Batch 1b: Physical state capture (hover/focus via Playwright)
    # Runs after InteractiveExtractor so buttons are cataloged.
    # Stores results in ctx.evidence['_mcp_state_capture'] for downstream use.
    StateCaptureExtractor,
    # Batch 1c: Color extraction (reads hover colors from state capture)
    ColorExtractor,
    # Batch 2: Network-dependent
    APIPatternExtractor,
    NetworkExtractor,
    # Batch 2b: CSS analysis (needs DOM + stylesheets loaded)
    CSSEfficiencyExtractor,    # CDP rule usage tracking
    CSSSpecificityExtractor,   # specificity + cascade health
    CSSAnalyticsExtractor,     # raw CSS authoring analytics + DTCG tokens
    ImageStrategyExtractor,    # aspect ratios, srcset, lazy loading, object-fit
    # Batch 3: Cross-dependency
    AccessibilityExtractor,   # needs colors
    AnimationExtractor,        # reads _mcp_state_capture, feeds motion_tokens
    BrandPersonalityExtractor, # needs colors, typography, animations, interactive, architecture
    EnrichmentExtractor,       # needs all evidence (must be last)
]

__all__ = [
    'BaseExtractor',
    'ExtractionContext',
    'ALL_EXTRACTORS',
    'CdpAnimationExtractor',
    'AxeContrastExtractor',
    'CSSEfficiencyExtractor',
    'CSSSpecificityExtractor',
    'CSSAnalyticsExtractor',
    'ImageStrategyExtractor',
]
