"""
TradSense - AI Prompt Builder
===============================
Membangun prompt untuk LLM berdasarkan data teknikal dan berita.
"""

from typing import Any


def build_analysis_prompt(stock_data: dict[str, Any]) -> str:
    """Membangun prompt analisis AI untuk satu saham.

    Args:
        stock_data: Dictionary berisi data teknikal dan berita saham.

    Returns:
        Prompt string untuk LLM.
    """
    ticker = stock_data["ticker"]
    score = stock_data.get("total_score", 0)
    features = stock_data.get("features", {})
    news = stock_data.get("news", [])

    # Format berita
    news_text = ""
    if news:
        news_items = []
        for i, n in enumerate(news[:10], 1):
            news_items.append(
                f"  {i}. [{n.get('source', 'unknown')}] {n.get('title', 'N/A')}\n"
                f"     Ringkasan: {n.get('summary', 'N/A')[:200]}"
            )
        news_text = "\n".join(news_items)
    else:
        news_text = "  Tidak ada berita terbaru."

    prompt = f"""Kamu adalah analis saham profesional Indonesia yang berpengalaman.
Analisis data saham berikut dan berikan rekomendasi trading jangka pendek.

═══════════════════════════════════════
DATA SAHAM: {ticker}
═══════════════════════════════════════

SCORING:
  Total Score: {score}/100

HARGA & VOLUME:
  Close: Rp {features.get('price', 0):,.0f}
  Volume Ratio: {features.get('volume_ratio', 1):.1f}x rata-rata 20 hari
  Avg Value 20D: Rp {features.get('avg_value_20d', 0):,.0f}

TEKNIKAL:
  EMA20: {features.get('ema20', 0):,.0f}
  EMA50: {features.get('ema50', 0):,.0f}
  EMA200: {features.get('ema200', 0):,.0f}
  RSI(14): {features.get('rsi14', 50):.1f}
  ATR(14): {features.get('atr14', 0):,.0f}
  ATR/Close: {features.get('atr_ratio', 0)*100:.1f}%
  Close Strength: {features.get('close_strength', 0.5):.2f}
  Breakout 20 Hari: {"YA" if features.get("breakout_20d") else "TIDAK"}
  Trend EMA: {features.get('trend', 'sideways').upper()}

RETURN:
  Harian: {features.get('return_1d', 0)*100:.2f}%
  5 Hari: {features.get('return_5d', 0)*100:.2f}%
  20 Hari: {features.get('return_20d', 0)*100:.2f}%

BERITA TERBARU:
{news_text}

═══════════════════════════════════════
INSTRUKSI:
═══════════════════════════════════════

Berikan analisis dalam format JSON berikut:

{{
  "ticker": "{ticker}",
  "analisis_teknikal": "...(penjelasan singkat kondisi teknikal)...",
  "analisis_berita": "...(rangkuman sentimen berita dan dampaknya)...",
  "risiko": ["risiko 1", "risiko 2", "risiko 3"],
  "peluang": ["peluang 1", "peluang 2", "peluang 3"],
  "strategi": "BELI_SORE_JUAL_PAGI" atau "BELI_PAGI_JUAL_SORE" atau "TIDAK_DIREKOMENDASIKAN",
  "alasan_strategi": "...(mengapa memilih strategi ini)...",
  "confidence": 0-100,
  "sentimen": {{
    "positif": <jumlah berita positif>,
    "netral": <jumlah berita netral>,
    "negatif": <jumlah berita negatif>
  }}
}}

ATURAN:
1. Pilih BELI_SORE_JUAL_PAGI jika ada indikasi gap up pagi (sentimen positif, akumulasi sore).
2. Pilih BELI_PAGI_JUAL_SORE jika ada momentum intraday kuat (volume spike, breakout).
3. Pilih TIDAK_DIREKOMENDASIKAN jika risiko terlalu tinggi atau sinyal tidak jelas.
4. Confidence harus realistis. Jangan memberikan confidence > 90 kecuali sinyal sangat kuat.
5. JANGAN menjanjikan keuntungan. Selalu ingatkan bahwa investasi saham mengandung risiko.
6. Jawab HANYA dalam format JSON di atas, tanpa teks tambahan.
"""
    return prompt


def build_batch_analysis_prompt(stocks_data: list[dict[str, Any]]) -> str:
    """Membangun prompt analisis AI massal untuk beberapa saham sekaligus.

    Args:
        stocks_data: List of dictionary berisi data teknikal dan berita saham.

    Returns:
        Prompt string untuk LLM.
    """
    stocks_sections = []
    for s in stocks_data:
        ticker = s["ticker"]
        score = s.get("total_score", 0)
        features = s.get("features", {})
        news = s.get("news", [])

        # Format berita
        news_text = ""
        if news:
            news_items = []
            for i, n in enumerate(news[:5], 1):  # Batasi berita per ticker agar tidak melebihi token limit
                news_items.append(
                    f"  - [{n.get('source', 'unknown')}] {n.get('title', 'N/A')}\n"
                    f"    Ringkasan: {n.get('summary', 'N/A')[:150]}"
                )
            news_text = "\n".join(news_items)
        else:
            news_text = "  Tidak ada berita terbaru."

        stock_section = f"""=== SAHAM: {ticker} ===
SCORING:
  Total Score: {score}/100

HARGA & VOLUME:
  Close: Rp {features.get('price', 0):,.0f}
  Volume Ratio: {features.get('volume_ratio', 1):.1f}x rata-rata 20 hari
  Avg Value 20D: Rp {features.get('avg_value_20d', 0):,.0f}

TEKNIKAL:
  EMA20: {features.get('ema20', 0):,.0f} | EMA50: {features.get('ema50', 0):,.0f} | EMA200: {features.get('ema200', 0):,.0f}
  RSI(14): {features.get('rsi14', 50):.1f} | ATR/Close: {features.get('atr_ratio', 0)*100:.1f}%
  Close Strength: {features.get('close_strength', 0.5):.2f} | Breakout 20 Hari: {"YA" if features.get("breakout_20d") else "TIDAK"}
  Trend EMA: {features.get('trend', 'sideways').upper()}

RETURN:
  Harian: {features.get('return_1d', 0)*100:.2f}% | 5 Hari: {features.get('return_5d', 0)*100:.2f}% | 20 Hari: {features.get('return_20d', 0)*100:.2f}%

BERITA TERBARU:
{news_text}
"""
        stocks_sections.append(stock_section)

    all_stocks_text = "\n\n".join(stocks_sections)

    prompt = f"""Kamu adalah analis saham profesional Indonesia yang berpengalaman.
Analisis data dari {len(stocks_data)} saham berikut secara objektif dan berikan rekomendasi trading jangka pendek.

═══════════════════════════════════════
DAFTAR SAHAM YANG DIANALISIS:
═══════════════════════════════════════

{all_stocks_text}

═══════════════════════════════════════
INSTRUKSI:
═══════════════════════════════════════

Kembalikan hasil analisis dalam format JSON array yang berisi objek untuk masing-masing ticker seperti contoh di bawah ini. Pastikan urutan dan jumlah objek di dalam array persis sama dengan daftar saham yang diberikan di atas.

[
  {{
    "ticker": "TICKER_CONTOH",
    "analisis_teknikal": "...(penjelasan singkat kondisi teknikal)...",
    "analisis_berita": "...(rangkuman sentimen berita dan dampaknya)...",
    "risiko": ["risiko 1", "risiko 2", "risiko 3"],
    "peluang": ["peluang 1", "peluang 2", "peluang 3"],
    "strategi": "BELI_SORE_JUAL_PAGI" atau "BELI_PAGI_JUAL_SORE" atau "TIDAK_DIREKOMENDASIKAN",
    "alasan_strategi": "...(mengapa memilih strategi ini)...",
    "confidence": 0-100,
    "sentimen": {{
      "positif": <jumlah berita positif>,
      "netral": <jumlah berita netral>,
      "negatif": <jumlah berita negatif>
    }}
  }}
]

ATURAN:
1. Pilih BELI_SORE_JUAL_PAGI jika ada indikasi gap up pagi (sentimen positif, akumulasi sore).
2. Pilih BELI_PAGI_JUAL_SORE jika ada momentum intraday kuat (volume spike, breakout).
3. Pilih TIDAK_DIREKOMENDASIKAN jika risiko terlalu tinggi atau sinyal tidak jelas.
4. Confidence harus realistis. Jangan memberikan confidence > 90 kecuali sinyal sangat kuat.
5. JANGAN menjanjikan keuntungan. Selalu ingatkan bahwa investasi saham mengandung risiko.
6. Jawab HANYA dalam format JSON array di atas, tanpa teks penjelasan tambahan di luar JSON.
"""
    return prompt
