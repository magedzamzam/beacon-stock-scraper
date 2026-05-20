"""Recommender pipeline — v2.0 (Sector-Aware, Schema-Validated).

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
    SessionLocal, Stock, StockAnalystConsensus,
    PortfolioPosition, PositionRecommendation,
    # Round-4: read scoring inputs from new parallel tables.
    StockHistoryQuote, StockFinRatios, StockFinStatement, StockFinCashflow,
    StockMktTechnicals, StockMktDividends,
    # Round-4: write canonical row + scoring history.
    StockQuote, StockScoring,
)
from shared.logging_setup import configure_logging

from .scoring import (
    StockMetrics, compute_score, recommend_position, PositionContext,
    MODEL_VERSION,
)

log = configure_logging("recommender")


def _f(x) -> Optional[float]:
    return float(x) if x is not None else None


def _safe_div(a, b) -> Optional[float]:
    """Safely divide two values, returning None on any error."""
    if a is None or b is None:
        return None
    try:
        b_f = float(b)
        if b_f == 0:
            return None
        return float(a) / b_f
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def gather_metrics(session, stock_id: int) -> StockMetrics:
    """Pull the latest available row from each new parallel-schema table and
    build StockMetrics for the scoring engine.

    v2.0 validated against beacon_schema.sql:
      - sector from Stock table
      - ps_ratio, ev_sales, peg_ratio, roic, z_score from stock_fin_ratios
      - gross_profit, revenue_growth_3y, shares_insiders_pct from stock_fin_statement
      - operating_cash_flow from stock_fin_cashflow
      - free_float_pct NOT in schema → omitted (graceful None)
      - interest_coverage NOT in schema → omitted
      - earnings_volatility NOT in schema → omitted
    """
    # --- Stock metadata (sector) ---
    stock = session.get(Stock, stock_id)
    sector = stock.sector if stock else None

    # --- Latest history quote (close, market_cap) ---
    hq = session.execute(
        select(StockHistoryQuote)
        .where(StockHistoryQuote.stock_id == stock_id)
        .order_by(desc(StockHistoryQuote.trading_date))
        .limit(1)
    ).scalar_one_or_none()

    # --- Latest valuation ratios (PE, PB, EV/EBITDA, P/S, EV/Sales, PEG, ROIC, Z) ---
    ratios = session.execute(
        select(StockFinRatios)
        .where(StockFinRatios.stock_id == stock_id)
        .order_by(desc(StockFinRatios.period_end), desc(StockFinRatios.id))
        .limit(1)
    ).scalar_one_or_none()

    # --- Latest two P&L periods (for YoY revenue growth, net margin) ---
    fin = session.execute(
        select(StockFinStatement)
        .where(StockFinStatement.stock_id == stock_id,
               StockFinStatement.is_estimate.is_(False))
        .order_by(desc(StockFinStatement.period_end), desc(StockFinStatement.id))
        .limit(2)
    ).scalars().all()

    # --- Latest dividend metrics ---
    div = session.execute(
        select(StockMktDividends)
        .where(StockMktDividends.stock_id == stock_id)
    ).scalar_one_or_none()

    # --- Latest technicals (RSI/SMA/52w/beta + momentum windows) ---
    tech = session.execute(
        select(StockMktTechnicals)
        .where(StockMktTechnicals.stock_id == stock_id)
        .order_by(desc(StockMktTechnicals.trading_date))
        .limit(1)
    ).scalar_one_or_none()

    # --- Latest analyst consensus ---
    ana = session.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == stock_id)
        .order_by(desc(StockAnalystConsensus.consensus_date))
        .limit(1)
    ).scalar_one_or_none()

    # --- Latest cashflow (for CFO/NI) ---
    cf = session.execute(
        select(StockFinCashflow)
        .where(StockFinCashflow.stock_id == stock_id,
               StockFinCashflow.is_estimate.is_(False))
        .order_by(desc(StockFinCashflow.period_end), desc(StockFinCashflow.id))
        .limit(1)
    ).scalar_one_or_none()

    # --- Derived: revenue growth YoY ---
    rev_growth = None
    if fin:
        rev_growth = _f(fin[0].revenue_growth_yoy)
        if rev_growth is None and len(fin) >= 2:
            rev_growth = _safe_div(
                float(fin[0].revenue) - float(fin[1].revenue),
                float(fin[1].revenue)
            )
            if rev_growth is not None:
                rev_growth *= 100

    # --- Derived: net margin ---
    net_margin = None
    if fin and fin[0].revenue and fin[0].net_income:
        net_margin = _safe_div(fin[0].net_income, fin[0].revenue)
        if net_margin is not None:
            net_margin *= 100

    # --- Derived: gross margin ---
    gross_margin = None
    if fin and fin[0].revenue and fin[0].gross_profit:
        gross_margin = _safe_div(fin[0].gross_profit, fin[0].revenue)
        if gross_margin is not None:
            gross_margin *= 100

    # --- Derived: 3Y revenue CAGR (if pre-computed) ---
    rev_cagr_3y = _f(fin[0].revenue_growth_3y) if fin else None

    # --- Derived: Net Cash per Share ---
    net_cpc = None
    if fin and fin[0].net_cash and fin[0].shares_outstanding:
        net_cpc = _safe_div(fin[0].net_cash, fin[0].shares_outstanding)

    # --- Derived: CFO / Net Income (earnings quality) ---
    # FIXED: schema column is operating_cash_flow (with underscore)
    cfo_to_ni = None
    if cf and fin and fin[0].net_income:
        cfo_to_ni = _safe_div(cf.operating_cash_flow, fin[0].net_income)

    return StockMetrics(
        sector=sector,
        revenue_growth_pct=rev_growth,
        net_margin_pct=net_margin,
        roe_pct=_f(ratios.roe if ratios else None),
        eps_growth_pct=_f(ratios.eps_growth_yoy if ratios else None),
        gross_margin_pct=gross_margin,
        revenue_growth_3y_cagr=rev_cagr_3y,
        pe_ratio=_f(ratios.pe_ratio if ratios else None),
        pb_ratio=_f(ratios.pb_ratio if ratios else None),
        ev_ebitda=_f(ratios.ev_ebitda if ratios else None),
        ps_ratio=_f(ratios.ps_ratio if ratios else None),
        ev_sales=_f(ratios.ev_sales if ratios else None),
        peg_ratio=_f(ratios.peg_ratio if ratios else None),
        dividend_yield_pct=_f(div.dividend_yield_pct if div else None),
        return_1m=_f(tech.price_chg_1m_pct if tech else None),
        return_3m=_f(tech.price_chg_3m_pct if tech else None),
        return_6m=_f(tech.price_chg_6m_pct if tech else None),
        return_1y=_f(tech.price_chg_1y_pct if tech else None),
        rsi_14=_f(tech.rsi_14 if tech else None),
        last_close=_f(hq.close_price if hq else None),
        sma_50=_f(tech.sma_50 if tech else None),
        sma_200=_f(tech.sma_200 if tech else None),
        week_52_high=_f(tech.week_52_high if tech else None),
        week_52_low=_f(tech.week_52_low if tech else None),
        analyst_rating=ana.rating if ana else None,
        analyst_count=ana.analyst_count if ana else None,
        analyst_upside_pct=_f(ana.implied_upside_pct if ana else None),
        debt_to_equity=_f(ratios.debt_to_equity if ratios else None),
        current_ratio=_f(ratios.current_ratio if ratios else None),
        fcf_yield=_f(ratios.fcf_yield if ratios else None),
        roic_pct=_f(ratios.roic if ratios else None),
        cfo_to_net_income=cfo_to_ni,
        beta=_f(tech.beta if tech else None),
        free_float_pct=None,  # NOT in schema — gracefully None
        cash_per_share=net_cpc,
        z_score=_f(ratios.z_score if ratios else None),
        shares_insiders_pct=_f(fin[0].shares_insiders_pct if fin else None),
    )


def _score_and_persist(session, stock_id: int, today: date) -> str:
    """Score one stock, append to stock_scoring history + denormalise onto
    stock_quotes (canonical row), return verdict.

    Caller owns the session lifecycle (commit/rollback).
    """
    metrics = gather_metrics(session, stock_id)
    result = compute_score(metrics)

    # Append to stock_scoring (history). v2.0: store all sub-scores.
    # NOTE: confidence and data_completeness_pct are stored in inputs_snapshot
    #       because they don't exist as dedicated columns in stock_scoring table.
    session.add(StockScoring(
        stock_id=stock_id,
        composite_score=result.composite,
        verdict=result.verdict,
        score_valuation=result.valuation,
        score_momentum=result.momentum,
        score_quality=result.quality,
        score_risk=result.risk,
        score_growth=result.fundamental,
        score_income=result.technical,
        pros=result.pros,
        cons=result.cons,
        risk_flags=None,
        model_version=MODEL_VERSION,
        inputs_snapshot={
            "fundamental_score": float(result.fundamental) if result.fundamental is not None else None,
            "technical_score": float(result.technical) if result.technical is not None else None,
            "analyst_score": float(result.analyst) if result.analyst is not None else None,
            "score_date": str(today),
            "data_completeness_pct": result.data_completeness_pct,
            "confidence": result.confidence,
        },
        updated_at=datetime.utcnow(),
    ))

    # Denormalise composite_score + verdict onto stock_quotes (canonical row).
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

            # Latest close from canonical stock_quotes row
            snap = session.get(StockQuote, pos.stock_id)
            current_price = float(snap.current_price) if snap and snap.current_price else None
            if current_price is None or metrics.last_close is None:
                continue

            # FIXED: use pos.entry_date instead of pos.opened_at (not in schema)
            holding_days = None
            if pos.entry_date:
                holding_days = (today - pos.entry_date).days
            elif pos.created_at:
                holding_days = (today - pos.created_at.date()).days

            ctx = PositionContext(
                avg_entry_price=float(pos.avg_entry_price),
                current_price=current_price,
                stock_score=stock_score,
                holding_days=holding_days,
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