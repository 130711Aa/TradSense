"""
TradSense - Test Report Formatting
==================================
Memuat hasil analisis terakhir dari DB dan menampilkan format laporan Telegram baru.
"""

import os
import sys

# Setup paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 console output
if sys.platform.startswith("win"):
    import io
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from database.models import AIAnalysis, get_session
from bot.telegram_reporter import TelegramReporter

def main():
    session = get_session()
    try:
        latest = session.query(AIAnalysis).order_by(AIAnalysis.date.desc()).first()
        if not latest:
            print("Belum ada data analisis untuk diformat.")
            return
            
        print(f"Memuat analisis untuk tanggal: {latest.date}")
        analyses = session.query(AIAnalysis).filter(
            AIAnalysis.date == latest.date
        ).all()
        
        # Konversi SQLAlchemy model ke dict yang diharapkan reporter
        analyses_dict = []
        for a in analyses:
            analyses_dict.append({
                "ticker": a.ticker,
                "strategy": a.strategy,
                "confidence": a.confidence,
                "score": a.score,
                "analysis_text": a.analysis_text,
                "opportunity_summary": a.opportunity_summary,
                "risk_summary": a.risk_summary,
                "sentiment": {
                    "positif": a.sentiment_positive,
                    "netral": a.sentiment_neutral,
                    "negatif": a.sentiment_negative
                },
                "features": {
                    "price": a.price,
                    "rsi14": a.rsi14,
                    "atr_ratio": a.atr_ratio,
                    "volume_ratio": a.volume_ratio,
                    "breakout_20d": a.breakout_20d,
                    "close_strength": a.close_strength,
                    "trend": a.trend
                }
            })
            
        reporter = TelegramReporter()
        report = reporter.format_report(analyses_dict)
        
        print("\n=== LAPORAN FORMAT TELEGRAM TERBARU ===")
        print(report)
        print("========================================\n")
        
    finally:
        session.close()

if __name__ == "__main__":
    main()
