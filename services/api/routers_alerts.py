"""Admin API for alert rules / channels.

Routes (mounted under /admin/alerts):
    GET    /admin/alerts/meta                  rule + channel UI metadata
    GET    /admin/alerts/channels              list user's channels
    POST   /admin/alerts/channels              create channel
    PATCH  /admin/alerts/channels/{id}         update channel
    DELETE /admin/alerts/channels/{id}         delete channel
    GET    /admin/alerts/rules                 list user's rules
    POST   /admin/alerts/rules                 create rule
    PATCH  /admin/alerts/rules/{id}            update rule
    DELETE /admin/alerts/rules/{id}            delete rule
    POST   /admin/alerts/rules/{id}/test-fire  send a synthetic alert through wired channels
    POST   /admin/alerts/evaluate-now          one-shot evaluation of every enabled rule
    GET    /admin/alerts/events                recent fired alerts (audit)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shared.db import AlertChannel, AlertEvent, AlertRule, AlertRuleChannel, User
from .alerts.channels import CHANNEL_REGISTRY, get_channel_meta
from .alerts.engine import evaluate_all, test_fire
from .alerts.rules import RULE_REGISTRY, get_rule_meta
from .auth import get_current_user, get_db


alerts_router = APIRouter(prefix="/admin/alerts", tags=["alerts"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


# ---------------------------------------------------------------------------
# Metadata — used by the UI to render rule/channel forms
# ---------------------------------------------------------------------------
@alerts_router.get("/meta")
def get_meta(_: User = Depends(_require_admin)):
    return {
        "rules": get_rule_meta(),
        "channels": get_channel_meta(),
    }


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
class ChannelIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    channel_type: str = Field(..., min_length=1, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


def _channel_out(c: AlertChannel) -> dict:
    return {
        "id": c.id, "name": c.name, "channel_type": c.channel_type,
        "config": c.config, "is_active": c.is_active,
        "created_at": c.created_at, "updated_at": c.updated_at,
    }


@alerts_router.get("/channels")
def list_channels(user: User = Depends(_require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(AlertChannel).where(AlertChannel.user_id == user.id)
        .order_by(AlertChannel.id.desc())
    ).scalars().all()
    return [_channel_out(c) for c in rows]


@alerts_router.post("/channels")
def create_channel(req: ChannelIn, user: User = Depends(_require_admin),
                   db: Session = Depends(get_db)):
    if req.channel_type not in CHANNEL_REGISTRY:
        raise HTTPException(400, f"Unknown channel_type '{req.channel_type}'. "
                                  f"Valid: {list(CHANNEL_REGISTRY)}")
    c = AlertChannel(user_id=user.id, **req.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return _channel_out(c)


@alerts_router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, req: ChannelUpdate,
                   user: User = Depends(_require_admin),
                   db: Session = Depends(get_db)):
    c = db.get(AlertChannel, channel_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Channel not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_at = datetime.utcnow()
    db.commit(); db.refresh(c)
    return _channel_out(c)


@alerts_router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int, user: User = Depends(_require_admin),
                   db: Session = Depends(get_db)):
    c = db.get(AlertChannel, channel_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Channel not found")
    db.delete(c); db.commit()
    return {"deleted": channel_id}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class RuleIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    rule_type: str = Field(..., min_length=1, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)
    stock_filter: Optional[dict[str, Any]] = None
    interval_seconds: int = Field(60, ge=10, le=86400)
    cooldown_seconds: int = Field(3600, ge=0, le=7 * 86400)
    is_enabled: bool = True
    channel_ids: list[int] = Field(default_factory=list)


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    params: Optional[dict[str, Any]] = None
    stock_filter: Optional[dict[str, Any]] = None
    interval_seconds: Optional[int] = Field(None, ge=10, le=86400)
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=7 * 86400)
    is_enabled: Optional[bool] = None
    channel_ids: Optional[list[int]] = None


def _rule_out(db: Session, r: AlertRule) -> dict:
    ch_ids = db.execute(
        select(AlertRuleChannel.channel_id).where(AlertRuleChannel.rule_id == r.id)
    ).scalars().all()
    return {
        "id": r.id, "name": r.name, "rule_type": r.rule_type,
        "params": r.params, "stock_filter": r.stock_filter,
        "interval_seconds": r.interval_seconds,
        "cooldown_seconds": r.cooldown_seconds,
        "is_enabled": r.is_enabled,
        "last_evaluated_at": r.last_evaluated_at,
        "last_error": r.last_error,
        "channel_ids": list(ch_ids),
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


def _set_rule_channels(db: Session, rule_id: int, channel_ids: list[int]):
    """Replace the rule's channel wiring with `channel_ids`. Validates IDs."""
    db.query(AlertRuleChannel).filter(AlertRuleChannel.rule_id == rule_id).delete()
    for cid in set(channel_ids):
        db.add(AlertRuleChannel(rule_id=rule_id, channel_id=cid))


@alerts_router.get("/rules")
def list_rules(user: User = Depends(_require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(AlertRule).where(AlertRule.user_id == user.id)
        .order_by(AlertRule.id.desc())
    ).scalars().all()
    return [_rule_out(db, r) for r in rows]


@alerts_router.post("/rules")
def create_rule(req: RuleIn, user: User = Depends(_require_admin),
                db: Session = Depends(get_db)):
    if req.rule_type not in RULE_REGISTRY:
        raise HTTPException(400, f"Unknown rule_type '{req.rule_type}'. "
                                  f"Valid: {list(RULE_REGISTRY)}")
    body = req.model_dump(exclude={"channel_ids"})
    r = AlertRule(user_id=user.id, **body)
    db.add(r); db.flush()
    _set_rule_channels(db, r.id, req.channel_ids)
    db.commit(); db.refresh(r)
    return _rule_out(db, r)


@alerts_router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, req: RuleUpdate,
                user: User = Depends(_require_admin),
                db: Session = Depends(get_db)):
    r = db.get(AlertRule, rule_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    body = req.model_dump(exclude_unset=True)
    channel_ids = body.pop("channel_ids", None)
    for k, v in body.items():
        setattr(r, k, v)
    r.updated_at = datetime.utcnow()
    if channel_ids is not None:
        _set_rule_channels(db, rule_id, channel_ids)
    db.commit(); db.refresh(r)
    return _rule_out(db, r)


@alerts_router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: User = Depends(_require_admin),
                db: Session = Depends(get_db)):
    r = db.get(AlertRule, rule_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    db.delete(r); db.commit()
    return {"deleted": rule_id}


@alerts_router.post("/rules/{rule_id}/test-fire")
def rule_test_fire(rule_id: int, user: User = Depends(_require_admin),
                   db: Session = Depends(get_db)):
    r = db.get(AlertRule, rule_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    return test_fire(db, r)


# ---------------------------------------------------------------------------
# Manual evaluate-now (also called by the scheduler tick)
# ---------------------------------------------------------------------------
@alerts_router.post("/evaluate-now")
def evaluate_now(_: User = Depends(_require_admin), db: Session = Depends(get_db)):
    return evaluate_all(db)


# ---------------------------------------------------------------------------
# Events history
# ---------------------------------------------------------------------------
@alerts_router.get("/events")
def list_events(limit: int = 50, rule_id: Optional[int] = None,
                user: User = Depends(_require_admin), db: Session = Depends(get_db)):
    q = (select(AlertEvent, AlertRule.name)
         .join(AlertRule, AlertRule.id == AlertEvent.rule_id)
         .where(AlertRule.user_id == user.id)
         .order_by(desc(AlertEvent.fired_at))
         .limit(min(max(limit, 1), 200)))
    if rule_id is not None:
        q = q.where(AlertEvent.rule_id == rule_id)
    rows = db.execute(q).all()
    return [
        {
            "id": e.id, "rule_id": e.rule_id, "rule_name": rule_name,
            "stock_id": e.stock_id,
            "fired_at": e.fired_at,
            "title": e.title, "body": e.body,
            "delivery": e.delivery, "snapshot": e.snapshot,
        }
        for (e, rule_name) in rows
    ]
