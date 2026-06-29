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
    AuthError, BrokerError, ModifyOrderRequest, ModifyPositionRequest,
    NetworkError, NotFoundError, OrderSide, OrderStatus,
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


@app.get("/accounts/{account_id}/stream_session")
async def stream_session(account_id: int):
    """Hand the price_stream service the WebSocket session tokens.

    The gateway is the only service allowed to decrypt broker credentials, so
    streaming auth is brokered here: we ensure a live Capital.com session and
    return its CST / security token (the same ones the WebSocket needs) plus
    whether this is a demo account. Tokens are valid for ~10 idle minutes.
    """
    _, broker, adapter = _build_adapter(account_id)
    try:
        await adapter._ensure_session()  # populates _cst / _sec_token
        cst = getattr(adapter, "_cst", None)
        sec = getattr(adapter, "_sec_token", None)
        if not cst or not sec:
            raise HTTPException(502, "Broker did not return streaming session tokens")
        _record_connect_status(account_id, ok=True, message=None)
        return {
            "cst": cst,
            "security_token": sec,
            "is_demo": bool(adapter.credentials.get("is_demo")),
        }
    except BrokerError as exc:
        _record_connect_status(account_id, ok=False, message=str(exc))
        raise HTTPException(_broker_error_to_status(exc), str(exc))
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
                broker_position_ref=p.broker_position_ref or None,
                broker_symbol=p.broker_symbol, quantity=p.quantity,
                avg_open_price=p.avg_open_price, current_price=p.current_price,
                unrealized_pl=p.unrealized_pl, unrealized_pl_pct=p.unrealized_pl_pct,
                stop_loss=p.stop_loss, take_profit=p.take_profit,
                opened_at=p.opened_at,
                currency=p.currency, direction=p.direction.value, raw=p.raw,
                fetched_at=datetime.utcnow(),
            ))
        session.commit()
        _record_connect_status(account_id, ok=True, message=None)

    return [{
        "broker_position_ref": p.broker_position_ref,
        "broker_symbol": p.broker_symbol, "quantity": str(p.quantity),
        "avg_open_price": str(p.avg_open_price) if p.avg_open_price else None,
        "current_price": str(p.current_price) if p.current_price else None,
        "unrealized_pl": str(p.unrealized_pl) if p.unrealized_pl else None,
        "stop_loss": str(p.stop_loss) if p.stop_loss else None,
        "take_profit": str(p.take_profit) if p.take_profit else None,
        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
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


# ----------------------------------------------------------------------------
# Position MUTATION routes — modify SL/TP, close, close-all.
#
# These map 1:1 to BrokerAdapter abstract methods. Adapters that don't
# implement them raise NotImplementedError -> we surface as HTTP 501.
# ----------------------------------------------------------------------------
class ModifyPositionIn(BaseModel):
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@app.patch("/accounts/{account_id}/positions/{ref}")
async def modify_position(account_id: int, ref: str, body: ModifyPositionIn):
    """Update SL/TP on an open position. Updates the cached snapshot row
    in-place so the UI immediately reflects the change without waiting for
    the next refresh tick.
    """
    _, _, adapter = _build_adapter(account_id)
    try:
        req = ModifyPositionRequest(
            broker_position_ref=ref,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
        try:
            updated = await adapter.modify_position(req)
        except NotImplementedError:
            raise HTTPException(501, "This broker does not support modify_position")

        # Mirror the change into the snapshot so the UI doesn't show stale
        # SL/TP for the next 60s until the cache TTL expires.
        with SessionLocal() as session:
            snap = session.execute(
                select(BrokerPositionSnapshot).where(
                    BrokerPositionSnapshot.account_id == account_id,
                    BrokerPositionSnapshot.broker_position_ref == ref,
                )
            ).scalar_one_or_none()
            if snap is not None:
                snap.stop_loss = updated.stop_loss
                snap.take_profit = updated.take_profit
                snap.fetched_at = datetime.utcnow()
                session.commit()

        return {
            "broker_position_ref": updated.broker_position_ref,
            "broker_symbol": updated.broker_symbol,
            "stop_loss": str(updated.stop_loss) if updated.stop_loss else None,
            "take_profit": str(updated.take_profit) if updated.take_profit else None,
        }
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


@app.delete("/accounts/{account_id}/positions/{ref}")
async def close_position(account_id: int, ref: str):
    """Close a single position by ref. Removes the cached snapshot row on
    success so the UI immediately shows it gone.
    """
    _, _, adapter = _build_adapter(account_id)
    try:
        try:
            result = await adapter.close_position(ref)
        except NotImplementedError:
            raise HTTPException(501, "This broker does not support close_position")

        if result.closed:
            with SessionLocal() as session:
                session.query(BrokerPositionSnapshot).filter(
                    BrokerPositionSnapshot.account_id == account_id,
                    BrokerPositionSnapshot.broker_position_ref == ref,
                ).delete()
                session.commit()

        return {
            "broker_position_ref": result.broker_position_ref,
            "closed": result.closed,
            "closed_quantity": str(result.closed_quantity) if result.closed_quantity else None,
            "close_price": str(result.close_price) if result.close_price else None,
            "realized_pl": str(result.realized_pl) if result.realized_pl else None,
        }
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


class CloseAllPositionsIn(BaseModel):
    broker_symbol: Optional[str] = None
    # Optional filter: only close positions whose broker_position_ref is in
    # this list. Used by the "close all bot positions for THIS SIGNAL"
    # button so we don't accidentally close manual positions on the same
    # symbol.
    refs: Optional[list[str]] = None


@app.post("/accounts/{account_id}/positions/close-all")
async def close_all_positions(account_id: int, body: CloseAllPositionsIn):
    """Close every open position (optionally filtered by symbol OR by an
    explicit list of refs). The 'refs' filter is the safer mode and the
    one the UI uses for "close all for this signal".
    """
    _, _, adapter = _build_adapter(account_id)
    try:
        if body.refs:
            # Targeted: close exactly these refs, no more, no less.
            # Faster than fetching the position list first and safer because
            # it doesn't touch anything the caller didn't ask for.
            results = []
            for ref in body.refs:
                try:
                    r = await adapter.close_position(ref)
                except NotImplementedError:
                    raise HTTPException(501, "This broker does not support close_position")
                except BrokerError as exc:
                    r = type("ClosePositionResult", (), {
                        "broker_position_ref": ref,
                        "closed": False,
                        "closed_quantity": None,
                        "close_price": None,
                        "realized_pl": None,
                        "raw": {"error": str(exc)},
                    })()
                results.append(r)
        else:
            try:
                results = await adapter.close_all_positions(body.broker_symbol)
            except NotImplementedError:
                raise HTTPException(501, "This broker does not support close_all_positions")

        # Clear closed rows from the snapshot.
        closed_refs = [r.broker_position_ref for r in results if r.closed and r.broker_position_ref]
        if closed_refs:
            with SessionLocal() as session:
                session.query(BrokerPositionSnapshot).filter(
                    BrokerPositionSnapshot.account_id == account_id,
                    BrokerPositionSnapshot.broker_position_ref.in_(closed_refs),
                ).delete(synchronize_session=False)
                session.commit()

        return {
            "results": [{
                "broker_position_ref": r.broker_position_ref,
                "closed": r.closed,
                "closed_quantity": str(r.closed_quantity) if r.closed_quantity else None,
                "close_price": str(r.close_price) if r.close_price else None,
                "realized_pl": str(r.realized_pl) if r.realized_pl else None,
            } for r in results],
            "closed_count": sum(1 for r in results if r.closed),
            "failed_count": sum(1 for r in results if not r.closed),
        }
    except BrokerError as exc:
        raise HTTPException(_broker_error_to_status(exc), str(exc))
    finally:
        await adapter.aclose()


class ModifyOrderIn(BaseModel):
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@app.patch("/accounts/{account_id}/orders/{ref}")
async def modify_order(account_id: int, ref: str, body: ModifyOrderIn):
    """Update levels on a pending working order."""
    _, _, adapter = _build_adapter(account_id)
    try:
        req = ModifyOrderRequest(
            broker_order_ref=ref,
            limit_price=body.limit_price,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
        try:
            updated = await adapter.modify_order(req)
        except NotImplementedError:
            raise HTTPException(501, "This broker does not support modify_order")

        with SessionLocal() as session:
            row = session.execute(
                select(BrokerOrderRow).where(BrokerOrderRow.broker_order_ref == ref)
            ).scalar_one_or_none()
            if row is not None:
                row.limit_price = updated.limit_price
                row.stop_loss = updated.stop_loss
                row.take_profit = updated.take_profit
                row.last_synced_at = datetime.utcnow()
                session.commit()

        return {
            "broker_order_ref": updated.broker_order_ref,
            "broker_symbol": updated.broker_symbol,
            "limit_price": str(updated.limit_price) if updated.limit_price else None,
            "stop_loss": str(updated.stop_loss) if updated.stop_loss else None,
            "take_profit": str(updated.take_profit) if updated.take_profit else None,
        }
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
    # NOTE: allow an empty symbol list. Callers can hit this endpoint with
    # whatever set of mappings they have; if a broker is connected but has
    # zero tradeable instruments yet, we'd rather return an empty batch than
    # 422 and break the loop. max_length still bounds the per-call cost.
    symbols: list[str] = Field(default_factory=list, max_length=1500)


@app.post("/brokers/{broker_id}/quotes/batch")
async def get_quotes_batch(broker_id: int, body: BatchQuoteRequest):
    """Fetch many quotes through ONE cached adapter session.

    Per-symbol failures are reported in the response under `errors`, not as a
    4xx. That way one bad ticker doesn't kill the batch — the caller logs the
    error and moves on. Auth failure mid-batch invalidates the cache and the
    rest of the batch retries through a fresh session.
    """
    log.info(f"Batch quote request for broker={broker_id}, symbols_count={len(body.symbols)}, first_5={body.symbols[:5]}")
    if not body.symbols:
        return {
            "broker_id": broker_id,
            "fetched_at": datetime.utcnow().isoformat(),
            "ok_count": 0, "error_count": 0,
            "quotes": {}, "errors": {},
            "note": "Empty symbols list — nothing to do.",
        }
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




# ----------------------------------------------------------------------------
# Historical bars (for the on-demand chart). Pass-through to the adapter.
# Not persisted — frontend polls this endpoint and renders directly. Keeping
# it out of the DB means the feature can be removed cleanly later.
# ----------------------------------------------------------------------------
_BARS_RESOLUTIONS = {
    "MINUTE", "MINUTE_5", "MINUTE_15", "MINUTE_30",
    "HOUR", "HOUR_4",
    "DAY", "WEEK", "MONTH",
}


@app.get("/brokers/{broker_id}/bars")
async def get_bars(
    broker_id: int,
    symbol: str,
    resolution: str = "MINUTE_5",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    max_bars: int = 200,
):
    """Historical OHLC bars at a given resolution for an epic.

    Uses the cached adapter so the chart doesn't trigger a fresh session per
    timeframe change. Resolution validated against the Capital.com whitelist.
    """
    if not symbol:
        raise HTTPException(400, "symbol is required")
    if resolution not in _BARS_RESOLUTIONS:
        raise HTTPException(
            400,
            f"Unsupported resolution. Allowed: {sorted(_BARS_RESOLUTIONS)}",
        )
    account_id = _resolve_quote_account(broker_id)

    for attempt in (1, 2):
        entry = await _get_cached_adapter(account_id)
        try:
            async with entry.lock:
                if not hasattr(entry.adapter, "get_bars"):
                    raise HTTPException(
                        404,
                        f"Broker '{entry.broker.name}' does not support historical bars",
                    )
                bars = await entry.adapter.get_bars(
                    symbol, resolution=resolution,
                    from_ts=from_ts, to_ts=to_ts, max_bars=max_bars,
                )
            return {
                "broker_id": broker_id,
                "symbol": symbol,
                "resolution": resolution,
                "fetched_at": datetime.utcnow().isoformat(),
                "bars": bars,
            }
        except AuthError:
            await _invalidate_adapter(account_id)
            if attempt == 2:
                raise HTTPException(401, "Broker auth failed after retry")
        except BrokerError as exc:
            raise HTTPException(_broker_error_to_status(exc), str(exc))
