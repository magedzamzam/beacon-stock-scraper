"""Bulk CSV importer for stockanalysis.com exchange-level exports.

A single CSV row spans 248 columns covering everything our parallel-schema
tables hold for one stock. This importer fans the row out across:

    * stocks                  (company metadata + ISIN + currency)
    * stock_quotes            (canonical "now" row — current price, change, etc.)
    * stock_history_quote     (today's OHLC + volume + market_cap)
    * stock_fin_ratios        (PE/PB/EV/PEG/etc., keyed by Last Report Date)
    * stock_fin_statement     (Revenue/NI/EBITDA/EPS + growth metrics)
    * stock_fin_cashflow      (OCF/FCF/CapEx/SBC + growth metrics)
    * stock_mkt_dividends     (yield, growth, streaks)
    * stock_mkt_technicals    (RSI/SMA/52w/momentum windows/beta + ATH/ATL)
    * stock_bulk_import_raw   (the original row as jsonb — unmapped columns
                               preserved for future migrations)

Per-row writes are wrapped in a SAVEPOINT so a single bad row is logged but
doesn't poison the whole import.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    Exchange, Stock, StockBulkImport, StockBulkImportRaw,
    StockCurQuote,
    StockEarningsCalendar,
    StockFinCashflow, StockFinRatios, StockFinStatement,
    StockHistoryQuote, StockMktDividends, StockMktTechnicals, StockQuote,
)


# =============================================================================
# Value parsers
# =============================================================================
# stockanalysis.com formats values like:
#   "850.64B"       -> 850_640_000_000
#   "1.23M"         -> 1_230_000
#   "2.5T"          -> 2_500_000_000_000
#   "-2.40%"        -> -2.40         (the percent suffix is informational; we
#                                     return the bare number, so a yield of
#                                     "1.96%" becomes Decimal('1.96'))
#   "Mar 4, 2026"   -> date(2026, 3, 4)
#   "262,884"       -> 262884
#   "True" / "False"-> True / False
#   "-"             -> None          (their canonical missing-value marker)
#   ""              -> None
# =============================================================================

_SUFFIX_MULT = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}

# Pre-compiled regex matching "<number><K|M|B|T>" optionally with sign / decimal
_SUFFIX_RE = re.compile(r"^([\-+]?\d+(?:\.\d+)?)\s*([KMBT])$", re.IGNORECASE)

# Pre-compiled date format list — stockanalysis.com uses "Mon D, YYYY" pretty
# consistently, but allow ISO too.
_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d")


def is_blank(v: Any) -> bool:
    """stockanalysis.com uses '-' as their canonical missing marker."""
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        return s == "" or s == "-" or s.lower() == "n/a"
    return False


def parse_number(raw: Any) -> Optional[Decimal]:
    """Parse stockanalysis.com numbers: 850.64B, -2.40%, 262,884, 43.95.

    Returns None for blanks and unrecognized strings.
    """
    if is_blank(raw):
        return None
    s = str(raw).strip()
    # Strip percent sign — caller knows whether the column is a percentage.
    if s.endswith("%"):
        s = s[:-1]
    # Suffix forms (K/M/B/T)
    m = _SUFFIX_RE.match(s)
    if m:
        try:
            num = Decimal(m.group(1)) * _SUFFIX_MULT[m.group(2).upper()]
            return num
        except InvalidOperation:
            return None
    # Plain number with optional commas
    s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_int(raw: Any) -> Optional[int]:
    n = parse_number(raw)
    if n is None:
        return None
    try:
        return int(n)
    except (ValueError, OverflowError):
        return None


def parse_date(raw: Any) -> Optional[date]:
    if is_blank(raw):
        return None
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_bool(raw: Any) -> Optional[bool]:
    if is_blank(raw):
        return None
    s = str(raw).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    return None


def parse_str(raw: Any) -> Optional[str]:
    if is_blank(raw):
        return None
    s = str(raw).strip()
    return s or None


# =============================================================================
# Row-shaped accessor — the CSV from stockanalysis.com has lots of columns,
# many with punctuation/whitespace. _G makes lookup forgiving.
# =============================================================================

def _G(row: dict[str, Any], *aliases: str) -> Any:
    """Lookup a CSV cell by any of several header aliases (first match wins).

    Returns None if no alias is present in the row dict.
    """
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


# =============================================================================
# Per-row import: stocks + every parallel-schema table
# =============================================================================

def _upsert_stock(
    db: Session, exchange_id: int, ticker: str, row: dict[str, Any],
) -> Stock:
    """Look up Stock by (exchange_id, ticker); create if missing."""
    stock = db.execute(
        select(Stock).where(
            Stock.exchange_id == exchange_id,
            Stock.ticker == ticker,
        )
    ).scalar_one_or_none()

    company_name = parse_str(_G(row, "Company Name")) or ticker
    sector = parse_str(_G(row, "Sector"))
    industry = parse_str(_G(row, "Industry"))
    country = parse_str(_G(row, "Country"))
    isin = parse_str(_G(row, "ISIN Number", "ISIN"))
    website = parse_str(_G(row, "Website"))
    employees = parse_int(_G(row, "Employees"))
    founded = parse_int(_G(row, "Founded"))
    currency = parse_str(_G(row, "Price Curr.", "Price Currency", "Currency"))

    if stock is None:
        stock = Stock(
            exchange_id=exchange_id,
            ticker=ticker,
            company_name=company_name,
            sector=sector, industry=industry, country=country,
            currency=currency, isin=isin, website=website,
            employees=employees, founded_year=founded,
            active=True, is_scraping_enabled=False,  # bulk-imported = not scraped
        )
        db.add(stock)
        db.flush()  # need stock.id for the foreign keys below
    else:
        # Patch only fields that arrived in the CSV (don't blank good data)
        if company_name and not stock.company_name:
            stock.company_name = company_name
        if sector and stock.sector != sector:
            stock.sector = sector
        if industry and stock.industry != industry:
            stock.industry = industry
        if country and not stock.country:
            stock.country = country
        if currency and not stock.currency:
            stock.currency = currency
        if isin and not stock.isin:
            stock.isin = isin
        if website and not stock.website:
            stock.website = website
        if employees and not stock.employees:
            stock.employees = employees
        if founded and not stock.founded_year:
            stock.founded_year = founded
        stock.updated_at = datetime.utcnow()

    return stock


def _upsert_history(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Today's OHLC + volume + market_cap → stock_history_quote."""
    price_date = parse_date(_G(row, "Price Date")) or date.today()
    payload = {
        "open_price": parse_number(_G(row, "Open")),
        "high_price": parse_number(_G(row, "High")),
        "low_price":  parse_number(_G(row, "Low")),
        "close_price": parse_number(_G(row, "Stock Price")),
        "volume":     parse_int(_G(row, "Volume")),
        "market_cap": parse_number(_G(row, "Market Cap")),
        "change_pct": parse_number(_G(row, "% Change")),
        "source":     "bulk_import",
        "scraped_at": datetime.utcnow(),
    }
    if not any(v is not None for v in (payload["open_price"], payload["high_price"],
                                        payload["low_price"], payload["close_price"],
                                        payload["volume"])):
        return
    stmt = pg_insert(StockHistoryQuote).values(
        stock_id=stock_id, trading_date=price_date, **payload,
    ).on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_fin_ratios(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Valuation ratios → stock_fin_ratios.

    period_end comes from "Last Report Date" — failing that, today.
    period_type defaults to "TTM" since these are the trailing snapshot ratios.
    """
    period_end = parse_date(_G(row, "Last Report Date")) or date.today()
    payload = {
        "pe_ratio":    parse_number(_G(row, "PE Ratio")),
        "pe_forward":  parse_number(_G(row, "Forward PE")),
        "ps_ratio":    parse_number(_G(row, "PS Ratio")),
        "pb_ratio":    parse_number(_G(row, "PB Ratio")),
        "p_fcf_ratio": parse_number(_G(row, "P/FCF")),
        "peg_ratio":   parse_number(_G(row, "PEG Ratio")),
        "ev_sales":    parse_number(_G(row, "EV/Sales")),
        "ev_ebitda":   parse_number(_G(row, "EV/EBITDA")),
        "roe":         parse_number(_G(row, "ROE")),
        "roa":         parse_number(_G(row, "ROA")),
        "roic":        parse_number(_G(row, "ROIC")),
        "sbc_revenue_ratio": parse_number(_G(row, "SBC / Rev")),
        "fcf_per_share":     parse_number(_G(row, "FCF / Share")),
        "snapshot_price":      parse_number(_G(row, "Stock Price")),
        "snapshot_market_cap": parse_number(_G(row, "Market Cap")),
        "scraped_at": datetime.utcnow(),
        "current_ratio":    parse_number(_G(row, "Current Ratio")),
        "debt_to_equity":   parse_number(_G(row, "Debt / Equity")),
        "fcf_yield": parse_number(_G(row, "FCF Yield")),
        "z_score": parse_number(_G(row, "Z-Score")),
    }
    if not any(v is not None for v in payload.values() if not isinstance(v, datetime)):
        return
    stmt = pg_insert(StockFinRatios).values(
        stock_id=stock_id, period_end=period_end, period_type="TTM", **payload,
    ).on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_fin_statement(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """P&L items + growth metrics + share structure → stock_fin_statement (TTM)."""
    period_end = parse_date(_G(row, "Last Report Date")) or date.today()
    payload = {
        "last_report_date":  period_end,
        "revenue":           parse_number(_G(row, "Revenue")),
        "gross_profit":      parse_number(_G(row, "Gross Profit")),
        "operating_income":  parse_number(_G(row, "Op. Income")),
        "net_income":        parse_number(_G(row, "Net Income")),
        "ebitda":            parse_number(_G(row, "EBITDA")),
        "income_tax":        parse_number(_G(row, "Income Tax")),
        "eps_diluted":       parse_number(_G(row, "EPS")),
        "revenue_growth_yoy": parse_number(_G(row, "Rev. Growth")),
        "revenue_growth_3y":  parse_number(_G(row, "Rev. Growth 3Y")),
        "revenue_growth_5y":  parse_number(_G(row, "Rev. Growth 5Y")),
        "gross_profit_growth_yoy":   parse_number(_G(row, "GP Growth")),
        "operating_income_growth_yoy": parse_number(_G(row, "OpInc Growth")),
        "net_income_growth_yoy":     parse_number(_G(row, "NetInc Growth")),
        "eps_growth_yoy":            parse_number(_G(row, "EPS Growth")),
        "eps_growth_3y":             parse_number(_G(row, "EPS Growth 3Y")),
        "eps_growth_5y":             parse_number(_G(row, "EPS Growth 5Y")),
        "profitable_years":          parse_int(_G(row, "Profit Years")),
        # Share structure
        "shares_change_yoy":         parse_number(_G(row, "Shares Ch. (YoY)")),
        "shares_change_qoq":         parse_number(_G(row, "Shares Ch. (QoQ)")),
        "shares_insiders_pct":       parse_number(_G(row, "Shares Insiders")),
        "shares_institutional_pct":  parse_number(_G(row, "Shares Institut.")),
        # Cash
        "shares_outstanding":       parse_number(_G(row, "Shares")),
        "net_cash":                 parse_number(_G(row, "Net Cash")),
        "total_debt":               parse_number(_G(row, "Total Debt")),
        "scraped_at":                datetime.utcnow(),
    }
    # Gate the whole write only when we have NOTHING — revenue, EBITDA, EPS,
    # AND no share-structure data. Allows rows that only have shares info
    # (e.g. early-stage companies with no reported revenue yet).
    if not any(v is not None for v in (
        payload["revenue"], payload["net_income"],
        payload["ebitda"], payload["eps_diluted"],
        payload["shares_change_yoy"], payload["shares_change_qoq"],
        payload["shares_insiders_pct"], payload["shares_institutional_pct"],
    )):
        return
    stmt = pg_insert(StockFinStatement).values(
        stock_id=stock_id, period_end=period_end, period_type="TTM",
        is_estimate=False, **payload,
    ).on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type", "is_estimate"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_earnings_calendar(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Earnings calendar + analyst estimates → stock_earnings_calendar.

    The CSV gives us:
        Last Earnings  / Earnings Date  → last_earnings_date
                                          (these are identical in stockanalysis.com
                                          exports, but we prefer Last Earnings)
        Next Earnings                    → next_earnings_date
        Earnings Time                    → 'Before Open' | 'After Close' | ...
        Est. Revenue, Est. Rev. Growth   → forward estimates for the next event
        Est. EPS

    One row per stock (UPSERT on stock_id). If the CSV has no earnings data at
    all for this row, we skip the write entirely.
    """
    payload = {
        "last_earnings_date":     parse_date(_G(row, "Last Earnings", "Earnings Date")),
        "next_earnings_date":     parse_date(_G(row, "Next Earnings")),
        "earnings_time":          parse_str(_G(row, "Earnings Time")),
        "est_revenue":            parse_number(_G(row, "Est. Revenue")),
        "est_revenue_growth_pct": parse_number(_G(row, "Est. Rev. Growth", "Est. Revenue Growth")),
        "est_eps":                parse_number(_G(row, "Est. EPS")),
        "source":                 "bulk_import",
        "updated_at":             datetime.utcnow(),
    }
    if not any(v is not None for v in (
        payload["last_earnings_date"], payload["next_earnings_date"],
        payload["earnings_time"], payload["est_revenue"],
        payload["est_revenue_growth_pct"], payload["est_eps"],
    )):
        return
    stmt = pg_insert(StockEarningsCalendar).values(stock_id=stock_id, **payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_fin_cashflow(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Cashflow items → stock_fin_cashflow (TTM)."""
    period_end = parse_date(_G(row, "Last Report Date")) or date.today()
    payload = {
        "operating_cash_flow": parse_number(_G(row, "Operating CF")),
        "investing_cash_flow": parse_number(_G(row, "Investing CF")),
        "financing_cash_flow": parse_number(_G(row, "Financing CF")),
        "net_cash_flow":       parse_number(_G(row, "Net CF")),
        "cap_ex":              parse_number(_G(row, "CapEx")),
        "free_cash_flow":      parse_number(_G(row, "FCF")),
        "sbc":                 parse_number(_G(row, "SBC")),
        "fcf_minus_sbc":       parse_number(_G(row, "FCF - SBC")),
        "net_borrowing":       parse_number(_G(row, "Net Borrowing")),
        "scraped_at":          datetime.utcnow(),
    }
    if not any(v is not None for v in (payload["operating_cash_flow"],
                                        payload["free_cash_flow"], payload["cap_ex"])):
        return
    stmt = pg_insert(StockFinCashflow).values(
        stock_id=stock_id, period_end=period_end, period_type="TTM",
        is_estimate=False, **payload,
    ).on_conflict_do_update(
        index_elements=["stock_id", "period_end", "period_type", "is_estimate"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_dividends(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Dividend metrics → stock_mkt_dividends (one row per stock)."""
    payload = {
        "dividend_yield_pct":   parse_number(_G(row, "Div. Yield")),
        "dividend_per_share":   parse_number(_G(row, "Div. ($)", "Div.")),
        "last_dividend_amount": parse_number(_G(row, "Last Div.")),
        "ex_dividend_date":     parse_date(_G(row, "Ex-Div Date")),
        "payout_ratio_pct":     parse_number(_G(row, "Payout Ratio")),
        "payout_frequency":     parse_str(_G(row, "Payout Freq.")),
        "div_growth_yoy":       parse_number(_G(row, "Div. Growth")),
        "div_growth_3y":        parse_number(_G(row, "Div. Growth 3Y")),
        "div_growth_5y":        parse_number(_G(row, "Div. Growth 5Y")),
        "growth_years_streak":  parse_int(_G(row, "Div. Gr. Years")),
        "payment_years_streak": parse_int(_G(row, "Div. Years")),
        "scraped_at":           datetime.utcnow(),
    }
    if not any(v is not None for v in payload.values() if not isinstance(v, datetime)):
        return
    stmt = pg_insert(StockMktDividends).values(stock_id=stock_id, **payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_=payload,
    )
    db.execute(stmt)


def _upsert_technicals(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """RSI/SMA/52w/momentum windows/beta/ATH/ATL → stock_mkt_technicals."""
    trading_date = parse_date(_G(row, "Price Date")) or date.today()
    payload = {
        "rsi_14":  parse_number(_G(row, "RSI")),
        "sma_50":  parse_number(_G(row, "50 MA")),
        "sma_200": parse_number(_G(row, "200 MA")),
        "atr_14":  parse_number(_G(row, "ATR")),
        # Momentum (price changes)
        "price_chg_1m_pct": parse_number(_G(row, "Change 1M")),
        "price_chg_3m_pct": parse_number(_G(row, "Change 3M")),
        "price_chg_6m_pct": parse_number(_G(row, "Change 6M")),
        "price_chg_1y_pct": parse_number(_G(row, "Change 1Y")),
        "price_chg_3y_pct": parse_number(_G(row, "Change 3Y")),
        "price_chg_5y_pct": parse_number(_G(row, "Change 5Y")),
        # Total returns (incl. dividends)
        "total_ret_1y_pct": parse_number(_G(row, "Return 1Y")),
        "total_ret_3y_pct": parse_number(_G(row, "Return 3Y")),
        "total_ret_5y_pct": parse_number(_G(row, "Return 5Y")),
        "ret_cagr_3y_pct":  parse_number(_G(row, "CAGR 3Y")),
        "ret_cagr_5y_pct":  parse_number(_G(row, "CAGR 5Y")),
        # 52-week range
        "week_52_high":          parse_number(_G(row, "52W High")),
        "week_52_low":           parse_number(_G(row, "52W Low")),
        "week_52_high_change_pct": parse_number(_G(row, "52W High Chg")),
        "week_52_low_change_pct":  parse_number(_G(row, "52W Low Chg")),
        # All-time
        "ath_price":      parse_number(_G(row, "ATH")),
        "ath_change_pct": parse_number(_G(row, "ATH Chg (%)")),
        # Volume
        "volume_daily":          parse_int(_G(row, "Volume")),
        "dollar_volume_daily":   parse_number(_G(row, "Dollar Vol.")),
        "avg_dollar_volume_30d": parse_number(_G(row, "Avg. Volume")),
        # Beta — prefer 5Y, fall back to 1Y
        "beta": parse_number(_G(row, "Beta (5Y)")) or parse_number(_G(row, "Beta (1Y)")),
        "scraped_at": datetime.utcnow(),
    }
    if not any(v is not None for v in payload.values() if not isinstance(v, datetime)):
        return
    stmt = pg_insert(StockMktTechnicals).values(
        stock_id=stock_id, trading_date=trading_date, **payload,
    ).on_conflict_do_update(
        index_elements=["stock_id", "trading_date"],
        set_=payload,
    )
    db.execute(stmt)


def _recompute_quote(db: Session, stock_id: int, row: dict[str, Any]) -> None:
    """Refresh canonical stock_quotes row from the CSV.

    The bulk import doesn't have broker quotes — this is unconditionally a
    'scrape'-source price. We compute change_pct from Stock Price + Prev.
    Close, fall back to "% Change" if those aren't both present.
    """
    current_price = parse_number(_G(row, "Stock Price"))
    prev_close = parse_number(_G(row, "Prev. Close"))
    change_pct = parse_number(_G(row, "% Change"))
    change_abs = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change_abs = current_price - prev_close
        # Prefer derived change_pct over the CSV's reported one for consistency
        change_pct = (change_abs / prev_close) * 100

    stock = db.get(Stock, stock_id)
    currency = stock.currency if stock else None

    record = {
        "current_price":     current_price,
        "prev_close":        prev_close,
        "change_abs":        change_abs,
        "change_pct":        change_pct,
        "price_source":      "scrape" if current_price is not None else None,
        "price_fetched_at":  datetime.utcnow() if current_price is not None else None,
        "market_cap":        parse_number(_G(row, "Market Cap")),
        "currency":          currency,
        "pe_ratio":          parse_number(_G(row, "PE Ratio")),
        "pe_forward":        parse_number(_G(row, "Forward PE")),
        "dividend_yield_pct": parse_number(_G(row, "Div. Yield")),
        "rsi_14":            parse_number(_G(row, "RSI")),
        "week_52_high":      parse_number(_G(row, "52W High")),
        "week_52_low":       parse_number(_G(row, "52W Low")),
        "last_updated":      datetime.utcnow(),
    }
    stmt = pg_insert(StockQuote).values(stock_id=stock_id, **record).on_conflict_do_update(
        index_elements=["stock_id"],
        # Don't blow away composite_score / verdict (set by the recommender).
        set_=record,
    )
    db.execute(stmt)


# =============================================================================
# Public entry point
# =============================================================================

def execute_bulk_import(
    db: Session,
    *,
    exchange_id: int,
    user_id: Optional[int],
    filename: Optional[str],
    file_bytes: bytes,
) -> dict[str, Any]:
    """Stream the CSV, fan each row across the parallel-schema tables.

    The whole job lives under a single audit row in stock_bulk_imports.
    Each per-row write happens in a SAVEPOINT so a single bad row gets logged
    but doesn't roll back the rest of the import.
    """
    # Decode (UTF-8 with BOM tolerance, fall back to latin-1)
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    # Audit row — single source of truth for outcome
    job = StockBulkImport(
        exchange_id=exchange_id, user_id=user_id, filename=filename,
        started_at=datetime.utcnow(), status="running",
    )
    db.add(job)
    db.flush()
    job_id = job.id

    inserted = updated = skipped = errored = 0
    row_logs: list[dict[str, Any]] = []

    reader = csv.DictReader(io.StringIO(text))
    rows_total = 0

    try:
        for row_number, row in enumerate(reader, start=2):
            rows_total += 1
            ticker_raw = parse_str(_G(row, "Symbol", "Ticker"))
            if not ticker_raw:
                skipped += 1
                _log(row_logs, row_number, "skipped",
                     "Row has no Symbol — skipped")
                continue
            ticker = ticker_raw.upper()

            try:
                with db.begin_nested():
                    existed = db.execute(
                        select(Stock.id).where(
                            Stock.exchange_id == exchange_id,
                            Stock.ticker == ticker,
                        )
                    ).scalar_one_or_none()
                    is_new = existed is None

                    stock = _upsert_stock(db, exchange_id, ticker, row)
                    _upsert_history(db, stock.id, row)
                    _upsert_fin_ratios(db, stock.id, row)
                    _upsert_fin_statement(db, stock.id, row)
                    _upsert_fin_cashflow(db, stock.id, row)
                    _upsert_dividends(db, stock.id, row)
                    _upsert_technicals(db, stock.id, row)
                    _upsert_earnings_calendar(db, stock.id, row)
                    _recompute_quote(db, stock.id, row)

                    # Preserve the raw row for future re-mapping
                    db.add(StockBulkImportRaw(
                        import_id=job_id,
                        stock_id=stock.id,
                        ticker=ticker,
                        raw_payload=row,
                        imported_at=datetime.utcnow(),
                    ))

                if is_new:
                    inserted += 1
                    _log(row_logs, row_number, "inserted",
                         f"New stock {ticker} created and populated")
                else:
                    updated += 1
                    _log(row_logs, row_number, "updated",
                         f"Stock {ticker} updated")
            except Exception as exc:
                errored += 1
                _log(row_logs, row_number, "error", f"{ticker}: {exc}")

        job.status = "ok"
        job.finished_at = datetime.utcnow()
        job.rows_total = rows_total
        job.rows_inserted = inserted
        job.rows_updated = updated
        job.rows_skipped = skipped
        job.rows_errored = errored
        job.summary = {"row_logs": row_logs[:200]}  # cap to keep audit row small
        db.commit()

    except Exception as exc:
        db.rollback()
        # Re-fetch the job (rollback nuked the in-flight state) and mark failed
        with db.begin():
            failed = db.get(StockBulkImport, job_id)
            if failed:
                failed.status = "failed"
                failed.finished_at = datetime.utcnow()
                failed.error_message = str(exc)
        raise

    return {
        "import_id": job_id,
        "status": job.status,
        "rows_total": rows_total,
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_skipped": skipped,
        "rows_errored": errored,
        "row_logs": row_logs,
    }


def preview_bulk_import(file_bytes: bytes, *, sample_rows: int = 5) -> dict[str, Any]:
    """Read the first N rows and return their parsed shape for the UI.

    Doesn't touch the DB — pure CSV inspection.
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    samples: list[dict[str, Any]] = []
    total = 0
    tickers_seen: list[str] = []
    rows_no_symbol = 0

    for i, row in enumerate(reader):
        total += 1
        ticker = parse_str(_G(row, "Symbol", "Ticker"))
        if ticker:
            tickers_seen.append(ticker.upper())
        else:
            rows_no_symbol += 1
        if i < sample_rows:
            # Show a compact subset — full row would be huge in the UI
            samples.append({
                "ticker": ticker,
                "company_name": parse_str(_G(row, "Company Name")),
                "sector": parse_str(_G(row, "Sector")),
                "stock_price": parse_str(_G(row, "Stock Price")),
                "market_cap": parse_str(_G(row, "Market Cap")),
                "pe_ratio": parse_str(_G(row, "PE Ratio")),
                "last_report_date": parse_str(_G(row, "Last Report Date")),
            })

    has_symbol = "Symbol" in headers or "Ticker" in headers
    return {
        "headers": headers,
        "header_count": len(headers),
        "row_count": total,
        "has_symbol_column": has_symbol,
        "rows_with_no_symbol": rows_no_symbol,
        "sample_tickers": tickers_seen[:10],
        "samples": samples,
    }


def _log(logs: list[dict[str, Any]], row_number: int, action: str, message: str) -> None:
    if len(logs) >= 200:
        return
    logs.append({"row_number": row_number, "action": action, "message": message})
