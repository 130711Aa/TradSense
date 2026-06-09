"""
TradSense - Konfigurasi Utama
=============================
File konfigurasi pusat untuk seluruh sistem rekomendasi saham.
Semua parameter dapat diubah di sini tanpa menyentuh kode utama.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ==================================================
# PATH
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(exist_ok=True)
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ==================================================
# DATABASE
# ==================================================
DATABASE_URL = f"sqlite:///{DB_DIR / 'tradsense.db'}"

# ==================================================
# API KEYS
# ==================================================
FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ==================================================
# DATA COLLECTION
# ==================================================
# Suffix yfinance untuk saham BEI
YF_SUFFIX = ".JK"

# Jumlah hari historis minimal
HISTORICAL_DAYS: int = 365  # ~250 trading days

# RSS Feed URLs
RSS_FEEDS: dict[str, str] = {
    "detik": "https://finance.detik.com/rss",
    "kontan": "https://investasi.kontan.co.id/rss",
    "cnbc": "https://www.cnbcindonesia.com/market/rss",
}

# Jumlah berita maksimal per saham
MAX_NEWS_PER_TICKER: int = 10

# ==================================================
# FILTERING (Layer 2)
# ==================================================
# Average Value Traded 20 hari (dalam Rupiah)
MIN_AVG_VALUE_20D: float = 5_000_000_000  # 5 miliar

# Harga minimum
MIN_PRICE: float = 100.0

# ATR(14)/Close minimum (dalam desimal, 3% = 0.03)
MIN_ATR_RATIO: float = 0.03

# Volume spike: Volume hari ini > X × SMA Volume 20
VOLUME_SPIKE_MULTIPLIER: float = 1.5

# Target jumlah kandidat
MIN_CANDIDATES: int = 10
MAX_CANDIDATES: int = 50

# ==================================================
# FEATURE ENGINE (Layer 3)
# ==================================================
EMA_PERIODS: list[int] = [20, 50, 200]
RSI_PERIOD: int = 14
ATR_PERIOD: int = 14
VOLUME_SMA_PERIOD: int = 20
BREAKOUT_PERIOD: int = 20

# ==================================================
# SCORING ENGINE (Layer 4)
# ==================================================
SCORING_WEIGHTS: dict[str, float] = {
    "liquidity": 10,
    "volatility": 20,
    "volume_spike": 20,
    "close_strength": 15,
    "breakout": 15,
    "trend_ema": 10,
    "rsi": 10,
}

# Jumlah top saham untuk AI analysis
TOP_N_FOR_AI: int = 10

# ==================================================
# AI ANALYSIS (Layer 5) - Google Gemini
# ==================================================
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_TEMPERATURE: float = 0.3

# ==================================================
# TELEGRAM OUTPUT
# ==================================================
# Jumlah saham yang ditampilkan di report
TELEGRAM_TOP_N: int = 5

# ==================================================
# SCHEDULER
# ==================================================
# Jam eksekusi harian (WIB = UTC+7)
# Sesi Sore (Beli Sore -> Jual Pagi): Sebelum market close (15:30 WIB)
SCHEDULE_SORE_HOUR: int = 15
SCHEDULE_SORE_MINUTE: int = 30

# Sesi Pagi (Beli Pagi -> Jual Sore): Sebelum market open (08:30 WIB)
SCHEDULE_PAGI_HOUR: int = 8
SCHEDULE_PAGI_MINUTE: int = 30

SCHEDULE_TIMEZONE: str = "Asia/Jakarta"

# ==================================================
# LOGGING
# ==================================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = str(LOG_DIR / "tradsense.log")

# ==================================================
# DAFTAR SAHAM BEI AKTIF
# ==================================================
# Daftar saham BEI yang aktif diperdagangkan (Top ~200 saham likuid)
# Bisa di-update secara periodik
IDX_TICKERS: list[str] = [
    "AALI", "ACES", "ADHI", "ADRO", "AGII", "AKRA", "AMRT", "ANTM",
    "ARTO", "ASII", "ASRI", "AVIA", "BBCA", "BBHI", "BBMD", "BBNI",
    "BBRI", "BBTN", "BBYB", "BDMN", "BEEN", "BFIN", "BIRD", "BJTM",
    "BMRI", "BMTR", "BRMS", "BRPT", "BRIS", "BSDE", "BTPS", "BUKA",
    "CLEO", "CPIN", "CTRA", "DEWA", "DILD", "DMAS", "DSNG", "DSSA",
    "ELSA", "EMTK", "ENRG", "ERAA", "ESSA", "EXCL", "FILM", "GGRM",
    "GIAA", "GOTO", "GJTL", "HEAL", "HEXA", "HMSP", "HRUM", "IATA",
    "ICBP", "INCO", "INDF", "INKP", "INTP", "ISAT", "ITMG", "JPFA",
    "JSMR", "KAEF", "KLBF", "KPIG", "LINK", "LPPF", "LSIP", "MAPI",
    "MBMA", "MDKA", "MEDC", "MIKA", "MNCN", "MPPA", "MTDL", "MTEL",
    "MYOH", "NCKL", "NICE", "NISP", "PANI", "PGAS", "PGEO", "PNBN",
    "PTBA", "PTPP", "PWON", "RAJA", "RANC", "SCMA", "SIDO", "SILO",
    "SIMP", "SMGR", "SMRA", "SRTG", "SSMS", "SSIA", "TAPG", "TBIG",
    "TINS", "TKIM", "TLKM", "TOWR", "TPIA", "TSPC", "UNTR", "UNVR",
    "VIVA", "WIKA", "WMUU", "WOOD", "WSKT",
]
