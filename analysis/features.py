"""
TradSense - Layer 3: Feature Engine
=====================================
Menghitung seluruh indikator teknikal untuk setiap saham kandidat.
"""

from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from config import (
    ATR_PERIOD,
    BREAKOUT_PERIOD,
    EMA_PERIODS,
    RSI_PERIOD,
    VOLUME_SMA_PERIOD,
)
from database.models import StockFeature, get_session
from utils.logger import get_logger

logger = get_logger("analysis.features")


class FeatureEngine:
    """Menghitung fitur/indikator teknikal untuk analisis saham."""

    def __init__(self) -> None:
        """Inisialisasi FeatureEngine."""
        pass

    # --------------------------------------------------
    # Indikator Teknikal
    # --------------------------------------------------

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """Menghitung Exponential Moving Average.

        Args:
            series: Data series.
            period: Periode EMA.

        Returns:
            Series EMA.
        """
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
        """Menghitung Relative Strength Index.

        Args:
            series: Data series (close price).
            period: Periode RSI.

        Returns:
            Series RSI (0-100).
        """
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
        """Menghitung Average True Range.

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
        atr = true_range.ewm(com=period - 1, min_periods=period).mean()
        return atr

    @staticmethod
    def calculate_volume_ratio(
        volume: pd.Series, period: int = VOLUME_SMA_PERIOD
    ) -> pd.Series:
        """Menghitung rasio volume terhadap SMA Volume.

        Args:
            volume: Data volume.
            period: Periode SMA.

        Returns:
            Series volume ratio.
        """
        sma_volume = volume.rolling(window=period, min_periods=period).mean()
        ratio = volume / sma_volume.replace(0, np.nan)
        return ratio

    @staticmethod
    def calculate_close_strength(df: pd.DataFrame) -> pd.Series:
        """Menghitung Close Strength = (Close - Low) / (High - Low).

        Args:
            df: DataFrame dengan kolom close, low, high.

        Returns:
            Series close strength (0-1).
        """
        range_hl = df["high"] - df["low"]
        strength = (df["close"] - df["low"]) / range_hl.replace(0, np.nan)
        return strength.clip(0, 1)

    @staticmethod
    def calculate_breakout(
        close: pd.Series,
        high: pd.Series,
        period: int = BREAKOUT_PERIOD,
    ) -> tuple[pd.Series, pd.Series]:
        """Menghitung breakout dan highest high N hari.

        Args:
            close: Close price series.
            high: High price series.
            period: Periode lookback.

        Returns:
            Tuple (breakout_bool, highest_high).
        """
        highest_high = high.rolling(window=period, min_periods=period).max()
        # Breakout terjadi jika close hari ini >= highest high 20 hari
        breakout = close >= highest_high
        return breakout, highest_high

    @staticmethod
    def calculate_returns(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Menghitung return harian, 5 hari, dan 20 hari.

        Args:
            close: Close price series.

        Returns:
            Tuple (return_1d, return_5d, return_20d).
        """
        return_1d = close.pct_change(1)
        return_5d = close.pct_change(5)
        return_20d = close.pct_change(20)
        return return_1d, return_5d, return_20d

    # --------------------------------------------------
    # Compute All Features
    # --------------------------------------------------

    def compute_features(self, ticker: str, df: pd.DataFrame) -> Optional[dict[str, Any]]:
        """Menghitung seluruh fitur teknikal untuk satu saham.

        Args:
            ticker: Kode saham.
            df: DataFrame harga saham.

        Returns:
            Dictionary fitur terbaru atau None jika gagal.
        """
        if len(df) < 50:
            logger.warning(f"{ticker}: Data terlalu sedikit ({len(df)} baris)")
            return None

        try:
            df = df.copy().sort_values("date").reset_index(drop=True)

            # EMA
            for period in EMA_PERIODS:
                df[f"ema{period}"] = self.calculate_ema(df["close"], period)

            # RSI
            df["rsi14"] = self.calculate_rsi(df["close"], RSI_PERIOD)

            # ATR
            df["atr14"] = self.calculate_atr(df, ATR_PERIOD)
            df["atr_ratio"] = df["atr14"] / df["close"].replace(0, np.nan)

            # Volume Ratio
            df["volume_ratio"] = self.calculate_volume_ratio(df["volume"])

            # Close Strength
            df["close_strength"] = self.calculate_close_strength(df)

            # Breakout
            df["breakout_20d"], df["highest_high_20d"] = self.calculate_breakout(
                df["close"], df["high"]
            )

            # Returns
            df["return_1d"], df["return_5d"], df["return_20d"] = self.calculate_returns(
                df["close"]
            )

            # Average Value 20d
            value_traded = df["close"] * df["volume"]
            df["avg_value_20d"] = value_traded.rolling(window=20, min_periods=20).mean()

            # Ambil baris terbaru
            latest = df.iloc[-1]

            features = {
                "ticker": ticker,
                "date": latest.get("date", datetime.now()),
                "price": float(latest["close"]),
                "ema20": float(latest.get("ema20", 0)),
                "ema50": float(latest.get("ema50", 0)),
                "ema200": float(latest.get("ema200", 0)),
                "rsi14": float(latest.get("rsi14", 50)),
                "atr14": float(latest.get("atr14", 0)),
                "atr_ratio": float(latest.get("atr_ratio", 0)),
                "volume_ratio": float(latest.get("volume_ratio", 1)),
                "close_strength": float(latest.get("close_strength", 0.5)),
                "breakout_20d": bool(latest.get("breakout_20d", False)),
                "highest_high_20d": float(latest.get("highest_high_20d", 0)),
                "return_1d": float(latest.get("return_1d", 0)),
                "return_5d": float(latest.get("return_5d", 0)),
                "return_20d": float(latest.get("return_20d", 0)),
                "avg_value_20d": float(latest.get("avg_value_20d", 0)),
                "volume": float(latest["volume"]),
            }

            # Tentukan trend berdasarkan EMA
            features["trend"] = self._determine_trend(features)

            logger.debug(
                f"✓ {ticker}: RSI={features['rsi14']:.1f}, "
                f"ATR%={features['atr_ratio']*100:.1f}%, "
                f"VR={features['volume_ratio']:.1f}, "
                f"CS={features['close_strength']:.2f}"
            )
            return features

        except Exception as e:
            logger.error(f"Feature error for {ticker}: {e}")
            return None

    def _determine_trend(self, features: dict[str, Any]) -> str:
        """Tentukan trend berdasarkan susunan EMA.

        Args:
            features: Dictionary fitur.

        Returns:
            "bullish", "bearish", atau "sideways".
        """
        price = features["price"]
        ema20 = features["ema20"]
        ema50 = features["ema50"]
        ema200 = features["ema200"]

        if ema200 == 0:
            return "sideways"

        # Bullish: Price > EMA20 > EMA50 > EMA200
        if price > ema20 > ema50 > ema200:
            return "bullish"
        # Bearish: Price < EMA20 < EMA50 < EMA200
        elif price < ema20 < ema50 < ema200:
            return "bearish"
        else:
            return "sideways"

    def compute_all(
        self,
        stock_data: dict[str, pd.DataFrame],
        candidates: list[str],
        save_to_db: bool = True,
    ) -> list[dict[str, Any]]:
        """Menghitung fitur untuk semua kandidat.

        Args:
            stock_data: Dictionary {ticker: DataFrame}.
            candidates: List of ticker kandidat.
            save_to_db: Simpan ke database.

        Returns:
            List of feature dictionaries.
        """
        logger.info(f"Computing features untuk {len(candidates)} kandidat...")
        all_features: list[dict[str, Any]] = []

        for ticker in candidates:
            df = stock_data.get(ticker)
            if df is None:
                continue

            features = self.compute_features(ticker, df)
            if features:
                all_features.append(features)
                if save_to_db:
                    self._save_to_db(features)

        logger.info(f"✓ Features dihitung untuk {len(all_features)} saham")
        return all_features

    def _save_to_db(self, features: dict[str, Any]) -> None:
        """Simpan fitur ke database.

        Args:
            features: Dictionary fitur.
        """
        session = get_session()
        try:
            record = StockFeature(
                ticker=features["ticker"],
                date=features["date"],
                ema20=features["ema20"],
                ema50=features["ema50"],
                ema200=features["ema200"],
                rsi14=features["rsi14"],
                atr14=features["atr14"],
                volume_ratio=features["volume_ratio"],
                close_strength=features["close_strength"],
                breakout_20d=features["breakout_20d"],
                highest_high_20d=features["highest_high_20d"],
                return_1d=features["return_1d"],
                return_5d=features["return_5d"],
                return_20d=features["return_20d"],
                avg_value_20d=features["avg_value_20d"],
                atr_ratio=features["atr_ratio"],
            )
            session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB save error for features {features['ticker']}: {e}")
        finally:
            session.close()
