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
    BrokerPositionSnapshot,
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
# ---------------------------------------------------------------------------
# FX helper — looks up rates from app_settings under 'fx.{ccy}_to_usd'.
#
# Direction convention is INTENTIONAL and explicit: keys ALWAYS store the
# multiplier that converts FROM the named currency TO USD.
#
#     fx.aed_to_usd = 0.2723   →   usd = aed * 0.2723
#     fx.eur_to_usd = 1.08     →   usd = eur * 1.08
#     fx.usd_to_usd = 1.0      →   identity row, seeded too
#
# Multiplication-only, no division. Flipping the rate division-style is the
# #1 way risk-sizing math accidentally produces positions 13x too large.
# ---------------------------------------------------------------------------
def _fx_to_usd(db: Session, currency: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """Look up the multiplier that converts `currency` to USD.

    Returns (rate, warning). On warning, the lot computation MUST refuse to
    return a number; the UI surfaces the warning instead of silently
    defaulting to a wrong lot size.
    """
    if not currency:
        return None, "Account currency is null — set it on the broker account."
    key = f"fx.{currency.lower()}_to_usd"
    row = db.execute(
        select(AppSetting).where(AppSetting.key == key)
    ).scalar_one_or_none()
    if row is None or row.value is None:
        return None, (
            f"No FX rate for {currency}. Add admin setting '{key}' "
            f"(value = how many USD per 1 {currency})."
        )
    try:
        rate = float(row.value)
    except (TypeError, ValueError):
        return None, f"Setting '{key}' is not a number: {row.value!r}"
    if rate <= 0:
        return None, f"Setting '{key}' must be positive, got {rate}"
    return rate, None


@trading_bot_router.get("/signals/{signal_id}/trade-options")
async def get_trade_options(
    signal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Single round trip for everything the trade modal needs.

    On top of the static account/signal data, this also fetches live balance
    from broker_gateway for each active account in parallel, plus the FX
    rate from `app_settings` so the modal can compute lot size correctly
    against an AED-denominated account trading USD-quoted XAU.
    """
    sig = db.get(TgSignal, signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")

    settings = _read_bot_settings(db)

    accounts = db.execute(
        select(TradingAccount, Broker)
        .join(Broker, TradingAccount.broker_id == Broker.id)
        .where(TradingAccount.user_id == user.id,
               TradingAccount.is_active.is_(True))
        .order_by(Broker.name, TradingAccount.label)
    ).all()

    # Fetch balances in parallel via broker_gateway. We've seen the gateway
    # tail-latency reach ~3s on cold Capital.com sessions, so serial would
    # noticeably block modal open with multiple accounts. asyncio.gather
    # keeps total wall time close to the slowest single call.
    import asyncio
    import httpx
    import os as _os
    gw_url = _os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")

    async def _fetch_account_info(account_id: int) -> Optional[dict]:
        """Best-effort balance lookup. Returns None on any failure — the
        frontend then disables the lot-compute path for that account and
        falls back to min_lot. We never block trade placement on this.
        """
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"{gw_url}/accounts/{account_id}/info")
                if r.status_code >= 400:
                    return None
                return r.json()
        except Exception:
            return None

    info_results = await asyncio.gather(
        *[_fetch_account_info(acct.id) for acct, _ in accounts],
        return_exceptions=False,
    )

    account_options = []
    for (acct, broker), info in zip(accounts, info_results):
        # AccountInfo from the adapter is {balance, available, currency, ...}.
        # We treat the adapter's 'currency' as authoritative — the DB value on
        # TradingAccount may be stale or unset. Fall back to DB if adapter null.
        currency = (info or {}).get("currency") or getattr(acct, "currency", None)
        balance_raw = (info or {}).get("balance")
        available_raw = (info or {}).get("available")

        def _f(x):
            if x is None:
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        balance = _f(balance_raw)
        available = _f(available_raw)

        # Convert to USD for the modal's lot math. Missing FX is non-fatal:
        # we surface a clear warning and the modal disables auto-lot.
        fx_rate, fx_warn = _fx_to_usd(db, currency)
        balance_usd = (balance * fx_rate) if (balance is not None and fx_rate is not None) else None

        account_options.append({
            "account_id":      acct.id,
            "broker_id":       broker.id,
            "broker_code":     broker.code,
            "broker_name":     broker.name,
            "account_label":   acct.label or f"Account {acct.id}",
            "account_type":    getattr(acct, "account_type", None),
            "currency":        currency,
            "is_active":       acct.is_active,
            "resolved_symbol": sig.symbol,
            # New fields for risk-based lot sizing:
            "balance":         balance,
            "available":       available,
            "fx_rate":         fx_rate,
            "balance_usd":     balance_usd,
            "fx_warning":      fx_warn,
            # info_fetched is the simple signal "did broker_gateway respond
            # for this account?" — frontend uses it to grey out lot field.
            "info_fetched":    info is not None,
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
# Fanout rules:
#   entry_from == entry_to  → N orders (one per TP), same entry for all
#   entry_from != entry_to  → 2N orders (each entry × each TP)
#
# All children share the SAME stop_loss. They differ only in take_profit
# (and entry, in the range case). The frontend computes the per-leg
# quantity from the chosen total_risk_pct split across the leg count;
# the server merely places each leg via the existing /orders code path.
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
    tp_level:        str       = Field(..., max_length=8)


class TradeSignalRequest(BaseModel):
    """Fanout request: one account + N order legs.

    Per-leg quantity is computed client-side from the chosen total_risk_pct
    split across `len(legs)` orders. Server records each leg's own
    risk_pct = total / N on bot_trades for auditability.

    If any leg fails at the broker, the others are NOT rolled back — broker
    orders aren't atomic. The response carries placed[] and failed[] so the
    UI can show what landed and let the user retry the failures.
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
    """Place N child orders against a Telegram signal."""
    sig = db.get(TgSignal, signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")

    acct = db.get(TradingAccount, body.account_id)
    if acct is None or acct.user_id != user.id or not acct.is_active:
        raise HTTPException(404, "Trading account not found / not yours / inactive")

    per_order_risk = body.total_risk_pct / Decimal(len(body.legs))

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
        db.flush()

        placed.append({
            "bot_trade_id":     bt.id,
            "order_id":         order_id,
            "leg_index":        idx,
            "tp_level":         leg.tp_level,
            "limit_price":      str(leg.limit_price) if leg.limit_price is not None else None,
            "take_profit":      str(leg.take_profit),
            "quantity":         str(leg.quantity),
            "status":           order_response.get("status"),
            "broker_order_ref": order_response.get("broker_order_ref"),
        })

    db.commit()
    return {
        "signal_id":          signal_id,
        "account_id":         body.account_id,
        "total_risk_pct":     str(body.total_risk_pct),
        "per_order_risk_pct": str(per_order_risk),
        "placed":             placed,
        "failed":             failed,
        "all_ok":             len(failed) == 0,
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


# ---------------------------------------------------------------------------
# Bot positions screen — surfaces only positions opened by the bot.
#
# The /trading-bot/positions screen needs:
#   - List bot-originated positions (= snapshot rows whose
#     broker_position_ref appears in some BrokerOrder linked to a BotTrade
#     owned by this user). Plain account snapshot would include manual
#     positions the user doesn't want touched.
#   - Modify SL (single position) — forwards to broker_gateway
#   - Move SL to entry — same modify, sl = position's avg_open_price
#   - Close one position — forwards
#   - Close all positions for a signal — forwards with refs[] filter
#
# Refresh: clicking Refresh triggers a position-list pull from broker_gateway
# (same as /accounts/{id}/positions does) — that's where the snapshot
# rows get repopulated with the new SL/TP/dealId fields.
# ---------------------------------------------------------------------------
@trading_bot_router.get("/positions")
async def list_bot_positions(
    account_id: Optional[int] = None,
    signal_id: Optional[int] = None,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Positions originating from bot-placed orders, joined with their signal."""

    if refresh:
        # Trigger a fresh pull from each account the user has, then re-read.
        # If the gateway is slow we accept the latency — admin clicked refresh
        # explicitly. We refresh each account in parallel since the user can
        # have multiple Capital.com sub-accounts.
        import asyncio
        import os as _os
        import httpx
        gw = _os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
        acct_q = select(TradingAccount.id).where(
            TradingAccount.user_id == user.id,
            TradingAccount.is_active.is_(True),
        )
        if account_id is not None:
            acct_q = acct_q.where(TradingAccount.id == account_id)
        acct_ids = [r for r in db.execute(acct_q).scalars().all()]

        async def _refresh_one(aid: int):
            try:
                async with httpx.AsyncClient(timeout=20) as c:
                    await c.get(f"{gw}/accounts/{aid}/positions")
            except Exception:
                pass  # best-effort; UI shows stale data on failure

        if acct_ids:
            await asyncio.gather(*[_refresh_one(a) for a in acct_ids])

    # Build the bot-only filter — only positions whose ref appears in a
    # BrokerOrder linked from a BotTrade row owned by this user.
    bot_refs_q = (
        select(BrokerOrder.broker_order_ref)
        .join(BotTrade, BotTrade.order_id == BrokerOrder.id)
        .where(BotTrade.user_id == user.id,
               BrokerOrder.broker_order_ref.is_not(None))
    )
    if signal_id is not None:
        bot_refs_q = bot_refs_q.where(BotTrade.signal_id == signal_id)
    bot_refs = [r for r in db.execute(bot_refs_q).scalars().all()]

    if not bot_refs:
        return []

    # Join snapshot with the bot_trade context (signal info).
    q = (
        select(BrokerPositionSnapshot, BotTrade, TgSignal, TradingAccount, Broker, BrokerOrder)
        .join(BrokerOrder,
              BrokerOrder.broker_order_ref == BrokerPositionSnapshot.broker_position_ref)
        .join(BotTrade, BotTrade.order_id == BrokerOrder.id)
        .outerjoin(TgSignal, TgSignal.id == BotTrade.signal_id)
        .join(TradingAccount, TradingAccount.id == BrokerPositionSnapshot.account_id)
        .join(Broker, Broker.id == TradingAccount.broker_id)
        .where(BotTrade.user_id == user.id,
               BrokerPositionSnapshot.broker_position_ref.in_(bot_refs))
        .order_by(desc(BrokerPositionSnapshot.fetched_at))
    )
    if account_id is not None:
        q = q.where(BrokerPositionSnapshot.account_id == account_id)
    if signal_id is not None:
        q = q.where(BotTrade.signal_id == signal_id)

    out = []
    for snap, bt, sig, acct, broker, order in db.execute(q).all():
        out.append({
            "snapshot_id":         snap.id,
            "broker_position_ref": snap.broker_position_ref,
            "broker_symbol":       snap.broker_symbol,
            "quantity":            _dec(snap.quantity),
            "avg_open_price":      _dec(snap.avg_open_price),
            "current_price":       _dec(snap.current_price),
            "unrealized_pl":       _dec(snap.unrealized_pl),
            "unrealized_pl_pct":   _dec(snap.unrealized_pl_pct),
            "stop_loss":           _dec(snap.stop_loss),
            "take_profit":         _dec(snap.take_profit),
            "currency":            snap.currency,
            "direction":           snap.direction,
            "opened_at":           snap.opened_at,
            "fetched_at":          snap.fetched_at,
            "account": {
                "account_id":  acct.id,
                "broker_code": broker.code,
                "broker_name": broker.name,
                "label":       acct.label,
            },
            "bot_trade": {
                "bot_trade_id": bt.id,
                "tp_level":     bt.tp_level,
                "risk_pct":     _dec(bt.risk_pct),
            },
            "signal": {
                "id":             sig.id if sig else None,
                "channel_title":  sig.channel_title if sig else None,
                "direction":      sig.direction if sig else None,
                "signal_time":    sig.signal_time if sig else None,
            } if sig else None,
        })
    return out


class ModifyPositionIn(BaseModel):
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@trading_bot_router.patch("/positions/{position_ref}")
async def modify_bot_position(
    position_ref: str,
    body: ModifyPositionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Forward modify request to broker_gateway after verifying ownership."""
    snap, _broker = _verify_position_ownership(db, user, position_ref)
    return await _gateway_call("PATCH",
        f"/accounts/{snap.account_id}/positions/{position_ref}",
        json={
            "stop_loss":   str(body.stop_loss)   if body.stop_loss   is not None else None,
            "take_profit": str(body.take_profit) if body.take_profit is not None else None,
        })


@trading_bot_router.post("/positions/{position_ref}/move-sl-to-entry")
async def move_sl_to_entry(
    position_ref: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Convenience: set SL to the position's avg_open_price (breakeven).

    This is one of the most-common manual operations on running trades.
    Doing it server-side avoids a round trip for the frontend to look up
    avg_open_price first.
    """
    snap, _broker = _verify_position_ownership(db, user, position_ref)
    if snap.avg_open_price is None:
        raise HTTPException(409,
            "Position has no avg_open_price — refresh positions first.")
    return await _gateway_call("PATCH",
        f"/accounts/{snap.account_id}/positions/{position_ref}",
        json={"stop_loss": str(snap.avg_open_price), "take_profit": None})


@trading_bot_router.delete("/positions/{position_ref}")
async def close_bot_position(
    position_ref: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Close a single bot position by ref."""
    snap, _broker = _verify_position_ownership(db, user, position_ref)
    return await _gateway_call("DELETE",
        f"/accounts/{snap.account_id}/positions/{position_ref}")


class CloseManyPositionsIn(BaseModel):
    """Either signal_id (= close all positions for that signal) OR
    explicit refs[]. Account_id is required either way (a request can't
    close across multiple accounts atomically anyway).
    """
    account_id: int
    signal_id: Optional[int] = None
    refs: Optional[list[str]] = None


@trading_bot_router.post("/positions/close-many")
async def close_many_bot_positions(
    body: CloseManyPositionsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Close many bot positions at once.

    Mode 1: pass `refs=[...]` directly — closes exactly those.
    Mode 2: pass `signal_id=N` — closes every bot position linked to that
            signal on the given account.
    """
    # Verify the account is the user's.
    acct = db.get(TradingAccount, body.account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found / not yours")

    if body.refs:
        refs = list(body.refs)
    elif body.signal_id is not None:
        # Resolve all bot-positions for the signal on this account.
        rows = db.execute(
            select(BrokerPositionSnapshot.broker_position_ref)
            .join(BrokerOrder,
                  BrokerOrder.broker_order_ref == BrokerPositionSnapshot.broker_position_ref)
            .join(BotTrade, BotTrade.order_id == BrokerOrder.id)
            .where(BotTrade.user_id == user.id,
                   BotTrade.signal_id == body.signal_id,
                   BrokerPositionSnapshot.account_id == body.account_id,
                   BrokerPositionSnapshot.broker_position_ref.is_not(None))
        ).scalars().all()
        refs = [r for r in rows if r]
    else:
        raise HTTPException(400, "Pass either signal_id or refs[]")

    if not refs:
        return {"results": [], "closed_count": 0, "failed_count": 0}

    # Sanity gate: every ref must belong to a position currently owned by
    # the user on this account. Prevents an attacker from passing in an
    # arbitrary deal_id and closing someone else's position.
    valid_refs = set(db.execute(
        select(BrokerPositionSnapshot.broker_position_ref)
        .where(BrokerPositionSnapshot.account_id == body.account_id,
               BrokerPositionSnapshot.broker_position_ref.in_(refs))
    ).scalars().all())
    safe_refs = [r for r in refs if r in valid_refs]
    if len(safe_refs) != len(refs):
        # Quiet — we don't echo back the rejected refs.
        pass

    if not safe_refs:
        return {"results": [], "closed_count": 0, "failed_count": 0}

    return await _gateway_call("POST",
        f"/accounts/{body.account_id}/positions/close-all",
        json={"refs": safe_refs})


# Helpers shared by the routes above
def _verify_position_ownership(db: Session, user: User, position_ref: str):
    """Return (snapshot_row, broker) or raise 404. Verifies that the position
    belongs to one of the user's bot trades — not just any position on the
    account. Prevents a user from closing manual positions via the bot UI.
    """
    row = db.execute(
        select(BrokerPositionSnapshot, Broker)
        .join(TradingAccount, TradingAccount.id == BrokerPositionSnapshot.account_id)
        .join(Broker, Broker.id == TradingAccount.broker_id)
        .join(BrokerOrder,
              BrokerOrder.broker_order_ref == BrokerPositionSnapshot.broker_position_ref)
        .join(BotTrade, BotTrade.order_id == BrokerOrder.id)
        .where(BotTrade.user_id == user.id,
               BrokerPositionSnapshot.broker_position_ref == position_ref)
    ).first()
    if row is None:
        raise HTTPException(404,
            f"Bot position '{position_ref}' not found / not yours")
    return row


async def _gateway_call(method: str, path: str, json: Optional[dict] = None):
    """Forward to broker_gateway and surface its error as our own."""
    import os as _os
    import httpx
    base = _os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(method, f"{base}{path}", json=json)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"broker_gateway unreachable: {exc}")
    if r.status_code >= 400:
        # Pass through gateway error verbatim so HTTP codes are meaningful.
        try:
            detail = r.json().get("detail") or r.text
        except Exception:
            detail = r.text
        raise HTTPException(r.status_code, detail or "Gateway error")
    return r.json()
