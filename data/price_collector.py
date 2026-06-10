"""
TradSense - Layer 1: Price Collector
=====================================
Mengambil data harga saham dari yfinance untuk seluruh saham BEI.

Fix cloud/Render deployment:
- Menggunakan curl-cffi session agar tidak diblokir Yahoo Finance di datacenter
- Retry logic dengan exponential backoff untuk menangani rate limit sementara
- Fallback ke yf.download() batch jika fetch_single gagal semua
"""

import time
import random
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

# Gunakan curl-cffi session agar tidak diblokir Yahoo Finance di server cloud
try:
    from curl_cffi import requests as curl_requests
    _CURL_SESSION = curl_requests.Session(impersonate="chrome")
    _USE_CURL = True
except ImportError:
    _CURL_SESSION = None
    _USE_CURL = False

from sqlalchemy import and_

from config import HISTORICAL_DAYS, IDX_TICKERS, YF_SUFFIX
from database.models import StockPrice, get_session
from utils.logger import get_logger

logger = get_logger("data.price_collector")

# Jumlah maksimal retry per ticker
MAX_RETRIES = 3
# Base delay untuk exponential backoff (detik)
RETRY_BASE_DELAY = 5.0


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

    def _get_yf_kwargs(self) -> dict:
        """Membuat kwargs untuk yfinance agar menggunakan curl-cffi session.

        Returns:
            Dict kwargs, termasuk session jika curl-cffi tersedia.
        """
        if _USE_CURL and _CURL_SESSION is not None:
            return {"session": _CURL_SESSION}
        return {}

    def fetch_single(
        self,
        ticker: str,
        days: int = HISTORICAL_DAYS,
        save_to_db: bool = True,
    ) -> Optional[pd.DataFrame]:
        """Mengambil data harga untuk satu ticker dengan retry logic.

        Args:
            ticker: Kode saham (tanpa suffix).
            days: Jumlah hari historis.
            save_to_db: Apakah menyimpan ke database.

        Returns:
            DataFrame dengan kolom OHLCV atau None jika gagal.
        """
        yf_ticker = self._build_yf_ticker(ticker)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(f"Fetching {yf_ticker} dari {start_date} (attempt {attempt})")
                stock = yf.Ticker(yf_ticker, **self._get_yf_kwargs())
                df = stock.history(start=start_date, auto_adjust=True)

                if df.empty:
                    logger.warning(f"Tidak ada data untuk {ticker} (attempt {attempt})")
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 2)
                        logger.debug(f"Retry {ticker} dalam {delay:.1f}s...")
                        time.sleep(delay)
                        continue
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
                err_str = str(e).lower()
                logger.warning(f"Error fetching {ticker} (attempt {attempt}): {e}")

                if attempt < MAX_RETRIES:
                    # Jika rate limit / network error, tunggu lebih lama
                    if any(k in err_str for k in ["429", "rate", "too many", "timeout", "connection"]):
                        delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                    else:
                        delay = RETRY_BASE_DELAY * attempt
                    logger.debug(f"Retry {ticker} dalam {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Gagal fetch {ticker} setelah {MAX_RETRIES} percobaan: {e}")
                    return None

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
        delay: float = 2.0,
    ) -> dict[str, pd.DataFrame]:
        """Mengambil data harga untuk seluruh ticker.

        Strategi 2 tahap:
        1. Fetch per ticker dengan retry (lebih terkontrol).
        2. Jika hasilnya < 20% dari total ticker, fallback ke yf.download() batch.

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

            # Rate limiting antar batch
            if i % batch_size == 0:
                logger.info(
                    f"Progress: {i}/{len(self.tickers)} "
                    f"({len(results)} OK, {len(failed)} gagal)"
                )
                time.sleep(delay)

        # Jika terlalu banyak yang gagal (> 80%), coba fallback batch download
        if len(results) < len(self.tickers) * 0.2 and failed:
            logger.warning(
                f"Terlalu banyak gagal ({len(failed)} ticker). "
                "Mencoba fallback yf.download() batch..."
            )
            fallback_results = self._fetch_batch_fallback(failed)
            results.update(fallback_results)

        logger.info(
            f"Selesai: {len(results)}/{len(self.tickers)} saham berhasil. "
            f"Gagal: {failed[:10]}{'...' if len(failed) > 10 else ''}"
        )

        if not results:
            logger.error(
                "TIDAK ADA DATA berhasil diambil. "
                "Kemungkinan Yahoo Finance memblokir IP server ini. "
                "Coba jalankan ulang atau periksa koneksi."
            )

        return results

    def _fetch_batch_fallback(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        """Fallback: download semua ticker sekaligus via yf.download() batch.

        Lebih efisien dan kadang berhasil ketika fetch_single diblokir,
        karena menggunakan satu request untuk banyak ticker.

        Args:
            tickers: Daftar kode saham yang gagal di fetch_single.

        Returns:
            Dictionary {ticker: DataFrame}.
        """
        results: dict[str, pd.DataFrame] = {}
        start_date = (datetime.now() - timedelta(days=HISTORICAL_DAYS)).strftime("%Y-%m-%d")
        yf_tickers = [self._build_yf_ticker(t) for t in tickers]

        # Proses dalam chunk 50 ticker agar tidak terlalu besar
        chunk_size = 50
        for chunk_start in range(0, len(yf_tickers), chunk_size):
            chunk_yf = yf_tickers[chunk_start:chunk_start + chunk_size]
            chunk_raw = tickers[chunk_start:chunk_start + chunk_size]

            try:
                logger.info(f"Batch download {len(chunk_yf)} ticker...")
                kwargs = self._get_yf_kwargs()
                raw = yf.download(
                    chunk_yf,
                    start=start_date,
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    **kwargs,
                )

                if raw.empty:
                    logger.warning("Batch download menghasilkan data kosong.")
                    continue

                for ticker, yf_t in zip(chunk_raw, chunk_yf):
                    try:
                        # Ambil slice per ticker dari MultiIndex column
                        if len(chunk_yf) == 1:
                            df_t = raw.copy()
                        else:
                            df_t = raw[yf_t].copy()

                        if df_t.empty or df_t["Close"].isna().all():
                            continue

                        df_t = df_t[["Open", "High", "Low", "Close", "Volume"]].copy()
                        df_t.columns = ["open", "high", "low", "close", "volume"]
                        df_t.index.name = "date"
                        df_t = df_t.reset_index()
                        df_t["ticker"] = ticker

                        if df_t["date"].dt.tz is not None:
                            df_t["date"] = df_t["date"].dt.tz_localize(None)

                        df_t = df_t.dropna(subset=["close"])
                        if df_t.empty:
                            continue

                        self._save_to_db(ticker, df_t)
                        results[ticker] = df_t
                        logger.debug(f"✓ Batch {ticker}: {len(df_t)} baris")

                    except Exception as e:
                        logger.warning(f"Batch parse error {ticker}: {e}")

                time.sleep(2.0)

            except Exception as e:
                logger.error(f"Batch download chunk gagal: {e}")

        logger.info(f"Fallback batch selesai: {len(results)} ticker berhasil")
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
