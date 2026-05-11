"""broker_gateway — only service that decrypts broker credentials and talks to broker APIs."""
from __future__ import annotations

import asyncio
import logging
import time
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


# ----------------------------------------------------------------------------
# Adapter session cache
# ----------------------------------------------------------------------------
# Capital.com sessions expire after 10 minutes of inactivity. Without caching,
# every /quote/... call constructs a fresh adapter -> POST /api/v1/session ->
# get one quote -> aclose(). Hammering /api/v1/session this way triggers
# 429 Too Many Requests from Capital.com's session endpoint.
#
# Strategy:
#   * Keep one adapter per account_id, alive for up to 8 minutes (under the
#     10-minute server-side TTL so we never race the expiry).
#   * Guard cache lookups with a per-key asyncio.Lock so simultaneous quote
#     requests on a cold cache only do ONE login.
#   * Invalidate on AuthError (server-side session was killed) so the next
#     call re-logs in.
#
# This is process-local. We run one broker_gateway container per environment,
# so there's no cross-worker coordination problem.
# ----------------------------------------------------------------------------

_ADAPTER_TTL_SECONDS = 8 * 60  # under Capital.com's 10-minute idle limit


class _CachedAdapter:
    __slots__ = ("account_id", "broker", "adapter", "expires_at", "lock")

    def __init__(self, account_id: int, broker: Broker, adapter: BrokerAdapter):
        self.account_id = account_id
        self.broker = broker
        self.adapter = adapter
        self.expires_at = time.monotonic() + _ADAPTER_TTL_SECONDS
        # Per-entry lock — concurrent batch requests on the SAME account
        # serialise through here. Different accounts run in parallel.
        self.lock = asyncio.Lock()

    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


_ADAPTER_CACHE: dict[int, _CachedAdapter] = {}
_CACHE_LOCK = asyncio.Lock()  # only guards cache-dict mutations, not adapter use


async def _get_cached_adapter(account_id: int) -> _CachedAdapter:
    """Return a cached adapter for this account, building one if missing/expired.

    On expiry we close the old client cleanly before replacing it.
    """
    async with _CACHE_LOCK:
        entry = _ADAPTER_CACHE.get(account_id)
        if entry is not None and not entry.expired():
            return entry
        # Discard stale entry (also close its client if present)
        if entry is not None:
            try:
                await entry.adapter.aclose()
            except Exception:
                pass
            _ADAPTER_CACHE.pop(account_id, None)

        # Build a fresh one
        _, broker, adapter = _build_adapter(account_id)
        entry = _CachedAdapter(account_id, broker, adapter)
        _ADAPTER_CACHE[account_id] = entry
        return entry


async def _invalidate_adapter(account_id: int) -> None:
    """Drop the cache entry — called on auth errors so the next call re-logs in."""
    async with _CACHE_LOCK:
        entry = _ADAPTER_CACHE.pop(account_id, None)
    if entry is not None:
        try:
            await entry.adapter.aclose()
        except Exception:
            pass


def _serialize_quote(q, broker_symbol: str) -> dict:
    """Common quote payload — used by single and batch endpoints."""
    return {
        "broker_symbol": getattr(q, "broker_symbol", broker_symbol),
        "bid": str(q.bid) if q.bid is not None else None,
        "offer": str(q.offer) if q.offer is not None else None,
        "last_price": str(q.last_price) if q.last_price is not None else None,
        "open_price": str(q.open_price) if q.open_price is not None else None,
        "high_price": str(q.high_price) if q.high_price is not None else None,
        "low_price": str(q.low_price) if q.low_price is not None else None,
        "close_price": str(q.close_price) if q.close_price is not None else None,
        "change_abs": str(q.change_abs) if q.change_abs is not None else None,
        "change_pct": str(q.change_pct) if q.change_pct is not None else None,
        "volume": str(q.volume) if q.volume is not None else None,
        "currency": q.currency,
        "market_status": q.market_status,
    }


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


def _resolve_quote_account(broker_id: int) -> int:
    """Pick any active account for this broker — quotes aren't account-specific."""
    with SessionLocal() as session:
        acct = session.execute(
            select(TradingAccount)
            .where(TradingAccount.broker_id == broker_id, TradingAccount.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
    if acct is None:
        raise HTTPException(409, "No active account on this broker — connect one first")
    return acct.id


@app.get("/brokers/{broker_id}/quote/{broker_symbol:path}")
async def get_quote(broker_id: int, broker_symbol: str):
    """Live quote for a (broker, broker_symbol) pair.

    Uses the per-account adapter cache so we don't POST /api/v1/session on
    every request. Falls back to a fresh login if the cached session has
    been killed server-side (we'll get an AuthError and retry once).
    """
    if not broker_symbol:
        raise HTTPException(400, "broker_symbol is required")
    account_id = _resolve_quote_account(broker_id)

    async def _fetch_one(entry: _CachedAdapter):
        async with entry.lock:
            return await entry.adapter.get_quote(broker_symbol)

    # Try with cached adapter; on AuthError invalidate and retry once.
    for attempt in (1, 2):
        entry = await _get_cached_adapter(account_id)
        try:
            q = await _fetch_one(entry)
            return {"broker_id": broker_id, **_serialize_quote(q, broker_symbol)}
        except NotImplementedError:
            raise HTTPException(404, f"Broker '{entry.broker.name}' does not support live quotes")
        except AuthError:
            await _invalidate_adapter(account_id)
            if attempt == 2:
                raise HTTPException(401, "Broker auth failed after retry")
        except BrokerError as exc:
            raise HTTPException(_broker_error_to_status(exc), str(exc))


class BatchQuoteRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=500)


@app.post("/brokers/{broker_id}/quotes/batch")
async def get_quotes_batch(broker_id: int, body: BatchQuoteRequest):
    """Fetch many quotes through ONE cached adapter session.

    Per-symbol failures are reported in the response under `errors`, not as a
    4xx. That way one bad ticker doesn't kill the batch — the caller logs the
    error and moves on. Auth failure mid-batch invalidates the cache and the
    rest of the batch retries through a fresh session.
    """
    if not body.symbols:
        raise HTTPException(400, "symbols list is empty")
    account_id = _resolve_quote_account(broker_id)

    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}
    remaining = list(body.symbols)

    # Use one cached adapter for the whole batch. If the session gets killed
    # mid-batch (AuthError), invalidate the cache, grab a fresh adapter, and
    # resume with the unprocessed symbols. The retry budget caps how many
    # times we'll re-login in a single batch (otherwise a persistently bad
    # session could loop forever).
    retries_left = 2
    while remaining and retries_left >= 0:
        entry = await _get_cached_adapter(account_id)
        async with entry.lock:
            processed_this_pass: list[str] = []
            auth_failed = False
            for symbol in remaining:
                try:
                    q = await entry.adapter.get_quote(symbol)
                    quotes[symbol] = _serialize_quote(q, symbol)
                    processed_this_pass.append(symbol)
                except NotImplementedError:
                    raise HTTPException(
                        404, f"Broker '{entry.broker.name}' does not support live quotes"
                    )
                except AuthError as exc:
                    errors[symbol] = f"auth: {exc}"
                    processed_this_pass.append(symbol)
                    auth_failed = True
                    break
                except BrokerError as exc:
                    errors[symbol] = str(exc)
                    processed_this_pass.append(symbol)
            remaining = [s for s in remaining if s not in processed_this_pass]
        if auth_failed:
            await _invalidate_adapter(account_id)
            retries_left -= 1
        else:
            break  # finished cleanly

    # Anything still in remaining means we burned the retry budget — mark them
    # as failed so the caller knows.
    for symbol in remaining:
        errors.setdefault(symbol, "auth retries exhausted")

    return {
        "broker_id": broker_id,
        "fetched_at": datetime.utcnow().isoformat(),
        "ok_count": len(quotes),
        "error_count": len(errors),
        "quotes": quotes,
        "errors": errors,
    }



