#!/bin/bash

# Web Intelligence Scraper — Startup Script
# Starts the Python web scraper on port 8080
#
# Usage:
#   ./start.sh              # Development mode (Flask debug server)
#   ./start.sh production   # Production mode (gunicorn — stays up for days)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-development}"

echo "=================================================="
echo "  Web Intelligence Dashboard"
echo "=================================================="
echo ""

# Activate virtualenv if available
if [ -d "venv310" ]; then
    source venv310/bin/activate
    echo "[OK] Activated venv310"
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed"
    echo "   Install from: https://www.python.org/downloads/"
    exit 1
fi

echo "[OK] Python 3 found: $(python3 --version)"

# Check if requirements are installed
echo ""
echo "Checking dependencies..."

if ! python3 -c "import flask" 2>/dev/null; then
    echo "[WARN] Flask not found. Installing dependencies..."
    pip3 install -r requirements.txt
else
    echo "[OK] Dependencies installed"
fi

# Check if patchright browser is installed (file check — no launch needed)
if ! python3 -c "import patchright" 2>/dev/null; then
    echo "[WARN] patchright not installed. Run: pip install patchright"
fi

# Build frontend assets
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    if [ -d "frontend/node_modules" ]; then
        echo ""
        echo "Building frontend..."
        npm run build --prefix frontend 2>/dev/null
        echo "[OK] Frontend built"
    else
        echo "[WARN] Frontend node_modules missing. Run: cd frontend && npm install"
    fi
fi

# Create runtime directories
mkdir -p .screenshots
echo "[OK] Directories ready"

# Auto-kill anything on port 8080 (no interactive prompt)
if lsof -ti:8080 > /dev/null 2>&1; then
    echo ""
    echo "[WARN] Port 8080 in use — killing old process..."
    kill -9 $(lsof -ti:8080) 2>/dev/null
    sleep 1
    echo "[OK] Port 8080 cleared"
fi

# Start the server
echo ""
echo "=================================================="

if [ "$MODE" = "production" ]; then
    echo "  Starting in PRODUCTION mode (gunicorn)..."
    echo "=================================================="
    echo ""
    export FLASK_ENV=production

    # Check gunicorn is installed
    if ! command -v gunicorn &> /dev/null; then
        echo "[WARN] gunicorn not found. Installing..."
        pip3 install gunicorn
    fi

    PID_FILE="$SCRIPT_DIR/.server.pid"

    gunicorn -c gunicorn.conf.py app:app &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$PID_FILE"
    echo ""
    echo "[OK] Server started (PID $SERVER_PID)"
    echo "  Dashboard: http://127.0.0.1:8080"
    echo "  Health:    http://127.0.0.1:8080/api/health"
    echo "  Stop:      kill $SERVER_PID"
    echo ""
    echo "Server running in background. Logs stream to stdout."
    wait "$SERVER_PID"
else
    echo "  Starting in DEVELOPMENT mode (Flask debug)..."
    echo "=================================================="
    echo ""
    export FLASK_ENV=development
    # Open dashboard in browser after a short delay
    (sleep 1.5 && open "http://127.0.0.1:8080") &
    python3 app.py
fi
