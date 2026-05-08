"""/stocks/* — screener listing + per-stock detail."""
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from shared.db import (
    Exchange, Stock, StockAnalystConsensus, StockBrokerQuote, StockLatestSnapshot,
    StockMarketDaily, StockNews, StockRecommendation, StockTechnicals,
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
    return StockSummary(
        id=r.id, ticker=r.ticker, exchange_code=r.exchange_code,
        company_name=r.company_name, sector=r.sector, industry=r.industry,
        country=r.country, currency=r.currency,
        last_close=_f(r.last_close), last_change_pct=_f(r.last_change_pct),
        market_cap=_f(r.market_cap), pe_ratio=_f(r.pe_ratio),
        dividend_yield_pct=_f(r.dividend_yield_pct),
        rsi_14=_f(getattr(r, "rsi_14", None)),
        composite_score=_f(r.composite_score),
        verdict=r.verdict, last_updated=r.last_updated,
    )


_SUMMARY_COLS = (
    Stock.id, Stock.ticker, Stock.company_name, Stock.sector, Stock.industry,
    Stock.country, Stock.currency,
    Exchange.code.label("exchange_code"),
    StockLatestSnapshot.last_close, StockLatestSnapshot.last_change_pct,
    StockLatestSnapshot.market_cap, StockLatestSnapshot.pe_ratio,
    StockLatestSnapshot.dividend_yield_pct, StockLatestSnapshot.rsi_14,
    StockLatestSnapshot.composite_score, StockLatestSnapshot.verdict,
    StockLatestSnapshot.last_updated,
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
        .outerjoin(StockLatestSnapshot, StockLatestSnapshot.stock_id == Stock.id)
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
        base = base.where(StockLatestSnapshot.verdict == verdict.upper())
    if min_score is not None:
        base = base.where(StockLatestSnapshot.composite_score >= min_score)
    if max_pe is not None:
        base = base.where(StockLatestSnapshot.pe_ratio <= max_pe)
    if min_dividend is not None:
        base = base.where(StockLatestSnapshot.dividend_yield_pct >= min_dividend)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0

    sort_col_map = {
        "composite_score": StockLatestSnapshot.composite_score,
        "market_cap": StockLatestSnapshot.market_cap,
        "last_close": StockLatestSnapshot.last_close,
        "last_change_pct": StockLatestSnapshot.last_change_pct,
        "dividend_yield_pct": StockLatestSnapshot.dividend_yield_pct,
        "pe_ratio": StockLatestSnapshot.pe_ratio,
        "rsi_14": StockLatestSnapshot.rsi_14,
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
    row = db.execute(
        select(
            *_SUMMARY_COLS,
            Stock.isin, Stock.founded_year, Stock.employees, Stock.website,
            StockLatestSnapshot.week_52_high, StockLatestSnapshot.week_52_low,
            StockLatestSnapshot.analyst_target, StockLatestSnapshot.analyst_upside_pct,
        )
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .outerjoin(StockLatestSnapshot, StockLatestSnapshot.stock_id == Stock.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
    ).first()
    if not row:
        raise HTTPException(404, "Stock not found")

    md = db.execute(
        select(StockMarketDaily)
        .where(StockMarketDaily.stock_id == row.id)
        .order_by(desc(StockMarketDaily.trading_date)).limit(1)
    ).scalars().first()
    tech = db.execute(
        select(StockTechnicals)
        .where(StockTechnicals.stock_id == row.id)
        .order_by(desc(StockTechnicals.trading_date)).limit(1)
    ).scalars().first()
    analyst = db.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == row.id)
        .order_by(desc(StockAnalystConsensus.consensus_date)).limit(1)
    ).scalars().first()

    # ---------------- Unified price (single source of truth) ----------------
    # Pick the most recent broker quote for this stock. Multiple brokers can
    # cover the same stock; prefer the one fetched most recently.
    bq = db.execute(
        select(StockBrokerQuote)
        .where(StockBrokerQuote.stock_id == row.id)
        .order_by(desc(StockBrokerQuote.fetched_at))
        .limit(1)
    ).scalars().first()

    # Reference: the second-most-recent close in stock_market_daily. Using the
    # second row guarantees we don't compare today's close against today's
    # close (which would always be 0%). If we only have ONE day on file,
    # there's no honest "previous close" — leave it null.
    prev_close = None
    md_rows = db.execute(
        select(StockMarketDaily.close_price, StockMarketDaily.trading_date)
        .where(StockMarketDaily.stock_id == row.id,
               StockMarketDaily.close_price.is_not(None))
        .order_by(desc(StockMarketDaily.trading_date))
        .limit(2)
    ).all()
    if len(md_rows) >= 2:
        prev_close = float(md_rows[1].close_price)

    # current_price: live broker if we have a fresh-enough quote, else scrape.
    current_price = None
    price_source = None
    price_fetched_at = None
    if bq is not None and bq.last_price is not None:
        current_price = float(bq.last_price)
        price_source = "broker"
        price_fetched_at = bq.fetched_at
    elif row.last_close is not None:
        current_price = float(row.last_close)
        price_source = "scrape"
        # last_updated on StockLatestSnapshot is the closest analog to "fetched_at"
        price_fetched_at = row.last_updated

    # change_abs / change_pct: always against prev_close, so header and quote
    # card mathematically agree.
    change_abs = change_pct = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change_abs = current_price - prev_close
        change_pct = (change_abs / prev_close) * 100.0

    summary = _row_to_summary(row)
    return StockDetail(
        **summary.model_dump(),
        isin=row.isin, founded_year=row.founded_year, employees=row.employees,
        website=row.website,
        beta=_f(md.beta) if md else None,
        forward_pe=_f(md.forward_pe) if md else None,
        week_52_high=_f(row.week_52_high), week_52_low=_f(row.week_52_low),
        enterprise_value=_f(md.enterprise_value) if md else None,
        revenue_ttm=_f(md.revenue_ttm) if md else None,
        sma_50=_f(tech.sma_50) if tech else None,
        sma_200=_f(tech.sma_200) if tech else None,
        analyst_target=_f(row.analyst_target),
        analyst_upside_pct=_f(row.analyst_upside_pct),
        analyst_count=analyst.analyst_count if analyst else None,
        analyst_rating=analyst.rating if analyst else None,
        # Unified price block
        current_price=current_price,
        prev_close=prev_close,
        change_abs=change_abs,
        change_pct=change_pct,
        price_source=price_source,
        price_fetched_at=price_fetched_at,
    )


# ---------------- Score breakdown ----------------
@router.get("/{exchange}/{ticker}/score", response_model=ScoreBreakdown)
def stock_score(exchange: str, ticker: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(StockRecommendation, Stock.ticker, Exchange.code.label("exchange_code"))
        .join(Stock, Stock.id == StockRecommendation.stock_id)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
        .order_by(desc(StockRecommendation.score_date)).limit(1)
    ).first()
    if not row:
        raise HTTPException(404, "No score yet for this stock — run the scoring job")
    rec: StockRecommendation = row[0]
    reasoning = rec.reasoning or {}
    return ScoreBreakdown(
        ticker=row.ticker, exchange_code=row.exchange_code, score_date=rec.score_date,
        fundamental_score=_f(rec.fundamental_score) or 0.0,
        valuation_score=_f(rec.valuation_score) or 0.0,
        momentum_score=_f(rec.momentum_score) or 0.0,
        technical_score=_f(rec.technical_score) or 0.0,
        analyst_score=_f(rec.analyst_score) or 0.0,
        quality_score=_f(rec.quality_score) or 0.0,
        risk_score=_f(rec.risk_score) or 0.0,
        composite_score=_f(rec.composite_score) or 0.0,
        verdict=rec.verdict,
        pros=reasoning.get("pros", []) or [],
        cons=reasoning.get("cons", []) or [],
        model_version=rec.model_version or "v1.0",
    )


# ---------------- Price history ----------------
@router.get("/{exchange}/{ticker}/price-history", response_model=list[PriceHistoryPoint])
def price_history(
    exchange: str, ticker: str,
    days: int = Query(180, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            StockMarketDaily.trading_date,
            StockMarketDaily.close_price,
            StockMarketDaily.volume,
        )
        .join(Stock, Stock.id == StockMarketDaily.stock_id)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(func.lower(Exchange.code) == exchange.lower(), func.upper(Stock.ticker) == ticker.upper())
        .order_by(desc(StockMarketDaily.trading_date)).limit(days)
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
