"""Live broker quotes for stocks that have a broker_instruments mapping.

Endpoints:
    GET  /stocks/{stock_id}/broker_quotes        list all latest quotes
    POST /stocks/{stock_id}/broker_quotes/refresh refresh one or all (manual)

The hourly periodic refresh lives in the scheduler.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    Broker, BrokerInstrument, Stock, StockBrokerQuote, User,
    # Round-2 dual-write targets:
    StockCurQuote, StockHistoryQuote, StockQuote,
)

from .auth import get_current_user, get_db


broker_quotes_router = APIRouter(prefix="/stocks", tags=["broker_quotes"])

_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")


def _serialize_quote(row, broker_name: Optional[str] = None) -> dict:
    """Serialize a quote row. Accepts either StockCurQuote (Round-3 reads) or
    StockBrokerQuote (legacy). The broker change fields are renamed on
    StockCurQuote to broker_change_*; the API still returns change_abs / change_pct
    for client compat (those names are baked into frontend types).
    """
    # StockCurQuote uses broker_change_*; StockBrokerQuote uses change_*.
    # Use getattr so we work with either model.
    change_abs = getattr(row, "broker_change_abs", None)
    if change_abs is None:
        change_abs = getattr(row, "change_abs", None)
    change_pct = getattr(row, "broker_change_pct", None)
    if change_pct is None:
        change_pct = getattr(row, "change_pct", None)
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
        "change_abs": str(change_abs) if change_abs is not None else None,
        "change_pct": str(change_pct) if change_pct is not None else None,
        "volume": str(row.volume) if row.volume is not None else None,
        "currency": row.currency,
        "market_status": row.market_status,
        "fetched_at": row.fetched_at,
    }


@broker_quotes_router.get("/{stock_id}/broker_quotes")
def list_broker_quotes(
    stock_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All persisted broker quotes for a stock (newest per broker).

    Round 3: reads from stock_cur_quote (parallel table).
    """
    if db.get(Stock, stock_id) is None:
        raise HTTPException(404, "Stock not found")
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

    values = {
        "stock_id": stock_id, "broker_id": broker_id,
        "broker_symbol": broker_symbol,
        "bid": _dec("bid"), "offer": _dec("offer"),
        "last_price": _dec("last_price"),
        "open_price": _dec("open_price"),
        "high_price": _dec("high_price"),
        "low_price": _dec("low_price"),
        "close_price": _dec("close_price"),
        "change_abs": _dec("change_abs"),
        "change_pct": _dec("change_pct"),
        "volume": _dec("volume"),
        "currency": payload.get("currency"),
        "market_status": payload.get("market_status"),
        "fetched_at": datetime.utcnow(),
    }
    stmt = pg_insert(StockBrokerQuote).values(**values).on_conflict_do_update(
        index_elements=["stock_id", "broker_id"],
        set_={k: v for k, v in values.items() if k not in ("stock_id", "broker_id", "broker_symbol")},
    )
    db.execute(stmt)

    # Round-2 dual-write: same payload into stock_cur_quote.
    # change_abs/change_pct on the broker quote are renamed to broker_change_*
    # since they often disagree with prev-close-based change.
    cur_quote_values = {
        "stock_id": stock_id, "broker_id": broker_id, "broker_symbol": broker_symbol,
        "bid": values["bid"], "offer": values["offer"],
        "last_price": values["last_price"],
        "open_price": values["open_price"], "high_price": values["high_price"],
        "low_price": values["low_price"], "close_price": values["close_price"],
        "broker_change_abs": values["change_abs"],
        "broker_change_pct": values["change_pct"],
        "volume": values["volume"], "currency": values["currency"],
        "market_status": values["market_status"], "fetched_at": values["fetched_at"],
    }
    cq_stmt = pg_insert(StockCurQuote).values(**cur_quote_values).on_conflict_do_update(
        index_elements=["stock_id", "broker_id"],
        set_={k: v for k, v in cur_quote_values.items()
              if k not in ("stock_id", "broker_id", "broker_symbol")},
    )
    db.execute(cq_stmt)

    # Round-2 dual-write: refresh canonical stock_quotes row with broker price.
    # We update only the price block; preserve composite_score/verdict.
    last_price = values["last_price"]
    if last_price is not None:
        # prev_close from history (second-most-recent close)
        hist = db.execute(
            select(StockHistoryQuote.close_price)
            .where(StockHistoryQuote.stock_id == stock_id,
                   StockHistoryQuote.close_price.is_not(None))
            .order_by(StockHistoryQuote.trading_date.desc()).limit(2)
        ).all()
        prev_close = hist[1].close_price if len(hist) >= 2 else None
        change_abs = change_pct = None
        if prev_close is not None and prev_close != 0:
            change_abs = last_price - prev_close
            change_pct = (change_abs / prev_close) * 100
        sq_record = {
            "stock_id": stock_id,
            "current_price": last_price,
            "prev_close": prev_close,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "price_source": "broker",
            "price_fetched_at": values["fetched_at"],
            "last_updated": datetime.utcnow(),
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
