"""Per-stock scraping pipeline.

For each active stock we fetch (URL pattern depends on exchange — see
Exchange.stockanalysis_url_template):
    * MENA / LSE: /quote/{exchange}/{ticker}/[statistics/]
    * US:         /stocks/{ticker}/[statistics/]

We then UPSERT into the parallel-schema tables:
    stocks (company metadata),
    stock_history_quote (daily OHLC time-series),
    stock_fin_ratios (PE / PB / EV multiples per period),
    stock_fin_statement (P&L items per period),
    stock_fin_cashflow (cashflow items per period),
    stock_mkt_technicals (RSI / SMAs / momentum windows / 52w / beta),
    stock_mkt_dividends (dividend metrics — one row per stock),
    stock_news (headlines),
    stock_quotes (canonical 'now' row — denormalised cache for fast UI),
    scrape_runs (audit trail, per source).
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
    # Round-2 dual-write targets are now the only writers (Round 4):
    StockQuote, StockCurQuote, StockHistoryQuote,
    StockFinRatios, StockFinStatement, StockFinCashflow,
    StockMktDividends, StockMktTechnicals,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .fetcher import HttpFetcher
from .parsers import (
    extract_label_value_pairs, extract_company_blurb, extract_news,
    build_market_daily, build_valuation, build_financials_ttm,
    build_technicals, extract_close_price, extract_change_pct, extract_currency,
)

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


# =============================================================================
# UPSERT helpers writing to the parallel-schema tables.
# =============================================================================

def _upsert_history_quote(session: Session, stock_id: int, today: date,
                          market: dict, change_pct, source: str = "scrape"):
    """Write OHLC + volume + market_cap + change_pct to stock_history_quote."""
    record = {
        "stock_id": stock_id, "trading_date": today,
        "open_price": market.get("open_price"),
        "high_price": market.get("high_price"),
        "low_price": market.get("low_price"),
        "close_price": market.get("close_price"),
        "volume": market.get("volume"),
        "market_cap": market.get("market_cap"),
        "change_pct": change_pct,
        "source": source,
        "scraped_at": datetime.utcnow(),
    }
    if not any(record[k] is not None for k in
               ("open_price", "high_price", "low_price", "close_price", "volume")):
        return  # nothing meaningful to write
    stmt = pg_insert(StockHistoryQuote).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: stmt.excluded[k] for k in record if k not in ("stock_id", "trading_date")},
    )
    session.execute(stmt)


def _upsert_fin_ratios(session: Session, stock_id: int, period_end: date,
                       period_type: str, ratios: dict):
    """Write valuation ratios to stock_fin_ratios."""
    if not any(v is not None for v in ratios.values()):
        return
    record = {
        "stock_id": stock_id, "period_end": period_end, "period_type": period_type,
        "scraped_at": datetime.utcnow(),
        **ratios,
    }
    stmt = pg_insert(StockFinRatios).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type"],
        set_={k: stmt.excluded[k] for k in record if k not in ("stock_id", "period_end", "period_type")},
    )
    session.execute(stmt)


def _upsert_fin_statement(session: Session, stock_id: int, period_end: date,
                          period_type: str, payload: dict, is_estimate: bool = False):
    """Write P&L items to stock_fin_statement."""
    if not any(v is not None for v in payload.values()):
        return
    record = {
        "stock_id": stock_id, "period_end": period_end, "period_type": period_type,
        "is_estimate": is_estimate, "scraped_at": datetime.utcnow(),
        **payload,
    }
    stmt = pg_insert(StockFinStatement).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type", "is_estimate"],
        set_={k: stmt.excluded[k] for k in record
              if k not in ("stock_id", "period_end", "period_type", "is_estimate")},
    )
    session.execute(stmt)


def _upsert_fin_cashflow(session: Session, stock_id: int, period_end: date,
                         period_type: str, payload: dict, is_estimate: bool = False):
    """Write cashflow items to stock_fin_cashflow."""
    if not any(v is not None for v in payload.values()):
        return
    record = {
        "stock_id": stock_id, "period_end": period_end, "period_type": period_type,
        "is_estimate": is_estimate, "scraped_at": datetime.utcnow(),
        **payload,
    }
    stmt = pg_insert(StockFinCashflow).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type", "is_estimate"],
        set_={k: stmt.excluded[k] for k in record
              if k not in ("stock_id", "period_end", "period_type", "is_estimate")},
    )
    session.execute(stmt)


def _upsert_mkt_dividends(session: Session, stock_id: int, payload: dict):
    """Write dividend metrics to stock_mkt_dividends (one row per stock)."""
    if not any(v is not None for v in payload.values()):
        return
    record = {"stock_id": stock_id, "scraped_at": datetime.utcnow(), **payload}
    stmt = pg_insert(StockMktDividends).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={k: stmt.excluded[k] for k in record if k != "stock_id"},
    )
    session.execute(stmt)


def _upsert_mkt_technicals(session: Session, stock_id: int, today: date, payload: dict):
    """Write technical indicators to stock_mkt_technicals."""
    if not any(v is not None for v in payload.values()):
        return
    record = {
        "stock_id": stock_id, "trading_date": today,
        "scraped_at": datetime.utcnow(),
        **payload,
    }
    stmt = pg_insert(StockMktTechnicals).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_={k: stmt.excluded[k] for k in record if k not in ("stock_id", "trading_date")},
    )
    session.execute(stmt)


def _recompute_stock_quote(session: Session, stock_id: int):
    """Refresh stock_quotes (the canonical "now" row) from latest scrape data.

    Strategy:
      * current_price: prefer fresh broker quote (<30 min old) else latest
        scrape close from stock_history_quote.
      * prev_close: second-most-recent close in stock_history_quote.
      * change_abs / change_pct: derived from current_price + prev_close.
      * Denormalised ratios from latest stock_fin_ratios + stock_mkt_technicals
        + stock_analyst_consensus + stock_mkt_dividends.

    Called at the end of scrape_one. Round-3 will move broker-quote refresh
    callers (broker_quotes router, scheduler) to also call this.
    """
    from sqlalchemy import select, desc as _desc  # local imports to keep top tidy
    from shared.db import StockAnalystConsensus  # noqa: PLC0415

    # --- price block --------------------------------------------------------
    hist = session.execute(
        select(StockHistoryQuote.close_price, StockHistoryQuote.market_cap,
               StockHistoryQuote.trading_date)
        .where(StockHistoryQuote.stock_id == stock_id,
               StockHistoryQuote.close_price.is_not(None))
        .order_by(_desc(StockHistoryQuote.trading_date)).limit(2)
    ).all()
    latest_close = hist[0].close_price if hist else None
    prev_close = hist[1].close_price if len(hist) >= 2 else None
    market_cap = hist[0].market_cap if hist else None

    # See if a fresh broker quote exists for this stock.
    bq = session.execute(
        select(StockCurQuote.last_price, StockCurQuote.fetched_at)
        .where(StockCurQuote.stock_id == stock_id,
               StockCurQuote.last_price.is_not(None))
        .order_by(_desc(StockCurQuote.fetched_at)).limit(1)
    ).first()
    use_broker = False
    if bq is not None and bq.fetched_at is not None:
        age = (datetime.utcnow() - bq.fetched_at).total_seconds()
        if age < 30 * 60:
            use_broker = True

    if use_broker:
        current_price = bq.last_price
        price_source = "broker"
        price_fetched_at = bq.fetched_at
    elif latest_close is not None:
        current_price = latest_close
        price_source = "scrape"
        price_fetched_at = datetime.utcnow()
    else:
        current_price = None
        price_source = None
        price_fetched_at = None

    change_abs = change_pct = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change_abs = current_price - prev_close
        change_pct = (change_abs / prev_close) * 100

    # --- denormalised ratios + technicals + analyst -------------------------
    ratios = session.execute(
        select(StockFinRatios.pe_ratio, StockFinRatios.pe_forward)
        .where(StockFinRatios.stock_id == stock_id)
        .order_by(_desc(StockFinRatios.period_end), _desc(StockFinRatios.id)).limit(1)
    ).first()
    div = session.execute(
        select(StockMktDividends.dividend_yield_pct).where(StockMktDividends.stock_id == stock_id)
    ).first()
    tech = session.execute(
        select(StockMktTechnicals.rsi_14, StockMktTechnicals.week_52_high,
               StockMktTechnicals.week_52_low)
        .where(StockMktTechnicals.stock_id == stock_id)
        .order_by(_desc(StockMktTechnicals.trading_date)).limit(1)
    ).first()
    analyst = session.execute(
        select(StockAnalystConsensus.target_price, StockAnalystConsensus.implied_upside_pct)
        .where(StockAnalystConsensus.stock_id == stock_id)
        .order_by(_desc(StockAnalystConsensus.consensus_date)).limit(1)
    ).first()

    stock = session.get(Stock, stock_id)
    currency = stock.currency if stock else None

    # Build the upsert. Use ON CONFLICT DO UPDATE to PRESERVE columns we don't
    # set (composite_score, verdict — those are owned by recommender).
    record = {
        "stock_id": stock_id,
        "current_price": current_price,
        "prev_close": prev_close,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "price_source": price_source,
        "price_fetched_at": price_fetched_at,
        "market_cap": market_cap,
        "currency": currency,
        "pe_ratio": ratios.pe_ratio if ratios else None,
        "pe_forward": ratios.pe_forward if ratios else None,
        "dividend_yield_pct": div.dividend_yield_pct if div else None,
        "rsi_14": tech.rsi_14 if tech else None,
        "week_52_high": tech.week_52_high if tech else None,
        "week_52_low": tech.week_52_low if tech else None,
        "analyst_target": analyst.target_price if analyst else None,
        "analyst_upside_pct": analyst.implied_upside_pct if analyst else None,
        "last_updated": datetime.utcnow(),
    }
    stmt = pg_insert(StockQuote).values(**record)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        # Only overwrite columns we just set — preserve composite_score / verdict
        # (those are owned by the recommender).
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

async def scrape_one(fetcher: HttpFetcher, stock_id: int, ticker: str,
                     url_template: str, mode: str = "full"):
    """One stock = one or two HTTP calls + one DB transaction.

    url_template comes from Exchange.stockanalysis_url_template — e.g.
    '/quote/dfm/{ticker}/' for DFM or '/stocks/{ticker}/' for NASDAQ.

    mode='daily' fetches only the overview page (price, technicals, news,
    analyst block) and writes the new parallel-schema price + technicals + news.

    mode='full' (default) additionally fetches the statistics page so we can
    populate stock_fin_ratios / stock_fin_statement / stock_fin_cashflow with
    multi-period growth metrics. That data only changes quarterly, so daily
    mode skips it.
    """
    today = date.today()
    overview_html: str | None = None
    statistics_html: str | None = None
    overview_status = stats_status = None
    err: str | None = None

    try:
        overview_status, overview_html = await fetcher.get(_quote_url(url_template, ticker))
    except Exception as exc:
        err = f"overview: {exc}"
        log.warning("overview_fetch_failed", ticker=ticker, error=str(exc))

    if mode == "full":
        try:
            stats_status, statistics_html = await fetcher.get(_quote_url(url_template, ticker, "statistics"))
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
    for item in news:
        item["news_date"] = today
        
    market = build_market_daily(pairs)
    valuation = build_valuation(pairs)
    financials = build_financials_ttm(pairs)
    technicals = build_technicals(pairs)
    close_price = extract_close_price(pairs, overview_html or "")
    if close_price is not None:
        market["close_price"] = close_price
    change_pct = extract_change_pct(overview_html or "")
    currency = extract_currency(pairs, overview_html or "")

    with SessionLocal() as session:
        try:
            stock = session.get(Stock, stock_id)
            if stock is None:
                log.error("stock_missing", stock_id=stock_id)
                return

            _update_stock_metadata(session, stock, blurb)
            # Persist currency on the stock row when the page provides it.
            if currency and stock.currency != currency:
                stock.currency = currency
                stock.updated_at = datetime.utcnow()

            # OHLC + volume + market_cap → stock_history_quote
            _upsert_history_quote(session, stock_id, today, market, change_pct)

            # Valuation + multi-period financials change quarterly. Skip in
            # daily mode to keep the scrape lightweight.
            if mode == "full":
                # period_end = Dec 31 of fiscal_year (best we can derive without
                # an explicit reporting date from the scraper).
                period_end = today.replace(month=12, day=31)
                _upsert_fin_ratios(session, stock_id, period_end, "ANNUAL", {
                    "pe_ratio": valuation.get("pe") or market.get("pe_ratio"),
                    "pe_forward": market.get("forward_pe"),
                    "ps_ratio": None,
                    "pb_ratio": valuation.get("price_to_book"),
                    "p_fcf_ratio": None,
                    "ev_sales": valuation.get("ev_sales"),
                    "ev_ebitda": valuation.get("ev_ebitda"),
                    "snapshot_price": market.get("close_price"),
                    "snapshot_market_cap": market.get("market_cap"),
                })
                _upsert_fin_statement(session, stock_id, period_end, "TTM", {
                    "revenue": financials.get("revenue"),
                    "operating_income": financials.get("operating_income"),
                    "net_income": financials.get("net_income"),
                    "ebitda": financials.get("ebitda"),
                })
                _upsert_fin_cashflow(session, stock_id, period_end, "TTM", {
                    "operating_cash_flow": financials.get("operating_cash_flow"),
                    "free_cash_flow": financials.get("free_cash_flow"),
                })

            # Technicals → stock_mkt_technicals.
            # Fold in 52w from the market payload since they belong here.
            _upsert_mkt_technicals(session, stock_id, today, {
                **technicals,
                "week_52_high": market.get("week_52_high"),
                "week_52_low": market.get("week_52_low"),
                "beta": market.get("beta"),
                "volume_daily": market.get("volume"),
            })

            # Dividends → stock_mkt_dividends (one row per stock)
            _upsert_mkt_dividends(session, stock_id, {
                "dividend_yield_pct": market.get("dividend_yield_pct"),
                "dividend_per_share": market.get("dividend"),
                "ex_dividend_date": market.get("ex_dividend_date"),
                "payout_ratio_pct": market.get("payout_ratio_pct"),
                "payout_frequency": market.get("payout_frequency"),
                "div_growth_yoy": market.get("dividend_growth_pct"),
            })

            if news:
                _upsert_news(session, stock_id, news)

            # Refresh canonical stock_quotes row.
            # MUST be called LAST since it reads from stock_history_quote +
            # stock_fin_ratios + stock_mkt_technicals + stock_mkt_dividends.
            _recompute_stock_quote(session, stock_id)

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