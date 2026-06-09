"""
TradSense - Layer 4: Scoring Engine
=====================================
Menghitung skor 0-100 untuk setiap saham kandidat.
Formula scoring modular dan mudah diubah.
"""

from datetime import datetime
from typing import Any

import numpy as np

from config import SCORING_WEIGHTS, TOP_N_FOR_AI
from database.models import StockScore, get_session
from utils.logger import get_logger

logger = get_logger("scoring.engine")


class ScoringEngine:
    """Mesin scoring modular untuk saham kandidat."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or SCORING_WEIGHTS.copy()
        total_weight = sum(self.weights.values())
        if total_weight != 100:
            logger.warning(f"Total weight = {total_weight}, normalizing to 100")
            factor = 100 / total_weight
            self.weights = {k: v * factor for k, v in self.weights.items()}

    @staticmethod
    def _score_liquidity(features: dict[str, Any]) -> float:
        avg_val = features.get("avg_value_20d", 0)
        if avg_val <= 0:
            return 0.0
        # 5B = 0, 50B+ = 100
        score = min(100, max(0, (avg_val - 5e9) / (50e9 - 5e9) * 100))
        return score

    @staticmethod
    def _score_volatility(features: dict[str, Any]) -> float:
        atr_ratio = features.get("atr_ratio", 0)
        if atr_ratio <= 0:
            return 0.0
        # 3% = 30, 5% = 60, 8%+ = 100
        pct = atr_ratio * 100
        if pct < 3:
            return pct / 3 * 30
        elif pct < 5:
            return 30 + (pct - 3) / 2 * 30
        elif pct < 8:
            return 60 + (pct - 5) / 3 * 40
        else:
            return 100.0

    @staticmethod
    def _score_volume_spike(features: dict[str, Any]) -> float:
        vr = features.get("volume_ratio", 1.0)
        if vr <= 1.0:
            return 0.0
        # 1.5 = 30, 2.0 = 50, 3.0 = 80, 5.0+ = 100
        if vr < 1.5:
            return (vr - 1.0) / 0.5 * 30
        elif vr < 2.0:
            return 30 + (vr - 1.5) / 0.5 * 20
        elif vr < 3.0:
            return 50 + (vr - 2.0) / 1.0 * 30
        elif vr < 5.0:
            return 80 + (vr - 3.0) / 2.0 * 20
        else:
            return 100.0

    @staticmethod
    def _score_close_strength(features: dict[str, Any]) -> float:
        cs = features.get("close_strength", 0.5)
        return min(100, max(0, cs * 100))

    @staticmethod
    def _score_breakout(features: dict[str, Any]) -> float:
        if features.get("breakout_20d", False):
            return 100.0
        price = features.get("price", 0)
        hh = features.get("highest_high_20d", 0)
        if hh <= 0:
            return 0.0
        ratio = price / hh
        if ratio >= 0.98:
            return 80.0
        elif ratio >= 0.95:
            return 50.0
        elif ratio >= 0.90:
            return 30.0
        else:
            return 0.0

    @staticmethod
    def _score_trend_ema(features: dict[str, Any]) -> float:
        trend = features.get("trend", "sideways")
        if trend == "bullish":
            return 100.0
        elif trend == "sideways":
            p = features.get("price", 0)
            e20 = features.get("ema20", 0)
            if e20 > 0 and p > e20:
                return 60.0
            return 40.0
        else:
            return 10.0

    @staticmethod
    def _score_rsi(features: dict[str, Any]) -> float:
        rsi = features.get("rsi14", 50)
        if 55 <= rsi <= 70:
            return 100.0
        elif 45 <= rsi < 55:
            return 70.0
        elif 70 < rsi <= 80:
            return 50.0
        elif 30 <= rsi < 45:
            return 40.0
        elif rsi > 80:
            return 20.0
        else:
            return 10.0

    def score_stock(self, features: dict[str, Any]) -> dict[str, Any]:
        component_scores = {
            "liquidity": self._score_liquidity(features),
            "volatility": self._score_volatility(features),
            "volume_spike": self._score_volume_spike(features),
            "close_strength": self._score_close_strength(features),
            "breakout": self._score_breakout(features),
            "trend_ema": self._score_trend_ema(features),
            "rsi": self._score_rsi(features),
        }
        total = sum(
            component_scores[k] * (self.weights[k] / 100)
            for k in component_scores
        )
        return {
            "ticker": features["ticker"],
            "total_score": round(total, 1),
            "components": component_scores,
            "features": features,
        }

    def score_all(
        self,
        features_list: list[dict[str, Any]],
        top_n: int = TOP_N_FOR_AI,
        save_to_db: bool = True,
    ) -> list[dict[str, Any]]:
        logger.info(f"Scoring {len(features_list)} saham...")
        scored: list[dict[str, Any]] = []
        for features in features_list:
            result = self.score_stock(features)
            scored.append(result)

        scored.sort(key=lambda x: x["total_score"], reverse=True)
        for i, s in enumerate(scored, 1):
            s["rank"] = i

        if save_to_db:
            self._save_scores_to_db(scored)

        top = scored[:top_n]
        logger.info(f"✓ Top {len(top)} saham:")
        for s in top:
            logger.info(
                f"  #{s['rank']} {s['ticker']}: {s['total_score']:.1f}"
            )
        return top

    def _save_scores_to_db(self, scored: list[dict[str, Any]]) -> None:
        session = get_session()
        try:
            for s in scored:
                record = StockScore(
                    ticker=s["ticker"],
                    date=datetime.now(),
                    score_liquidity=s["components"]["liquidity"],
                    score_volatility=s["components"]["volatility"],
                    score_volume_spike=s["components"]["volume_spike"],
                    score_close_strength=s["components"]["close_strength"],
                    score_breakout=s["components"]["breakout"],
                    score_trend_ema=s["components"]["trend_ema"],
                    score_rsi=s["components"]["rsi"],
                    total_score=s["total_score"],
                    rank=s["rank"],
                )
                session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB save error for scores: {e}")
        finally:
            session.close()
