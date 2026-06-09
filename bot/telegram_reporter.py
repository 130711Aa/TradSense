"""
TradSense - Telegram Reporter
===============================
Mengirim laporan analisis saham ke Telegram.
"""

import asyncio
from datetime import datetime
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TOP_N
from utils.logger import get_logger

logger = get_logger("bot.telegram")

# Mapping strategi ke emoji dan label
STRATEGY_MAP = {
    "BELI_SORE_JUAL_PAGI": ("🌅", "BELI SORE → JUAL PAGI"),
    "BELI_PAGI_JUAL_SORE": ("☀️", "BELI PAGI → JUAL SORE"),
    "TIDAK_DIREKOMENDASIKAN": ("⛔", "TIDAK DIREKOMENDASIKAN"),
}


class TelegramReporter:
    """Mengirim laporan analisis ke Telegram."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.bot = Bot(token=self.token) if self.token else None

    def _format_single_stock(
        self, rank: int, analysis: dict[str, Any]
    ) -> str:
        ticker = analysis["ticker"]
        strategy = analysis.get("strategy", "TIDAK_DIREKOMENDASIKAN")
        confidence = analysis.get("confidence", 0)
        score = analysis.get("score", 0)
        features = analysis.get("features", {})

        emoji, label = STRATEGY_MAP.get(
            strategy, ("❓", strategy)
        )

        # Rangkuman Analisis dari AI
        analysis_text = analysis.get("analysis_text", "")
        opportunity_text = analysis.get("opportunity_summary", "")
        risk_text = analysis.get("risk_summary", "")

        # Format Opportunity / Alasan Positif
        opp_lines = []
        if opportunity_text:
            for line in opportunity_text.split("\n"):
                if line.strip():
                    clean_line = line.strip().lstrip("*-• ").strip()
                    opp_lines.append(f"• {clean_line}")
        if not opp_lines and analysis_text:
            opp_lines.append(f"• {analysis_text[:120]}...")
        opp_display = "\n".join(opp_lines[:3]) if opp_lines else "• Sinyal teknikal standar"

        # Format Risiko / Alasan Penolakan
        risk_lines = []
        if risk_text:
            for line in risk_text.split("\n"):
                if line.strip():
                    clean_line = line.strip().lstrip("*-• ").strip()
                    risk_lines.append(f"• {clean_line}")
        risk_display = "\n".join(risk_lines[:3]) if risk_lines else "• Risiko volatilitas pasar"

        # Sentimen Berita
        sentiment = analysis.get("sentiment", {})
        pos = sentiment.get("positif", 0)
        net = sentiment.get("netral", 0)
        neg = sentiment.get("negatif", 0)
        sentiment_display = f"🟢 Positif: {pos} | ⚪ Netral: {net} | 🔴 Negatif: {neg}"

        price = features.get("price", 0)
        rsi = features.get("rsi14", 50)
        atr_ratio = features.get("atr_ratio")
        atr_pct = (atr_ratio * 100) if atr_ratio is not None else 0.0

        msg = f"""
{'━' * 32}

*#{rank} {ticker}* {emoji}

📊 *Score:* {score:.0f}/100
💰 *Harga:* Rp {price:,.0f}

🎯 *Strategi:*
{label} (Confidence: {confidence}%)

📈 *RSI:* {rsi:.0f} | *ATR:* {atr_pct:.1f}%
📰 *Sentimen Berita:*
{sentiment_display}

✅ *Potensi / Katalis:*
{opp_display}

⚠️ *Risiko / Peringatan:*
{risk_display}
"""
        return msg.strip()

    def format_report(
        self, analyses: list[dict[str, Any]], strategy_filter: str | None = None
    ) -> str:
        now = datetime.now().strftime("%d %B %Y, %H:%M WIB")

        # Filter rekomendasi aktif
        recommended = [
            a for a in analyses
            if a.get("strategy") not in ("TIDAK_DIREKOMENDASIKAN", None)
        ]

        if strategy_filter == "BELI_SORE":
            filtered = [
                a for a in recommended
                if a.get("strategy") == "BELI_SORE_JUAL_PAGI"
            ]
            title = "🌅 *REKOMENDASI BELI SORE (JUAL PAGI)*"
            subtitle = "_Analisis otomatis menjelang market close_"
        elif strategy_filter == "BELI_PAGI":
            filtered = [
                a for a in recommended
                if a.get("strategy") == "BELI_PAGI_JUAL_SORE"
            ]
            title = "☀️ *REKOMENDASI BELI PAGI (JUAL SORE)*"
            subtitle = "_Analisis otomatis menjelang market open_"
        else:
            filtered = recommended
            title = "📈 *TOP REKOMENDASI HARI INI*"
            subtitle = "_Analisis otomatis sistem AI TradSense_"

        top = filtered[:TELEGRAM_TOP_N]
        is_fallback_view = False

        if not top:
            # Jika tidak ada rekomendasi beli aktif, tampilkan 5 kandidat teratas yang dianalisis sebagai referensi watchlist
            top = [a for a in analyses if a.get("ticker") is not None][:TELEGRAM_TOP_N]
            is_fallback_view = True

        if is_fallback_view:
            header = f"""
⚠️ *ALERT: HIGH RISK MARKET*
{title}
🗓 {now}
{'━' * 32}

*Tidak ada saham yang memenuhi kriteria rekomendasi aman saat ini.*
Berikut adalah analisis 5 kandidat teratas sebagai referensi pantauan Anda (Watchlist):
"""
        else:
            header = f"""
{title}
🗓 {now}
{'━' * 32}

_Sistem AI TradSense_
{subtitle}
"""

        body_parts = []
        for i, analysis in enumerate(top, 1):
            body_parts.append(
                self._format_single_stock(i, analysis)
            )

        footer = f"""
{'━' * 32}

⚠️ *DISCLAIMER:*
_Rekomendasi ini dibuat oleh AI dan bukan merupakan ajakan untuk membeli/menjual saham. Investasi saham mengandung risiko. Lakukan riset mandiri sebelum mengambil keputusan._

🤖 _Powered by TradSense AI_
"""

        full_report = header.strip() + "\n"
        for part in body_parts:
            full_report += "\n" + part + "\n"
        full_report += "\n" + footer.strip()

        return full_report

    async def _send_message(self, chat_id: str, text: str) -> bool:
        if not self.bot or not chat_id:
            logger.error("Telegram bot atau chat_id belum dikonfigurasi")
            return False

        try:
            # Telegram max message = 4096 chars
            if len(text) <= 4096:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                # Split menjadi beberapa pesan
                parts = self._split_message(text, 4000)
                for part in parts:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=part,
                        parse_mode=ParseMode.MARKDOWN,
                    )
            logger.info(f"✓ Laporan terkirim ke chat_id: {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Telegram send error untuk chat_id {chat_id}: {e}")
            return False

    def send_report(
        self, analyses: list[dict[str, Any]], strategy_filter: str | None = None
    ) -> bool:
        report = self.format_report(analyses, strategy_filter=strategy_filter)
        logger.info(f"Mengirim laporan ({len(report)} chars)...")

        # Ambil semua subscriber aktif dari database
        from database.models import Subscriber, get_session
        session = get_session()
        chat_ids = []
        try:
            subscribers = session.query(Subscriber).filter(Subscriber.is_active == True).all()
            chat_ids = [sub.chat_id for sub in subscribers]
        except Exception as e:
            logger.error(f"Gagal memuat subscriber dari DB: {e}")
        finally:
            session.close()

        # Fallback ke chat_id config jika database kosong
        if not chat_ids and self.chat_id:
            logger.info("Database subscriber kosong. Menggunakan fallback chat_id dari config.")
            chat_ids = [self.chat_id]

        if not chat_ids:
            logger.warning("Tidak ada target chat_id untuk mengirim laporan.")
            return False

        success = True
        for cid in chat_ids:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run, self._send_message(cid, report)
                        )
                        res = future.result(timeout=30)
                else:
                    res = asyncio.run(self._send_message(cid, report))
                if not res:
                    success = False
            except Exception as e:
                logger.error(f"Gagal mengirim ke chat_id {cid}: {e}")
                success = False
        return success

    def send_error_alert(self, error_msg: str) -> bool:
        text = (
            f"🚨 *TradSense Error Alert*\n\n"
            f"Terjadi error saat menjalankan pipeline:\n\n"
            f"`{error_msg[:500]}`\n\n"
            f"_Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}_"
        )
        try:
            return asyncio.run(self._send_message(self.chat_id, text))
        except Exception as e:
            logger.error(f"Failed to send error alert: {e}")
            return False

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        parts = []
        lines = text.split("\n")
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > max_len:
                parts.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            parts.append(current)
        return parts
