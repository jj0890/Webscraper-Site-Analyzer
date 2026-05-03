"""
Accessibility Tree Extractor — The browser's semantic model of the page.

Captures the Playwright aria_snapshot() and parses it into structured
evidence: landmarks, heading hierarchy, navigation structure, interactive
elements, content sections, and a compact page outline.

This is the semantic backbone that grounds spatial composition and visual
hierarchy in the browser's own understanding, replacing CSS heuristics
with definitive accessibility data.

Runs in Batch 1 (first) so downstream extractors and post-processors can
consume its output via ctx.evidence['accessibility_tree'].
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from extractors.base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)

# ── YAML-like line parser for aria_snapshot output ──

# Matches lines like:
#   - banner [ref=e4]:
#   - heading "Financial infrastructure" [level=1]
#   - link "Pricing" [ref=e33] [cursor=pointer]:
#   - text: Products
#   /url: /pricing
LINE_PATTERN = re.compile(
    r'^(\w+)'                        # role (e.g., "banner", "heading", "link")
    r'(?:\s+"([^"]*)")?'             # optional quoted name
    r'((?:\s+\[[^\]]*\])*)'          # optional [attr=value] groups (multiple)
    r'\s*:?\s*$'                      # optional trailing colon
)

ATTR_PATTERN = re.compile(r'\[(\w+)(?:=([^\]]*))?\]')

# Text-only lines: "text: Products" or just plain text content
TEXT_LINE_PATTERN = re.compile(r'^text:\s*(.+)$')

# URL property lines: "/url: /pricing"
URL_LINE_PATTERN = re.compile(r'^/url:\s*(.+)$')

# ── Landmark role mapping ──

LANDMARK_ROLES = {
    'banner': 'header',
    'navigation': 'navigation',
    'main': 'main',
    'complementary': 'aside',
    'contentinfo': 'footer',
    'region': 'region',
    'form': 'form',
    'search': 'search',
}

# ── CTA detection keywords ──

CTA_WORDS = frozenset({
    'start', 'get', 'try', 'sign', 'buy', 'shop',
    'subscribe', 'download', 'free', 'demo', 'register',
    'contact', 'request', 'book', 'schedule', 'join',
})

# Maximum raw snapshot size to store in evidence (chars)
MAX_SNAPSHOT_SIZE = 50000


class AccessibilityTreeExtractor(BaseExtractor):
    name = "accessibility_tree"

    async def extract(self, ctx: ExtractionContext) -> Dict:
        logger.info("Capturing accessibility tree...")

        # Capture the aria snapshot
        raw_snapshot = None
        try:
            raw_snapshot = await ctx.page.locator("body").aria_snapshot()
        except Exception as e:
            logger.warning("aria_snapshot() failed: %s", str(e)[:150])
            return {
                'pattern': 'Accessibility tree capture failed',
                'confidence': 0,
                'error': str(e)[:200],
            }

        if not raw_snapshot or not raw_snapshot.strip():
            logger.warning("aria_snapshot() returned empty result")
            return {
                'pattern': 'Empty accessibility tree',
                'confidence': 0,
            }

        # Parse YAML-like output into tree structure
        tree = self._parse_snapshot(raw_snapshot)

        if not tree:
            logger.warning("Failed to parse accessibility tree")
            return {
                'pattern': 'Failed to parse accessibility tree',
                'confidence': 10,
                'raw_snapshot': raw_snapshot[:MAX_SNAPSHOT_SIZE],
            }

        # Extract semantic components
        landmarks_grouped = self._extract_landmarks(tree)
        headings = self._extract_heading_hierarchy(tree)
        nav_structure = self._extract_navigation_structure(tree)
        interactive = self._extract_interactive_elements(tree)
        content_sections = self._extract_content_sections(tree)
        page_outline = self._generate_page_outline(landmarks_grouped, headings)
        confidence = self._calculate_confidence(landmarks_grouped, headings, interactive)

        # Flatten landmarks into a list for downstream consumers
        # Each item: {'type': 'header', 'label': '...', 'children_count': N}
        landmarks_flat = []
        for sem_type, instances in landmarks_grouped.items():
            for inst in instances:
                landmarks_flat.append({
                    'type': sem_type,
                    'label': inst.get('name') or '',
                    'children_count': inst.get('children_count', 0),
                    'children_summary': inst.get('children_summary', ''),
                })

        landmark_count = len(landmarks_flat)

        return {
            'pattern': (
                f"Semantic structure: {landmark_count} landmarks, "
                f"{len(headings)} headings, "
                f"{interactive.get('total_links', 0)} links, "
                f"{interactive.get('total_buttons', 0)} buttons"
            ),
            'confidence': confidence,
            'landmarks': landmarks_flat,
            'landmarks_grouped': landmarks_grouped,  # keep dict form for outline
            'heading_hierarchy': headings,
            'navigation_structure': nav_structure,
            'interactive_elements': interactive,
            'content_sections': content_sections,
            'page_outline': page_outline,
            'raw_snapshot': raw_snapshot[:MAX_SNAPSHOT_SIZE],
        }

    # ------------------------------------------------------------------
    # Snapshot parser
    # ------------------------------------------------------------------

    def _parse_snapshot(self, yaml_str: str) -> List[Dict]:
        """
        Parse Playwright aria_snapshot YAML into a list of tree nodes.

        Each line: "- role \"name\" [attr=value]:"
        Indentation determines parent-child relationships.
        """
        lines = yaml_str.split('\n')
        root = {'role': 'root', 'name': None, 'attrs': {}, 'children': [], 'url': None}
        stack: List[Tuple[Dict, int]] = [(root, -1)]

        for raw_line in lines:
            if not raw_line.strip():
                continue

            # Calculate indent (number of leading spaces)
            indent = len(raw_line) - len(raw_line.lstrip())
            stripped = raw_line.strip()

            # Strip leading "- " bullet
            if stripped.startswith('- '):
                stripped = stripped[2:]

            # Check for URL property line
            url_match = URL_LINE_PATTERN.match(stripped)
            if url_match:
                # Attach URL to the most recent node at this or higher indent
                if len(stack) > 1:
                    stack[-1][0]['url'] = url_match.group(1).strip()
                continue

            # Check for text-only line
            text_match = TEXT_LINE_PATTERN.match(stripped)
            if text_match:
                text_node = {
                    'role': 'text',
                    'name': text_match.group(1).strip().strip('"'),
                    'attrs': {},
                    'children': [],
                    'url': None,
                }
                # Pop stack to find parent
                while len(stack) > 1 and stack[-1][1] >= indent:
                    stack.pop()
                stack[-1][0]['children'].append(text_node)
                continue

            # Try to parse as a role line
            parsed = self._parse_line(stripped)
            if not parsed:
                # Could be plain text content (e.g., just "Products")
                # Treat as unnamed text node
                if stripped and not stripped.startswith('#'):
                    text_node = {
                        'role': 'text',
                        'name': stripped.strip('"').strip("'"),
                        'attrs': {},
                        'children': [],
                        'url': None,
                    }
                    while len(stack) > 1 and stack[-1][1] >= indent:
                        stack.pop()
                    stack[-1][0]['children'].append(text_node)
                continue

            node = {
                'role': parsed['role'],
                'name': parsed['name'],
                'attrs': parsed['attrs'],
                'children': [],
                'url': None,
            }

            # Pop stack to find correct parent based on indentation
            while len(stack) > 1 and stack[-1][1] >= indent:
                stack.pop()

            stack[-1][0]['children'].append(node)
            stack.append((node, indent))

        return root['children']

    def _parse_line(self, line: str) -> Optional[Dict]:
        """Parse a single aria snapshot line into role, name, attrs."""
        # Remove trailing colon
        if line.endswith(':'):
            line = line[:-1].rstrip()

        match = LINE_PATTERN.match(line)
        if not match:
            return None

        role = match.group(1)
        name = match.group(2)  # May be None
        attrs_str = match.group(3) or ''

        # Parse all [attr=value] pairs
        attrs = {}
        for attr_match in ATTR_PATTERN.finditer(attrs_str):
            key = attr_match.group(1)
            value = attr_match.group(2)
            if value is not None:
                attrs[key] = value.strip('"')
            else:
                attrs[key] = True  # Boolean attrs like [checked], [disabled]

        # Skip ref attributes (ephemeral, not useful for analysis)
        attrs.pop('ref', None)

        return {'role': role, 'name': name, 'attrs': attrs}

    # ------------------------------------------------------------------
    # Landmark extraction
    # ------------------------------------------------------------------

    def _extract_landmarks(self, tree: List[Dict]) -> Dict:
        """
        Walk tree and collect ARIA landmark nodes.
        Returns dict mapping semantic_type → list of instances.
        """
        landmarks: Dict[str, List[Dict]] = {}

        def walk(node: Dict):
            role = node['role']
            if role in LANDMARK_ROLES:
                semantic_type = LANDMARK_ROLES[role]
                if semantic_type not in landmarks:
                    landmarks[semantic_type] = []
                landmarks[semantic_type].append({
                    'name': node.get('name'),
                    'children_count': len(node.get('children', [])),
                    'children_summary': self._summarize_children(node),
                })
            for child in node.get('children', []):
                walk(child)

        for node in tree:
            walk(node)

        return landmarks

    def _summarize_children(self, node: Dict) -> str:
        """Generate a compact summary of a node's children roles."""
        if not node.get('children'):
            return ''

        role_counts: Dict[str, int] = {}
        for child in node['children']:
            role = child['role']
            if role == 'generic':
                continue  # Skip noise
            role_counts[role] = role_counts.get(role, 0) + 1

        parts = []
        for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
            if count > 1:
                parts.append(f"{role}x{count}")
            else:
                parts.append(role)

        return ', '.join(parts[:6])

    # ------------------------------------------------------------------
    # Heading hierarchy
    # ------------------------------------------------------------------

    def _extract_heading_hierarchy(self, tree: List[Dict]) -> List[Dict]:
        """Extract all headings in document order with their level and text."""
        headings: List[Dict] = []

        def walk(node: Dict):
            if node['role'] == 'heading':
                level_raw = node['attrs'].get('level', '0')
                try:
                    level = int(level_raw)
                except (ValueError, TypeError):
                    level = 0

                # Name may be directly on heading, or composed from children
                text = node.get('name') or self._collect_text(node)

                if text:
                    headings.append({
                        'level': level,
                        'text': text[:200],  # Cap text length
                    })

            for child in node.get('children', []):
                walk(child)

        for node in tree:
            walk(node)

        return headings

    def _collect_text(self, node: Dict) -> str:
        """Recursively collect text content from a node and its children."""
        parts = []

        if node.get('name'):
            parts.append(node['name'])

        for child in node.get('children', []):
            if child['role'] == 'text':
                if child.get('name'):
                    parts.append(child['name'])
            elif child.get('name'):
                parts.append(child['name'])
            else:
                # Recurse into unnamed children
                child_text = self._collect_text(child)
                if child_text:
                    parts.append(child_text)

        return ' '.join(parts).strip()

    # ------------------------------------------------------------------
    # Navigation structure
    # ------------------------------------------------------------------

    def _extract_navigation_structure(self, tree: List[Dict]) -> Dict:
        """Extract navigation items with URLs and CTA links."""
        nav_items: List[Dict] = []
        cta_links: List[Dict] = []
        all_links: List[Dict] = []

        def walk(node: Dict, in_nav: bool = False):
            is_nav = node['role'] == 'navigation'
            current_in_nav = in_nav or is_nav

            if node['role'] == 'link':
                name = node.get('name') or self._collect_text(node)
                url = node.get('url') or node['attrs'].get('url', '')
                item = {'text': name or '', 'url': url}

                if current_in_nav:
                    nav_items.append(item)
                all_links.append(item)

                # CTA detection
                if name:
                    text_lower = name.lower()
                    if any(w in text_lower for w in CTA_WORDS):
                        cta_links.append(item)

            elif node['role'] == 'button':
                name = node.get('name') or self._collect_text(node)
                if current_in_nav and name:
                    nav_items.append({
                        'text': name,
                        'type': 'button',
                        'expanded': node['attrs'].get('expanded'),
                        'haspopup': node['attrs'].get('haspopup'),
                    })

            for child in node.get('children', []):
                walk(child, current_in_nav)

        for node in tree:
            walk(node)

        return {
            'primary_nav': {'items': nav_items[:20]},
            'cta_links': cta_links[:5],
            'total_nav_items': len(nav_items),
        }

    # ------------------------------------------------------------------
    # Interactive elements
    # ------------------------------------------------------------------

    def _extract_interactive_elements(self, tree: List[Dict]) -> Dict:
        """Extract all interactive elements by type."""
        buttons: List[Dict] = []
        links: List[Dict] = []
        inputs: List[Dict] = []
        forms: List[Dict] = []

        def walk(node: Dict):
            role = node['role']

            if role == 'button':
                name = node.get('name') or self._collect_text(node)
                if name:
                    buttons.append({'name': name[:100]})

            elif role == 'link':
                name = node.get('name') or self._collect_text(node)
                url = node.get('url') or node['attrs'].get('url', '')
                if name:
                    links.append({'name': name[:100], 'url': url})

            elif role in ('textbox', 'searchbox', 'combobox', 'checkbox',
                          'radio', 'slider', 'spinbutton'):
                name = node.get('name') or ''
                inputs.append({
                    'type': role,
                    'name': name[:100],
                    'checked': node['attrs'].get('checked', None),
                    'disabled': node['attrs'].get('disabled', None),
                })

            elif role == 'form':
                name = node.get('name') or ''
                forms.append({'name': name[:100]})

            for child in node.get('children', []):
                walk(child)

        for node in tree:
            walk(node)

        return {
            'buttons': buttons[:30],
            'links': links[:50],
            'inputs': inputs[:20],
            'forms': forms[:10],
            'total_buttons': len(buttons),
            'total_links': len(links),
            'total_inputs': len(inputs),
            'total_forms': len(forms),
        }

    # ------------------------------------------------------------------
    # Content sections
    # ------------------------------------------------------------------

    def _extract_content_sections(self, tree: List[Dict]) -> List[Dict]:
        """Extract named regions, articles, and sections."""
        sections: List[Dict] = []

        def walk(node: Dict):
            if node['role'] in ('region', 'article'):
                name = node.get('name') or ''
                sections.append({
                    'role': node['role'],
                    'name': name[:100],
                    'children_count': len(node.get('children', [])),
                })

            for child in node.get('children', []):
                walk(child)

        for node in tree:
            walk(node)

        return sections[:20]

    # ------------------------------------------------------------------
    # Page outline
    # ------------------------------------------------------------------

    def _generate_page_outline(self, landmarks: Dict, headings: List[Dict]) -> str:
        """
        Generate compact page skeleton string.
        Example: "banner(nav[5]) → main(h1 → h2*4) → contentinfo(6 items)"
        """
        parts = []

        # Header/banner
        if 'header' in landmarks:
            header = landmarks['header'][0]
            nav_count = header.get('children_count', 0)
            parts.append(f"banner({nav_count} children)")

        # Navigation (standalone, not inside header)
        if 'navigation' in landmarks:
            nav_instances = landmarks['navigation']
            total_items = sum(n.get('children_count', 0) for n in nav_instances)
            if total_items and 'header' not in landmarks:
                parts.append(f"nav[{total_items}]")

        # Main content
        if 'main' in landmarks:
            # Summarize headings in main
            h_parts = []
            h_level_counts: Dict[int, int] = {}
            for h in headings:
                level = h['level']
                h_level_counts[level] = h_level_counts.get(level, 0) + 1

            for level in sorted(h_level_counts.keys()):
                count = h_level_counts[level]
                if count > 1:
                    h_parts.append(f"h{level}×{count}")
                else:
                    h_parts.append(f"h{level}")

            if h_parts:
                parts.append(f"main({', '.join(h_parts)})")
            else:
                parts.append("main")

        # Sidebar
        if 'aside' in landmarks:
            parts.append("aside")

        # Footer
        if 'footer' in landmarks:
            footer = landmarks['footer'][0]
            children = footer.get('children_count', 0)
            parts.append(f"contentinfo({children} items)")

        return ' → '.join(parts) if parts else 'No landmarks detected'

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self, landmarks: Dict, headings: List[Dict], interactive: Dict
    ) -> int:
        """
        Confidence based on richness of semantic structure.
        - 50: base (snapshot captured)
        - +20: 4+ landmarks
        - +10: h1 present
        - +10: 3+ headings
        - +10: 10+ interactive elements
        """
        confidence = 30  # Base: tree captured

        landmark_count = sum(len(v) for v in landmarks.values())
        confidence += min(25, landmark_count * 5)  # +5 per landmark, max 25

        heading_count = len(headings)
        confidence += min(20, heading_count * 3)   # +3 per heading, max 20

        has_h1 = any(h['level'] == 1 for h in headings)
        if has_h1:
            confidence += 5  # Proper document structure bonus

        total_interactive = (
            interactive.get('total_buttons', 0) +
            interactive.get('total_links', 0)
        )
        confidence += min(15, total_interactive)    # +1 per interactive, max 15

        return min(confidence, 95)
