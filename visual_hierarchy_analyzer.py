"""
Visual Hierarchy Analyzer

Detects:
1. Hero section (CV-based visual salience + fallback heuristic)
2. Primary CTA (most prominent button)
3. Navigation hierarchy (header → nav → sections)
4. Content groupings (cards, grids, lists)
5. Reading order (F-pattern, Z-pattern detection)
6. Visual weight scoring (computer vision + heuristic fallback)

Philosophy: "What does the eye see first?"

CV Enhancement: Uses OpenCV visual salience detector for robust hero detection
"""

from typing import Dict, List, Tuple

# Import CV detector (graceful fallback if not available)
try:
    from visual_salience_detector import VisualSalienceDetector
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False
    print("⚠️  OpenCV not available - using heuristic hero detection")


class VisualHierarchyAnalyzer:
    """
    Analyze visual hierarchy of a web page
    """

    def __init__(self):
        self.hierarchy = {}

    async def analyze(self, page) -> Dict:
        """
        Comprehensive visual hierarchy analysis

        Returns:
            {
                'hero_section': {...},
                'primary_cta': {...},
                'navigation': {...},
                'content_groups': [...],
                'reading_pattern': 'F-pattern' | 'Z-pattern' | 'Grid',
                'visual_weight_map': [...],
                'attention_flow': [...]
            }
        """
        print("   👁️  Analyzing visual hierarchy...")

        # Extract visual hierarchy data
        hierarchy_data = await page.evaluate('''() => {
            const elements = [...document.querySelectorAll('*')];
            const viewport = {
                width: window.innerWidth,
                height: window.innerHeight
            };

            // ── Leaf content detection: what humans actually SEE ──
            const CONTENT_TAGS = new Set([
                'img', 'video', 'canvas', 'svg', 'picture', 'iframe',
                'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'button', 'input', 'select', 'textarea',
                'figcaption', 'label', 'blockquote', 'code', 'pre',
                'li', 'td', 'th',
            ]);
            const CONTAINER_TAGS = new Set([
                'html', 'body', 'div', 'section', 'article', 'main', 'aside', 'header',
                'footer', 'nav', 'ul', 'ol', 'form', 'fieldset', 'table',
                'thead', 'tbody', 'tr', 'dl', 'figure', 'details',
            ]);

            // Get page background for contrast calculations
            const bodyStyles = window.getComputedStyle(document.body);
            const pageBg = bodyStyles.backgroundColor || 'rgb(255,255,255)';

            function parseRGB(str) {
                const m = (str || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                return m ? { r: +m[1], g: +m[2], b: +m[3] } : { r: 255, g: 255, b: 255 };
            }
            function relativeLuminance(c) {
                const sR = c.r / 255, sG = c.g / 255, sB = c.b / 255;
                const R = sR <= 0.03928 ? sR / 12.92 : Math.pow((sR + 0.055) / 1.055, 2.4);
                const G = sG <= 0.03928 ? sG / 12.92 : Math.pow((sG + 0.055) / 1.055, 2.4);
                const B = sB <= 0.03928 ? sB / 12.92 : Math.pow((sB + 0.055) / 1.055, 2.4);
                return 0.2126 * R + 0.7152 * G + 0.0722 * B;
            }
            function saturation(c) {
                const max = Math.max(c.r, c.g, c.b) / 255;
                const min = Math.min(c.r, c.g, c.b) / 255;
                return max === 0 ? 0 : (max - min) / max;
            }
            const pageBgLum = relativeLuminance(parseRGB(pageBg));

            // Calculate visual weight for each element
            const weightedElements = elements.map(el => {
                const rect = el.getBoundingClientRect();
                const styles = window.getComputedStyle(el);

                // Skip invisible elements
                if (rect.width === 0 || rect.height === 0 || styles.display === 'none' || styles.visibility === 'hidden') {
                    return null;
                }

                const aboveFold = rect.top >= 0 && rect.top < viewport.height;
                const zIndex = parseInt(styles.zIndex) || 0;
                const fontSize = parseFloat(styles.fontSize) || 0;
                const fontWeight = parseInt(styles.fontWeight) || 400;
                const color = styles.color;
                const bgColor = styles.backgroundColor;
                const role = el.getAttribute('role');
                const ariaLabel = el.getAttribute('aria-label');
                const tagName = el.tagName.toLowerCase();

                // ── Leaf vs Container classification ──
                const trimmedText = (el.textContent || '').trim();
                const isLeafContent = CONTENT_TAGS.has(tagName)
                    || (tagName === 'a' && trimmedText.length > 0 && trimmedText.length < 100);
                const isContainer = CONTAINER_TAGS.has(tagName);
                const textLen = (el.textContent || '').length;
                const isLikelyWrapper = isContainer && textLen > 200;

                // Content bonus/penalty: leaf content ranks higher than containers
                const contentBonus = isLeafContent ? 40 : (isLikelyWrapper ? -60 : 0);

                // ── Color contrast against page background ──
                const elBg = parseRGB(bgColor);
                const elBgLum = relativeLuminance(elBg);
                const lumDelta = Math.abs(elBgLum - pageBgLum);
                const bgSat = saturation(elBg);
                const contrastScore = (lumDelta * 40) + (bgSat > 0.5 ? 30 : 0);

                // ── Bold text bonus ──
                const boldBonus = fontWeight >= 700 ? 20 : 0;

                // Nav/header structural elements: cap sizeScore
                const isNavStructural = tagName === 'nav' || role === 'navigation' || role === 'banner'
                    || (tagName === 'header' && rect.width > viewport.width * 0.8);
                const isViewportContainer = rect.width >= viewport.width * 0.85
                    && rect.height >= viewport.height * 0.85
                    && CONTAINER_TAGS.has(tagName);
                const size = rect.width * rect.height;
                const sizeScore = (isNavStructural || isViewportContainer)
                    ? Math.min(size * 0.0001, 5.0) : size * 0.0001;

                const foldBonus = aboveFold ? 50 : 0;
                const fontScore = fontSize * 2;  // slightly reduced — contrast matters more
                const zBonus = zIndex > 0 ? Math.min(zIndex, 30) : 0;

                // Semantic importance bonus (reduced — let contrast/content do the work)
                let semanticBonus = 0;
                if (tagName === 'nav' || role === 'navigation' || role === 'banner') {
                    semanticBonus = 100;
                } else if (tagName === 'header' && rect.top < viewport.height * 0.2) {
                    semanticBonus = 120;
                } else if (tagName === 'main' || role === 'main') {
                    semanticBonus = 80;
                } else if (tagName.match(/^h[1-3]$/)) {
                    semanticBonus = 100;
                } else if (tagName === 'footer' || role === 'contentinfo') {
                    semanticBonus = 30;
                }

                const weight = sizeScore + foldBonus + fontScore + boldBonus + contrastScore + contentBonus + zBonus + semanticBonus;

                const safeClassName = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');

                return {
                    tag: tagName,
                    text: el.textContent?.substring(0, 100) || '',
                    alt: el.getAttribute('alt') || '',
                    className: safeClassName,
                    id: el.id,
                    weight: weight,
                    isNavStructural: isNavStructural,
                    isLeafContent: isLeafContent,
                    rect: {
                        top: rect.top,
                        left: rect.left,
                        width: rect.width,
                        height: rect.height
                    },
                    styles: {
                        fontSize: fontSize,
                        color: color,
                        backgroundColor: bgColor,
                        fontWeight: styles.fontWeight,
                        zIndex: zIndex
                    },
                    aboveFold: aboveFold
                };
            }).filter(el => el !== null);

            // ── Non-Maximum Suppression (NMS) ──
            // Removes nested elements that share nearly identical bounding boxes.
            // Keeps the highest-scored element when overlap exceeds threshold.
            function computeOverlap(a, b) {
                const xOverlap = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left));
                const yOverlap = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));
                const intersection = xOverlap * yOverlap;
                const smallerArea = Math.min(a.width * a.height, b.width * b.height);
                return smallerArea > 0 ? intersection / smallerArea : 0;
            }

            // Sort by weight descending, separate nav structural from content
            const navStructural = weightedElements
                .filter(el => el.isNavStructural)
                .sort((a, b) => b.weight - a.weight);
            const candidates = weightedElements
                .filter(el => !el.isNavStructural)
                .sort((a, b) => b.weight - a.weight);

            // NMS pass: suppress overlapping lower-scored elements
            const kept = [];
            for (const el of candidates) {
                let suppressed = false;
                for (const existing of kept) {
                    if (computeOverlap(el.rect, existing.rect) > 0.7) {
                        suppressed = true;
                        break;
                    }
                }
                if (!suppressed) kept.push(el);
            }

            // Category diversity cap: max 3 per tag type in top results
            const tagCounts = {};
            const sorted = [];
            for (const el of kept) {
                const tc = tagCounts[el.tag] || 0;
                if (tc >= 3) continue;
                tagCounts[el.tag] = tc + 1;
                sorted.push(el);
            }

            // Inject top nav/header as reserved region (guaranteed visibility)
            // Nav is important for IA understanding but shouldn't compete with content
            if (navStructural.length > 0) {
                const topNav = navStructural[0];
                // Only inject if it has a meaningful rect and isn't a viewport-spanning wrapper
                if (topNav.rect.width > 100 && topNav.rect.height > 20
                    && topNav.rect.height < topNav.rect.width * 0.5) {
                    // Mark it so dashboard can style it differently
                    topNav.isNavReserved = true;
                    // Insert after rank 1 (hero) but before other content
                    const insertPos = Math.min(1, sorted.length);
                    sorted.splice(insertPos, 0, topNav);
                }
            }

            // Detect hero section (largest heading + nearby image)
            const heroHeading = sorted.find(el =>
                (el.tag === 'h1' || el.tag === 'h2') &&
                el.aboveFold &&
                el.text.length > 10
            );

            // Detect primary CTA (most prominent button with action-oriented text)
            const buttons = sorted.filter(el =>
                el.tag === 'button' ||
                el.tag === 'a' && (el.className.includes('btn') || el.className.includes('button'))
            );

            // Bug 2 Fix: Score buttons by CTA likelihood
            const actionWords = ['start', 'get', 'try', 'sign up', 'signup', 'buy', 'shop', 'join', 'subscribe', 'download', 'free', 'demo'];
            const scoredButtons = buttons.map(btn => {
                const textLower = btn.text.toLowerCase();
                let ctaScore = btn.weight; // Start with visual weight

                // Boost for action-oriented text
                const hasActionWord = actionWords.some(word => textLower.includes(word));
                if (hasActionWord) {
                    ctaScore += 300; // Significant boost for action words
                }

                // Boost for button tag (more likely CTA than link)
                if (btn.tag === 'button') {
                    ctaScore += 100;
                }

                // Boost for primary/cta class names
                if (btn.className.includes('primary') || btn.className.includes('cta')) {
                    ctaScore += 200;
                }

                return { ...btn, ctaScore };
            });

            // Sort by CTA score instead of just visual weight
            scoredButtons.sort((a, b) => b.ctaScore - a.ctaScore);
            const primaryCTA = scoredButtons[0];

            // Detect navigation
            const nav = elements.find(el => el.tagName.toLowerCase() === 'nav');
            const navData = nav ? {
                exists: true,
                position: window.getComputedStyle(nav).position,
                top: nav.getBoundingClientRect().top
            } : { exists: false };

            // Detect content groupings
            const contentGroups = sorted.filter(el =>
                (el.className.includes('card') ||
                 el.className.includes('grid') ||
                 el.tag === 'article' ||
                 el.tag === 'section') &&
                el.rect.width > 200 &&
                el.rect.height > 100
            ).slice(0, 10);

            return {
                topElements: sorted.slice(0, 20),
                heroHeading: heroHeading,
                primaryCTA: primaryCTA,
                navigation: navData,
                contentGroups: contentGroups,
                viewport: viewport
            };
        }''')

        # Analyze patterns
        reading_pattern = self._detect_reading_pattern(hierarchy_data['topElements'])
        attention_flow = self._calculate_attention_flow(hierarchy_data['topElements'], hierarchy_data['viewport'])

        # Try CV-enhanced hero detection if available
        hero_sections = []
        detection_method = 'heuristic'

        if CV_AVAILABLE:
            try:
                cv_heroes = await self._cv_enhanced_hero_detection(page)
                if cv_heroes and len(cv_heroes) > 0:
                    hero_sections = cv_heroes
                    detection_method = 'computer_vision'
                    print("      ✅ CV hero detection successful")
            except Exception as e:
                print(f"      ⚠️  CV hero detection failed, using heuristic fallback: {str(e)}")
                hero_sections = [hierarchy_data.get('heroHeading')] if hierarchy_data.get('heroHeading') else []
        else:
            hero_sections = [hierarchy_data.get('heroHeading')] if hierarchy_data.get('heroHeading') else []

        return {
            'pattern': f"Visual hierarchy detected: {len(hierarchy_data['topElements'])} key elements",
            'confidence': self._calculate_vh_confidence(
                detection_method, hero_sections, hierarchy_data),
            'hero_sections': hero_sections,  # CV returns list of candidates
            'hero_section': self._format_hero_section(hero_sections[0] if hero_sections else None),
            'detection_method': detection_method,
            'primary_cta': self._format_primary_cta(hierarchy_data.get('primaryCTA')),
            'navigation': hierarchy_data['navigation'],
            'content_groups': hierarchy_data['contentGroups'][:5],  # Top 5
            'reading_pattern': reading_pattern,
            'visual_weight_map': hierarchy_data['topElements'][:10],  # Top 10 weighted
            'attention_flow': attention_flow,
            'viewport': hierarchy_data['viewport']
        }

    @staticmethod
    def _calculate_vh_confidence(detection_method, hero_sections, hierarchy_data):
        """Formula-based confidence for visual hierarchy."""
        confidence = 55
        # Detection method bonus
        confidence += 15 if detection_method == 'computer_vision' else 10
        # Hero candidate richness
        confidence += min(10, len(hero_sections) * 5)
        # Top element count (more elements analyzed = richer picture)
        top_count = len(hierarchy_data.get('topElements', []))
        confidence += min(10, top_count * 2)
        # CTA detection bonus
        if hierarchy_data.get('primaryCTA'):
            confidence += 5
        return min(95, confidence)

    async def _cv_enhanced_hero_detection(self, page) -> List[Dict]:
        """
        Computer vision-based hero detection

        Uses visual salience detector to find visually prominent elements.
        More robust than heuristics across diverse site types.
        """
        # Take screenshot for CV analysis
        screenshot_bytes = await page.screenshot(full_page=False)  # Above-the-fold only

        # Extract candidate elements with bounding boxes
        elements = await page.evaluate('''() => {
            const candidates = document.querySelectorAll('section, article, div, header, main');
            return Array.from(candidates).map(el => {
                const rect = el.getBoundingClientRect();
                const styles = window.getComputedStyle(el);

                // Filter out invisible/tiny elements
                if (rect.width < 100 || rect.height < 100) return null;
                if (styles.display === 'none' || styles.visibility === 'hidden') return null;

                // Safe className handling (SVG elements have SVGAnimatedString)
                const safeClassName = (typeof el.className === 'string') ?
                    el.className : (el.className?.baseVal || '');

                return {
                    selector: el.tagName.toLowerCase() +
                             (el.id ? '#' + el.id : '') +
                             (safeClassName ? '.' + safeClassName.split(' ')[0] : ''),
                    tag: el.tagName.toLowerCase(),
                    text: el.textContent?.substring(0, 100) || '',
                    className: safeClassName,
                    id: el.id,
                    bbox: {
                        x: Math.round(Math.max(0, rect.x)),
                        y: Math.round(Math.max(0, rect.y)),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    rect: {
                        top: rect.top,
                        left: rect.left,
                        width: rect.width,
                        height: rect.height
                    }
                };
            }).filter(el => el !== null);
        }''')

        if not elements or len(elements) == 0:
            return []

        # Run computer vision analysis
        detector = VisualSalienceDetector(screenshot_bytes)
        scored_elements = detector.find_hero_elements(elements)

        # Top 3 candidates with score > 400 are considered heroes
        heroes = [
            el for el in scored_elements[:3]
            if el.get('visual_weight', 0) > 400
        ]

        return heroes

    def _format_hero_section(self, hero) -> Dict:
        """Format hero section data"""
        if not hero:
            return {
                'detected': False,
                'message': 'No clear hero section detected'
            }

        return {
            'detected': True,
            'tag': hero['tag'],
            'text': hero['text'][:80] + '...' if len(hero['text']) > 80 else hero['text'],
            'position': f"top: {hero['rect']['top']}px",
            'size': f"{hero['rect']['width']}px × {hero['rect']['height']}px",
            'weight': round(hero['weight'], 1),
            'above_fold': hero['aboveFold']
        }

    def _format_primary_cta(self, cta) -> Dict:
        """Format primary CTA data"""
        if not cta:
            return {
                'detected': False,
                'message': 'No clear primary CTA detected'
            }

        return {
            'detected': True,
            'tag': cta['tag'],
            'text': cta['text'][:50] + '...' if len(cta['text']) > 50 else cta['text'],
            'position': f"top: {cta['rect']['top']}px, left: {cta['rect']['left']}px",
            'size': f"{cta['rect']['width']}px × {cta['rect']['height']}px",
            'weight': round(cta['weight'], 1),
            'className': cta['className']
        }

    def _detect_reading_pattern(self, elements: List[Dict]) -> str:
        """
        Detect reading pattern (F-pattern, Z-pattern, or Grid) based on element positions

        Heuristic: Analyzes spatial distribution of top 10 elements
        - F-pattern: 7+ elements with left < 300px (text-heavy, blog-style)
        - Z-pattern: 5+ elements with left > 500px (horizontal, landing pages)
        - Grid: Balanced distribution (ecommerce, galleries)

        Rationale:
        - F-pattern common in content sites (eyes scan left column)
        - Z-pattern in marketing pages (zigzag across headings/CTAs)
        - Grid for product listings and media galleries

        Confidence: Heuristic-based, not ML - treats as low confidence
        Failure modes:
        - Responsive designs may shift patterns at different breakpoints
        - Mixed layouts (header Z, content F) will classify by dominant pattern
        """
        # Simple heuristic:
        # F-pattern: Elements clustered on left side
        # Z-pattern: Elements spread horizontally
        # Grid: Evenly distributed

        left_heavy = sum(1 for el in elements[:10] if el['rect']['left'] < 300)
        spread = sum(1 for el in elements[:10] if el['rect']['left'] > 500)

        if left_heavy > 7:
            return 'F-pattern (Left-heavy, text-focused)'
        elif spread > 5:
            return 'Z-pattern (Horizontal spread)'
        else:
            return 'Grid layout (Balanced distribution)'

    def _calculate_attention_flow(self, elements: List[Dict], viewport: Dict = None) -> List[str]:
        """
        Calculate likely attention flow based on visual weight.
        Skips structural containers (html, body, div wrappers) that span
        the full page — those aren't what the eye actually lands on.

        Bug 3 Fix: Deduplicates nested elements by detecting text overlap.
        """
        # Tags that are pure layout containers, not visual targets
        SKIP_TAGS = {'html', 'body', 'head', 'script', 'style', 'noscript'}

        # Semantic tags that should ALWAYS be included (navigation, headers, main content)
        SEMANTIC_TAGS = {'nav', 'header', 'main', 'article', 'aside'}

        # Use real viewport or fall back to standard desktop
        vp_w = (viewport or {}).get('width', 1920)
        vp_h = (viewport or {}).get('height', 1080)

        flow = []
        added_texts = set()  # Track text content to avoid duplicates

        for el in elements:
            if len(flow) >= 10:  # Increased from 5 to 10 to ensure nav gets included
                break
            # Skip structural containers
            if el['tag'] in SKIP_TAGS:
                continue
            # Skip any element that spans >80% viewport width AND >200% viewport height —
            # UNLESS it's a semantic tag (nav, header, etc.)
            if el['tag'] not in SEMANTIC_TAGS:
                if el['rect']['width'] > vp_w * 0.8 and el['rect']['height'] > vp_h * 2:
                    continue

            # Bug 3 Fix: Skip if we've already added an element with same/similar text
            el_text = el['text'][:40].strip().lower()
            if el_text and len(el_text) > 3:  # Only check non-trivial text
                # Check if this text is a substring of any previously added text, or vice versa
                is_duplicate = False
                for added_text in added_texts:
                    if el_text in added_text or added_text in el_text:
                        # This is likely a nested element (parent/child)
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue  # Skip this duplicate

                added_texts.add(el_text)

            step = f"{len(flow)+1}. {el['tag'].upper()}"
            if el['text']:
                step += f" - '{el['text'][:40]}...'"
            step += f" (weight: {round(el['weight'], 1)})"
            flow.append(step)

        return flow


# Integration test
async def test_visual_hierarchy():
    """Test visual hierarchy analysis"""
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto('https://stripe.com', wait_until='networkidle')

        analyzer = VisualHierarchyAnalyzer()
        result = await analyzer.analyze(page)

        print("\n" + "="*70)
        print(" 👁️  VISUAL HIERARCHY ANALYSIS")
        print("="*70)

        print("\n🦸 Hero Section:")
        hero = result['hero_section']
        if hero['detected']:
            print(f"   Tag: {hero['tag']}")
            print(f"   Text: {hero['text']}")
            print(f"   Position: {hero['position']}")
            print(f"   Weight: {hero['weight']}")
        else:
            print(f"   {hero['message']}")

        print("\n🎯 Primary CTA:")
        cta = result['primary_cta']
        if cta['detected']:
            print(f"   Tag: {cta['tag']}")
            print(f"   Text: {cta['text']}")
            print(f"   Position: {cta['position']}")
        else:
            print(f"   {cta['message']}")

        print(f"\n🧭 Navigation: {'✅ Detected' if result['navigation']['exists'] else '❌ Not found'}")

        print(f"\n📖 Reading Pattern: {result['reading_pattern']}")

        print("\n👀 Attention Flow (Top 5):")
        for step in result['attention_flow']:
            print(f"   {step}")

        print(f"\n📦 Content Groups: {len(result['content_groups'])} detected")

        await browser.close()

        print("\n" + "="*70 + "\n")


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_visual_hierarchy())
