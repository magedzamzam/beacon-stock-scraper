"""Topic pipelines — one entry point per scraper topic.

Each pipeline:
  1. Selects active stocks (optionally only those WITHOUT a broker mapping
     for the current_quote topic).
  2. Iterates them, calls the configured provider, hands the result to
     the matching writer.
  3. Records an audit row per stock in scrape_runs.

The fetcher's semaphore + per-request delay throttle concurrency, so
asyncio.gather is safe across all enabled stocks.

Public callables are the only surface exposed to FastAPI + scheduler:
    run_news(...)
    run_current_quote(...)
    run_financials(...)
    run_technicals(...)
    run_ratios(...)
    run_forecast(...)
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db import (
    BrokerInstrument, Exchange, SessionLocal, Stock,
)
from shared.logging_setup import configure_logging

from .fetcher import HttpFetcher
from .providers import StockContext, get_provider
from . import writers

log = configure_logging("scraper")


# ---------------------------------------------------------------------------
# Stock selection — shared across topics
# ---------------------------------------------------------------------------
def _select_stocks(exchanges: Optional[list[str]] = None,
                   *, only_unmapped: bool = False) -> list[StockContext]:
    """Return the StockContext list for an enabled scrape run.

    only_unmapped=True excludes any stock that has a tradeable broker
    instrument — used for the current_quote topic so we don't waste a
    page fetch on stocks whose price comes from the broker API.
    """
    with SessionLocal() as session:
        stmt = (
            select(Stock.id, Stock.ticker, Exchange.code,
                   Exchange.stockanalysis_url_template)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Stock.active.is_(True), Stock.is_scraping_enabled.is_(True))
        )
        if exchanges:
            codes = [c.lower() for c in exchanges]
            stmt = stmt.where(func.lower(Exchange.code).in_(codes))
        if only_unmapped:
            # Anti-join via NOT EXISTS — clearer in SQL than .outerjoin().is_()
            mapped = (
                select(BrokerInstrument.stock_id)
                .where(BrokerInstrument.stock_id == Stock.id,
                       BrokerInstrument.is_tradeable.is_(True))
            )
            stmt = stmt.where(~mapped.exists())
        rows = session.execute(stmt).all()
    return [
        StockContext(stock_id=r.id, ticker=r.ticker,
                     exchange_code=r.code, url_template=r.stockanalysis_url_template)
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Generic per-topic batch runner.
# ---------------------------------------------------------------------------
async def _run_topic(
    topic: str,
    stocks: list[StockContext],
    fetch_method_name: str,
    write_func: Callable[[Session, int, object], object],
    *,
    audit_source: str,
) -> dict:
    """Loop over stocks, call provider.<fetch_method>, then write.

    Errors are caught per-stock so one bad page doesn't kill the batch.
    Each stock gets one scrape_runs row regardless of outcome.
    """
    provider = get_provider(topic)
    fetch = getattr(provider, fetch_method_name)
    ok = failed = skipped = 0

    async with HttpFetcher() as fetcher:
        async def _do(s: StockContext):
            nonlocal ok, failed, skipped
            try:
                data = await fetch(fetcher, s)
            except Exception as exc:
                failed += 1
                with SessionLocal() as session:
                    writers.record_run(session, s.stock_id, audit_source,
                                       "FAILED", err=str(exc))
                    session.commit()
                log.warning("fetch_failed", topic=topic, ticker=s.ticker,
                            error=str(exc))
                return
            if data is None:
                # Provider couldn't fetch the page at all
                failed += 1
                with SessionLocal() as session:
                    writers.record_run(session, s.stock_id, audit_source,
                                       "FAILED", err="provider_returned_none")
                    session.commit()
                return
            try:
                with SessionLocal() as session:
                    wrote = write_func(session, s.stock_id, data)
                    writers.record_run(session, s.stock_id, audit_source,
                                       "OK" if wrote else "EMPTY")
                    session.commit()
                if wrote:
                    ok += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                with SessionLocal() as session:
                    writers.record_run(session, s.stock_id, audit_source,
                                       "FAILED", err=str(exc))
                    session.commit()
                log.exception("write_failed", topic=topic, ticker=s.ticker)

        await asyncio.gather(*(_do(s) for s in stocks))

    summary = {
        "topic": topic, "total": len(stocks),
        "ok": ok, "skipped": skipped, "failed": failed,
        "ts": datetime.utcnow().isoformat(),
    }
    log.info("topic_done", **summary)
    return summary


# ---------------------------------------------------------------------------
# Public per-topic entry points. The scheduler + FastAPI call these.
# ---------------------------------------------------------------------------
async def run_news(exchanges: Optional[list[str]] = None) -> dict:
    stocks = _select_stocks(exchanges)
    return await _run_topic(
        topic="news",
        stocks=stocks,
        fetch_method_name="fetch_news",
        write_func=lambda s, sid, items: writers.write_news(s, sid, items or []),
        audit_source="news",
    )


async def run_current_quote(exchanges: Optional[list[str]] = None) -> dict:
    """ONLY runs for stocks WITHOUT a tradeable broker mapping — mapped
    stocks get their price from the broker API via job.broker_quote_refresh.
    """
    stocks = _select_stocks(exchanges, only_unmapped=True)
    return await _run_topic(
        topic="current_quote",
        stocks=stocks,
        fetch_method_name="fetch_current_quote",
        write_func=writers.write_current_quote,
        audit_source="current_quote",
    )


async def run_financials(exchanges: Optional[list[str]] = None) -> dict:
    stocks = _select_stocks(exchanges)
    return await _run_topic(
        topic="financials",
        stocks=stocks,
        fetch_method_name="fetch_financials",
        write_func=writers.write_financials,
        audit_source="financials",
    )


async def run_technicals(exchanges: Optional[list[str]] = None) -> dict:
    stocks = _select_stocks(exchanges)
    return await _run_topic(
        topic="technicals",
        stocks=stocks,
        fetch_method_name="fetch_technicals",
        write_func=writers.write_technicals,
        audit_source="technicals",
    )


async def run_ratios(exchanges: Optional[list[str]] = None) -> dict:
    stocks = _select_stocks(exchanges)
    return await _run_topic(
        topic="ratios",
        stocks=stocks,
        fetch_method_name="fetch_ratios",
        write_func=writers.write_ratios,
        audit_source="ratios",
    )


async def run_forecast(exchanges: Optional[list[str]] = None) -> dict:
    stocks = _select_stocks(exchanges)
    return await _run_topic(
        topic="forecast",
        stocks=stocks,
        fetch_method_name="fetch_forecast",
        write_func=writers.write_forecast,
        audit_source="forecast",
    )


# ---------------------------------------------------------------------------
# Single-stock invocation (used by the FastAPI on-demand endpoint).
# ---------------------------------------------------------------------------
async def run_one_topic(topic: str, exchange_code: str, ticker: str) -> dict:
    """Run a single topic against a single ticker."""
    with SessionLocal() as session:
        row = session.execute(
            select(Stock.id, Stock.ticker, Exchange.code,
                   Exchange.stockanalysis_url_template)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(func.lower(Exchange.code) == exchange_code.lower(),
                   func.upper(Stock.ticker) == ticker.upper())
        ).first()
    if not row:
        return {"ok": False, "error": "stock_not_found"}

    stock = StockContext(stock_id=row.id, ticker=row.ticker,
                        exchange_code=row.code,
                        url_template=row.stockanalysis_url_template)

    topic_to_pipeline = {
        "news":          (run_news,          [stock]),
        "current_quote": (run_current_quote, [stock]),
        "financials":    (run_financials,    [stock]),
        "technicals":    (run_technicals,    [stock]),
        "ratios":        (run_ratios,        [stock]),
        "forecast":      (run_forecast,      [stock]),
    }
    if topic not in topic_to_pipeline:
        return {"ok": False,
                "error": f"unknown_topic: {topic}",
                "valid": list(topic_to_pipeline.keys())}

    # Run the topic but with a list scoped to this one stock — we override
    # _select_stocks via a direct call to _run_topic to avoid hitting the
    # generic selector that would include all stocks.
    method_map = {
        "news":          ("fetch_news",          lambda s, sid, items: writers.write_news(s, sid, items or [])),
        "current_quote": ("fetch_current_quote", writers.write_current_quote),
        "financials":    ("fetch_financials",    writers.write_financials),
        "technicals":    ("fetch_technicals",    writers.write_technicals),
        "ratios":        ("fetch_ratios",        writers.write_ratios),
        "forecast":      ("fetch_forecast",      writers.write_forecast),
    }
    method_name, write_func = method_map[topic]
    summary = await _run_topic(
        topic=topic, stocks=[stock],
        fetch_method_name=method_name, write_func=write_func,
        audit_source=topic,
    )
    return {"ok": True, "exchange": exchange_code, "ticker": ticker, **summary}
