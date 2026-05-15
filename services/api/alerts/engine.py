"""Alert engine — orchestration.

Called once per minute by the scheduler. For each enabled rule:
  1. Skip if last_evaluated_at + interval_seconds > now
  2. Run the rule's evaluate() to get candidate triggers
  3. For each trigger, look up the most recent fire for (rule, stock) —
     skip if within cooldown
  4. For each survivor, dispatch through every active channel wired to
     the rule, record the alert_events row
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.db import (
    AlertChannel, AlertEvent, AlertRule, AlertRuleChannel,
)

from .channels import CHANNEL_REGISTRY
from .rules import AlertTrigger, RULE_REGISTRY


def _due_rules(session: Session, now: datetime) -> list[AlertRule]:
    """Enabled rules whose last_evaluated_at + interval_seconds <= now.

    Includes rules that have never been evaluated (last_evaluated_at IS NULL).
    """
    return session.execute(
        select(AlertRule).where(
            AlertRule.is_enabled.is_(True),
        )
    ).scalars().all()


def _within_cooldown(session: Session, rule: AlertRule, stock_id: int | None, now: datetime) -> bool:
    """True iff a recent enough event exists for (rule, stock)."""
    cooldown_cutoff = now - timedelta(seconds=rule.cooldown_seconds)
    q = select(AlertEvent.fired_at).where(
        AlertEvent.rule_id == rule.id,
        AlertEvent.fired_at >= cooldown_cutoff,
    )
    if stock_id is None:
        q = q.where(AlertEvent.stock_id.is_(None))
    else:
        q = q.where(AlertEvent.stock_id == stock_id)
    return session.execute(q.limit(1)).scalar() is not None


def _dispatch(session: Session, rule: AlertRule, trigger: AlertTrigger,
              now: datetime) -> dict[str, Any]:
    """Send `trigger` through every channel wired to `rule`. Record the event."""
    channel_ids = session.execute(
        select(AlertRuleChannel.channel_id).where(AlertRuleChannel.rule_id == rule.id)
    ).scalars().all()
    channels = []
    if channel_ids:
        channels = session.execute(
            select(AlertChannel).where(
                AlertChannel.id.in_(channel_ids),
                AlertChannel.is_active.is_(True),
            )
        ).scalars().all()

    delivery: dict[str, Any] = {}
    for ch in channels:
        ch_cls = CHANNEL_REGISTRY.get(ch.channel_type)
        if ch_cls is None:
            delivery[str(ch.id)] = {"status": "failed",
                                    "error": f"unknown channel_type '{ch.channel_type}'"}
            continue
        try:
            ok, err = ch_cls(ch.config or {}).send(trigger.title, trigger.body)
            delivery[str(ch.id)] = {"status": "ok" if ok else "failed", "error": err}
        except Exception as exc:
            delivery[str(ch.id)] = {"status": "failed",
                                    "error": f"{type(exc).__name__}: {exc}"}

    event = AlertEvent(
        rule_id=rule.id,
        stock_id=trigger.stock_id,
        fired_at=now,
        title=trigger.title,
        body=trigger.body,
        delivery=delivery,
        snapshot=trigger.snapshot,
    )
    session.add(event)
    return delivery


def evaluate_all(session: Session) -> dict[str, Any]:
    """Single pass over enabled rules. Returns a summary for the job log."""
    now = datetime.utcnow()
    rules = _due_rules(session, now)

    summary = {
        "rules_total": len(rules),
        "rules_evaluated": 0,
        "rules_skipped_interval": 0,
        "rules_errored": 0,
        "alerts_fired": 0,
        "alerts_skipped_cooldown": 0,
    }

    for rule in rules:
        # Interval gate
        if rule.last_evaluated_at is not None:
            next_due = rule.last_evaluated_at + timedelta(seconds=rule.interval_seconds)
            if next_due > now:
                summary["rules_skipped_interval"] += 1
                continue

        cls = RULE_REGISTRY.get(rule.rule_type)
        if cls is None:
            rule.last_error = f"unknown rule_type '{rule.rule_type}'"
            rule.last_evaluated_at = now
            summary["rules_errored"] += 1
            session.commit()
            continue

        try:
            triggers = cls(rule.params or {}).evaluate(session)
        except Exception as exc:
            session.rollback()
            rule.last_error = f"{type(exc).__name__}: {exc}"
            rule.last_evaluated_at = now
            session.commit()
            summary["rules_errored"] += 1
            continue

        # Optional stock_filter: {"stock_ids": [1, 2, 3]}
        if rule.stock_filter and isinstance(rule.stock_filter, dict):
            allowed = set(rule.stock_filter.get("stock_ids") or [])
            if allowed:
                triggers = [t for t in triggers if t.stock_id in allowed]

        for t in triggers:
            if _within_cooldown(session, rule, t.stock_id, now):
                summary["alerts_skipped_cooldown"] += 1
                continue
            _dispatch(session, rule, t, now)
            summary["alerts_fired"] += 1

        rule.last_error = None
        rule.last_evaluated_at = now
        summary["rules_evaluated"] += 1
        session.commit()

    return summary


def test_fire(session: Session, rule: AlertRule) -> dict[str, Any]:
    """Send a synthetic alert through this rule's channels, ignoring conditions
    and cooldown — useful for verifying notification delivery from the UI.
    """
    trigger = AlertTrigger(
        stock_id=None,
        title=f"[TEST] {rule.name}",
        body=f"This is a test fire for rule '{rule.name}' (type={rule.rule_type}). "
             f"If you received this, the channel is working.",
        snapshot={"test": True},
    )
    delivery = _dispatch(session, rule, trigger, datetime.utcnow())
    session.commit()
    return {"delivery": delivery}
