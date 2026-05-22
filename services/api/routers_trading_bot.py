"""Trading Bot — read endpoints for the /trading-bot page + admin CRUD for
channels + manual trade execution from signals.

Milestone 1 endpoints:
    GET    /trading-bot/signals?limit=50              recent parsed signals
    GET    /trading-bot/raw?limit=50                  recent raw messages
Milestone 2 endpoints:
    GET    /trading-bot/channels                      list channels
    POST   /trading-bot/channels                      admin: add channel
    PATCH  /trading-bot/channels/{id}                 admin: edit channel
    DELETE /trading-bot/channels/{id}                 admin: remove channel
    GET    /trading-bot/resolve?query=...             admin: resolve @username/id
Milestone 3 endpoints (manual trading):
    GET    /trading-bot/settings                      bot globals (risk %, lot rules)
    PATCH  /trading-bot/settings                      admin: update bot globals
    GET    /trading-bot/signals/{id}/trade-options    pre-fill data for trade form
    POST   /trading-bot/signals/{id}/trade            place a trade from a signal
    GET    /trading-bot/signals/{id}/trades           trades placed against this signal
    GET    /trading-bot/trades                        user's recent trade history

The listener service polls tg_channels every 60s, so admin changes propagate
without a service restart.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shared.db import (
    AppSetting, BotTrade, Broker, BrokerInstrument, BrokerOrder,
    TgChannel, TgRawMessage, TgSignal, TradingAccount, User,
)

from .auth import get_current_user, get_db


trading_bot_router = APIRouter(prefix="/trading-bot", tags=["trading_bot"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


def _dec(v):
    """Decimal → float for JSON serialisation. Decimals lose precision but
    these are price levels — six decimals max, well within float64 safe range.
    """
    return float(v) if isinstance(v, Decimal) else v


# ---------------------------------------------------------------------------
# Signals (the sidebar)
# ---------------------------------------------------------------------------
@trading_bot_router.get("/signals")
def list_signals(
    limit: int = 50,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest parsed signals — drives the sidebar on the /trading-bot page."""
    limit = max(1, min(limit, 200))
    rows = db.execute(
        select(TgSignal).order_by(desc(TgSignal.signal_time)).limit(limit)
    ).scalars().all()
    return [
        {
            "id": s.id,
            "signal_time": s.signal_time,
            "symbol": s.symbol,
            "direction": s.direction,
            "entry_from": _dec(s.entry_from),
            "entry_to": _dec(s.entry_to),
            "sl": _dec(s.sl),
            "tps": [_dec(x) for x in (s.tps or [])],
            "parser_key": s.parser_key,
            "status": s.status,
            "channel_id": s.channel_id,
            "channel_title": s.channel_title,
            "raw_text": s.raw_text,
        }
        for s in rows
    ]


@trading_bot_router.get("/raw")
def list_raw_messages(
    limit: int = 50,
    parse_status: Optional[str] = None,
    _: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: recent raw messages. Useful when a known signal didn't
    appear in /signals — find it here, see why parse_status went to 'noise'
    or 'failed'.
    """
    limit = max(1, min(limit, 200))
    q = select(TgRawMessage).order_by(desc(TgRawMessage.received_at)).limit(limit)
    if parse_status:
        q = q.where(TgRawMessage.parse_status == parse_status)
    rows = db.execute(q).scalars().all()
    return [
        {
            "id": r.id,
            "channel_id": r.channel_id,
            "channel_title": r.channel_title,
            "tg_message_id": r.tg_message_id,
            "received_at": r.received_at,
            "processed_at": r.processed_at,
            "parse_status": r.parse_status,
            "parse_error": r.parse_error,
            "message_text": r.message_text,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Channels (admin CRUD)
# ---------------------------------------------------------------------------
_VALID_ORDER_TYPES = ("MARKET", "LIMIT", "STOP")


class ChannelIn(BaseModel):
    channel_id: int = Field(..., description="Telegram channel id, e.g. -1001234567890")
    channel_title: str = Field(..., min_length=1, max_length=160)
    channel_username: Optional[str] = Field(None, max_length=80)
    parser_key: str = Field("gold_xau", max_length=32)
    is_enabled: bool = True
    notes: Optional[str] = None
    # Strategy params (Milestone 2)
    order_position_type: str = Field("MARKET", max_length=16)
    tp_strategy: str = Field("tp1", max_length=120)
    is_tradeable: bool = True
    is_trusted: bool = True
    image_url: Optional[str] = None


class ChannelUpdate(BaseModel):
    channel_title: Optional[str] = Field(None, max_length=160)
    channel_username: Optional[str] = Field(None, max_length=80)
    parser_key: Optional[str] = Field(None, max_length=32)
    is_enabled: Optional[bool] = None
    notes: Optional[str] = None
    order_position_type: Optional[str] = Field(None, max_length=16)
    tp_strategy: Optional[str] = Field(None, max_length=120)
    is_tradeable: Optional[bool] = None
    is_trusted: Optional[bool] = None
    image_url: Optional[str] = None


def _channel_out(c: TgChannel) -> dict[str, Any]:
    return {
        "id": c.id,
        "channel_id": c.channel_id,
        "channel_title": c.channel_title,
        "channel_username": c.channel_username,
        "parser_key": c.parser_key,
        "is_enabled": c.is_enabled,
        "notes": c.notes,
        "order_position_type": c.order_position_type,
        "tp_strategy": c.tp_strategy,
        "is_tradeable": c.is_tradeable,
        "is_trusted": c.is_trusted,
        "image_url": c.image_url,
        "last_message_at": c.last_message_at,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _validate_strategy_fields(order_position_type: Optional[str]) -> None:
    """Raise HTTPException(400) on bad enum-like inputs.

    Centralised so create + update paths give identical error messages.
    """
    if order_position_type is not None and order_position_type not in _VALID_ORDER_TYPES:
        raise HTTPException(
            400,
            f"order_position_type must be one of {_VALID_ORDER_TYPES}",
        )


@trading_bot_router.get("/channels")
def list_channels(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(TgChannel).order_by(TgChannel.channel_title)
    ).scalars().all()
    return [_channel_out(c) for c in rows]


@trading_bot_router.post("/channels")
def create_channel(
    req: ChannelIn,
    _: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    _validate_strategy_fields(req.order_position_type)
    existing = db.execute(
        select(TgChannel).where(TgChannel.channel_id == req.channel_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            409,
            f"Channel {req.channel_id} already exists (row id={existing.id})",
        )
    c = TgChannel(**req.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _channel_out(c)


@trading_bot_router.patch("/channels/{channel_pk}")
def update_channel(
    channel_pk: int,
    req: ChannelUpdate,
    _: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    _validate_strategy_fields(req.order_position_type)
    c = db.get(TgChannel, channel_pk)
    if c is None:
        raise HTTPException(404, "Channel not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return _channel_out(c)


@trading_bot_router.delete("/channels/{channel_pk}")
def delete_channel(
    channel_pk: int,
    _: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    c = db.get(TgChannel, channel_pk)
    if c is None:
        raise HTTPException(404, "Channel not found")
    db.delete(c)
    db.commit()
    return {"deleted": channel_pk}


# ---------------------------------------------------------------------------
# Channel resolver — asks the listener container to look up a channel by
# @username or numeric id using the authenticated Telethon session. Lets
# admins paste either form into the Add Channel form and get the canonical
# numeric id + title back without leaving the UI.
# ---------------------------------------------------------------------------
@trading_bot_router.get("/resolve")
async def resolve_channel(
    query: str,
    _: User = Depends(_require_admin),
):
    """Proxy to telegram_listener:8005/resolve."""
    import os
    import httpx

    base = os.environ.get("TELEGRAM_RESOLVER_URL", "http://telegram_listener:8005")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}/resolve", params={"query": query})
    except httpx.RequestError as exc:
        # Listener service down / unreachable — give the admin a specific
        # actionable error, not a generic 500.
        raise HTTPException(
            503,
            f"Telegram listener is unreachable ({type(exc).__name__}). "
            f"Is the telegram_listener service running and configured?",
        )

    if r.status_code >= 400:
        # Pass the listener's error through verbatim so HTTP 404 stays 404.
        try:
            detail = r.json().get("detail") or r.text
        except Exception:
            detail = r.text
        raise HTTPException(r.status_code, detail or "Resolve failed")

    return r.json()


# =============================================================================
# Milestone 3: Bot settings + manual trade execution
# =============================================================================
# Bot-global settings live in app_settings under keys 'tgbot.*'. Values are
# stored as JSONB so numbers stay numbers and strings stay strings.
_BOT_SETTING_KEYS = (
    "tgbot.risk_pct_per_trade",
    "tgbot.max_risk_pct_per_trade",
    "tgbot.min_lot_size",
    "tgbot.lot_step",
    "tgbot.default_tp_level",
)


def _read_bot_settings(db: Session) -> dict[str, Any]:
    """Return all 'tgbot.*' settings as a flat dict with safe fallbacks.

    Defaults match migration 017's seed values so the form works even on
    an environment where the migration hasn't fully applied.
    """
    defaults = {
        "tgbot.risk_pct_per_trade":     1.0,
        "tgbot.max_risk_pct_per_trade": 5.0,
        "tgbot.min_lot_size":           0.01,
        "tgbot.lot_step":               0.01,
        "tgbot.default_tp_level":       "TP1",
    }
    rows = db.execute(
        select(AppSetting).where(AppSetting.key.in_(_BOT_SETTING_KEYS))
    ).scalars().all()
    out = dict(defaults)
    for r in rows:
        out[r.key] = r.value
    return out


@trading_bot_router.get("/settings")
def get_bot_settings(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bot globals (lot sizing / risk caps). Anyone authenticated can read —
    the trade form needs these to compute lot sizes for non-admin users too.
    """
    return _read_bot_settings(db)


class BotSettingsUpdate(BaseModel):
    """Partial update. Each field maps to one app_settings row.

    Constraints — defensive only; the frontend should enforce these too.
    """
    risk_pct_per_trade:     Optional[float] = Field(None, ge=0.01, le=100)
    max_risk_pct_per_trade: Optional[float] = Field(None, ge=0.01, le=100)
    min_lot_size:           Optional[float] = Field(None, gt=0)
    lot_step:               Optional[float] = Field(None, gt=0)
    default_tp_level:       Optional[str]   = Field(None, max_length=8)


@trading_bot_router.patch("/settings")
def update_bot_settings(
    body: BotSettingsUpdate,
    user: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only. Each provided field UPSERTs one app_settings row."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _read_bot_settings(db)

    for field, value in updates.items():
        key = f"tgbot.{field}"
        existing = db.execute(
            select(AppSetting).where(AppSetting.key == key)
        ).scalar_one_or_none()
        if existing is None:
            db.add(AppSetting(
                key=key, value=value,
                description=f"Bot setting: {field}",
                updated_by=user.id, updated_at=datetime.utcnow(),
            ))
        else:
            existing.value = value
            existing.updated_by = user.id
            existing.updated_at = datetime.utcnow()
    db.commit()
    return _read_bot_settings(db)


# ---------------------------------------------------------------------------
# Trade-options endpoint — gives the frontend everything it needs to render
# the "Trade signal" modal in one round trip:
#   - the signal itself
#   - bot settings (default risk %, max risk %, lot rules)
#   - eligible trading accounts (active + Capital.com for now)
#   - resolved broker_symbol per account (so we know if the symbol is mapped)
# ---------------------------------------------------------------------------
@trading_bot_router.get("/signals/{signal_id}/trade-options")
def get_trade_options(
    signal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sig = db.get(TgSignal, signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")

    settings = _read_bot_settings(db)

    # Active trading accounts owned by this user — keyed by broker for the
    # frontend to group them under broker headings.
    accounts = db.execute(
        select(TradingAccount, Broker)
        .join(Broker, TradingAccount.broker_id == Broker.id)
        .where(TradingAccount.user_id == user.id,
               TradingAccount.is_active.is_(True))
        .order_by(Broker.name, TradingAccount.label)
    ).all()

    # Build the (account → resolved broker_symbol) map. The signal's symbol
    # is something like 'XAUUSD' — each broker may use a different symbol
    # (XAUUSD vs GOLD vs XAU/USD). We look it up via broker_instruments
    # using a stock_id that matches by ticker if one exists; otherwise we
    # pass the signal symbol through unchanged and let the broker reject it
    # (the trade form lets the user override).
    account_options = []
    for acct, broker in accounts:
        # Best-effort symbol resolution. Currently the bot only handles XAU,
        # which isn't in the stocks table. For now we just echo the signal's
        # symbol. Future: instrument lookup by ticker/broker.
        account_options.append({
            "account_id": acct.id,
            "broker_id": broker.id,
            "broker_code": broker.code,
            "broker_name": broker.name,
            "account_label": acct.label or f"Account {acct.id}",
            "account_type": getattr(acct, "account_type", None),
            "currency": getattr(acct, "currency", None),
            "is_active": acct.is_active,
            "resolved_symbol": sig.symbol,  # placeholder mapping
        })

    return {
        "signal": {
            "id": sig.id,
            "symbol": sig.symbol,
            "direction": sig.direction,
            "entry_from": float(sig.entry_from),
            "entry_to": float(sig.entry_to),
            "sl": float(sig.sl),
            "tps": [float(x) for x in (sig.tps or [])],
            "channel_id": sig.channel_id,
            "channel_title": sig.channel_title,
            "signal_time": sig.signal_time,
            "raw_text": sig.raw_text,
        },
        "settings": settings,
        "accounts": account_options,
        # Also include the channel's strategy params — the frontend uses
        # `order_position_type` to pre-fill the order type radio.
        "channel_strategy": _channel_strategy_for(db, sig.channel_id),
    }


def _channel_strategy_for(db: Session, channel_id: int) -> Optional[dict[str, Any]]:
    """Returns the strategy block from tg_channels for a given Telegram
    channel_id, or None if the channel was somehow removed since the signal
    was logged."""
    c = db.execute(
        select(TgChannel).where(TgChannel.channel_id == channel_id)
    ).scalar_one_or_none()
    if c is None:
        return None
    return {
        "order_position_type": c.order_position_type,
        "tp_strategy": c.tp_strategy,
        "is_tradeable": c.is_tradeable,
        "is_trusted": c.is_trusted,
    }


# ---------------------------------------------------------------------------
# Trade endpoint — fans out a SIGNAL into N (or 2N) orders.
#
# Fanout rules (from your spec):
#   entry_from == entry_to  → N orders (one per TP), same entry for all
#   entry_from != entry_to  → 2N orders (each entry × each TP)
#
# All children share the SAME stop_loss. They differ only in take_profit
# (and entry, in the range case). Because the distance from entry to SL is
# identical for every child within one entry, the per-order RISK in account
# currency is identical for all children at that entry — so we split the
# user's chosen total risk_pct evenly across the children.
#
#   per_order_risk_pct = total_risk_pct / child_count
#
# The client computes the lot size per child from per_order_risk_pct so the
# total account exposure equals the user's total_risk_pct figure.
# ---------------------------------------------------------------------------
class TradeOrderLeg(BaseModel):
    """One child in the fanout. Computed by the client; validated here."""
    broker_symbol:   str       = Field(..., min_length=1, max_length=64)
    side:            str       = Field(..., pattern="^(BUY|SELL)$")
    order_type:      str       = Field(..., pattern="^(MARKET|LIMIT|STOP)$")
    quantity:        Decimal   = Field(..., gt=0)
    limit_price:     Optional[Decimal] = None
    stop_loss:       Decimal
    take_profit:     Decimal
    tp_level:        str       = Field(..., max_length=8)   # 'TP1' | 'TP2' …


class TradeSignalRequest(BaseModel):
    """Fanout request: one ACCOUNT + N order legs.

    The client computes per-leg quantity from the chosen total_risk_pct
    (split evenly across legs). The server places each leg via the existing
    /orders code path and links every resulting BrokerOrder to the same
    signal via bot_trades. ATOMIC SEMANTICS: if any leg fails, we DO NOT
    roll back already-placed legs — that would be impossible (you can't
    un-place an order at the broker). Instead we record what succeeded
    and surface failures back to the UI so the user can see + retry.
    """
    account_id:     int
    total_risk_pct: Decimal     = Field(..., ge=0, le=100)
    notes:          Optional[str] = None
    legs:           list[TradeOrderLeg] = Field(..., min_length=1, max_length=50)


@trading_bot_router.post("/signals/{signal_id}/trade")
async def trade_signal(
    signal_id: int,
    body: TradeSignalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Place N child orders against a Telegram signal.

    All children share the same account + same stop_loss. They differ in
    take_profit (per TP level) and possibly entry/limit_price (when the
    signal has an entry range).
    """
    sig = db.get(TgSignal, signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")

    acct = db.get(TradingAccount, body.account_id)
    if acct is None or acct.user_id != user.id or not acct.is_active:
        raise HTTPException(404, "Trading account not found / not yours / inactive")

    # Per-order risk pct — recorded on each bot_trades row so the audit log
    # shows how the total was split. We use Decimal division to avoid
    # float drift (totals must reconcile to total_risk_pct exactly).
    per_order_risk = (body.total_risk_pct / Decimal(len(body.legs)))

    # We import lazily so this module doesn't depend on routers_orders at
    # import time (avoids any circular-import surprises).
    from .routers_orders import place_order, PlaceOrderIn

    placed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for idx, leg in enumerate(body.legs):
        order_in = PlaceOrderIn(
            account_id=body.account_id,
            stock_id=None,
            broker_symbol=leg.broker_symbol,
            side=leg.side,
            order_type=leg.order_type,
            quantity=leg.quantity,
            limit_price=leg.limit_price,
            stop_loss=leg.stop_loss,
            take_profit=leg.take_profit,
            notes=(body.notes or
                   f"Bot signal #{signal_id} ({sig.channel_title}) "
                   f"leg {idx + 1}/{len(body.legs)} @ {leg.tp_level}"),
        )

        try:
            order_response = await place_order(order_in, user=user, db=db)
        except HTTPException as exc:
            failed.append({
                "leg_index":   idx,
                "tp_level":    leg.tp_level,
                "limit_price": str(leg.limit_price) if leg.limit_price is not None else None,
                "take_profit": str(leg.take_profit),
                "quantity":    str(leg.quantity),
                "error":       exc.detail,
                "status":      exc.status_code,
            })
            # Carry on — placing the remaining legs is the right call.
            # An "all-or-nothing" semantic isn't achievable when legs land
            # at the broker one at a time.
            continue
        except Exception as exc:
            failed.append({
                "leg_index": idx,
                "tp_level":  leg.tp_level,
                "error":     f"{type(exc).__name__}: {exc}",
            })
            continue

        order_id = (
            order_response.get("id")
            or order_response.get("order_id")
            or order_response.get("order", {}).get("id")
        )
        if not order_id:
            failed.append({
                "leg_index": idx, "tp_level": leg.tp_level,
                "error": "Order placed but no id returned",
                "response": order_response,
            })
            continue

        bt = BotTrade(
            signal_id=signal_id,
            order_id=order_id,
            user_id=user.id,
            account_id=body.account_id,
            tp_level=leg.tp_level,
            risk_pct=per_order_risk,
            trade_mode="manual",
            notes=order_in.notes,
        )
        db.add(bt)
        db.flush()         # need bt.id before commit

        placed.append({
            "bot_trade_id": bt.id,
            "order_id":     order_id,
            "leg_index":    idx,
            "tp_level":     leg.tp_level,
            "limit_price":  str(leg.limit_price) if leg.limit_price is not None else None,
            "take_profit":  str(leg.take_profit),
            "quantity":     str(leg.quantity),
            "status":       order_response.get("status"),
            "broker_order_ref": order_response.get("broker_order_ref"),
        })

    db.commit()

    return {
        "signal_id":       signal_id,
        "account_id":      body.account_id,
        "total_risk_pct":  str(body.total_risk_pct),
        "per_order_risk_pct": str(per_order_risk),
        "placed":          placed,
        "failed":          failed,
        "all_ok":          len(failed) == 0,
    }


# ---------------------------------------------------------------------------
# Trade history endpoints
# ---------------------------------------------------------------------------
def _bot_trade_out(bt: BotTrade, order: Optional[BrokerOrder],
                   sig: Optional[TgSignal]) -> dict[str, Any]:
    """Build the trade-row payload the UI table renders.

    Includes the underlying order's status so the user can see fills /
    rejections / pending state without an extra fetch.
    """
    return {
        "id": bt.id,
        "signal_id": bt.signal_id,
        "order_id": bt.order_id,
        "account_id": bt.account_id,
        "tp_level": bt.tp_level,
        "risk_pct": float(bt.risk_pct) if bt.risk_pct is not None else None,
        "trade_mode": bt.trade_mode,
        "notes": bt.notes,
        "created_at": bt.created_at,
        "signal": {
            "symbol": sig.symbol, "direction": sig.direction,
            "channel_title": sig.channel_title,
            "signal_time": sig.signal_time,
        } if sig else None,
        "order": {
            "side": order.side, "order_type": order.order_type,
            "quantity": float(order.quantity),
            "limit_price": float(order.limit_price) if order.limit_price is not None else None,
            "stop_loss":   float(order.stop_loss)   if order.stop_loss   is not None else None,
            "take_profit": float(order.take_profit) if order.take_profit is not None else None,
            "status": order.status,
            "fill_price": float(order.fill_price) if order.fill_price is not None else None,
            "broker_order_ref": order.broker_order_ref,
            "rejection_reason": order.rejection_reason,
            "placed_at": order.placed_at,
            "filled_at": order.filled_at,
        } if order else None,
    }


@trading_bot_router.get("/signals/{signal_id}/trades")
def list_trades_for_signal(
    signal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trades placed against a specific signal — used by the UI to show
    a "✓ Traded N times" badge and a quick list.
    """
    rows = db.execute(
        select(BotTrade, BrokerOrder, TgSignal)
        .outerjoin(BrokerOrder, BrokerOrder.id == BotTrade.order_id)
        .outerjoin(TgSignal,    TgSignal.id == BotTrade.signal_id)
        .where(BotTrade.signal_id == signal_id, BotTrade.user_id == user.id)
        .order_by(desc(BotTrade.created_at))
    ).all()
    return [_bot_trade_out(bt, order, sig) for (bt, order, sig) in rows]


@trading_bot_router.get("/trades")
def list_my_trades(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All of the current user's bot-trades, newest first."""
    limit = max(1, min(limit, 200))
    rows = db.execute(
        select(BotTrade, BrokerOrder, TgSignal)
        .outerjoin(BrokerOrder, BrokerOrder.id == BotTrade.order_id)
        .outerjoin(TgSignal,    TgSignal.id == BotTrade.signal_id)
        .where(BotTrade.user_id == user.id)
        .order_by(desc(BotTrade.created_at))
        .limit(limit)
    ).all()
    return [_bot_trade_out(bt, order, sig) for (bt, order, sig) in rows]
