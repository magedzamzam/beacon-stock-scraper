"""Trading Bot — read endpoints for the /trading-bot page + admin CRUD for
channels.

Milestone 1 endpoints (no trade execution yet):
    GET    /trading-bot/signals?limit=50      recent parsed signals (latest first)
    GET    /trading-bot/raw?limit=50          recent raw messages (audit / debug)
    GET    /trading-bot/channels              list channels
    POST   /trading-bot/channels              admin: add channel
    PATCH  /trading-bot/channels/{id}         admin: enable / rename / change parser
    DELETE /trading-bot/channels/{id}         admin: remove channel

The listener service polls tg_channels every 60s, so changes take effect
without a service restart.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shared.db import TgChannel, TgRawMessage, TgSignal, User

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
