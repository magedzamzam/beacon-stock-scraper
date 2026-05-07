"""Parser for stockanalysis.com quote pages.

Three pages per stock:
    /quote/{exchange}/{ticker}/             -> overview (price, market cap, key ratios)
    /quote/{exchange}/{ticker}/statistics/   -> deep statistics (margins, scores, etc.)
    /quote/{exchange}/{ticker}/financials/   -> annual income/balance/cash-flow

The HTML uses simple two-column tables ('label | value'). We parse robustly so
new rows simply add to the dict — anything we don't know about is ignored.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Number / unit parsing
# ---------------------------------------------------------------------------
_SUFFIX_MULTIPLIER = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_number(raw: Optional[str]) -> Optional[Decimal]:
    """Parse strings like '871.14B', '+9.40 (2.41%)', '45.01', 'n/a', '171,124'."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"n/a", "na", "-", "—", "upgrade"}:
        return None

    # Take only the leading number+unit token (drop trailing parens, %, etc.)
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
    """Strip a trailing % and parse."""
    if raw is None:
        return None
    return parse_number(str(raw).replace("%", ""))


def parse_date(raw: Optional[str]) -> Optional[date]:
    """Parse 'Feb 23, 2026' / '2026-02-23' / 'Mar 9, 2026'."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"n/a", "na", "-", "—"}:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# HTML table extraction
# ---------------------------------------------------------------------------
def extract_label_value_pairs(html: str) -> dict[str, str]:
    """Walk every two-column table in the page and return {label: value}.

    stockanalysis.com renders all key data this way, so this single helper
    captures statistics, valuation, share-stats, margins, etc. in one pass.
    """
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, str] = {}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) == 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if label and value and label not in out:
                    out[label] = value
    return out


def extract_company_blurb(html: str) -> dict[str, Optional[str]]:
    """Pulls company name, sector/industry from the overview header."""
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, Optional[str]] = {
        "company_name": None,
        "industry": None,
        "country": None,
        "founded_year": None,
        "ticker": None,
    }

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        # "International Holding Company PJSC (ADX:IHC)"
        m = re.match(r"^(.+?)\s*\(([A-Z]+):([A-Z0-9]+)\)\s*$", text)
        if m:
            out["company_name"] = m.group(1).strip()
            out["ticker"] = m.group(3).strip()
        else:
            out["company_name"] = text

    # Look for plain-text "Industry Conglomerates", "Founded 1998", "Country UAE"
    body_text = soup.get_text("\n", strip=True)
    for key in ("Industry", "Founded", "Country", "Ticker Symbol"):
        m = re.search(rf"^{key}\s+(.+)$", body_text, flags=re.MULTILINE)
        if m:
            value = m.group(1).strip()
            if key == "Industry":
                out["industry"] = value
            elif key == "Founded":
                try:
                    out["founded_year"] = int(re.match(r"\d{4}", value).group(0))
                except (AttributeError, ValueError):
                    pass
            elif key == "Country":
                out["country"] = value
            elif key == "Ticker Symbol" and not out["ticker"]:
                out["ticker"] = value

    return out


def extract_news(html: str) -> list[dict]:
    """News headlines on the overview page (h3 -> nearest 'X ago - Source')."""
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []
    for h3 in soup.find_all("h3"):
        a = h3.find("a")
        if not a:
            continue
        url = a.get("href")
        headline = a.get_text(strip=True)
        if not headline or not url:
            continue
        # Find the nearest sibling text describing "<n> ago - Source"
        sibling = h3.find_next(string=re.compile(r"ago\s*-\s*"))
        source = None
        news_date = None
        if sibling:
            m = re.search(r"-\s*(.+?)$", sibling.strip())
            if m:
                source = m.group(1).strip()
        items.append({
            "headline": headline,
            "url": url,
            "source_code": source,
            "news_date": news_date,
        })
    return items


# ---------------------------------------------------------------------------
# Field mapping → DB columns
# ---------------------------------------------------------------------------
def build_market_daily(pairs: dict[str, str]) -> dict:
    """Map labels from the overview / statistics pages to stock_market_daily."""
    return {
        "market_cap": parse_number(pairs.get("Market Cap")),
        "revenue_ttm": parse_number(pairs.get("Revenue (ttm)")),
        "pe_ratio": parse_number(pairs.get("PE Ratio")),
        "forward_pe": parse_number(pairs.get("Forward PE")),
        "dividend": parse_number(pairs.get("Dividend")),
        "beta": parse_number(pairs.get("Beta")) or parse_number(pairs.get("Beta (5Y)")),
        "open_price": parse_number(pairs.get("Open")),
        "volume": int(parse_number(pairs.get("Volume")) or 0) or None,
        "enterprise_value": parse_number(pairs.get("Enterprise Value")),
        "week_52_high": _range_high(pairs.get("52-Week Range")),
        "week_52_low": _range_low(pairs.get("52-Week Range")),
        "dividend_yield_pct": parse_percent(pairs.get("Dividend Yield")),
    }


def build_valuation(pairs: dict[str, str]) -> dict:
    return {
        "pe": parse_number(pairs.get("PE Ratio")),
        "ev_sales": parse_number(pairs.get("EV / Sales")),
        "ev_ebitda": parse_number(pairs.get("EV / EBITDA")),
        "price_to_book": parse_number(pairs.get("PB Ratio")),
        "dividend_yield_pct": parse_percent(pairs.get("Dividend Yield")),
    }


def build_financials_ttm(pairs: dict[str, str]) -> dict:
    """The statistics page's Income Statement / Balance / Cash Flow sections
    give us the latest TTM figures — store as fiscal_year=current with period_type='TTM'."""
    return {
        "revenue": parse_number(pairs.get("Revenue")),
        "net_income": parse_number(pairs.get("Net Income")),
        "ebitda": parse_number(pairs.get("EBITDA")),
        "operating_income": parse_number(pairs.get("Operating Income")),
        "total_equity": parse_number(pairs.get("Equity (Book Value)")),
        "total_debt": parse_number(pairs.get("Total Debt")),
        "cash_and_equivalents": parse_number(pairs.get("Cash & Cash Equivalents")),
        "operating_cash_flow": parse_number(pairs.get("Operating Cash Flow")),
        "free_cash_flow": parse_number(pairs.get("Free Cash Flow")),
    }


def build_technicals(pairs: dict[str, str]) -> dict:
    return {
        "rsi_14": parse_number(pairs.get("Relative Strength Index (RSI)")) or parse_number(pairs.get("RSI")),
        "sma_50": parse_number(pairs.get("50-Day Moving Average")),
        "sma_200": parse_number(pairs.get("200-Day Moving Average")),
    }


def extract_close_price(pairs: dict[str, str], html: str) -> Optional[Decimal]:
    """Best-effort current price. The big number sits at the top of the page."""
    soup = BeautifulSoup(html, "lxml")
    # Header price is the first standalone numeric on the page after h1.
    h1 = soup.find("h1")
    if h1:
        for sib in h1.find_all_next(string=True, limit=20):
            cleaned = sib.strip()
            if not cleaned:
                continue
            v = parse_number(cleaned)
            if v is not None and v > 0:
                return v
    return parse_number(pairs.get("Previous Close"))


# ---------- helpers ----------
def _range_high(raw: Optional[str]) -> Optional[Decimal]:
    if not raw:
        return None
    parts = raw.split("-")
    return parse_number(parts[1]) if len(parts) == 2 else None


def _range_low(raw: Optional[str]) -> Optional[Decimal]:
    if not raw:
        return None
    parts = raw.split("-")
    return parse_number(parts[0]) if len(parts) == 2 else None
