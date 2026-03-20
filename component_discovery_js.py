"""
Shared JavaScript for lightweight component discovery.

Used by both:
- component_ripper.py (full discovery with screenshots)
- deep_evidence_engine.py (lightweight discovery during scan, no screenshots)

This avoids duplicating the 200-line classify/scan JS block.
"""

COMPONENT_DISCOVERY_JS = '''() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const results = [];
    const seen = new Set();

    function getSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        const tag = el.tagName.toLowerCase();
        const cn = (typeof el.className === 'string') ? el.className : (el.className?.baseVal || '');
        if (cn) {
            const first = cn.trim().split(/\\s+/)[0];
            if (first) {
                const sel = tag + '.' + CSS.escape(first);
                if (document.querySelectorAll(sel).length === 1) return sel;
            }
        }
        const parent = el.parentElement;
        if (!parent) return tag;
        const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
        if (siblings.length === 1) {
            const parentSel = parent.id ? '#' + CSS.escape(parent.id) : parent.tagName.toLowerCase();
            return parentSel + ' > ' + tag;
        }
        const idx = siblings.indexOf(el) + 1;
        const parentSel = parent.id ? '#' + CSS.escape(parent.id) : parent.tagName.toLowerCase();
        return parentSel + ' > ' + tag + ':nth-child(' + idx + ')';
    }

    function getPreview(el) {
        const text = (el.textContent || '').trim().substring(0, 120);
        const imgs = el.querySelectorAll('img, picture, video, svg').length;
        const links = el.querySelectorAll('a').length;
        const buttons = el.querySelectorAll('button, [role="button"]').length;
        const inputs = el.querySelectorAll('input, textarea, select').length;
        const headings = el.querySelectorAll('h1, h2, h3, h4, h5, h6').length;
        const children = el.children.length;
        return { text, imgs, links, buttons, inputs, headings, children };
    }

    function classify(el, rect) {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const cn = ((typeof el.className === 'string') ? el.className : '').toLowerCase();
        const s = window.getComputedStyle(el);

        // Navigation
        if (tag === 'nav' || tag === 'header' || role === 'navigation' || role === 'banner') {
            const linkCount = el.querySelectorAll('a').length;
            return { category: 'navigation', label: linkCount > 0 ? 'Navigation (' + linkCount + ' links)' : 'Header', priority: 90 };
        }

        // Footer
        if (tag === 'footer' || role === 'contentinfo') {
            const linkCount = el.querySelectorAll('a').length;
            return { category: 'footer', label: linkCount > 0 ? 'Footer (' + linkCount + ' links)' : 'Footer', priority: 70 };
        }

        // Hero — large section near top with imagery, but NOT the whole page
        if (rect.top < vh * 0.5 && rect.height > vh * 0.3 && rect.height < vh * 1.5) {
            const hasImg = el.querySelectorAll('img, video, picture').length > 0;
            const hasCTA = el.querySelectorAll('button, a[href]').length > 0;
            const bgImg = s.backgroundImage !== 'none';
            const links = el.querySelectorAll('a').length;
            if ((hasImg || bgImg || hasCTA) && links < 30) {
                return { category: 'hero', label: 'Hero Section', priority: 85 };
            }
        }

        // Form
        if (tag === 'form' || el.querySelector('form')) {
            const inputCount = el.querySelectorAll('input, textarea, select').length;
            if (inputCount > 0) {
                return { category: 'form', label: 'Form (' + inputCount + ' fields)', priority: 75 };
            }
        }

        // Media/Player
        if (cn.includes('player') || cn.includes('audio') || cn.includes('video') ||
            el.querySelector('audio, video, [class*="player"]')) {
            return { category: 'media', label: 'Media Player', priority: 80 };
        }

        // Content grid — find repeating children
        const kids = Array.from(el.children).filter(c => {
            const cr = c.getBoundingClientRect();
            return cr.width > 40 && cr.height > 20;
        });
        if (kids.length >= 3) {
            const groups = {};
            for (const kid of kids) {
                const kt = kid.tagName;
                if (!groups[kt]) groups[kt] = [];
                groups[kt].push(kid);
            }
            for (const [, group] of Object.entries(groups)) {
                if (group.length < 3) continue;
                const sig = (el2) => {
                    const ct = Array.from(el2.children).map(c => c.tagName).sort().join(',');
                    return ct + '|' + (!!el2.querySelector('img')) + '|' + (!!el2.querySelector('a'));
                };
                const ref = sig(group[0]);
                const matching = group.filter(el2 => sig(el2) === ref);
                if (matching.length >= 3) {
                    const hasImgs = !!matching[0].querySelector('img, picture');
                    const hasHeadings = !!matching[0].querySelector('h1,h2,h3,h4');
                    const itemType = hasImgs && hasHeadings ? 'Card' :
                                     hasImgs ? 'Image' :
                                     hasHeadings ? 'Text' : 'Item';
                    return {
                        category: 'content_grid',
                        label: matching.length + '-Item ' + itemType + ' Grid',
                        priority: 80,
                        meta: { itemCount: matching.length, hasImages: hasImgs, hasHeadings: hasHeadings }
                    };
                }
            }
        }

        // Generic section
        if (tag === 'section' || tag === 'main' || tag === 'article' ||
            role === 'main' || role === 'region') {
            const headingEl = el.querySelector('h1, h2, h3');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 60) : null;
            const label = heading ? 'Section: "' + heading + '"' : 'Content Section';
            return { category: 'section', label: label, priority: 50 };
        }

        // Aside / sidebar
        if (tag === 'aside' || role === 'complementary') {
            return { category: 'sidebar', label: 'Sidebar', priority: 60 };
        }

        // Large div with significant content
        if (rect.width > vw * 0.5 && rect.height > 100 && kids.length >= 2) {
            const headingEl = el.querySelector('h1, h2, h3, h4');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 60) : null;
            return {
                category: 'block',
                label: heading ? 'Block: "' + heading + '"' : 'Content Block',
                priority: 30
            };
        }

        return null;
    }

    // Scan semantic elements + large visible divs
    const candidates = [
        ...document.querySelectorAll('nav, header, footer, main, section, article, aside, form, [role="navigation"], [role="banner"], [role="main"], [role="contentinfo"], [role="region"], [role="complementary"]'),
        ...Array.from(document.querySelectorAll('div')).filter(d => {
            const r = d.getBoundingClientRect();
            return r.width > vw * 0.4 && r.height > 80 && d.children.length >= 2;
        })
    ];

    for (const el of candidates) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;

        const sel = getSelector(el);
        if (seen.has(sel)) continue;
        seen.add(sel);

        const info = classify(el, rect);
        if (!info) continue;

        const preview = getPreview(el);
        const layout = s.display.includes('flex') ? 'flex' :
                       s.display.includes('grid') ? 'grid' : 'block';

        results.push({
            selector: sel,
            label: info.label,
            category: info.category,
            priority: info.priority,
            bounds: {
                top: Math.round(rect.top + window.scrollY),
                left: Math.round(rect.left),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            preview: preview,
            layout: layout,
            tag: el.tagName.toLowerCase(),
            meta: info.meta || null
        });
    }

    // Sort by vertical position then priority
    results.sort((a, b) => {
        const aThird = Math.floor(a.bounds.top / (vh / 3));
        const bThird = Math.floor(b.bounds.top / (vh / 3));
        if (aThird !== bThird) return aThird - bThird;
        return b.priority - a.priority;
    });

    // Deduplicate overlapping elements (keep higher priority, preserve different categories)
    const filtered = [];
    for (const comp of results) {
        const dominated = filtered.some(existing => {
            if (comp.category !== existing.category) return false;
            const overlap =
                comp.bounds.top >= existing.bounds.top - 5 &&
                comp.bounds.left >= existing.bounds.left - 5 &&
                (comp.bounds.top + comp.bounds.height) <= (existing.bounds.top + existing.bounds.height + 5) &&
                (comp.bounds.left + comp.bounds.width) <= (existing.bounds.left + existing.bounds.width + 5);
            return overlap && existing.priority >= comp.priority;
        });
        if (!dominated) filtered.push(comp);
    }

    return { components: filtered, viewport: { width: vw, height: vh } };
}'''
