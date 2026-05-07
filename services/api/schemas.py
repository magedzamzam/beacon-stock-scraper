"""Pydantic response & request schemas for the public API.

Field names here are the public REST contract. The frontend (TypeScript types
in `frontend/lib/api.ts`) is built against these exact names — keep them in
sync.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: Optional[str] = None
    is_admin: bool = False
    created_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Stocks ----------
class StockSummary(BaseModel):
    """Stock row shown in screener / watchlist / portfolio lists."""
    id: int
    ticker: str
    exchange_code: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    last_close: Optional[float] = None
    last_change_pct: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    rsi_14: Optional[float] = None
    composite_score: Optional[float] = None
    verdict: Optional[str] = None
    last_updated: Optional[datetime] = None


class StockDetail(StockSummary):
    isin: Optional[str] = None
    founded_year: Optional[int] = None
    employees: Optional[int] = None
    website: Optional[str] = None
    beta: Optional[float] = None
    forward_pe: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    enterprise_value: Optional[float] = None
    revenue_ttm: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    analyst_target: Optional[float] = None
    analyst_upside_pct: Optional[float] = None
    analyst_count: Optional[int] = None
    analyst_rating: Optional[str] = None


class ScoreBreakdown(BaseModel):
    ticker: str
    exchange_code: str
    score_date: date
    fundamental_score: float
    valuation_score: float
    momentum_score: float
    technical_score: float
    analyst_score: float
    quality_score: float
    risk_score: float
    composite_score: float
    verdict: str
    pros: list[str] = []
    cons: list[str] = []
    model_version: str = "v1.0"


class PriceHistoryPoint(BaseModel):
    trading_date: date
    close: Optional[float] = None
    volume: Optional[float] = None


class NewsItem(BaseModel):
    id: int
    news_date: date
    headline: str
    source_code: Optional[str] = None
    url: Optional[str] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    summary: Optional[str] = None


class ScreenerResponse(BaseModel):
    total: int
    items: list[StockSummary]


class FilterExchange(BaseModel):
    code: str
    name: str


class FilterOptions(BaseModel):
    exchanges: list[FilterExchange]
    sectors: list[str] = []
    industries: list[str] = []
    verdicts: list[str] = ["BUY", "WATCH", "STAY_AWAY"]


# ---------- Watchlists ----------
class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WatchlistAddItemRequest(BaseModel):
    stock_id: int
    note: Optional[str] = None


class WatchlistItemOut(BaseModel):
    id: int
    note: Optional[str] = None
    added_at: datetime
    stock: StockSummary


class WatchlistOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    items: list[WatchlistItemOut] = []


# ---------- Portfolio ----------
class PositionCreateRequest(BaseModel):
    stock_id: int
    quantity: float = Field(gt=0)
    avg_entry_price: float = Field(gt=0)
    entry_date: Optional[date] = None
    notes: Optional[str] = None


class PositionOut(BaseModel):
    id: int
    stock: StockSummary
    quantity: float
    avg_entry_price: float
    entry_date: Optional[date] = None
    notes: Optional[str] = None
    cost_basis: float
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None
    unrealized_pl_pct: Optional[float] = None
    position_verdict: Optional[str] = None
    position_confidence: Optional[float] = None
    position_reasoning: Optional[list[str]] = None


class PortfolioOut(BaseModel):
    positions: list[PositionOut]
    total_cost: float = 0.0
    total_value: float = 0.0
    total_pl: float = 0.0
    total_pl_pct: float = 0.0


# ---------- Admin ----------
class ScrapeRunOut(BaseModel):
    id: int
    run_time: Optional[datetime] = None
    source: Optional[str] = None
    status: Optional[str] = None
    http_status: Optional[int] = None
    error_message: Optional[str] = None
    ticker: Optional[str] = None  # joined from stocks if stock_id is set


class AdminStatusOut(BaseModel):
    stock_count: int
    scored_today: int
    open_positions: int
    last_scrape_at: Optional[datetime] = None
    scrape_runs: list[ScrapeRunOut] = []
