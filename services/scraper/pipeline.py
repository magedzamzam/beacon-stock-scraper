"""Per-stock scraping pipeline — NEWS ONLY.

For each active stock we fetch the overview page and extract news headlines
into stock_news. Financials, fundamentals, technicals, dividends and history
are NOT scraped — that data comes from the bulk CSV import (more complete,
more reliable, and bulk-keyed correctly).

URL pattern depends on exchange — see Exchange.stockanalysis_url_template:
    * MENA / LSE: /quote/{exchange}/{ticker}/
    * US:         /stocks/{ticker}/

Tables touched:
    stocks       (just bumps updated_at)
    stock_news   (UPSERT headlines)
    scrape_runs  (audit trail)
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    SessionLocal, Stock, Exchange, ScrapeRun, StockNews,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .fetcher import HttpFetcher
from .parsers import extract_news

log = configure_logging("scraper")
settings = get_settings()


def _quote_url(url_template: str, ticker: str, sub: str = "") -> str:
    """Build a stockanalysis.com URL for this stock.

    url_template is the per-exchange pattern from Exchange.stockanalysis_url_template,
    e.g. '/quote/dfm/{ticker}/' or '/stocks/{ticker}/'. We substitute the ticker
    and optionally append a sub-page (e.g. 'statistics').
    """
    base = settings.scraper_base_url + url_template.format(ticker=ticker)
    # Ensure trailing slash on the base before any sub-page is appended.
    if not base.endswith("/"):
        base += "/"
    return base + (sub.rstrip("/") + "/" if sub else "")


# ----- DB write helpers (UPSERT semantics) -----

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



def _record_run(session: Session, stock_id: Optional[int], source: str,
                status: str, http_status: Optional[int], err: Optional[str]):
    session.add(ScrapeRun(
        stock_id=stock_id, source=source, status=status,
        http_status=http_status, error_message=err,
    ))




# ----- main per-stock job -----

async def scrape_one(fetcher: HttpFetcher, stock_id: int, ticker: str,
                     url_template: str, mode: str = "full"):
    """News-only scrape.

    Previous behavior wrote financials, fundamentals, technicals, dividends,
    history, and a recomputed stock_quotes row. All of that came from scraping
    the stockanalysis.com HTML, which was a poor source compared to the bulk
    CSV import (incomplete data, mismatched period_end values caused new rows
    instead of updates). The single use-case kept here is the news headlines:
    they only exist on the overview page and are otherwise hard to come by.

    `mode` and `url_template` are still accepted for caller compatibility but
    only the overview page is fetched regardless of mode.
    """
    today = date.today()
    overview_html: str | None = None
    overview_status = None
    err: str | None = None

    try:
        overview_status, overview_html = await fetcher.get(_quote_url(url_template, ticker))
    except Exception as exc:
        err = f"overview: {exc}"
        log.warning("overview_fetch_failed", ticker=ticker, error=str(exc))

    if not overview_html:
        with SessionLocal() as session:
            _record_run(session, stock_id, "stockanalysis.com", "FAILED",
                        overview_status, err)
            session.commit()
        return

    news = extract_news(overview_html)
    for item in news:
        item["news_date"] = today

    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                log.error("stock_missing", stock_id=stock_id)
                return

            if news:
                _upsert_news(session, stock_id, news)

            # Bump last_scraped_at so the UI can show data freshness even
            # though we didn't write fundamentals.
            stock.updated_at = datetime.utcnow()

            _record_run(session, stock_id, "stockanalysis.com", "OK",
                        overview_status, None)
            session.commit()
            log.info("scrape_news_ok", ticker=ticker, news_count=len(news))
        except Exception as exc:
            session.rollback()
            log.exception("scrape_db_error", ticker=ticker, error=str(exc))
            with SessionLocal() as s2:
                _record_run(s2, stock_id, "stockanalysis.com", "FAILED",
                            overview_status, str(exc))
                s2.commit()


# ----- batch entrypoint -----

async def scrape_all_active(mode: str = "full",
                            exchanges: Optional[list[str]] = None) -> dict:
    """Iterate scraping-enabled stocks and scrape them.

    mode      'daily' or 'full' — see scrape_one().
    exchanges list of exchange codes (case-insensitive) to include. None or
              empty list means all exchanges.
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
    successes = failures = 0

    async with HttpFetcher() as fetcher:
        async def _wrapped(row):
            nonlocal successes, failures
            try:
                await scrape_one(fetcher, row.id, row.ticker,
                                 row.stockanalysis_url_template, mode=mode)
                successes += 1
            except Exception as exc:
                failures += 1
                log.exception("scrape_one_unhandled", ticker=row.ticker, error=str(exc))

        await asyncio.gather(*(_wrapped(row) for row in rows))

    summary = {
        "total": len(rows), "ok": successes, "failed": failures,
        "mode": mode, "exchanges": exchanges or "all",
        "ts": datetime.utcnow().isoformat(),
    }
    log.info("scrape_batch_done", **summary)
    return summary


async def scrape_by_ticker(exchange_code: str, ticker: str) -> dict:
    """On-demand scrape for a single ticker (used by API)."""
    with SessionLocal() as session:
        row = session.execute(
            select(Stock.id, Stock.ticker, Exchange.stockanalysis_url_template)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Exchange.code == exchange_code.lower(), Stock.ticker == ticker.upper())
        ).first()
    if not row:
        return {"ok": False, "error": "stock_not_found"}

    async with HttpFetcher() as fetcher:
        await scrape_one(fetcher, row.id, row.ticker, row.stockanalysis_url_template)
    return {"ok": True, "exchange": exchange_code, "ticker": ticker}
