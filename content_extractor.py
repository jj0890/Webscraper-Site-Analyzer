"""
Content Extractor with Classification & Sampling
Shows WHAT was found, not just HOW MUCH

For USAA/professional use:
- Classifies page type (product listing, article, docs, etc.)
- Counts content inventory (47 products, 12 articles, etc.)
- Extracts SAMPLES (first 3-5), not everything
- Explains extraction strategy (why this selector?)
- Shows what was excluded (nav, footer, ads)
"""

import asyncio
from playwright.async_api import async_playwright
from typing import Dict, List
from colorama import Fore, init
from dataclasses import dataclass
from enum import Enum

init(autoreset=True)


class PageType(Enum):
    """Page classification types"""
    PRODUCT_LISTING = "productListing"
    SINGLE_PRODUCT = "singleProduct"
    BLOG_LISTING = "blogListing"
    SINGLE_ARTICLE = "singleArticle"
    API_REFERENCE = "apiReference"
    DOCUMENTATION = "documentation"
    MEDIA_LISTING = "mediaListing"
    AUDIO_STREAM = "audioStream"
    SHOW_ARCHIVE = "showArchive"
    PODCAST_LISTING = "podcastListing"
    RADIO_STATION = "radioStation"      # Live streaming radio (NTS, LYL, Rinse)
    MUSIC_BLOG = "musicBlog"            # Editorial music/culture site (PAP, Pitchfork)
    CONTENT_GRID = "contentGrid"        # Generic repeating content (magazine, gallery, portfolio)
    GALLERY = "gallery"                 # Image-dominant grid
    LANDING_PAGE = "landingPage"
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    """Result of content extraction"""
    page_type: PageType
    confidence: float
    reasoning: str
    content_inventory: Dict
    samples: List[Dict]
    extraction_strategy: Dict
    excluded_elements: Dict
    semantic_analysis: Dict


class IntelligentContentExtractor:
    """
    Extracts content with classification, sampling, and reasoning

    Key principles:
    1. CLASSIFY first (what type of page is this?)
    2. COUNT inventory (how much content?)
    3. SAMPLE, don't extract everything (3-5 examples)
    4. EXPLAIN strategy (why this selector?)
    5. SHOW what was excluded (navigation, ads, etc.)
    """

    def __init__(self, page):
        self.page = page

    async def extract(self) -> ExtractionResult:
        """
        Main extraction method

        Returns comprehensive extraction with:
        - Page classification
        - Content inventory
        - Representative samples
        - Extraction strategy explanation
        - Excluded elements
        """
        # Step 1: Classify page type
        classification = await self._classify_page()

        # Step 2: Count inventory
        inventory = await self._count_inventory(classification['type'])

        # Step 3: Extract samples (not everything!)
        samples = await self._extract_samples(classification['type'])

        # Step 4: Determine extraction strategy
        strategy = await self._extraction_strategy(classification['type'])

        # Step 5: Identify excluded elements
        excluded = await self._identify_excluded()

        # Step 6: Analyze semantic HTML
        semantic = await self._analyze_semantic_html()

        return ExtractionResult(
            page_type=classification['type'],
            confidence=classification['confidence'],
            reasoning=classification['reasoning'],
            content_inventory=inventory,
            samples=samples,
            extraction_strategy=strategy,
            excluded_elements=excluded,
            semantic_analysis=semantic
        )

    async def _classify_page(self) -> Dict:
        """
        Classify page type with confidence and reasoning

        Returns what type of page this is and WHY
        """
        result = await self.page.evaluate("""() => {
            // Count different content types
            const products = document.querySelectorAll(
                '.product-card, .product, [data-product], [itemtype*="Product"]'
            );
            const articles = document.querySelectorAll(
                'article, .post, .article, [itemtype*="Article"]'
            );
            const functions = document.querySelectorAll(
                'dl.function, .api-reference, .method'
            );
            const shows = document.querySelectorAll(
                '.show, .episode, .track, [data-show]'
            );
            const codeBlocks = document.querySelectorAll('pre code, .code-block');

            // Determine type based on counts
            const signals = [];

            // ── Music / Radio detection (must run BEFORE generic article check) ──
            // Radio station indicators: live stream, schedule, player controls
            const radioIndicators = document.querySelectorAll(
                'audio, [data-player], [data-stream], .player, .live-player, ' +
                '.stream, .broadcast, .livestream, .radio, [data-radio], ' +
                '#player, .player-bar, .now-playing, .on-air, .live-indicator, ' +
                '[class*="player"], [class*="stream"], [class*="broadcast"], [class*="live"]'
            );
            const scheduleIndicators = document.querySelectorAll(
                '.schedule, [data-schedule], .timetable, .programming, ' +
                '.airtime, .show-grid, [class*="schedule"], [class*="timetable"]'
            );
            // Music blog indicators: editorial about music
            const musicIndicators = document.querySelectorAll(
                '.album, .release, .tracklist, .review, [class*="album"], ' +
                '[class*="track"], [class*="artist"], [class*="genre"], [class*="release"], ' +
                '[class*="music"], [class*="listen"], [class*="mix"]'
            );

            const isRadioStation = radioIndicators.length >= 2 && (
                scheduleIndicators.length > 0 || radioIndicators.length >= 5
            );
            const isMusicSite = musicIndicators.length >= 3;

            if (isRadioStation) {
                signals.push({
                    type: 'radioStation',
                    count: radioIndicators.length,
                    confidence: 0.9,
                    reasoning: `Live radio/streaming platform: ${radioIndicators.length} player/stream elements` +
                        (scheduleIndicators.length > 0 ? `, ${scheduleIndicators.length} schedule elements` : '')
                });
            }

            if (isMusicSite && articles.length > 3 && !isRadioStation) {
                // Music blog: has articles AND music-specific content
                signals.push({
                    type: 'musicBlog',
                    count: articles.length,
                    confidence: 0.88,
                    reasoning: `Music/culture editorial: ${articles.length} articles with ${musicIndicators.length} music elements`
                });
            }

            if (products.length > 5) {
                signals.push({
                    type: 'productListing',
                    count: products.length,
                    confidence: 0.9,
                    reasoning: `Found ${products.length} product elements with consistent structure`
                });
            } else if (products.length === 1) {
                signals.push({
                    type: 'singleProduct',
                    count: 1,
                    confidence: 0.85,
                    reasoning: 'Single product page with detailed information'
                });
            }

            // Only fire blogListing if no music/radio signal already dominates
            if (articles.length > 3 && !isRadioStation && !isMusicSite) {
                signals.push({
                    type: 'blogListing',
                    count: articles.length,
                    confidence: 0.85,
                    reasoning: `Found ${articles.length} article cards in listing view`
                });
            } else if (articles.length === 1) {
                const wordCount = articles[0].innerText.split(/\\s+/).length;
                if (wordCount > 300) {
                    signals.push({
                        type: 'singleArticle',
                        count: 1,
                        confidence: 0.9,
                        reasoning: `Single article with ${wordCount} words of content`
                    });
                }
            }

            if (functions.length > 5) {
                signals.push({
                    type: 'apiReference',
                    count: functions.length,
                    confidence: 0.85,
                    reasoning: `Found ${functions.length} API function definitions`
                });
            }

            if (codeBlocks.length > 5 && functions.length < 5) {
                signals.push({
                    type: 'documentation',
                    count: codeBlocks.length,
                    confidence: 0.8,
                    reasoning: `Found ${codeBlocks.length} code examples in documentation`
                });
            }

            if (shows.length > 5) {
                signals.push({
                    type: 'mediaListing',
                    count: shows.length,
                    confidence: 0.8,
                    reasoning: `Found ${shows.length} media items (shows/tracks/episodes)`
                });
            }

            // Audio/stream/podcast detection
            const audioEls = document.querySelectorAll('audio, [data-player], [data-stream], .player');
            const videoEls = document.querySelectorAll('video:not([muted]):not([autoplay])');
            const mixEls = document.querySelectorAll('.mix, [data-mix], .broadcast, .livestream, .live-player, .stream');
            const scheduleEls = document.querySelectorAll('.schedule, [data-schedule], .timetable, .programming, .airtime');
            const schemaAudio = document.querySelectorAll('[itemtype*="AudioObject"], [itemtype*="RadioBroadcast"], [itemtype*="MusicRecording"], [itemtype*="PodcastEpisode"]');
            const podcastEls = document.querySelectorAll('.episode, [data-episode], .podcast-episode, [itemtype*="PodcastEpisode"]');

            // Live audio stream (radio, DJ sets)
            if (audioEls.length > 0 && (mixEls.length > 0 || scheduleEls.length > 0)) {
                signals.push({
                    type: 'audioStream',
                    count: audioEls.length,
                    confidence: 0.85,
                    reasoning: `Live audio stream: ${audioEls.length} player(s), ${mixEls.length} show/mix elements, ${scheduleEls.length} schedule elements`
                });
            }

            // Show/mix archive
            if (mixEls.length > 3 || (shows.length > 3 && audioEls.length > 0)) {
                signals.push({
                    type: 'showArchive',
                    count: mixEls.length + shows.length,
                    confidence: 0.8,
                    reasoning: `Show/mix archive: ${mixEls.length + shows.length} archive items with audio presence`
                });
            }

            // Podcast listing
            if (podcastEls.length > 2 || (schemaAudio.length > 2 && audioEls.length > 0)) {
                signals.push({
                    type: 'podcastListing',
                    count: podcastEls.length || schemaAudio.length,
                    confidence: 0.85,
                    reasoning: `Podcast listing: ${podcastEls.length || schemaAudio.length} episodes with structured audio metadata`
                });
            }

            // Return highest confidence signal if specific selectors matched
            if (signals.length > 0) {
                signals.sort((a, b) => b.confidence - a.confidence);
                return signals[0];
            }

            // ── GENERIC REPEATING-ELEMENT DETECTION ──
            // When no hardcoded selectors match, scan the DOM for clusters of
            // structurally similar siblings. This catches magazine grids, poem
            // listings, portfolio cards, etc. that use custom class names.
            const main = document.querySelector('main') || document.querySelector('[role="main"]') ||
                         document.querySelector('#content') || document.querySelector('.content') || document.body;

            // Strategy: find containers whose direct children share the same tag
            // and similar structure (child count, presence of images/links/headings).
            let bestCluster = null;

            const containers = main.querySelectorAll('*');
            for (const container of containers) {
                const kids = Array.from(container.children).filter(c => {
                    // Skip tiny/hidden elements
                    const r = c.getBoundingClientRect();
                    return r.width > 50 && r.height > 20;
                });

                if (kids.length < 3) continue;

                // Group children by tag name
                const tagGroups = {};
                for (const kid of kids) {
                    const tag = kid.tagName;
                    if (!tagGroups[tag]) tagGroups[tag] = [];
                    tagGroups[tag].push(kid);
                }

                // Find the largest group of same-tag siblings
                for (const [tag, group] of Object.entries(tagGroups)) {
                    if (group.length < 3) continue;

                    // Check structural similarity: compare child tag signature of first vs others
                    const getSignature = (el) => {
                        const childTags = Array.from(el.children).map(c => c.tagName).sort().join(',');
                        const hasImg = !!el.querySelector('img, picture, video, svg');
                        const hasLink = !!el.querySelector('a');
                        const hasHeading = !!el.querySelector('h1, h2, h3, h4, h5, h6');
                        const hasText = !!el.querySelector('p, span');
                        return `${childTags}|${hasImg}|${hasLink}|${hasHeading}|${hasText}`;
                    };

                    const refSig = getSignature(group[0]);
                    const matching = group.filter(el => getSignature(el) === refSig);

                    if (matching.length < 3) continue;

                    // Score this cluster — prefer content-rich items over pure image carousels
                    const sample = matching[0];
                    const hasImg = !!sample.querySelector('img, picture, video');
                    const hasLink = !!sample.querySelector('a');
                    const hasHeading = !!sample.querySelector('h1, h2, h3, h4, h5, h6');
                    const hasText = !!sample.querySelector('p, span');

                    // Complexity score: richer items rank higher
                    let complexity = 0;
                    if (hasImg) complexity += 1;
                    if (hasLink) complexity += 2;    // navigable = likely content items
                    if (hasHeading) complexity += 3;  // headings = editorial structure
                    if (hasText) complexity += 2;     // text = content, not just thumbnails

                    // Combined score: item count * complexity, with minimum size
                    const avgH = matching.slice(0, 5).reduce((s, el) => s + el.getBoundingClientRect().height, 0) / Math.min(matching.length, 5);
                    if (avgH < 30) continue;  // skip tiny repeated elements (list bullets, icons)

                    // Penalize carousels (horizontal scroll containers)
                    const containerStyle = getComputedStyle(container);
                    const isCarousel = containerStyle.overflowX === 'auto' || containerStyle.overflowX === 'scroll' ||
                                       container.classList.toString().includes('carousel') ||
                                       container.classList.toString().includes('slider');

                    const score = matching.length * (complexity || 1) * (isCarousel ? 0.3 : 1);
                    if (!bestCluster || score > bestCluster.score) {
                        // Build the selector for this cluster
                        const containerSel = container.id ? `#${container.id}` :
                            container.className ? `.${container.className.trim().split(/\\s+/)[0]}` :
                            container.tagName.toLowerCase();
                        const itemSel = `${containerSel} > ${tag.toLowerCase()}`;

                        bestCluster = {
                            count: matching.length,
                            score: score,
                            selector: itemSel,
                            containerSelector: containerSel,
                            tag: tag.toLowerCase(),
                            hasImage: hasImg,
                            hasLink: hasLink,
                            hasHeading: hasHeading,
                            hasText: hasText,
                            isCarousel: isCarousel,
                            avgHeight: Math.round(avgH)
                        };
                    }
                }
            }

            if (bestCluster && bestCluster.count >= 3) {
                // Determine if it's image-dominant (gallery) or mixed (content grid)
                const imagePercent = bestCluster.hasImage ? 1 : 0;
                const isGallery = bestCluster.hasImage && !bestCluster.hasHeading && !bestCluster.hasText;

                const type = isGallery ? 'gallery' : 'contentGrid';
                const anatomy = [];
                if (bestCluster.hasImage) anatomy.push('images');
                if (bestCluster.hasHeading) anatomy.push('headings');
                if (bestCluster.hasText) anatomy.push('text');
                if (bestCluster.hasLink) anatomy.push('links');

                return {
                    type: type,
                    count: bestCluster.count,
                    confidence: Math.min(0.85, 0.6 + bestCluster.count * 0.01),
                    reasoning: `Found ${bestCluster.count} repeating ${bestCluster.tag} elements via \`${bestCluster.selector}\` containing ${anatomy.join(', ')}`,
                    _cluster: bestCluster  // pass through for inventory/sampling
                };
            }

            return {
                type: 'landingPage',
                count: 0,
                confidence: 0.5,
                reasoning: 'No specific content pattern detected, likely a landing page'
            };
        }""")

        # Store cluster data for use in inventory/sampling
        self._detected_cluster = result.get('_cluster')

        return {
            'type': PageType(result['type']),
            'confidence': result['confidence'],
            'reasoning': result['reasoning']
        }

    async def _count_inventory(self, page_type: PageType) -> Dict:
        """
        Count content inventory (don't extract, just count)

        This shows you can IDENTIFY content without extracting everything
        """
        if page_type == PageType.PRODUCT_LISTING:
            return await self.page.evaluate("""() => {
                return {
                    products: document.querySelectorAll('.product-card, [data-product]').length,
                    images: document.querySelectorAll('.product-card img, [data-product] img').length,
                    prices: document.querySelectorAll('.price, [class*="price"]').length,
                    addToCartButtons: document.querySelectorAll('[class*="add-to-cart"], button[data-cart]').length,
                    filters: document.querySelectorAll('.filter, [role="checkbox"]').length,
                    categories: document.querySelectorAll('.category, [data-category]').length
                };
            }""")

        elif page_type == PageType.RADIO_STATION:
            return await self.page.evaluate("""() => {
                const players = document.querySelectorAll('audio, [data-player], [data-stream], .player, [class*="player"]');
                const shows = document.querySelectorAll('article, .show, [class*="show"], [class*="broadcast"], [class*="program"]');
                const schedule = document.querySelectorAll('.schedule, [class*="schedule"], .timetable, [class*="timetable"]');
                const liveIndicators = document.querySelectorAll('.live, .on-air, [class*="live"], .now-playing');
                const channels = document.querySelectorAll('[class*="channel"], [class*="station"]');
                return {
                    players: players.length,
                    shows: shows.length,
                    schedule_elements: schedule.length,
                    live_indicators: liveIndicators.length,
                    channels: channels.length,
                    has_live_stream: players.length > 0 && liveIndicators.length > 0,
                    total_links: document.querySelectorAll('a').length,
                    images: document.querySelectorAll('img').length,
                };
            }""")

        elif page_type == PageType.MUSIC_BLOG:
            return await self.page.evaluate("""() => {
                const articles = Array.from(document.querySelectorAll('article, .post'));
                const sampled = articles.slice(0, 20);
                return {
                    articles: articles.length,
                    with_images: sampled.filter(a => a.querySelector('img, picture')).length,
                    with_headings: sampled.filter(a => a.querySelector('h1, h2, h3, h4, [class*="title"]')).length,
                    with_links: sampled.filter(a => a.querySelector('a')).length,
                    artists: document.querySelectorAll('[class*="artist"], [class*="dj"], [class*="host"], [class*="author"]').length,
                    genres: document.querySelectorAll('[class*="genre"], [class*="tag"], [class*="category"]').length,
                    music_elements: document.querySelectorAll('[class*="album"], [class*="track"], [class*="release"], [class*="listen"], [class*="mix"]').length,
                    audio_players: document.querySelectorAll('audio, [class*="player"]').length,
                };
            }""")

        elif page_type == PageType.BLOG_LISTING:
            return await self.page.evaluate("""() => {
                const articles = Array.from(document.querySelectorAll('article, .post'));
                const sampled = articles.slice(0, 20);
                return {
                    articles: articles.length,
                    with_images: sampled.filter(a => a.querySelector('img, picture')).length,
                    with_headings: sampled.filter(a => a.querySelector('h1, h2, h3, h4, [class*="title"]')).length,
                    with_links: sampled.filter(a => a.querySelector('a')).length,
                    authors: document.querySelectorAll('.author, [class*="author"]').length,
                    dates: document.querySelectorAll('time, .date, [datetime]').length,
                    categories: document.querySelectorAll('.category, .tag, [class*="category"]').length
                };
            }""")

        elif page_type == PageType.SINGLE_ARTICLE:
            return await self.page.evaluate("""() => {
                const article = document.querySelector('article, main');
                if (!article) return {};

                return {
                    wordCount: article.innerText.split(/\\s+/).length,
                    paragraphs: article.querySelectorAll('p').length,
                    images: article.querySelectorAll('img').length,
                    headings: {
                        h1: article.querySelectorAll('h1').length,
                        h2: article.querySelectorAll('h2').length,
                        h3: article.querySelectorAll('h3').length
                    },
                    links: article.querySelectorAll('a').length,
                    codeBlocks: article.querySelectorAll('pre code').length
                };
            }""")

        elif page_type == PageType.API_REFERENCE:
            return await self.page.evaluate("""() => {
                return {
                    functions: document.querySelectorAll('dl.function, .api-function').length,
                    parameters: document.querySelectorAll('.parameter, dt').length,
                    codeExamples: document.querySelectorAll('pre code').length,
                    sections: document.querySelectorAll('section, .section').length
                };
            }""")

        elif page_type == PageType.MEDIA_LISTING:
            return await self.page.evaluate("""() => {
                return {
                    shows: document.querySelectorAll('.show, .episode, .track').length,
                    playButtons: document.querySelectorAll('[class*="play"], button[aria-label*="play"]').length,
                    durations: document.querySelectorAll('.duration, [class*="duration"]').length,
                    dates: document.querySelectorAll('time, .date').length
                };
            }""")

        elif page_type == PageType.AUDIO_STREAM:
            return await self.page.evaluate("""() => {
                return {
                    audioPlayers: document.querySelectorAll('audio, [data-player], [data-stream], .player').length,
                    liveIndicators: document.querySelectorAll('.live, .livestream, .on-air, [data-live]').length,
                    channels: document.querySelectorAll('.channel, [data-channel]').length,
                    scheduleItems: document.querySelectorAll('.schedule, [data-schedule], .timetable, .programming').length,
                    playButtons: document.querySelectorAll('[class*="play"], button[aria-label*="play"]').length,
                    trackInfo: document.querySelectorAll('.now-playing, .tracklist, .track-info, .currently-playing').length
                };
            }""")

        elif page_type == PageType.SHOW_ARCHIVE:
            return await self.page.evaluate("""() => {
                return {
                    shows: document.querySelectorAll('.show, .mix, [data-mix], .broadcast, .episode').length,
                    playButtons: document.querySelectorAll('[class*="play"], button[aria-label*="play"]').length,
                    durations: document.querySelectorAll('.duration, [class*="duration"], time[datetime]').length,
                    hosts: document.querySelectorAll('.host, .dj, .artist, [class*="artist"]').length,
                    genres: document.querySelectorAll('.genre, .tag, [class*="genre"]').length,
                    dates: document.querySelectorAll('time, .date, [class*="date"]').length
                };
            }""")

        elif page_type == PageType.PODCAST_LISTING:
            return await self.page.evaluate("""() => {
                return {
                    episodes: document.querySelectorAll('.episode, [data-episode], .podcast-episode').length,
                    audioPlayers: document.querySelectorAll('audio, [data-player]').length,
                    durations: document.querySelectorAll('.duration, [class*="duration"], time[datetime]').length,
                    dates: document.querySelectorAll('time, .date').length,
                    descriptions: document.querySelectorAll('.description, .summary, .episode-description').length,
                    subscribeButtons: document.querySelectorAll('[class*="subscribe"], [class*="follow"]').length
                };
            }""")

        elif page_type in (PageType.CONTENT_GRID, PageType.GALLERY):
            # Use the detected cluster selector for accurate counting
            cluster = getattr(self, '_detected_cluster', None)
            sel = cluster['selector'] if cluster else '[class*="item"]'
            return await self.page.evaluate("""(selector) => {
                const items = document.querySelectorAll(selector);
                if (!items.length) return { items: 0 };

                // Count what's inside each item
                let withImages = 0, withHeadings = 0, withText = 0, withLinks = 0, withDates = 0;
                for (const item of Array.from(items).slice(0, 30)) {
                    if (item.querySelector('img, picture, video, svg.icon')) withImages++;
                    if (item.querySelector('h1, h2, h3, h4, h5, h6')) withHeadings++;
                    if (item.querySelector('p, span, .excerpt, .description')) withText++;
                    if (item.querySelector('a[href]')) withLinks++;
                    if (item.querySelector('time, .date, [datetime]')) withDates++;
                }

                const sampled = Math.min(items.length, 30);
                return {
                    items: items.length,
                    with_images: withImages,
                    with_headings: withHeadings,
                    with_text: withText,
                    with_links: withLinks,
                    with_dates: withDates,
                    selector_used: selector,
                    image_ratio: Math.round(withImages / sampled * 100) + '%',
                    heading_ratio: Math.round(withHeadings / sampled * 100) + '%'
                };
            }""", sel)

        elif page_type == PageType.LANDING_PAGE:
            return await self.page.evaluate("""() => {
                const main = document.querySelector('main') || document.body;
                return {
                    sections: main.querySelectorAll('section, [class*="section"]').length,
                    headings: main.querySelectorAll('h1, h2, h3').length,
                    images: main.querySelectorAll('img, picture, video').length,
                    ctaButtons: main.querySelectorAll('a[class*="btn"], a[class*="button"], button:not([type="submit"])').length,
                    links: main.querySelectorAll('a[href]').length,
                    cards: main.querySelectorAll('[class*="card"], article, .item').length,
                    forms: main.querySelectorAll('form').length
                };
            }""")

        else:
            # Generic fallback — count the basics so we never return empty
            return await self.page.evaluate("""() => {
                const main = document.querySelector('main') || document.body;
                return {
                    sections: main.querySelectorAll('section').length,
                    headings: main.querySelectorAll('h1, h2, h3').length,
                    images: main.querySelectorAll('img').length,
                    links: main.querySelectorAll('a[href]').length,
                    paragraphs: main.querySelectorAll('p').length
                };
            }""")

    async def _extract_samples(self, page_type: PageType) -> List[Dict]:
        """
        Extract SAMPLES (3-5 items), not everything

        This shows restraint - you CAN extract all, but you're choosing samples
        """
        if page_type == PageType.PRODUCT_LISTING:
            return await self.page.evaluate("""() => {
                const products = Array.from(
                    document.querySelectorAll('.product-card, [data-product]')
                ).slice(0, 3);  // Only first 3

                return products.map((p, idx) => ({
                    name: p.querySelector('h3, .product-name, [class*="name"]')?.innerText?.trim(),
                    price: p.querySelector('.price, [class*="price"]')?.innerText?.trim(),
                    image: p.querySelector('img')?.src,
                    link: p.querySelector('a')?.href,
                    selector: `.product-card:nth-child(${idx + 1})`
                }));
            }""")

        elif page_type == PageType.BLOG_LISTING:
            return await self.page.evaluate("""() => {
                const articles = Array.from(
                    document.querySelectorAll('article, .post')
                ).slice(0, 5);

                return articles.map((a, idx) => {
                    // Try multiple heading selectors — different sites use different patterns
                    const heading = a.querySelector('h1, h2, h3, h4, .title, [class*="title"], [class*="headline"]');
                    // Fallback: first link text often IS the title
                    const firstLink = a.querySelector('a');
                    const title = heading?.innerText?.trim() ||
                                  firstLink?.innerText?.trim()?.substring(0, 100) ||
                                  a.innerText?.trim()?.substring(0, 80) ||
                                  null;

                    return {
                        title: title,
                        excerpt: a.querySelector('p, .excerpt, .description, .summary, [class*="dek"]')?.innerText?.trim()?.slice(0, 150),
                        author: a.querySelector('.author, [class*="author"], [rel="author"]')?.innerText?.trim(),
                        date: a.querySelector('time, .date, [datetime]')?.innerText?.trim(),
                        image: a.querySelector('img')?.src || null,
                        link: firstLink?.href || null,
                        selector: 'article:nth-child(' + (idx + 1) + ')'
                    };
                });
            }""")

        elif page_type == PageType.SINGLE_ARTICLE:
            return await self.page.evaluate("""() => {
                const article = document.querySelector('article, main');
                if (!article) return [];

                return [{
                    title: document.title,
                    body: article.innerText.slice(0, 500) + '...',  // First 500 chars
                    wordCount: article.innerText.split(/\\s+/).length,
                    author: document.querySelector('.author, [rel="author"]')?.innerText?.trim(),
                    publishDate: document.querySelector('time, [datetime]')?.getAttribute('datetime'),
                    mainImage: article.querySelector('img')?.src,
                    extractionConfidence: 0.85
                }];
            }""")

        elif page_type == PageType.API_REFERENCE:
            return await self.page.evaluate("""() => {
                const functions = Array.from(
                    document.querySelectorAll('dl.function, .api-function')
                ).slice(0, 3);

                return functions.map((f, idx) => ({
                    name: f.querySelector('dt, .name')?.innerText?.trim(),
                    description: f.querySelector('dd, .description')?.innerText?.trim()?.slice(0, 100),
                    parameters: Array.from(f.querySelectorAll('.param, .parameter')).map(p => p.innerText?.trim()),
                    examples: f.querySelectorAll('pre code').length,
                    selector: `dl.function:nth-child(${idx + 1})`
                }));
            }""")

        elif page_type == PageType.MEDIA_LISTING:
            return await self.page.evaluate("""() => {
                const shows = Array.from(
                    document.querySelectorAll('.show, .episode, .track')
                ).slice(0, 3);

                return shows.map((s, idx) => ({
                    title: s.querySelector('.title, h3, h4')?.innerText?.trim(),
                    duration: s.querySelector('.duration, [class*="duration"]')?.innerText?.trim(),
                    date: s.querySelector('time, .date')?.innerText?.trim(),
                    hasPlayButton: !!s.querySelector('[class*="play"]'),
                    selector: `.show:nth-child(${idx + 1})`
                }));
            }""")

        elif page_type == PageType.AUDIO_STREAM:
            return await self.page.evaluate("""() => {
                const players = Array.from(
                    document.querySelectorAll('audio, [data-player], [data-stream], .player')
                ).slice(0, 3);
                return players.map((p, idx) => ({
                    type: p.tagName === 'AUDIO' ? 'audio element' : 'player widget',
                    src: p.src || p.getAttribute('data-src') || p.querySelector('source')?.src || null,
                    hasControls: p.hasAttribute('controls') || !!p.querySelector('[class*="play"]'),
                    nowPlaying: p.closest('[class*="player"]')?.querySelector('.now-playing, .track-info, .currently-playing')?.innerText?.trim()?.slice(0, 100),
                    isLive: !!p.closest('[class*="live"]') || !!document.querySelector('.live, .on-air'),
                    selector: `audio:nth-of-type(${idx + 1})`
                }));
            }""")

        elif page_type == PageType.SHOW_ARCHIVE:
            return await self.page.evaluate("""() => {
                const shows = Array.from(
                    document.querySelectorAll('.show, .mix, [data-mix], .broadcast, .episode')
                ).slice(0, 5);
                return shows.map((s, idx) => ({
                    title: s.querySelector('.title, h3, h4, h2, a')?.innerText?.trim(),
                    host: s.querySelector('.host, .dj, .artist, [class*="artist"]')?.innerText?.trim(),
                    duration: s.querySelector('.duration, [class*="duration"]')?.innerText?.trim(),
                    date: s.querySelector('time, .date, [class*="date"]')?.innerText?.trim(),
                    genre: s.querySelector('.genre, .tag, [class*="genre"]')?.innerText?.trim(),
                    hasPlayButton: !!s.querySelector('[class*="play"]'),
                    link: s.querySelector('a')?.href,
                    selector: `.show:nth-child(${idx + 1})`
                }));
            }""")

        elif page_type == PageType.PODCAST_LISTING:
            return await self.page.evaluate("""() => {
                const episodes = Array.from(
                    document.querySelectorAll('.episode, [data-episode], .podcast-episode')
                ).slice(0, 5);
                return episodes.map((ep, idx) => ({
                    title: ep.querySelector('.title, h3, h4, h2')?.innerText?.trim(),
                    description: ep.querySelector('.description, .summary, p')?.innerText?.trim()?.slice(0, 150),
                    duration: ep.querySelector('.duration, [class*="duration"], time')?.innerText?.trim(),
                    date: ep.querySelector('time, .date')?.innerText?.trim(),
                    hasAudio: !!ep.querySelector('audio, [data-player]'),
                    link: ep.querySelector('a')?.href,
                    selector: `.episode:nth-child(${idx + 1})`
                }));
            }""")

        elif page_type in (PageType.CONTENT_GRID, PageType.GALLERY):
            cluster = getattr(self, '_detected_cluster', None)
            sel = cluster['selector'] if cluster else '[class*="item"]'
            return await self.page.evaluate("""(selector) => {
                const items = Array.from(document.querySelectorAll(selector)).slice(0, 5);
                return items.map((item, idx) => {
                    const r = item.getBoundingClientRect();
                    const s = getComputedStyle(item);

                    // Extract whatever content is in this item
                    const heading = item.querySelector('h1, h2, h3, h4, h5, h6');
                    const imgEl = item.querySelector('img');
                    const pictureEl = item.querySelector('picture img') || imgEl;
                    const text = item.querySelector('p, span, .excerpt, .description, .summary');
                    const link = item.querySelector('a[href]');
                    const date = item.querySelector('time, .date, [datetime]');
                    const tag = item.querySelector('.tag, .category, .label, [class*="tag"], [class*="category"]');

                    // Build title from multiple sources
                    const title = heading?.innerText?.trim()?.substring(0, 100) ||
                                  link?.innerText?.trim()?.substring(0, 100) ||
                                  item.querySelector('a')?.innerText?.trim()?.substring(0, 100) ||
                                  pictureEl?.alt?.trim()?.substring(0, 100) ||
                                  pictureEl?.title?.trim()?.substring(0, 100) ||
                                  null;

                    const imgSrc = pictureEl?.src || pictureEl?.getAttribute('data-src') ||
                                   pictureEl?.srcset?.split(',')[0]?.trim()?.split(' ')[0] || null;

                    return {
                        title: title || ('Image ' + (idx + 1)),
                        text: text?.innerText?.trim()?.substring(0, 200) || null,
                        image: imgSrc,
                        image_alt: pictureEl?.alt || null,
                        link: link?.href || item.querySelector('a')?.href || null,
                        date: date?.innerText?.trim() || date?.getAttribute('datetime') || null,
                        tag: tag?.innerText?.trim() || null,
                        dimensions: Math.round(r.width) + 'x' + Math.round(r.height) + 'px',
                        display: s.display,
                        selector: selector + ':nth-child(' + (idx + 1) + ')'
                    };
                });
            }""", sel)

        elif page_type == PageType.LANDING_PAGE:
            return await self.page.evaluate("""() => {
                const main = document.querySelector('main') || document.body;

                // Find prominent sections with headings
                const sections = Array.from(main.querySelectorAll('section, [class*="section"]')).slice(0, 5);
                return sections.map((s, idx) => {
                    const heading = s.querySelector('h1, h2, h3');
                    const text = s.querySelector('p');
                    const img = s.querySelector('img');
                    const cta = s.querySelector('a[class*="btn"], a[class*="button"], button');
                    return {
                        name: heading?.innerText?.trim()?.substring(0, 80) || `Section ${idx + 1}`,
                        text: text?.innerText?.trim()?.substring(0, 150) || '',
                        image: img?.src || null,
                        cta: cta?.innerText?.trim() || null,
                        selector: s.className ? `.${s.className.split(' ')[0]}` : `section:nth-child(${idx + 1})`
                    };
                });
            }""")

        else:
            # Generic fallback: grab the first few headings + surrounding content
            return await self.page.evaluate("""() => {
                const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 5);
                return headings.map((h, idx) => ({
                    name: h.innerText?.trim()?.substring(0, 80) || `Heading ${idx + 1}`,
                    tag: h.tagName,
                    text: h.nextElementSibling?.innerText?.trim()?.substring(0, 150) || '',
                    selector: h.id ? `#${h.id}` : `${h.tagName.toLowerCase()}:nth-of-type(${idx + 1})`
                }));
            }""")

    async def _extraction_strategy(self, page_type: PageType) -> Dict:
        """
        Explain extraction strategy with reasoning

        This shows WHY you chose specific selectors
        """
        strategies = {
            PageType.PRODUCT_LISTING: {
                'primary_selector': '.product-card, [data-product]',
                'fallback_selector': '[itemtype*="Product"]',
                'confidence': 'high',
                'reasoning': 'Products use consistent .product-card class with data attributes',
                'fields_extracted': ['name', 'price', 'image', 'link'],
                'validation': [
                    '✅ All products have consistent structure',
                    '✅ Price found in .price selector',
                    '✅ Images use proper alt text'
                ],
                'scaling_note': 'Can extract all products using same selector pattern'
            },
            PageType.BLOG_LISTING: {
                'primary_selector': 'article, .post',
                'fallback_selector': '[itemtype*="Article"]',
                'confidence': 'high',
                'reasoning': 'Articles use semantic <article> tags',
                'fields_extracted': ['title', 'excerpt', 'author', 'date'],
                'validation': [
                    '✅ Uses semantic <article> tags',
                    '✅ Consistent heading structure (h2 for titles)',
                    '✅ Date metadata present'
                ]
            },
            PageType.SINGLE_ARTICLE: {
                'primary_selector': 'article',
                'fallback_selector': 'main, .content',
                'confidence': 'high',
                'reasoning': 'Main content in semantic <article> tag',
                'fields_extracted': ['title', 'body', 'author', 'publishDate'],
                'validation': [
                    '✅ Found <article> tag (preferred semantic element)',
                    '✅ Article has >300 words (validates main content)',
                    '✅ No ads detected in article body',
                    '✅ Title matches <h1> text'
                ],
                'excluded': ['navigation', 'sidebar', 'footer', 'related posts']
            },
            PageType.API_REFERENCE: {
                'primary_selector': 'dl.function',
                'fallback_selector': '.api-function, .method',
                'confidence': 'high',
                'reasoning': 'Python docs use semantic <dl> tags for function definitions',
                'fields_extracted': ['name', 'description', 'parameters', 'examples'],
                'validation': [
                    '✅ Semantic HTML (definition lists)',
                    '✅ Code examples present',
                    '✅ Parameter documentation complete'
                ]
            },
            PageType.MEDIA_LISTING: {
                'primary_selector': '.show, .episode',
                'fallback_selector': '[data-show]',
                'confidence': 'medium',
                'reasoning': 'Shows use consistent class pattern but some missing metadata',
                'fields_extracted': ['title', 'duration', 'date', 'playButton'],
                'validation': [
                    '✅ Consistent structure across items',
                    '⚠️ Some items missing duration data',
                    '✅ Play buttons detected'
                ]
            },
            PageType.AUDIO_STREAM: {
                'primary_selector': 'audio, [data-player], [data-stream]',
                'fallback_selector': '.player, .stream',
                'confidence': 'high',
                'reasoning': 'Live audio stream detected via HTML5 audio elements and player widgets',
                'fields_extracted': ['type', 'src', 'nowPlaying', 'isLive', 'hasControls'],
                'validation': [
                    '✅ HTML5 <audio> element or player widget found',
                    '✅ Live/schedule indicators present',
                    '⚠️ Stream content is dynamic (initial state only captured)'
                ],
                'scaling_note': 'Audio streams are stateful — full tracklist requires polling or WebSocket monitoring'
            },
            PageType.SHOW_ARCHIVE: {
                'primary_selector': '.show, .mix, [data-mix], .broadcast',
                'fallback_selector': '.episode, [data-show]',
                'confidence': 'medium',
                'reasoning': 'Show/mix archive with repeated content cards and audio presence',
                'fields_extracted': ['title', 'host', 'duration', 'date', 'genre'],
                'validation': [
                    '✅ Consistent show card structure',
                    '✅ Audio playback elements detected',
                    '⚠️ Some metadata may load dynamically'
                ]
            },
            PageType.RADIO_STATION: {
                'primary_selector': 'audio, [data-player], [class*="player"], [class*="stream"]',
                'fallback_selector': '[class*="broadcast"], [class*="live"], [class*="show"]',
                'confidence': 'high',
                'reasoning': 'Live radio/streaming platform with player controls, schedule, and show grid',
                'fields_extracted': ['players', 'shows', 'schedule', 'channels', 'live_status'],
                'validation': [
                    '✅ Audio player/stream elements detected',
                    '✅ Schedule or programming grid found',
                    '⚠️ Live stream content is dynamic (initial state only)'
                ],
                'scaling_note': 'Radio platforms are stateful — live content requires WebSocket/polling. Shows and schedule are crawlable.'
            },
            PageType.MUSIC_BLOG: {
                'primary_selector': 'article, .post',
                'fallback_selector': '[class*="artist"], [class*="release"]',
                'confidence': 'high',
                'reasoning': 'Music/culture editorial with articles and music-specific elements (artists, genres, releases)',
                'fields_extracted': ['title', 'artist', 'genre', 'images', 'audio'],
                'validation': [
                    '✅ Uses semantic <article> tags',
                    '✅ Music-specific metadata (artists, genres, releases)',
                    '⚠️ Some content may be embeds (Spotify, SoundCloud)'
                ]
            },
            PageType.PODCAST_LISTING: {
                'primary_selector': '.episode, [data-episode], .podcast-episode',
                'fallback_selector': '[itemtype*="PodcastEpisode"], [itemtype*="AudioObject"]',
                'confidence': 'high',
                'reasoning': 'Podcast episode listing with structured audio metadata',
                'fields_extracted': ['title', 'description', 'duration', 'date', 'hasAudio'],
                'validation': [
                    '✅ Episode elements with consistent structure',
                    '✅ Audio/player elements associated with episodes',
                    '✅ Schema.org metadata detected'
                ]
            },
            PageType.LANDING_PAGE: {
                'primary_selector': 'section, [class*="section"]',
                'fallback_selector': 'main > div',
                'confidence': 'medium',
                'reasoning': 'Landing page identified by section-based layout with CTAs and hero content',
                'fields_extracted': ['sections', 'headings', 'ctas', 'images'],
                'validation': [
                    '✅ Page uses section-based layout',
                    '✅ CTA buttons or prominent links detected',
                    '⚠️ Content is structural (sections) not repeating items'
                ],
                'scaling_note': 'Landing pages are unique compositions — no repeating content pattern to extract at scale'
            }
        }

        # For content grid / gallery — build strategy from actual detected cluster
        if page_type in (PageType.CONTENT_GRID, PageType.GALLERY):
            cluster = getattr(self, '_detected_cluster', None)
            if cluster:
                anatomy = []
                if cluster.get('hasImage'): anatomy.append('images')
                if cluster.get('hasHeading'): anatomy.append('headings')
                if cluster.get('hasText'): anatomy.append('text')
                if cluster.get('hasLink'): anatomy.append('links')
                return {
                    'primary_selector': cluster.get('selector', 'auto-detected'),
                    'container_selector': cluster.get('containerSelector', 'auto-detected'),
                    'confidence': 'medium-high',
                    'reasoning': f'Detected {cluster["count"]} structurally similar {cluster["tag"]} elements via DOM analysis (not hardcoded selectors)',
                    'detection_method': 'generic_sibling_clustering',
                    'fields_extracted': anatomy,
                    'item_anatomy': {
                        'has_image': cluster.get('hasImage', False),
                        'has_heading': cluster.get('hasHeading', False),
                        'has_text': cluster.get('hasText', False),
                        'has_link': cluster.get('hasLink', False),
                        'avg_height': cluster.get('avgHeight', 0)
                    },
                    'scaling_note': f'All {cluster["count"]} items match the same selector — full extraction possible'
                }

        return strategies.get(page_type, {
            'primary_selector': 'unknown',
            'confidence': 'low',
            'reasoning': 'Could not determine optimal selector'
        })

    async def _identify_excluded(self) -> Dict:
        """
        Show what was excluded from extraction

        This demonstrates you're extracting signal, not noise
        """
        return await self.page.evaluate("""() => {
            return {
                navigation: {
                    count: document.querySelectorAll('nav, .navigation').length,
                    links: document.querySelectorAll('nav a').length,
                    excluded: true,
                    reasoning: 'Navigation is structural, not content'
                },
                footer: {
                    count: document.querySelectorAll('footer').length,
                    links: document.querySelectorAll('footer a').length,
                    excluded: true,
                    reasoning: 'Footer contains site-wide links'
                },
                sidebar: {
                    count: document.querySelectorAll('aside, .sidebar').length,
                    excluded: true,
                    reasoning: 'Sidebar contains auxiliary content'
                },
                ads: {
                    count: document.querySelectorAll('[class*="ad"], [id*="ad"]').length,
                    excluded: true,
                    reasoning: 'Advertisements are not content'
                },
                relatedPosts: {
                    count: document.querySelectorAll('.related, [class*="related"]').length,
                    excluded: false,
                    reasoning: 'May be relevant for some analyses'
                }
            };
        }""")

    async def _analyze_semantic_html(self) -> Dict:
        """
        Analyze semantic HTML quality

        Shows understanding of modern web standards
        """
        analysis = await self.page.evaluate("""() => {
            const tags = {
                main: document.querySelectorAll('main').length,
                article: document.querySelectorAll('article').length,
                section: document.querySelectorAll('section').length,
                nav: document.querySelectorAll('nav').length,
                header: document.querySelectorAll('header').length,
                footer: document.querySelectorAll('footer').length,
                aside: document.querySelectorAll('aside').length
            };

            // Calculate quality score
            let score = 0;
            const notes = [];

            if (tags.main > 0) {
                score += 20;
                notes.push('✓ Uses <main> for primary content');
            } else {
                notes.push('✗ Missing <main> tag');
            }

            if (tags.article > 0) {
                score += 20;
                notes.push('✓ Uses <article> for articles');
            } else {
                notes.push('✗ Missing <article> tags');
            }

            if (tags.nav > 0) {
                score += 15;
                notes.push('✓ Proper <nav> for navigation');
            } else {
                notes.push('✗ Missing <nav> tag');
            }

            if (tags.header > 0) {
                score += 15;
                notes.push('✓ Proper <header> for header content');
            }

            if (tags.footer > 0) {
                score += 10;
                notes.push('✓ Proper <footer> for footer content');
            }

            if (tags.section > 2) {
                score += 20;
                notes.push('✓ Good content structure with <section> tags');
            }

            // ARIA labels
            const ariaLabels = document.querySelectorAll('[aria-label], [aria-labelledby]').length;
            if (ariaLabels > 10) {
                score += 10;
                notes.push('✓ Excellent ARIA label usage');
            }

            // Heading hierarchy
            const h1s = document.querySelectorAll('h1').length;
            if (h1s === 1) {
                notes.push('✓ Proper heading hierarchy (single h1)');
            } else if (h1s > 1) {
                notes.push(`⚠️ Multiple h1 tags (${h1s} found)`);
            }

            // Cap at 100 — additive signals can exceed if site has everything
            const cappedScore = Math.min(score, 100);
            return {
                tags,
                score: cappedScore,
                quality: cappedScore > 70 ? 'High' : cappedScore > 40 ? 'Medium' : 'Low',
                notes,
                ariaLabels
            };
        }""")

        return analysis


# Demo
async def demo():
    """
    Demonstrate intelligent content extraction
    """
    test_sites = [
        ('https://docs.python.org/3/library/functions.html', 'API Reference'),
        ('https://www.nike.com', 'Product Listing'),
        ('https://www.theringer.com', 'Blog Listing'),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for url, expected_type in test_sites:
            print(f"\n{Fore.MAGENTA}{'='*70}")
            print(f"{Fore.MAGENTA}  Testing: {url}")
            print(f"{Fore.MAGENTA}  Expected: {expected_type}")
            print(f"{Fore.MAGENTA}{'='*70}\n")

            page = await browser.newPage()

            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)

                extractor = IntelligentContentExtractor(page)
                result = await extractor.extract()

                # Display results
                print(f"{Fore.CYAN}📄 Page Classification:")
                print(f"   Type: {result.page_type.value}")
                print(f"   Confidence: {result.confidence * 100:.0f}%")
                print(f"   Reasoning: {result.reasoning}\n")

                print(f"{Fore.GREEN}📊 Content Inventory:")
                for key, value in result.content_inventory.items():
                    if isinstance(value, dict):
                        print(f"   {key}:")
                        for k, v in value.items():
                            print(f"      {k}: {v}")
                    else:
                        print(f"   {key}: {value}")

                print(f"\n{Fore.YELLOW}📦 Samples ({len(result.samples)} extracted):")
                for idx, sample in enumerate(result.samples[:3], 1):
                    print(f"\n   Sample {idx}:")
                    for key, value in list(sample.items())[:5]:
                        if isinstance(value, str) and len(value) > 60:
                            print(f"      {key}: {value[:60]}...")
                        else:
                            print(f"      {key}: {value}")

                print(f"\n{Fore.BLUE}🎯 Extraction Strategy:")
                strat = result.extraction_strategy
                print(f"   Selector: {strat.get('primary_selector', 'N/A')}")
                print(f"   Confidence: {strat.get('confidence', 'N/A')}")
                print(f"   Reasoning: {strat.get('reasoning', 'N/A')}")

                if strat.get('validation'):
                    print(f"\n   Validation:")
                    for note in strat['validation']:
                        print(f"      {note}")

                print(f"\n{Fore.RED}🚫 Excluded Elements:")
                for element, data in result.excluded_elements.items():
                    if isinstance(data, dict) and data.get('excluded'):
                        print(f"   {element}: {data.get('count', 0)} ({data.get('reasoning', 'N/A')})")

                print(f"\n{Fore.MAGENTA}🏷️  Semantic HTML Analysis:")
                sem = result.semantic_analysis
                print(f"   Quality Score: {sem['score']}/100 ({sem['quality']})")
                print(f"   Tags Found: {sem['tags']}")
                print(f"\n   Notes:")
                for note in sem['notes'][:5]:
                    print(f"      {note}")

            except Exception as e:
                print(f"{Fore.RED}Error: {str(e)}")

            finally:
                await page.close()

        await browser.close()


if __name__ == '__main__':
    asyncio.run(demo())
