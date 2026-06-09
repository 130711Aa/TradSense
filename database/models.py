"""
TradSense - Database Models
============================
SQLAlchemy ORM models untuk menyimpan data saham, skor, dan analisis.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Base class untuk semua model."""
    pass


class StockPrice(Base):
    """Tabel harga saham harian."""

    __tablename__ = "stock_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<StockPrice(ticker={self.ticker}, date={self.date}, close={self.close})>"


class StockFeature(Base):
    """Tabel fitur/indikator teknikal yang dihitung."""

    __tablename__ = "stock_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    ema20 = Column(Float)
    ema50 = Column(Float)
    ema200 = Column(Float)
    rsi14 = Column(Float)
    atr14 = Column(Float)
    volume_ratio = Column(Float)
    close_strength = Column(Float)
    breakout_20d = Column(Boolean)
    highest_high_20d = Column(Float)
    return_1d = Column(Float)
    return_5d = Column(Float)
    return_20d = Column(Float)
    avg_value_20d = Column(Float)
    atr_ratio = Column(Float)  # ATR14 / Close
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<StockFeature(ticker={self.ticker}, date={self.date})>"


class StockScore(Base):
    """Tabel skor akhir per saham per hari."""

    __tablename__ = "stock_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    score_liquidity = Column(Float, default=0.0)
    score_volatility = Column(Float, default=0.0)
    score_volume_spike = Column(Float, default=0.0)
    score_close_strength = Column(Float, default=0.0)
    score_breakout = Column(Float, default=0.0)
    score_trend_ema = Column(Float, default=0.0)
    score_rsi = Column(Float, default=0.0)
    total_score = Column(Float, nullable=False)
    rank = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<StockScore(ticker={self.ticker}, score={self.total_score})>"


class AIAnalysis(Base):
    """Tabel hasil analisis AI per saham per hari."""

    __tablename__ = "ai_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    strategy = Column(String(50))  # "BELI_SORE_JUAL_PAGI" / "BELI_PAGI_JUAL_SORE" / "TIDAK_DIREKOMENDASIKAN"
    confidence = Column(Float)
    analysis_text = Column(Text)
    risk_summary = Column(Text)
    opportunity_summary = Column(Text)
    news_summary = Column(Text)
    news_count = Column(Integer, default=0)
    sentiment_positive = Column(Integer, default=0)
    sentiment_neutral = Column(Integer, default=0)
    sentiment_negative = Column(Integer, default=0)
    raw_ai_response = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AIAnalysis(ticker={self.ticker}, strategy={self.strategy}, confidence={self.confidence})>"


class RunLog(Base):
    """Tabel log eksekusi pipeline."""

    __tablename__ = "run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(DateTime, nullable=False)
    layer = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # "success", "error", "partial"
    message = Column(Text)
    duration_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<RunLog(layer={self.layer}, status={self.status})>"


class Subscriber(Base):
    """Tabel telegram chat id pelanggan/user."""

    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Subscriber(chat_id={self.chat_id}, username={self.username})>"


# ==================================================
# Database Engine & Session Factory
# ==================================================

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    """Inisialisasi database dan buat semua tabel."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Mendapatkan database session baru."""
    return SessionLocal()
