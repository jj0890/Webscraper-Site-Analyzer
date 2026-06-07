#!/bin/bash
# setup.sh — First-time install. Run once after cloning.
# After this, use ./start.sh to launch the server.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  Web Intelligence Scraper — First-time Setup"
echo "=================================================="
echo ""

# ── Python version check ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install from https://www.python.org/downloads/"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Python $PY_VER found"

# Warn if < 3.10 (Scrapling stealth requires 3.10+)
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MINOR" -lt 10 ]; then
    echo "[WARN] Python 3.10+ recommended (you have $PY_VER). Scrapling stealth bypass won't work."
fi

# ── Virtualenv ────────────────────────────────────────
if [ ! -d "venv310" ]; then
    echo ""
    echo "Creating virtualenv venv310..."
    python3 -m venv venv310
    echo "[OK] Virtualenv created"
else
    echo "[OK] venv310 already exists"
fi

source venv310/bin/activate

# ── Python dependencies ───────────────────────────────
echo ""
echo "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "[OK] Python dependencies installed"

# ── Browser binary ────────────────────────────────────
echo ""
echo "Installing Patchright Chromium browser..."
python -m patchright install chromium
echo "[OK] Chromium installed"

# ── Node SDK (axe-core contrast auditing) ────────────
if command -v npm &>/dev/null; then
    if [ -d "website-understanding-sdk" ]; then
        echo ""
        echo "Installing Node SDK dependencies..."
        npm install --prefix ./website-understanding-sdk -q
        npm install axe-core --prefix ./website-understanding-sdk -q
        echo "[OK] Node SDK ready"
    fi
else
    echo "[WARN] npm not found — contrast auditing (axe-core) won't work. Install Node.js from https://nodejs.org"
fi

# ── Optional: Scrapling stealth bypass ───────────────
echo ""
echo "Installing optional Scrapling stealth bypass (Cloudflare sites)..."
if pip install "scrapling[fetchers]" -q 2>/dev/null; then
    scrapling install -q 2>/dev/null || true
    echo "[OK] Scrapling installed"
else
    echo "[SKIP] Scrapling install failed — stealth bypass won't work (optional)"
fi

# ── Runtime directories ───────────────────────────────
mkdir -p .screenshots
echo "[OK] Runtime directories ready"

# ── Smoke test ────────────────────────────────────────
echo ""
echo "Running smoke test (verifies end-to-end in ~10 seconds)..."
if python tests/smoke_test.py; then
    echo ""
    echo "=================================================="
    echo "  ✅ Setup complete!"
    echo "=================================================="
    echo ""
    echo "  Start the server:  ./start.sh"
    echo "  Dashboard:         http://127.0.0.1:8080"
    echo ""
else
    echo ""
    echo "[WARN] Smoke test failed — check the error above."
    echo "       The tool may still work. Try: ./start.sh"
fi
