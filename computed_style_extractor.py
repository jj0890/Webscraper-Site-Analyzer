"""
Computed Style Extractor - Get ACTUAL pixel values, not just class names

This solves the "CSS-in-JS problem" where sites like NTS Live use:
- Styled Components (sc-* classes)
- Tailwind with custom themes
- CSS Modules with hashed names
- Runtime-generated styles

Instead of returning useless class names, we return EXACT values:
- padding: "24px 32px" (not "p-6")
- background: "#f7f7f7" (not "bg-gray-100")
- font-size: "14px" (not "text-sm")
"""

import asyncio
from patchright.async_api import Page
from typing import Dict, List, Optional
import json


class ComputedStyleExtractor:
    """
    Extract actual computed styles from live sites

    Use cases:
    - NTS Live: Get exact card spacing (not Tailwind classes)
    - Bandcamp: Extract gradient overlays (not styled-component hashes)
    - Pitchfork: Capture typography scale (not CSS variable references)
    """

    def __init__(self, page: Page):
        self.page = page

    async def extract_computed_styles(self, selector: str) -> Dict:
        """
        Get ALL computed styles for an element

        Args:
            selector: CSS selector (e.g., '.channel-card', '#hero')

        Returns:
            {
                'selector': '.channel-card',
                'computed_styles': {...actual pixel values...},
                'confidence': 100,
                'found': true
            }
        """
        print(f"\n🎨 Extracting computed styles for: {selector}")

        result = await self.page.evaluate('''(sel) => {
            const element = document.querySelector(sel);
            if (!element) {
                return {
                    found: false,
                    error: 'Element not found',
                    selector: sel
                };
            }

            const styles = window.getComputedStyle(element);

            // Extract ALL style properties
            const computed = {};
            for (let i = 0; i < styles.length; i++) {
                const prop = styles[i];
                computed[prop] = styles.getPropertyValue(prop);
            }

            // Also get critical layout values explicitly
            const critical = {
                // Box Model
                display: styles.display,
                width: styles.width,
                height: styles.height,
                padding: styles.padding,
                paddingTop: styles.paddingTop,
                paddingRight: styles.paddingRight,
                paddingBottom: styles.paddingBottom,
                paddingLeft: styles.paddingLeft,
                margin: styles.margin,
                marginTop: styles.marginTop,
                marginRight: styles.marginRight,
                marginBottom: styles.marginBottom,
                marginLeft: styles.marginLeft,

                // Flexbox/Grid
                flexDirection: styles.flexDirection,
                flexWrap: styles.flexWrap,
                justifyContent: styles.justifyContent,
                alignItems: styles.alignItems,
                gap: styles.gap,
                gridTemplateColumns: styles.gridTemplateColumns,
                gridTemplateRows: styles.gridTemplateRows,
                gridGap: styles.gridGap,

                // Typography
                fontFamily: styles.fontFamily,
                fontSize: styles.fontSize,
                fontWeight: styles.fontWeight,
                lineHeight: styles.lineHeight,
                letterSpacing: styles.letterSpacing,
                textAlign: styles.textAlign,
                textTransform: styles.textTransform,

                // Colors
                color: styles.color,
                backgroundColor: styles.backgroundColor,
                borderColor: styles.borderColor,

                // Visual
                border: styles.border,
                borderRadius: styles.borderRadius,
                boxShadow: styles.boxShadow,
                background: styles.background,
                backgroundImage: styles.backgroundImage,
                opacity: styles.opacity,

                // Positioning
                position: styles.position,
                top: styles.top,
                right: styles.right,
                bottom: styles.bottom,
                left: styles.left,
                zIndex: styles.zIndex,

                // Effects
                transform: styles.transform,
                transition: styles.transition,
                animation: styles.animation,
                filter: styles.filter,
                backdropFilter: styles.backdropFilter,

                // Overflow
                overflow: styles.overflow,
                overflowX: styles.overflowX,
                overflowY: styles.overflowY
            };

            return {
                found: true,
                selector: sel,
                computed_styles: critical,
                all_styles: computed,
                confidence: 100
            };
        }''', selector)

        if result['found']:
            print(f"   ✅ Extracted {len(result['computed_styles'])} style properties")
        else:
            print(f"   ❌ {result['error']}")

        return result

    async def extract_multiple_selectors(self, selectors: List[str]) -> Dict:
        """
        Extract styles for multiple elements at once

        Use case: Compare card styles across different sections

        Args:
            selectors: List of CSS selectors

        Returns:
            {
                '.channel-card': {...styles...},
                '.episode-card': {...styles...},
                '.genre-card': {...styles...}
            }
        """
        results = {}

        for selector in selectors:
            result = await self.extract_computed_styles(selector)
            if result['found']:
                results[selector] = result['computed_styles']

        return results

    async def extract_critical_values(self, selector: str) -> Dict:
        """
        Extract ONLY the values designers care about

        Perfect for copy-pasting into Figma or code

        Returns:
            {
                'spacing': {'padding': '24px 32px', 'gap': '16px'},
                'colors': {'background': '#f7f7f7', 'text': '#1a1a1a'},
                'typography': {'font': 'Inter', 'size': '14px', 'weight': '500'},
                'effects': {'radius': '12px', 'shadow': '0 2px 8px rgba(0,0,0,0.1)'}
            }
        """
        full_styles = await self.extract_computed_styles(selector)

        if not full_styles['found']:
            return full_styles

        styles = full_styles['computed_styles']

        # Organize into designer-friendly categories
        critical = {
            'spacing': {
                'padding': styles.get('padding'),
                'margin': styles.get('margin'),
                'gap': styles.get('gap')
            },
            'colors': {
                'background': styles.get('backgroundColor'),
                'text': styles.get('color'),
                'border': styles.get('borderColor')
            },
            'typography': {
                'font_family': styles.get('fontFamily', '').split(',')[0].replace('"', '').strip(),
                'font_size': styles.get('fontSize'),
                'font_weight': styles.get('fontWeight'),
                'line_height': styles.get('lineHeight'),
                'letter_spacing': styles.get('letterSpacing')
            },
            'layout': {
                'display': styles.get('display'),
                'flex_direction': styles.get('flexDirection') if styles.get('display') == 'flex' else None,
                'grid_columns': styles.get('gridTemplateColumns') if styles.get('display') == 'grid' else None,
                'justify': styles.get('justifyContent'),
                'align': styles.get('alignItems')
            },
            'effects': {
                'border_radius': styles.get('borderRadius'),
                'box_shadow': styles.get('boxShadow'),
                'opacity': styles.get('opacity'),
                'transform': styles.get('transform'),
                'transition': styles.get('transition')
            }
        }

        return {
            'found': True,
            'selector': selector,
            'critical_values': critical,
            'confidence': 100
        }

    def generate_copy_paste_css(self, styles: Dict) -> str:
        """
        Generate ready-to-use CSS from computed styles

        Input: Computed styles object
        Output: Clean CSS you can paste into your project
        """
        if not styles.get('found'):
            return "/* Element not found */"

        critical = styles.get('critical_values') or styles.get('computed_styles')

        css_lines = []

        # Handle nested structure (critical_values) or flat (computed_styles)
        if 'spacing' in critical:
            # Critical values format
            for category, props in critical.items():
                if category in ['spacing', 'colors', 'typography', 'layout', 'effects']:
                    for key, value in props.items():
                        if value and value != 'none' and value != 'auto' and value != 'normal':
                            # Convert snake_case to kebab-case
                            css_key = key.replace('_', '-')
                            css_lines.append(f"  {css_key}: {value};")
        else:
            # Flat computed styles format
            for key, value in critical.items():
                if value and value != 'none' and value != 'auto' and value != 'normal':
                    css_lines.append(f"  {key}: {value};")

        selector = styles.get('selector', '.element')
        css = f"{selector} {{\n" + "\n".join(css_lines[:30]) + "\n}"  # Limit to 30 most important

        return css


async def demo_computed_styles():
    """
    Demo: Extract exact styles from real sites
    """
    from patchright.async_api import async_playwright

    print("\n" + "="*70)
    print(" 🎨 COMPUTED STYLE EXTRACTOR DEMO")
    print("="*70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Test with Stripe docs (clean, predictable)
        print(f"\n🌐 Loading: https://stripe.com/docs")
        await page.goto('https://stripe.com/docs', wait_until='networkidle')

        extractor = ComputedStyleExtractor(page)

        # Extract navigation styles
        nav_styles = await extractor.extract_critical_values('nav')

        if nav_styles['found']:
            print("\n📊 CRITICAL VALUES FOR NAVIGATION:")
            print(json.dumps(nav_styles['critical_values'], indent=2))

            # Generate copy-paste CSS
            css = extractor.generate_copy_paste_css(nav_styles)
            print("\n📋 COPY-PASTE CSS:")
            print(css)

        # Compare multiple card elements
        print(f"\n🔍 Comparing card styles...")
        cards = await extractor.extract_multiple_selectors([
            'article', '.card', '[class*="card"]'
        ])

        for selector, styles in cards.items():
            if styles.get('display'):
                print(f"\n   {selector}:")
                print(f"      Display: {styles.get('display')}")
                print(f"      Padding: {styles.get('padding')}")
                print(f"      Border Radius: {styles.get('borderRadius')}")

        await browser.close()


if __name__ == '__main__':
    asyncio.run(demo_computed_styles())
