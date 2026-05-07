"""/admin/* — manual triggers + system status. Requires is_admin."""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    Exchange, PortfolioPosition, ScrapeRun, Stock, StockAnalystConsensus,
    StockLatestSnapshot, StockMarketDaily, StockRecommendation, User,
)
from .auth import get_current_user, get_db
from .schemas import AdminStatusOut, ScrapeRunOut

router = APIRouter(prefix="/admin", tags=["admin"])

_SCRAPER_URL = os.environ.get("SCRAPER_URL", "http://scraper:8001")
_RECOMMENDER_URL = os.environ.get("RECOMMENDER_URL", "http://recommender:8002")
_SENTIMENT_URL = os.environ.get("SENTIMENT_URL", "http://sentiment:8003")


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


@router.get("/status", response_model=AdminStatusOut)
def system_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    stock_count = db.scalar(
        select(func.count()).select_from(Stock).where(Stock.active.is_(True))
    ) or 0
    scored_today = db.scalar(
        select(func.count()).select_from(StockRecommendation)
        .where(StockRecommendation.score_date == date.today())
    ) or 0
    open_positions = db.scalar(
        select(func.count()).select_from(PortfolioPosition)
        .where(PortfolioPosition.is_open.is_(True))
    ) or 0
    last_scrape_at = db.scalar(select(func.max(ScrapeRun.run_time)))

    runs = db.execute(
        select(ScrapeRun, Stock.ticker)
        .outerjoin(Stock, Stock.id == ScrapeRun.stock_id)
        .order_by(desc(ScrapeRun.run_time)).limit(20)
    ).all()
    scrape_runs = [
        ScrapeRunOut(
            id=r[0].id, run_time=r[0].run_time, source=r[0].source,
            status=r[0].status, http_status=r[0].http_status,
            error_message=r[0].error_message, ticker=r[1],
        )
        for r in runs
    ]
    return AdminStatusOut(
        stock_count=stock_count, scored_today=scored_today,
        open_positions=open_positions, last_scrape_at=last_scrape_at,
        scrape_runs=scrape_runs,
    )


@router.post("/scrape-all")
async def trigger_scrape_all(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_SCRAPER_URL}/scrape/all")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.post("/score-all")
async def trigger_score_all(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_RECOMMENDER_URL}/score/all")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.post("/score-portfolio")
async def trigger_score_portfolio(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_RECOMMENDER_URL}/score/portfolio")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.post("/score-sentiment")
async def trigger_sentiment(_: User = Depends(require_admin)):
    """Run FinBERT over any news rows that don't have a sentiment label yet."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{_SENTIMENT_URL}/sentiment/score-pending")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


# ---------------------------------------------------------------------------
# Manual overrides (price + analyst consensus)
# ---------------------------------------------------------------------------
class StockOverrideRequest(BaseModel):
    """Admin-only override for a single stock.

    Any field omitted (or set to None) is left untouched. Submit only what you
    want to change. After submission the recommender should be re-scored so the
    verdict picks up the new inputs.
    """
    last_close: Optional[float] = Field(None, gt=0, description="Latest traded price.")
    currency: Optional[str] = Field(None, min_length=3, max_length=8,
                                    description="ISO-style currency code, e.g. AED, EGP.")
    analyst_target: Optional[float] = Field(None, gt=0)
    analyst_count: Optional[int] = Field(None, ge=0)
    analyst_rating: Optional[str] = Field(
        None, description="One of: Strong Buy, Buy, Hold, Sell, Strong Sell.",
    )


@router.post("/stocks/{exchange}/{ticker}/override")
def override_stock(
    exchange: str, ticker: str,
    req: StockOverrideRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manually overwrite price and/or analyst consensus for one stock.

    - Price overrides write to today's `stock_market_daily` row AND
      `stock_latest_snapshot.last_close`. Last-change-pct is recomputed if a
      previous-day close exists.
    - Analyst overrides upsert today's `stock_analyst_consensus` row. The
      recommender reads ONLY from this table for analyst inputs (not from the
      snapshot), so the next scoring run will pick the values up.
    - Currency is written to the `stocks` table.
    """
    stock = db.execute(
        select(Stock)
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .where(
            func.lower(Exchange.code) == exchange.lower(),
            func.upper(Stock.ticker) == ticker.upper(),
        )
    ).scalar_one_or_none()
    if not stock:
        raise HTTPException(404, "Stock not found")

    today = date.today()
    changes: dict[str, object] = {}

    # ---- Currency ----
    if req.currency:
        new_cur = req.currency.upper()
        if stock.currency != new_cur:
            stock.currency = new_cur
            stock.updated_at = datetime.utcnow()
            changes["currency"] = new_cur

    # ---- Price ----
    if req.last_close is not None:
        new_price = Decimal(str(req.last_close))

        # 1) Update today's market_daily row, creating it if missing.
        md_today = db.execute(
            select(StockMarketDaily)
            .where(StockMarketDaily.stock_id == stock.id,
                   StockMarketDaily.trading_date == today)
        ).scalar_one_or_none()
        if md_today:
            md_today.close_price = new_price
        else:
            db.add(StockMarketDaily(
                stock_id=stock.id, trading_date=today, close_price=new_price,
            ))

        # 2) Compute last_change_pct vs the most recent previous trading day.
        last_change_pct: Optional[Decimal] = None
        prev = db.execute(
            select(StockMarketDaily.close_price)
            .where(StockMarketDaily.stock_id == stock.id,
                   StockMarketDaily.trading_date < today,
                   StockMarketDaily.close_price.isnot(None))
            .order_by(desc(StockMarketDaily.trading_date)).limit(1)
        ).scalar_one_or_none()
        if prev and prev > 0:
            last_change_pct = (new_price - prev) / prev * Decimal("100")

        # 3) Snapshot.
        snap = {"last_close": new_price, "last_updated": datetime.utcnow()}
        if last_change_pct is not None:
            snap["last_change_pct"] = last_change_pct
        _upsert_snapshot(db, stock.id, snap)
        changes["last_close"] = float(new_price)
        if last_change_pct is not None:
            changes["last_change_pct"] = float(last_change_pct)

    # ---- Analyst consensus ----
    if any(v is not None for v in (req.analyst_target, req.analyst_count, req.analyst_rating)):
        # Compute upside vs latest known close (could be the override above).
        latest_close: Optional[Decimal] = None
        if req.last_close is not None:
            latest_close = Decimal(str(req.last_close))
        else:
            latest_close = db.execute(
                select(StockLatestSnapshot.last_close)
                .where(StockLatestSnapshot.stock_id == stock.id)
            ).scalar_one_or_none()

        upside_pct: Optional[Decimal] = None
        target_dec: Optional[Decimal] = None
        if req.analyst_target is not None:
            target_dec = Decimal(str(req.analyst_target))
            if latest_close and latest_close > 0:
                upside_pct = (target_dec - latest_close) / latest_close * Decimal("100")

        rating_cleaned = req.analyst_rating.strip() if req.analyst_rating else None

        # Upsert today's consensus row. Unique key in the schema is
        # (stock_id, consensus_date), so today's row is the natural target.
        existing = db.execute(
            select(StockAnalystConsensus)
            .where(StockAnalystConsensus.stock_id == stock.id,
                   StockAnalystConsensus.consensus_date == today)
        ).scalar_one_or_none()
        if existing:
            if target_dec is not None:
                existing.target_price = target_dec
                existing.implied_upside_pct = upside_pct
            if req.analyst_count is not None:
                existing.analyst_count = req.analyst_count
            if rating_cleaned is not None:
                existing.rating = rating_cleaned
            existing.scraped_at = datetime.utcnow()
        else:
            db.add(StockAnalystConsensus(
                stock_id=stock.id,
                consensus_date=today,
                analyst_count=req.analyst_count,
                rating=rating_cleaned,
                target_price=target_dec,
                implied_upside_pct=upside_pct,
                scraped_at=datetime.utcnow(),
            ))

        # Mirror into the snapshot for the screener UI.
        snap_an = {"last_updated": datetime.utcnow()}
        if target_dec is not None:
            snap_an["analyst_target"] = target_dec
        if upside_pct is not None:
            snap_an["analyst_upside_pct"] = upside_pct
        _upsert_snapshot(db, stock.id, snap_an)

        if req.analyst_target is not None:
            changes["analyst_target"] = float(target_dec)
            if upside_pct is not None:
                changes["analyst_upside_pct"] = float(upside_pct)
        if req.analyst_count is not None:
            changes["analyst_count"] = req.analyst_count
        if rating_cleaned is not None:
            changes["analyst_rating"] = rating_cleaned

    if not changes:
        raise HTTPException(400, "No fields provided")

    db.commit()

    # Fire-and-forget single-stock rescore so the verdict reflects the override
    # without requiring a follow-up call. We tolerate failures because the
    # override itself succeeded.
    rescored = None
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{_RECOMMENDER_URL}/score/single/{exchange.lower()}/{ticker.upper()}")
            if r.status_code < 400:
                rescored = r.json()
    except Exception:
        pass

    return {
        "ticker": stock.ticker,
        "exchange": exchange.lower(),
        "changes": changes,
        "rescored": rescored,
    }


def _upsert_snapshot(db: Session, stock_id: int, payload: dict):
    """PG-flavoured upsert that won't blow away unrelated columns."""
    record = {"stock_id": stock_id, **payload}
    stmt = pg_insert(StockLatestSnapshot).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={k: stmt.excluded[k] for k in record if k != "stock_id"},
    )
    db.execute(stmt)
