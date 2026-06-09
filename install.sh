#!/bin/bash
# ==================================================
# TradSense - MSYS2 Installation Script
# ==================================================
# Jalankan di MSYS2 UCRT64 terminal:
#   cd /d/TradSense && bash install.sh
# ==================================================
set -e

echo "=== TradSense MSYS2 Installer ==="

# Set SSL cert dari certifi
export SSL_CERT_FILE=/ucrt64/lib/python3.12/site-packages/certifi/cacert.pem

# Install system packages via pacman
echo ""
echo "[1/3] Installing system packages via pacman..."
pacman -S --noconfirm --needed \
    mingw-w64-ucrt-x86_64-python-numpy \
    mingw-w64-ucrt-x86_64-python-pandas \
    mingw-w64-ucrt-x86_64-python-cffi \
    mingw-w64-ucrt-x86_64-python-pip \
    mingw-w64-ucrt-x86_64-python-certifi

# Install pip packages (pure Python, no compilation needed)
echo ""
echo "[2/3] Installing pip packages..."
pip install --break-system-packages \
    "yfinance==0.2.36" \
    requests \
    feedparser \
    SQLAlchemy \
    APScheduler \
    "python-telegram-bot>=21.0" \
    google-genai \
    textblob \
    python-dotenv \
    rich

# Copy .env.example jika .env belum ada
echo ""
echo "[3/3] Setup environment..."
if [ ! -f /d/TradSense/.env ]; then
    cp /d/TradSense/.env.example /d/TradSense/.env
    echo "Created .env from .env.example - EDIT WITH YOUR API KEYS!"
else
    echo ".env already exists"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Langkah selanjutnya:"
echo "  1. Edit .env dan isi API keys (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, dll)"
echo "  2. Test:  python /d/TradSense/main.py --mode test"
echo "  3. Run:   python /d/TradSense/main.py"
