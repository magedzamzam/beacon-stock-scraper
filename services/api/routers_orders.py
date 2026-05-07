"""/orders, /accounts/{id}/positions, /instruments routers.

Orders flow:
  Manual account   -> we write directly to broker_orders.
  Automated account -> we forward to broker_gateway, which writes to broker_orders.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    Broker, BrokerInstrument, BrokerOrder as BrokerOrderRow,
    BrokerPositionSnapshot, Exchange, Stock, TradingAccount, User,
)
from .auth import get_current_user, get_db


_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
_POSITION_TTL_S = int(os.environ.get("BROKER_POSITION_TTL_S", "60"))


# =============================================================================
# Orders
# =============================================================================
orders_router = APIRouter(prefix="/orders", tags=["orders"])


class PlaceOrderIn(BaseModel):
    account_id: int
    stock_id: Optional[int] = None
    broker_symbol: Optional[str] = None
    side: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field(..., pattern="^(MARKET|LIMIT|STOP)$")
    quantity: Decimal = Field(..., gt=0)
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    notes: Optional[str] = None


def _resolve_broker_symbol(db: Session, account: TradingAccount,
                           stock_id: Optional[int],
                           explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    if stock_id is None:
        return None
    bi = db.execute(
        select(BrokerInstrument)
        .where(BrokerInstrument.broker_id == account.broker_id,
               BrokerInstrument.stock_id == stock_id,
               BrokerInstrument.is_tradeable.is_(True))
        .limit(1)
    ).scalar_one_or_none()
    return bi.broker_symbol if bi else None


@orders_router.post("")
async def place_order(
    body: PlaceOrderIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(TradingAccount, body.account_id)
    if acct is None or acct.user_id != user.id or not acct.is_active:
        raise HTTPException(404, "Account not found")
    broker = db.get(Broker, acct.broker_id)
    if broker is None:
        raise HTTPException(409, "Broker missing")

    broker_symbol = _resolve_broker_symbol(db, acct, body.stock_id, body.broker_symbol)
    if broker.kind == "automated" and not broker_symbol:
        raise HTTPException(
            409,
            "This stock isn't mapped to a broker symbol on this account. "
            "Ask an admin to map it, or pick a different account."
        )

    if broker.kind == "manual":
        if body.order_type != "MARKET" and body.limit_price is None:
            raise HTTPException(400, "limit_price is required for LIMIT/STOP orders")
        if not broker_symbol and not body.stock_id:
            raise HTTPException(400, "Provide either stock_id or broker_symbol")
        row = BrokerOrderRow(
            account_id=acct.id, user_id=user.id, stock_id=body.stock_id,
            broker_symbol=broker_symbol or "", side=body.side, order_type=body.order_type,
            quantity=body.quantity, limit_price=body.limit_price,
            stop_loss=body.stop_loss, take_profit=body.take_profit,
            currency=acct.currency, status="FILLED",
            fill_price=body.limit_price, fill_quantity=body.quantity,
            placed_at=datetime.utcnow(), filled_at=datetime.utcnow(),
            notes=body.notes,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "status": row.status, "manual": True}

    payload = {
        "broker_symbol": broker_symbol,
        "side": body.side, "order_type": body.order_type,
        "quantity": str(body.quantity),
        "limit_price": str(body.limit_price) if body.limit_price else None,
        "stop_loss": str(body.stop_loss) if body.stop_loss else None,
        "take_profit": str(body.take_profit) if body.take_profit else None,
        "user_id": user.id, "stock_id": body.stock_id, "notes": body.notes,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_GATEWAY_URL}/accounts/{acct.id}/orders", json=payload)
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"broker_gateway unreachable: {e}")


@orders_router.get("")
def list_orders(
    account_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(BrokerOrderRow).where(BrokerOrderRow.user_id == user.id)
    if account_id is not None:
        q = q.where(BrokerOrderRow.account_id == account_id)
    q = q.order_by(desc(BrokerOrderRow.placed_at)).limit(limit)
    rows = db.execute(q).scalars().all()
    return [{
        "id": r.id, "account_id": r.account_id, "stock_id": r.stock_id,
        "broker_symbol": r.broker_symbol, "side": r.side, "order_type": r.order_type,
        "quantity": str(r.quantity),
        "limit_price": str(r.limit_price) if r.limit_price is not None else None,
        "stop_loss": str(r.stop_loss) if r.stop_loss is not None else None,
        "take_profit": str(r.take_profit) if r.take_profit is not None else None,
        "currency": r.currency, "broker_order_ref": r.broker_order_ref,
        "status": r.status,
        "fill_price": str(r.fill_price) if r.fill_price is not None else None,
        "fill_quantity": str(r.fill_quantity) if r.fill_quantity is not None else None,
        "rejection_reason": r.rejection_reason,
        "placed_at": r.placed_at, "filled_at": r.filled_at, "notes": r.notes,
    } for r in rows]


@orders_router.delete("/{order_id}")
async def cancel_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(BrokerOrderRow, order_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Order not found")
    if row.status not in ("PENDING", "WORKING"):
        raise HTTPException(400, f"Cannot cancel order in status {row.status}")
    if not row.broker_order_ref:
        row.status = "CANCELLED"
        db.commit()
        return {"cancelled": True, "manual": True}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{_GATEWAY_URL}/accounts/{row.account_id}/orders/{row.broker_order_ref}")
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"broker_gateway unreachable: {e}")


# =============================================================================
# Live positions per account
# =============================================================================
positions_router = APIRouter(prefix="/accounts", tags=["accounts"])


@positions_router.get("/{account_id}/positions")
async def get_positions(
    account_id: int,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    broker = db.get(Broker, acct.broker_id)

    if broker.kind == "manual":
        from shared.db import PortfolioPosition
        rows = db.execute(
            select(PortfolioPosition, Stock, Exchange)
            .join(Stock, PortfolioPosition.stock_id == Stock.id)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(PortfolioPosition.account_id == account_id, PortfolioPosition.is_open.is_(True))
        ).all()
        return [{
            "source": "manual",
            "stock_id": s.id, "ticker": s.ticker, "exchange": e.code,
            "company_name": s.company_name, "currency": s.currency,
            "quantity": str(p.quantity), "avg_open_price": str(p.avg_entry_price),
            "broker_symbol": s.ticker,
        } for (p, s, e) in rows]

    needs_refresh = refresh
    if not needs_refresh:
        latest = db.execute(
            select(BrokerPositionSnapshot.fetched_at)
            .where(BrokerPositionSnapshot.account_id == account_id)
            .order_by(desc(BrokerPositionSnapshot.fetched_at)).limit(1)
        ).scalar_one_or_none()
        if latest is None:
            needs_refresh = True
        else:
            age = (datetime.utcnow() - latest).total_seconds()
            if age > _POSITION_TTL_S:
                needs_refresh = True

    if needs_refresh:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                await client.get(f"{_GATEWAY_URL}/accounts/{account_id}/positions")
        except httpx.RequestError:
            pass

    rows = db.execute(
        select(BrokerPositionSnapshot, Stock, Exchange)
        .outerjoin(Stock, BrokerPositionSnapshot.stock_id == Stock.id)
        .outerjoin(Exchange, Stock.exchange_id == Exchange.id)
        .where(BrokerPositionSnapshot.account_id == account_id)
        .order_by(BrokerPositionSnapshot.broker_symbol)
    ).all()
    return [{
        "source": "broker",
        "stock_id": (s.id if s else None),
        "ticker": (s.ticker if s else None),
        "exchange": (e.code if e else None),
        "company_name": (s.company_name if s else None),
        "broker_symbol": p.broker_symbol,
        "quantity": str(p.quantity),
        "avg_open_price": str(p.avg_open_price) if p.avg_open_price else None,
        "current_price": str(p.current_price) if p.current_price else None,
        "unrealized_pl": str(p.unrealized_pl) if p.unrealized_pl else None,
        "currency": p.currency, "direction": p.direction,
        "fetched_at": p.fetched_at,
    } for (p, s, e) in rows]


# =============================================================================
# Broker instruments (admin: map ticker -> broker symbol)
# =============================================================================
instruments_router = APIRouter(prefix="/instruments", tags=["instruments"])


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")


class InstrumentMapIn(BaseModel):
    broker_code: str
    broker_symbol: str = Field(..., min_length=1, max_length=64)
    stock_id: Optional[int] = None
    broker_name: Optional[str] = None
    instrument_type: Optional[str] = None
    currency: Optional[str] = None
    min_qty: Optional[Decimal] = None
    is_tradeable: bool = True


@instruments_router.get("/by-stock/{stock_id}")
def list_for_stock(stock_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    rows = db.execute(
        select(BrokerInstrument, Broker)
        .join(Broker, BrokerInstrument.broker_id == Broker.id)
        .where(BrokerInstrument.stock_id == stock_id, BrokerInstrument.is_tradeable.is_(True))
    ).all()
    return [{
        "broker_code": br.code, "broker_name": br.name,
        "broker_symbol": bi.broker_symbol,
        "instrument_type": bi.instrument_type, "currency": bi.currency,
        "min_qty": str(bi.min_qty) if bi.min_qty else None,
    } for (bi, br) in rows]


@instruments_router.post("")
def upsert_instrument(
    body: InstrumentMapIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    broker = db.execute(select(Broker).where(Broker.code == body.broker_code)).scalar_one_or_none()
    if broker is None:
        raise HTTPException(404, f"Unknown broker '{body.broker_code}'")
    if body.stock_id is not None:
        if db.get(Stock, body.stock_id) is None:
            raise HTTPException(404, "Unknown stock_id")

    stmt = pg_insert(BrokerInstrument).values(
        broker_id=broker.id, broker_symbol=body.broker_symbol,
        broker_name=body.broker_name, instrument_type=body.instrument_type,
        stock_id=body.stock_id, currency=body.currency, min_qty=body.min_qty,
        is_tradeable=body.is_tradeable,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["broker_id", "broker_symbol"],
        set_={
            "broker_name": stmt.excluded.broker_name,
            "instrument_type": stmt.excluded.instrument_type,
            "stock_id": stmt.excluded.stock_id,
            "currency": stmt.excluded.currency,
            "min_qty": stmt.excluded.min_qty,
            "is_tradeable": stmt.excluded.is_tradeable,
        },
    )
    db.execute(stmt)
    db.commit()
    return {"ok": True}


@instruments_router.delete("/{broker_code}/{broker_symbol}")
def delete_instrument(
    broker_code: str, broker_symbol: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    broker = db.execute(select(Broker).where(Broker.code == broker_code)).scalar_one_or_none()
    if broker is None:
        raise HTTPException(404, "Unknown broker")
    deleted = db.query(BrokerInstrument).filter(
        BrokerInstrument.broker_id == broker.id,
        BrokerInstrument.broker_symbol == broker_symbol,
    ).delete()
    db.commit()
    return {"deleted": deleted}


@instruments_router.get("/search/{broker_code}")
async def search_instruments(
    broker_code: str, q: str = Query(..., min_length=1, max_length=64),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_admin(user)
    broker = db.execute(select(Broker).where(Broker.code == broker_code)).scalar_one_or_none()
    if broker is None:
        raise HTTPException(404, "Unknown broker")
    if broker.kind != "automated":
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{_GATEWAY_URL}/brokers/{broker.id}/search", params={"q": q})
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"broker_gateway unreachable: {e}")
