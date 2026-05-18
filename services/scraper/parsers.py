"""Parsers for stockanalysis.com pages.

One parser per URL we scrape. Each returns a plain dict mapped to the DB
columns it will eventually populate — no DB access, pure functions.

Page layout on stockanalysis.com is mostly two-column tables ('label | value'),
so we extract every (label, value) pair once with extract_label_value_pairs()
and then each per-page parser is just a label-lookup function. New labels
appearing on the source page are silently ignored unless we look them up
explicitly.

The number/percent/date parsers are tolerant of 'n/a', '-', '—', 'Upgrade'
(a paywall placeholder), so a missing field stays NULL in the DB rather
than crashing the run.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup


# =============================================================================
# Value parsers
# =============================================================================
_SUFFIX_MULTIPLIER = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_BLANK = {"", "n/a", "na", "-", "—", "upgrade"}


def parse_number(raw: Optional[str]) -> Optional[Decimal]:
    """Parse strings like '871.14B', '+9.40 (2.41%)', '45.01', '171,124'.

    Returns None on blank / 'n/a' / paywall markers.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _BLANK:
        return None
    m = re.match(r"^\s*([+-]?[\d,]+\.?\d*)\s*([KMBT])?", s)
    if not m:
        return None
    num_str, suffix = m.group(1), m.group(2)
    try:
        value = Decimal(num_str.replace(",", ""))
    except InvalidOperation:
        return None
    if suffix:
        value *= Decimal(str(_SUFFIX_MULTIPLIER[suffix]))
    return value


def parse_percent(raw: Optional[str]) -> Optional[Decimal]:
    if raw is None:
        return None
    return parse_number(str(raw).replace("%", ""))


def parse_date(raw: Optional[str]) -> Optional[date]:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _BLANK:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(raw: Optional[str]) -> Optional[int]:
    n = parse_number(raw)
    return int(n) if n is not None else None


# =============================================================================
# Shared HTML helpers
# =============================================================================
def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_label_value_pairs(html: str) -> dict[str, str]:
    """Walk every two-column table; return {label: value}.

    First occurrence wins — pages can repeat the same label in different
    contexts (e.g. summary table + detail table), and the summary version
    is usually what we want.
    """
    soup = make_soup(html)
    out: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) == 2:
            label = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if label and value and label not in out:
                out[label] = value
    return out


def _get(pairs: dict[str, str], *aliases: str) -> Optional[str]:
    """Look up the first matching label from a list of aliases."""
    for a in aliases:
        if a in pairs and pairs[a]:
            return pairs[a]
    return None


# =============================================================================
# Per-page parsers
# =============================================================================
def parse_overview_page(html: str) -> dict:
    """Overview page (e.g. /stocks/tsla/ or /quote/egx/comi/).

    The light-touch daily fetch. Returns:
        company:     {company_name, industry, country, founded_year}
        quote:       {current_price, change_pct, currency, market_cap, ...}
        history_row: {open_price, high_price, low_price, close_price,
                      volume, market_cap, change_pct} for today's row
        news:        [ {headline, url, source_code}, ... ]
    """
    pairs = extract_label_value_pairs(html)
    soup = make_soup(html)

    # --- Company blurb (only used to fill stocks.* fields if still null) ---
    company = {"company_name": None, "industry": None,
               "country": None, "founded_year": None}
    h1 = soup.find("h1")
    if h1:
        m = re.match(r"^(.+?)\s*\(([A-Z]+):([A-Z0-9]+)\)\s*$",
                     h1.get_text(strip=True))
        if m:
            company["company_name"] = m.group(1).strip()
        else:
            company["company_name"] = h1.get_text(strip=True)
    body_text = soup.get_text("\n", strip=True)
    for key, ckey in (("Industry", "industry"), ("Country", "country")):
        m = re.search(rf"^{key}\s+(.+)$", body_text, flags=re.MULTILINE)
        if m:
            company[ckey] = m.group(1).strip()
    m = re.search(r"^Founded\s+(\d{4})", body_text, flags=re.MULTILINE)
    if m:
        company["founded_year"] = int(m.group(1))

    # --- Quote / market data ---
    close_price = parse_number(_get(pairs, "Stock Price", "Price", "Last Trade"))
    change_pct = _extract_change_pct(html)
    market_cap = parse_number(_get(pairs, "Market Cap"))
    volume = parse_int(_get(pairs, "Volume"))
    open_p = parse_number(_get(pairs, "Open"))
    high_p, low_p = _day_range(_get(pairs, "Day Range"))
    week_52_high, week_52_low = _day_range(_get(pairs, "52-Week Range"))

    quote = {
        "current_price": close_price,
        "change_pct": change_pct,
        "currency": _extract_currency(pairs, soup),
        "market_cap": market_cap,
        "pe_ratio": parse_number(_get(pairs, "PE Ratio", "P/E Ratio")),
        "pe_forward": parse_number(_get(pairs, "Forward PE", "Forward P/E")),
        "dividend_yield_pct": parse_percent(
            _get(pairs, "Dividend Yield", "Dividend (Yield)", "Yield")),
        "rsi_14": parse_number(_get(pairs, "RSI (14)", "RSI")),
        "week_52_high": week_52_high,
        "week_52_low": week_52_low,
    }

    history_row = {
        "open_price": open_p,
        "high_price": high_p,
        "low_price": low_p,
        "close_price": close_price,
        "volume": volume,
        "market_cap": market_cap,
        "change_pct": change_pct,
    }

    news = _extract_news(soup)

    return {
        "company": company,
        "quote": quote,
        "history_row": history_row,
        "news": news,
    }


def parse_statistics_page(html: str) -> dict:
    """Statistics page — the most label-dense page on the site.

    Maps to:
        ratios:     PE/PB/PS/PEG/EV/ROE/ROA/ROIC/FCF metrics
        fin_stmt:   shares-outstanding + insider/institutional + growth
        dividends:  yield, payout, frequency, growth streaks
        technicals: 52w, ATH, beta, SMA, volume avgs
    """
    pairs = extract_label_value_pairs(html)

    week_52_high, week_52_low = _day_range(_get(pairs, "52-Week Range"))

    ratios = {
        "pe_ratio":       parse_number(_get(pairs, "PE Ratio")),
        "pe_forward":     parse_number(_get(pairs, "Forward PE")),
        "ps_ratio":       parse_number(_get(pairs, "PS Ratio")),
        "pb_ratio":       parse_number(_get(pairs, "PB Ratio")),
        "p_fcf_ratio":    parse_number(_get(pairs, "P/FCF Ratio", "P/FCF")),
        "peg_ratio":      parse_number(_get(pairs, "PEG Ratio")),
        "ev_sales":       parse_number(_get(pairs, "EV/Sales")),
        "ev_ebitda":      parse_number(_get(pairs, "EV/EBITDA")),
        "roe":            parse_percent(_get(pairs, "Return on Equity (ROE)")),
        "roa":            parse_percent(_get(pairs, "Return on Assets (ROA)")),
        "roic":           parse_percent(_get(pairs, "Return on Capital (ROIC)")),
        "current_ratio":  parse_number(_get(pairs, "Current Ratio")),
        "debt_to_equity": parse_number(_get(pairs, "Debt / Equity Ratio",
                                            "Debt / Equity", "D/E")),
        "fcf_yield":      parse_percent(_get(pairs, "FCF Yield")),
        "fcf_per_share":  parse_number(_get(pairs, "FCF per Share")),
        "sbc_revenue_ratio": parse_percent(_get(pairs, "SBC / Revenue")),
    }

    fin_stmt = {
        "shares_outstanding": parse_number(_get(pairs, "Shares Outstanding")),
        "shares_change_yoy":  parse_percent(_get(pairs, "Shares Change (YoY)",
                                                 "Shares Ch. (YoY)")),
        "shares_change_qoq":  parse_percent(_get(pairs, "Shares Change (QoQ)",
                                                 "Shares Ch. (QoQ)")),
        "shares_insiders_pct": parse_percent(_get(pairs, "Owned by Insiders",
                                                  "Shares Insiders")),
        "shares_institutional_pct": parse_percent(_get(pairs, "Owned by Institutions",
                                                       "Shares Institut.")),
        "net_cash": parse_number(_get(pairs, "Net Cash")),
        "total_debt": parse_number(_get(pairs, "Total Debt")),
        "profitable_years": parse_int(_get(pairs, "Profitable Years")),
    }

    dividends = {
        "dividend_yield_pct": parse_percent(_get(pairs, "Dividend Yield")),
        "dividend_per_share": parse_number(_get(pairs, "Dividend",
                                                "Dividend Per Share")),
        "ex_dividend_date":   parse_date(_get(pairs, "Ex-Dividend Date")),
        "payout_ratio_pct":   parse_percent(_get(pairs, "Payout Ratio")),
        "payout_frequency":   _get(pairs, "Payout Frequency"),
        "div_growth_yoy":     parse_percent(_get(pairs, "Dividend Growth (YoY)",
                                                 "Div. Growth")),
        "div_growth_3y":      parse_percent(_get(pairs, "Dividend Growth (3Y)")),
        "div_growth_5y":      parse_percent(_get(pairs, "Dividend Growth (5Y)")),
        "growth_years_streak":  parse_int(_get(pairs, "Years of Growth",
                                               "Growth Streak")),
        "payment_years_streak": parse_int(_get(pairs, "Years of Payments",
                                               "Payment Streak")),
    }

    technicals = {
        "rsi_14":   parse_number(_get(pairs, "RSI (14)", "RSI")),
        "sma_50":   parse_number(_get(pairs, "50-Day Moving Average", "SMA 50")),
        "sma_200":  parse_number(_get(pairs, "200-Day Moving Average", "SMA 200")),
        "atr_14":   parse_number(_get(pairs, "ATR (14)")),
        "volatility_30d": parse_percent(_get(pairs, "Volatility (30-Day)",
                                             "30-Day Volatility")),
        "beta":     parse_number(_get(pairs, "Beta (5Y)", "Beta")),
        "week_52_high": week_52_high,
        "week_52_low":  week_52_low,
        "week_52_high_change_pct": parse_percent(_get(pairs, "52-Week Change")),
        "ath_price":         parse_number(_get(pairs, "All-Time High")),
        "ath_change_pct":    parse_percent(_get(pairs, "Change from ATH")),
        "price_chg_1m_pct":  parse_percent(_get(pairs, "1-Month Return",
                                                "Performance (1M)")),
        "price_chg_3m_pct":  parse_percent(_get(pairs, "3-Month Return",
                                                "Performance (3M)")),
        "price_chg_6m_pct":  parse_percent(_get(pairs, "6-Month Return",
                                                "Performance (6M)")),
        "price_chg_1y_pct":  parse_percent(_get(pairs, "1-Year Return",
                                                "Performance (1Y)")),
        "price_chg_3y_pct":  parse_percent(_get(pairs, "3-Year Return",
                                                "Performance (3Y)")),
        "price_chg_5y_pct":  parse_percent(_get(pairs, "5-Year Return",
                                                "Performance (5Y)")),
        "volume_daily": parse_int(_get(pairs, "Volume")),
        "avg_dollar_volume_30d": parse_number(_get(pairs, "Average Volume (30 Days)",
                                                   "Avg. Volume")),
    }

    return {"ratios": ratios, "fin_stmt": fin_stmt,
            "dividends": dividends, "technicals": technicals}


def parse_financials_page(html: str) -> dict:
    """Income statement page (/financials/). Maps to stock_fin_statement (P&L)."""
    cols = _read_financial_table(html)
    pick = cols.get("TTM") or (list(cols.values())[-1] if cols else {})
    return {
        "revenue":          parse_number(pick.get("Revenue")),
        "gross_profit":     parse_number(pick.get("Gross Profit")),
        "operating_income": parse_number(pick.get("Operating Income")),
        "net_income":       parse_number(pick.get("Net Income")),
        "ebitda":           parse_number(pick.get("EBITDA")),
        "income_tax":       parse_number(pick.get("Income Tax",
                                                  pick.get("Tax Provision"))),
        "eps_diluted":      parse_number(pick.get("EPS (Diluted)",
                                                  pick.get("EPS"))),
        "revenue_growth_yoy":          parse_percent(pick.get("Revenue Growth (YoY)")),
        "net_income_growth_yoy":       parse_percent(pick.get("Net Income Growth (YoY)")),
        "operating_income_growth_yoy": parse_percent(pick.get("Operating Income Growth")),
        "eps_growth_yoy":              parse_percent(pick.get("EPS Growth (YoY)")),
        "period_end": parse_date(pick.get("_header")),
    }


def parse_balance_sheet_page(html: str) -> dict:
    """Balance sheet page. Cash & debt for stock_fin_statement."""
    cols = _read_financial_table(html)
    pick = cols.get("TTM") or (list(cols.values())[-1] if cols else {})
    cash = parse_number(pick.get("Cash & Equivalents",
                                 pick.get("Cash And Short Term Investments")))
    total_debt = parse_number(pick.get("Total Debt"))
    return {
        "shares_outstanding": parse_number(pick.get("Shares Outstanding",
                                                    pick.get("Common Stock Shares Outstanding"))),
        "total_debt": total_debt,
        "net_cash": (cash - total_debt) if (cash is not None and total_debt is not None) else None,
    }


def parse_cashflow_page(html: str) -> dict:
    """Cash flow page. Maps to stock_fin_cashflow."""
    cols = _read_financial_table(html)
    pick = cols.get("TTM") or (list(cols.values())[-1] if cols else {})
    return {
        "operating_cash_flow": parse_number(pick.get("Operating Cash Flow")),
        "investing_cash_flow": parse_number(pick.get("Investing Cash Flow")),
        "financing_cash_flow": parse_number(pick.get("Financing Cash Flow")),
        "net_cash_flow":       parse_number(pick.get("Net Cash Flow")),
        "cap_ex":              parse_number(pick.get("Capital Expenditures",
                                                     pick.get("CapEx"))),
        "free_cash_flow":      parse_number(pick.get("Free Cash Flow")),
        "sbc":                 parse_number(pick.get("Stock-Based Compensation")),
        "net_borrowing":       parse_number(pick.get("Net Debt Issued/Repaid",
                                                     pick.get("Net Borrowing"))),
        "period_end": parse_date(pick.get("_header")),
    }


def parse_ratios_page(html: str) -> dict:
    """Ratios page. Most also appear on /statistics but this page is canonical."""
    cols = _read_financial_table(html)
    pick = cols.get("TTM") or (list(cols.values())[-1] if cols else {})
    return {
        "pe_ratio":       parse_number(pick.get("PE Ratio")),
        "pe_forward":     parse_number(pick.get("Forward PE")),
        "ps_ratio":       parse_number(pick.get("PS Ratio")),
        "pb_ratio":       parse_number(pick.get("PB Ratio")),
        "p_fcf_ratio":    parse_number(pick.get("P/FCF Ratio")),
        "peg_ratio":      parse_number(pick.get("PEG Ratio")),
        "ev_sales":       parse_number(pick.get("EV/Sales")),
        "ev_ebitda":      parse_number(pick.get("EV/EBITDA")),
        "roe":            parse_percent(pick.get("Return on Equity (ROE)")),
        "roa":            parse_percent(pick.get("Return on Assets (ROA)")),
        "roic":           parse_percent(pick.get("Return on Capital (ROIC)")),
        "current_ratio":  parse_number(pick.get("Current Ratio")),
        "debt_to_equity": parse_number(pick.get("Debt / Equity Ratio")),
        "fcf_yield":      parse_percent(pick.get("FCF Yield")),
        "fcf_per_share":  parse_number(pick.get("FCF per Share")),
        "period_end":     parse_date(pick.get("_header")),
    }


def parse_forecast_page(html: str) -> dict:
    """Forecast page — analyst estimates for next earnings event."""
    pairs = extract_label_value_pairs(html)
    return {
        "est_revenue":            parse_number(_get(pairs, "Revenue Forecast",
                                                    "Expected Revenue",
                                                    "Forecasted Revenue")),
        "est_revenue_growth_pct": parse_percent(_get(pairs, "Revenue Growth (YoY)",
                                                     "Est. Rev. Growth")),
        "est_eps":                parse_number(_get(pairs, "EPS Forecast",
                                                    "Expected EPS",
                                                    "Forecasted EPS")),
        "next_earnings_date":     parse_date(_get(pairs, "Earnings Date",
                                                  "Next Earnings",
                                                  "Next Earnings Report")),
    }


def parse_ratings_page(html: str) -> dict:
    """Analyst ratings page. Maps to stock_analyst_consensus."""
    pairs = extract_label_value_pairs(html)
    return {
        "rating":             _get(pairs, "Consensus Rating", "Analyst Rating", "Rating"),
        "analyst_count":      parse_int(_get(pairs, "Analyst Count",
                                             "Number of Analysts")),
        "target_price":       parse_number(_get(pairs, "Price Target",
                                                "Average Price Target",
                                                "Consensus Target")),
        "implied_upside_pct": parse_percent(_get(pairs, "Implied Upside", "Upside")),
    }


def parse_history_page(html: str) -> list[dict]:
    """History page — daily OHLC table. Newest-first."""
    soup = make_soup(html)
    rows: list[dict] = []
    for table in soup.find_all("table"):
        thead = table.find("thead")
        if not thead:
            continue
        headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
        if not headers or "Date" not in headers[0]:
            continue
        col_idx = {h: i for i, h in enumerate(headers)}
        tbody = table.find("tbody")
        if not tbody:
            continue
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) < 2:
                continue
            trading_date = parse_date(cells[col_idx.get("Date", 0)])
            if trading_date is None:
                continue
            rows.append({
                "trading_date": trading_date,
                "open_price":   parse_number(_safe_idx(cells, col_idx.get("Open"))),
                "high_price":   parse_number(_safe_idx(cells, col_idx.get("High"))),
                "low_price":    parse_number(_safe_idx(cells, col_idx.get("Low"))),
                "close_price":  parse_number(_safe_idx(cells, col_idx.get("Close"))),
                "volume":       parse_int(_safe_idx(cells, col_idx.get("Volume"))),
                "change_pct":   parse_percent(_safe_idx(cells, col_idx.get("% Change"))),
            })
        break
    return rows


# =============================================================================
# Internal helpers
# =============================================================================
def _safe_idx(cells: list[str], i: Optional[int]) -> Optional[str]:
    if i is None or i < 0 or i >= len(cells):
        return None
    return cells[i]


def _day_range(raw: Optional[str]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """'170.50 - 175.30' -> (175.30, 170.50). Returns (high, low)."""
    if not raw:
        return (None, None)
    parts = re.split(r"\s*[-–]\s*", raw)
    if len(parts) != 2:
        return (None, None)
    lo, hi = parse_number(parts[0]), parse_number(parts[1])
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return (hi, lo)


def _extract_change_pct(html: str) -> Optional[Decimal]:
    """The percent in a header like '+1.23 (+0.45%)'."""
    m = re.search(r"\(([+-]?\d+\.\d+)%\)", html)
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            return None
    return None


def _extract_currency(pairs: dict[str, str], soup: BeautifulSoup) -> Optional[str]:
    raw = _get(pairs, "Currency")
    if raw:
        m = re.match(r"([A-Z]{3})", raw)
        if m:
            return m.group(1)
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Currency is\s+([A-Z]{3})\b", text)
    return m.group(1) if m else None


def _extract_news(soup: BeautifulSoup) -> list[dict]:
    """News headlines from the overview page (h3 → anchor → 'X ago - Source')."""
    items: list[dict] = []
    seen: set[str] = set()
    for h3 in soup.find_all("h3"):
        a = h3.find("a")
        if not a:
            continue
        headline = a.get_text(strip=True)
        url = a.get("href")
        if not headline or not url or headline in seen:
            continue
        seen.add(headline)
        source = None
        sibling = h3.find_next(string=re.compile(r"ago\s*-\s*"))
        if sibling:
            m = re.search(r"-\s*(.+?)$", sibling.strip())
            if m:
                source = m.group(1).strip()
        items.append({"headline": headline, "url": url, "source_code": source})
    return items


def _read_financial_table(html: str) -> dict[str, dict[str, str]]:
    """Parse a multi-column financial table into {column_header: {row_label: cell}}.

    Each inner dict gets a synthetic '_header' key with the column header text,
    useful for callers that want to extract a period_end date.
    """
    soup = make_soup(html)
    out: dict[str, dict[str, str]] = {}
    for table in soup.find_all("table"):
        thead = table.find("thead")
        tbody = table.find("tbody")
        if not thead or not tbody:
            continue
        header_cells = thead.find_all(["th", "td"])
        if len(header_cells) < 3:
            continue
        col_names = [c.get_text(strip=True) for c in header_cells[1:]]
        for name in col_names:
            if name and name not in out:
                out[name] = {"_header": name}
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            row_label = cells[0].get_text(strip=True)
            if not row_label:
                continue
            for i, name in enumerate(col_names):
                if i + 1 >= len(cells):
                    break
                value = cells[i + 1].get_text(strip=True)
                if name and value:
                    out[name][row_label] = value
        if out:
            break
    return out
