# Start Here

You last ran this weeks ago. Here's exactly what to do.

---

## Coming back after a break

```bash
cd ~/Desktop/Webscraper
source venv310/bin/activate
./start.sh
```

Dashboard opens at **http://127.0.0.1:8080** automatically.

---

## First time (fresh clone)

```bash
bash setup.sh
```

That one command creates the virtualenv, installs everything, downloads Chromium, and runs a smoke test. Takes ~3 minutes.

---

## Run a scan

1. Open http://127.0.0.1:8080
2. Paste a URL (e.g. `https://stripe.com`)
3. Choose mode — **Single** for speed, **Smart Nav** for depth
4. Click **Analyze**

Or via API:
```bash
curl -X POST http://127.0.0.1:8080/api/deep-scan \
  -H "Content-Type: application/json" \
  -d '{"site_url": "https://stripe.com", "analysis_mode": "single"}'
```

---

## Verify the tool actually works

```bash
python tests/smoke_test.py
```

Pass = environment healthy. Takes ~10 seconds against `example.com`.

---

## If something is broken

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| `patchright not found` | `python -m patchright install chromium` |
| `Port 8080 already in use` | `lsof -ti:8080 \| xargs kill -9` |
| Cloudflare blocking scans | `pip install "scrapling[fetchers]" && scrapling install` |
| axe contrast audit fails | `npm install axe-core --prefix ./website-understanding-sdk` |
| Nothing works | `rm -rf venv310 && bash setup.sh` |

---

## Run tests

```bash
# All unit tests (fast, no network, ~1 second)
pytest tests/ -v -m "not slow"

# Including integration tests (needs network, ~30 seconds)
pytest tests/ -v
```

---

## Key files

| File | What it is |
|---|---|
| `app.py` | Flask server — API routes |
| `deep_evidence_engine.py` | Main analysis orchestrator |
| `extractors/` | 18+ focused extraction modules |
| `component_ripper.py` | HTML+CSS blueprint extractor |
| `templates/web_dashboard.html` | The entire dashboard UI |
| `CLAUDE.md` | AI operating doctrine (read this before editing) |

---

## Modes explained

| Mode | Time | Use when |
|---|---|---|
| **Single** | ~60s | Quick check, one page |
| **Smart Nav** | ~2-4 min | Full design system extraction |
| **Multi-Template** | ~5-8 min | Identify what's consistent across all page types |
| **Interactive** | ~3-5 min | Sites with mega-menus or JS-gated content |

---

*Server runs on port 8080. Binds to 127.0.0.1 only (localhost, not network-accessible).*
