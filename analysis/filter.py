"""
TradSense - Layer 2: Stock Filter
===================================
Filter saham berdasarkan likuiditas, harga, volatilitas, dan momentum.
"""

from typing import Optional

import numpy as np
import pandas as pd

from config import (
    MAX_CANDIDATES,
    MIN_ATR_RATIO,
    MIN_AVG_VALUE_20D,
    MIN_PRICE,
    VOLUME_SPIKE_MULTIPLIER,
)
from utils.logger import get_logger

logger = get_logger("analysis.filter")


class StockFilter:
    """Filter saham untuk menghasilkan candidate pool."""

    def __init__(
        self,
        min_avg_value: float = MIN_AVG_VALUE_20D,
        min_price: float = MIN_PRICE,
        min_atr_ratio: float = MIN_ATR_RATIO,
        volume_spike_mult: float = VOLUME_SPIKE_MULTIPLIER,
    ) -> None:
        """Inisialisasi StockFilter.

        Args:
            min_avg_value: Minimum average value traded 20 hari.
            min_price: Minimum harga saham.
            min_atr_ratio: Minimum ATR(14)/Close ratio.
            volume_spike_mult: Multiplier untuk volume spike.
        """
        self.min_avg_value = min_avg_value
        self.min_price = min_price
        self.min_atr_ratio = min_atr_ratio
        self.volume_spike_mult = volume_spike_mult

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Menghitung Average True Range (ATR).

        Args:
            df: DataFrame dengan kolom high, low, close.
            period: Periode ATR.

        Returns:
            Series ATR.
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period, min_periods=period).mean()
        return atr

    def check_liquidity(self, df: pd.DataFrame) -> bool:
        """Cek filter likuiditas: Avg Value Traded 20 hari > threshold.

        Args:
            df: DataFrame harga saham.

        Returns:
            True jika lolos filter.
        """
        if len(df) < 20:
            return False

        # Value traded = Close × Volume
        df_recent = df.tail(20).copy()
        value_traded = df_recent["close"] * df_recent["volume"]
        avg_value = value_traded.mean()

        return avg_value > self.min_avg_value

    def check_price(self, df: pd.DataFrame) -> bool:
        """Cek filter harga: Close terakhir > threshold.

        Args:
            df: DataFrame harga saham.

        Returns:
            True jika lolos filter.
        """
        if df.empty:
            return False
        latest_close = df["close"].iloc[-1]
        return latest_close > self.min_price

    def check_volatility(self, df: pd.DataFrame) -> bool:
        """Cek filter volatilitas: ATR(14)/Close > threshold.

        Args:
            df: DataFrame harga saham.

        Returns:
            True jika lolos filter.
        """
        if len(df) < 15:
            return False

        atr = self._calculate_atr(df, period=14)
        latest_atr = atr.iloc[-1]
        latest_close = df["close"].iloc[-1]

        if pd.isna(latest_atr) or latest_close == 0:
            return False

        atr_ratio = latest_atr / latest_close
        return atr_ratio > self.min_atr_ratio

    def check_volume_spike(self, df: pd.DataFrame) -> bool:
        """Cek filter momentum: Volume hari ini > X × SMA Volume 20.

        Args:
            df: DataFrame harga saham.

        Returns:
            True jika lolos filter.
        """
        if len(df) < 21:
            return False

        sma_volume_20 = df["volume"].iloc[-21:-1].mean()  # 20 hari sebelum hari ini
        today_volume = df["volume"].iloc[-1]

        if sma_volume_20 == 0:
            return False

        return today_volume > (self.volume_spike_mult * sma_volume_20)

    def filter_single(self, ticker: str, df: pd.DataFrame) -> dict[str, bool]:
        """Jalankan semua filter untuk satu saham.

        Args:
            ticker: Kode saham.
            df: DataFrame harga saham.

        Returns:
            Dictionary hasil filter per kriteria.
        """
        results = {
            "ticker": ticker,
            "liquidity": self.check_liquidity(df),
            "price": self.check_price(df),
            "volatility": self.check_volatility(df),
            "volume_spike": self.check_volume_spike(df),
        }
        results["passed"] = all([
            results["liquidity"],
            results["price"],
            results["volatility"],
            results["volume_spike"],
        ])
        return results

    def filter_all(
        self,
        stock_data: dict[str, pd.DataFrame],
        relax_if_few: bool = True,
    ) -> list[str]:
        """Filter seluruh saham dan hasilkan candidate pool.

        Jika jumlah kandidat terlalu sedikit, filter akan dilonggarkan
        secara bertahap (hapus volume spike requirement terlebih dahulu).

        Args:
            stock_data: Dictionary {ticker: DataFrame}.
            relax_if_few: Apakah melonggarkan filter jika kandidat < MIN_CANDIDATES.

        Returns:
            List of ticker yang lolos filter.
        """
        logger.info(f"Filtering {len(stock_data)} saham...")

        # Round 1: Full filter
        candidates: list[str] = []
        filter_stats = {"liquidity": 0, "price": 0, "volatility": 0, "volume_spike": 0}

        for ticker, df in stock_data.items():
            result = self.filter_single(ticker, df)

            for key in filter_stats:
                if result.get(key):
                    filter_stats[key] += 1

            if result["passed"]:
                candidates.append(ticker)

        logger.info(
            f"Filter stats: Likuiditas={filter_stats['liquidity']}, "
            f"Harga={filter_stats['price']}, "
            f"Volatilitas={filter_stats['volatility']}, "
            f"Volume Spike={filter_stats['volume_spike']}"
        )
        logger.info(f"Round 1: {len(candidates)} kandidat lolos semua filter")

        # Round 2: Relaxed filter (tanpa volume spike) jika terlalu sedikit
        if relax_if_few and len(candidates) < 10:
            logger.warning("Kandidat < 10, melonggarkan filter (tanpa volume spike)...")
            candidates = []
            for ticker, df in stock_data.items():
                result = self.filter_single(ticker, df)
                if result["liquidity"] and result["price"] and result["volatility"]:
                    candidates.append(ticker)

            logger.info(f"Round 2 (relaxed): {len(candidates)} kandidat")

        # Round 3: Only liquidity + price jika masih terlalu sedikit
        if relax_if_few and len(candidates) < 10:
            logger.warning("Masih < 10, hanya filter likuiditas + harga...")
            candidates = []
            for ticker, df in stock_data.items():
                result = self.filter_single(ticker, df)
                if result["liquidity"] and result["price"]:
                    candidates.append(ticker)

            logger.info(f"Round 3 (minimal): {len(candidates)} kandidat")

        # Cap di MAX_CANDIDATES
        if len(candidates) > MAX_CANDIDATES:
            logger.info(f"Membatasi kandidat ke {MAX_CANDIDATES}")
            candidates = candidates[:MAX_CANDIDATES]

        logger.info(f"✓ Candidate pool: {len(candidates)} saham")
        return candidates
