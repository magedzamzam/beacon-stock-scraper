"""/portfolio/* — positions and live P/L."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from shared.db import (
    Broker, Exchange, PortfolioPosition, PositionRecommendation, Stock,
    TradingAccount, User,
)
from .auth import get_current_user, get_db
from .routers_watchlists import _stock_summary
from .schemas import PortfolioOut, PositionCreateRequest, PositionOut

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _build_position_out(db: Session, pos: PortfolioPosition) -> Optional[PositionOut]:
    stock = _stock_summary(db, pos.stock_id)

    last_rec = db.execute(
        select(PositionRecommendation)
        .where(PositionRecommendation.position_id == pos.id)
        .order_by(desc(PositionRecommendation.score_date)).limit(1)
    ).scalar_one_or_none()

    qty = float(pos.quantity)
    entry = float(pos.avg_entry_price)
    cost = qty * entry
    cur = stock.last_close
    mv = qty * cur if cur is not None else None
    pl = (mv - cost) if mv is not None else None
    plp = (pl / cost * 100.0) if (pl is not None and cost) else None

    reasoning_list: Optional[list[str]] = None
    if last_rec and last_rec.reasoning:
        reasoning = last_rec.reasoning
        if isinstance(reasoning, dict):
            reasoning_list = reasoning.get("reasons") or reasoning.get("notes") or []
            if isinstance(reasoning_list, str):
                reasoning_list = [reasoning_list]
        elif isinstance(reasoning, list):
            reasoning_list = [str(x) for x in reasoning]

    return PositionOut(
        id=pos.id,
        stock=stock,
        quantity=qty,
        avg_entry_price=entry,
        entry_date=pos.entry_date,
        notes=pos.notes,
        cost_basis=cost,
        market_value=mv,
        unrealized_pl=pl,
        unrealized_pl_pct=plp,
        position_verdict=last_rec.verdict if last_rec else None,
        position_confidence=_f(last_rec.confidence) if last_rec else None,
        position_reasoning=reasoning_list,
    )


@router.get("", response_model=PortfolioOut)
def get_portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    positions = db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.user_id == user.id, PortfolioPosition.is_open.is_(True))
        .order_by(PortfolioPosition.created_at)
    ).scalars().all()

    out_positions: list[PositionOut] = []
    total_cost = 0.0
    total_value = 0.0
    for pos in positions:
        try:
            po = _build_position_out(db, pos)
        except HTTPException:
            continue
        if po is None:
            continue
        total_cost += po.cost_basis
        if po.market_value is not None:
            total_value += po.market_value
        out_positions.append(po)

    total_pl = total_value - total_cost
    total_pl_pct = (total_pl / total_cost * 100.0) if total_cost else 0.0
    return PortfolioOut(
        positions=out_positions,
        total_cost=total_cost,
        total_value=total_value,
        total_pl=total_pl,
        total_pl_pct=total_pl_pct,
    )


@router.post("", response_model=PositionOut)
def create_position(
    req: PositionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not db.get(Stock, req.stock_id):
        raise HTTPException(404, "Stock not found")

    # Validate the optional account: must belong to the user, must be active,
    # and must be a MANUAL broker. Automated accounts get their positions
    # from the broker_gateway (broker_positions_snapshot), not portfolio_positions.
    if req.account_id is not None:
        acct = db.get(TradingAccount, req.account_id)
        if acct is None or acct.user_id != user.id or not acct.is_active:
            raise HTTPException(404, "Trading account not found")
        broker = db.get(Broker, acct.broker_id)
        if broker is None or broker.kind != "manual":
            raise HTTPException(
                400,
                "Only manual accounts can hold portfolio_positions. "
                "Automated accounts pull positions live from the broker.",
            )

    pos = PortfolioPosition(
        user_id=user.id, stock_id=req.stock_id, account_id=req.account_id,
        quantity=req.quantity, avg_entry_price=req.avg_entry_price,
        entry_date=req.entry_date or date.today(), notes=req.notes, is_open=True,
    )
    db.add(pos); db.commit(); db.refresh(pos)
    return _build_position_out(db, pos)


@router.delete("/{position_id}", status_code=204)
def close_position(
    position_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pos = db.get(PortfolioPosition, position_id)
    if not pos or pos.user_id != user.id:
        raise HTTPException(404, "Not found")
    pos.is_open = False
    db.commit()
