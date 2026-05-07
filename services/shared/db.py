"""SQLAlchemy engine + ORM models. Imported by every service."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric,
    String, Text, UniqueConstraint, create_engine, JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session,
)

from .settings import get_settings


class Base(DeclarativeBase):
    pass


# --------- Reference tables ---------
class Exchange(Base):
    __tablename__ = "exchanges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(100))


class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exchange_id: Mapped[int] = mapped_column(Integer, ForeignKey("exchanges.id"))
    ticker: Mapped[str] = mapped_column(String(32))
    isin: Mapped[Optional[str]] = mapped_column(String(32))
    marketscreener_slug: Mapped[Optional[str]] = mapped_column(Text)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(Text)
    industry: Mapped[Optional[str]] = mapped_column(Text)
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    founded_year: Mapped[Optional[int]] = mapped_column(Integer)
    employees: Mapped[Optional[int]] = mapped_column(Integer)
    website: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    country: Mapped[Optional[str]] = mapped_column(Text)

    exchange: Mapped[Exchange] = relationship()


# --------- Market & price data ---------
class StockMarketDaily(Base):
    __tablename__ = "stock_market_daily"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    free_float_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    forward_pe: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    dividend: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    dividend_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    week_52_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    week_52_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    enterprise_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    revenue_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "trading_date"),)


class StockPerformanceDaily(Base):
    __tablename__ = "stock_performance_daily"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_1d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_1w: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_1m: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_3m: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_6m: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_ytd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_1y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_5y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    return_10y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "trading_date"),)


class StockValuation(Base):
    __tablename__ = "stock_valuation"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    pe: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ev_sales: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ev_ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    price_to_book: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    dividend_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    source_date: Mapped[Optional[date]] = mapped_column(Date)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "fiscal_year"),)


class StockFinancials(Base):
    __tablename__ = "stock_financials"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    net_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    operating_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    total_assets: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    total_equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    total_debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    cash_and_equivalents: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    operating_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    free_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    source_date: Mapped[Optional[date]] = mapped_column(Date)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockAnalystConsensus(Base):
    __tablename__ = "stock_analyst_consensus"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    consensus_date: Mapped[date] = mapped_column(Date, nullable=False)
    analyst_count: Mapped[Optional[int]] = mapped_column(Integer)
    rating: Mapped[Optional[str]] = mapped_column(String(32))
    target_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    implied_upside_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockNews(Base):
    __tablename__ = "stock_news"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id"), nullable=False)
    news_date: Mapped[Optional[date]] = mapped_column(Date)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source_code: Mapped[Optional[str]] = mapped_column(String(32))
    url: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(16))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("stocks.id"))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    run_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[Optional[str]] = mapped_column(String(16))
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


# --------- Enhancements (new tables from migration 001) ---------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), default="Default")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("watchlists.id", ondelete="CASCADE"))
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    note: Mapped[Optional[str]] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    entry_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional FK to a manual trading account. NULL = legacy / unattached.
    account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("trading_accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockRecommendation(Base):
    __tablename__ = "stock_recommendations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    fundamental_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    valuation_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    momentum_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    technical_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    analyst_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    risk_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reasoning: Mapped[Optional[dict]] = mapped_column(JSONB)
    model_version: Mapped[Optional[str]] = mapped_column(String(32), default="v1")
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PositionRecommendation(Base):
    __tablename__ = "position_recommendations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("portfolio_positions.id", ondelete="CASCADE"))
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    unrealized_pl_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    reasoning: Mapped[Optional[dict]] = mapped_column(JSONB)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockTechnicals(Base):
    __tablename__ = "stock_technicals"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    sma_50: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    sma_200: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ema_20: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    atr_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volatility_30d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    above_sma_50: Mapped[Optional[bool]] = mapped_column(Boolean)
    above_sma_200: Mapped[Optional[bool]] = mapped_column(Boolean)
    golden_cross: Mapped[Optional[bool]] = mapped_column(Boolean)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockDisclosure(Base):
    __tablename__ = "stock_disclosures"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    disclosure_date: Mapped[Optional[date]] = mapped_column(Date)
    disclosure_type: Mapped[Optional[str]] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    importance: Mapped[Optional[str]] = mapped_column(String(16))
    source: Mapped[Optional[str]] = mapped_column(String(64))
    url: Mapped[Optional[str]] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockLatestSnapshot(Base):
    __tablename__ = "stock_latest_snapshot"
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    last_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    last_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    dividend_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    week_52_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    week_52_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    analyst_target: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    analyst_upside_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    verdict: Mapped[Optional[str]] = mapped_column(String(16))
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StockCorporateAction(Base):
    __tablename__ = "stock_corporate_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"))
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
# ============================================================================
# Broker integration (migration 002)
# ============================================================================
class Broker(Base):
    """Registry of broker types. Each row = a kind of broker, not a user account."""
    __tablename__ = "brokers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    adapter_class: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(255))
    docs_url: Mapped[Optional[str]] = mapped_column(String(255))
    credential_schema: Mapped[list] = mapped_column(JSONB, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradingAccount(Base):
    __tablename__ = "trading_accounts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    broker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brokers.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    credentials_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    credentials_nonce: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    display_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connect_status: Mapped[Optional[str]] = mapped_column(String(16))
    last_connect_error: Mapped[Optional[str]] = mapped_column(Text)
    last_connect_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "broker_id", "label"),)


class BrokerInstrument(Base):
    __tablename__ = "broker_instruments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    broker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brokers.id", ondelete="CASCADE"))
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_name: Mapped[Optional[str]] = mapped_column(String(255))
    instrument_type: Mapped[Optional[str]] = mapped_column(String(32))
    stock_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="SET NULL"))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    min_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("broker_id", "broker_symbol"),)


class BrokerOrder(Base):
    __tablename__ = "broker_orders"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trading_accounts.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    stock_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="SET NULL"))
    broker_symbol: Mapped[Optional[str]] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    limit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    take_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    broker_order_ref: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    fill_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BrokerPositionSnapshot(Base):
    __tablename__ = "broker_positions_snapshot"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trading_accounts.id", ondelete="CASCADE"))
    stock_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="SET NULL"))
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    avg_open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    unrealized_pl: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    unrealized_pl_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    direction: Mapped[Optional[str]] = mapped_column(String(8))
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("account_id", "broker_symbol"),)


# ---------- Engine factory ----------
_settings = get_settings()
_engine = create_engine(_settings.database_url_sync, pool_pre_ping=True, pool_size=10)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    return SessionLocal()
