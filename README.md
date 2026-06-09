# TradSense 🤖📈

Sistem Rekomendasi Saham Indonesia berbasis AI.

TradSense melakukan pemindaian otomatis pasar saham BEI dua kali sehari:
1. **Sesi Pagi (08:30 WIB):** Sebelum market buka, menyajikan rekomendasi **BELI PAGI → JUAL SORE**.
2. **Sesi Sore (15:30 WIB):** Sebelum market tutup, menyajikan rekomendasi **BELI SORE → JUAL PAGI**.

Rekomendasi dikirim langsung ke Telegram dalam bentuk laporan analisis visual.

> **⚠️ DISCLAIMER:** Sistem ini TIDAK melakukan auto trading. Hanya memberikan rekomendasi analisis. Investasi saham mengandung risiko.

---

## Arsitektur

```
Layer 1 → Data Collection (yfinance + Finnhub + RSS)
Layer 2 → Filtering (Likuiditas, Harga, Volatilitas, Momentum)
Layer 3 → Feature Engine (EMA, RSI, ATR, Volume Ratio, dll)
Layer 4 → Scoring Engine (Skor 0-100 dengan bobot modular)
Layer 5 → AI Analysis (Google Gemini) + News Sentiment
Output  → Telegram Report (Top 5 rekomendasi per sesi)
```

## Struktur Proyek

```
TradSense/
├── config.py              # Konfigurasi pusat
├── main.py                # CLI entry point
├── pipeline.py            # Orchestrator pipeline
├── scheduler.py           # APScheduler dua sesi harian
├── requirements.txt       # Dependencies
├── .env.example           # Template environment variables
│
├── data/                  # Layer 1: Data Collection
│   ├── price_collector.py # Pengambilan harga via yfinance
│   └── news_collector.py  # Berita dari Finnhub + RSS
│
├── analysis/              # Layer 2 & 3
│   ├── filter.py          # Filtering kandidat saham
│   └── features.py        # Perhitungan indikator teknikal
│
├── scoring/               # Layer 4
│   └── engine.py          # Scoring engine modular
│
├── ai/                    # Layer 5
│   ├── analyzer.py        # AI/LLM analyzer (Gemini)
│   └── prompts.py         # Prompt builder
│
├── bot/                   # Telegram Output
│   └── telegram_reporter.py
│
├── database/              # Database layer
│   └── models.py          # SQLAlchemy ORM models
│
├── utils/                 # Utilities
│   └── logger.py          # Logging setup (UTF-8 Windows fixed)
│
├── db/                    # SQLite database (auto-created)
└── logs/                  # Log files (auto-created)
```

## Quick Start

### 1. Install Dependencies

Melalui terminal UCRT64 MSYS2 atau terminal Windows:
```bash
# Jalankan install script untuk setup lingkungan MSYS2 Python & Pip
bash install.sh
```

### 2. Konfigurasi Environment

```bash
cp .env.example .env
# Edit .env dan isi API keys
```

**API keys yang dibutuhkan:**
- `TELEGRAM_BOT_TOKEN` - Buat bot di [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` - Dapatkan dari [@userinfobot](https://t.me/userinfobot)
- `GEMINI_API_KEY` - Untuk AI analysis (Google Gemini)
- `FINNHUB_API_KEY` (opsional) - Untuk berita dari [finnhub.io](https://finnhub.io)

### 3. Test Komponen

```bash
python main.py --mode test
```

### 4. Jalankan Pipeline Manual

```bash
# Jalankan full pipeline untuk kedua strategi
python main.py

# Jalankan khusus untuk rekomendasi Beli Sore
python main.py --session BELI_SORE

# Jalankan khusus untuk rekomendasi Beli Pagi
python main.py --session BELI_PAGI

# Gunakan data lokal dari database (skip download yfinance)
python main.py --skip-fetch --session BELI_SORE
```

### 5. Jalankan Scheduler Harian

```bash
python main.py --mode scheduler
# Pipeline akan standby dan berjalan otomatis:
# - Setiap hari jam 08:30 WIB (Sesi Pagi)
# - Setiap hari jam 15:30 WIB (Sesi Sore)
```

### 6. Jalankan Bot Listener Interaktif (Multi-User)

Untuk membiarkan pengguna lain mendaftar (subscribe) ke bot Anda dan mendapatkan rekomendasi otomatis ke akun mereka sendiri:

```bash
python main.py --mode listener
# Bot akan standby mendengarkan perintah /start, /stop, /rekomendasi
```

Ketika pengguna mengirimkan perintah:
* `/start`: Bot mencatat `chat_id` mereka ke dalam database SQLite (`subscribers` table).
* `/rekomendasi`: Bot langsung mencarikan dan membalas dengan rekomendasi terupdate hari ini dari DB.
* `/stop`: Menghentikan langganan (menonaktifkan broadcast harian ke mereka).

Setiap kali scheduler atau pipeline harian berjalan, laporan rekomendasi akan otomatis dikirimkan (di-broadcast) ke **seluruh** pengguna aktif yang terdaftar di database. Jika database kosong, sistem akan otomatis melakukan fallback untuk mengirimkan ke `TELEGRAM_CHAT_ID` tunggal yang ada di file `.env`.

## Konfigurasi

Semua parameter dapat diubah di `config.py`:

| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `MIN_AVG_VALUE_20D` | 5 miliar | Filter likuiditas minimum |
| `MIN_PRICE` | 100 | Harga minimum saham |
| `MIN_ATR_RATIO` | 0.03 | ATR/Close minimum (3%) |
| `VOLUME_SPIKE_MULTIPLIER` | 1.5 | Multiplier volume spike |
| `SCORING_WEIGHTS` | dict | Bobot scoring (total 100) |
| `TOP_N_FOR_AI` | 10 | Jumlah saham untuk AI |
| `TELEGRAM_TOP_N` | 5 | Jumlah saham di report |
| `SCHEDULE_SORE_HOUR` | 15 | Jam eksekusi sesi sore |
| `SCHEDULE_SORE_MINUTE` | 30 | Menit eksekusi sesi sore |
| `SCHEDULE_PAGI_HOUR` | 8 | Jam eksekusi sesi pagi |
| `SCHEDULE_PAGI_MINUTE` | 30 | Menit eksekusi sesi pagi |

## Strategi Rekomendasi

TradSense merekomendasikan salah satu dari:

1. **BELI SORE → JUAL PAGI** - Saham dengan indikasi gap up (sentimen positif, akumulasi sore)
2. **BELI PAGI → JUAL SORE** - Saham dengan momentum intraday kuat (volume spike, breakout)
3. **TIDAK DIREKOMENDASIKAN** - Risiko terlalu tinggi / sinyal tidak jelas

## Scoring Weights

| Komponen | Bobot |
|----------|-------|
| Likuiditas | 10 |
| Volatilitas | 20 |
| Volume Spike | 20 |
| Close Strength | 15 |
| Breakout | 15 |
| Trend EMA | 10 |
| RSI | 10 |

## Tech Stack

- Python 3.12+
- pandas, numpy
- yfinance
- SQLAlchemy + SQLite
- APScheduler
- python-telegram-bot
- OpenAI / Google Gemini
- Rich (logging)
