"""
TradSense - Pipeline Utama
============================
Orchestrator yang menjalankan seluruh layer secara berurutan.
"""

import time
from datetime import datetime
from typing import Any

from ai.analyzer import AIAnalyzer
from analysis.features import FeatureEngine
from analysis.filter import StockFilter
from bot.telegram_reporter import TelegramReporter
from data.news_collector import NewsCollector
from data.price_collector import PriceCollector
from database.models import RunLog, get_session, init_db
from scoring.engine import ScoringEngine
from utils.logger import get_logger

logger = get_logger("pipeline")


class TradSensePipeline:
    """Pipeline utama TradSense yang mengoordinasikan seluruh layer."""

    def __init__(self) -> None:
        """Inisialisasi semua komponen pipeline."""
        self.price_collector = PriceCollector()
        self.news_collector = NewsCollector()
        self.stock_filter = StockFilter()
        self.feature_engine = FeatureEngine()
        self.scoring_engine = ScoringEngine()
        self.ai_analyzer = AIAnalyzer()
        self.telegram = TelegramReporter()

    def run(
        self, skip_fetch: bool = False, strategy_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Jalankan pipeline lengkap.

        Args:
            skip_fetch: Skip fetching data (gunakan data dari DB).
            strategy_filter: Filter strategi rekomendasi ("BELI_SORE" atau "BELI_PAGI").

        Returns:
            List hasil analisis AI.
        """
        pipeline_start = time.time()
        logger.info("=" * 60)
        logger.info("🚀 TRADSENSE PIPELINE DIMULAI")
        if strategy_filter:
            logger.info(f"   Mode Sesi: {strategy_filter}")
        logger.info(f"   Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}")
        logger.info("=" * 60)

        # Init database
        init_db()

        try:
            # ══════════════════════════════════════════
            # LAYER 1: DATA COLLECTION
            # ══════════════════════════════════════════
            stock_data = self._run_layer1(skip_fetch)
            if not stock_data:
                raise RuntimeError("Layer 1 gagal: Tidak ada data saham")

            # ══════════════════════════════════════════
            # LAYER 2: FILTERING
            # ══════════════════════════════════════════
            candidates = self._run_layer2(stock_data)
            if not candidates:
                raise RuntimeError("Layer 2 gagal: Tidak ada kandidat")

            # ══════════════════════════════════════════
            # LAYER 3: FEATURE ENGINE
            # ══════════════════════════════════════════
            features_list = self._run_layer3(stock_data, candidates)
            if not features_list:
                raise RuntimeError("Layer 3 gagal: Tidak ada fitur")

            # ══════════════════════════════════════════
            # LAYER 4: SCORING ENGINE
            # ══════════════════════════════════════════
            top_stocks = self._run_layer4(features_list)
            if not top_stocks:
                raise RuntimeError("Layer 4 gagal: Tidak ada skor")

            # ══════════════════════════════════════════
            # LAYER 5: NEWS + AI ANALYSIS
            # ══════════════════════════════════════════
            analyses = self._run_layer5(top_stocks)

            # ══════════════════════════════════════════
            # OUTPUT: TELEGRAM REPORT
            # ══════════════════════════════════════════
            self._send_report(analyses, strategy_filter=strategy_filter)

            duration = time.time() - pipeline_start
            logger.info("=" * 60)
            logger.info(f"✅ PIPELINE SELESAI dalam {duration:.1f} detik")
            logger.info("=" * 60)

            self._log_run("pipeline", "success", f"Completed ({strategy_filter}) in {duration:.1f}s", duration)
            return analyses

        except Exception as e:
            duration = time.time() - pipeline_start
            logger.error(f"❌ PIPELINE ERROR: {e}")
            self._log_run("pipeline", "error", str(e), duration)

            # Kirim error alert ke Telegram
            try:
                self.telegram.send_error_alert(str(e))
            except Exception:
                pass

            raise

    def _run_layer1(self, skip_fetch: bool) -> dict:
        """Layer 1: Data Collection."""
        start = time.time()
        logger.info("━" * 40)
        logger.info("📊 LAYER 1: DATA COLLECTION")
        logger.info("━" * 40)

        if skip_fetch:
            logger.info("Skip fetch, loading dari database...")
            stock_data = self.price_collector.load_all_from_db()
        else:
            stock_data = self.price_collector.fetch_all()

        duration = time.time() - start
        logger.info(f"Layer 1 selesai: {len(stock_data)} saham ({duration:.1f}s)")
        self._log_run("layer1_data", "success", f"{len(stock_data)} stocks", duration)
        return stock_data

    def _run_layer2(self, stock_data: dict) -> list[str]:
        """Layer 2: Filtering."""
        start = time.time()
        logger.info("━" * 40)
        logger.info("🔍 LAYER 2: FILTERING")
        logger.info("━" * 40)

        candidates = self.stock_filter.filter_all(stock_data)

        duration = time.time() - start
        logger.info(f"Layer 2 selesai: {len(candidates)} kandidat ({duration:.1f}s)")
        self._log_run("layer2_filter", "success", f"{len(candidates)} candidates", duration)
        return candidates

    def _run_layer3(self, stock_data: dict, candidates: list[str]) -> list[dict]:
        """Layer 3: Feature Engine."""
        start = time.time()
        logger.info("━" * 40)
        logger.info("⚙️ LAYER 3: FEATURE ENGINE")
        logger.info("━" * 40)

        features_list = self.feature_engine.compute_all(stock_data, candidates)

        duration = time.time() - start
        logger.info(f"Layer 3 selesai: {len(features_list)} features ({duration:.1f}s)")
        self._log_run("layer3_features", "success", f"{len(features_list)} features", duration)
        return features_list

    def _run_layer4(self, features_list: list[dict]) -> list[dict]:
        """Layer 4: Scoring Engine."""
        start = time.time()
        logger.info("━" * 40)
        logger.info("🏆 LAYER 4: SCORING ENGINE")
        logger.info("━" * 40)

        top_stocks = self.scoring_engine.score_all(features_list)

        duration = time.time() - start
        logger.info(f"Layer 4 selesai: Top {len(top_stocks)} saham ({duration:.1f}s)")
        self._log_run("layer4_scoring", "success", f"Top {len(top_stocks)}", duration)
        return top_stocks

    def _run_layer5(self, top_stocks: list[dict]) -> list[dict]:
        """Layer 5: News + AI Analysis."""
        start = time.time()
        logger.info("━" * 40)
        logger.info("🤖 LAYER 5: NEWS + AI ANALYSIS")
        logger.info("━" * 40)

        # Ambil berita untuk setiap saham
        for stock in top_stocks:
            ticker = stock["ticker"]
            news = self.news_collector.fetch_all_news(ticker)
            stock["news"] = news

        # AI Analysis
        analyses = self.ai_analyzer.analyze_all(top_stocks)

        duration = time.time() - start
        logger.info(f"Layer 5 selesai: {len(analyses)} analisis ({duration:.1f}s)")
        self._log_run("layer5_ai", "success", f"{len(analyses)} analyses", duration)
        return analyses

    def _send_report(
        self, analyses: list[dict], strategy_filter: str | None = None
    ) -> None:
        """Kirim laporan ke Telegram."""
        logger.info("━" * 40)
        logger.info("📤 MENGIRIM LAPORAN KE TELEGRAM")
        logger.info("━" * 40)

        success = self.telegram.send_report(analyses, strategy_filter=strategy_filter)
        if success:
            logger.info("✓ Laporan berhasil dikirim ke Telegram")
        else:
            logger.warning("⚠ Gagal mengirim ke Telegram, print ke console...")
            report = self.telegram.format_report(analyses, strategy_filter=strategy_filter)
            print("\n" + report)

    def _log_run(
        self, layer: str, status: str, message: str, duration: float
    ) -> None:
        """Log eksekusi ke database."""
        session = get_session()
        try:
            record = RunLog(
                run_date=datetime.now(),
                layer=layer,
                status=status,
                message=message,
                duration_seconds=duration,
            )
            session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Run log error: {e}")
        finally:
            session.close()
