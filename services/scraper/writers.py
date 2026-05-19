"""Database writers — one per topic.

EVERY write goes through `_safe_upsert()`. There is no other path to the DB
from scrapers. This is the choke point that prevents duplicate-row bugs:
each writer declares its conflict columns explicitly, matching the actual
unique constraint in the DB.

`_safe_upsert()` behaviour:
  - Builds an INSERT … ON CONFLICT (conflict_cols) DO UPDATE
  - Only updates non-None values from the new payload (preserves
    previously-good data when a parser couldn't read a field this run)
  - Skips entirely if every non-key field is None (avoids overwriting
    a complete row with all-NULLs)

Tables touched + their conflict_cols (matching beacon_schema.sql):
  stock_news               (stock_id, headline)
  stock_quotes             (stock_id)                 -- PK
  stock_history_quote      (stock_id, trading_date)
  stock_fin_statement      (stock_id, period_end, period_type, is_estimate)
  stock_fin_cashflow       (stock_id, period_end, period_type, is_estimate)
  stock_fin_ratios         (stock_id, period_end, period_type)
  stock_mkt_technicals     (stock_id, trading_date)
  stock_mkt_dividends      (stock_id)                 -- PK
  stock_analyst_consensus  (stock_id, consensus_date)
  stock_earnings_calendar  (stock_id)                 -- PK
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    StockAnalystConsensus, StockEarningsCalendar, StockFinCashflow,
    StockFinRatios, StockFinStatement, StockHistoryQuote, StockMktDividends,
    StockMktTechnicals, StockNews, StockQuote, ScrapeRun,
)


# ---------------------------------------------------------------------------
# Core helper — every writer calls this.
# ---------------------------------------------------------------------------
def _safe_upsert(session: Session, model, payload: dict,
                 conflict_cols: list[str]) -> bool:
    """Insert-or-update one row, never duplicate, never overwrite with NULLs.

    Returns True if a write was attempted, False if we skipped (everything
    was None).
    """
    if not payload:
        return False

    # Skip if EVERY non-key field is None — don't blow away an existing row.
    skip_keys = set(conflict_cols) | {"scraped_at", "updated_at"}
    if not any(payload.get(k) is not None
               for k in payload.keys() if k not in skip_keys):
        return False

    stmt = pg_insert(model).values(**payload)
    update_set = {
        k: stmt.excluded[k]
        for k in payload.keys()
        if k not in conflict_cols and payload[k] is not None
    }
    # Always refresh scraped_at / updated_at if present
    for ts_col in ("scraped_at", "updated_at"):
        if ts_col in payload:
            update_set[ts_col] = stmt.excluded[ts_col]

    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_=update_set,
    )
    session.execute(stmt)
    return True


# ---------------------------------------------------------------------------
# scrape_runs audit row — every topic logs one per (stock, run).
# ---------------------------------------------------------------------------
def record_run(session: Session, stock_id: Optional[int], source: str,
               status: str, http_status: Optional[int] = None,
               err: Optional[str] = None):
    """Append an audit row to scrape_runs. Never UPSERTs — runs are events."""
    session.add(ScrapeRun(
        stock_id=stock_id, source=source, status=status,
        http_status=http_status, error_message=err,
    ))


# ---------------------------------------------------------------------------
# Topic writers
# ---------------------------------------------------------------------------
def write_news(session: Session, stock_id: int, items: list[dict]) -> int:
    """Headlines into stock_news. UNIQUE(stock_id, headline) ensures the
    same headline UPSERTs in place. Returns number of items written.
    """
    today = date.today()
    count = 0
    for item in items or []:
        payload = {
            "stock_id":    stock_id,
            "headline":    item["headline"],
            "url":         item.get("url"),
            "source_code": item.get("source_code"),
            "news_date":   today,
            "scraped_at":  datetime.utcnow(),
        }
        if _safe_upsert(session, StockNews, payload,
                        conflict_cols=["stock_id", "headline"]):
            count += 1
    return count


def write_current_quote(session: Session, stock_id: int, quote: dict) -> bool:
    """Refresh the one-row-per-stock stock_quotes cache AND today's
    stock_history_quote row.

    The current_quote topic is the ONLY way news/financial scrapers refresh
    stock_history_quote — other topics don't touch it.

    composite_score / verdict / pe_ratio / dividend_yield_pct are NEVER
    overwritten here — those come from the recommender, bulk import, or
    other writers.
    """
    if not quote:
        return False

    trading_date = quote.get("trading_date") or date.today()

    # 1) stock_quotes — refresh price + change + currency + price_source.
    quote_payload = {
        "stock_id":         stock_id,
        "current_price":    quote.get("current_price"),
        "change_abs":       quote.get("change_abs"),
        "change_pct":       quote.get("change_pct"),
        "currency":         quote.get("currency"),
        "price_source":     "scrape",
        "price_fetched_at": datetime.utcnow(),
        "last_updated":     datetime.utcnow(),
    }
    _safe_upsert(session, StockQuote, quote_payload, conflict_cols=["stock_id"])

    # 2) stock_history_quote — today's row (or whatever trading_date the
    # page reported). UPSERTs on (stock_id, trading_date) so re-running
    # the same day updates in place.
    hist_payload = {
        "stock_id":     stock_id,
        "trading_date": trading_date,
        "close_price":  quote.get("current_price"),
        "change_pct":   quote.get("change_pct"),
        "source":       "scrape",
        "scraped_at":   datetime.utcnow(),
    }
    _safe_upsert(session, StockHistoryQuote, hist_payload,
                 conflict_cols=["stock_id", "trading_date"])
    return True


def write_financials(session: Session, stock_id: int, data: dict) -> bool:
    """Write parsed financials → stock_fin_statement + stock_fin_cashflow."""
    if not data:
        return False
    wrote = False

    fs = data.get("fin_statement") or {}
    if fs:
        period_end = fs.pop("period_end", None) or date.today()
        payload = {
            "stock_id":    stock_id,
            "period_end":  period_end,
            "period_type": "TTM",
            "is_estimate": False,
            "scraped_at":  datetime.utcnow(),
            **fs,
        }
        wrote |= _safe_upsert(
            session, StockFinStatement, payload,
            conflict_cols=["stock_id", "period_end", "period_type", "is_estimate"],
        )

    fc = data.get("fin_cashflow") or {}
    if fc:
        period_end = fc.pop("period_end", None) or date.today()
        payload = {
            "stock_id":    stock_id,
            "period_end":  period_end,
            "period_type": "TTM",
            "is_estimate": False,
            "scraped_at":  datetime.utcnow(),
            **fc,
        }
        wrote |= _safe_upsert(
            session, StockFinCashflow, payload,
            conflict_cols=["stock_id", "period_end", "period_type", "is_estimate"],
        )

    return wrote


def write_technicals(session: Session, stock_id: int, data: dict) -> bool:
    """Write technicals → stock_mkt_technicals + stock_mkt_dividends.

    Technicals use (stock_id, trading_date=today) so today's row UPSERTs
    in place — a daily indicator snapshot, NOT a per-period one.
    """
    if not data:
        return False
    wrote = False
    today = date.today()

    tech = data.get("technicals") or {}
    if tech:
        payload = {
            "stock_id":     stock_id,
            "trading_date": today,
            "scraped_at":   datetime.utcnow(),
            **tech,
        }
        wrote |= _safe_upsert(
            session, StockMktTechnicals, payload,
            conflict_cols=["stock_id", "trading_date"],
        )

    div = data.get("dividends") or {}
    if div:
        payload = {
            "stock_id":   stock_id,
            "scraped_at": datetime.utcnow(),
            **div,
        }
        wrote |= _safe_upsert(
            session, StockMktDividends, payload,
            conflict_cols=["stock_id"],
        )

    return wrote


def write_ratios(session: Session, stock_id: int, data: dict) -> bool:
    """Write ratios → stock_fin_ratios."""
    if not data:
        return False
    period_end = data.pop("period_end", None) or date.today()
    payload = {
        "stock_id":    stock_id,
        "period_end":  period_end,
        "period_type": "TTM",
        "scraped_at":  datetime.utcnow(),
        **data,
    }
    return _safe_upsert(
        session, StockFinRatios, payload,
        conflict_cols=["stock_id", "period_end", "period_type"],
    )


def write_forecast(session: Session, stock_id: int, data: dict) -> bool:
    """Write {analyst_consensus, earnings_estimates}.

    analyst_consensus → stock_analyst_consensus, keyed on today's date.
    earnings_estimates → stock_earnings_calendar (one row per stock).
    """
    if not data:
        return False
    wrote = False
    today = date.today()

    ac = data.get("analyst_consensus") or {}
    if ac:
        payload = {
            "stock_id":       stock_id,
            "consensus_date": today,
            "scraped_at":     datetime.utcnow(),
            **ac,
        }
        wrote |= _safe_upsert(
            session, StockAnalystConsensus, payload,
            conflict_cols=["stock_id", "consensus_date"],
        )

    ee = data.get("earnings_estimates") or {}
    if ee:
        payload = {
            "stock_id":   stock_id,
            "source":     "scrape",
            "updated_at": datetime.utcnow(),
            **ee,
        }
        wrote |= _safe_upsert(
            session, StockEarningsCalendar, payload,
            conflict_cols=["stock_id"],
        )

    return wrote
