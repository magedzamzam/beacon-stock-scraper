"""Pydantic response & request schemas for the public API.

Field names here are the public REST contract. The frontend (TypeScript types
in `frontend/lib/api.ts`) is built against these exact names — keep them in
sync.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal, Any

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


# ---------- AI ----------
class AIProviderSettingUpsert(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None


class AIProviderSettingOut(BaseModel):
    provider_key: str
    provider_name: str
    enabled: bool
    api_key_present: bool
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_error: Optional[str] = None
    updated_at: Optional[datetime] = None


class AIPromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    scope: str
    description: Optional[str] = None
    system_prompt: str
    max_output_tokens: int = 256
    updated_at: Optional[datetime] = None


class AIAnalysisResult(BaseModel):
    provider_key: str
    provider_name: str
    model_name: str
    ok: bool
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    analysis: Optional[dict[str, Any]] = None


class AIAnalysisRequest(BaseModel):
    provider_keys: list[str] = []
    prompt_key: str = "stock_brief"
    account_id: Optional[int] = None


class AIAnalysisResponse(BaseModel):
    scope: str
    prompt_key: str
    context: dict[str, Any]
    results: list[AIAnalysisResult]


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
    next_earnings_date: Optional[date] = None
    earnings_time: Optional[str] = None


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

    # ----- Unified price (single source of truth) -----
    # current_price: live broker last_price if available, else scraped close.
    current_price: Optional[float] = None
    # prev_close: scraped close on the most recent prior trading day. Always
    # the same reference, regardless of which source current_price came from.
    prev_close: Optional[float] = None
    # change_abs / change_pct: ALWAYS (current_price - prev_close), so the
    # header and broker-quote card never disagree.
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    # Where current_price came from. 'broker' or 'scrape' or null.
    price_source: Optional[str] = None
    # When current_price was last refreshed.
    price_fetched_at: Optional[datetime] = None

    # ----- Earnings & share structure -----
    # Populated from the bulk-imported CSV (stockanalysis.com). Frontend uses
    # `data_imported_at` to show the user how fresh the figures are — bulk
    # imports happen manually so stale data is a real concern.
    earnings: Optional["EarningsBlock"] = None
    share_structure: Optional["ShareStructureBlock"] = None


class EarningsBlock(BaseModel):
    last_earnings_date: Optional[date] = None
    next_earnings_date: Optional[date] = None
    earnings_time: Optional[str] = None
    est_revenue: Optional[float] = None
    est_revenue_growth_pct: Optional[float] = None
    est_eps: Optional[float] = None
    # Days until next earnings (negative = past). Computed on the fly to avoid
    # cache invalidation pain. Null when next_earnings_date is null.
    days_to_next: Optional[int] = None
    # Days since last earnings. Negative = future.
    days_since_last: Optional[int] = None
    data_imported_at: Optional[datetime] = None


class ShareStructureBlock(BaseModel):
    shares_change_yoy_pct: Optional[float] = None
    shares_change_qoq_pct: Optional[float] = None
    insiders_pct: Optional[float] = None
    institutional_pct: Optional[float] = None
    # Derived at read time: 100 - insiders - institutional. Null if either
    # input is null (would be misleading otherwise).
    retail_pct: Optional[float] = None
    period_end: Optional[date] = None


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
    news_date: Optional[date] = None
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
    # Optional manual trading account that owns this position.
    # Must be a manual broker account; the API rejects automated ones.
    account_id: Optional[int] = None


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


# ---------- CSV Import ----------
class ImportTableColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    foreign_key: Optional[str] = None
    default: Optional[str] = None


class ImportTableOut(BaseModel):
    name: str
    label: str
    primary_key: list[str] = []
    unique_constraints: list[list[str]] = []
    suggested_match_columns: list[str] = []
    columns: list[ImportTableColumnOut] = []


class ImportCatalogOut(BaseModel):
    tables: list[ImportTableOut] = []


class ImportPreviewRowOut(BaseModel):
    row_number: int
    values: dict[str, Optional[str]]


class ImportPreviewOut(BaseModel):
    import_id: str
    filename: str
    encoding: str
    delimiter: str
    row_count: int
    headers: list[str] = []
    sample_rows: list[ImportPreviewRowOut] = []


class ImportExecuteRequest(BaseModel):
    import_id: str
    table_name: str
    mode: Literal["update", "insert"] = "update"
    column_mapping: dict[str, str] = {}
    match_columns: list[str] = []
    ignore_blank_values: bool = True


class ImportRowLogOut(BaseModel):
    row_number: int
    action: str
    message: str


class ImportExecuteOut(BaseModel):
    import_id: str
    table_name: str
    mode: str
    encoding: str
    delimiter: str
    processed: int
    inserted: int
    updated: int
    skipped: int
    errors: int
    row_logs: list[ImportRowLogOut] = []
    finished_at: datetime


# Resolve forward refs declared on StockDetail (earnings, share_structure).
StockDetail.model_rebuild()
