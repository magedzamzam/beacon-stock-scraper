"""Recommender pipeline.

Reads the latest data for each stock from the DB and produces:
    1. stock_recommendations  — daily verdict + sub-scores per stock
    2. position_recommendations — HOLD/SELL/BUY_MORE per open portfolio position
    3. updates the cached verdict in stock_latest_snapshot
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.db import (
    SessionLocal, Stock, StockMarketDaily, StockPerformanceDaily, StockValuation,
    StockFinancials, StockTechnicals, StockAnalystConsensus, StockRecommendation,
    PortfolioPosition, PositionRecommendation, StockLatestSnapshot,
    # Round-2 dual-write targets:
    StockQuote, StockScoring,
)
from shared.logging_setup import configure_logging

from .scoring import (
    StockMetrics, compute_score, recommend_position, PositionContext,
)

log = configure_logging("recommender")


def _f(x) -> Optional[float]:
    return float(x) if x is not None else None


def gather_metrics(session, stock_id: int) -> StockMetrics:
    """Pull the latest available row from each table and build StockMetrics."""
    md = session.execute(
        select(StockMarketDaily)
        .where(StockMarketDaily.stock_id == stock_id)
        .order_by(desc(StockMarketDaily.trading_date))
        .limit(1)
    ).scalar_one_or_none()

    perf = session.execute(
        select(StockPerformanceDaily)
        .where(StockPerformanceDaily.stock_id == stock_id)
        .order_by(desc(StockPerformanceDaily.trading_date))
        .limit(1)
    ).scalar_one_or_none()

    val = session.execute(
        select(StockValuation)
        .where(StockValuation.stock_id == stock_id)
        .order_by(desc(StockValuation.fiscal_year))
        .limit(1)
    ).scalar_one_or_none()

    fin = session.execute(
        select(StockFinancials)
        .where(StockFinancials.stock_id == stock_id)
        .order_by(desc(StockFinancials.fiscal_year))
        .limit(2)
    ).scalars().all()

    tech = session.execute(
        select(StockTechnicals)
        .where(StockTechnicals.stock_id == stock_id)
        .order_by(desc(StockTechnicals.trading_date))
        .limit(1)
    ).scalar_one_or_none()

    ana = session.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == stock_id)
        .order_by(desc(StockAnalystConsensus.consensus_date))
        .limit(1)
    ).scalar_one_or_none()

    # Compute revenue growth & margin if we have 2 years
    rev_growth = None
    if len(fin) >= 2 and fin[0].revenue and fin[1].revenue:
        try:
            rev_growth = (float(fin[0].revenue) - float(fin[1].revenue)) / float(fin[1].revenue) * 100
        except ZeroDivisionError:
            pass

    net_margin = None
    if fin and fin[0].revenue and fin[0].net_income:
        try:
            net_margin = float(fin[0].net_income) / float(fin[0].revenue) * 100
        except ZeroDivisionError:
            pass

    roe = None
    if fin and fin[0].total_equity and fin[0].net_income:
        try:
            roe = float(fin[0].net_income) / float(fin[0].total_equity) * 100
        except ZeroDivisionError:
            pass

    debt_eq = None
    if fin and fin[0].total_equity and fin[0].total_debt:
        try:
            debt_eq = float(fin[0].total_debt) / float(fin[0].total_equity)
        except ZeroDivisionError:
            pass

    return StockMetrics(
        revenue_growth_pct=rev_growth,
        net_margin_pct=net_margin,
        roe_pct=roe,
        pe_ratio=_f(md.pe_ratio if md else None) or _f(val.pe if val else None),
        pb_ratio=_f(val.price_to_book if val else None),
        ev_ebitda=_f(val.ev_ebitda if val else None),
        dividend_yield_pct=_f(md.dividend_yield_pct if md else None),
        return_1m=_f(perf.return_1m if perf else None),
        return_3m=_f(perf.return_3m if perf else None),
        return_6m=_f(perf.return_6m if perf else None),
        return_1y=_f(perf.return_1y if perf else None),
        rsi_14=_f(tech.rsi_14 if tech else None),
        last_close=_f(md.close_price if md else None),
        sma_50=_f(tech.sma_50 if tech else None),
        sma_200=_f(tech.sma_200 if tech else None),
        week_52_high=_f(md.week_52_high if md else None),
        week_52_low=_f(md.week_52_low if md else None),
        analyst_rating=ana.rating if ana else None,
        analyst_count=ana.analyst_count if ana else None,
        analyst_upside_pct=_f(ana.implied_upside_pct if ana else None),
        debt_to_equity=debt_eq,
        beta=_f(md.beta if md else None),
        free_float_pct=_f(md.free_float_pct if md else None),
    )


def _score_and_persist(session, stock_id: int, today: date) -> str:
    """Score one stock, upsert recommendation + snapshot, return verdict.

    Caller owns the session lifecycle (commit/rollback). Used both by score_all
    and by the per-stock /score/single endpoint that admins hit after manual
    overrides so the verdict reflects the new inputs immediately.
    """
    metrics = gather_metrics(session, stock_id)
    result = compute_score(metrics)

    stmt = pg_insert(StockRecommendation).values(
        stock_id=stock_id,
        score_date=today,
        fundamental_score=result.fundamental,
        valuation_score=result.valuation,
        momentum_score=result.momentum,
        technical_score=result.technical,
        analyst_score=result.analyst,
        quality_score=result.quality,
        risk_score=result.risk,
        composite_score=result.composite,
        verdict=result.verdict,
        reasoning={"pros": result.pros, "cons": result.cons},
        model_version="v1.1",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "score_date"],
        set_={
            "fundamental_score": stmt.excluded.fundamental_score,
            "valuation_score":   stmt.excluded.valuation_score,
            "momentum_score":    stmt.excluded.momentum_score,
            "technical_score":   stmt.excluded.technical_score,
            "analyst_score":     stmt.excluded.analyst_score,
            "quality_score":     stmt.excluded.quality_score,
            "risk_score":        stmt.excluded.risk_score,
            "composite_score":   stmt.excluded.composite_score,
            "verdict":           stmt.excluded.verdict,
            "reasoning":         stmt.excluded.reasoning,
        },
    )
    session.execute(stmt)

    snap_stmt = pg_insert(StockLatestSnapshot).values(
        stock_id=stock_id,
        composite_score=result.composite,
        verdict=result.verdict,
    ).on_conflict_do_update(
        index_elements=["stock_id"],
        set_={"composite_score": result.composite, "verdict": result.verdict},
    )
    session.execute(snap_stmt)

    # Round-2 dual-write: append a row to stock_scoring (new history table).
    # Component scores cut differently from the old StockRecommendation:
    #   old fundamental → mapped to score_quality (best fit)
    #   old technical   → mapped to score_momentum
    #   old analyst     → no direct equivalent — preserved in inputs_snapshot
    session.add(StockScoring(
        stock_id=stock_id,
        composite_score=result.composite,
        verdict=result.verdict,
        score_valuation=result.valuation,
        score_momentum=result.momentum,
        score_quality=result.quality,
        score_risk=result.risk,
        # score_growth, score_income left NULL — old model didn't compute them
        pros=result.pros,
        cons=result.cons,
        risk_flags=None,
        model_version="v1.1",
        inputs_snapshot={
            "fundamental_score": float(result.fundamental) if result.fundamental is not None else None,
            "technical_score": float(result.technical) if result.technical is not None else None,
            "analyst_score": float(result.analyst) if result.analyst is not None else None,
            "score_date": str(today),
        },
        updated_at=datetime.utcnow(),
    ))

    # Round-2 dual-write: also denormalise composite_score + verdict onto
    # stock_quotes (the canonical row). Preserve other columns by only setting
    # the two we own here.
    sq_stmt = pg_insert(StockQuote).values(
        stock_id=stock_id,
        composite_score=result.composite,
        verdict=result.verdict,
        last_updated=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["stock_id"],
        set_={
            "composite_score": result.composite,
            "verdict": result.verdict,
            "last_updated": datetime.utcnow(),
        },
    )
    session.execute(sq_stmt)

    return result.verdict


def score_one(stock_id: int) -> dict:
    """Public single-stock scoring entrypoint. Returns the new verdict."""
    today = date.today()
    with SessionLocal() as session:
        verdict = _score_and_persist(session, stock_id, today)
        session.commit()
    return {"stock_id": stock_id, "verdict": verdict}


def score_all() -> dict:
    today = date.today()
    counts = {"BUY": 0, "WATCH": 0, "STAY_AWAY": 0, "errors": 0}

    with SessionLocal() as session:
        stock_ids = [r[0] for r in session.execute(
            select(Stock.id).where(Stock.active.is_(True))
        ).all()]

    for stock_id in stock_ids:
        try:
            with SessionLocal() as session:
                verdict = _score_and_persist(session, stock_id, today)
                session.commit()
                counts[verdict] += 1
        except Exception as exc:
            log.exception("score_failed", stock_id=stock_id, error=str(exc))
            counts["errors"] += 1

    log.info("score_batch_done", **counts)
    return counts


def score_portfolio() -> dict:
    """For every open position, compute HOLD/SELL/BUY_MORE."""
    today = date.today()
    n = 0
    with SessionLocal() as session:
        positions = session.execute(
            select(PortfolioPosition).where(PortfolioPosition.is_open.is_(True))
        ).scalars().all()

        for pos in positions:
            metrics = gather_metrics(session, pos.stock_id)
            stock_score = compute_score(metrics)

            # Latest close from snapshot
            snap = session.get(StockLatestSnapshot, pos.stock_id)
            current_price = float(snap.last_close) if snap and snap.last_close else None
            if current_price is None or metrics.last_close is None:
                continue

            ctx = PositionContext(
                avg_entry_price=float(pos.avg_entry_price),
                current_price=current_price,
                stock_score=stock_score,
            )
            rec = recommend_position(ctx)

            stmt = pg_insert(PositionRecommendation).values(
                position_id=pos.id,
                score_date=today,
                current_price=current_price,
                unrealized_pl_pct=rec["unrealized_pl_pct"],
                verdict=rec["verdict"],
                confidence=rec["confidence"],
                reasoning=rec["reasoning"],
            ).on_conflict_do_update(
                index_elements=["position_id", "score_date"],
                set_={
                    "current_price": current_price,
                    "unrealized_pl_pct": rec["unrealized_pl_pct"],
                    "verdict": rec["verdict"],
                    "confidence": rec["confidence"],
                    "reasoning": rec["reasoning"],
                },
            )
            session.execute(stmt)
            n += 1
        session.commit()

    log.info("portfolio_scored", positions=n)
    return {"positions": n}
