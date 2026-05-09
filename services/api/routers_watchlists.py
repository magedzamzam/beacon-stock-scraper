"""/watchlists/* — user watchlists."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db import (
    Exchange, Stock, StockQuote, User, Watchlist, WatchlistItem,
)
from .auth import get_current_user, get_db
from .schemas import (
    StockSummary, WatchlistAddItemRequest, WatchlistCreateRequest,
    WatchlistItemOut, WatchlistOut,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _stock_summary(db: Session, stock_id: int) -> StockSummary:
    # Round 3: read from stock_quotes (canonical row). API field names
    # last_close/last_change_pct preserved for client compat.
    row = db.execute(
        select(
            Stock.id, Stock.ticker, Stock.company_name, Stock.sector, Stock.industry,
            Stock.country, Stock.currency,
            Exchange.code.label("exchange_code"),
            StockQuote.current_price, StockQuote.change_pct,
            StockQuote.market_cap, StockQuote.pe_ratio,
            StockQuote.dividend_yield_pct, StockQuote.rsi_14,
            StockQuote.composite_score, StockQuote.verdict,
            StockQuote.last_updated,
        )
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .outerjoin(StockQuote, StockQuote.stock_id == Stock.id)
        .where(Stock.id == stock_id)
    ).first()
    if not row:
        raise HTTPException(404, "Stock not found")
    return StockSummary(
        id=row.id, ticker=row.ticker, exchange_code=row.exchange_code,
        company_name=row.company_name, sector=row.sector, industry=row.industry,
        country=row.country, currency=row.currency,
        last_close=_f(row.current_price), last_change_pct=_f(row.change_pct),
        market_cap=_f(row.market_cap), pe_ratio=_f(row.pe_ratio),
        dividend_yield_pct=_f(row.dividend_yield_pct), rsi_14=_f(row.rsi_14),
        composite_score=_f(row.composite_score), verdict=row.verdict,
        last_updated=row.last_updated,
    )


def _serialize_wl(db: Session, wl: Watchlist) -> WatchlistOut:
    items = db.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)
        .order_by(WatchlistItem.added_at.desc())
    ).scalars().all()
    return WatchlistOut(
        id=wl.id, name=wl.name, created_at=wl.created_at,
        items=[
            WatchlistItemOut(
                id=i.id, note=i.note, added_at=i.added_at,
                stock=_stock_summary(db, i.stock_id),
            )
            for i in items
        ],
    )


@router.get("", response_model=list[WatchlistOut])
def list_watchlists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wls = db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at)
    ).scalars().all()
    return [_serialize_wl(db, w) for w in wls]


@router.post("", response_model=WatchlistOut)
def create_watchlist(
    req: WatchlistCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.name == req.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A watchlist with that name already exists")
    wl = Watchlist(user_id=user.id, name=req.name)
    db.add(wl); db.commit(); db.refresh(wl)
    return _serialize_wl(db, wl)


@router.delete("/{wl_id}", status_code=204)
def delete_watchlist(
    wl_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = db.get(Watchlist, wl_id)
    if not wl or wl.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(wl); db.commit()


@router.post("/{wl_id}/items", response_model=WatchlistItemOut)
def add_item(
    wl_id: int, req: WatchlistAddItemRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = db.get(Watchlist, wl_id)
    if not wl or wl.user_id != user.id:
        raise HTTPException(404, "Watchlist not found")
    if not db.get(Stock, req.stock_id):
        raise HTTPException(404, "Stock not found")
    existing = db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl_id,
            WatchlistItem.stock_id == req.stock_id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Stock already in this watchlist")
    item = WatchlistItem(watchlist_id=wl_id, stock_id=req.stock_id, note=req.note)
    db.add(item); db.commit(); db.refresh(item)
    return WatchlistItemOut(
        id=item.id, note=item.note, added_at=item.added_at,
        stock=_stock_summary(db, item.stock_id),
    )


@router.delete("/{wl_id}/items/{item_id}", status_code=204)
def remove_item(
    wl_id: int, item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = db.get(Watchlist, wl_id)
    if not wl or wl.user_id != user.id:
        raise HTTPException(404, "Watchlist not found")
    item = db.get(WatchlistItem, item_id)
    if not item or item.watchlist_id != wl_id:
        raise HTTPException(404, "Item not found")
    db.delete(item); db.commit()
