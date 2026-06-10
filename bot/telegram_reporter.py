"""
TradSense - Telegram Reporter
===============================
Mengirim laporan analisis saham ke Telegram.
"""

import asyncio
import html
import re
from datetime import datetime
from typing import Any

import requests as http_requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TOP_N
from utils.logger import get_logger

logger = get_logger("bot.telegram")

# Mapping strategi ke emoji dan label
STRATEGY_MAP = {
    "BELI_SORE_JUAL_PAGI": ("🌅", "BELI SORE → JUAL PAGI"),
    "BELI_PAGI_JUAL_SORE": ("☀️", "BELI PAGI → JUAL SORE"),
    "TIDAK_DIREKOMENDASIKAN": ("⛔", "TIDAK DIREKOMENDASIKAN"),
}


def _escape_html(text: str) -> str:
    """Escape karakter HTML spesial untuk parse_mode=HTML."""
    if not text:
        return ""
    return html.escape(str(text))


def _send_telegram_http(token: str, chat_id: str, text: str) -> bool:
    """Kirim pesan Telegram via requests langsung (sync, tidak butuh asyncio).

    Lebih reliabel dari background thread karena tidak bergantung pada
    asyncio event loop yang hanya tersedia di main thread.

    Args:
        token: Telegram bot token.
        chat_id: Target chat ID.
        text: Teks pesan (HTML format).

    Returns:
        True jika berhasil.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Kirim dalam chunks jika terlalu panjang
    chunks = _split_message(text, 4000)
    success = True
    for chunk in chunks:
        try:
            resp = http_requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                },
                timeout=30,
            )
            if not resp.ok:
                # Fallback: coba kirim tanpa parse_mode jika HTML error
                resp2 = http_requests.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": re.sub(r"<[^>]+>", "", chunk),  # strip HTML tags
                    },
                    timeout=30,
                )
                if not resp2.ok:
                    logger.error(f"Telegram send gagal: {resp2.text[:200]}")
                    success = False
        except Exception as e:
            logger.error(f"Telegram HTTP error: {e}")
            success = False
    return success


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split pesan panjang menjadi beberapa bagian."""
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


class TelegramReporter:
    """Mengirim laporan analisis ke Telegram."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID

    def _format_single_stock(
        self, rank: int, analysis: dict[str, Any]
    ) -> str:
        ticker = _escape_html(analysis["ticker"])
        strategy = analysis.get("strategy", "TIDAK_DIREKOMENDASIKAN")
        confidence = analysis.get("confidence", 0)
        score = analysis.get("score", 0)
        features = analysis.get("features", {})

        emoji, label = STRATEGY_MAP.get(
            strategy, ("❓", strategy)
        )
        label_safe = _escape_html(label)

        # Rangkuman Analisis dari AI — escape HTML
        analysis_text = _escape_html(analysis.get("analysis_text", ""))
        opportunity_text = _escape_html(analysis.get("opportunity_summary", ""))
        risk_text = _escape_html(analysis.get("risk_summary", ""))

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

        # Format Risiko
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

<b>#{rank} {ticker}</b> {emoji}

📊 <b>Score:</b> {score:.0f}/100
💰 <b>Harga:</b> Rp {price:,.0f}

🎯 <b>Strategi:</b>
{label_safe} (Confidence: {confidence}%)

📈 <b>RSI:</b> {rsi:.0f} | <b>ATR:</b> {atr_pct:.1f}%
📰 <b>Sentimen Berita:</b>
{sentiment_display}

✅ <b>Potensi / Katalis:</b>
{opp_display}

⚠️ <b>Risiko / Peringatan:</b>
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
            title = "🌅 <b>REKOMENDASI BELI SORE (JUAL PAGI)</b>"
            subtitle = "<i>Analisis otomatis menjelang market close</i>"
        elif strategy_filter == "BELI_PAGI":
            filtered = [
                a for a in recommended
                if a.get("strategy") == "BELI_PAGI_JUAL_SORE"
            ]
            title = "☀️ <b>REKOMENDASI BELI PAGI (JUAL SORE)</b>"
            subtitle = "<i>Analisis otomatis menjelang market open</i>"
        else:
            filtered = recommended
            title = "📈 <b>TOP REKOMENDASI HARI INI</b>"
            subtitle = "<i>Analisis otomatis sistem AI TradSense</i>"

        top = filtered[:TELEGRAM_TOP_N]
        is_fallback_view = False

        if not top:
            top = [a for a in analyses if a.get("ticker") is not None][:TELEGRAM_TOP_N]
            is_fallback_view = True

        if is_fallback_view:
            header = f"""
⚠️ <b>ALERT: HIGH RISK MARKET</b>
{title}
🗓 {now}
{'━' * 32}

<b>Tidak ada saham yang memenuhi kriteria rekomendasi aman saat ini.</b>
Berikut adalah analisis 5 kandidat teratas sebagai referensi pantauan Anda (Watchlist):
"""
        else:
            header = f"""
{title}
🗓 {now}
{'━' * 32}

<i>Sistem AI TradSense</i>
{subtitle}
"""

        body_parts = []
        for i, analysis in enumerate(top, 1):
            body_parts.append(
                self._format_single_stock(i, analysis)
            )

        footer = f"""
{'━' * 32}

⚠️ <b>DISCLAIMER:</b>
<i>Rekomendasi ini dibuat oleh AI dan bukan merupakan ajakan untuk membeli/menjual saham. Investasi saham mengandung risiko. Lakukan riset mandiri sebelum mengambil keputusan.</i>

🤖 <i>Powered by TradSense AI</i>
"""

        full_report = header.strip() + "\n"
        for part in body_parts:
            full_report += "\n" + part + "\n"
        full_report += "\n" + footer.strip()

        return full_report

    def send_report(
        self, analyses: list[dict[str, Any]], strategy_filter: str | None = None
    ) -> bool:
        """Kirim laporan ke semua subscriber via HTTP langsung (sync, thread-safe)."""
        report = self.format_report(analyses, strategy_filter=strategy_filter)
        logger.info(f"Mengirim laporan ({len(report)} chars)...")

        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN tidak tersedia")
            return False

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
            ok = _send_telegram_http(self.token, cid, report)
            if ok:
                logger.info(f"✓ Laporan terkirim ke chat_id: {cid}")
            else:
                logger.error(f"Gagal mengirim ke chat_id: {cid}")
                success = False

        return success

    def send_error_alert(self, error_msg: str) -> bool:
        """Kirim error alert ke admin (sync, thread-safe)."""
        if not self.token or not self.chat_id:
            return False
        text = (
            f"🚨 <b>TradSense Error Alert</b>\n\n"
            f"Terjadi error saat menjalankan pipeline:\n\n"
            f"<code>{_escape_html(error_msg[:500])}</code>\n\n"
            f"<i>Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}</i>"
        )
        return _send_telegram_http(self.token, self.chat_id, text)

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        """Split pesan panjang menjadi beberapa bagian."""
        return _split_message(text, max_len)
