"""Per-stock scraping pipeline — NEWS + CURRENT QUOTE + HISTORY QUOTE.

For each active stock we fetch the overview page and extract:
    * news headlines (stock_news)
    * today's OHLC + volume + market_cap (stock_history_quote — time series)
    * canonical "now" row (stock_quotes — denormalised cache for fast UI;
      reads from stock_history_quote + existing stock_fin_ratios /
      stock_mkt_technicals / stock_mkt_dividends snapshots).

Financials, fundamentals, technicals, dividends remain NOT scraped — those
come from the bulk CSV import. The two quote tables are restored here
because the daily scoring depends on them (price-driven momentum +
verdict).

URL pattern depends on exchange — see Exchange.stockanalysis_url_template:
    * MENA / LSE: /quote/{exchange}/{ticker}/
    * US:         /stocks/{ticker}/

Tables touched:
    stocks               (bumps updated_at, sets currency if discovered)
    stock_news           (UPSERT headlines)
    stock_history_quote  (UPSERT today's OHLC + volume + market_cap)
    stock_quotes         (recomputed canonical "now" row)
    scrape_runs          (audit trail)
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    SessionLocal, Stock, Exchange, ScrapeRun, StockNews,
    StockQuote, StockHistoryQuote,
    StockFinRatios, StockMktTechnicals, StockMktDividends,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .fetcher import HttpFetcher
from .parsers import (
    extract_label_value_pairs, extract_news, build_market_daily,
    extract_close_price, extract_change_pct, extract_currency,
)

log = configure_logging("scraper")
settings = get_settings()


def _quote_url(url_template: str, ticker: str, sub: str = "") -> str:
    """Build a stockanalysis.com URL for this stock."""
    base = settings.scraper_base_url + url_template.format(ticker=ticker)
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


def _upsert_history_quote(session: Session, stock_id: int, today: date,
                          market: dict, change_pct, source: str = "scrape"):
    """OHLC + volume + market_cap → stock_history_quote (time-series).

    Keyed on (stock_id, trading_date), so today's row UPSERTs in place if it
    already exists. Used by the 6-month chart and by the recommender's
    momentum scoring.
    """
    record = {
        "stock_id": stock_id, "trading_date": today,
        "open_price": market.get("open_price"),
        "high_price": market.get("high_price"),
        "low_price":  market.get("low_price"),
        "close_price": market.get("close_price"),
        "volume": market.get("volume"),
        "market_cap": market.get("market_cap"),
        "change_pct": change_pct,
        "source": source,
        "scraped_at": datetime.utcnow(),
    }
    # Drop None values that came in as no-data so we don't clobber a good
    # value from an earlier write today.
    record = {k: v for k, v in record.items() if v is not None
              or k in ("stock_id", "trading_date", "source", "scraped_at")}
    if not any(k in record for k in (
            "open_price", "high_price", "low_price", "close_price", "volume", "market_cap")):
        return
    stmt = pg_insert(StockHistoryQuote).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: stmt.excluded[k] for k in record if k not in ("stock_id", "trading_date")},
    )
    session.execute(stmt)


def _recompute_stock_quote(session: Session, stock_id: int):
    """Refresh the canonical stock_quotes row for this stock.

    Reads the latest stock_history_quote (price + change_pct), the latest
    stock_fin_ratios (PE), the latest stock_mkt_technicals (RSI / 52w / beta),
    and the latest stock_mkt_dividends (yield) — most of these are populated
    by the bulk CSV import, not by us. We just stitch them into the
    denormalised one-row-per-stock cache that the UI screener reads from.

    composite_score and verdict are NOT touched here — the recommender owns
    those and writes them on its own pass.
    """
    hist = session.execute(
        select(StockHistoryQuote)
        .where(StockHistoryQuote.stock_id == stock_id)
        .order_by(desc(StockHistoryQuote.trading_date)).limit(1)
    ).scalar_one_or_none()
    ratios = session.execute(
        select(StockFinRatios.pe_ratio, StockFinRatios.pe_forward)
        .where(StockFinRatios.stock_id == stock_id)
    ).first()
    div = session.execute(
        select(StockMktDividends.dividend_yield_pct)
        .where(StockMktDividends.stock_id == stock_id)
    ).first()
    tech = session.execute(
        select(StockMktTechnicals.rsi_14,
               StockMktTechnicals.week_52_high,
               StockMktTechnicals.week_52_low)
        .where(StockMktTechnicals.stock_id == stock_id)
    ).first()

    if hist is None:
        return  # nothing to denormalise yet

    record = {
        "stock_id": stock_id,
        "current_price": hist.close_price,
        "prev_close": None,    # filled by the bulk import flow; we leave alone
        "change_abs": None,
        "change_pct": hist.change_pct,
        "market_cap": hist.market_cap,
        "pe_ratio": (ratios.pe_ratio if ratios else None),
        "dividend_yield_pct": (div.dividend_yield_pct if div else None),
        "rsi_14": (tech.rsi_14 if tech else None),
        "week_52_high": (tech.week_52_high if tech else None),
        "week_52_low":  (tech.week_52_low if tech else None),
        "price_source": "scrape",
        "price_fetched_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    # Only overwrite fields that we actually have values for — keeps the
    # bulk-import-derived columns (prev_close, composite_score, verdict, etc)
    # intact when the scraper doesn't have them.
    record = {k: v for k, v in record.items() if v is not None or k == "stock_id"}

    stmt = pg_insert(StockQuote).values(**record)
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


# ----- main per-stock job -----

async def scrape_one(fetcher: HttpFetcher, stock_id: int, ticker: str,
                     url_template: str, mode: str = "full"):
    """News + current/history quote scrape.

    We fetch the overview page, parse OHLC + market data + news, write today's
    stock_history_quote row, refresh the canonical stock_quotes cache, and
    upsert any news headlines. Fundamentals / financials / technicals /
    dividends are NOT scraped (those come from the bulk CSV import).
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

    pairs = extract_label_value_pairs(overview_html)
    market = build_market_daily(pairs)
    close_price = extract_close_price(pairs, overview_html)
    if close_price is not None:
        market["close_price"] = close_price
    change_pct = extract_change_pct(overview_html)
    currency = extract_currency(pairs, overview_html)

    news = extract_news(overview_html)
    for item in news:
        item["news_date"] = today

    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                log.error("stock_missing", stock_id=stock_id)
                return

            # Persist currency on the stock row when the page provides it.
            if currency and stock.currency != currency:
                stock.currency = currency

            # Today's OHLC row (or update if we already wrote one this morning).
            _upsert_history_quote(session, stock_id, today, market, change_pct)

            # Refresh the canonical stock_quotes "now" row. Must be after
            # _upsert_history_quote because it reads stock_history_quote.
            _recompute_stock_quote(session, stock_id)

            if news:
                _upsert_news(session, stock_id, news)

            stock.updated_at = datetime.utcnow()

            _record_run(session, stock_id, "stockanalysis.com", "OK",
                        overview_status, None)
            session.commit()
            log.info("scrape_ok", ticker=ticker,
                     news_count=len(news), has_close=close_price is not None)
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
    """Iterate scraping-enabled stocks and scrape them."""
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