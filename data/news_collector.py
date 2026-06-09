"""
TradSense - Layer 1: News Collector
=====================================
Mengambil berita dari Finnhub API dan RSS feeds Indonesia.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Optional

import feedparser
import requests

from config import (
    FINNHUB_API_KEY,
    MAX_NEWS_PER_TICKER,
    RSS_FEEDS,
)
from utils.logger import get_logger

logger = get_logger("data.news_collector")


class NewsCollector:
    """Mengumpulkan berita saham dari berbagai sumber."""

    def __init__(self) -> None:
        """Inisialisasi NewsCollector."""
        self.finnhub_base_url = "https://finnhub.io/api/v1"
        self.finnhub_api_key = FINNHUB_API_KEY

    # --------------------------------------------------
    # Finnhub News
    # --------------------------------------------------
    def fetch_finnhub_news(
        self,
        ticker: str,
        days_back: int = 3,
    ) -> list[dict[str, Any]]:
        """Mengambil berita dari Finnhub untuk ticker tertentu.

        Args:
            ticker: Kode saham (tanpa suffix).
            days_back: Jumlah hari ke belakang.

        Returns:
            List of news items.
        """
        if not self.finnhub_api_key:
            logger.warning("FINNHUB_API_KEY belum diset, skip Finnhub news")
            return []

        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")

        try:
            url = f"{self.finnhub_base_url}/company-news"
            params = {
                "symbol": f"{ticker}.JK",
                "from": date_from,
                "to": date_to,
                "token": self.finnhub_api_key,
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            articles = response.json()
            if not isinstance(articles, list):
                return []

            news_items = []
            for article in articles[:MAX_NEWS_PER_TICKER]:
                news_items.append({
                    "source": "finnhub",
                    "title": article.get("headline", ""),
                    "summary": article.get("summary", ""),
                    "url": article.get("url", ""),
                    "datetime": datetime.fromtimestamp(article.get("datetime", 0)),
                    "related": article.get("related", ""),
                })

            logger.debug(f"Finnhub: {len(news_items)} berita untuk {ticker}")
            return news_items

        except Exception as e:
            # Finnhub free tier returns 403 Forbidden for international stocks (.JK suffix)
            if "403" in str(e):
                logger.debug(f"Finnhub free tier restriction: news not available for {ticker} (using RSS feeds instead)")
            else:
                logger.warning(f"Finnhub news warning for {ticker}: {e}")
            return []

    # --------------------------------------------------
    # RSS Feeds
    # --------------------------------------------------
    def fetch_rss_news(
        self,
        ticker: str,
        company_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Mengambil berita dari RSS feeds yang relevan dengan ticker.

        Args:
            ticker: Kode saham.
            company_name: Nama perusahaan untuk pencarian (opsional).

        Returns:
            List of news items.
        """
        all_news: list[dict[str, Any]] = []
        search_terms = [ticker.lower()]
        if company_name:
            search_terms.append(company_name.lower())

        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                resp = requests.get(feed_url, headers=headers, timeout=10)
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                if not feed.entries:
                    logger.warning(f"RSS feed empty or failed to parse: {feed_name}")
                    continue

                for entry in feed.entries:
                    title = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()
                    content = f"{title} {summary}"

                    # Filter berita yang relevan dengan ticker
                    if any(term in content for term in search_terms):
                        published = entry.get("published_parsed")
                        pub_date = (
                            datetime(*published[:6])
                            if published
                            else datetime.now()
                        )

                        all_news.append({
                            "source": feed_name,
                            "title": entry.get("title", ""),
                            "summary": entry.get("summary", "")[:500],
                            "url": entry.get("link", ""),
                            "datetime": pub_date,
                            "related": ticker,
                        })

            except Exception as e:
                logger.error(f"RSS error ({feed_name}): {e}")
                continue

        logger.debug(f"RSS: {len(all_news)} berita relevan untuk {ticker}")
        return all_news

    def fetch_general_market_news(self) -> list[dict[str, Any]]:
        """Mengambil berita pasar umum dari RSS feeds.

        Returns:
            List of market news items.
        """
        market_keywords = [
            "ihsg", "bursa", "saham", "idx", "bei", "market",
            "inflasi", "bi rate", "suku bunga", "rupiah",
            "komoditas", "nikel", "batubara", "cpo", "minyak",
        ]
        all_news: list[dict[str, Any]] = []

        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                resp = requests.get(feed_url, headers=headers, timeout=10)
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:50]:
                    title = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()
                    content = f"{title} {summary}"

                    if any(kw in content for kw in market_keywords):
                        published = entry.get("published_parsed")
                        pub_date = (
                            datetime(*published[:6])
                            if published
                            else datetime.now()
                        )
                        all_news.append({
                            "source": feed_name,
                            "title": entry.get("title", ""),
                            "summary": entry.get("summary", "")[:500],
                            "url": entry.get("link", ""),
                            "datetime": pub_date,
                            "related": "MARKET",
                        })

            except Exception as e:
                logger.error(f"RSS market news error ({feed_name}): {e}")
                continue

        logger.info(f"Market news: {len(all_news)} berita umum")
        return all_news

    def fetch_all_news(self, ticker: str) -> list[dict[str, Any]]:
        """Mengambil semua berita dari seluruh sumber untuk satu ticker.

        Args:
            ticker: Kode saham.

        Returns:
            List of combined news items, dibatasi MAX_NEWS_PER_TICKER.
        """
        news: list[dict[str, Any]] = []

        # Finnhub
        finnhub_news = self.fetch_finnhub_news(ticker)
        news.extend(finnhub_news)

        # RSS
        rss_news = self.fetch_rss_news(ticker)
        news.extend(rss_news)

        # Sort by datetime (terbaru dulu) dan batasi
        news.sort(key=lambda x: x["datetime"], reverse=True)
        news = news[:MAX_NEWS_PER_TICKER]

        logger.info(f"{ticker}: Total {len(news)} berita terkumpul")
        return news
