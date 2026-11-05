#!/usr/bin/env bash
# ==============================================================================
# KURINJI — Ubuntu VPS Automated Deployment & Setup Script
# ==============================================================================
set -e

echo "=== [1/6] Installing Ubuntu System Dependencies ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl nginx libsndfile1 ffmpeg

# Install Node.js (v20 LTS) if not installed
if ! command -v node &> /dev/null; then
    echo "Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "=== [2/6] Setting Up Python Virtual Environment ==="
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [3/6] Pre-Warming All 324 Curriculum Audio Snippets ==="
python backend/warmup_tts_cache.py

echo "=== [4/6] Building Production React Frontend ==="
cd frontend
npm install
npm run build
cd ..

echo "=== [5/6] Registering Systemd Background Service ==="
sudo cp kurinji.service /etc/systemd/system/kurinji.service
sudo systemctl daemon-reload
sudo systemctl enable kurinji
sudo systemctl restart kurinji

echo "=== [6/6] Verifying Backend Health ==="
sleep 2
sudo systemctl status kurinji --no-pager

echo ""
echo "================================================================================"
echo "  KURINJI FastAPI Backend is live on http://127.0.0.1:8000"
echo "  Next: Configure Nginx to serve the site to the public."
echo "================================================================================"

