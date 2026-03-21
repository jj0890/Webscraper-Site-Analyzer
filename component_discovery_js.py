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

        // ── Navigation / Header ──
        if (tag === 'nav' || tag === 'header' || role === 'navigation' || role === 'banner') {
            const linkCount = el.querySelectorAll('a').length;
            const hasLogo = !!el.querySelector('img, svg, [class*="logo"], [class*="brand"]');
            const hasSearch = !!el.querySelector('input[type="search"], [class*="search"]');
            const hasDropdown = !!el.querySelector('[class*="dropdown"], [class*="menu"], ul ul, [aria-expanded]');
            const parts = [];
            if (hasLogo) parts.push('Logo');
            if (linkCount > 0) parts.push(linkCount + ' links');
            if (hasSearch) parts.push('Search');
            if (hasDropdown) parts.push('Dropdowns');
            const detail = parts.length > 0 ? ' — ' + parts.join(', ') : '';
            // Distinguish sticky/fixed nav
            const isSticky = s.position === 'fixed' || s.position === 'sticky';
            const prefix = isSticky ? 'Sticky Navbar' : (rect.height < 120 ? 'Navbar' : 'Header');
            return { category: 'navigation', label: prefix + detail, priority: 90 };
        }

        // ── Footer ──
        if (tag === 'footer' || role === 'contentinfo') {
            const linkCount = el.querySelectorAll('a').length;
            const cols = Array.from(el.children).filter(c => {
                const cr = c.getBoundingClientRect();
                return cr.width > 100 && cr.height > 40;
            }).length;
            const detail = [];
            if (cols >= 3) detail.push(cols + '-column');
            if (linkCount > 0) detail.push(linkCount + ' links');
            return { category: 'footer', label: 'Footer' + (detail.length ? ' — ' + detail.join(', ') : ''), priority: 70 };
        }

        // ── Hero — large section near top with imagery ──
        if (rect.top < vh * 0.5 && rect.height > vh * 0.3 && rect.height < vh * 1.5) {
            const hasImg = el.querySelectorAll('img, video, picture').length > 0;
            const hasCTA = el.querySelectorAll('button, a[href]').length > 0;
            const bgImg = s.backgroundImage !== 'none';
            const links = el.querySelectorAll('a').length;
            if ((hasImg || bgImg || hasCTA) && links < 30) {
                const headingEl = el.querySelector('h1, h2');
                const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
                const hasBg = bgImg || !!el.querySelector('video');
                const label = heading
                    ? 'Hero — "' + heading + '"'
                    : hasBg ? 'Hero Banner' : 'Hero Section';
                return { category: 'hero', label: label, priority: 85 };
            }
        }

        // ── Form ──
        if (tag === 'form' || el.querySelector('form')) {
            const inputCount = el.querySelectorAll('input, textarea, select').length;
            if (inputCount > 0) {
                const hasEmail = !!el.querySelector('input[type="email"], input[name*="email"]');
                const hasPassword = !!el.querySelector('input[type="password"]');
                const hasSubmit = !!el.querySelector('button[type="submit"], input[type="submit"]');
                const formType = hasPassword ? 'Login Form' :
                                 hasEmail && inputCount <= 2 ? 'Email Signup' :
                                 inputCount > 5 ? 'Long Form' : 'Form';
                return { category: 'form', label: formType + ' (' + inputCount + ' fields)', priority: 75 };
            }
        }

        // ── Media/Player ──
        if (cn.includes('player') || cn.includes('audio') || cn.includes('video') ||
            el.querySelector('audio, video, [class*="player"]')) {
            const hasVideo = !!el.querySelector('video');
            const hasAudio = !!el.querySelector('audio');
            return { category: 'media', label: hasVideo ? 'Video Player' : hasAudio ? 'Audio Player' : 'Media Player', priority: 80 };
        }

        // ── Repeating children — smart grid classification ──
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
                    const sample = matching[0];
                    const hasImgs = !!sample.querySelector('img, picture');
                    const hasHeadings = !!sample.querySelector('h1,h2,h3,h4');
                    const hasLinks = !!sample.querySelector('a');
                    const hasParagraphs = !!sample.querySelector('p');
                    const sampleText = (sample.textContent || '').trim();
                    const avgTextLen = sampleText.length / Math.max(1, matching.length);
                    const isInline = s.display.includes('flex') && s.flexDirection !== 'column';
                    const isGridLayout = s.display.includes('grid');
                    const itemR = sample.getBoundingClientRect();
                    const isSmallItem = itemR.height < 80 && itemR.width < 200;
                    const isOnlyImgs = hasImgs && !hasHeadings && !hasParagraphs && avgTextLen < 30;

                    // ── Classify the repeating pattern ──
                    var gridLabel, gridCategory;

                    if (isSmallItem && !hasImgs && !hasHeadings && avgTextLen < 50) {
                        // Small repeating items with little content = stats, pills, or tags
                        gridLabel = matching.length + ' Metric Stats';
                        gridCategory = 'content_grid';
                    } else if (isOnlyImgs && isInline && !hasHeadings) {
                        // Row of images with no text = logo bar or image strip
                        gridLabel = matching.length + '-Logo Strip';
                        gridCategory = 'content_grid';
                    } else if (hasImgs && hasHeadings && hasParagraphs) {
                        // Full cards: image + heading + description
                        gridLabel = matching.length + ' Feature Cards';
                        gridCategory = 'content_grid';
                    } else if (hasImgs && hasHeadings) {
                        // Cards with image + title (no body text)
                        gridLabel = matching.length + ' Product Cards';
                        gridCategory = 'content_grid';
                    } else if (hasImgs && hasLinks && !hasHeadings) {
                        // Linked images = gallery or portfolio
                        gridLabel = matching.length + '-Image Gallery';
                        gridCategory = 'content_grid';
                    } else if (hasHeadings && hasParagraphs && !hasImgs) {
                        // Text-only with heading + body = feature list
                        gridLabel = matching.length + ' Feature List';
                        gridCategory = 'content_grid';
                    } else if (hasHeadings && !hasImgs) {
                        // Headings only = link list or menu group
                        gridLabel = matching.length + ' Link Group';
                        gridCategory = 'content_grid';
                    } else if (hasImgs && !hasHeadings && !hasLinks) {
                        // Images only, no links = testimonial logos or icons
                        gridLabel = matching.length + ' Icon/Logo Row';
                        gridCategory = 'content_grid';
                    } else {
                        // Fallback — describe what's inside
                        const parts = [];
                        if (hasImgs) parts.push('images');
                        if (hasHeadings) parts.push('headings');
                        if (hasLinks) parts.push('links');
                        gridLabel = matching.length + ' Repeating Blocks' + (parts.length ? ' (' + parts.join('+') + ')' : '');
                        gridCategory = 'content_grid';
                    }

                    return {
                        category: gridCategory,
                        label: gridLabel,
                        priority: 80,
                        meta: { itemCount: matching.length, hasImages: hasImgs, hasHeadings: hasHeadings, layout: isGridLayout ? 'grid' : isInline ? 'row' : 'stack' }
                    };
                }
            }
        }

        // ── Testimonial / Quote ──
        if (el.querySelector('blockquote, [class*="testimonial"], [class*="quote"]') ||
            cn.includes('testimonial') || cn.includes('quote')) {
            return { category: 'section', label: 'Testimonial', priority: 65 };
        }

        // ── CTA / Banner strip ──
        if (rect.height < 200 && rect.width > vw * 0.7) {
            const btns = el.querySelectorAll('button, a[href]').length;
            const headingEl = el.querySelector('h1, h2, h3, h4');
            if (btns >= 1 && headingEl) {
                return { category: 'section', label: 'CTA Banner — "' + headingEl.textContent.trim().substring(0, 40) + '"', priority: 65 };
            }
        }

        // ── Generic section ──
        if (tag === 'section' || tag === 'main' || tag === 'article' ||
            role === 'main' || role === 'region') {
            const headingEl = el.querySelector('h1, h2, h3');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
            const imgCount = el.querySelectorAll('img, picture').length;
            const linkCount = el.querySelectorAll('a').length;
            // Try to give a useful descriptor
            if (tag === 'article') {
                return { category: 'section', label: heading ? 'Article — "' + heading + '"' : 'Article', priority: 55 };
            }
            const detail = [];
            if (imgCount > 3) detail.push(imgCount + ' images');
            if (linkCount > 5) detail.push(linkCount + ' links');
            const suffix = detail.length ? ' (' + detail.join(', ') + ')' : '';
            const label = heading ? '"' + heading + '"' + suffix : 'Content Section' + suffix;
            return { category: 'section', label: label, priority: 50 };
        }

        // ── Aside / sidebar ──
        if (tag === 'aside' || role === 'complementary') {
            const headingEl = el.querySelector('h2, h3, h4');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 40) : null;
            return { category: 'sidebar', label: heading ? 'Sidebar — "' + heading + '"' : 'Sidebar', priority: 60 };
        }

        // ── Large div fallback ──
        if (rect.width > vw * 0.5 && rect.height > 100 && kids.length >= 2) {
            const headingEl = el.querySelector('h1, h2, h3, h4');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
            const imgCount = el.querySelectorAll('img, picture').length;
            // Smarter fallback label
            if (imgCount > 5 && !heading) {
                return { category: 'block', label: 'Image Gallery (' + imgCount + ' images)', priority: 35 };
            }
            return {
                category: 'block',
                label: heading ? '"' + heading + '"' : 'Content Block',
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

        // Skip mega-elements (entire page wrappers) — not useful as patterns
        const absTop = rect.top + window.scrollY;
        const totalH = rect.height;
        if (totalH > vh * 3 && rect.width > vw * 0.9) continue;

        // Skip off-screen elements (left beyond viewport)
        if (rect.left > vw) continue;

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
