"""
Screenshot Annotator - Visual Evidence Capture

Captures screenshots and overlays annotations showing:
1. Hero section highlight (red box)
2. Primary CTA highlight (green box)
3. Navigation bar outline (blue box)
4. Content groups (purple boxes)
5. Visual hierarchy labels

Philosophy: "Show, don't just tell"
"""

import base64
from typing import Dict, List, Optional
from pathlib import Path


class ScreenshotAnnotator:
    """
    Capture and annotate screenshots with visual hierarchy overlays
    """

    def __init__(self):
        # Hidden dir — one file per domain, always overwritten. Never accumulates.
        self.screenshot_dir = Path(".screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)

    async def capture_and_annotate(self, page, visual_hierarchy: Dict, site_url: str) -> Dict:
        """
        Capture screenshot and overlay visual hierarchy annotations

        Args:
            page: Playwright page object
            visual_hierarchy: Visual hierarchy analysis results
            site_url: URL being analyzed

        Returns:
            {
                'screenshot_base64': '...',  # Base64 encoded screenshot
                'screenshot_path': 'path/to/screenshot.png',
                'annotations': [...],  # Annotation data
                'annotated_base64': '...'  # Annotated screenshot
            }
        """
        print("   📸 Capturing screenshot with annotations...")

        # Step 1: Capture clean screenshot (full page with scrolling)
        screenshot_bytes = await page.screenshot(full_page=True)
        from urllib.parse import urlparse
        domain = urlparse(site_url).netloc.replace("www.", "") or "unknown"
        screenshot_path = self.screenshot_dir / f"{domain}.png"

        # Save screenshot
        with open(screenshot_path, 'wb') as f:
            f.write(screenshot_bytes)

        # Convert to base64 for web display
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        # Step 2: Add annotations overlay
        annotations = self._prepare_annotations(visual_hierarchy)

        # Step 3: Capture annotated version (with overlays)
        annotated_base64 = await self._capture_annotated_screenshot(
            page,
            visual_hierarchy,
            annotations
        )

        return {
            'screenshot_base64': screenshot_base64,
            'screenshot_path': str(screenshot_path),
            'annotations': annotations,
            'annotated_base64': annotated_base64,
            'success': True
        }

    def _prepare_annotations(self, visual_hierarchy: Dict) -> List[Dict]:
        """
        Prepare annotation data from visual hierarchy analysis
        """
        annotations = []

        # Hero section annotation
        hero = visual_hierarchy.get('hero_section', {})
        if hero.get('detected'):
            annotations.append({
                'type': 'hero',
                'label': '🦸 Hero Section',
                'color': '#ff453a',
                'position': hero.get('position', ''),
                'size': hero.get('size', ''),
                'text': hero.get('text', '')[:50]
            })

        # Primary CTA annotation
        cta = visual_hierarchy.get('primary_cta', {})
        if cta.get('detected'):
            annotations.append({
                'type': 'cta',
                'label': '🎯 Primary CTA',
                'color': '#34c759',
                'position': cta.get('position', ''),
                'size': cta.get('size', ''),
                'text': cta.get('text', '')[:30]
            })

        # Navigation annotation
        nav = visual_hierarchy.get('navigation', {})
        if nav.get('exists'):
            annotations.append({
                'type': 'navigation',
                'label': '🧭 Navigation',
                'color': '#0a84ff',
                'position': f"top: {nav.get('top', 0)}px"
            })

        # Content groups annotations
        content_groups = visual_hierarchy.get('content_groups', [])
        for i, group in enumerate(content_groups[:3]):  # Top 3 groups
            annotations.append({
                'type': 'content_group',
                'label': f'📦 Content Group {i+1}',
                'color': '#bf5af2',
                'position': f"top: {group['rect']['top']}px, left: {group['rect']['left']}px",
                'size': f"{group['rect']['width']}px × {group['rect']['height']}px"
            })

        return annotations

    async def _capture_annotated_screenshot(self, page, visual_hierarchy: Dict, annotations: List[Dict]) -> str:
        """
        Inject overlay annotations and capture screenshot

        This adds visual boxes/labels on the page before screenshotting
        """
        # Inject annotation overlay CSS and HTML
        await page.evaluate('''(visualHierarchy) => {
            // Remove any existing overlays
            const existingOverlay = document.getElementById('hierarchy-overlay');
            if (existingOverlay) {
                existingOverlay.remove();
            }

            // Create overlay container
            const overlay = document.createElement('div');
            overlay.id = 'hierarchy-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 999999;
            `;

            // Add hero section box
            const hero = visualHierarchy.hero_section;
            if (hero && hero.detected) {
                const heroBox = document.createElement('div');
                heroBox.style.cssText = `
                    position: absolute;
                    border: 3px solid #ff453a;
                    background: rgba(255, 69, 58, 0.1);
                    top: ${hero.rect?.top || 0}px;
                    left: ${hero.rect?.left || 0}px;
                    width: ${hero.rect?.width || 0}px;
                    height: ${hero.rect?.height || 0}px;
                    border-radius: 8px;
                `;

                const heroLabel = document.createElement('div');
                heroLabel.textContent = '🦸 Hero Section';
                heroLabel.style.cssText = `
                    position: absolute;
                    top: -30px;
                    left: 0;
                    background: #ff453a;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    font-family: -apple-system, sans-serif;
                `;
                heroBox.appendChild(heroLabel);
                overlay.appendChild(heroBox);
            }

            // Add primary CTA box
            const cta = visualHierarchy.primary_cta;
            if (cta && cta.detected) {
                const ctaBox = document.createElement('div');
                ctaBox.style.cssText = `
                    position: absolute;
                    border: 3px solid #34c759;
                    background: rgba(52, 199, 89, 0.1);
                    top: ${cta.rect?.top || 0}px;
                    left: ${cta.rect?.left || 0}px;
                    width: ${cta.rect?.width || 0}px;
                    height: ${cta.rect?.height || 0}px;
                    border-radius: 8px;
                `;

                const ctaLabel = document.createElement('div');
                ctaLabel.textContent = '🎯 Primary CTA';
                ctaLabel.style.cssText = `
                    position: absolute;
                    top: -30px;
                    left: 0;
                    background: #34c759;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    font-family: -apple-system, sans-serif;
                `;
                ctaBox.appendChild(ctaLabel);
                overlay.appendChild(ctaBox);
            }

            // Add navigation box
            const nav = document.querySelector('nav');
            if (nav) {
                const navRect = nav.getBoundingClientRect();
                const navBox = document.createElement('div');
                navBox.style.cssText = `
                    position: absolute;
                    border: 3px solid #0a84ff;
                    background: rgba(10, 132, 255, 0.1);
                    top: ${navRect.top}px;
                    left: ${navRect.left}px;
                    width: ${navRect.width}px;
                    height: ${navRect.height}px;
                    border-radius: 8px;
                `;

                const navLabel = document.createElement('div');
                navLabel.textContent = '🧭 Navigation';
                navLabel.style.cssText = `
                    position: absolute;
                    top: -30px;
                    left: 0;
                    background: #0a84ff;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    font-family: -apple-system, sans-serif;
                `;
                navBox.appendChild(navLabel);
                overlay.appendChild(navBox);
            }

            // Add content group boxes
            const contentGroups = visualHierarchy.content_groups || [];
            contentGroups.slice(0, 3).forEach((group, i) => {
                const groupBox = document.createElement('div');
                groupBox.style.cssText = `
                    position: absolute;
                    border: 2px dashed #bf5af2;
                    background: rgba(191, 90, 242, 0.05);
                    top: ${group.rect.top}px;
                    left: ${group.rect.left}px;
                    width: ${group.rect.width}px;
                    height: ${group.rect.height}px;
                    border-radius: 8px;
                `;

                const groupLabel = document.createElement('div');
                groupLabel.textContent = `📦 Group ${i+1}`;
                groupLabel.style.cssText = `
                    position: absolute;
                    top: -25px;
                    left: 0;
                    background: #bf5af2;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    font-family: -apple-system, sans-serif;
                `;
                groupBox.appendChild(groupLabel);
                overlay.appendChild(groupBox);
            });

            document.body.appendChild(overlay);

        }''', visual_hierarchy)

        # Wait for overlay to paint — rAF syncs to render cycle
        await page.evaluate("() => new Promise(r => requestAnimationFrame(r))")

        # Capture annotated screenshot (full page with scrolling)
        annotated_bytes = await page.screenshot(full_page=True)
        annotated_base64 = base64.b64encode(annotated_bytes).decode('utf-8')

        # Remove overlay
        await page.evaluate('''() => {
            const overlay = document.getElementById('hierarchy-overlay');
            if (overlay) {
                overlay.remove();
            }
        }''')

        return annotated_base64


# Test
async def test_screenshot_annotator():
    """Test screenshot annotation"""
    from patchright.async_api import async_playwright
    from visual_hierarchy_analyzer import VisualHierarchyAnalyzer

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        url = 'https://example.com'
        await page.goto(url, wait_until='domcontentloaded')

        # Analyze visual hierarchy
        hierarchy_analyzer = VisualHierarchyAnalyzer()
        visual_hierarchy = await hierarchy_analyzer.analyze(page)

        # Capture and annotate
        annotator = ScreenshotAnnotator()
        result = await annotator.capture_and_annotate(page, visual_hierarchy, url)

        print("\n" + "="*70)
        print(" 📸 SCREENSHOT ANNOTATION TEST")
        print("="*70)

        if result['success']:
            print(f"\n✅ Screenshot captured!")
            print(f"   Path: {result['screenshot_path']}")
            print(f"   Annotations: {len(result['annotations'])}")

            for anno in result['annotations']:
                print(f"\n   {anno['label']}")
                print(f"     Type: {anno['type']}")
                print(f"     Color: {anno['color']}")
                if 'text' in anno:
                    print(f"     Text: {anno['text']}")

        await browser.close()

        print("\n" + "="*70 + "\n")


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_screenshot_annotator())
