"""/stocks/* — screener listing + per-stock detail."""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from shared.db import (
    Exchange, Stock, StockAnalystConsensus, StockNews,
    StockQuote, StockHistoryQuote, StockCurQuote,
    StockFinRatios, StockFinStatement, StockMktTechnicals, StockScoring,
)
from .auth import get_db
from .schemas import (
    FilterExchange, FilterOptions, NewsItem, PriceHistoryPoint, ScoreBreakdown,
    ScreenerResponse, StockDetail, StockSummary,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])

_SCRAPER_URL = os.environ.get("SCRAPER_URL", "http://scraper:8001")


def _f(v) -> Optional[float]:
    """Decimal/None -> float/None."""
    return float(v) if v is not None else None


def _row_to_summary(r) -> StockSummary:
    """Map a screener result row → StockSummary.

    Round 3: reads now come from StockQuote, but the API contract still uses
    last_close / last_change_pct field names for backward compat. We map
    StockQuote.current_price → last_close, StockQuote.change_pct → last_change_pct.
    Frontend keeps working without changes.
    """
    return StockSummary(
        id=r.id, ticker=r.ticker, exchange_code=r.exchange_code,
        company_name=r.company_name, sector=r.sector, industry=r.industry,
        country=r.country, currency=r.currency,
        last_close=_f(r.current_price), last_change_pct=_f(r.change_pct),
        market_cap=_f(r.market_cap), pe_ratio=_f(r.pe_ratio),
        dividend_yield_pct=_f(r.dividend_yield_pct),
        rsi_14=_f(getattr(r, "rsi_14", None)),
        composite_score=_f(r.composite_score),
        verdict=r.verdict, last_updated=r.last_updated,
    )


# Round 3: _SUMMARY_COLS now sources from stock_quotes (canonical row).
# Joining stock_quotes is O(1) per row — no DISTINCT ON needed since it's
# Joining stock_quotes is O(1) per row — already denormalised.
_SUMMARY_COLS = (
    Stock.id, Stock.ticker, Stock.company_name, Stock.sector, Stock.industry,
    Stock.country, Stock.currency,
    Exchange.code.label("exchange_code"),
    StockQuote.current_price, StockQuote.change_pct,
    StockQuote.market_cap, StockQuote.pe_ratio,
    StockQuote.dividend_yield_pct, StockQuote.rsi_14,
    StockQuote.composite_score, StockQuote.verdict,
    StockQuote.last_updated,
)


# ---------------- Screener ----------------
@router.get("", response_model=ScreenerResponse)
def screener(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None),
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    verdict: Optional[str] = None,
    min_score: Optional[float] = None,
    max_pe: Optional[float] = None,
    min_dividend: Optional[float] = None,
    sort_by: str = Query(
        "composite_score",
        pattern="^(composite_score|market_cap|last_close|last_change_pct|dividend_yield_pct|pe_ratio|rsi_14|ticker)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
):
    base = (
        select(*_SUMMARY_COLS)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .outerjoin(StockQuote, StockQuote.stock_id == Stock.id)
        .where(Stock.active.is_(True))
    )
    if q:
        like = f"%{q.lower()}%"
        base = base.where(func.lower(Stock.ticker).like(like) | func.lower(Stock.company_name).like(like))
    if exchange:
        base = base.where(func.lower(Exchange.code) == exchange.lower())
    if sector:
        base = base.where(Stock.sector == sector)
    if industry:
        base = base.where(Stock.industry == industry)
    if verdict:
        base = base.where(StockQuote.verdict == verdict.upper())
    if min_score is not None:
        base = base.where(StockQuote.composite_score >= min_score)
    if max_pe is not None:
        base = base.where(StockQuote.pe_ratio <= max_pe)
    if min_dividend is not None:
        base = base.where(StockQuote.dividend_yield_pct >= min_dividend)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0

    sort_col_map = {
        "composite_score": StockQuote.composite_score,
        "market_cap": StockQuote.market_cap,
        "last_close": StockQuote.current_price,
        "last_change_pct": StockQuote.change_pct,
        "dividend_yield_pct": StockQuote.dividend_yield_pct,
        "pe_ratio": StockQuote.pe_ratio,
        "rsi_14": StockQuote.rsi_14,
        "ticker": Stock.ticker,
    }
    col = sort_col_map[sort_by]
    base = base.order_by(desc(col).nullslast() if sort_dir == "desc" else col.asc().nullslast())

    rows = db.execute(base.offset(offset).limit(limit)).all()
    return ScreenerResponse(total=total, items=[_row_to_summary(r) for r in rows])


# ---------------- Filter options ----------------
@router.get("/filters", response_model=FilterOptions)
def filters(db: Session = Depends(get_db)):
    exchanges = [
        FilterExchange(code=ex.code, name=ex.name)
        for ex in db.execute(select(Exchange).order_by(Exchange.code)).scalars().all()
    ]
    sectors = sorted({
        s for (s,) in db.execute(
            select(Stock.sector).where(Stock.sector.isnot(None), Stock.active.is_(True)).distinct()
        ).all() if s
    })
    industries = sorted({
        i for (i,) in db.execute(
            select(Stock.industry).where(Stock.industry.isnot(None), Stock.active.is_(True)).distinct()
        ).all() if i
    })
    return FilterOptions(exchanges=exchanges, sectors=sectors, industries=industries)


# ---------------- Stock detail ----------------
@router.get("/{exchange}/{ticker}", response_model=StockDetail)
def stock_detail(exchange: str, ticker: str, db: Session = Depends(get_db)):
    # Round 3: read the canonical price block (current_price, prev_close,
    # change_abs, change_pct, price_source, price_fetched_at) directly from
    # stock_quotes. The recompute logic now lives in the writers (scraper,
    # broker_quotes router, scheduler), so this handler doesn't need to
    # re-derive anything — single source of truth, no chance of disagreement.
    row = db.execute(
        select(
            *_SUMMARY_COLS,
            Stock.isin, Stock.founded_year, Stock.employees, Stock.website,
            StockQuote.prev_close, StockQuote.change_abs,
            StockQuote.price_source, StockQuote.price_fetched_at,
            StockQuote.week_52_high, StockQuote.week_52_low,
            StockQuote.analyst_target, StockQuote.analyst_upside_pct,
        )
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .outerjoin(StockQuote, StockQuote.stock_id == Stock.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
    ).first()
    if not row:
        raise HTTPException(404, "Stock not found")

    # Detail-only context: latest financials for forward_pe / EV / revenue_ttm,
    # latest technicals for SMA / beta, latest analyst for count/rating.
    fin_ratios = db.execute(
        select(StockFinRatios)
        .where(StockFinRatios.stock_id == row.id)
        .order_by(desc(StockFinRatios.period_end), desc(StockFinRatios.id)).limit(1)
    ).scalars().first()
    fin_stmt = db.execute(
        select(StockFinStatement)
        .where(StockFinStatement.stock_id == row.id,
               StockFinStatement.is_estimate.is_(False))
        .order_by(desc(StockFinStatement.period_end), desc(StockFinStatement.id)).limit(1)
    ).scalars().first()
    tech = db.execute(
        select(StockMktTechnicals)
        .where(StockMktTechnicals.stock_id == row.id)
        .order_by(desc(StockMktTechnicals.trading_date)).limit(1)
    ).scalars().first()
    analyst = db.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == row.id)
        .order_by(desc(StockAnalystConsensus.consensus_date)).limit(1)
    ).scalars().first()

    summary = _row_to_summary(row)
    return StockDetail(
        **summary.model_dump(),
        isin=row.isin, founded_year=row.founded_year, employees=row.employees,
        website=row.website,
        beta=_f(tech.beta) if tech else None,
        forward_pe=_f(fin_ratios.pe_forward) if fin_ratios else None,
        week_52_high=_f(row.week_52_high), week_52_low=_f(row.week_52_low),
        enterprise_value=_f(fin_ratios.snapshot_market_cap) if fin_ratios else None,
        revenue_ttm=_f(fin_stmt.revenue) if fin_stmt else None,
        sma_50=_f(tech.sma_50) if tech else None,
        sma_200=_f(tech.sma_200) if tech else None,
        analyst_target=_f(row.analyst_target),
        analyst_upside_pct=_f(row.analyst_upside_pct),
        analyst_count=analyst.analyst_count if analyst else None,
        analyst_rating=analyst.rating if analyst else None,
        # Canonical price block — straight from stock_quotes.
        current_price=_f(row.current_price),
        prev_close=_f(row.prev_close),
        change_abs=_f(row.change_abs),
        change_pct=_f(row.change_pct),
        price_source=row.price_source,
        price_fetched_at=row.price_fetched_at,
    )


# ---------------- Score breakdown ----------------
@router.get("/{exchange}/{ticker}/score", response_model=ScoreBreakdown)
def stock_score(exchange: str, ticker: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(StockScoring, Stock.ticker, Exchange.code.label("exchange_code"))
        .join(Stock, Stock.id == StockScoring.stock_id)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
        .order_by(desc(StockScoring.updated_at)).limit(1)
    ).first()
    if not row:
        raise HTTPException(404, "No score yet for this stock — run the scoring job")
    rec: StockScoring = row[0]
    inputs = rec.inputs_snapshot or {}
    # ScoreBreakdown still wants 7 component scores; map new schema + recover
    # fundamental/technical/analyst from inputs_snapshot when present.
    return ScoreBreakdown(
        ticker=row.ticker, exchange_code=row.exchange_code,
        score_date=rec.updated_at.date() if rec.updated_at else date.today(),
        fundamental_score=float(inputs.get("fundamental_score") or 0.0),
        valuation_score=_f(rec.score_valuation) or 0.0,
        momentum_score=_f(rec.score_momentum) or 0.0,
        technical_score=float(inputs.get("technical_score") or 0.0),
        analyst_score=float(inputs.get("analyst_score") or 0.0),
        quality_score=_f(rec.score_quality) or 0.0,
        risk_score=_f(rec.score_risk) or 0.0,
        composite_score=_f(rec.composite_score) or 0.0,
        verdict=rec.verdict or "WATCH",
        pros=rec.pros or [],
        cons=rec.cons or [],
        model_version=rec.model_version or "v1.1",
    )


# ---------------- Price history ----------------
@router.get("/{exchange}/{ticker}/price-history", response_model=list[PriceHistoryPoint])
def price_history(
    exchange: str, ticker: str,
    days: int = Query(180, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    # Round 3: read history from stock_history_quote (parallel table).
    rows = db.execute(
        select(
            StockHistoryQuote.trading_date,
            StockHistoryQuote.close_price,
            StockHistoryQuote.volume,
        )
        .join(Stock, Stock.id == StockHistoryQuote.stock_id)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
        .order_by(desc(StockHistoryQuote.trading_date)).limit(days)
    ).all()
    return [
        PriceHistoryPoint(
            trading_date=r.trading_date,
            close=_f(r.close_price),
            volume=_f(r.volume),
        )
        for r in reversed(rows)
    ]


# ---------------- News ----------------
@router.get("/{exchange}/{ticker}/news", response_model=list[NewsItem])
def stock_news(
    exchange: str, ticker: str,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(StockNews)
        .join(Stock, Stock.id == StockNews.stock_id)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
        .order_by(desc(StockNews.news_date), desc(StockNews.scraped_at)).limit(limit)
    ).scalars().all()
    out = []
    for n in rows:
        out.append(NewsItem(
            id=n.id,
            news_date=n.news_date,
            headline=n.headline,
            source_code=n.source_code,
            url=n.url,
            sentiment_label=n.sentiment_label,
            sentiment_score=_f(n.sentiment_score),
            summary=n.summary,
        ))
    return out


# ---------------- Refresh (re-scrape one stock) ----------------
@router.post("/{exchange}/{ticker}/refresh")
async def refresh_stock(exchange: str, ticker: str):
    if exchange.lower() not in {"adx", "dfm", "egx"}:
        raise HTTPException(400, "Bad exchange")
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{_SCRAPER_URL}/scrape/{exchange.lower()}/{ticker.upper()}")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()
