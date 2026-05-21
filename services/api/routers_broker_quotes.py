"""Live broker quotes for stocks that have a broker_instruments mapping.

Endpoints:
    GET  /stocks/{stock_id}/broker_quotes        list all latest quotes
                                                 (auto-refreshes if stale/missing)
    POST /stocks/{stock_id}/broker_quotes/refresh refresh one or all (manual)

The hourly periodic refresh lives in the scheduler.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    Broker, BrokerInstrument, Stock, User,
    StockCurQuote, StockHistoryQuote, StockQuote,
)

from .auth import get_current_user, get_db


broker_quotes_router = APIRouter(prefix="/stocks", tags=["broker_quotes"])

_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
# Auto-refresh threshold — if the newest persisted quote is older than this
# we re-fetch on page load. Long enough that opening 10 tabs doesn't hammer
# Capital.com; short enough that the user sees a live-looking price.
_AUTO_REFRESH_AGE = timedelta(minutes=5)


def _serialize_quote(row: "StockCurQuote", broker_name: Optional[str] = None) -> dict:
    """Serialize a StockCurQuote row.

    Renames broker_change_* → change_* in the API response since clients
    expect change_abs / change_pct field names.
    """
    return {
        "broker_id": row.broker_id,
        "broker_name": broker_name,
        "broker_symbol": row.broker_symbol,
        "bid": str(row.bid) if row.bid is not None else None,
        "offer": str(row.offer) if row.offer is not None else None,
        "last_price": str(row.last_price) if row.last_price is not None else None,
        "open_price": str(row.open_price) if row.open_price is not None else None,
        "high_price": str(row.high_price) if row.high_price is not None else None,
        "low_price": str(row.low_price) if row.low_price is not None else None,
        "close_price": str(row.close_price) if row.close_price is not None else None,
        "change_abs": str(row.broker_change_abs) if row.broker_change_abs is not None else None,
        "change_pct": str(row.broker_change_pct) if row.broker_change_pct is not None else None,
        "volume": str(row.volume) if row.volume is not None else None,
        "currency": row.currency,
        "market_status": row.market_status,
        "fetched_at": row.fetched_at,
    }


@broker_quotes_router.get("/{stock_id}/broker_quotes")
async def list_broker_quotes(
    stock_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All persisted broker quotes for a stock (newest per broker).

    Auto-refresh: if any tradeable broker mapping has no persisted quote OR
    the quote is older than _AUTO_REFRESH_AGE, fetch fresh quotes through
    the gateway (which has its own cached adapter session) before returning.
    That way the stock detail page always shows a live-looking price even
    when the hourly job is broken — at the cost of one Capital.com call
    per stale mapping per page load.
    """
    if db.get(Stock, stock_id) is None:
        raise HTTPException(404, "Stock not found")

    # Decide which mappings need refreshing
    mappings = db.execute(
        select(BrokerInstrument)
        .where(BrokerInstrument.stock_id == stock_id,
               BrokerInstrument.is_tradeable.is_(True),
               BrokerInstrument.broker_symbol.is_not(None))
    ).scalars().all()

    if mappings:
        now = datetime.utcnow()
        threshold = now - _AUTO_REFRESH_AGE
        latest_by_broker = {
            r.broker_id: r.fetched_at for r in db.execute(
                select(StockCurQuote).where(StockCurQuote.stock_id == stock_id)
            ).scalars().all()
        }
        for m in mappings:
            last = latest_by_broker.get(m.broker_id)
            if last is None or last < threshold:
                # Fire and forget per-mapping refresh. Errors from the gateway
                # (broker down, symbol unmapped, auth issue) come back as None
                # and we just fall through to whatever's in stock_cur_quote.
                try:
                    await _refresh_one(db, stock_id, m.broker_id, m.broker_symbol)
                except Exception:
                    pass

    rows = db.execute(
        select(StockCurQuote, Broker.name, Broker.code)
        .join(Broker, StockCurQuote.broker_id == Broker.id)
        .where(StockCurQuote.stock_id == stock_id)
        .order_by(StockCurQuote.fetched_at.desc())
    ).all()
    return [{**_serialize_quote(r, name), "broker_code": code} for (r, name, code) in rows]


async def _refresh_one(db: Session, stock_id: int, broker_id: int, broker_symbol: str) -> Optional[dict]:
    """Hit the gateway, persist the result, return the saved row as dict.

    Returns None on broker failures so the caller can decide what to do.
    
        Writes to THREE tables in order:
        1. stock_cur_quote      — per-broker live quote (one row per
                                  stock×broker pair, full bid/offer/OHLC).
        2. stock_history_quote  — today's OHLC row (one row per
                                  stock×trading_date). Without this, the
                                  6-month chart freezes for broker-mapped
                                  stocks since the scrape pipeline skips
                                  them on purpose.
        3. stock_quotes         — canonical "now" cache (one row per stock).

    We compute prev_close BEFORE writing today's history row, otherwise the
    history UPSERT would shift the "second-most-recent close" lookup to
    today + today and prev_close would equal current price.
    """
    
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{_GATEWAY_URL}/brokers/{broker_id}/quote/{broker_symbol}")
            if r.status_code >= 400:
                return None
            payload = r.json()
    except httpx.RequestError:
        return None

    def _dec(k):
        v = payload.get(k)
        return Decimal(str(v)) if v is not None else None
        
    now = datetime.utcnow()
    today = date.today()
    last_price = _dec("last_price")

    # Write live quote into stock_cur_quote.
    # The broker's reported change_abs/change_pct often disagree with
    # prev-close-based change — store them under broker_change_* and never
    # use them as canonical.
    cur_quote_values = {
        "stock_id": stock_id, "broker_id": broker_id, "broker_symbol": broker_symbol,
        "bid": _dec("bid"), "offer": _dec("offer"),
        "last_price": last_price,
        "open_price": _dec("open_price"), "high_price": _dec("high_price"),
        "low_price": _dec("low_price"), "close_price": _dec("close_price"),
        "broker_change_abs": _dec("change_abs"),
        "broker_change_pct": _dec("change_pct"),
        "volume": _dec("volume"), "currency": payload.get("currency"),
        "market_status": payload.get("market_status"),
        "fetched_at": now,
    }
    cq_stmt = pg_insert(StockCurQuote).values(**cur_quote_values).on_conflict_do_update(
        index_elements=["stock_id", "broker_id"],
        set_={k: v for k, v in cur_quote_values.items()
              if k not in ("stock_id", "broker_id", "broker_symbol")},
    )
    db.execute(cq_stmt)

    # Nothing else to do without a price. Commit the cur_quote upsert so the
    # bid/offer/etc are still persisted, and bail out — change calcs depend
    # on last_price being non-null.
    if last_price is None:
        db.commit()
        return payload

    # ---------------------------------------------------------------
    # 2) prev_close lookup — BEFORE writing today's history row so we don't
    #    pollute the result. We want the most-recent close on a DIFFERENT
    #    trading day from today.
    # ---------------------------------------------------------------
    prev_close_row = db.execute(
        select(StockHistoryQuote.close_price)
        .where(StockHistoryQuote.stock_id == stock_id,
               StockHistoryQuote.close_price.is_not(None),
               StockHistoryQuote.trading_date < today)
        .order_by(StockHistoryQuote.trading_date.desc())
        .limit(1)
    ).first()
    prev_close = prev_close_row.close_price if prev_close_row else None

    change_abs = change_pct = None
    if prev_close is not None and prev_close != 0:
        change_abs = last_price - prev_close
        change_pct = (change_abs / prev_close) * 100

    # ---------------------------------------------------------------
    # 3) stock_history_quote — today's OHLC row (UNIQUE on stock_id,
    #    trading_date so re-running during the day updates in place).
    # ---------------------------------------------------------------
    # OHLC comes from the broker if reported, otherwise we fall back to
    # last_price for all four. The change_pct uses our prev-close-based
    # calc, not the broker's (consistent with stock_quotes).
    open_price = _dec("open_price") or last_price
    high_price = _dec("high_price") or last_price
    low_price = _dec("low_price") or last_price
    # close_price is intentionally last_price (intraday: rolling close;
    # post-close: the real close once the broker reports it).
    hist_values = {
        "stock_id": stock_id,
        "trading_date": today,
        "open_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "close_price": last_price,
        "volume": _dec("volume"),
        "change_pct": change_pct,
        "source": "broker",
        "scraped_at": now,
    }
    # Strip None values from the SET clause so a missing field doesn't blow
    # away a previously-good value from earlier in the day.
    hist_stmt = pg_insert(StockHistoryQuote).values(**hist_values).on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: v for k, v in hist_values.items()
              if k not in ("stock_id", "trading_date") and v is not None},
    )
    db.execute(hist_stmt)

    # ---------------------------------------------------------------
    # 4) stock_quotes — canonical "now" row. Refresh price block only;
    #    composite_score / verdict / pe_ratio etc are owned by other writers.
    # ---------------------------------------------------------------
    sq_record = {
        "stock_id": stock_id,
        "current_price": last_price,
        "prev_close": prev_close,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "price_source": "broker",
        "price_fetched_at": now,
        "last_updated": now,
    }
    sq_stmt = pg_insert(StockQuote).values(**sq_record).on_conflict_do_update(
        index_elements=["stock_id"],
        set_={k: v for k, v in sq_record.items() if k != "stock_id"},
    )
    db.execute(sq_stmt)

    db.commit()
    return payload


@broker_quotes_router.post("/{stock_id}/broker_quotes/refresh")
async def refresh_broker_quotes(
    stock_id: int,
    broker_id: Optional[int] = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually refresh broker quotes for a stock.

    With ?broker_id=N, only that broker. Otherwise every broker that has a
    tradeable mapping for this stock.
    """
    if db.get(Stock, stock_id) is None:
        raise HTTPException(404, "Stock not found")
    q = (
        select(BrokerInstrument)
        .where(BrokerInstrument.stock_id == stock_id,
               BrokerInstrument.is_tradeable.is_(True))
    )
    if broker_id is not None:
        q = q.where(BrokerInstrument.broker_id == broker_id)
    mappings = db.execute(q).scalars().all()
    if not mappings:
        raise HTTPException(409, "No broker mapping for this stock")

    refreshed = []
    failed = []
    for m in mappings:
        result = await _refresh_one(db, stock_id, m.broker_id, m.broker_symbol)
        if result is None:
            failed.append({"broker_id": m.broker_id, "broker_symbol": m.broker_symbol})
        else:
            refreshed.append({"broker_id": m.broker_id, "broker_symbol": m.broker_symbol})

    return {"refreshed": refreshed, "failed": failed}


# ----------------------------------------------------------------------------
# Bars endpoint — for the on-demand live chart at /stock/.../chart.
# Resolves the stock's broker mapping, then proxies to broker_gateway's
# /brokers/{id}/bars. Pure pass-through — nothing persisted.
# ----------------------------------------------------------------------------
@broker_quotes_router.get("/{stock_id}/bars")
async def stock_bars(
    stock_id: int,
    resolution: str = "MINUTE_5",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    max_bars: int = 200,
    broker_id: Optional[int] = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historical bars for charting. Requires a broker mapping.

    If the stock has mappings on multiple brokers and the caller didn't pin
    one, we pick the first tradeable one. 409 if no mapping exists.
    """
    stock_row = db.get(Stock, stock_id)
    if stock_row is None:
        # Be specific in the error — caller may be hitting this with a stale
        # ID from a cached SWR response. Frontend should reload.
        raise HTTPException(404, f"Stock id={stock_id} not found in database")

    q = select(BrokerInstrument).where(
        BrokerInstrument.stock_id == stock_id,
        BrokerInstrument.is_tradeable.is_(True),
        BrokerInstrument.broker_symbol.is_not(None),
    )
    if broker_id is not None:
        q = q.where(BrokerInstrument.broker_id == broker_id)
    mapping = db.execute(q.limit(1)).scalar_one_or_none()
    if mapping is None:
        # Distinguish the two failure modes the user actually cares about:
        # (a) the stock has no broker mapping at all → user needs to "Map symbol"
        # (b) the stock IS mapped but to a different broker than requested
        if broker_id is not None:
            any_mapping = db.execute(
                select(BrokerInstrument).where(
                    BrokerInstrument.stock_id == stock_id,
                    BrokerInstrument.is_tradeable.is_(True),
                    BrokerInstrument.broker_symbol.is_not(None),
                ).limit(1)
            ).scalar_one_or_none()
            if any_mapping is not None:
                raise HTTPException(
                    409,
                    f"{stock_row.ticker} has no tradeable mapping on broker_id={broker_id}. "
                    f"It is mapped to broker_id={any_mapping.broker_id} ({any_mapping.broker_symbol}).",
                )
        raise HTTPException(
            409,
            f"No tradeable broker mapping for {stock_row.ticker}. "
            f"Map this stock to a broker first under 'Map symbol'.",
        )

    params = {
        "symbol": mapping.broker_symbol,
        "resolution": resolution,
        "max_bars": str(max_bars),
    }
    if from_ts:
        params["from_ts"] = from_ts
    if to_ts:
        params["to_ts"] = to_ts

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(
                f"{_GATEWAY_URL}/brokers/{mapping.broker_id}/bars",
                params=params,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                502,
                f"broker_gateway unreachable: {type(exc).__name__}: {exc}",
            )
        if r.status_code >= 400:
            # Pass the gateway's error verbatim so we can see "endpoint missing"
            # vs "auth failed" vs "broker rate-limited".
            raise HTTPException(
                r.status_code,
                f"broker_gateway returned {r.status_code}: {r.text[:300]}",
            )
        return r.json()
