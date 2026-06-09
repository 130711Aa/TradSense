"""
TradSense - News Collection Verification
========================================
Menguji apakah RSS feeds Indonesia berhasil mengambil berita untuk saham BEI.
"""

import os
import sys

# Setup paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 console output
if sys.platform.startswith("win"):
    import io
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from data.news_collector import NewsCollector
from utils.logger import setup_logging

import requests
import feedparser

feeds = {
    "detik": "https://finance.detik.com/rss",
    "kontan": "https://investasi.kontan.co.id/rss",
    "cnbc": "https://www.cnbcindonesia.com/market/rss",
}

for name, url in feeds.items():
    print(f"\n=== Feed: {name.upper()} ===")
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, timeout=10)
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:5]:
            print(f"- {entry.get('title')}")
    except Exception as e:
        print(f"Error: {e}")

# Selesai
