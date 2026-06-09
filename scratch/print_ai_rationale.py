"""
TradSense - Print AI Analysis Rationale
=======================================
Membaca dan menampilkan analisis AI Gemini untuk masing-masing saham hari ini.
"""

import os
import sys
from datetime import datetime

# Setup paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 console output
if sys.platform.startswith("win"):
    import io
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from database.models import AIAnalysis, get_session

def main():
    session = get_session()
    try:
        latest = session.query(AIAnalysis).order_by(AIAnalysis.date.desc()).first()
        if not latest:
            print("Belum ada data analisis di database.")
            return

        latest_date = latest.date.date()
        print(f"=== ANALISIS AI GEMINI TANGGAL: {latest_date} ===")
        
        analyses = session.query(AIAnalysis).filter(
            AIAnalysis.date >= datetime.combine(latest_date, datetime.min.time()),
            AIAnalysis.date <= datetime.combine(latest_date, datetime.max.time()),
        ).all()

        for a in analyses:
            print("-" * 60)
            print(f"TICKER      : {a.ticker}")
            print(f"REKOMENDASI : {a.strategy} (Confidence: {a.confidence}%)")
            print(f"OPPORTUNITY : {a.opportunity_summary}")
            print(f"RISK        : {a.risk_summary}")
            print(f"ANALISIS    : {a.analysis_text[:200]}...")
            print(f"SENTIMEN    : Positif={a.sentiment_positive}, Netral={a.sentiment_neutral}, Negatif={a.sentiment_negative}")
        print("-" * 60)
    finally:
        session.close()

if __name__ == "__main__":
    main()
