"""Scraping pipeline — orchestration.

# Design

For each stock we scrape stockanalysis.com pages, parse them into dicts
(see parsers.py), and UPSERT into the right tables. Two tiers:

  * `daily` (default schedule, every day, throttled): overview page only.
    Updates today's row in stock_history_quote (UPSERT on (stock_id,
    trading_date)) and the per-stock stock_quotes "now" cache. News
    headlines also come from this page.

  * `weekly` (schedule once a week): all the slow-moving pages:
    /financials/, /financials/balance-sheet/, /financials/cash-flow-statement/,
    /financials/ratios/, /forecast/, /ratings/, /statistics/. These write
    fundamentals + analyst estimates + technicals + dividends. /history/
    is also fetched but only on FIRST encounter (no historical row yet)
    so we backfill OHLC for the chart.

# Safety

Every DB write goes through `_safe_upsert()`, which knows each table's
unique key and uses PostgreSQL `ON CONFLICT DO UPDATE` against it. Same
stock + same (period_end / trading_date) → row updated in place. Different
date → new row, but only on time-series tables that allow it.

We NEVER do raw INSERTs. The tables `stock_quotes`, `stock_mkt_dividends`,
and `stock_earnings_calendar` are one-row-per-stock (PK = stock_id), so
their UPSERT target is just `stock_id`. The financial / technicals / history
tables have composite UNIQUE constraints — we use them as the target.

If a parsed dict has all-None values, we skip the write entirely so we
don't blow away a previously-good row with NULLs.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    SessionLocal, Stock, Exchange, ScrapeRun,
    StockNews, StockQuote, StockHistoryQuote,
    StockFinRatios, StockFinStatement, StockFinCashflow,
    StockEarningsCalendar, StockMktDividends, StockMktTechnicals,
    StockAnalystConsensus,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .fetcher import HttpFetcher
from . import parsers

log = configure_logging("scraper")
_settings = get_settings()


# =============================================================================
# URL builders
# =============================================================================
# stockanalysis.com sub-pages we care about. Each value is the suffix appended
# to the per-exchange base URL.
PAGE_SUFFIXES = {
    "overview":      "",
    "statistics":    "statistics",
    "financials":    "financials",
    "balance_sheet": "financials/balance-sheet",
    "cashflow":      "financials/cash-flow-statement",
    "ratios":        "financials/ratios",
    "forecast":      "forecast",
    "ratings":       "ratings",
    "history":       "history",
}


def _build_url(url_template: str, ticker: str, sub: str = "") -> str:
    """Build a stockanalysis.com URL for this stock.

    `url_template` is Exchange.stockanalysis_url_template, e.g.
    '/stocks/{ticker}/' (US) or '/quote/dfm/{ticker}/' (DFM).
    """
    base = _settings.scraper_base_url + url_template.format(ticker=ticker.lower())
    if not base.endswith("/"):
        base += "/"
    return base + (sub.rstrip("/") + "/" if sub else "")


# =============================================================================
# Safe UPSERT helper
# =============================================================================
def _safe_upsert(session: Session, model, payload: dict, conflict_cols: list[str]):
    """UPSERT one row, keeping previously-set values when payload has None.

    Logic:
        1. If every payload value (excluding key columns) is None, skip —
           we don't want to overwrite a previously-good row with all NULLs.
        2. Use PG ON CONFLICT DO UPDATE against the supplied conflict_cols.
           Only columns whose payload value is not None are updated; the rest
           are left as-is on the existing row.
    """
    if not payload:
        return False

    # Always-include columns are conflict_cols + scraped_at/updated_at if
    # present in payload. Anything else gets filtered to "not None" so we
    # don't trample existing data.
    data_keys = [k for k in payload.keys()
                 if k not in conflict_cols
                 and k not in ("scraped_at", "updated_at")]
    if not any(payload.get(k) is not None for k in data_keys):
        return False  # everything we'd write is None — skip

    # Build the insert with all the columns (None will be inserted as NULL
    # for first-time rows, but on conflict we only update the non-None ones).
    stmt = pg_insert(model).values(**payload)
    update_set = {k: stmt.excluded[k]
                  for k in payload.keys()
                  if k not in conflict_cols and payload[k] is not None}
    # Always bump scraped_at/updated_at if present
    for ts_col in ("scraped_at", "updated_at"):
        if ts_col in payload:
            update_set[ts_col] = stmt.excluded[ts_col]
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_=update_set,
    )
    session.execute(stmt)
    return True


def _record_run(session: Session, stock_id: Optional[int], source: str,
                status: str, http_status: Optional[int], err: Optional[str]):
    session.add(ScrapeRun(
        stock_id=stock_id, source=source, status=status,
        http_status=http_status, error_message=err,
    ))


# =============================================================================
# Per-page write helpers — each takes a parsed dict, performs the safe upsert.
# =============================================================================
def _write_company_blurb(session: Session, stock: Stock, company: dict):
    """Only fills nullable company fields if currently null — don't overwrite
    admin-curated values like industry/sector.
    """
    changed = False
    for k in ("industry", "country", "founded_year"):
        v = company.get(k)
        if v and getattr(stock, k, None) in (None, ""):
            setattr(stock, k, v)
            changed = True
    if company.get("company_name") and not stock.company_name:
        stock.company_name = company["company_name"]
        changed = True
    if changed:
        stock.updated_at = datetime.utcnow()


def _write_news(session: Session, stock_id: int, news: list[dict], today: date):
    """News has a UNIQUE(stock_id, headline) — same headline updates in place."""
    for item in news:
        payload = {
            "stock_id": stock_id,
            "headline": item["headline"],
            "url": item.get("url"),
            "source_code": item.get("source_code"),
            "news_date": today,
            "scraped_at": datetime.utcnow(),
        }
        _safe_upsert(session, StockNews, payload,
                     conflict_cols=["stock_id", "headline"])


def _write_history_row(session: Session, stock_id: int, today: date, row: dict):
    """One row per (stock, trading_date). Today's row UPSERTs in place."""
    payload = {
        "stock_id": stock_id,
        "trading_date": today,
        "source": "scrape",
        "scraped_at": datetime.utcnow(),
        **{k: row.get(k) for k in (
            "open_price", "high_price", "low_price", "close_price",
            "volume", "market_cap", "change_pct",
        )},
    }
    _safe_upsert(session, StockHistoryQuote, payload,
                 conflict_cols=["stock_id", "trading_date"])


def _write_quote_cache(session: Session, stock_id: int, quote: dict):
    """Canonical stock_quotes 'now' row (PK = stock_id).

    composite_score / verdict are NEVER written here — they belong to the
    recommender. We just refresh the price / valuation / yield columns.
    """
    payload = {
        "stock_id": stock_id,
        "price_source": "scrape",
        "price_fetched_at": datetime.utcnow(),
        "last_updated": datetime.utcnow(),
        **{k: quote.get(k) for k in (
            "current_price", "change_pct", "currency", "market_cap",
            "pe_ratio", "pe_forward", "dividend_yield_pct",
            "rsi_14", "week_52_high", "week_52_low",
        )},
    }
    _safe_upsert(session, StockQuote, payload, conflict_cols=["stock_id"])


def _write_fin_ratios(session: Session, stock_id: int, ratios: dict):
    """UNIQUE(stock_id, period_end, period_type)."""
    period_end = ratios.pop("period_end", None) or date.today()
    payload = {
        "stock_id": stock_id,
        "period_end": period_end,
        "period_type": "TTM",
        "scraped_at": datetime.utcnow(),
        **ratios,
    }
    _safe_upsert(session, StockFinRatios, payload,
                 conflict_cols=["stock_id", "period_end", "period_type"])


def _write_fin_statement(session: Session, stock_id: int, fin_stmt: dict,
                         balance: Optional[dict] = None):
    """UNIQUE(stock_id, period_end, period_type, is_estimate)."""
    period_end = fin_stmt.pop("period_end", None) or date.today()
    payload = {
        "stock_id": stock_id,
        "period_end": period_end,
        "period_type": "TTM",
        "is_estimate": False,
        "scraped_at": datetime.utcnow(),
        **fin_stmt,
    }
    if balance:
        # Balance sheet contributes shares_outstanding + net_cash + total_debt
        for k in ("shares_outstanding", "net_cash", "total_debt"):
            if balance.get(k) is not None:
                payload[k] = balance[k]
    _safe_upsert(session, StockFinStatement, payload,
                 conflict_cols=["stock_id", "period_end", "period_type",
                                "is_estimate"])


def _write_fin_cashflow(session: Session, stock_id: int, cashflow: dict):
    """UNIQUE(stock_id, period_end, period_type, is_estimate)."""
    period_end = cashflow.pop("period_end", None) or date.today()
    payload = {
        "stock_id": stock_id,
        "period_end": period_end,
        "period_type": "TTM",
        "is_estimate": False,
        "scraped_at": datetime.utcnow(),
        **cashflow,
    }
    _safe_upsert(session, StockFinCashflow, payload,
                 conflict_cols=["stock_id", "period_end", "period_type",
                                "is_estimate"])


def _write_dividends(session: Session, stock_id: int, dividends: dict):
    """One row per stock (PK = stock_id)."""
    payload = {
        "stock_id": stock_id,
        "scraped_at": datetime.utcnow(),
        **dividends,
    }
    _safe_upsert(session, StockMktDividends, payload, conflict_cols=["stock_id"])


def _write_technicals(session: Session, stock_id: int, today: date, technicals: dict):
    """UNIQUE(stock_id, trading_date)."""
    payload = {
        "stock_id": stock_id,
        "trading_date": today,
        "scraped_at": datetime.utcnow(),
        **technicals,
    }
    _safe_upsert(session, StockMktTechnicals, payload,
                 conflict_cols=["stock_id", "trading_date"])


def _write_analyst_consensus(session: Session, stock_id: int, today: date, rating: dict):
    """One row per (stock, consensus_date) — most-recent value wins by date."""
    if not any(v is not None for v in rating.values()):
        return
    # Look for today's row first; if present we update in place, else insert.
    existing = session.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == stock_id,
               StockAnalystConsensus.consensus_date == today)
    ).scalar_one_or_none()
    if existing:
        for k, v in rating.items():
            if v is not None:
                setattr(existing, k, v)
        existing.scraped_at = datetime.utcnow()
    else:
        session.add(StockAnalystConsensus(
            stock_id=stock_id,
            consensus_date=today,
            scraped_at=datetime.utcnow(),
            **rating,
        ))


def _write_earnings(session: Session, stock_id: int, forecast: dict):
    """One row per stock (PK = stock_id)."""
    if not any(v is not None for v in forecast.values()):
        return
    payload = {
        "stock_id": stock_id,
        "source": "scrape",
        "updated_at": datetime.utcnow(),
        **forecast,
    }
    _safe_upsert(session, StockEarningsCalendar, payload, conflict_cols=["stock_id"])


# =============================================================================
# Per-stock orchestrators
# =============================================================================
async def _scrape_overview(fetcher: HttpFetcher, stock_id: int, ticker: str,
                           url_template: str) -> tuple[Optional[int], Optional[str]]:
    """Daily-tier scrape: just the overview page."""
    url = _build_url(url_template, ticker, PAGE_SUFFIXES["overview"])
    today = date.today()
    try:
        status, html = await fetcher.get(url)
    except Exception as exc:
        log.warning("overview_fetch_failed", ticker=ticker, error=str(exc))
        return None, f"overview: {exc}"

    parsed = parsers.parse_overview_page(html)
    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                return status, "stock_missing"
            _write_company_blurb(session, stock, parsed["company"])
            _write_history_row(session, stock_id, today, parsed["history_row"])
            _write_quote_cache(session, stock_id, parsed["quote"])
            _write_news(session, stock_id, parsed["news"], today)
            stock.updated_at = datetime.utcnow()
            _record_run(session, stock_id, "stockanalysis.com:overview",
                        "OK", status, None)
            session.commit()
            log.info("scrape_overview_ok", ticker=ticker,
                     news=len(parsed["news"]),
                     price=str(parsed["quote"].get("current_price") or "n/a"))
            return status, None
        except Exception as exc:
            session.rollback()
            log.exception("scrape_overview_db_error", ticker=ticker, error=str(exc))
            with SessionLocal() as s2:
                _record_run(s2, stock_id, "stockanalysis.com:overview",
                            "FAILED", status, str(exc))
                s2.commit()
            return status, str(exc)


async def _scrape_weekly_pages(fetcher: HttpFetcher, stock_id: int, ticker: str,
                               url_template: str,
                               include_history: bool) -> dict[str, Any]:
    """Weekly-tier scrape: financials, ratios, forecast, ratings, statistics.

    History is fetched only if `include_history=True` (typically when there's
    no row yet in stock_history_quote for this stock).
    """
    pages: dict[str, str] = {}
    errors: list[str] = []
    last_status: Optional[int] = None

    needed = ["statistics", "ratios", "financials",
              "balance_sheet", "cashflow", "forecast", "ratings"]
    if include_history:
        needed.append("history")

    for key in needed:
        url = _build_url(url_template, ticker, PAGE_SUFFIXES[key])
        try:
            status, html = await fetcher.get(url)
            pages[key] = html
            last_status = status
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            log.warning("weekly_page_fetch_failed", ticker=ticker,
                        page=key, error=str(exc))

    today = date.today()
    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                return {"ok": False, "error": "stock_missing"}

            if "statistics" in pages:
                stats = parsers.parse_statistics_page(pages["statistics"])
                _write_fin_ratios(session, stock_id, stats["ratios"])
                _write_fin_statement(session, stock_id, stats["fin_stmt"])
                _write_dividends(session, stock_id, stats["dividends"])
                _write_technicals(session, stock_id, today, stats["technicals"])

            if "ratios" in pages:
                # /ratios/ overrides statistics where both have a value
                _write_fin_ratios(session, stock_id,
                                  parsers.parse_ratios_page(pages["ratios"]))

            if "financials" in pages:
                fin = parsers.parse_financials_page(pages["financials"])
                balance = (parsers.parse_balance_sheet_page(pages["balance_sheet"])
                           if "balance_sheet" in pages else None)
                _write_fin_statement(session, stock_id, fin, balance)

            if "cashflow" in pages:
                _write_fin_cashflow(session, stock_id,
                                    parsers.parse_cashflow_page(pages["cashflow"]))

            if "forecast" in pages:
                _write_earnings(session, stock_id,
                                parsers.parse_forecast_page(pages["forecast"]))

            if "ratings" in pages:
                _write_analyst_consensus(session, stock_id, today,
                                         parsers.parse_ratings_page(pages["ratings"]))

            if "history" in pages:
                # Bulk-load historical OHLC. Each row UPSERTs on
                # (stock_id, trading_date) so re-runs are idempotent.
                for row in parsers.parse_history_page(pages["history"]):
                    payload = {
                        "stock_id": stock_id,
                        "source": "scrape:history",
                        "scraped_at": datetime.utcnow(),
                        **row,
                    }
                    _safe_upsert(session, StockHistoryQuote, payload,
                                 conflict_cols=["stock_id", "trading_date"])

            stock.updated_at = datetime.utcnow()
            status_str = "OK" if not errors else "PARTIAL"
            err_str = "; ".join(errors) if errors else None
            _record_run(session, stock_id, "stockanalysis.com:weekly",
                        status_str, last_status, err_str)
            session.commit()
            log.info("scrape_weekly_ok", ticker=ticker,
                     pages=len(pages), errors=len(errors))
            return {"ok": True, "pages": list(pages.keys()), "errors": errors}
        except Exception as exc:
            session.rollback()
            log.exception("scrape_weekly_db_error", ticker=ticker, error=str(exc))
            with SessionLocal() as s2:
                _record_run(s2, stock_id, "stockanalysis.com:weekly",
                            "FAILED", last_status, str(exc))
                s2.commit()
            return {"ok": False, "error": str(exc)}


# =============================================================================
# Public entry points (called by FastAPI + scheduler)
# =============================================================================
async def scrape_one(fetcher: HttpFetcher, stock_id: int, ticker: str,
                     url_template: str, mode: str = "daily"):
    """One stock. mode='daily' (overview only) or 'weekly' (everything else).

    The legacy `mode='full'` is treated as 'weekly' for backward-compat with
    older callers in the scheduler.
    """
    if mode in ("daily",):
        await _scrape_overview(fetcher, stock_id, ticker, url_template)
        return
    if mode in ("weekly", "full"):
        # Check if we have any historical rows yet — if not, backfill via /history/
        with SessionLocal() as session:
            has_history = session.execute(
                select(func.count(StockHistoryQuote.id))
                .where(StockHistoryQuote.stock_id == stock_id)
            ).scalar() or 0
        await _scrape_weekly_pages(fetcher, stock_id, ticker, url_template,
                                   include_history=(has_history == 0))
        return
    raise ValueError(f"unknown scrape mode: {mode!r}")


# =============================================================================
# Batch runner
# =============================================================================
async def scrape_all_active(mode: str = "daily",
                            exchanges: Optional[list[str]] = None) -> dict:
    """Iterate scraping-enabled stocks and scrape them in throttled batches.

    The fetcher's per-request delay + concurrency cap already protects us
    against hammering. We use asyncio.gather across all stocks; the
    semaphore inside the fetcher serialises actual HTTP calls.
    """
    with SessionLocal() as session:
        stmt = (
            select(Stock.id, Stock.ticker, Exchange.stockanalysis_url_template)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Stock.active.is_(True), Stock.is_scraping_enabled.is_(True))
        )
        if exchanges:
            codes = [c.lower() for c in exchanges]
            stmt = stmt.where(func.lower(Exchange.code).in_(codes))
        rows = session.execute(stmt).all()

    log.info("scrape_batch_start", total=len(rows), mode=mode,
             exchanges=exchanges or "all")
    ok = fail = 0

    async with HttpFetcher() as fetcher:
        async def _wrap(row):
            nonlocal ok, fail
            try:
                await scrape_one(fetcher, row.id, row.ticker,
                                 row.stockanalysis_url_template, mode=mode)
                ok += 1
            except Exception as exc:
                fail += 1
                log.exception("scrape_one_unhandled",
                              ticker=row.ticker, error=str(exc))

        await asyncio.gather(*(_wrap(row) for row in rows))

    summary = {
        "total": len(rows), "ok": ok, "failed": fail,
        "mode": mode, "exchanges": exchanges or "all",
        "ts": datetime.utcnow().isoformat(),
    }
    log.info("scrape_batch_done", **summary)
    return summary


async def scrape_by_ticker(exchange_code: str, ticker: str,
                           mode: str = "daily") -> dict:
    """On-demand scrape for one ticker (used by the API)."""
    with SessionLocal() as session:
        row = session.execute(
            select(Stock.id, Stock.ticker,
                   Exchange.stockanalysis_url_template)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(func.lower(Exchange.code) == exchange_code.lower(),
                   func.upper(Stock.ticker) == ticker.upper())
        ).first()
    if not row:
        return {"ok": False, "error": "stock_not_found"}
    async with HttpFetcher() as fetcher:
        await scrape_one(fetcher, row.id, row.ticker,
                         row.stockanalysis_url_template, mode=mode)
    return {"ok": True, "exchange": exchange_code,
            "ticker": ticker, "mode": mode}
