"""
TradSense - Layer 1: Price Collector
=====================================
Mengambil data harga saham dari yfinance untuk seluruh saham BEI.
"""

import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import and_

# Monkeypatch to avoid Yahoo Finance 429 crumb/cookie errors on modern python environments
yf.data.YfData.user_agent_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

from config import HISTORICAL_DAYS, IDX_TICKERS, YF_SUFFIX
from database.models import StockPrice, get_session
from utils.logger import get_logger

logger = get_logger("data.price_collector")


class PriceCollector:
    """Mengumpulkan data harga saham dari yfinance."""

    def __init__(self, tickers: Optional[list[str]] = None) -> None:
        """Inisialisasi PriceCollector.

        Args:
            tickers: Daftar ticker saham. Default menggunakan IDX_TICKERS dari config.
        """
        self.tickers = tickers or IDX_TICKERS
        self.suffix = YF_SUFFIX

    def _build_yf_ticker(self, ticker: str) -> str:
        """Menambahkan suffix yfinance ke ticker.

        Args:
            ticker: Ticker saham tanpa suffix.

        Returns:
            Ticker dengan suffix (contoh: BBCA.JK).
        """
        return f"{ticker}{self.suffix}"

    def fetch_single(
        self,
        ticker: str,
        days: int = HISTORICAL_DAYS,
        save_to_db: bool = True,
    ) -> Optional[pd.DataFrame]:
        """Mengambil data harga untuk satu ticker.

        Args:
            ticker: Kode saham (tanpa suffix).
            days: Jumlah hari historis.
            save_to_db: Apakah menyimpan ke database.

        Returns:
            DataFrame dengan kolom OHLCV atau None jika gagal.
        """
        yf_ticker = self._build_yf_ticker(ticker)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            logger.debug(f"Fetching {yf_ticker} dari {start_date}")
            stock = yf.Ticker(yf_ticker)
            df = stock.history(start=start_date, auto_adjust=True)

            if df.empty:
                logger.warning(f"Tidak ada data untuk {ticker}")
                return None

            # Bersihkan kolom
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            df.index.name = "date"
            df = df.reset_index()
            df["ticker"] = ticker

            # Konversi timezone-aware datetime ke naive
            if df["date"].dt.tz is not None:
                df["date"] = df["date"].dt.tz_localize(None)

            if save_to_db:
                self._save_to_db(ticker, df)

            logger.debug(f"✓ {ticker}: {len(df)} baris data")
            return df

        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            return None

    def _save_to_db(self, ticker: str, df: pd.DataFrame) -> None:
        """Menyimpan data harga ke database.

        Args:
            ticker: Kode saham.
            df: DataFrame dengan data harga.
        """
        session = get_session()
        try:
            # Hapus data lama untuk ticker ini
            session.query(StockPrice).filter(
                StockPrice.ticker == ticker
            ).delete()

            # Insert data baru
            records = []
            for _, row in df.iterrows():
                records.append(
                    StockPrice(
                        ticker=ticker,
                        date=row["date"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )

            session.bulk_save_objects(records)
            session.commit()
            logger.debug(f"Saved {len(records)} records for {ticker}")

        except Exception as e:
            session.rollback()
            logger.error(f"DB save error for {ticker}: {e}")
        finally:
            session.close()

    def fetch_all(
        self,
        batch_size: int = 10,
        delay: float = 1.0,
    ) -> dict[str, pd.DataFrame]:
        """Mengambil data harga untuk seluruh ticker.

        Args:
            batch_size: Jumlah ticker per batch.
            delay: Delay antar batch (detik) untuk menghindari rate limit.

        Returns:
            Dictionary {ticker: DataFrame}.
        """
        logger.info(f"Mulai fetch data {len(self.tickers)} saham...")
        results: dict[str, pd.DataFrame] = {}
        failed: list[str] = []

        for i, ticker in enumerate(self.tickers, 1):
            df = self.fetch_single(ticker)
            if df is not None:
                results[ticker] = df
            else:
                failed.append(ticker)

            # Rate limiting
            if i % batch_size == 0:
                logger.info(f"Progress: {i}/{len(self.tickers)} ({len(results)} OK, {len(failed)} gagal)")
                time.sleep(delay)

        logger.info(
            f"Selesai: {len(results)}/{len(self.tickers)} saham berhasil. "
            f"Gagal: {failed[:10]}{'...' if len(failed) > 10 else ''}"
        )
        return results

    def load_from_db(self, ticker: str) -> Optional[pd.DataFrame]:
        """Memuat data harga dari database.

        Args:
            ticker: Kode saham.

        Returns:
            DataFrame dengan data harga atau None.
        """
        session = get_session()
        try:
            rows = (
                session.query(StockPrice)
                .filter(StockPrice.ticker == ticker)
                .order_by(StockPrice.date.asc())
                .all()
            )

            if not rows:
                return None

            data = [
                {
                    "date": r.date,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "ticker": r.ticker,
                }
                for r in rows
            ]
            return pd.DataFrame(data)

        except Exception as e:
            logger.error(f"DB load error for {ticker}: {e}")
            return None
        finally:
            session.close()

    def load_all_from_db(self) -> dict[str, pd.DataFrame]:
        """Memuat semua data harga dari database.

        Returns:
            Dictionary {ticker: DataFrame}.
        """
        results: dict[str, pd.DataFrame] = {}
        for ticker in self.tickers:
            df = self.load_from_db(ticker)
            if df is not None and len(df) >= 50:  # Minimal 50 hari data
                results[ticker] = df
        logger.info(f"Loaded {len(results)} saham dari database")
        return results
