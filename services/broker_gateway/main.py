"""broker_gateway — only service that decrypts broker credentials and talks to broker APIs."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from shared.db import (
    Broker, BrokerInstrument, BrokerOrder as BrokerOrderRow,
    BrokerPositionSnapshot, SessionLocal, TradingAccount,
)
from brokers.adapter_base import BrokerAdapter
from brokers.crypto import decrypt_credentials, CryptoIntegrityError, CryptoConfigError
from brokers.registry import get_adapter_class
from brokers.types import (
    AuthError, BrokerError, NetworkError, NotFoundError, OrderSide, OrderStatus,
    OrderType, PlaceOrderRequest, RateLimitError,
)


log = logging.getLogger("broker_gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Beacon Broker Gateway", version="1.0.0")


def _build_adapter(account_id: int) -> tuple[TradingAccount, Broker, BrokerAdapter]:
    with SessionLocal() as session:
        acct = session.get(TradingAccount, account_id)
        if acct is None or not acct.is_active:
            raise HTTPException(404, "Trading account not found")
        broker = session.get(Broker, acct.broker_id)
        if broker is None or not broker.is_enabled:
            raise HTTPException(409, "Broker is disabled")
        try:
            creds = decrypt_credentials(acct.credentials_encrypted, acct.credentials_nonce)
        except CryptoIntegrityError as e:
            raise HTTPException(500, f"Credential decryption failed: {e}")
        except CryptoConfigError as e:
            raise HTTPException(500, str(e))
        adapter_cls = get_adapter_class(broker.adapter_class)
        adapter = adapter_cls(
            credentials=creds,
            display_metadata=acct.display_metadata or {},
            base_url=broker.base_url,
        )
        return acct, broker, adapter


def _broker_error_to_status(exc: BrokerError) -> int:
    if isinstance(exc, AuthError):
        return 401
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, RateLimitError):
        return 429
    if isinstance(exc, NetworkError):
        return 502
    return 500


def _record_connect_status(account_id: int, ok: bool, message: Optional[str]) -> None:
    with SessionLocal() as session:
        acct = session.get(TradingAccount, account_id)
        if acct is None:
            return
        acct.last_connect_status = "ok" if ok else "error"
        acct.last_connect_error = None if ok else (message or "unknown")
        acct.last_connect_at = datetime.utcnow()
        session.commit()


class PlaceOrderIn(BaseModel):
    broker_symbol: str = Field(..., min_length=1, max_length=64)
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0)
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    user_id: int
    stock_id: Optional[int] = None
    notes: Optional[str] = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/accounts/{account_id}/test")
async def test_connection(account_id: int):
    _, _, adapter = _build_adapter(account_id)
    try:
        result = await adapter.healthcheck()
        _record_connect_status(account_id, ok=bool(result.get("ok")), message=result.get("message"))
        return result
    finally:
        await adapter.aclose()


@app.get("/accounts/{account_id}/info")
async def account_info(account_id: int):
    _, _, adapter = _build_adapter(account_id)
    try:
        info = await adapter.get_account_info()
        _record_connect_status(account_id, ok=True, message=None)
        return {
            "account_id": info.account_id,
            "balance": str(info.balance) if info.balance is not None else None,
            "available": str(info.available) if info.available is not None else None,
            "currency": info.currency,
        }
    except BrokerError as exc:
        _record_connect_status(account_id, ok=False, message=str(exc))
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


@app.get("/accounts/{account_id}/positions")
async def list_positions(account_id: int):
    acct, _, adapter = _build_adapter(account_id)
    try:
        positions = await adapter.list_positions()
    except BrokerError as exc:
        _record_connect_status(account_id, ok=False, message=str(exc))
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()

    with SessionLocal() as session:
        session.query(BrokerPositionSnapshot).filter(
            BrokerPositionSnapshot.account_id == account_id
        ).delete()
        for p in positions:
            mapping = session.execute(
                select(BrokerInstrument.stock_id)
                .where(BrokerInstrument.broker_id == acct.broker_id,
                       BrokerInstrument.broker_symbol == p.broker_symbol)
            ).scalar_one_or_none()
            session.add(BrokerPositionSnapshot(
                account_id=account_id, stock_id=mapping,
                broker_symbol=p.broker_symbol, quantity=p.quantity,
                avg_open_price=p.avg_open_price, current_price=p.current_price,
                unrealized_pl=p.unrealized_pl, unrealized_pl_pct=p.unrealized_pl_pct,
                currency=p.currency, direction=p.direction.value, raw=p.raw,
                fetched_at=datetime.utcnow(),
            ))
        session.commit()
        _record_connect_status(account_id, ok=True, message=None)

    return [{
        "broker_symbol": p.broker_symbol, "quantity": str(p.quantity),
        "avg_open_price": str(p.avg_open_price) if p.avg_open_price else None,
        "current_price": str(p.current_price) if p.current_price else None,
        "unrealized_pl": str(p.unrealized_pl) if p.unrealized_pl else None,
        "currency": p.currency, "direction": p.direction.value,
    } for p in positions]


@app.get("/accounts/{account_id}/orders")
async def list_orders(account_id: int):
    _, _, adapter = _build_adapter(account_id)
    try:
        orders = await adapter.list_orders()
        return [{
            "broker_order_ref": o.broker_order_ref,
            "broker_symbol": o.broker_symbol,
            "side": o.side.value, "order_type": o.order_type.value,
            "quantity": str(o.quantity),
            "limit_price": str(o.limit_price) if o.limit_price else None,
            "stop_loss": str(o.stop_loss) if o.stop_loss else None,
            "take_profit": str(o.take_profit) if o.take_profit else None,
            "status": o.status.value, "currency": o.currency,
        } for o in orders]
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


@app.post("/accounts/{account_id}/orders")
async def place_order(account_id: int, body: PlaceOrderIn):
    acct, _, adapter = _build_adapter(account_id)
    req = PlaceOrderRequest(
        broker_symbol=body.broker_symbol, side=body.side, order_type=body.order_type,
        quantity=body.quantity, limit_price=body.limit_price,
        stop_loss=body.stop_loss, take_profit=body.take_profit,
    )
    try:
        result = await adapter.place_order(req)
    except BrokerError as exc:
        with SessionLocal() as session:
            session.add(BrokerOrderRow(
                account_id=account_id, user_id=body.user_id, stock_id=body.stock_id,
                broker_symbol=body.broker_symbol, side=body.side.value,
                order_type=body.order_type.value, quantity=body.quantity,
                limit_price=body.limit_price, stop_loss=body.stop_loss,
                take_profit=body.take_profit, status=OrderStatus.REJECTED.value,
                rejection_reason=str(exc), notes=body.notes,
            ))
            session.commit()
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()

    with SessionLocal() as session:
        row = BrokerOrderRow(
            account_id=account_id, user_id=body.user_id, stock_id=body.stock_id,
            broker_symbol=result.broker_symbol, side=result.side.value,
            order_type=result.order_type.value, quantity=result.quantity,
            limit_price=result.limit_price, stop_loss=result.stop_loss,
            take_profit=result.take_profit, currency=result.currency,
            broker_order_ref=result.broker_order_ref, status=result.status.value,
            fill_price=result.fill_price, fill_quantity=result.fill_quantity,
            placed_at=datetime.utcnow(),
            filled_at=datetime.utcnow() if result.status == OrderStatus.FILLED else None,
            last_synced_at=datetime.utcnow(), notes=body.notes,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        order_id = row.id

    return {
        "id": order_id, "broker_order_ref": result.broker_order_ref,
        "status": result.status.value,
        "fill_price": str(result.fill_price) if result.fill_price else None,
    }


@app.delete("/accounts/{account_id}/orders/{ref}")
async def cancel_order(account_id: int, ref: str):
    _, _, adapter = _build_adapter(account_id)
    try:
        ok = await adapter.cancel_order(ref)
        with SessionLocal() as session:
            row = session.execute(
                select(BrokerOrderRow).where(BrokerOrderRow.broker_order_ref == ref)
            ).scalar_one_or_none()
            if row is not None and ok:
                row.status = OrderStatus.CANCELLED.value
                row.last_synced_at = datetime.utcnow()
                session.commit()
        return {"cancelled": ok}
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


@app.get("/brokers/{broker_id}/search")
async def search_instruments(broker_id: int, q: str):
    if not q or len(q) < 1:
        raise HTTPException(400, "q is required")
    with SessionLocal() as session:
        acct = session.execute(
            select(TradingAccount)
            .where(TradingAccount.broker_id == broker_id, TradingAccount.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if acct is None:
            raise HTTPException(409, "No active account on this broker — connect one first")
    _, _, adapter = _build_adapter(acct.id)
    try:
        results = await adapter.search_instrument(q)
        return [{
            "broker_symbol": r.broker_symbol, "name": r.name,
            "instrument_type": r.instrument_type, "currency": r.currency,
            "min_qty": str(r.min_qty) if r.min_qty else None,
        } for r in results]
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()
