"""
Shared JavaScript for lightweight component discovery.

Used by both:
- component_ripper.py (full discovery with screenshots)
- deep_evidence_engine.py (lightweight discovery during scan, no screenshots)

This avoids duplicating the classify/scan JS block.

Categories detected (25 total):
  navigation, hero, footer, form, media, content_grid, section, sidebar, block,
  accordion, tabs, modal, breadcrumb, table, carousel, pricing, timeline,
  alert, stepper, marquee, testimonial, cta, split_content, newsletter,
  social_proof
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
        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
        const s = window.getComputedStyle(el);

        // ── 1. Navigation / Header ──
        if (tag === 'nav' || tag === 'header' || role === 'navigation' || role === 'banner') {
            // Skip breadcrumb navs — handled separately
            if (ariaLabel.includes('breadcrumb') || cn.includes('breadcrumb')) {
                var bcLinks = el.querySelectorAll('a, span').length;
                return { category: 'breadcrumb', label: 'Breadcrumb (' + bcLinks + ' levels)', priority: 55 };
            }

            const linkCount = el.querySelectorAll('a').length;
            const hasLogo = !!el.querySelector('img, svg, [class*="logo"], [class*="brand"]');
            const hasSearch = !!el.querySelector('input[type="search"], [class*="search"]');
            const hasDropdown = !!el.querySelector('[class*="dropdown"], [class*="menu"], ul ul, [aria-expanded]');
            const hasBurger = !!el.querySelector('[class*="hamburger"], [class*="burger"], [class*="menu-toggle"], [class*="nav-toggle"], [class*="mobile-menu"], [class*="menu-icon"], [class*="menu-btn"], [aria-label*="menu" i], [aria-label*="Menu" i], button svg line, button svg path[d*="M3"], [class*="sandwich"]');
            const parts = [];
            if (hasLogo) parts.push('Logo');
            if (linkCount > 0) parts.push(linkCount + ' links');
            if (hasSearch) parts.push('Search');
            if (hasBurger) parts.push('Burger Menu');
            if (hasDropdown && !hasBurger) parts.push('Dropdowns');
            const detail = parts.length > 0 ? ' — ' + parts.join(', ') : '';

            const isSticky = s.position === 'fixed' || s.position === 'sticky';
            const isVertical = s.flexDirection === 'column' && rect.width < vw * 0.25;
            const isBottomNav = rect.top > vh * 0.8 && rect.height < 80;

            var prefix;
            if (isBottomNav) prefix = 'Tab Bar';
            else if (isVertical) prefix = 'Sidebar Nav';
            else if (isSticky) prefix = 'Sticky Navbar';
            else prefix = rect.height < 120 ? 'Navbar' : 'Header';

            return { category: 'navigation', label: prefix + detail, priority: 90 };
        }

        // ── 2. Footer ──
        if (tag === 'footer' || role === 'contentinfo') {
            const linkCount = el.querySelectorAll('a').length;
            const hasNewsletter = !!el.querySelector('input[type="email"], [class*="newsletter"], [class*="subscribe"]');
            const hasSocial = !!el.querySelector('[class*="social"], [aria-label*="twitter" i], [aria-label*="facebook" i], [aria-label*="instagram" i], [aria-label*="linkedin" i], [href*="twitter.com"], [href*="facebook.com"], [href*="instagram.com"], [href*="linkedin.com"], [href*="x.com"]');
            const cols = Array.from(el.children).filter(function(c) {
                var cr = c.getBoundingClientRect();
                return cr.width > 100 && cr.height > 40;
            }).length;

            var footerType;
            if (cols >= 4 && (hasNewsletter || hasSocial)) footerType = 'Mega Footer';
            else if (cols >= 3) footerType = 'Fat Footer';
            else footerType = 'Minimal Footer';

            const detail = [];
            if (cols >= 3) detail.push(cols + ' columns');
            if (linkCount > 0) detail.push(linkCount + ' links');
            if (hasNewsletter) detail.push('Newsletter');
            if (hasSocial) detail.push('Social');
            return { category: 'footer', label: footerType + (detail.length ? ' — ' + detail.join(', ') : ''), priority: 70 };
        }

        // ── 3. Hero — large section near top with imagery ──
        if (rect.top < vh * 0.5 && rect.height > vh * 0.3 && rect.height < vh * 1.5) {
            const hasImg = el.querySelectorAll('img, video, picture').length > 0;
            const hasCTA = el.querySelectorAll('button, a[href]').length > 0;
            const bgImg = s.backgroundImage !== 'none';
            const links = el.querySelectorAll('a').length;
            if ((hasImg || bgImg || hasCTA) && links < 30) {
                const headingEl = el.querySelector('h1, h2');
                const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
                const hasVideo = !!el.querySelector('video');

                // Detect hero variant
                const kidEls = Array.from(el.children).filter(function(c) {
                    var cr = c.getBoundingClientRect();
                    return cr.width > 100 && cr.height > 50;
                });
                const isSplit = (s.display.includes('flex') || s.display.includes('grid')) &&
                    kidEls.length === 2 &&
                    kidEls.some(function(k) { return !!k.querySelector('img, video, picture'); }) &&
                    kidEls.some(function(k) { return !!k.querySelector('h1, h2'); });
                const isCentered = s.textAlign === 'center' ||
                    (headingEl && window.getComputedStyle(headingEl).textAlign === 'center');

                var heroVariant;
                if (hasVideo) heroVariant = 'Video Hero';
                else if (isSplit) heroVariant = 'Split Hero';
                else if (isCentered) heroVariant = 'Centered Hero';
                else if (bgImg) heroVariant = 'Hero Banner';
                else heroVariant = 'Hero Section';

                const label = heading ? heroVariant + ' — "' + heading + '"' : heroVariant;
                return { category: 'hero', label: label, priority: 85 };
            }
        }

        // ── 4. Form ──
        if (tag === 'form' || (el.querySelector('form') && !el.querySelector('nav'))) {
            const inputCount = el.querySelectorAll('input, textarea, select').length;
            if (inputCount > 0) {
                const hasEmail = !!el.querySelector('input[type="email"], input[name*="email"]');
                const hasPassword = !!el.querySelector('input[type="password"]');
                const hasSearch = !!el.querySelector('input[type="search"], [class*="search"]');
                const formType = hasPassword ? 'Login Form' :
                                 hasSearch ? 'Search Form' :
                                 hasEmail && inputCount <= 2 ? 'Email Signup' :
                                 inputCount > 5 ? 'Long Form' : 'Form';
                return { category: 'form', label: formType + ' (' + inputCount + ' fields)', priority: 75 };
            }
        }

        // ── 5. Media/Player ──
        if (cn.includes('player') || cn.includes('audio') || cn.includes('video') ||
            el.querySelector('audio, video, [class*="player"]')) {
            const hasVideo = !!el.querySelector('video');
            const hasAudio = !!el.querySelector('audio');
            return { category: 'media', label: hasVideo ? 'Video Player' : hasAudio ? 'Audio Player' : 'Media Player', priority: 80 };
        }

        // ── 6. Accordion / FAQ ──
        if (tag === 'details' || el.querySelector('details') ||
            cn.includes('accordion') || cn.includes('faq') || cn.includes('collapsible') ||
            cn.includes('expandable')) {
            const detailEls = el.querySelectorAll('details, [class*="accordion-item"], [class*="faq-item"]');
            const expandEls = el.querySelectorAll('[aria-expanded]');
            const itemCount = Math.max(detailEls.length, expandEls.length);
            if (itemCount >= 2 || tag === 'details') {
                const isFAQ = cn.includes('faq') || (el.textContent || '').match(/\\?/g)?.length >= 2;
                const label = isFAQ
                    ? 'FAQ (' + Math.max(itemCount, 1) + ' questions)'
                    : 'Accordion (' + Math.max(itemCount, 1) + ' panels)';
                return { category: 'accordion', label: label, priority: 72 };
            }
        }
        // Also check for [aria-expanded] patterns without accordion class
        if (!cn.includes('nav') && !cn.includes('menu')) {
            const expandPanels = el.querySelectorAll('[aria-expanded]');
            if (expandPanels.length >= 3) {
                const headingsNearby = el.querySelectorAll('h2, h3, h4, button').length;
                if (headingsNearby >= expandPanels.length) {
                    return { category: 'accordion', label: 'Accordion (' + expandPanels.length + ' panels)', priority: 72 };
                }
            }
        }

        // ── 7. Tabs ──
        if (role === 'tablist' || el.querySelector('[role="tablist"]') ||
            cn.includes('tabs') || cn.includes('tab-bar') || cn.includes('tablist')) {
            const tabEls = el.querySelectorAll('[role="tab"], [class*="tab-item"], [class*="tab-link"]');
            const tabCount = tabEls.length || el.querySelectorAll('button, a').length;
            const activeTab = el.querySelector('[aria-selected="true"], [class*="active"], [class*="selected"]');
            const activeLabel = activeTab ? activeTab.textContent.trim().substring(0, 20) : '';
            const label = 'Tabs (' + tabCount + ')' + (activeLabel ? ' — active: "' + activeLabel + '"' : '');
            return { category: 'tabs', label: label, priority: 73 };
        }

        // ── 8. Modal / Dialog ──
        if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||
            cn.includes('modal') || cn.includes('dialog') || cn.includes('lightbox')) {
            const zi = parseInt(s.zIndex) || 0;
            const isOverlay = s.position === 'fixed' || s.position === 'absolute';
            if (isOverlay || zi > 100 || tag === 'dialog') {
                const headingEl = el.querySelector('h1, h2, h3, h4');
                const heading = headingEl ? headingEl.textContent.trim().substring(0, 30) : '';
                const label = heading ? 'Modal — "' + heading + '"' : 'Modal Dialog';
                return { category: 'modal', label: label, priority: 68 };
            }
        }

        // ── 9. Breadcrumb ──
        if (cn.includes('breadcrumb') || role === 'breadcrumb' ||
            el.querySelector('[class*="breadcrumb"]')) {
            const crumbs = el.querySelectorAll('a, span, li').length;
            return { category: 'breadcrumb', label: 'Breadcrumb (' + crumbs + ' levels)', priority: 55 };
        }

        // ── 10. Table / Data Grid ──
        if (tag === 'table' || role === 'grid' || role === 'table' ||
            cn.includes('data-table') || cn.includes('datagrid') || cn.includes('data-grid')) {
            const rows = el.querySelectorAll('tr, [role="row"]').length;
            const cols = el.querySelectorAll('th, [role="columnheader"]').length;
            const isSortable = !!el.querySelector('[aria-sort], [class*="sort"]');
            const detail = [];
            if (rows > 0) detail.push(rows + ' rows');
            if (cols > 0) detail.push(cols + ' columns');
            if (isSortable) detail.push('sortable');
            return { category: 'table', label: 'Data Table' + (detail.length ? ' (' + detail.join(', ') + ')' : ''), priority: 70 };
        }

        // ── 11. Carousel / Slider ──
        if (cn.includes('carousel') || cn.includes('slider') || cn.includes('swiper') ||
            cn.includes('slick') || cn.includes('splide') || cn.includes('glide') ||
            cn.includes('flickity') || role === 'listbox') {
            const slides = el.querySelectorAll('[class*="slide"], [class*="item"], [role="option"]').length;
            const hasDots = !!el.querySelector('[class*="dot"], [class*="pagination"], [class*="indicator"]');
            const hasArrows = !!el.querySelector('[class*="prev"], [class*="next"], [class*="arrow"]');
            const detail = [];
            if (slides > 0) detail.push(slides + ' slides');
            if (hasDots) detail.push('dots');
            if (hasArrows) detail.push('arrows');
            return { category: 'carousel', label: 'Carousel' + (detail.length ? ' (' + detail.join(', ') + ')' : ''), priority: 75 };
        }
        // Overflow-x scroll detection (carousel without library class)
        if (s.overflowX === 'auto' || s.overflowX === 'scroll') {
            const scrollKids = Array.from(el.children).filter(function(c) {
                return c.getBoundingClientRect().width > 80;
            });
            if (scrollKids.length >= 3) {
                const hasArrows = !!el.parentElement?.querySelector('[class*="prev"], [class*="next"], [class*="arrow"]');
                if (hasArrows || scrollKids.length >= 5) {
                    return { category: 'carousel', label: 'Scroll Carousel (' + scrollKids.length + ' items)', priority: 72 };
                }
            }
        }

        // ── 12. Pricing ──
        if (cn.includes('pricing') || cn.includes('plan') || cn.includes('tier')) {
            const priceEls = el.querySelectorAll('[class*="price"], [class*="amount"]');
            const headingEl = el.querySelector('h1, h2, h3');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 40) : '';
            const cardCount = el.querySelectorAll('[class*="plan"], [class*="tier"], [class*="card"]').length;
            return { category: 'pricing', label: 'Pricing' + (cardCount > 1 ? ' (' + cardCount + ' plans)' : '') + (heading ? ' — "' + heading + '"' : ''), priority: 78 };
        }
        // Price detection by content ($/€/£ + /mo or /yr)
        if (!cn.includes('footer') && !cn.includes('nav')) {
            const textContent = (el.textContent || '');
            const priceMatches = textContent.match(/[$€£]\\s*\\d+|\\d+\\/mo|\\d+\\/yr|\\d+\\/month|\\d+\\/year|per month|per year/gi);
            if (priceMatches && priceMatches.length >= 2) {
                const kids2 = Array.from(el.children).filter(function(c) {
                    return c.getBoundingClientRect().height > 100;
                });
                if (kids2.length >= 2) {
                    return { category: 'pricing', label: 'Pricing (' + kids2.length + ' plans)', priority: 76 };
                }
            }
        }

        // ── 13. Timeline ──
        if (cn.includes('timeline') || cn.includes('chronolog') || cn.includes('history')) {
            const items = el.querySelectorAll('[class*="timeline-item"], [class*="event"], li').length;
            return { category: 'timeline', label: 'Timeline (' + items + ' events)', priority: 65 };
        }

        // ── 14. Alert / Banner Notification ──
        if (role === 'alert' || role === 'status' ||
            cn.includes('alert') || cn.includes('notification') || cn.includes('toast') ||
            cn.includes('announcement')) {
            // Only classify if it's small/strip-like, not a full section
            if (rect.height < 150) {
                const headingEl = el.querySelector('h2, h3, h4, strong');
                const text = headingEl ? headingEl.textContent.trim().substring(0, 30) : (el.textContent || '').trim().substring(0, 30);
                const isCloseable = !!el.querySelector('[class*="close"], [class*="dismiss"], button[aria-label*="close" i]');
                return { category: 'alert', label: 'Alert' + (isCloseable ? ' (dismissible)' : '') + ' — "' + text + '"', priority: 60 };
            }
        }

        // ── 15. Stepper / Progress ──
        if (cn.includes('stepper') || cn.includes('wizard') || cn.includes('progress-bar') ||
            cn.includes('step-indicator') || el.querySelector('[aria-current="step"]')) {
            const steps = el.querySelectorAll('[class*="step"], [class*="stage"], li').length;
            const currentStep = el.querySelector('[aria-current="step"], [class*="active"], [class*="current"]');
            const currentLabel = currentStep ? currentStep.textContent.trim().substring(0, 20) : '';
            return { category: 'stepper', label: 'Stepper (' + steps + ' steps)' + (currentLabel ? ' — "' + currentLabel + '"' : ''), priority: 62 };
        }

        // ── 16. Marquee / Ticker ──
        if (cn.includes('marquee') || cn.includes('ticker') || cn.includes('scroll-text') ||
            tag === 'marquee') {
            return { category: 'marquee', label: 'Marquee / Ticker', priority: 55 };
        }
        // Detect CSS animation marquee (overflow hidden + wide inner with translateX animation)
        if (s.overflow === 'hidden' || s.overflowX === 'hidden') {
            const inner = el.children[0];
            if (inner && el.children.length <= 2) {
                var innerS = window.getComputedStyle(inner);
                if (innerS.animationName && innerS.animationName !== 'none' &&
                    inner.scrollWidth > rect.width * 1.5) {
                    return { category: 'marquee', label: 'Scrolling Marquee', priority: 55 };
                }
            }
        }

        // ── 17. Repeating children — smart grid classification ──
        const kids = Array.from(el.children).filter(function(c) {
            var cr = c.getBoundingClientRect();
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
                const sig = function(el2) {
                    var ct = Array.from(el2.children).map(function(c) { return c.tagName; }).sort().join(',');
                    return ct + '|' + (!!el2.querySelector('img')) + '|' + (!!el2.querySelector('a'));
                };
                const ref = sig(group[0]);
                const matching = group.filter(function(el2) { return sig(el2) === ref; });
                if (matching.length >= 3) {
                    const sample = matching[0];
                    const hasImgs = !!sample.querySelector('img, picture');
                    const hasHeadings = !!sample.querySelector('h1,h2,h3,h4');
                    const hasLinks = !!sample.querySelector('a');
                    const hasParagraphs = !!sample.querySelector('p');
                    const hasSvgs = !!sample.querySelector('svg');
                    const sampleText = (sample.textContent || '').trim();
                    const avgTextLen = sampleText.length / Math.max(1, matching.length);
                    const isInline = s.display.includes('flex') && s.flexDirection !== 'column';
                    const isGridLayout = s.display.includes('grid');
                    const itemR = sample.getBoundingClientRect();
                    const isSmallItem = itemR.height < 80 && itemR.width < 200;
                    const isOnlyImgs = hasImgs && !hasHeadings && !hasParagraphs && avgTextLen < 30;

                    // ── Sub-classify the repeating pattern ──
                    var gridLabel, gridCategory;

                    // Testimonial cards — blockquote, quotes in text, or testimonial/review class
                    const sampleCn = ((typeof sample.className === 'string') ? sample.className : '').toLowerCase();
                    const hasBlockquote = !!sample.querySelector('blockquote');
                    const hasQuoteMark = sampleText.includes('\\u201C') || sampleText.includes('\\u201D') || sampleText.includes('"');
                    const isTestimonial = sampleCn.includes('testimonial') || sampleCn.includes('review') || sampleCn.includes('quote');
                    if ((hasBlockquote || isTestimonial || (hasQuoteMark && hasParagraphs)) &&
                        (hasImgs || sample.querySelector('[class*="avatar"]'))) {
                        gridLabel = matching.length + ' Testimonial Cards';
                        gridCategory = 'testimonial';
                    }
                    // Team / People grid — small images (headshots) + short name headings
                    else if (hasImgs && hasHeadings) {
                        const img = sample.querySelector('img');
                        const imgRect = img ? img.getBoundingClientRect() : null;
                        const isAvatar = imgRect && (imgRect.width < 200 || imgRect.height < 200);
                        const headingText = (sample.querySelector('h2,h3,h4') || {}).textContent || '';
                        const isShortName = headingText.trim().split(/\\s+/).length <= 4;
                        const hasRole = !!sample.querySelector('p, span, [class*="role"], [class*="title"], [class*="position"]');

                        if (isAvatar && isShortName && hasRole &&
                            (sampleCn.includes('team') || sampleCn.includes('member') || sampleCn.includes('people') || sampleCn.includes('staff') || isAvatar)) {
                            gridLabel = matching.length + '-Person Team Grid';
                            gridCategory = 'content_grid';
                        }
                        // Blog post grid — images + headings + date/author meta
                        else if (sample.querySelector('time, [class*="date"], [class*="meta"], [class*="author"], [datetime]') &&
                                 hasParagraphs) {
                            gridLabel = matching.length + ' Blog Post Cards';
                            gridCategory = 'content_grid';
                        }
                        // Full feature cards: image + heading + description paragraph
                        else if (hasParagraphs) {
                            gridLabel = matching.length + ' Feature Cards';
                            gridCategory = 'content_grid';
                        }
                        // Product cards: image + heading (no body text)
                        else {
                            gridLabel = matching.length + ' Product Cards';
                            gridCategory = 'content_grid';
                        }
                    }
                    // Stat counters — large numbers with labels
                    else if (isSmallItem && !hasImgs && !hasHeadings && avgTextLen < 50) {
                        // Check if text looks like numbers/stats
                        const firstText = (matching[0].textContent || '').trim();
                        const hasNumber = /\\d/.test(firstText);
                        gridLabel = hasNumber
                            ? matching.length + ' Stat Counters'
                            : matching.length + ' Metric Tags';
                        gridCategory = 'content_grid';
                    }
                    // Logo / partner bar — row of images with no text
                    else if (isOnlyImgs && isInline && !hasHeadings) {
                        gridLabel = matching.length + '-Logo Partner Bar';
                        gridCategory = 'content_grid';
                    }
                    // Icon grid — SVGs/small images + short labels
                    else if ((hasSvgs || hasImgs) && !hasParagraphs && avgTextLen < 60) {
                        const firstImg = sample.querySelector('img, svg');
                        const imgR = firstImg ? firstImg.getBoundingClientRect() : null;
                        if (imgR && imgR.width < 64 && imgR.height < 64) {
                            gridLabel = matching.length + ' Icon Grid';
                            gridCategory = 'content_grid';
                        } else {
                            gridLabel = matching.length + '-Image Gallery';
                            gridCategory = 'content_grid';
                        }
                    }
                    // Linked images = gallery or portfolio
                    else if (hasImgs && hasLinks && !hasHeadings) {
                        gridLabel = matching.length + '-Image Gallery';
                        gridCategory = 'content_grid';
                    }
                    // Text feature list — heading + body, no images
                    else if (hasHeadings && hasParagraphs && !hasImgs) {
                        gridLabel = matching.length + ' Feature List';
                        gridCategory = 'content_grid';
                    }
                    // Heading-only group = link list or nav group
                    else if (hasHeadings && !hasImgs) {
                        gridLabel = matching.length + ' Link Group';
                        gridCategory = 'content_grid';
                    }
                    // Images only, no links = icon/logo row
                    else if (hasImgs && !hasHeadings && !hasLinks) {
                        gridLabel = matching.length + ' Icon/Logo Row';
                        gridCategory = 'content_grid';
                    }
                    // Fallback — describe what's inside
                    else {
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
                        priority: gridCategory === 'testimonial' ? 74 : 80,
                        meta: { itemCount: matching.length, hasImages: hasImgs, hasHeadings: hasHeadings, layout: isGridLayout ? 'grid' : isInline ? 'row' : 'stack' }
                    };
                }
            }
        }

        // ── 18. Testimonial / Quote (standalone, not grid) ──
        if (el.querySelector('blockquote, [class*="testimonial"], [class*="quote"]') ||
            cn.includes('testimonial') || cn.includes('quote') || cn.includes('review')) {
            const hasAvatar = !!el.querySelector('img, [class*="avatar"]');
            const label = hasAvatar ? 'Testimonial (with avatar)' : 'Testimonial / Quote';
            return { category: 'testimonial', label: label, priority: 65 };
        }

        // ── 19. CTA Banner strip ──
        if (rect.height < 200 && rect.width > vw * 0.7) {
            const btns = el.querySelectorAll('button, a[href]').length;
            const headingEl = el.querySelector('h1, h2, h3, h4');
            if (btns >= 1 && headingEl) {
                return { category: 'cta', label: 'CTA Banner — "' + headingEl.textContent.trim().substring(0, 40) + '"', priority: 65 };
            }
        }

        // ── 20. Split Content (text + image side-by-side) ──
        if (tag === 'section' || tag === 'div' || tag === 'article') {
            const directKids = Array.from(el.children).filter(function(c) {
                var cr = c.getBoundingClientRect();
                return cr.width > 100 && cr.height > 50;
            });
            if (directKids.length === 2 && (s.display.includes('flex') || s.display.includes('grid'))) {
                const hasImgSide = directKids.some(function(k) { return !!k.querySelector('img, video, picture'); });
                const hasTextSide = directKids.some(function(k) { return !!k.querySelector('h1, h2, h3') && !!k.querySelector('p'); });
                if (hasImgSide && hasTextSide) {
                    const headingEl = el.querySelector('h1, h2, h3');
                    const heading = headingEl ? headingEl.textContent.trim().substring(0, 40) : '';
                    return { category: 'split_content', label: 'Split Content' + (heading ? ' — "' + heading + '"' : ''), priority: 68 };
                }
            }
        }

        // ── 21. Newsletter Section ──
        if (cn.includes('newsletter') || cn.includes('subscribe') || cn.includes('signup')) {
            const hasEmail = !!el.querySelector('input[type="email"], input[name*="email"]');
            if (hasEmail) {
                return { category: 'newsletter', label: 'Newsletter Signup', priority: 66 };
            }
        }
        // Also detect by content pattern (email input + submit, no password)
        if (!cn.includes('login') && !cn.includes('auth')) {
            const emailInput = el.querySelector('input[type="email"]');
            const submitBtn = el.querySelector('button[type="submit"], button');
            const passwordInput = el.querySelector('input[type="password"]');
            if (emailInput && submitBtn && !passwordInput && rect.height < 300) {
                return { category: 'newsletter', label: 'Newsletter Signup', priority: 64 };
            }
        }

        // ── 22. Social Proof ──
        if (cn.includes('social-proof') || cn.includes('trusted') || cn.includes('partners') ||
            cn.includes('clients') || cn.includes('as-seen') || cn.includes('press')) {
            const logoCount = el.querySelectorAll('img, svg').length;
            return { category: 'social_proof', label: 'Social Proof' + (logoCount > 2 ? ' (' + logoCount + ' logos)' : ''), priority: 63 };
        }
        // Detect by "trusted by" text pattern
        if (!cn.includes('footer')) {
            const elText = (el.textContent || '').toLowerCase();
            if ((elText.includes('trusted by') || elText.includes('used by') ||
                 elText.includes('as seen') || elText.includes('our partners') ||
                 elText.includes('our clients')) && rect.height < 300) {
                const logoCount = el.querySelectorAll('img, svg').length;
                if (logoCount >= 3) {
                    return { category: 'social_proof', label: 'Social Proof (' + logoCount + ' logos)', priority: 63 };
                }
            }
        }

        // ── 23. Generic section (improved) ──
        if (tag === 'section' || tag === 'main' || tag === 'article' ||
            role === 'main' || role === 'region') {
            const headingEl = el.querySelector('h1, h2, h3');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
            const imgCount = el.querySelectorAll('img, picture').length;
            const linkCount = el.querySelectorAll('a').length;
            const btnCount = el.querySelectorAll('button, a[href]').length;

            if (tag === 'article') {
                return { category: 'section', label: heading ? 'Article — "' + heading + '"' : 'Article', priority: 55 };
            }

            // CTA section — heading + buttons, minimal other content
            if (heading && btnCount >= 1 && btnCount <= 3 && imgCount <= 1 && linkCount < 10 && rect.height < vh * 0.6) {
                return { category: 'cta', label: 'CTA Section — "' + heading + '"', priority: 64 };
            }

            // Feature spotlight — heading + single large image + description
            if (heading && imgCount === 1 && el.querySelector('p') && rect.height > 200) {
                const img = el.querySelector('img, picture');
                if (img) {
                    const imgR = img.getBoundingClientRect();
                    if (imgR.width > 300 || imgR.height > 200) {
                        return { category: 'section', label: 'Feature Spotlight — "' + heading + '"', priority: 58 };
                    }
                }
            }

            const detail = [];
            if (imgCount > 3) detail.push(imgCount + ' images');
            if (linkCount > 5) detail.push(linkCount + ' links');
            const suffix = detail.length ? ' (' + detail.join(', ') + ')' : '';
            const label = heading ? '"' + heading + '"' + suffix : 'Content Section' + suffix;
            return { category: 'section', label: label, priority: 50 };
        }

        // ── 24. Aside / sidebar ──
        if (tag === 'aside' || role === 'complementary') {
            const headingEl = el.querySelector('h2, h3, h4');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 40) : null;
            return { category: 'sidebar', label: heading ? 'Sidebar — "' + heading + '"' : 'Sidebar', priority: 60 };
        }

        // ── 25. Large div fallback ──
        if (rect.width > vw * 0.5 && rect.height > 100 && kids.length >= 2) {
            const headingEl = el.querySelector('h1, h2, h3, h4');
            const heading = headingEl ? headingEl.textContent.trim().substring(0, 50) : null;
            const imgCount = el.querySelectorAll('img, picture').length;
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

    // Scan semantic elements + large visible divs + interactive elements
    // Uses window.__queryShadowAll (injected by ComponentRipper._inject_shadow_utils) so
    // components inside <template> content and open shadow DOMs are included.
    const _qsa = (typeof window.__queryShadowAll === 'function')
        ? window.__queryShadowAll.bind(window)
        : (sel) => Array.from(document.querySelectorAll(sel));  // safe fallback

    const candidates = [
        ..._qsa('nav, header, footer, main, section, article, aside, form, dialog, details, table, [role="navigation"], [role="banner"], [role="main"], [role="contentinfo"], [role="region"], [role="complementary"], [role="tablist"], [role="dialog"], [role="alertdialog"], [role="alert"], [role="grid"], [role="table"]'),
        ..._qsa('div').filter(function(d) {
            var r = d.getBoundingClientRect();
            return r.width > vw * 0.4 && r.height > 80 && d.children.length >= 2;
        }),
        // Also scan smaller divs that might be interactive components
        ..._qsa('div[class*="accordion"], div[class*="tabs"], div[class*="carousel"], div[class*="slider"], div[class*="pricing"], div[class*="timeline"], div[class*="stepper"], div[class*="marquee"], div[class*="faq"], div[class*="breadcrumb"], div[class*="testimonial"], div[class*="newsletter"], div[class*="social-proof"], div[class*="trusted"], div[class*="alert"], div[class*="notification"]')
    ];

    for (const el of candidates) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        // Skip mega-elements (entire page wrappers) — not useful as patterns
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
    results.sort(function(a, b) {
        var aThird = Math.floor(a.bounds.top / (vh / 3));
        var bThird = Math.floor(b.bounds.top / (vh / 3));
        if (aThird !== bThird) return aThird - bThird;
        return b.priority - a.priority;
    });

    // Deduplicate overlapping elements (keep higher priority, preserve different categories)
    const filtered = [];
    for (const comp of results) {
        const dominated = filtered.some(function(existing) {
            if (comp.category !== existing.category) return false;
            var overlap =
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
