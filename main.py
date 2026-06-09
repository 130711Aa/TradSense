"""
TradSense - Entry Point
========================
CLI untuk menjalankan pipeline secara manual atau mode tertentu.
"""

import argparse
import sys

from database.models import init_db
from pipeline import TradSensePipeline
from utils.logger import setup_logging, get_logger


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TradSense - Sistem Rekomendasi Saham AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python main.py                    # Jalankan pipeline lengkap
  python main.py --skip-fetch       # Gunakan data dari database
  python main.py --mode scheduler   # Jalankan scheduler harian
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["run", "scheduler", "test", "listener", "render"],
        default="run",
        help="Mode eksekusi (default: run)",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetching data, gunakan data dari database",
    )
    parser.add_argument(
        "--session",
        choices=["BELI_SORE", "BELI_PAGI"],
        default=None,
        help="Sesi strategi rekomendasi (BELI_SORE atau BELI_PAGI)",
    )

    args = parser.parse_args()

    # Setup
    setup_logging()
    logger = get_logger("main")
    init_db()

    if args.mode == "run":
        logger.info(f"Mode: Single Run (Session: {args.session or 'ALL'})")
        pipeline = TradSensePipeline()
        try:
            results = pipeline.run(skip_fetch=args.skip_fetch, strategy_filter=args.session)
            logger.info(f"Pipeline selesai dengan {len(results)} hasil analisis")
        except Exception as e:
            logger.error(f"Pipeline gagal: {e}")
            sys.exit(1)

    elif args.mode == "scheduler":
        logger.info("Mode: Scheduler")
        from scheduler import main as scheduler_main
        scheduler_main()

    elif args.mode == "listener":
        logger.info("Mode: Telegram Listener")
        from bot.listener import run_listener
        run_listener()

    elif args.mode == "render":
        logger.info("Mode: Render Consolidated Web Service")
        from server import main as render_main
        render_main()

    elif args.mode == "test":
        logger.info("Mode: Test")
        _run_test()


def _run_test() -> None:
    """Jalankan test sederhana untuk memverifikasi semua komponen."""
    logger = get_logger("test")

    logger.info("Testing komponen...")

    # Test 1: Config
    from config import IDX_TICKERS, SCORING_WEIGHTS
    logger.info(f"✓ Config: {len(IDX_TICKERS)} tickers, weights={SCORING_WEIGHTS}")

    # Test 2: Database
    from database.models import init_db, get_session
    init_db()
    session = get_session()
    session.close()
    logger.info("✓ Database: OK")

    # Test 3: Feature Engine
    from analysis.features import FeatureEngine
    import pandas as pd
    import numpy as np

    fe = FeatureEngine()
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100)
    test_df = pd.DataFrame({
        "date": dates,
        "open": np.random.uniform(1000, 2000, 100),
        "high": np.random.uniform(1500, 2500, 100),
        "low": np.random.uniform(500, 1500, 100),
        "close": np.random.uniform(1000, 2000, 100),
        "volume": np.random.uniform(1e6, 1e8, 100),
    })
    features = fe.compute_features("TEST", test_df)
    if features:
        logger.info(f"✓ Feature Engine: RSI={features['rsi14']:.1f}")
    else:
        logger.error("✗ Feature Engine: Failed")

    # Test 4: Scoring Engine
    from scoring.engine import ScoringEngine
    se = ScoringEngine()
    if features:
        score = se.score_stock(features)
        logger.info(f"✓ Scoring Engine: {score['ticker']} = {score['total_score']:.1f}")

    # Test 5: Telegram formatting
    from bot.telegram_reporter import TelegramReporter
    tr = TelegramReporter()
    test_analysis = [{
        "ticker": "TEST",
        "strategy": "BELI_SORE_JUAL_PAGI",
        "confidence": 75,
        "score": 85,
        "features": features or {},
        "analysis_text": "Test analysis",
        "risk_summary": "Test risk",
        "opportunity_summary": "Test opportunity",
        "news_summary": "Test news",
        "sentiment": {"positif": 3, "netral": 1, "negatif": 0},
    }]
    report = tr.format_report(test_analysis)
    logger.info(f"✓ Telegram: Report length = {len(report)} chars")

    logger.info("=" * 40)
    logger.info("✅ Semua test passed!")


if __name__ == "__main__":
    main()
