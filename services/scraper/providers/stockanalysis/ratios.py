"""Ratios provider — stockanalysis.com /financials/ratios/.

Writes the latest TTM-or-most-recent column into stock_fin_ratios:
    PE, PB, PS, P/FCF, PEG, EV multiples, ROE/ROA/ROIC, current ratio,
    debt/equity, FCF yield, FCF per share, etc.
"""
from __future__ import annotations

from typing import Optional

from ...fetcher import HttpFetcher
from .. import StockContext
from . import PAGE, build_url
from ._common import (
    parse_date, parse_number, parse_percent, pick_latest_column,
    read_financial_table,
)


class StockAnalysisRatiosProvider:
    async def fetch_ratios(self, fetcher: HttpFetcher,
                           stock: StockContext) -> Optional[dict]:
        url = build_url(stock.url_template, stock.ticker, PAGE["ratios"])
        try:
            _s, html = await fetcher.get(url)
        except Exception:
            return None

        col = pick_latest_column(read_financial_table(html))
        return {
            "period_end":     parse_date(col.get("_header")),
            "pe_ratio":       parse_number(col.get("PE Ratio")),
            "pe_forward":     parse_number(col.get("Forward PE")),
            "ps_ratio":       parse_number(col.get("PS Ratio")),
            "pb_ratio":       parse_number(col.get("PB Ratio")),
            "p_fcf_ratio":    parse_number(col.get("P/FCF Ratio")),
            "peg_ratio":      parse_number(col.get("PEG Ratio")),
            "ev_sales":       parse_number(col.get("EV/Sales")),
            "ev_ebitda":      parse_number(col.get("EV/EBITDA")),
            "roe":            parse_percent(col.get("Return on Equity (ROE)")),
            "roa":            parse_percent(col.get("Return on Assets (ROA)")),
            "roic":           parse_percent(col.get("Return on Capital (ROIC)")),
            "current_ratio":  parse_number(col.get("Current Ratio")),
            "debt_to_equity": parse_number(col.get("Debt / Equity Ratio")),
            "fcf_yield":      parse_percent(col.get("FCF Yield")),
            "fcf_per_share":  parse_number(col.get("FCF per Share")),
        }
