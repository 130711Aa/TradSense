"""
TradSense - Layer 5: AI Analyzer
==================================
Mengirim data saham ke Google Gemini dan mem-parse respons analisis.
"""

import json
import time
from datetime import datetime
from typing import Any

from config import (
    AI_TEMPERATURE,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)
from database.models import AIAnalysis, get_session
from utils.logger import get_logger

from .prompts import build_analysis_prompt

logger = get_logger("ai.analyzer")


class AIAnalyzer:
    """Analyzer AI menggunakan Google Gemini untuk analisis saham."""

    def __init__(self) -> None:
        """Inisialisasi AIAnalyzer dengan Gemini client."""
        self._client = None

    def _get_client(self) -> Any:
        """Lazy-load Gemini client.

        Returns:
            Google GenAI client instance.
        """
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=GEMINI_API_KEY)
        return self._client

    def _call_gemini(self, prompt: str) -> str:
        """Panggil Gemini API dengan prompt.

        Args:
            prompt: Prompt untuk analisis.

        Returns:
            Teks respons dari Gemini.
        """
        client = self._get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text or ""

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Parse respons JSON dari Gemini.

        Args:
            raw: Raw text response.

        Returns:
            Dictionary hasil parsing.
        """
        cleaned = raw.strip()

        # Hapus markdown code fence jika ada
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # Remove ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Coba ekstrak JSON dari dalam teks
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    pass
            logger.error(f"Gagal parse JSON response: {cleaned[:200]}")
            return {}

    def analyze_stock(
        self, stock_data: dict[str, Any], save_to_db: bool = True
    ) -> dict[str, Any]:
        """Analisis satu saham menggunakan Gemini.

        Args:
            stock_data: Dictionary berisi data teknikal, skor, dan berita.
            save_to_db: Simpan hasil ke database.

        Returns:
            Dictionary hasil analisis.
        """
        ticker = stock_data["ticker"]
        logger.info(f"Menganalisis {ticker} dengan Gemini ({GEMINI_MODEL})...")

        prompt = build_analysis_prompt(stock_data)

        try:
            raw_response = self._call_gemini(prompt)
            parsed = self._parse_response(raw_response)

            if not parsed:
                logger.warning(f"Empty parse result for {ticker}, using fallback")
                parsed = self._fallback_analysis(stock_data)

            result = {
                "ticker": ticker,
                "strategy": parsed.get("strategi", "TIDAK_DIREKOMENDASIKAN"),
                "confidence": parsed.get("confidence", 0),
                "analysis_text": parsed.get("analisis_teknikal", ""),
                "news_summary": parsed.get("analisis_berita", ""),
                "risk_summary": "\n".join(parsed.get("risiko", [])),
                "opportunity_summary": "\n".join(parsed.get("peluang", [])),
                "strategy_reason": parsed.get("alasan_strategi", ""),
                "sentiment": parsed.get("sentimen", {}),
                "raw_response": raw_response,
                "score": stock_data.get("total_score", 0),
                "features": stock_data.get("features", {}),
                "components": stock_data.get("components", {}),
            }

            if save_to_db:
                self._save_to_db(result)

            logger.info(
                f"✓ {ticker}: {result['strategy']} "
                f"(confidence: {result['confidence']}%)"
            )
            return result

        except Exception as e:
            logger.error(f"Gemini analysis error for {ticker}: {e}")
            fallback = self._fallback_analysis(stock_data)
            return {
                "ticker": ticker,
                "strategy": fallback.get("strategi", "TIDAK_DIREKOMENDASIKAN"),
                "confidence": fallback.get("confidence", 0),
                "analysis_text": "Analisis Gemini gagal, menggunakan fallback.",
                "news_summary": "",
                "risk_summary": "Gemini tidak tersedia",
                "opportunity_summary": "",
                "strategy_reason": "Fallback analysis",
                "sentiment": {},
                "raw_response": str(e),
                "score": stock_data.get("total_score", 0),
                "features": stock_data.get("features", {}),
                "components": stock_data.get("components", {}),
            }

    def _fallback_analysis(self, stock_data: dict[str, Any]) -> dict[str, Any]:
        """Analisis fallback berbasis rule jika Gemini gagal.

        Args:
            stock_data: Dictionary data saham.

        Returns:
            Dictionary analisis sederhana.
        """
        features = stock_data.get("features", {})
        score = stock_data.get("total_score", 0)
        vr = features.get("volume_ratio", 1)
        cs = features.get("close_strength", 0.5)
        rsi = features.get("rsi14", 50)

        if score >= 75 and cs > 0.8 and vr > 2:
            strategy = "BELI_SORE_JUAL_PAGI" if cs > 0.9 else "BELI_PAGI_JUAL_SORE"
            confidence = min(80, int(score * 0.8))
        elif score >= 60:
            strategy = "BELI_PAGI_JUAL_SORE"
            confidence = min(65, int(score * 0.7))
        else:
            strategy = "TIDAK_DIREKOMENDASIKAN"
            confidence = 30

        return {
            "strategi": strategy,
            "confidence": confidence,
            "analisis_teknikal": f"Score {score}, RSI {rsi:.0f}, VR {vr:.1f}x",
            "risiko": ["Analisis AI tidak tersedia"],
            "peluang": [f"Score tinggi: {score}"],
        }

    def analyze_all(
        self, top_stocks: list[dict[str, Any]], delay: float = 2.0
    ) -> list[dict[str, Any]]:
        """Analisis seluruh saham top menggunakan Gemini dengan batching.

        Args:
            top_stocks: List of stock data dictionaries.
            delay: Delay antar request (detik) jika menggunakan fallback.

        Returns:
            List of analysis results, diurutkan berdasarkan strategi & confidence.
        """
        from .prompts import build_batch_analysis_prompt
        logger.info(f"Menganalisis {len(top_stocks)} saham secara massal (batch) dengan Gemini...")
        
        results: list[dict[str, Any]] = []
        batch_success = False

        try:
            # 1. Buat prompt batch
            prompt = build_batch_analysis_prompt(top_stocks)
            raw_response = self._call_gemini(prompt)
            parsed_list = self._parse_response(raw_response)

            if isinstance(parsed_list, list) and len(parsed_list) > 0:
                # Map parsed items ke data asal
                stocks_map = {s["ticker"]: s for s in top_stocks}
                for parsed in parsed_list:
                    ticker = parsed.get("ticker")
                    if ticker and ticker in stocks_map:
                        stock_data = stocks_map[ticker]
                        res = {
                            "ticker": ticker,
                            "strategy": parsed.get("strategi", "TIDAK_DIREKOMENDASIKAN"),
                            "confidence": parsed.get("confidence", 0),
                            "analysis_text": parsed.get("analisis_teknikal", ""),
                            "news_summary": parsed.get("analisis_berita", ""),
                            "risk_summary": "\n".join(parsed.get("risiko", [])),
                            "opportunity_summary": "\n".join(parsed.get("peluang", [])),
                            "strategy_reason": parsed.get("alasan_strategi", ""),
                            "sentiment": parsed.get("sentimen", {}),
                            "raw_response": raw_response,
                            "score": stock_data.get("total_score", 0),
                            "features": stock_data.get("features", {}),
                            "components": stock_data.get("components", {}),
                        }
                        self._save_to_db(res)
                        results.append(res)
                
                # Pastikan seluruh saham terisi (jika ada yang terlewat dalam respon AI)
                analyzed_tickers = {r["ticker"] for r in results}
                for stock in top_stocks:
                    if stock["ticker"] not in analyzed_tickers:
                        logger.warning(f"Ticker {stock['ticker']} terlewat di batch AI, jalankan fallback...")
                        fallback_res = self.analyze_stock(stock, save_to_db=True)
                        results.append(fallback_res)
                
                batch_success = True
                logger.info("✓ Batch analysis dengan Gemini berhasil diselesaikan (1 API Call).")
            else:
                logger.warning("Respon batch Gemini tidak berbentuk list JSON array valid. Menggunakan fallback individual...")
        
        except Exception as e:
            logger.warning(f"Batch analysis gagal ({e}). Menggunakan fallback individual...")

        # 2. Fallback: Analisis saham satu per satu jika batch gagal
        if not batch_success:
            results = []
            for i, stock in enumerate(top_stocks, 1):
                try:
                    result = self.analyze_stock(stock, save_to_db=True)
                    results.append(result)
                except Exception as ex:
                    # Jika kena 429 atau error lainnya, jalankan fallback lokal rule-based
                    logger.error(f"Gagal menganalisis {stock['ticker']} via Gemini, menggunakan fallback teknikal: {ex}")
                    fb = self._fallback_analysis(stock)
                    res = {
                        "ticker": stock["ticker"],
                        "strategy": fb.get("strategi", "TIDAK_DIREKOMENDASIKAN"),
                        "confidence": fb.get("confidence", 0),
                        "analysis_text": "Analisis AI tidak tersedia (API Quota Limit), menggunakan fallback teknikal.",
                        "news_summary": "",
                        "risk_summary": "Batas kuota API Gemini terlampaui",
                        "opportunity_summary": f"Teknikal Score: {stock.get('total_score', 0):.1f}",
                        "strategy_reason": "Rule-based fallback",
                        "sentiment": {},
                        "raw_response": str(ex),
                        "score": stock.get("total_score", 0),
                        "features": stock.get("features", {}),
                        "components": stock.get("components", {}),
                    }
                    self._save_to_db(res)
                    results.append(res)

                if i < len(top_stocks) and batch_success is False:
                    time.sleep(delay)

        # Urutkan: rekomendasi dulu, lalu berdasarkan confidence
        results.sort(
            key=lambda x: (
                0 if x["strategy"] != "TIDAK_DIREKOMENDASIKAN" else 1,
                -x["confidence"],
            )
        )
        logger.info(f"✓ Gemini analysis selesai untuk {len(results)} saham")
        return results

    def _save_to_db(self, result: dict[str, Any]) -> None:
        """Simpan hasil analisis ke database.

        Args:
            result: Dictionary hasil analisis.
        """
        session = get_session()
        try:
            sentiment = result.get("sentiment", {})
            record = AIAnalysis(
                ticker=result["ticker"],
                date=datetime.now(),
                strategy=result["strategy"],
                confidence=result["confidence"],
                analysis_text=result["analysis_text"],
                risk_summary=result["risk_summary"],
                opportunity_summary=result["opportunity_summary"],
                news_summary=result["news_summary"],
                news_count=sum(sentiment.values()) if sentiment else 0,
                sentiment_positive=sentiment.get("positif", 0),
                sentiment_neutral=sentiment.get("netral", 0),
                sentiment_negative=sentiment.get("negatif", 0),
                raw_ai_response=result.get("raw_response", ""),
            )
            session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB save error for AI analysis {result['ticker']}: {e}")
        finally:
            session.close()
