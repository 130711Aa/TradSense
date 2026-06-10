"""
TradSense - Telegram Listener
=============================
Listener interaktif untuk menerima perintah Telegram (/start, /stop, /rekomendasi).
Menjalankan polling server agar bot bisa diakses oleh banyak pengguna secara langsung.
"""

import logging
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Flag untuk mencegah pipeline berjalan ganda
_pipeline_running = False

from config import TELEGRAM_BOT_TOKEN
from database.models import AIAnalysis, StockFeature, Subscriber, get_session
from bot.telegram_reporter import TelegramReporter, STRATEGY_MAP

# Logger
logger = logging.getLogger("tradsense.bot.listener")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /start untuk pendaftaran subscriber baru."""
    user = update.effective_user
    chat_id = str(update.effective_chat.id)

    if not user:
        return

    session = get_session()
    try:
        # Cari subscriber lama
        sub = session.query(Subscriber).filter(Subscriber.chat_id == chat_id).first()
        if sub:
            if not sub.is_active:
                sub.is_active = True
                sub.username = user.username
                sub.first_name = user.first_name
                session.commit()
                msg = (
                    f"Selamat datang kembali, *{user.first_name}*! 📈\n\n"
                    "Anda telah mengaktifkan kembali langganan rekomendasi harian TradSense.\n"
                    "Rekomendasi harian akan dikirim ke chat ini sebelum market buka (08:30 WIB) dan sebelum market tutup (15:30 WIB).\n\n"
                    "Gunakan perintah /rekomendasi untuk melihat analisis terbaru saat ini."
                )
            else:
                msg = (
                    f"Halo *{user.first_name}*, Anda sudah terdaftar sebagai subscriber aktif! 🤖\n\n"
                    "Ketik /rekomendasi untuk mendapatkan rekomendasi saham terbaru harian."
                )
        else:
            # Buat subscriber baru
            new_sub = Subscriber(
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                is_active=True,
            )
            session.add(new_sub)
            session.commit()
            msg = (
                f"Halo *{user.first_name}*, selamat bergabung di *TradSense Bot*! 🤖📈\n\n"
                "Anda akan menerima rekomendasi saham harian dari Indonesian Stock Exchange (BEI) secara otomatis:\n"
                "🌅 *Sesi Sore (15:30 WIB)*: Rekomendasi BELI SORE -> JUAL PAGI\n"
                "☀️ *Sesi Pagi (08:30 WIB)*: Rekomendasi BELI PAGI -> JUAL SORE\n\n"
                "Gunakan perintah berikut:\n"
                "• /rekomendasi — Lihat rekomendasi terupdate hari ini\n"
                "• /help — Petunjuk penggunaan dan daftar perintah\n"
                "• /stop — Berhenti berlangganan"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("Terjadi kesalahan teknis saat memproses perintah /start.")
    finally:
        session.close()


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /stop untuk berhenti berlangganan."""
    chat_id = str(update.effective_chat.id)

    session = get_session()
    try:
        sub = session.query(Subscriber).filter(Subscriber.chat_id == chat_id).first()
        if sub and sub.is_active:
            sub.is_active = False
            session.commit()
            msg = "Anda telah berhasil berhenti berlangganan rekomendasi harian TradSense. Ketik /start kapan saja untuk bergabung kembali."
        else:
            msg = "Anda belum terdaftar atau sudah tidak aktif."
        await update.message.reply_text(msg)
    except Exception as e:
        session.rollback()
        logger.error(f"Error in stop_command: {e}")
        await update.message.reply_text("Terjadi kesalahan saat menonaktifkan langganan Anda.")
    finally:
        session.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan panduan penggunaan bot."""
    msg = (
        "🤖 *TradSense Bot Helper*\n"
        "Sistem Analisis Saham BEI Berbasis AI (Google Gemini)\n\n"
        "📢 *Perintah yang Tersedia:*\n"
        "• /start — Daftar langganan rekomendasi harian otomatis\n"
        "• /rekomendasi — Lihat rekomendasi terupdate dari database\n"
        "• /jalankan — ⚡ Trigger pipeline sekarang (ambil data & analisis baru)\n"
        "• /help — Tampilkan menu panduan ini\n"
        "• /stop — Berhenti mendapatkan broadcast rekomendasi harian\n\n"
        "⚠️ *Disclaimer:* Semua output bot ini adalah analisis teknikal & berita berbasis AI dan bukan ajakan finansial mengikat. Selalu lakukan riset mandiri."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def rekomendasi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim rekomendasi terupdate yang ada di database."""
    await update.message.reply_text("Memuat rekomendasi saham terupdate dari database, harap tunggu... 📊")

    session = get_session()
    try:
        # Cari tanggal rilis analisis terbaru di DB
        latest_analysis = session.query(AIAnalysis).order_by(AIAnalysis.date.desc()).first()
        if not latest_analysis:
            await update.message.reply_text("Belum ada data analisis di database saat ini.")
            return

        latest_date = latest_analysis.date.date()

        # Ambil seluruh analisis untuk tanggal tersebut
        analyses_db = session.query(AIAnalysis).filter(
            AIAnalysis.date >= datetime.combine(latest_date, datetime.min.time()),
            AIAnalysis.date <= datetime.combine(latest_date, datetime.max.time()),
        ).all()

        if not analyses_db:
            await update.message.reply_text("Tidak ditemukan analisis aktif untuk hari ini.")
            return

        # Dapatkan juga features pendukung dari StockFeature & StockPrice & StockScore untuk format_report
        analyses_list = []
        from database.models import StockPrice, StockScore
        for a in analyses_db:
            feat = session.query(StockFeature).filter(
                StockFeature.ticker == a.ticker,
                StockFeature.date >= datetime.combine(latest_date, datetime.min.time()),
                StockFeature.date <= datetime.combine(latest_date, datetime.max.time()),
            ).order_by(StockFeature.id.desc()).first()

            price_rec = session.query(StockPrice).filter(
                StockPrice.ticker == a.ticker,
                StockPrice.date >= datetime.combine(latest_date, datetime.min.time()),
                StockPrice.date <= datetime.combine(latest_date, datetime.max.time()),
            ).order_by(StockPrice.id.desc()).first()

            score_rec = session.query(StockScore).filter(
                StockScore.ticker == a.ticker,
                StockScore.date >= datetime.combine(latest_date, datetime.min.time()),
                StockScore.date <= datetime.combine(latest_date, datetime.max.time()),
            ).order_by(StockScore.id.desc()).first()

            price_val = price_rec.close if price_rec else 0.0
            score_val = score_rec.total_score if score_rec else 80.0

            features_dict = {}
            if feat:
                features_dict = {
                    "price": price_val,
                    "volume_ratio": feat.volume_ratio,
                    "close_strength": feat.close_strength,
                    "breakout_20d": feat.breakout_20d,
                    "rsi14": feat.rsi14,
                    "atr_ratio": feat.atr_ratio,
                }

            analyses_list.append({
                "ticker": a.ticker,
                "strategy": a.strategy,
                "confidence": int(a.confidence or 0),
                "analysis_text": a.analysis_text,
                "risk_summary": a.risk_summary,
                "opportunity_summary": a.opportunity_summary,
                "news_summary": a.news_summary,
                "sentiment": {
                    "positif": a.sentiment_positive or 0,
                    "netral": a.sentiment_neutral or 0,
                    "negatif": a.sentiment_negative or 0,
                },
                "features": features_dict,
                "score": score_val,
            })

        # Kirim hasil menggunakan TelegramReporter
        reporter = TelegramReporter()
        report = reporter.format_report(analyses_list)

        # Telegram max length handling — gunakan HTML parse_mode (lebih aman dari Markdown)
        if len(report) <= 4096:
            await update.message.reply_text(report, parse_mode="HTML")
        else:
            from bot.telegram_reporter import _split_message
            parts = _split_message(report, 4000)
            for part in parts:
                await update.message.reply_text(part, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in rekomendasi_command: {e}")
        try:
            await update.message.reply_text(f"Gagal memuat rekomendasi: {str(e)[:200]}")
        except Exception:
            pass
    finally:
        session.close()


async def jalankan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger pipeline secara manual via Telegram.

    Menjalankan full pipeline (fetch data → filter → scoring → AI → report)
    di background thread agar bot tetap responsif.
    """
    global _pipeline_running

    if _pipeline_running:
        await update.message.reply_text(
            "⏳ Pipeline sedang berjalan, harap tunggu hingga selesai sebelum menjalankan lagi."
        )
        return

    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "🚀 *Pipeline dimulai!*\n\n"
        "Proses pengambilan data saham BEI sedang berjalan di background.\n"
        "Estimasi waktu: 5–15 menit tergantung jumlah saham.\n\n"
        "Laporan rekomendasi akan dikirim ke sini secara otomatis setelah selesai.",
        parse_mode="Markdown",
    )

    # Ambil bot object untuk mengirim pesan dari thread background
    bot = context.bot

    def _run_pipeline_thread() -> None:
        """Jalankan pipeline di thread terpisah."""
        global _pipeline_running
        _pipeline_running = True

        from pipeline import TradSensePipeline
        from bot.telegram_reporter import _send_telegram_http
        from config import TELEGRAM_BOT_TOKEN

        try:
            pipeline = TradSensePipeline()
            results = pipeline.run(skip_fetch=False)
            msg = (
                f"✅ <b>Pipeline selesai!</b> <b>{len(results)} saham</b> berhasil dianalisis.\n"
                "Gunakan /rekomendasi untuk melihat hasilnya."
            )
        except Exception as e:
            logger.error(f"Pipeline manual gagal: {e}")
            msg = f"❌ Pipeline gagal:\n<code>{str(e)[:300]}</code>"
        finally:
            _pipeline_running = False

        # Kirim notifikasi via HTTP langsung — tidak butuh asyncio event loop
        try:
            _send_telegram_http(TELEGRAM_BOT_TOKEN, str(chat_id), msg)
        except Exception as send_err:
            logger.error(f"Gagal kirim notifikasi selesai: {send_err}")

    thread = threading.Thread(target=_run_pipeline_thread, daemon=True)
    thread.start()


def run_listener() -> None:
    """Memulai polling listener server."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN belum diset di file .env")
        return

    logger.info("Memulai Telegram Bot Listener...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Registrasi handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rekomendasi", rekomendasi_command))
    app.add_handler(CommandHandler("jalankan", jalankan_command))

    logger.info("Bot Listener berjalan dalam mode polling. Tekan Ctrl+C untuk berhenti.")
    app.run_polling()


if __name__ == "__main__":
    from utils.logger import setup_logging
    setup_logging()
    run_listener()
