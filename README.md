# Web Intelligence Scraper

A web scraping and design analysis system that extracts design systems, layout patterns, and site architecture — legible to humans and LLMs.

This is **not a content crawler** — it's an **evidence engine** for structural understanding.

---

## Quick Start

```bash
# Clone (include the component SDK submodule)
git clone --recurse-submodules https://github.com/ScumbagJones/Webscraper-Site-Analyzer.git
cd Webscraper-Site-Analyzer

# Python environment (3.9+, 3.10+ recommended)
python3 -m venv venv310
source venv310/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install browser binary (patchright Chromium — ~300MB download)
python -m patchright install

# Install SDK dependencies (for component mapping + contrast auditing)
cd website-understanding-sdk && npm install && cd ..

# Start the server
./start.sh
# Opens http://127.0.0.1:8080 automatically
```

### Optional: Enhanced Stealth (Cloudflare bypass)

```bash
# Requires Python 3.10+
pip install "scrapling[fetchers]"
scrapling install
```

---

## What It Extracts

| Category | Examples | Confidence |
|----------|----------|------------|
| Typography | Fonts, sizes, type scale ratio | 95% avg |
| Spacing | Scale, base unit, rhythm | 85% avg |
| Colors | Palette, CSS variable roles | 69% avg (drops on Tailwind) |
| Layout | Flex/Grid patterns, containers | 85% avg |
| Visual Hierarchy | Hero, CTA, attention flow | 85% avg |
| Shadows | Elevation levels, anatomy | 73% avg |
| Breakpoints | Actual media queries | 88% avg |
| Spatial Composition | Page structure, zones, whitespace | 85%+ |
| Motion | Duration scale, easing palette | Varies |
| Accessibility | Landmarks, headings, contrast (WCAG AA) | Varies |
| API Relationships | Endpoints, categories, redundancy | Varies |
| + 10 more | SEO, security, performance, DOM depth... | |

---

## API Endpoints

### Deep Scan (primary)
```bash
curl -X POST http://127.0.0.1:8080/api/deep-scan \
  -H "Content-Type: application/json" \
  -d '{"site_url": "https://stripe.com", "analysis_mode": "single"}'
```

Analysis modes: `single` (one page) or `smart-nav` (auto-discover 3 representative pages).

### Other Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/discover-urls` | POST | Extract and categorize all links |
| `/api/batch-analyze` | POST | Compare up to 5 URLs |
| `/api/rip-component` | POST | Extract HTML + CSS for a selector |
| `/api/extract-styles` | POST | Get computed CSS values |
| `/api/discover-components` | POST | Scan page for all detectable components |
| `/api/health` | GET | Server health check |

All POST endpoints accept `{"site_url": "..."}` as the base parameter.

---

## Output Structure

Every deep scan returns structured evidence:

```json
{
  "success": true,
  "evidence": {
    "typography": {
      "fonts": ["Inter", "system-ui"],
      "type_scale": {"ratio": 1.25, "sizes_px": [14, 16, 20, 25, 31]},
      "confidence": 95
    },
    "colors": {
      "palette": {"primary": [...], "secondary": [...], "intentional": [...]},
      "color_roles": {"accent": "#635BFF", "background": "#0A2540"},
      "confidence": 85
    },
    "spacing_scale": {
      "scale": [4, 8, 12, 16, 24, 32, 48, 64],
      "base_unit": "4px",
      "confidence": 85
    },
    "visual_hierarchy": {
      "hero_section": {"detected": true, ...},
      "primary_cta": {"detected": true, ...},
      "confidence": 85
    },
    "spatial_composition": {
      "page_structure": {"pattern_type": "Landing Page (Hero + Features)"},
      "component_zones": [...],
      "whitespace_analysis": {...},
      "confidence": 85
    },
    "llm_helper": {
      "suggested_next_steps": [...],
      "url_patterns": {...},
      "analysis_tips": [...]
    }
  }
}
```

---

## Architecture

| Layer | Tech | Files |
|-------|------|-------|
| Server | Python 3.9+ / Flask | `app.py`, `start.sh` |
| Browser | Patchright (Chromium, CDP anti-detection) | `deep_evidence_engine.py` |
| Parsing | BeautifulSoup, lxml | Various extractors |
| Extractors | 18 specialized modules | `extractors/` |
| SDK Bridge | Node.js (component mapping, axe-core) | `website-understanding-sdk/` |
| Frontend | Vanilla JS (no framework) | `templates/web_dashboard.html` |

### Core Files
- `deep_evidence_engine.py` — Main orchestrator (20+ metrics)
- `app.py` — Flask server and API routing
- `extractors/` — 18 extraction modules (typography, colors, layout, etc.)
- `spatial_composition_analyzer.py` — Page structure and zones
- `component_ripper.py` — HTML + CSS component extraction
- `templates/web_dashboard.html` — Dashboard UI

---

## Running

```bash
# Development (auto-reload, opens browser)
./start.sh

# Production (gunicorn, 2 workers, 300s timeout)
./start.sh production

# Direct Python (no venv activation, no port check)
python3 app.py
```

Server binds to `127.0.0.1:8080` (localhost only).

---

## Known Limitations

**Works best with:** Semantic CSS (BEM, SMACSS), marketing sites, documentation sites, e-commerce.

**Works with caveats:** Utility-first CSS (Tailwind) — detects values but loses semantic names. Color confidence drops to ~25%.

**Does not work with:** Closed Shadow DOM, aggressive bot protection (Cloudflare Turnstile, PerimeterX), auth-gated pages, infinite scroll content.

**Graceful degradation (MRI mode):** When Playwright is blocked, falls back to HTTP + BeautifulSoup (~70% accuracy).

---

## Troubleshooting

**Port 8080 in use:**
```bash
lsof -ti:8080 | xargs kill -9
```

**Browser not installed:**
```bash
python -m patchright install
```

**Bot detection blocking scans:** Stealth mode activates automatically. If still blocked, install Scrapling (see Optional setup above).

**Missing contrast auditing:** Ensure axe-core is installed:
```bash
npm install axe-core --prefix ./website-understanding-sdk
```

---

## Philosophy

This tool treats websites as systems, not pages.

- Every extraction must be **verifiable** (traceable to DOM/CSS/network)
- Every metric must be **defensible** (confidence scores based on evidence)
- No metric exists without traceable evidence
- Low confidence is displayed honestly, not hidden

For the full engineering doctrine, see `CLAUDE.md`.
