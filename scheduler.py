"""
TradSense - Scheduler
======================
APScheduler untuk menjalankan pipeline secara otomatis dua kali sehari:
1. Pagi (Sebelum buka market, 08:30 WIB): Rekomendasi BELI_PAGI -> JUAL_SORE.
2. Sore (Sebelum tutup market, 15:30 WIB): Rekomendasi BELI_SORE -> JUAL_PAGI.
"""

import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    SCHEDULE_PAGI_HOUR,
    SCHEDULE_PAGI_MINUTE,
    SCHEDULE_SORE_HOUR,
    SCHEDULE_SORE_MINUTE,
    SCHEDULE_TIMEZONE,
)
from database.models import init_db
from pipeline import TradSensePipeline
from utils.logger import get_logger, setup_logging

logger = get_logger("scheduler")


def run_session_pipeline(session_name: str) -> None:
    """Fungsi yang dipanggil scheduler untuk menjalankan sesi tertentu.

    Args:
        session_name: Nama sesi ("BELI_PAGI" atau "BELI_SORE").
    """
    logger.info(f"⏰ Scheduler triggered - memulai pipeline sesi: {session_name}")
    try:
        pipeline = TradSensePipeline()
        # skip_fetch=False agar mengambil data harga terbaru
        pipeline.run(skip_fetch=False, strategy_filter=session_name)
    except Exception as e:
        logger.error(f"Pipeline sesi {session_name} gagal: {e}")


def main() -> None:
    """Entry point untuk scheduler."""
    setup_logging()
    init_db()

    logger.info("=" * 60)
    logger.info("🤖 TradSense Scheduler")
    logger.info(f"   Sesi Pagi (Beli Pagi): {SCHEDULE_PAGI_HOUR:02d}:{SCHEDULE_PAGI_MINUTE:02d} WIB")
    logger.info(f"   Sesi Sore (Beli Sore): {SCHEDULE_SORE_HOUR:02d}:{SCHEDULE_SORE_MINUTE:02d} WIB")
    logger.info(f"   Timezone: {SCHEDULE_TIMEZONE}")
    logger.info("=" * 60)

    scheduler = BlockingScheduler()

    # 1. Jadwal Sesi Pagi (BELI_PAGI)
    trigger_pagi = CronTrigger(
        hour=SCHEDULE_PAGI_HOUR,
        minute=SCHEDULE_PAGI_MINUTE,
        timezone=SCHEDULE_TIMEZONE,
    )
    scheduler.add_job(
        run_session_pipeline,
        args=["BELI_PAGI"],
        trigger=trigger_pagi,
        id="session_pagi",
        name="TradSense Sesi Pagi",
        misfire_grace_time=3600,
    )

    # 2. Jadwal Sesi Sore (BELI_SORE)
    trigger_sore = CronTrigger(
        hour=SCHEDULE_SORE_HOUR,
        minute=SCHEDULE_SORE_MINUTE,
        timezone=SCHEDULE_TIMEZONE,
    )
    scheduler.add_job(
        run_session_pipeline,
        args=["BELI_SORE"],
        trigger=trigger_sore,
        id="session_sore",
        name="TradSense Sesi Sore",
        misfire_grace_time=3600,
    )

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Scheduler dimulai. Menunggu jadwal...")
    now = datetime.now()
    logger.info(f"Next Run Pagi: {trigger_pagi.get_next_fire_time(None, now)}")
    logger.info(f"Next Run Sore: {trigger_sore.get_next_fire_time(None, now)}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler dihentikan.")


if __name__ == "__main__":
    main()
