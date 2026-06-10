"""
TradSense - Render Deploy Server
================================
Server HTTP gabungan untuk deploy ke Render (Free Web Service).
Menjalankan Web Health Check (agar Render tetap aktif),
Telegram Bot Listener, dan Scheduler Harian dalam satu proses.

Fix arsitektur:
- HTTP health-check server dijalankan di thread terpisah
- Bot Telegram (asyncio) dijalankan di main thread via asyncio.run()
- Scheduler APScheduler dijalankan sebagai BackgroundScheduler
  sebelum asyncio loop dimulai
"""

import asyncio
import http.server
import os
import sys
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Setup path agar import module lokal berfungsi
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from config import (
    SCHEDULE_PAGI_HOUR,
    SCHEDULE_PAGI_MINUTE,
    SCHEDULE_SORE_HOUR,
    SCHEDULE_SORE_MINUTE,
    SCHEDULE_TIMEZONE,
    TELEGRAM_BOT_TOKEN,
)
from database.models import init_db
from scheduler import run_session_pipeline
from utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger("render_server")


# ──────────────────────────────────────────────────────────────
# Health Check HTTP Server
# ──────────────────────────────────────────────────────────────

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    """Handler sederhana untuk health check Render."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TradSense AI Bot</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #0f172a;
                    color: #e2e8f0;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }}
                .card {{
                    background-color: #1e293b;
                    padding: 30px 40px;
                    border-radius: 12px;
                    border: 1px solid #334155;
                    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
                    text-align: center;
                    max-width: 450px;
                }}
                h1 {{
                    color: #38bdf8;
                    margin-top: 0;
                    font-size: 24px;
                }}
                .status-badge {{
                    background-color: #15803d;
                    color: #bbf7d0;
                    padding: 4px 12px;
                    border-radius: 9999px;
                    font-size: 14px;
                    font-weight: bold;
                    display: inline-block;
                    margin-bottom: 20px;
                }}
                .info-grid {{
                    text-align: left;
                    font-family: monospace;
                    background: #0f172a;
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid #1e293b;
                    font-size: 13px;
                }}
                p {{ margin: 6px 0; }}
                .accent {{ color: #fb7185; }}
            </style>
        </head>
        <body>
            <div class="card">
                <span class="status-badge">🟢 ONLINE</span>
                <h1>🤖 TradSense AI Engine</h1>
                <p style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">
                    Sistem Analisis Saham BEI Terintegrasi
                </p>
                <div class="info-grid">
                    <p>Status Bot   : <span style="color: #4ade80;">Active &amp; Listening</span></p>
                    <p>Timezone     : {SCHEDULE_TIMEZONE}</p>
                    <p>Beli Pagi    : {SCHEDULE_PAGI_HOUR:02d}:{SCHEDULE_PAGI_MINUTE:02d} WIB</p>
                    <p>Beli Sore    : {SCHEDULE_SORE_HOUR:02d}:{SCHEDULE_SORE_MINUTE:02d} WIB</p>
                    <p>Waktu Server : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <p style="font-size: 11px; color: #64748b; margin-top: 20px;">
                    Developed for TradSense Platform
                </p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Mute log default HTTP request agar console bersih
        pass


def start_http_server() -> None:
    """Menjalankan HTTP health-check server di thread terpisah."""
    port = int(os.environ.get("PORT", 8000))
    server_address = ("", port)
    httpd = http.server.HTTPServer(server_address, HealthCheckHandler)
    logger.info(f"🌐 Health Check HTTP server berjalan di port {port}")
    httpd.serve_forever()


# ──────────────────────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────────────────────

def _is_market_day() -> bool:
    """Cek apakah hari ini adalah hari kerja (Senin-Jumat). BEI tutup weekend."""
    return datetime.now().weekday() < 5  # 0=Senin, 4=Jumat


def run_session_pipeline_safe(session_name: str) -> None:
    """Wrapper run_session_pipeline dengan pengecekan hari kerja.

    Args:
        session_name: Nama sesi ("BELI_PAGI" atau "BELI_SORE").
    """
    if not _is_market_day():
        logger.info(
            f"⏭ Skip pipeline {session_name} — hari ini bukan hari kerja BEI "
            f"(hari ke-{datetime.now().weekday()+1}/7)"
        )
        return
    run_session_pipeline(session_name)


def start_scheduler() -> BackgroundScheduler:
    """Menjalankan Background Scheduler dan mengembalikan instance-nya.

    Returns:
        BackgroundScheduler yang sudah berjalan.
    """
    logger.info("Memulai Background Scheduler...")
    # misfire_grace_time=300 (5 menit): jika server restart dan jadwal
    # sudah lewat > 5 menit, job dilewati — bukan dijalankan langsung.
    scheduler = BackgroundScheduler()

    # 1. Jadwal Sesi Pagi (BELI_PAGI) — Senin–Jumat 08:30 WIB
    trigger_pagi = CronTrigger(
        day_of_week="mon-fri",
        hour=SCHEDULE_PAGI_HOUR,
        minute=SCHEDULE_PAGI_MINUTE,
        timezone=SCHEDULE_TIMEZONE,
    )
    scheduler.add_job(
        run_session_pipeline_safe,
        args=["BELI_PAGI"],
        trigger=trigger_pagi,
        id="session_pagi",
        name="TradSense Sesi Pagi",
        misfire_grace_time=300,
    )

    # 2. Jadwal Sesi Sore (BELI_SORE) — Senin–Jumat 15:30 WIB
    trigger_sore = CronTrigger(
        day_of_week="mon-fri",
        hour=SCHEDULE_SORE_HOUR,
        minute=SCHEDULE_SORE_MINUTE,
        timezone=SCHEDULE_TIMEZONE,
    )
    scheduler.add_job(
        run_session_pipeline_safe,
        args=["BELI_SORE"],
        trigger=trigger_sore,
        id="session_sore",
        name="TradSense Sesi Sore",
        misfire_grace_time=300,
    )

    scheduler.start()
    logger.info("✓ Background Scheduler aktif.")
    now = datetime.now()
    logger.info(f"Jadwal Berikutnya (Pagi): {trigger_pagi.get_next_fire_time(None, now)}")
    logger.info(f"Jadwal Berikutnya (Sore): {trigger_sore.get_next_fire_time(None, now)}")
    return scheduler


# ──────────────────────────────────────────────────────────────
# Telegram Bot (async) — harus jalan di main thread asyncio loop
# ──────────────────────────────────────────────────────────────

async def run_bot_async() -> None:
    """Menjalankan Telegram Bot Listener secara async.

    Menggunakan python-telegram-bot v21+ API yang sepenuhnya async.
    Harus dipanggil dari asyncio.run() di main thread.
    """
    from telegram.ext import ApplicationBuilder, CommandHandler
    from bot.listener import (
        start_command,
        stop_command,
        help_command,
        rekomendasi_command,
    )

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN belum diset — Telegram Bot tidak dijalankan.")
        # Biarkan jalan tanpa bot (HTTP server tetap aktif via thread)
        # Tunggu selamanya agar proses tidak exit
        await asyncio.Event().wait()
        return

    logger.info("Memulai Telegram Bot Listener (async)...")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rekomendasi", rekomendasi_command))

    logger.info("🤖 Bot Listener aktif — menunggu perintah Telegram...")

    # Jalankan polling tanpa stop_signals agar tidak konflik
    # dengan signal handler di main thread (Render menggunakan SIGTERM)
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Tunggu selamanya sampai proses dihentikan
        await asyncio.Event().wait()

        await app.updater.stop()
        await app.stop()


# ──────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point untuk Render deployment."""
    init_db()

    # 1. HTTP Health Check — di thread daemon terpisah
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    # 2. APScheduler — background thread, tidak butuh asyncio
    scheduler = start_scheduler()

    logger.info("🚀 TradSense Server siap. Bot Listener dimulai di main thread...")

    try:
        # 3. Telegram Bot — di main thread via asyncio.run()
        #    python-telegram-bot v21+ membutuhkan asyncio di main thread
        asyncio.run(run_bot_async())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Mematikan server...")
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Server dihentikan.")


if __name__ == "__main__":
    main()
