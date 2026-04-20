#!/bin/bash
# Setup script for Alpha Tracker Call Logger
# Run this on your Ubuntu/Debian server

set -e

echo "=== Alpha Tracker Call Logger — Setup ==="
echo ""

# 1. Install system dependencies
echo "[1/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv

# 2. Create virtual environment
echo "[2/5] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
echo "[3/5] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright + Chromium
echo "[4/5] Installing Playwright and Chromium browser..."
playwright install chromium
playwright install-deps chromium

# 5. Create .env from example if it doesn't exist
echo "[5/5] Setting up configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it if needed."
else
    echo ".env already exists, skipping."
fi

# Create data directories
mkdir -p data/session data/csv logs

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Run the scraper:  source .venv/bin/activate && python main.py"
echo "  2. A browser window will open — log into trade.padre.gg with your throwaway wallet"
echo "  3. Once logged in, click the Alpha tab — the scraper will start capturing calls"
echo "  4. The session is saved, so next time it won't need manual login"
echo ""
echo "To run as a background service, install the systemd unit:"
echo "  sudo cp alpha-tracker.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable alpha-tracker"
echo "  sudo systemctl start alpha-tracker"
