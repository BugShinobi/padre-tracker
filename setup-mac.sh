#!/bin/bash
# Setup script for Alpha Tracker Call Logger — macOS version (for testing)

set -e

echo "=== Alpha Tracker Call Logger — macOS Setup ==="
echo ""

# 1. Check Python 3
echo "[1/4] Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Install it with: brew install python3"
    exit 1
fi
echo "  Found: $(python3 --version)"

# 2. Create virtual environment
echo "[2/4] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
echo "[3/4] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright + Chromium
echo "[4/4] Installing Playwright and Chromium browser..."
playwright install chromium

# Create .env if needed
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

# Create data directories
mkdir -p data/session data/csv logs

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Run it:"
echo "  source .venv/bin/activate"
echo "  python main.py"
