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
    # URL path template for stockanalysis.com. {ticker} is the placeholder.
    # MENA / LSE: '/quote/dfm/{ticker}/', '/quote/lon/{ticker}/'
    # US:         '/stocks/{ticker}/'
    stockanalysis_url_template: Mapped[str] = mapped_column(Text, nullable=False)


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
    is_scraping_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    country: Mapped[Optional[str]] = mapped_column(Text)

    exchange: Mapped[Exchange] = relationship()


# --------- Market & price data ---------
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


class AccountBalanceSnapshot(Base):
    """Timeseries of account balance / equity / unrealized P/L.

    Captured both periodically (scheduler tick) and lazily (when the user
    opens an account view, with a freshness TTL). Manual accounts have
    NULL balance but DO have equity computed from open positions.
    """
    __tablename__ = "account_balance_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trading_accounts.id", ondelete="CASCADE"))
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    available: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    unrealized_pl: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    open_position_count: Mapped[Optional[int]] = mapped_column(Integer)
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(16), default="periodic")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    """Generic key/value config store. Values are JSON for flexibility.

    Today: holds the four scheduled-job descriptors keyed by 'job.<name>'.
    Tomorrow: any system-wide config the admin UI exposes.
    """
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))


class AIProviderSetting(Base):
    __tablename__ = "ai_provider_settings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text)
    model_name: Mapped[Optional[str]] = mapped_column(String(120))
    base_url: Mapped[Optional[str]] = mapped_column(Text)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_test_status: Mapped[Optional[str]] = mapped_column(String(16))
    last_test_error: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("user_id", "provider_key", name="ai_provider_settings_user_id_provider_key_key"),)


class AIPromptTemplate(Base):
    __tablename__ = "ai_prompt_templates"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=256)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobRun(Base):
    """Audit log of scheduled job executions, scheduled or manual."""
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")
    triggered_by: Mapped[str] = mapped_column(String(16), default="scheduled")
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    duration_s: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


# =========================================================================
# Parallel-schema models (Round 1 created the tables, Round 2 dual-writes,
# Round 3 switches reads, Round 4 drops the old tables).
# =========================================================================

class StockQuote(Base):
    """Denormalised 'current state' per stock — the canonical row that the
    screener and stock detail header will read from once Round 3 is in place.

    Maintained by:
      * scraper.pipeline._upsert_quote() after each daily scrape
      * scheduler.run_broker_quote_refresh() after each broker quote pull
      * recommender.pipeline after each scoring run (composite_score, verdict)
      * routers_admin.override (manual price override)
    """
    __tablename__ = "stock_quotes"
    stock_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True,
    )
    # Canonical price block
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    prev_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    change_abs: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_source: Mapped[Optional[str]] = mapped_column(String(16))
    price_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Denormalised for fast list rendering
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    pe_forward: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    dividend_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    week_52_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    week_52_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    analyst_target: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    analyst_upside_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    # Composite scoring (materialised by recommender)
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    verdict: Mapped[Optional[str]] = mapped_column(String(16))
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockCurQuote(Base):
    """Live broker quote per (stock, broker). Replaces stock_broker_quotes
    in Round 4.
    """
    __tablename__ = "stock_cur_quote"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    broker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    offer: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    last_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    # Renamed from change_abs/change_pct on stock_broker_quotes — these often
    # disagree with prev-close-based change. Don't use as canonical.
    broker_change_abs: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    broker_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    market_status: Mapped[Optional[str]] = mapped_column(String(32))
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "broker_id"),)


class StockHistoryQuote(Base):
    """Daily OHLC + volume time series per (stock, trading_date).
    NO broker_id — history is per-exchange.
    """
    __tablename__ = "stock_history_quote"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    source: Mapped[Optional[str]] = mapped_column(String(32))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "trading_date"),)


class StockFinRatios(Base):
    """Valuation ratios time series per (stock, period_end, period_type)."""
    __tablename__ = "stock_fin_ratios"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TTM")
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    pe_forward: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ps_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    pb_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    p_fcf_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    peg_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ev_sales: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ev_ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    roa: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    roic: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    sbc_revenue_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    fcf_per_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    current_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    debt_to_equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    fcf_yield: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    z_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 3))
    snapshot_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    snapshot_market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "period_end", "period_type"),)


class StockFinStatement(Base):
    """P&L items + growth metrics, time series."""
    __tablename__ = "stock_fin_statement"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TTM")
    last_report_date: Mapped[Optional[date]] = mapped_column(Date)
    revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    gross_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    operating_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    net_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    income_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    eps_diluted: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    revenue_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    revenue_growth_3y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    revenue_growth_5y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    gross_profit_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    operating_income_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    net_income_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    eps_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    eps_growth_3y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    eps_growth_5y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    profitable_years: Mapped[Optional[int]] = mapped_column(Integer)
    # Share structure (slow-moving, attached to the latest period snapshot)
    shares_change_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    shares_change_qoq: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    shares_insiders_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    shares_institutional_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    # Net Cash, Total Debt, and Shares Outstanding Calculation
    shares_outstanding: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    net_cash: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    total_debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "period_end", "period_type", "is_estimate"),)


class StockEarningsCalendar(Base):
    """One row per stock — latest known earnings calendar + analyst estimates.

    Populated by the bulk CSV importer. The screener filter
    'earnings within N days' queries the indexed next_earnings_date column.
    """
    __tablename__ = "stock_earnings_calendar"
    stock_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True,
    )
    last_earnings_date: Mapped[Optional[date]] = mapped_column(Date)
    next_earnings_date: Mapped[Optional[date]] = mapped_column(Date)
    earnings_time: Mapped[Optional[str]] = mapped_column(String(16))
    est_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    est_revenue_growth_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    est_eps: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    source: Mapped[Optional[str]] = mapped_column(String(32), default="bulk_import")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockFinCashflow(Base):
    """Cashflow items, time series. SBC lives here (non-cash expense)."""
    __tablename__ = "stock_fin_cashflow"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TTM")
    operating_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    investing_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    financing_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    net_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    cap_ex: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    free_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    sbc: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    fcf_minus_sbc: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    net_borrowing: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "period_end", "period_type", "is_estimate"),)


class StockMktDividends(Base):
    """Dividend metrics, current state only — one row per stock."""
    __tablename__ = "stock_mkt_dividends"
    stock_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True,
    )
    dividend_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    dividend_per_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    last_dividend_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ex_dividend_date: Mapped[Optional[date]] = mapped_column(Date)
    payout_ratio_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    payout_frequency: Mapped[Optional[str]] = mapped_column(String(32))
    div_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    div_growth_3y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    div_growth_5y: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    growth_years_streak: Mapped[Optional[int]] = mapped_column(Integer)
    payment_years_streak: Mapped[Optional[int]] = mapped_column(Integer)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockMktTechnicals(Base):
    """Technical indicators time series per (stock, trading_date).
    Replaces stock_technicals + stock_performance_daily in Round 4.
    """
    __tablename__ = "stock_mkt_technicals"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
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
    price_chg_1m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_chg_3m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_chg_6m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_chg_1y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_chg_3y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    price_chg_5y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    total_ret_1y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    total_ret_3y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    total_ret_5y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    ret_cagr_3y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    ret_cagr_5y_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    week_52_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    week_52_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    week_52_high_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    week_52_low_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    ath_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    ath_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    volume_daily: Mapped[Optional[int]] = mapped_column(BigInteger)
    dollar_volume_daily: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    avg_dollar_volume_30d: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4))
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("stock_id", "trading_date"),)


class StockScoring(Base):
    """Append-only scoring history. Each scoring run produces a new row.
    The latest row is denormalised onto stock_quotes.composite_score / verdict.
    """
    __tablename__ = "stock_scoring"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    verdict: Mapped[Optional[str]] = mapped_column(String(16))
    score_valuation: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    score_growth: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    score_quality: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    score_momentum: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    score_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    score_risk: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    pros: Mapped[Optional[list]] = mapped_column(JSONB)
    cons: Mapped[Optional[list]] = mapped_column(JSONB)
    risk_flags: Mapped[Optional[list]] = mapped_column(JSONB)
    model_version: Mapped[Optional[str]] = mapped_column(String(32))
    inputs_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockBulkImport(Base):
    """Audit row for a single bulk-CSV import job."""
    __tablename__ = "stock_bulk_imports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exchange_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exchanges.id", ondelete="RESTRICT"), nullable=False,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"),
    )
    filename: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    rows_errored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB)


class StockBulkImportRaw(Base):
    """Raw CSV row preserved per-stock per-import.

    The bulk importer maps ~220 of the 248 stockanalysis.com columns to
    structured tables. The ~30 unmapped columns (Z-Score, F-Score, 20MA,
    insider ownership, etc.) live here as jsonb so a future migration can
    extract them without re-uploading the CSV.
    """
    __tablename__ = "stock_bulk_import_raw"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stock_bulk_imports.id", ondelete="CASCADE"), nullable=False,
    )
    stock_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =============================================================================
# Alerts module (migration 012)
# =============================================================================
class AlertChannel(Base):
    """Where an alert goes — email, telegram, webhook, sms."""
    __tablename__ = "alert_channels"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRule(Base):
    """A rule that fires alerts when its condition is met."""
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stock_filter: Mapped[Optional[dict]] = mapped_column(JSONB)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRuleChannel(Base):
    """M2M wiring of rules to channels."""
    __tablename__ = "alert_rule_channels"
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alert_rules.id", ondelete="CASCADE"), primary_key=True,
    )
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alert_channels.id", ondelete="CASCADE"), primary_key=True,
    )


class AlertEvent(Base):
    """A fired alert — audit log + dedup state.

    Dedup: when evaluating, we look up the most recent event per (rule_id,
    stock_id) and skip firing if fired_at + cooldown_seconds > now.
    """
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False,
    )
    stock_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("stocks.id", ondelete="SET NULL"),
    )
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    delivery: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)


# =============================================================================
# Trading Bot — Milestone 1 (migration 015)
# =============================================================================
class TgChannel(Base):
    """Telegram channel the listener subscribes to. Includes per-channel
    strategy parameters used at execute-time (Milestone 3): order_position_type,
    tp_strategy, is_tradeable, is_trusted, image_url. Ported from the original
    bot's strategy_config.json.
    """
    __tablename__ = "tg_channels"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    channel_username: Mapped[Optional[str]] = mapped_column(String(80))
    channel_title: Mapped[str] = mapped_column(String(160), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parser_key: Mapped[str] = mapped_column(String(32), nullable=False, default="gold_xau")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Strategy params (migration 016). Defaults give "trade as MARKET, full
    # size at tp1, tradeable, trusted" so existing channels keep current
    # behaviour without admin re-edits.
    order_position_type: Mapped[str] = mapped_column(String(16), nullable=False, default="MARKET")
    tp_strategy: Mapped[str] = mapped_column(String(120), nullable=False, default="tp1")
    is_tradeable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TgRawMessage(Base):
    """Raw message captured by the listener. Queue for the parser worker."""
    __tablename__ = "tg_raw_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_title: Mapped[Optional[str]] = mapped_column(String(160))
    tg_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    message_text: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    parse_error: Mapped[Optional[str]] = mapped_column(Text)


class TgSignal(Base):
    """Parsed signal — one row per successful parse."""
    __tablename__ = "tg_signals"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tg_raw_messages.id", ondelete="CASCADE"), nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_title: Mapped[Optional[str]] = mapped_column(String(160))
    signal_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_from: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    entry_to: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    sl: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    tps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parser_key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BotTrade(Base):
    """Trade placed from a signal — links tg_signals → broker_orders.

    One signal can have many trades (different accounts, different TPs,
    user repeating the same trade by mistake). Lookup by signal_id is
    indexed so the UI can show "✓ Traded" badges efficiently.
    """
    __tablename__ = "bot_trades"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tg_signals.id", ondelete="CASCADE"), nullable=False,
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("broker_orders.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False,
    )
    tp_level: Mapped[Optional[str]] = mapped_column(String(8))
    risk_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    trade_mode: Mapped[str] = mapped_column(String(16), default="manual")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------- Engine factory ----------
_settings = get_settings()
_engine = create_engine(_settings.database_url_sync, pool_pre_ping=True, pool_size=10)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    return SessionLocal()
