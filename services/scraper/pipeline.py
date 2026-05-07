"""Per-stock scraping pipeline.

For each active stock we fetch:
    - /quote/{exchange}/{ticker}/             (overview)
    - /quote/{exchange}/{ticker}/statistics/  (statistics)

We then UPSERT into:
    stocks (company metadata),
    stock_market_daily (price + valuations of the day),
    stock_valuation (TTM ratios),
    stock_financials (TTM snapshot, period_type='TTM'),
    stock_technicals (RSI / SMAs),
    stock_news (headlines),
    stock_latest_snapshot (denormalised cache for fast UI),
    scrape_runs (audit trail, per source).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    SessionLocal, Stock, Exchange, ScrapeRun, StockMarketDaily, StockValuation,
    StockFinancials, StockTechnicals, StockNews, StockLatestSnapshot,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .fetcher import HttpFetcher
from .parsers import (
    extract_label_value_pairs, extract_company_blurb, extract_news,
    build_market_daily, build_valuation, build_financials_ttm,
    build_technicals, extract_close_price,
)

log = configure_logging("scraper")
settings = get_settings()


def _quote_url(exchange_code: str, ticker: str, sub: str = "") -> str:
    base = f"{settings.scraper_base_url}/quote/{exchange_code.lower()}/{ticker}/"
    return base + (sub.rstrip("/") + "/" if sub else "")


# ----- DB write helpers (UPSERT semantics) -----

def _upsert_market_daily(session: Session, stock_id: int, today: date, payload: dict):
    stmt = pg_insert(StockMarketDaily).values(
        stock_id=stock_id, trading_date=today, **payload
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: stmt.excluded[k] for k in payload.keys()},
    )
    session.execute(stmt)


def _upsert_valuation(session: Session, stock_id: int, fiscal_year: int, payload: dict):
    payload = {**payload, "source_date": date.today()}
    stmt = pg_insert(StockValuation).values(
        stock_id=stock_id, fiscal_year=fiscal_year, **payload
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "fiscal_year"],
        set_={k: stmt.excluded[k] for k in payload.keys()},
    )
    session.execute(stmt)


def _upsert_financials_ttm(session: Session, stock_id: int, fiscal_year: int, payload: dict):
    """TTM snapshot lives at (stock_id, fiscal_year, 'TTM', 'INCOME', is_estimate=False)."""
    record = {
        "stock_id": stock_id,
        "fiscal_year": fiscal_year,
        "period_type": "TTM",
        "statement_type": "MIXED",
        "is_estimate": False,
        "source_date": date.today(),
        **payload,
    }
    stmt = pg_insert(StockFinancials).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "fiscal_year", "period_type", "statement_type", "is_estimate"],
        set_={k: stmt.excluded[k] for k in payload.keys()},
    )
    session.execute(stmt)


def _upsert_technicals(session: Session, stock_id: int, today: date, payload: dict):
    stmt = pg_insert(StockTechnicals).values(
        stock_id=stock_id, trading_date=today, **payload,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: stmt.excluded[k] for k in payload.keys()},
    )
    session.execute(stmt)


def _upsert_news(session: Session, stock_id: int, items: list[dict]):
    for item in items:
        stmt = pg_insert(StockNews).values(
            stock_id=stock_id,
            headline=item["headline"],
            url=item.get("url"),
            source_code=item.get("source_code"),
            news_date=item.get("news_date"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "headline"],
            set_={"url": stmt.excluded.url, "source_code": stmt.excluded.source_code},
        )
        session.execute(stmt)


def _upsert_snapshot(session: Session, stock_id: int, payload: dict):
    record = {"stock_id": stock_id, "last_updated": datetime.utcnow(), **payload}
    stmt = pg_insert(StockLatestSnapshot).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={k: stmt.excluded[k] for k in record if k != "stock_id"},
    )
    session.execute(stmt)


def _record_run(session: Session, stock_id: Optional[int], source: str,
                status: str, http_status: Optional[int], err: Optional[str]):
    session.add(ScrapeRun(
        stock_id=stock_id, source=source, status=status,
        http_status=http_status, error_message=err,
    ))


def _update_stock_metadata(session: Session, stock: Stock, blurb: dict):
    changed = False
    if blurb.get("company_name") and not stock.company_name:
        stock.company_name = blurb["company_name"]; changed = True
    if blurb.get("industry") and stock.industry != blurb["industry"]:
        stock.industry = blurb["industry"]; changed = True
    if blurb.get("country") and stock.country != blurb["country"]:
        stock.country = blurb["country"]; changed = True
    if blurb.get("founded_year") and not stock.founded_year:
        stock.founded_year = blurb["founded_year"]; changed = True
    if changed:
        stock.updated_at = datetime.utcnow()


# ----- main per-stock job -----

async def scrape_one(fetcher: HttpFetcher, stock_id: int, exchange_code: str, ticker: str):
    """One stock = up to two HTTP calls + one DB transaction."""
    today = date.today()
    overview_html: str | None = None
    statistics_html: str | None = None
    overview_status = stats_status = None
    err: str | None = None

    try:
        overview_status, overview_html = await fetcher.get(_quote_url(exchange_code, ticker))
    except Exception as exc:
        err = f"overview: {exc}"
        log.warning("overview_fetch_failed", ticker=ticker, error=str(exc))

    try:
        stats_status, statistics_html = await fetcher.get(_quote_url(exchange_code, ticker, "statistics"))
    except Exception as exc:
        log.warning("stats_fetch_failed", ticker=ticker, error=str(exc))
        if not err:
            err = f"statistics: {exc}"

    if not overview_html and not statistics_html:
        with SessionLocal() as session:
            _record_run(session, stock_id, "stockanalysis.com", "FAILED", None, err)
            session.commit()
        return

    pairs: dict[str, str] = {}
    if overview_html:
        pairs.update(extract_label_value_pairs(overview_html))
    if statistics_html:
        pairs.update(extract_label_value_pairs(statistics_html))

    blurb = extract_company_blurb(overview_html or statistics_html or "")
    news = extract_news(overview_html or "")

    market = build_market_daily(pairs)
    valuation = build_valuation(pairs)
    financials = build_financials_ttm(pairs)
    technicals = build_technicals(pairs)
    close_price = extract_close_price(pairs, overview_html or "")
    if close_price is not None:
        market["close_price"] = close_price

    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                log.error("stock_missing", stock_id=stock_id)
                return

            _update_stock_metadata(session, stock, blurb)

            if any(v is not None for v in market.values()):
                _upsert_market_daily(session, stock_id, today, market)

            fiscal_year = today.year
            if any(v is not None for v in valuation.values()):
                _upsert_valuation(session, stock_id, fiscal_year, valuation)
            if any(v is not None for v in financials.values()):
                _upsert_financials_ttm(session, stock_id, fiscal_year, financials)
            if any(v is not None for v in technicals.values()):
                _upsert_technicals(session, stock_id, today, technicals)

            if news:
                _upsert_news(session, stock_id, news)

            _upsert_snapshot(session, stock_id, {
                "last_close": market.get("close_price"),
                "market_cap": market.get("market_cap"),
                "pe_ratio": market.get("pe_ratio"),
                "dividend_yield_pct": market.get("dividend_yield_pct"),
                "week_52_high": market.get("week_52_high"),
                "week_52_low": market.get("week_52_low"),
                "rsi_14": technicals.get("rsi_14"),
            })

            _record_run(session, stock_id, "stockanalysis.com", "OK",
                        overview_status or stats_status, None)
            session.commit()
            log.info("scrape_ok", ticker=ticker, fields=len(pairs))
        except Exception as exc:
            session.rollback()
            log.exception("scrape_db_error", ticker=ticker, error=str(exc))
            with SessionLocal() as s2:
                _record_run(s2, stock_id, "stockanalysis.com", "FAILED",
                            overview_status or stats_status, str(exc))
                s2.commit()


# ----- batch entrypoint -----

async def scrape_all_active() -> dict:
    """Iterate every active stock and scrape it. Returns summary."""
    with SessionLocal() as session:
        rows = session.execute(
            select(Stock.id, Exchange.code, Stock.ticker)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Stock.active.is_(True))
        ).all()

    log.info("scrape_batch_start", total=len(rows))
    successes = failures = 0

    async with HttpFetcher() as fetcher:
        async def _wrapped(row):
            nonlocal successes, failures
            try:
                await scrape_one(fetcher, row.id, row.code, row.ticker)
                successes += 1
            except Exception as exc:
                failures += 1
                log.exception("scrape_one_unhandled", ticker=row.ticker, error=str(exc))

        await asyncio.gather(*(_wrapped(row) for row in rows))

    summary = {"total": len(rows), "ok": successes, "failed": failures, "ts": datetime.utcnow().isoformat()}
    log.info("scrape_batch_done", **summary)
    return summary


async def scrape_by_ticker(exchange_code: str, ticker: str) -> dict:
    """On-demand scrape for a single ticker (used by API)."""
    with SessionLocal() as session:
        row = session.execute(
            select(Stock.id, Exchange.code, Stock.ticker)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Exchange.code == exchange_code.lower(), Stock.ticker == ticker.upper())
        ).first()
    if not row:
        return {"ok": False, "error": "stock_not_found"}

    async with HttpFetcher() as fetcher:
        await scrape_one(fetcher, row.id, row.code, row.ticker)
    return {"ok": True, "exchange": exchange_code, "ticker": ticker}
