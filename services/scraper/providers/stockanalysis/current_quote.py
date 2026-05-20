"""Current quote provider — stockanalysis.com overview page.

We parse the price block exactly as it appears on the page header:

    Commercial International Bank Egypt (CIB) S.A.E. (EGX:COMI)
    Egypt · Delayed Price · Currency is EGP
    131.51   -1.49 (-1.12%)
    At close: May 18, 2026

The numbers go into stock_quotes (the canonical one-row-per-stock cache)
AND into stock_history_quote's row for that trading date.

Rules:
  - 'At close: <date>' is parsed and used as `trading_date` for the
    history row. If the date is missing, today is used as a fallback
    but only as a last resort.
  - 'Currency is XXX' is captured for stocks.currency / stock_quotes.currency.
  - The page is flagged 'Delayed Price' — that's expected on free pages.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from ...fetcher import HttpFetcher
from .. import StockContext
from . import PAGE, build_url
from ._common import make_soup, parse_date, parse_number


class StockAnalysisCurrentQuoteProvider:
    """Parse the price header block on the overview page."""

    async def fetch_current_quote(self, fetcher: HttpFetcher,
                                  stock: StockContext) -> Optional[dict]:
        url = build_url(stock.url_template, stock.ticker, PAGE["overview"])
        try:
            _status, html = await fetcher.get(url)
        except Exception:
            return None

        soup = make_soup(html)
        # Take the page text once — the price block is rendered as plain
        # text and reading it from a single string is more robust than
        # guessing CSS class names that change.
        full_text = soup.get_text("\n", strip=True)

        currency = _extract_currency(full_text)
        price, change_abs, change_pct = _extract_price_block(full_text)
        as_of = _extract_as_of_date(full_text)

        return {
            "current_price":   price,
            "change_abs":      change_abs,
            "change_pct":      change_pct,
            "currency":        currency,
            "trading_date":    as_of,   # used for stock_history_quote row
        }


# ---------------------------------------------------------------------------
# Page-specific text extractors. Kept private to this module so the regexes
# don't leak as "shared" parsing logic.
# ---------------------------------------------------------------------------
_PRICE_LINE = re.compile(
    # 131.51   -1.49 (-1.12%)
    # Catches numbers with optional thousands commas; price > 0 by assumption.
    r"(?P<price>\d[\d,]*\.\d+)\s+"
    r"(?P<abs>[+-]?\d[\d,]*\.\d+)\s+"
    r"\((?P<pct>[+-]?\d+\.\d+)%\)"
)

_AS_OF = re.compile(r"At close:\s*([A-Za-z]+\s+\d+,\s*\d{4})")
_CURRENCY = re.compile(r"Currency is\s+([A-Z]{3})\b")


def _extract_price_block(text: str) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Return (price, change_abs, change_pct) from the header line."""
    m = _PRICE_LINE.search(text)
    if not m:
        return (None, None, None)
    try:
        price = Decimal(m.group("price").replace(",", ""))
        change_abs = Decimal(m.group("abs").replace(",", ""))
        change_pct = Decimal(m.group("pct"))
    except InvalidOperation:
        return (None, None, None)
    return (price, change_abs, change_pct)


def _extract_as_of_date(text: str) -> Optional[date]:
    m = _AS_OF.search(text)
    return parse_date(m.group(1)) if m else None


def _extract_currency(text: str) -> Optional[str]:
    m = _CURRENCY.search(text)
    return m.group(1) if m else None
