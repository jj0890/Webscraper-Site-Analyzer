"""
Component Ripper - Extract "The Stuff Itself"

Instead of vague descriptions, this extracts EXACT architectural blueprints:
- Box model (padding, margin, gap)
- Layout logic (grid vs flex, alignment)
- Typography scale (sizes, weights, spacing)
- Interactivity patterns (transitions, animations)
- CSS custom properties
- Component relationships

Returns JSON blueprint + React/Tailwind boilerplate code
"""

import asyncio
from patchright.async_api import async_playwright
import json
import logging
from typing import Dict, List, Optional


class ComponentRipper:
    """
    Deep component extraction - returns implementation-ready blueprints
    """

    def __init__(self, url: str, selector: Optional[str] = None):
        self.url = url
        self.selector = selector  # Specific component to rip (e.g., '.product-grid')
        self.blueprint = {}

    async def rip(self, auth_state: Optional[str] = None, use_stealth: bool = False,
                  include_states: bool = False, output_format: str = 'json'):
        """
        Extract component blueprint with optional auth and stealth mode

        Args:
            auth_state: Path to saved auth state (for login walls)
            use_stealth: Enable stealth mode to bypass anti-bot measures
            include_states: Capture hover/focus interactive state deltas
            output_format: 'json' (default) or 'figma' (Tailwind JSX markdown)
        """
        self._include_states = include_states
        self._output_format = output_format
        if use_stealth:
            # Use stealth agent for protected sites
            from stealth_agent import StealthAgent
            agent = StealthAgent(self.url, auth_state)
            page = await agent.get_stealth_page()
            success = await agent.navigate_with_jitter()

            if not success:
                print("   ❌ Stealth navigation failed")
                return {'error': 'Navigation failed'}

            # Extract for stealth mode
            if self.selector:
                self.blueprint = await self._rip_component(page, self.selector)
                if include_states:
                    self.blueprint['interactive_states'] = await self._extract_component_states(page, self.selector)
                if output_format == 'figma':
                    self._attach_figma_output(self.blueprint)
            else:
                self.blueprint = await self._rip_page_sections(page)

        else:
            # Standard approach - keep browser management inside context
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                # Load auth state if provided
                if auth_state:
                    context = await browser.new_context(storage_state=auth_state)
                else:
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080}
                    )

                page = await context.new_page()
                page.set_default_timeout(60000)

                print(f"\n🔬 Component Ripper: {self.url}")
                if self.selector:
                    print(f"   Targeting: {self.selector}")

                # Load page and extract
                try:
                    await page.goto(self.url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(3)

                    # Extract component blueprint
                    if self.selector:
                        self.blueprint = await self._rip_component(page, self.selector)
                        if include_states:
                            self.blueprint['interactive_states'] = await self._extract_component_states(page, self.selector)
                        if output_format == 'figma':
                            self._attach_figma_output(self.blueprint)
                    else:
                        # Rip common high-value components
                        self.blueprint = await self._rip_page_sections(page)

                except Exception as e:
                    print(f"   ❌ Error during rip: {e}")
                    self.blueprint = {'error': str(e)}

                finally:
                    await browser.close()

        return self.blueprint

    async def _rip_component(self, page, selector: str):
        """
        Deep dive into a specific component

        Returns:
            - Layout blueprint
            - Typography scale
            - Spacing system
            - Computed styles (what actually renders)
            - Framework hints (React, Vue, Tailwind detection)
            - React/Tailwind code
        """
        print(f"\n   🎯 Extracting blueprint for: {selector}")

        blueprint = await page.evaluate(f'''(selector) => {{
            const element = document.querySelector(selector);
            if (!element) return {{ error: 'Selector not found' }};

            const styles = window.getComputedStyle(element);

            // Extract ALL computed styles (not just selected ones)
            const computedStyles = {{}};
            for (let i = 0; i < styles.length; i++) {{
                const prop = styles[i];
                computedStyles[prop] = styles.getPropertyValue(prop);
            }}

            // Detect framework hints
            const frameworkHints = {{
                react: !!(element.hasAttribute('data-reactroot') ||
                         element.hasAttribute('data-reactid') ||
                         element.closest('[data-reactroot]') ||
                         window.React || window.__REACT_DEVTOOLS_GLOBAL_HOOK__),
                vue: !!(element.hasAttribute('data-v-') ||
                       element.__vue__ ||
                       element.__vueParentComponent ||
                       window.Vue || window.__VUE_DEVTOOLS_GLOBAL_HOOK__),
                angular: !!(element.hasAttribute('ng-version') ||
                           window.ng || window.getAllAngularRootElements),
                svelte: !!(element.hasAttribute('data-svelte-h') ||
                          element.closest('[data-svelte-h]')),
                tailwind: false,  // detected via classes below
                bootstrap: false,  // detected via classes below
                materialUI: false,  // detected via classes below
            }};

            // Check classes for framework signatures
            const classes = Array.from(element.classList);
            const allClasses = Array.from(element.querySelectorAll('*'))
                .flatMap(el => Array.from(el.classList));

            // Tailwind detection (utility-first patterns)
            const tailwindPatterns = /^(flex|grid|p-|m-|w-|h-|text-|bg-|border-|rounded-|shadow-)/;
            frameworkHints.tailwind = allClasses.some(c => tailwindPatterns.test(c));

            // Bootstrap detection
            frameworkHints.bootstrap = allClasses.some(c =>
                c.startsWith('col-') || c.startsWith('row') ||
                c.startsWith('btn-') || c.startsWith('container')
            );

            // Material UI detection
            frameworkHints.materialUI = allClasses.some(c =>
                c.startsWith('Mui') || c.startsWith('MuiButton') ||
                c.startsWith('makeStyles')
            );

            // CSS-in-JS detection
            const cssInJS = {{
                styledComponents: allClasses.some(c => c.match(/^sc-[a-zA-Z]+-[a-zA-Z]+$/)),
                emotion: allClasses.some(c => c.startsWith('css-')),
                jss: allClasses.some(c => c.match(/^[a-zA-Z]+-\d+-\d+/))
            }};
            frameworkHints.cssInJS = Object.values(cssInJS).some(v => v);
            frameworkHints.cssInJSDetails = cssInJS;

            // Box Model
            const boxModel = {{
                width: styles.width,
                height: styles.height,
                padding: styles.padding,
                margin: styles.margin,
                border: styles.border,
                display: styles.display,
                position: styles.position
            }};

            // Layout (if flex or grid)
            const layout = {{}};
            if (styles.display === 'flex') {{
                layout.type = 'flexbox';
                layout.direction = styles.flexDirection;
                layout.wrap = styles.flexWrap;
                layout.justify = styles.justifyContent;
                layout.align = styles.alignItems;
                layout.gap = styles.gap;
            }} else if (styles.display === 'grid') {{
                layout.type = 'grid';
                layout.columns = styles.gridTemplateColumns;
                layout.rows = styles.gridTemplateRows;
                layout.gap = styles.gap;
                layout.autoFlow = styles.gridAutoFlow;
            }}

            // Typography (direct children)
            const typography = [];
            const textElements = element.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, a');
            for (const el of Array.from(textElements).slice(0, 5)) {{
                const s = window.getComputedStyle(el);
                typography.push({{
                    tag: el.tagName.toLowerCase(),
                    fontSize: s.fontSize,
                    fontWeight: s.fontWeight,
                    lineHeight: s.lineHeight,
                    letterSpacing: s.letterSpacing,
                    textTransform: s.textTransform,
                    color: s.color
                }});
            }}

            // Spacing patterns (children gaps)
            const children = Array.from(element.children);
            const childSpacing = children.slice(0, 3).map(child => {{
                const s = window.getComputedStyle(child);
                return {{
                    margin: s.margin,
                    padding: s.padding,
                    gap: s.gap
                }};
            }});

            // Interactivity (transitions, transforms)
            const interactivity = {{
                transition: styles.transition,
                transform: styles.transform,
                cursor: styles.cursor,
                overflow: styles.overflow,
                opacity: styles.opacity
            }};

            // Background & Colors
            const visual = {{
                backgroundColor: styles.backgroundColor,
                backgroundImage: styles.backgroundImage,
                borderRadius: styles.borderRadius,
                boxShadow: styles.boxShadow
            }};

            // Component hierarchy
            const hierarchy = {{
                depth: element.querySelectorAll('*').length,
                directChildren: element.children.length,
                childTags: Array.from(element.children).map(c => c.tagName.toLowerCase())
            }};

            return {{
                selector: selector,
                boxModel,
                layout,
                typography,
                childSpacing,
                interactivity,
                visual,
                hierarchy,
                computedStyles,  // ALL computed styles for exact replication
                frameworkHints   // Framework detection for context
            }};
        }}''', selector)

        if 'error' in blueprint:
            print(f"   ❌ {blueprint['error']}")
            return blueprint

        # Extract source HTML and CSS
        source_data = await page.evaluate(f'''(selector) => {{
            const element = document.querySelector(selector);
            if (!element) return {{}};

            // Get source HTML (outer HTML with indentation preserved)
            const sourceHTML = element.outerHTML;

            // Get inline styles
            const inlineStyles = element.style.cssText;

            // Try to find stylesheet rules matching this element
            const matchingRules = [];
            for (const sheet of document.styleSheets) {{
                try {{
                    const rules = sheet.cssRules || sheet.rules;
                    for (const rule of rules) {{
                        if (rule.selectorText && element.matches(rule.selectorText)) {{
                            matchingRules.push({{
                                selector: rule.selectorText,
                                css: rule.cssText
                            }});
                        }}
                    }}
                }} catch (e) {{
                    // CORS or security restriction, skip this sheet
                }}
            }}

            return {{
                sourceHTML: sourceHTML,
                inlineStyles: inlineStyles,
                matchingCSSRules: matchingRules
            }};
        }}''', selector)

        blueprint['source'] = source_data

        # Extract component anatomy — walk 2 levels deep into children
        try:
            raw_anatomy = await page.evaluate('''(selector) => {
                const root = document.querySelector(selector);
                if (!root) return { children: [], parent: {} };

                const s = window.getComputedStyle(root);
                const rootRect = root.getBoundingClientRect();

                const parent = {
                    display: s.display,
                    flexDirection: s.flexDirection,
                    justifyContent: s.justifyContent,
                    alignItems: s.alignItems,
                    gap: s.gap,
                    gridTemplateColumns: s.gridTemplateColumns,
                    width: Math.round(rootRect.width),
                    height: Math.round(rootRect.height),
                    left: Math.round(rootRect.left)
                };

                function extractChild(el, depth) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) return null;
                    const cs = window.getComputedStyle(el);
                    if (cs.display === 'none' || cs.visibility === 'hidden') return null;

                    const cn = (typeof el.className === 'string') ?
                        el.className : (el.className?.baseVal || '');

                    const node = {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        className: cn.substring(0, 80),
                        text: (el.textContent || '').replace(/\\s+/g, ' ').trim().substring(0, 60),
                        href: el.getAttribute('href') || null,
                        src: el.getAttribute('src') || el.querySelector('img')?.src || null,
                        role: el.getAttribute('role') || null,
                        ariaLabel: el.getAttribute('aria-label') || null,
                        rect: {
                            top: Math.round(rect.top - rootRect.top),
                            left: Math.round(rect.left - rootRect.left),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        },
                        styles: {
                            display: cs.display,
                            position: cs.position,
                            flexDirection: cs.flexDirection,
                            justifyContent: cs.justifyContent,
                            alignItems: cs.alignItems,
                            gap: cs.gap,
                            fontFamily: cs.fontFamily,
                            fontSize: cs.fontSize,
                            fontWeight: cs.fontWeight,
                            color: cs.color,
                            backgroundColor: cs.backgroundColor,
                            borderRadius: cs.borderRadius,
                            padding: cs.padding,
                            transition: cs.transition
                        },
                        childCount: el.children.length,
                        children: []
                    };

                    if (depth < 2) {
                        const kids = Array.from(el.children).slice(0, 20);
                        for (const kid of kids) {
                            const c = extractChild(kid, depth + 1);
                            if (c) node.children.push(c);
                        }
                    }

                    return node;
                }

                const children = [];
                const directKids = Array.from(root.children).slice(0, 30);
                for (const kid of directKids) {
                    const c = extractChild(kid, 1);
                    if (c) children.push(c);
                }

                return { children, parent };
            }''', selector)

            blueprint['anatomy'] = self._extract_component_anatomy(raw_anatomy)
        except Exception as e:
            blueprint['anatomy'] = {'error': str(e), 'zones': [], 'layout_system': {}, 'child_summary': {}}

        # Extract Tailwind classes (V2 enhancement)
        tailwind_extraction = await self._extract_tailwind_classes(page, selector)
        blueprint['tailwind'] = tailwind_extraction

        # Detect JavaScript behavior (V2 enhancement)
        js_detection = await self._detect_javascript_behavior(page, selector)
        blueprint['javascript'] = js_detection

        # Get semantic name (V2 enhancement)
        semantic_name = await self._get_semantic_name(page, selector)
        blueprint['semantic_name'] = semantic_name

        # Generate code snippets
        blueprint['code'] = self._generate_component_code(blueprint)

        # Add portability analysis (NEW: addresses LLM feedback)
        blueprint['portability'] = self._analyze_portability(blueprint)

        # Add metadata about extraction
        import datetime
        blueprint['metadata'] = {
            'extracted_at': datetime.datetime.now().isoformat(),
            'url': self.url,
            'selector': selector,
            'extraction_method': 'playwright_computed_styles'
        }

        # Generate Markdown documentation (V2)
        component_name = selector.replace('.', '').replace('#', '').replace('[', '').replace(']', '')
        blueprint['markdown'] = self._generate_markdown_doc(blueprint, component_name)

        return blueprint

    async def _extract_component_states(self, page, selector: str) -> Dict:
        """
        Physically hover/focus interactive elements WITHIN the component
        to capture real CSS state deltas.

        Reuses STATE_PROPERTIES and _compute_delta from interaction_state_capture.
        """
        from extractors.interaction_state_capture import STATE_PROPERTIES, _compute_delta

        logger = logging.getLogger(__name__)
        logger.info(f"Capturing interactive states for component: {selector}")

        # Find interactive elements within the component + the root itself
        elements = await page.evaluate('''(args) => {
            const { rootSel, stateProps } = args;
            const root = document.querySelector(rootSel);
            if (!root) return [];

            const results = [];

            function readStyles(el) {
                const s = window.getComputedStyle(el);
                const out = {};
                for (const p of stateProps) out[p] = s[p] || '';
                return out;
            }

            function buildSelector(el) {
                if (el.id) return '#' + CSS.escape(el.id);
                const parent = el.parentElement;
                if (!parent) return el.tagName.toLowerCase();
                const siblings = parent.querySelectorAll(':scope > ' + el.tagName.toLowerCase());
                let idx = 0;
                for (let i = 0; i < siblings.length; i++) {
                    if (siblings[i] === el) { idx = i; break; }
                }
                const parentSel = parent.id ? '#' + CSS.escape(parent.id) :
                    parent.tagName.toLowerCase();
                return parentSel + ' > ' + el.tagName.toLowerCase() + ':nth-of-type(' + (idx + 1) + ')';
            }

            // Root element
            const rootRect = root.getBoundingClientRect();
            if (rootRect.width > 0 && rootRect.height > 0) {
                const cn = (typeof root.className === 'string') ? root.className : (root.className?.baseVal || '');
                results.push({
                    isRoot: true,
                    selector: rootSel,
                    displaySelector: rootSel,
                    text: (root.textContent || '').replace(/\\s+/g, ' ').trim().substring(0, 30),
                    tag: root.tagName.toLowerCase(),
                    resting: readStyles(root),
                    transition: window.getComputedStyle(root).transition || 'none',
                });
            }

            // Interactive children (buttons, links, inputs)
            const interactiveEls = root.querySelectorAll(
                'button, a[href], [role="button"], input, textarea, select, [tabindex]:not([tabindex="-1"])'
            );
            let count = 0;
            for (const el of interactiveEls) {
                if (count >= 10) break;
                const rect = el.getBoundingClientRect();
                if (rect.width < 5 || rect.height < 5) continue;
                if (rect.top < -200 || rect.top > window.innerHeight + 500) continue;

                const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                results.push({
                    isRoot: false,
                    selector: buildSelector(el),
                    displaySelector: el.id ? '#' + el.id : (cn.split(/\\s+/)[0] ? '.' + cn.split(/\\s+/)[0] : el.tagName.toLowerCase()),
                    text: (el.textContent || '').replace(/\\s+/g, ' ').trim().substring(0, 30),
                    tag: el.tagName.toLowerCase(),
                    resting: readStyles(el),
                    transition: window.getComputedStyle(el).transition || 'none',
                });
                count++;
            }

            return results;
        }''', {'rootSel': selector, 'stateProps': STATE_PROPERTIES})

        if not elements:
            return {'root': None, 'children': [], 'states_detected': 0}

        root_state = None
        child_states = []
        states_detected = 0

        for el in elements:
            sel = el['selector']
            hover_delta = {}
            focus_delta = {}

            try:
                locator = page.locator(sel).first
                if not await locator.is_visible(timeout=1000):
                    continue

                # --- HOVER ---
                try:
                    await locator.hover(timeout=2000)
                    await page.wait_for_timeout(150)

                    hover_styles = await page.evaluate('''(args) => {
                        const el = document.querySelector(args.sel);
                        if (!el) return null;
                        const s = window.getComputedStyle(el);
                        const out = {};
                        for (const p of args.props) out[p] = s[p] || '';
                        return out;
                    }''', {'sel': sel, 'props': STATE_PROPERTIES})

                    if hover_styles:
                        raw_delta = _compute_delta(el['resting'], hover_styles)
                        if raw_delta:
                            # Store actual CSS values, not just boolean markers
                            hover_delta = {prop: hover_styles[prop] for prop in raw_delta}
                            states_detected += 1
                except Exception as e:
                    logger.debug(f"Hover failed for {sel}: {str(e)[:60]}")

                # --- FOCUS ---
                try:
                    await page.mouse.move(0, 0)
                    await page.wait_for_timeout(100)
                    await locator.focus(timeout=2000)
                    await page.wait_for_timeout(100)

                    focus_styles = await page.evaluate('''(args) => {
                        const el = document.querySelector(args.sel);
                        if (!el) return null;
                        const s = window.getComputedStyle(el);
                        const out = {};
                        for (const p of args.props) out[p] = s[p] || '';
                        return out;
                    }''', {'sel': sel, 'props': STATE_PROPERTIES})

                    if focus_styles:
                        raw_delta = _compute_delta(el['resting'], focus_styles)
                        if raw_delta:
                            # Store actual CSS values, not just boolean markers
                            focus_delta = {prop: focus_styles[prop] for prop in raw_delta}
                            states_detected += 1

                    # Blur to reset
                    await page.evaluate('''(sel) => {
                        const el = document.querySelector(sel);
                        if (el && el.blur) el.blur();
                    }''', sel)
                except Exception as e:
                    logger.debug(f"Focus failed for {sel}: {str(e)[:60]}")

            except Exception as e:
                logger.debug(f"State capture failed for {sel}: {str(e)[:60]}")
                continue

            entry = {
                'selector': el['displaySelector'],
                'tag': el['tag'],
                'text': el['text'],
                'hover_delta': hover_delta,
                'focus_delta': focus_delta,
                'transition': el['transition'],
                'has_state_change': bool(hover_delta or focus_delta),
            }

            if el['isRoot']:
                root_state = entry
            else:
                child_states.append(entry)

        # Reset hover state
        try:
            await page.mouse.move(0, 0)
        except Exception:
            pass

        logger.info(f"Component state capture: {states_detected} state changes across {len(elements)} elements")

        return {
            'root': root_state,
            'children': child_states,
            'states_detected': states_detected,
        }

    def _attach_figma_output(self, blueprint: Dict):
        """Generate Figma-compatible markdown and attach to blueprint."""
        try:
            from component_translator import TailwindTranslator, generate_figma_markdown
            translator = TailwindTranslator()
            states = blueprint.get('interactive_states', {})
            blueprint['figma_markdown'] = generate_figma_markdown(blueprint, states, translator)
        except Exception as e:
            import traceback
            logging.getLogger(__name__).error(f"Figma output failed: {traceback.format_exc()}")
            blueprint['figma_markdown'] = f'<!-- Figma output generation failed: {e} -->'

    async def discover_components(self, page=None):
        """
        Discover ALL visible components on a page and return a visual inventory.
        Unlike _rip_page_sections (which picks the best per category), this returns
        every meaningful section with bounding boxes, labels, and content previews.

        Returns a list of component descriptors, each with:
        - selector: CSS selector to target this component
        - label: Human-readable name (e.g. "Navigation Bar", "12-Item Content Grid")
        - category: Semantic category (navigation, hero, content_grid, section, footer, etc.)
        - bounds: {top, left, width, height} bounding box
        - score: Relevance score
        - preview: Content summary (text snippet, child count, image count)
        - rippable: Whether this can be passed to the targeted ripper
        """
        close_browser = False
        if page is None:
            from patchright.async_api import async_playwright
            self._pw = await async_playwright().start()
            browser = await self._pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = await context.new_page()
            page.set_default_timeout(60000)
            await page.goto(self.url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            close_browser = True

        try:
            from component_discovery_js import COMPONENT_DISCOVERY_JS
            components = await page.evaluate(COMPONENT_DISCOVERY_JS)

            component_list = components.get('components', [])
            viewport = components.get('viewport', {'width': 1920, 'height': 1080})

            # Take element screenshots for each component (max 15 to avoid timeout)
            for comp in component_list[:15]:
                try:
                    el = await page.query_selector(comp['selector'])
                    if el:
                        screenshot_bytes = await el.screenshot(timeout=5000)
                        import base64
                        comp['screenshot'] = base64.b64encode(screenshot_bytes).decode('utf-8')
                    else:
                        comp['screenshot'] = None
                except Exception:
                    comp['screenshot'] = None

            # Generate plain-language summary
            categories = {}
            for comp in component_list:
                cat = comp['category']
                if cat not in categories:
                    categories[cat] = 0
                categories[cat] += 1

            summary_parts = []
            cat_labels = {
                'navigation': 'navigation bar',
                'hero': 'hero section',
                'content_grid': 'content grid',
                'footer': 'footer',
                'section': 'content section',
                'sidebar': 'sidebar',
                'form': 'form',
                'media': 'media player',
                'block': 'content block'
            }
            for cat, count in categories.items():
                label = cat_labels.get(cat, cat)
                if count > 1:
                    summary_parts.append(f"{count} {label}s")
                else:
                    summary_parts.append(f"1 {label}")

            summary = f"Found {len(component_list)} components: " + ", ".join(summary_parts)

            return {
                'components': component_list,
                'viewport': viewport,
                'summary': summary,
                'total': len(component_list)
            }

        finally:
            if close_browser:
                await page.context.browser.close()
                await self._pw.stop()

    async def _rip_page_sections(self, page):
        """
        Auto-detect high-value page components using scoring heuristics.
        Scans all candidates, scores them, picks the best per category,
        then runs full forensics on each winner.
        """
        print(f"\n   🔍 Auto-detecting high-value components...")

        # Phase 1: Single evaluate to scan ALL candidate elements and score them
        candidates = await page.evaluate('''() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const results = [];

            function score(el, tag, cls, id) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return null;
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return null;

                const links = el.querySelectorAll('a').length;
                const buttons = el.querySelectorAll('button').length;
                const imgs = el.querySelectorAll('img, svg, picture').length;
                const inputs = el.querySelectorAll('input, textarea').length;
                const hasNav = el.querySelector('nav') !== null || el.getAttribute('role') === 'navigation';
                const hasForm = el.querySelector('form') !== null;
                const widthPct = rect.width / vw;
                const text = (el.textContent || '').toLowerCase();

                // Build a unique CSS selector for this element
                let sel = tag;
                if (id) sel = '#' + CSS.escape(id);
                else if (cls) {
                    const firstClass = cls.split(/\\s+/)[0];
                    if (firstClass) sel = tag + '.' + CSS.escape(firstClass);
                }

                return {
                    sel,
                    tag,
                    id: id || null,
                    className: cls.substring(0, 60),
                    rect: { top: Math.round(rect.top), left: Math.round(rect.left),
                            width: Math.round(rect.width), height: Math.round(rect.height) },
                    position: s.position,
                    links, buttons, imgs, inputs,
                    hasNav, hasForm,
                    widthPct: Math.round(widthPct * 100),
                    children: el.children.length,
                    hasPlay: text.includes('play') || !!el.querySelector('[aria-label*="play" i], [class*="play"]'),
                    hasLive: text.includes('live') || !!el.querySelector('[class*="live"]'),
                    hasAudio: !!el.querySelector('audio, video, [class*="player"]'),
                    textLen: text.length
                };
            }

            // Scan header candidates
            document.querySelectorAll('header, nav, [role="navigation"], [role="banner"]').forEach(el => {
                const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const r = score(el, el.tagName.toLowerCase(), cn, el.id);
                if (r) { r.category = 'navigation'; results.push(r); }
            });

            // Scan hero candidates
            document.querySelectorAll('section, [class*="hero"], [class*="banner"], [class*="jumbotron"]').forEach(el => {
                const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const rect = el.getBoundingClientRect();
                if (rect.top < vh && rect.height > vh * 0.3) {
                    const r = score(el, el.tagName.toLowerCase(), cn, el.id);
                    if (r) { r.category = 'hero'; results.push(r); }
                }
            });

            // Scan player/media candidates
            document.querySelectorAll('[class*="player"], [class*="live"], [id*="player"], [id*="live"], [class*="audio"], [class*="video"]').forEach(el => {
                const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const r = score(el, el.tagName.toLowerCase(), cn, el.id);
                if (r) { r.category = 'player'; results.push(r); }
            });

            // Scan footer
            document.querySelectorAll('footer, [role="contentinfo"]').forEach(el => {
                const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
                const r = score(el, el.tagName.toLowerCase(), cn, el.id);
                if (r) { r.category = 'footer'; results.push(r); }
            });

            // Scan content grid: find containers with 3+ structurally similar children
            const main = document.querySelector('main') || document.querySelector('[role="main"]') ||
                         document.querySelector('#content') || document.querySelector('.content') || document.body;
            const allContainers = main.querySelectorAll('*');
            let bestGrid = null;
            for (const container of allContainers) {
                const kids = Array.from(container.children).filter(c => {
                    const cr = c.getBoundingClientRect();
                    return cr.width > 50 && cr.height > 20;
                });
                if (kids.length < 3) continue;

                // Find same-tag groups
                const groups = {};
                for (const kid of kids) {
                    const kt = kid.tagName;
                    if (!groups[kt]) groups[kt] = [];
                    groups[kt].push(kid);
                }
                for (const [kt, group] of Object.entries(groups)) {
                    if (group.length < 3) continue;

                    // Check structural similarity
                    const sig = (el) => {
                        const ct = Array.from(el.children).map(c => c.tagName).sort().join(',');
                        return `${ct}|${!!el.querySelector('img')}|${!!el.querySelector('a')}`;
                    };
                    const ref = sig(group[0]);
                    const matching = group.filter(el => sig(el) === ref);
                    if (matching.length < 3) continue;

                    if (!bestGrid || matching.length > bestGrid.matchCount) {
                        const cn2 = (typeof container.className === 'string') ? container.className : (container.className?.baseVal || '');
                        const r = score(container, container.tagName.toLowerCase(), cn2, container.id);
                        if (r) {
                            r.category = 'content_grid';
                            r.matchCount = matching.length;
                            r.itemTag = kt.toLowerCase();
                            r.hasItemImages = !!matching[0].querySelector('img, picture, video');
                            r.hasItemHeadings = !!matching[0].querySelector('h1, h2, h3, h4');
                            r.hasItemLinks = !!matching[0].querySelector('a');
                            bestGrid = r;
                        }
                    }
                }
            }
            if (bestGrid) results.push(bestGrid);

            return { candidates: results, vh };
        }''')

        # Extract viewport height and candidate list
        vh = candidates.get('vh', 800) if isinstance(candidates, dict) else 800
        candidates = candidates.get('candidates', []) if isinstance(candidates, dict) else candidates

        # Phase 2: Score and pick best per category
        scored = {}
        for c in candidates:
            cat = c['category']
            s = 0

            if cat == 'navigation':
                # Main nav: most links, widest, near top, fixed/sticky, contains <nav>
                s += c['links'] * 10                                 # more links = more nav-like
                s += 50 if c['widthPct'] > 80 else 0                # full width
                s += 40 if c['rect']['top'] < 100 else 0            # near top
                s += 30 if c['position'] in ('fixed', 'sticky') else 0
                s += 20 if c['hasNav'] else 0
                s -= 100 if c['links'] == 0 else 0                  # no links = not a nav
                s -= 50 if c['widthPct'] < 50 else 0                # narrow = section header

            elif cat == 'hero':
                s += c['rect']['height'] // 5                       # taller = more hero-like
                s += 30 if c['imgs'] > 0 else 0                     # has imagery
                s += 20 if c['buttons'] > 0 else 0                  # has CTA
                s += 50 if c['rect']['top'] < 200 else 0            # near top
                s -= 50 if c['links'] > 20 else 0                   # too many links = nav, not hero

            elif cat == 'player':
                s += 80 if c['hasPlay'] else 0
                s += 60 if c['hasLive'] else 0
                s += 60 if c['hasAudio'] else 0
                s += 30 if c['buttons'] >= 2 else 0
                s += 20 if c['widthPct'] > 60 else 0
                s -= 100 if c['textLen'] > 5000 else 0              # too much text = not a player
                # Penalize root-level elements (html, body) — they're never a "player"
                s -= 500 if c['tag'] in ('html', 'body') else 0

            elif cat == 'content_grid':
                match_count = c.get('matchCount', 0)
                s += match_count * 5                                 # more items = stronger signal
                s += 30 if c.get('hasItemImages') else 0             # visual grid
                s += 20 if c.get('hasItemHeadings') else 0           # editorial content
                s += 20 if c.get('hasItemLinks') else 0              # navigable items
                s += 30 if c['widthPct'] > 60 else 0                # takes up most of the page
                s -= 50 if c['tag'] in ('html', 'body') else 0      # avoid root

            elif cat == 'footer':
                s += 50 if c['tag'] == 'footer' else 0
                s += c['links'] * 2
                s += 30 if c['rect']['top'] > vh else 0             # below fold

            c['score'] = s
            if cat not in scored or s > scored[cat]['score']:
                scored[cat] = c

        # Phase 3: Run full forensics on each winner
        sections = {}
        for cat, winner in scored.items():
            if winner['score'] <= 0:
                continue
            sel = winner['sel']
            try:
                blueprint = await self._rip_component(page, sel)
                blueprint['code'] = self._generate_component_code(blueprint)
                blueprint['markdown'] = self._generate_markdown_doc(blueprint, cat)
                blueprint['auto_detected'] = {
                    'selector': sel,
                    'score': winner['score'],
                    'signals': {
                        'links': winner['links'],
                        'buttons': winner['buttons'],
                        'width_pct': winner['widthPct'],
                        'position': winner['position'],
                        'has_nav': winner['hasNav'],
                        'has_play': winner['hasPlay'],
                        'has_live': winner['hasLive']
                    }
                }
                sections[cat] = blueprint
                print(f"   ✅ {cat}: {sel} (score: {winner['score']})")
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Auto-detect rip failed for {cat} ({sel}): {e}")
                continue

        return sections

    def _generate_component_code(self, blueprint: Dict) -> Dict[str, str]:
        """
        Generate React + Tailwind code from blueprint
        """
        code = {}

        # CSS code (vanilla)
        css_rules = []
        if 'boxModel' in blueprint:
            bm = blueprint['boxModel']
            if bm.get('display'):
                css_rules.append(f"  display: {bm['display']};")
            if bm.get('padding') and bm['padding'] != '0px':
                css_rules.append(f"  padding: {bm['padding']};")
            if bm.get('margin') and bm['margin'] != '0px':
                css_rules.append(f"  margin: {bm['margin']};")

        if 'layout' in blueprint and blueprint['layout']:
            layout = blueprint['layout']
            if layout.get('type') == 'grid':
                css_rules.append(f"  display: grid;")
                css_rules.append(f"  grid-template-columns: {layout.get('columns', 'repeat(auto-fit, minmax(250px, 1fr)')};")
                if layout.get('gap'):
                    css_rules.append(f"  gap: {layout['gap']};")
            elif layout.get('type') == 'flexbox':
                css_rules.append(f"  display: flex;")
                css_rules.append(f"  flex-direction: {layout.get('direction', 'row')};")
                if layout.get('gap'):
                    css_rules.append(f"  gap: {layout['gap']};")
                if layout.get('justify'):
                    css_rules.append(f"  justify-content: {layout['justify']};")

        code['css'] = '.component {\n' + '\n'.join(css_rules) + '\n}'

        # Tailwind code
        tailwind_classes = []
        if 'boxModel' in blueprint:
            bm = blueprint['boxModel']
            # Convert padding
            if bm.get('padding'):
                p = bm['padding'].replace('px', '').split()
                if len(p) == 1:
                    tailwind_classes.append(f"p-[{p[0]}px]")
                elif len(p) == 2:
                    tailwind_classes.append(f"py-[{p[0]}px] px-[{p[1]}px]")

        if 'layout' in blueprint and blueprint['layout']:
            layout = blueprint['layout']
            if layout.get('type') == 'grid':
                # Approximate grid columns
                cols = layout.get('columns', '')
                if 'repeat' in cols:
                    tailwind_classes.append('grid grid-cols-auto-fit')
                else:
                    count = len(cols.split()) if cols else 4
                    tailwind_classes.append(f'grid grid-cols-{min(count, 12)}')

                # Gap
                gap = layout.get('gap', '0px').replace('px', '')
                if gap and gap != '0':
                    tailwind_classes.append(f'gap-[{gap}px]')

            elif layout.get('type') == 'flexbox':
                tailwind_classes.append('flex')
                direction = layout.get('direction', 'row')
                if direction == 'column':
                    tailwind_classes.append('flex-col')

                # Gap
                gap = layout.get('gap', '0px').replace('px', '')
                if gap and gap != '0':
                    tailwind_classes.append(f'gap-[{gap}px]')

        code['tailwind'] = ' '.join(tailwind_classes)

        # React component
        component_name = blueprint.get('selector', '.component').replace('.', '').replace('-', '_').title().replace('_', '')

        react_code = f'''const {component_name} = () => {{
  return (
    <div className="{code['tailwind']}">
      {{/* Component content here */}}
    </div>
  );
}};

export default {component_name};'''

        code['react'] = react_code

        return code

    async def _extract_tailwind_classes(self, page, selector: str) -> Dict:
        """
        Extract and categorize ALL Tailwind classes from component
        Includes hover, focus, active, and responsive variants
        """
        tailwind_data = await page.evaluate(f'''(selector) => {{
            const element = document.querySelector(selector);
            if (!element) return {{found: false}};

            // Get all elements including root
            const allElements = [element, ...element.querySelectorAll('*')];
            const allClasses = [];

            allElements.forEach(el => {{
                if (el.className && typeof el.className === 'string') {{
                    el.className.split(' ').forEach(c => {{
                        if (c.trim()) allClasses.push(c.trim());
                    }});
                }}
            }});

            // Remove duplicates
            const uniqueClasses = [...new Set(allClasses)];

            // Categorize Tailwind classes
            const categories = {{
                // Layout
                display: uniqueClasses.filter(c => /^(flex|grid|block|inline|hidden)/.test(c)),
                flexbox: uniqueClasses.filter(c => /^(flex-|items-|justify-|self-|gap-)/.test(c)),
                grid: uniqueClasses.filter(c => /^(grid-|col-|row-)/.test(c)),

                // Spacing
                padding: uniqueClasses.filter(c => /^p[xytblr]?-/.test(c)),
                margin: uniqueClasses.filter(c => /^m[xytblr]?-/.test(c)),
                space: uniqueClasses.filter(c => /^space-[xy]-/.test(c)),

                // Sizing
                width: uniqueClasses.filter(c => /^w-/.test(c)),
                height: uniqueClasses.filter(c => /^h-/.test(c)),
                minMax: uniqueClasses.filter(c => /^(min|max)-(w|h)-/.test(c)),

                // Colors
                background: uniqueClasses.filter(c => /^bg-/.test(c)),
                text: uniqueClasses.filter(c => /^text-(white|black|gray|red|blue|green|yellow|purple|pink|indigo|emerald|cyan|amber|orange|lime|teal|sky|violet|fuchsia|rose)-/.test(c)),
                border: uniqueClasses.filter(c => /^border-(white|black|gray|red|blue|green|yellow|purple|pink|indigo|emerald|cyan|amber|orange|lime|teal|sky|violet|fuchsia|rose)-/.test(c)),

                // Typography
                fontSize: uniqueClasses.filter(c => /^text-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)/.test(c)),
                fontWeight: uniqueClasses.filter(c => /^font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)/.test(c)),
                textAlign: uniqueClasses.filter(c => /^text-(left|center|right|justify)/.test(c)),

                // Borders & Radius
                borderWidth: uniqueClasses.filter(c => /^border(-[0-9])?$/.test(c)),
                borderRadius: uniqueClasses.filter(c => /^rounded/.test(c)),

                // Effects
                shadow: uniqueClasses.filter(c => /^shadow/.test(c)),
                opacity: uniqueClasses.filter(c => /^opacity-/.test(c)),

                // Interactive States
                hover: uniqueClasses.filter(c => c.startsWith('hover:')),
                focus: uniqueClasses.filter(c => c.startsWith('focus:')),
                active: uniqueClasses.filter(c => c.startsWith('active:')),
                disabled: uniqueClasses.filter(c => c.startsWith('disabled:')),

                // Responsive
                sm: uniqueClasses.filter(c => c.startsWith('sm:')),
                md: uniqueClasses.filter(c => c.startsWith('md:')),
                lg: uniqueClasses.filter(c => c.startsWith('lg:')),
                xl: uniqueClasses.filter(c => c.startsWith('xl:')),
                '2xl': uniqueClasses.filter(c => c.startsWith('2xl:')),

                // Transitions
                transition: uniqueClasses.filter(c => /^transition/.test(c)),
                duration: uniqueClasses.filter(c => /^duration-/.test(c)),
                ease: uniqueClasses.filter(c => /^ease-/.test(c)),

                // Position
                position: uniqueClasses.filter(c => /^(static|fixed|absolute|relative|sticky)$/.test(c)),
                zIndex: uniqueClasses.filter(c => /^z-/.test(c)),

                // Other utilities
                other: []
            }};

            // Categorize remaining classes as "other"
            const categorized = Object.values(categories).flat();
            categories.other = uniqueClasses.filter(c => !categorized.includes(c));

            return {{
                found: true,
                total: uniqueClasses.length,
                allClasses: uniqueClasses,
                categories: categories,
                isTailwind: uniqueClasses.some(c =>
                    /^(flex|grid|p-|m-|w-|h-|text-|bg-|border-|rounded-|shadow-)/.test(c)
                )
            }};
        }}''', selector)

        return tailwind_data

    async def _detect_javascript_behavior(self, page, selector: str) -> Dict:
        """
        Detect JavaScript behaviors and interactive patterns
        Returns warnings about required JavaScript and detected patterns
        """
        js_detection = await page.evaluate(f'''(selector) => {{
            const element = document.querySelector(selector);
            if (!element) return {{found: false}};

            const behaviors = {{
                hasClickHandlers: false,
                hasDataAttributes: false,
                hasARIAControls: false,
                hasFormHandlers: false,
                hasAnimationTriggers: false,
                interactiveElements: [],
                detectedPatterns: []
            }};

            // Check for click handlers and interactive elements
            const clickables = element.querySelectorAll('a, button, [onclick], [role="button"]');
            clickables.forEach(el => {{
                const tag = el.tagName.toLowerCase();
                const text = el.textContent.trim().substring(0, 30);
                const role = el.getAttribute('role');
                const ariaExpanded = el.getAttribute('aria-expanded');
                const ariaControls = el.getAttribute('aria-controls');

                behaviors.interactiveElements.push({{
                    tag,
                    text,
                    hasOnclick: el.onclick !== null,
                    role,
                    ariaExpanded,
                    ariaControls
                }});

                if (el.onclick) behaviors.hasClickHandlers = true;
                if (ariaControls || ariaExpanded) behaviors.hasARIAControls = true;
            }});

            // Check for data attributes suggesting JS behavior
            const dataToggle = element.querySelectorAll('[data-toggle], [data-target], [data-dismiss]');
            if (dataToggle.length > 0) {{
                behaviors.hasDataAttributes = true;
                dataToggle.forEach(el => {{
                    const toggle = el.getAttribute('data-toggle');
                    if (toggle) behaviors.detectedPatterns.push(toggle);
                }});
            }}

            // Check for form handlers
            const forms = element.querySelectorAll('form');
            if (forms.length > 0) {{
                behaviors.hasFormHandlers = true;
                behaviors.detectedPatterns.push('form-submission');
            }}

            // Detect common UI patterns
            const dropdownIndicators = element.querySelectorAll('[aria-expanded], .dropdown, [class*="dropdown"]');
            if (dropdownIndicators.length > 0) behaviors.detectedPatterns.push('dropdown');

            const modalTriggers = element.querySelectorAll('[data-toggle="modal"], [data-bs-toggle="modal"], .modal-trigger');
            if (modalTriggers.length > 0) behaviors.detectedPatterns.push('modal');

            const tabs = element.querySelectorAll('[role="tab"], [data-toggle="tab"], .tab');
            if (tabs.length > 0) behaviors.detectedPatterns.push('tabs');

            const accordions = element.querySelectorAll('[role="button"][aria-expanded], .accordion, [class*="accordion"]');
            if (accordions.length > 0) behaviors.detectedPatterns.push('accordion');

            const carousel = element.querySelectorAll('[data-slide], [class*="carousel"], [class*="slider"]');
            if (carousel.length > 0) behaviors.detectedPatterns.push('carousel/slider');

            const hamburger = element.querySelectorAll('.hamburger, [aria-label*="menu"], [class*="menu-toggle"]');
            if (hamburger.length > 0) behaviors.detectedPatterns.push('mobile-menu-toggle');

            // Check for scroll triggers or lazy loading
            const lazyLoad = element.querySelectorAll('[data-src], [loading="lazy"], .lazy');
            if (lazyLoad.length > 0) {{
                behaviors.hasAnimationTriggers = true;
                behaviors.detectedPatterns.push('lazy-loading');
            }}

            // Determine if JavaScript is required
            const requiresJS =
                behaviors.hasClickHandlers ||
                behaviors.hasDataAttributes ||
                behaviors.hasARIAControls ||
                behaviors.detectedPatterns.length > 0;

            return {{
                found: true,
                requiresJavaScript: requiresJS,
                behaviors,
                summary: {{
                    totalInteractive: behaviors.interactiveElements.length,
                    patterns: [...new Set(behaviors.detectedPatterns)],
                    hasEventHandlers: behaviors.hasClickHandlers
                }}
            }};
        }}''', selector)

        return js_detection

    async def _get_semantic_name(self, page, selector: str) -> str:
        """
        Get semantic name for component instead of generic "DIV"
        Examples: "Navigation Bar", "Article Card", "Hero Section"
        """
        semantic_name = await page.evaluate(f'''(selector) => {{
            const element = document.querySelector(selector);
            if (!element) return selector;

            const tag = element.tagName.toLowerCase();
            const role = element.getAttribute('role');
            const ariaLabel = element.getAttribute('aria-label');
            const classList = Array.from(element.classList).join(' ');

            // Semantic HTML tags
            if (tag === 'nav') return 'Navigation Bar';
            if (tag === 'header') return 'Header';
            if (tag === 'footer') return 'Footer';
            if (tag === 'aside') return 'Sidebar';
            if (tag === 'article') return 'Article Card';
            if (tag === 'section') return 'Section';
            if (tag === 'main') return 'Main Content';
            if (tag === 'form') return 'Form';

            // ARIA roles
            if (role === 'navigation') return 'Navigation';
            if (role === 'banner') return 'Banner';
            if (role === 'contentinfo') return 'Footer';
            if (role === 'complementary') return 'Sidebar';
            if (role === 'search') return 'Search';
            if (role === 'button') return 'Button Group';

            // Class-based detection
            if (classList.match(/hero|banner|jumbotron/i)) return 'Hero Section';
            if (classList.match(/nav|menu|navigation/i)) return 'Navigation';
            if (classList.match(/card|product/i)) return 'Card Component';
            if (classList.match(/grid|gallery/i)) return 'Grid Layout';
            if (classList.match(/modal|dialog/i)) return 'Modal';
            if (classList.match(/dropdown|submenu/i)) return 'Dropdown Menu';
            if (classList.match(/carousel|slider/i)) return 'Carousel';
            if (classList.match(/sidebar|aside/i)) return 'Sidebar';
            if (classList.match(/header|masthead/i)) return 'Header';
            if (classList.match(/footer/i)) return 'Footer';

            // ARIA labels
            if (ariaLabel) {{
                return ariaLabel.charAt(0).toUpperCase() + ariaLabel.slice(1);
            }}

            // Fallback to tag
            return tag.toUpperCase() + ' Element';
        }}''', selector)

        return semantic_name

    def _generate_markdown_doc(self, blueprint: Dict, component_name: str) -> str:
        """
        Generate Markdown documentation for the component
        Human and LLM readable format
        """
        md = f"# {component_name.title()} Component\n\n"

        # Metadata
        if 'metadata' in blueprint:
            meta = blueprint['metadata']
            md += f"**Source:** {meta.get('url', 'N/A')}  \n"
            md += f"**Selector:** `{meta.get('selector', 'N/A')}`  \n"
            md += f"**Extracted:** {meta.get('extracted_at', 'N/A')[:10]}  \n\n"

        md += "---\n\n"

        # JavaScript Warning
        if blueprint.get('javascript', {}).get('requiresJavaScript'):
            js = blueprint['javascript']
            patterns = js.get('summary', {}).get('patterns', [])
            md += "## ⚠️ Interactive Behavior\n\n"
            md += "**This component requires JavaScript for full functionality.**\n\n"
            if patterns:
                md += f"**Detected patterns:** {', '.join(patterns)}\n\n"
            md += "The code below provides structure and styling only. You'll need to implement:\n"
            md += "- Event handlers for user interactions\n"
            md += "- State management for dynamic content\n"
            md += "- Animation/transition logic\n\n"
            md += "---\n\n"

        # Structure
        md += "## Structure\n\n"
        if 'selector' in blueprint:
            md += f"**Element:** `{blueprint['selector']}`\n\n"
        if 'layout' in blueprint and blueprint['layout']:
            layout = blueprint['layout']
            md += f"**Layout Type:** {layout.get('type', 'unknown').title()}\n\n"
            if layout.get('type') == 'flexbox':
                md += f"- Direction: {layout.get('direction', 'row')}\n"
                if layout.get('justify'):
                    md += f"- Justify: {layout['justify']}\n"
                if layout.get('align'):
                    md += f"- Align: {layout['align']}\n"
            elif layout.get('type') == 'grid':
                md += f"- Columns: {layout.get('columns', 'auto')}\n"
            if layout.get('gap'):
                md += f"- Gap: {layout['gap']}\n"
            md += "\n"

        # Component Anatomy
        if blueprint.get('anatomy') and not blueprint['anatomy'].get('error'):
            anatomy_md = self._generate_anatomy_doc(blueprint['anatomy'])
            if anatomy_md:
                md += anatomy_md + "\n"

        # Tailwind Classes
        if blueprint.get('tailwind', {}).get('isTailwind'):
            tw = blueprint['tailwind']
            md += "## 🎨 Tailwind Classes\n\n"
            md += f"**Total:** {tw.get('total', 0)} classes\n\n"
            md += "```\n"
            md += " ".join(tw.get('allClasses', []))
            md += "\n```\n\n"

            # Categorized
            cats = tw.get('categories', {})
            if cats.get('hover'):
                md += f"**Hover states:** `{' '.join(cats['hover'][:5])}`\n\n"
            if cats.get('sm') or cats.get('md') or cats.get('lg'):
                responsive = cats.get('sm', []) + cats.get('md', []) + cats.get('lg', [])
                md += f"**Responsive:** `{' '.join(responsive[:5])}`\n\n"

        # CSS Code
        if blueprint.get('code', {}).get('css'):
            md += "## CSS\n\n"
            md += "```css\n"
            md += blueprint['code']['css']
            md += "\n```\n\n"

        # React Component
        if blueprint.get('code', {}).get('react'):
            md += "## React Component\n\n"
            md += "```jsx\n"
            md += blueprint['code']['react']
            md += "\n```\n\n"

        # Portability Notes
        if blueprint.get('portability'):
            port = blueprint['portability']
            if port.get('blockers'):
                md += "## ⚠️ Portability Notes\n\n"
                for blocker in port['blockers'][:3]:
                    md += f"- {blocker}\n"
                md += "\n"

        md += "---\n\n"
        md += "_Generated by Web Intelligence Scraper Component Ripper_\n"

        return md

    def _analyze_portability(self, blueprint: Dict) -> Dict:
        """
        Analyze component portability - what's needed to reuse this elsewhere

        Addresses LLM feedback: "Component Ripper extracts code that won't work on other sites"

        Returns portability report with:
        - Reusability score (0-100)
        - Dependencies detected
        - What needs to be recreated
        - Recommendations for Claude
        """
        portability = {
            'reusability_score': 100,  # Start optimistic
            'blockers': [],
            'dependencies': {
                'css_variables': [],
                'external_fonts': [],
                'framework_specifics': [],
                'absolute_units': False
            },
            'recommendations': [],
            'difficulty': 'easy'  # easy, medium, hard
        }

        computed = blueprint.get('computedStyles', {})
        source_css = blueprint.get('source', {}).get('matchingCSSRules', [])
        framework = blueprint.get('frameworkHints', {})

        # Check for CSS custom properties (var(--*))
        css_vars = set()
        for rule in source_css:
            css_text = rule.get('css', '')
            import re
            vars_found = re.findall(r'var\((--[\w-]+)\)', css_text)
            css_vars.update(vars_found)

        if css_vars:
            portability['dependencies']['css_variables'] = list(css_vars)
            portability['reusability_score'] -= 20
            portability['blockers'].append(f"{len(css_vars)} CSS custom properties need to be defined")
            portability['recommendations'].append(
                f"Define these CSS variables in your stylesheet: {', '.join(list(css_vars)[:3])}..."
            )

        # Check for external fonts
        font_family = computed.get('font-family', '')
        common_system_fonts = ['Arial', 'Helvetica', 'Times', 'Courier', 'Verdana', 'Georgia', 'sans-serif', 'serif', 'monospace']
        if font_family and not any(sys_font in font_family for sys_font in common_system_fonts):
            portability['dependencies']['external_fonts'].append(font_family)
            portability['reusability_score'] -= 10
            portability['recommendations'].append(
                f"Load font: {font_family.split(',')[0].strip()}"
            )

        # Check for framework-specific requirements
        if framework.get('react'):
            portability['dependencies']['framework_specifics'].append('React')
            portability['recommendations'].append("This is a React component - use in React app")

        if framework.get('tailwind'):
            portability['dependencies']['framework_specifics'].append('Tailwind CSS')
            portability['reusability_score'] -= 15
            portability['blockers'].append("Uses Tailwind utility classes")
            portability['recommendations'].append(
                "Install Tailwind CSS and configure tailwind.config.js with matching theme"
            )

        if framework.get('cssInJS'):
            portability['dependencies']['framework_specifics'].append('CSS-in-JS')
            portability['reusability_score'] -= 25
            portability['blockers'].append("Uses CSS-in-JS (styled-components/emotion)")
            portability['recommendations'].append(
                "Extract computed styles instead of source code for CSS-in-JS components"
            )

        # Check for absolute positioning (harder to reuse)
        position = computed.get('position', '')
        if position in ['absolute', 'fixed']:
            portability['reusability_score'] -= 10
            portability['recommendations'].append(
                f"Component uses {position} positioning - may need layout adjustments"
            )

        # Check for viewport units (context-dependent)
        for prop, value in computed.items():
            if isinstance(value, str) and ('vw' in value or 'vh' in value):
                portability['dependencies']['absolute_units'] = True
                portability['reusability_score'] -= 5
                portability['recommendations'].append(
                    "Uses viewport units (vw/vh) - appearance depends on screen size"
                )
                break

        # Calculate difficulty
        score = portability['reusability_score']
        if score >= 80:
            portability['difficulty'] = 'easy'
            portability['summary'] = "✅ Highly portable - minimal dependencies"
        elif score >= 60:
            portability['difficulty'] = 'medium'
            portability['summary'] = "⚠️ Moderately portable - some dependencies to recreate"
        else:
            portability['difficulty'] = 'hard'
            portability['summary'] = "❌ Low portability - significant framework/dependency requirements"

        # Add Claude-specific guidance
        if portability['reusability_score'] < 70:
            portability['claude_guidance'] = {
                'approach': 'Use computed styles instead of source code',
                'reasoning': 'Source code has dependencies that won\'t work elsewhere',
                'workflow': [
                    '1. Extract computed styles (already included in blueprint.computedStyles)',
                    '2. Create new component with same visual properties',
                    '3. Recreate dependencies listed above',
                    '4. Test in target environment'
                ]
            }
        else:
            portability['claude_guidance'] = {
                'approach': 'Source code can be reused with minor adjustments',
                'reasoning': 'Few dependencies detected',
                'workflow': [
                    '1. Copy HTML structure from blueprint.source.sourceHTML',
                    '2. Copy CSS from blueprint.source.matchingCSSRules',
                    '3. Add any missing dependencies listed above',
                    '4. Test in target environment'
                ]
            }

        return portability

    # ── Component Anatomy Processing ──────────────────────────────────

    def _extract_component_anatomy(self, raw: Dict) -> Dict:
        """
        Transform raw child traversal data into structured anatomy:
        layout system, spatial zones, role-grouped elements.
        """
        parent = raw.get('parent', {})
        children = raw.get('children', [])

        if not children:
            return {'layout_system': {}, 'zones': [], 'child_summary': {'total': 0, 'by_tag': {}, 'by_role': {}}}

        # 1. Detect parent layout system
        layout_system = self._classify_layout_system(parent)

        # 2. Classify each child by functional role
        parent_width = parent.get('width', 1280)
        classified = []
        for child in children:
            role = self._classify_child_role(child, parent_width)
            summary = self._summarize_child(child)
            summary['role'] = role
            classified.append(summary)

        # 3. Group into spatial zones (left / center / right)
        zones = self._detect_zones(classified, parent_width)

        # 4. Build summary counts
        tag_counts = {}
        role_counts = {}
        for c in classified:
            tag_counts[c['tag']] = tag_counts.get(c['tag'], 0) + 1
            role_counts[c['role']] = role_counts.get(c['role'], 0) + 1

        return {
            'layout_system': layout_system,
            'zones': zones,
            'child_summary': {
                'total': len(classified),
                'by_tag': tag_counts,
                'by_role': role_counts
            }
        }

    def _classify_layout_system(self, parent: Dict) -> Dict:
        """Determine the layout type from parent computed styles."""
        display = parent.get('display', 'block')
        result = {'type': 'block', 'direction': None, 'justify': None, 'align': None, 'gap': None}

        if 'flex' in display:
            result['type'] = 'flex'
            result['direction'] = parent.get('flexDirection', 'row')
            justify = parent.get('justifyContent', '')
            align = parent.get('alignItems', '')
            gap = parent.get('gap', '')
            if justify and justify != 'normal':
                result['justify'] = justify
            if align and align != 'normal':
                result['align'] = align
            if gap and gap != 'normal' and gap != '0px':
                result['gap'] = gap

        elif 'grid' in display:
            result['type'] = 'grid'
            cols = parent.get('gridTemplateColumns', '')
            if cols and cols != 'none':
                result['columns'] = cols
            gap = parent.get('gap', '')
            if gap and gap != 'normal' and gap != '0px':
                result['gap'] = gap

        return result

    def _classify_child_role(self, child: Dict, parent_width: int) -> str:
        """Assign a functional role to a child element."""
        tag = child.get('tag', '')
        href = child.get('href', '')
        src = child.get('src', '')
        text = child.get('text', '')
        role_attr = child.get('role', '') or ''
        aria = child.get('ariaLabel', '') or ''
        rect = child.get('rect', {})
        w = rect.get('width', 0)
        h = rect.get('height', 0)
        left = rect.get('left', 0)
        child_count = child.get('childCount', 0)
        styles = child.get('styles', {})
        display = styles.get('display', '')

        # Logo / branding: image or SVG near left, or link wrapping image
        if tag in ('img', 'svg', 'picture'):
            if left < parent_width * 0.3:
                return 'branding'
            return 'media'

        # Link wrapping an image child (common logo pattern)
        if tag == 'a' and src and left < parent_width * 0.3:
            return 'branding'

        # Navigation role explicitly set
        if role_attr == 'navigation' or tag == 'nav':
            return 'navigation_links'

        # Buttons and inputs
        if tag in ('button', 'input'):
            return 'action_elements'

        # Small icon-sized elements near the right edge
        if w > 0 and w <= 48 and h > 0 and h <= 48 and left > parent_width * 0.7:
            return 'action_elements'

        # Link clusters — an anchor with short text
        if tag == 'a' and len(text) < 30:
            return 'navigation_links'

        # Headings
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            return 'text_content'

        # Paragraphs / text blocks
        if tag in ('p', 'span', 'label') and text:
            return 'text_content'

        # Flex/grid containers with children — layout group
        if ('flex' in display or 'grid' in display) and child_count > 0:
            return 'layout_group'

        # List items — inherit role from children (common nav pattern: ul > li > a)
        if tag == 'li':
            children_data = child.get('children', [])
            has_link_child = any(c.get('tag') == 'a' for c in children_data)
            if has_link_child:
                return 'navigation_links'
            has_button_child = any(c.get('tag') in ('button', 'input') for c in children_data)
            if has_button_child:
                return 'action_elements'

        # Container divs with children
        if tag in ('div', 'section', 'ul', 'ol') and child_count > 0:
            return 'layout_group'

        # Search form
        if tag == 'form' or (role_attr == 'search') or ('search' in aria.lower()):
            return 'action_elements'

        return 'other'

    def _summarize_child(self, child: Dict) -> Dict:
        """Extract the meaningful subset of a child for the anatomy output."""
        styles = child.get('styles', {})
        rect = child.get('rect', {})

        # Build compact font string
        family = styles.get('fontFamily', '')
        # Extract first font name only
        if family:
            family = family.split(',')[0].strip().strip('"').strip("'")
        size = styles.get('fontSize', '')
        weight = styles.get('fontWeight', '')
        font_str = ', '.join(filter(None, [family, size, weight])) if family else ''

        # Filter out transparent/default backgrounds
        bg = styles.get('backgroundColor', '')
        if bg in ('rgba(0, 0, 0, 0)', 'transparent', ''):
            bg = None

        # Filter out default transitions
        transition = styles.get('transition', '') or ''
        default_transitions = ['all 0s ease 0s', 'none 0s ease 0s', 'none', '', 'all']
        if transition in default_transitions or transition.startswith('none'):
            transition = None

        summary = {
            'tag': child.get('tag', ''),
            'text': child.get('text', ''),
            'href': child.get('href'),
            'src': child.get('src'),
            'width': rect.get('width', 0),
            'height': rect.get('height', 0),
            'left': rect.get('left', 0),
            'top': rect.get('top', 0),
        }

        # Only include non-empty values
        if font_str:
            summary['font'] = font_str
        color = styles.get('color', '')
        if color:
            summary['color'] = color
        if bg:
            summary['background'] = bg
        border_radius = styles.get('borderRadius', '')
        if border_radius and border_radius != '0px':
            summary['borderRadius'] = border_radius
        if transition:
            summary['transition'] = transition

        # Include child anatomy if this is a layout group with children
        child_children = child.get('children', [])
        if child_children:
            summary['children'] = []
            for cc in child_children[:10]:
                sub_summary = self._summarize_child(cc)
                sub_summary['role'] = self._classify_child_role(cc, rect.get('width', 0) or 1)
                summary['children'].append(sub_summary)

        return summary

    def _detect_zones(self, classified: list, parent_width: int) -> list:
        """Group classified children into left/center/right spatial zones."""
        if parent_width <= 0:
            parent_width = 1280

        left_zone = []
        center_zone = []
        right_zone = []

        third = parent_width / 3

        for child in classified:
            center_x = child.get('left', 0) + child.get('width', 0) / 2
            if center_x < third:
                left_zone.append(child)
            elif center_x > third * 2:
                right_zone.append(child)
            else:
                center_zone.append(child)

        zones = []

        for position, elements in [('left', left_zone), ('center', center_zone), ('right', right_zone)]:
            if not elements:
                continue

            # Determine dominant role in this zone
            role_counts = {}
            for el in elements:
                r = el.get('role', 'other')
                role_counts[r] = role_counts.get(r, 0) + 1
            dominant_role = max(role_counts, key=role_counts.get)

            zone = {
                'position': position,
                'role': dominant_role,
                'count': len(elements),
                'elements': elements[:8]  # Cap at 8 examples per zone
            }
            zones.append(zone)

        return zones

    def _generate_anatomy_doc(self, anatomy: Dict) -> str:
        """Generate human-readable markdown from component anatomy."""
        if not anatomy or anatomy.get('error') or not anatomy.get('zones'):
            return ''

        lines = ['## Component Anatomy\n']

        # Layout system
        ls = anatomy.get('layout_system', {})
        layout_type = ls.get('type', 'block')
        parts = [layout_type.capitalize()]
        if ls.get('direction'):
            parts.append(ls['direction'])
        if ls.get('justify'):
            parts.append(ls['justify'])
        if ls.get('align'):
            parts.append(f"align-{ls['align']}")
        if ls.get('gap'):
            parts.append(f"{ls['gap']} gap")
        lines.append(f"**Layout:** {', '.join(parts)}\n")

        # Summary
        summary = anatomy.get('child_summary', {})
        total = summary.get('total', 0)
        by_role = summary.get('by_role', {})
        role_parts = [f"{count} {role}" for role, count in sorted(by_role.items(), key=lambda x: -x[1])]
        if role_parts:
            lines.append(f"**Children:** {total} total ({', '.join(role_parts)})\n")

        # Zones
        for zone in anatomy.get('zones', []):
            pos = zone.get('position', '?').capitalize()
            role = zone.get('role', 'unknown').replace('_', ' ').title()
            count = zone.get('count', 0)

            lines.append(f"### {pos} Zone — {role} ({count})\n")

            for el in zone.get('elements', [])[:5]:
                tag = el.get('tag', '?')
                text = el.get('text', '')[:40]
                font = el.get('font', '')
                color = el.get('color', '')
                bg = el.get('background', '')
                w = el.get('width', 0)
                h = el.get('height', 0)
                transition = el.get('transition', '')
                href = el.get('href', '')

                parts = [f"`<{tag}>`"]
                if text:
                    parts.append(f'"{text}"')
                if w and h:
                    parts.append(f"{w}×{h}px")
                if font:
                    parts.append(font)
                if color:
                    parts.append(color)
                if bg:
                    parts.append(f"bg: {bg}")
                if href:
                    parts.append(f"→ {href}")

                lines.append(f"- {' — '.join(parts)}")

                if transition:
                    lines.append(f"  - Transition: `{transition}`")

            lines.append('')

        return '\n'.join(lines)

    # ── End Component Anatomy ─────────────────────────────────────────

    def export_blueprint(self, output_path: str = 'component_blueprint.json'):
        """
        Export blueprint as JSON file
        """
        with open(output_path, 'w') as f:
            json.dump(self.blueprint, f, indent=2)
        print(f"\n✅ Blueprint exported to: {output_path}")

    async def rip_batch(self, selectors: List[str], auth_state: Optional[str] = None) -> Dict[str, Dict]:
        """
        Extract multiple components in one scan (batch mode)

        Args:
            selectors: List of CSS selectors to extract
            auth_state: Optional auth state for login-protected pages

        Returns:
            Dictionary mapping selector to component blueprint
        """
        results = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            if auth_state:
                context = await browser.new_context(storage_state=auth_state)
            else:
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )

            page = await context.new_page()
            page.set_default_timeout(60000)

            print(f"\n🔬 Component Ripper (Batch Mode): {self.url}")
            print(f"   Extracting {len(selectors)} components...")

            try:
                await page.goto(self.url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(3)

                for i, selector in enumerate(selectors, 1):
                    print(f"\n   [{i}/{len(selectors)}] Extracting: {selector}")

                    try:
                        # Check if element exists
                        element = await page.query_selector(selector)

                        if not element:
                            print(f"      ⚠️  Not found: {selector}")
                            results[selector] = {'error': 'Selector not found'}
                            continue

                        # Extract component
                        blueprint = await self._rip_component(page, selector)

                        # Generate code
                        if blueprint and 'error' not in blueprint:
                            code = self._generate_component_code(blueprint)
                            blueprint['code'] = code

                        # Extract Tailwind classes
                        tailwind_data = await self._extract_tailwind_classes(page, selector)
                        if tailwind_data.get('found'):
                            blueprint['tailwind_classes'] = tailwind_data

                        # Detect JavaScript behavior
                        js_behavior = await self._detect_javascript_behavior(page, selector)
                        if js_behavior:
                            blueprint['javascript'] = js_behavior

                        results[selector] = blueprint
                        print(f"      ✅ Extracted successfully")

                    except Exception as e:
                        print(f"      ❌ Error: {str(e)[:100]}")
                        results[selector] = {'error': str(e)}

                await browser.close()

            except Exception as e:
                print(f"\n❌ Page load failed: {str(e)}")
                await browser.close()
                return {'error': str(e)}

        print(f"\n✅ Batch extraction complete: {len(results)} components")
        return results


async def demo_component_ripper():
    """
    Demo: Rip the product grid from SSENSE
    """
    ripper = ComponentRipper(
        url='https://www.ssense.com/en-us/men',
        selector='.product-grid'  # Target specific grid
    )

    blueprint = await ripper.rip()

    print("\n" + "="*70)
    print(" 📋 COMPONENT BLUEPRINT")
    print("="*70)
    print(json.dumps(blueprint, indent=2, default=str))

    # Export
    ripper.export_blueprint('ssense_product_grid.json')


async def demo_page_sections():
    """
    Demo: Auto-rip all major sections from Stripe docs
    """
    ripper = ComponentRipper(url='https://stripe.com/docs')

    blueprint = await ripper.rip()

    print("\n" + "="*70)
    print(" 📋 PAGE SECTIONS BLUEPRINT")
    print("="*70)

    for section_name, section_data in blueprint.items():
        print(f"\n🔹 {section_name.upper()}")
        if 'code' in section_data:
            print(f"   Tailwind: {section_data['code'].get('tailwind', 'N/A')}")


if __name__ == '__main__':
    # Run demo
    asyncio.run(demo_page_sections())
