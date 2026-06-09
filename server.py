"""
TradSense - Render Deploy Server
================================
Server HTTP gabungan untuk deploy ke Render (Free Web Service).
Menjalankan Web Health Check (agar Render tetap aktif), 
Telegram Bot Listener, dan Scheduler Harian dalam satu proses.
"""

import os
import sys
import threading
import http.server
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
from bot.listener import run_listener
from scheduler import run_session_pipeline
from utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger("render_server")

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
                    <p>Status Bot   : <span style="color: #4ade80;">Active & Listening</span></p>
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

def start_scheduler():
    """Menjalankan Background Scheduler."""
    logger.info("Memulai Background Scheduler...")
    scheduler = BackgroundScheduler()

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

    scheduler.start()
    logger.info("✓ Background Scheduler aktif.")
    now = datetime.now()
    logger.info(f"Jadwal Berikutnya (Pagi): {trigger_pagi.get_next_fire_time(None, now)}")
    logger.info(f"Jadwal Berikutnya (Sore): {trigger_sore.get_next_fire_time(None, now)}")

def start_bot_listener():
    """Menjalankan Telegram Bot Listener."""
    logger.info("Memulai Telegram Bot Listener...")
    try:
        run_listener()
    except Exception as e:
        logger.error(f"Gagal memulai Telegram Bot Listener: {e}")

def main():
    """Main entry point."""
    init_db()

    # 1. Start Scheduler di Background
    start_scheduler()

    # 2. Start Bot Listener di Thread terpisah
    listener_thread = threading.Thread(target=start_bot_listener, daemon=True)
    listener_thread.start()

    # 3. Start Web Server di Main Thread untuk health check Render
    port = int(os.environ.get("PORT", 8000))
    server_address = ("", port)
    httpd = http.server.HTTPServer(server_address, HealthCheckHandler)
    
    logger.info(f"🚀 Web Server Health Check berjalan di port {port}...")
    logger.info("Aplikasi TradSense siap di-deploy secara gratis di Render!")
    
    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Mematikan server...")
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    main()
