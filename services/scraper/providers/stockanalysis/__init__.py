"""stockanalysis.com providers — URL builder + sub-page paths.

Centralised so a future site path change is a single-line fix.
"""
from __future__ import annotations

from shared.settings import get_settings

_settings = get_settings()

PAGE = {
    "overview":      "",
    "statistics":    "statistics",
    "financials":    "financials",
    "balance_sheet": "financials/balance-sheet",
    "cashflow":      "financials/cash-flow-statement",
    "ratios":        "financials/ratios",
    "forecast":      "forecast",
    "ratings":       "ratings",
}


def build_url(url_template: str, ticker: str, sub: str = "") -> str:
    base = _settings.scraper_base_url + url_template.format(ticker=ticker.lower())
    if not base.endswith("/"):
        base += "/"
    return base + (sub.rstrip("/") + "/" if sub else "")
