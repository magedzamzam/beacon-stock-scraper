"""/accounts/{id}/stats and /stats/history — balance/equity/P-L plus history.

Snapshots are written by:
  * the scheduler on a periodic tick (services/scheduler/main.py)
  * this router on demand when the user opens an account view (TTL gate)
  * routers_portfolio.create_position / close_position (event-driven)

Equity formula:
  Automated account: equity = balance + sum(unrealized_pl on open positions)
  Manual account:    balance = NULL,
                     equity = sum(quantity * current_price)
                     where current_price comes from stock_latest_snapshot.

If a position has no current_price (stock not yet scraped, snapshot missing),
it is excluded from equity / unrealized_pl rather than counted at zero — we
prefer "I don't know" over silently understating the account.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shared.db import (
    AccountBalanceSnapshot, Broker, BrokerPositionSnapshot, PortfolioPosition,
    Stock, StockLatestSnapshot, TradingAccount, User,
)

from .auth import get_current_user, get_db


_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
# Re-fetching balance from a broker is "expensive" (a session + REST call).
# We re-snapshot on UI open only when the latest is older than this many seconds.
_STATS_TTL_S = int(os.environ.get("ACCOUNT_STATS_TTL_S", "60"))


stats_router = APIRouter(prefix="/accounts", tags=["accounts"])


def _compute_manual_stats(
    db: Session, account: TradingAccount,
) -> tuple[Optional[Decimal], Optional[Decimal], int, Optional[str]]:
    """Equity & unrealized P/L for a manual account, from local data only."""
    rows = db.execute(
        select(PortfolioPosition, Stock, StockLatestSnapshot)
        .join(Stock, PortfolioPosition.stock_id == Stock.id)
        .outerjoin(StockLatestSnapshot, StockLatestSnapshot.stock_id == Stock.id)
        .where(
            PortfolioPosition.account_id == account.id,
            PortfolioPosition.is_open.is_(True),
        )
    ).all()
    if not rows:
        return Decimal("0"), Decimal("0"), 0, account.currency

    equity = Decimal("0")
    unrealized = Decimal("0")
    counted = 0
    currency_hint: Optional[str] = account.currency
    for (p, s, snap) in rows:
        current = snap.last_close if snap else None
        if current is None:
            continue  # skip rather than guess
        equity += Decimal(str(current)) * Decimal(str(p.quantity))
        unrealized += (Decimal(str(current)) - Decimal(str(p.avg_entry_price))) * Decimal(str(p.quantity))
        counted += 1
        if currency_hint is None and s.currency:
            currency_hint = s.currency
    return equity, unrealized, counted, currency_hint


async def _fetch_automated_stats(
    db: Session, account: TradingAccount,
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal], int, Optional[str]]:
    """Pull balance from the broker, sum unrealized_pl from snapshot, derive equity.

    Returns (balance, available, equity, unrealized_pl, open_position_count, currency).
    Any field can be None if the broker call fails — we keep going so the
    UI gets *some* answer rather than a 502.
    """
    balance: Optional[Decimal] = None
    available: Optional[Decimal] = None
    currency: Optional[str] = account.currency

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{_GATEWAY_URL}/accounts/{account.id}/info")
            if r.status_code < 400:
                info = r.json()
                if info.get("balance") is not None:
                    balance = Decimal(str(info["balance"]))
                if info.get("available") is not None:
                    available = Decimal(str(info["available"]))
                if info.get("currency"):
                    currency = info["currency"]
    except httpx.RequestError:
        pass

    # Sum P/L from the most recent broker positions snapshot we have on file.
    pl_rows = db.execute(
        select(BrokerPositionSnapshot.unrealized_pl)
        .where(BrokerPositionSnapshot.account_id == account.id)
    ).scalars().all()
    unrealized = sum((Decimal(str(x)) for x in pl_rows if x is not None), start=Decimal("0"))
    pos_count = len(pl_rows)

    equity = None
    if balance is not None:
        equity = balance + unrealized

    return balance, available, equity, unrealized, pos_count, currency


@stats_router.get("/{account_id}/stats")
async def account_stats(
    account_id: int,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current balance/equity/P-L. Re-snapshots if stale (> _STATS_TTL_S)."""
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    broker = db.get(Broker, acct.broker_id)

    # Decide if we need a fresh snapshot.
    latest = db.execute(
        select(AccountBalanceSnapshot)
        .where(AccountBalanceSnapshot.account_id == account_id)
        .order_by(desc(AccountBalanceSnapshot.fetched_at))
        .limit(1)
    ).scalar_one_or_none()

    needs_refresh = refresh or latest is None
    if not needs_refresh and latest is not None:
        age = (datetime.utcnow() - latest.fetched_at).total_seconds()
        if age > _STATS_TTL_S:
            needs_refresh = True

    if needs_refresh:
        if broker.kind == "manual":
            equity, unrealized, count, currency = _compute_manual_stats(db, acct)
            snap = AccountBalanceSnapshot(
                account_id=acct.id,
                balance=None, available=None,
                equity=equity, unrealized_pl=unrealized,
                open_position_count=count, currency=currency,
                source="on_demand",
            )
        else:
            balance, available, equity, unrealized, count, currency = await _fetch_automated_stats(db, acct)
            snap = AccountBalanceSnapshot(
                account_id=acct.id,
                balance=balance, available=available,
                equity=equity, unrealized_pl=unrealized,
                open_position_count=count, currency=currency,
                source="on_demand",
            )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        latest = snap

    return {
        "account_id": acct.id,
        "broker_kind": broker.kind,
        "balance": str(latest.balance) if latest.balance is not None else None,
        "available": str(latest.available) if latest.available is not None else None,
        "equity": str(latest.equity) if latest.equity is not None else None,
        "unrealized_pl": str(latest.unrealized_pl) if latest.unrealized_pl is not None else None,
        "open_position_count": latest.open_position_count,
        "currency": latest.currency,
        "fetched_at": latest.fetched_at,
        "source": latest.source,
    }


@stats_router.get("/{account_id}/stats/history")
def stats_history(
    account_id: int,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Time-series of snapshots for charting."""
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        select(AccountBalanceSnapshot)
        .where(
            AccountBalanceSnapshot.account_id == account_id,
            AccountBalanceSnapshot.fetched_at >= cutoff,
        )
        .order_by(AccountBalanceSnapshot.fetched_at)
    ).scalars().all()
    return [{
        "fetched_at": r.fetched_at,
        "balance": str(r.balance) if r.balance is not None else None,
        "equity": str(r.equity) if r.equity is not None else None,
        "unrealized_pl": str(r.unrealized_pl) if r.unrealized_pl is not None else None,
        "currency": r.currency,
        "source": r.source,
    } for r in rows]
