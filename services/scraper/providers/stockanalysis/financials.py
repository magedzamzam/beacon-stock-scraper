"""Financials provider — stockanalysis.com /financials/, /balance-sheet/,
/cash-flow-statement/.

Writes the latest TTM-or-most-recent-fiscal-year column into:
    fin_statement  → stock_fin_statement (revenue, EPS, growth, shares, debt)
    fin_cashflow   → stock_fin_cashflow (OCF, FCF, capex, SBC)
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


class StockAnalysisFinancialsProvider:
    async def fetch_financials(self, fetcher: HttpFetcher,
                               stock: StockContext) -> Optional[dict]:
        # Three pages. We only fail the whole topic if /financials/ is
        # unreachable; balance sheet & cashflow are optional enrichers.
        html_income = await _safe_fetch(fetcher,
            build_url(stock.url_template, stock.ticker, PAGE["financials"]))
        if html_income is None:
            return None
        html_balance = await _safe_fetch(fetcher,
            build_url(stock.url_template, stock.ticker, PAGE["balance_sheet"]))
        html_cashflow = await _safe_fetch(fetcher,
            build_url(stock.url_template, stock.ticker, PAGE["cashflow"]))

        income = pick_latest_column(read_financial_table(html_income))
        balance = (pick_latest_column(read_financial_table(html_balance))
                   if html_balance else {})
        cashflow_cols = (pick_latest_column(read_financial_table(html_cashflow))
                         if html_cashflow else {})

        # Period end — prefer income statement's column header, fall back to
        # balance sheet. None means writer will fall back to today (the writer
        # uses the date as part of the conflict key for fin_* tables).
        period_end = (parse_date(income.get("_header"))
                      or parse_date(balance.get("_header")))

        fin_statement = {
            "period_end": period_end,
            "revenue":                     parse_number(income.get("Revenue")),
            "gross_profit":                parse_number(income.get("Gross Profit")),
            "operating_income":            parse_number(income.get("Operating Income")),
            "net_income":                  parse_number(income.get("Net Income")),
            "ebitda":                      parse_number(income.get("EBITDA")),
            "income_tax":                  parse_number(income.get("Income Tax",
                                                                   income.get("Tax Provision"))),
            "eps_diluted":                 parse_number(income.get("EPS (Diluted)",
                                                                   income.get("EPS"))),
            "revenue_growth_yoy":          parse_percent(income.get("Revenue Growth (YoY)")),
            "net_income_growth_yoy":       parse_percent(income.get("Net Income Growth (YoY)")),
            "operating_income_growth_yoy": parse_percent(income.get("Operating Income Growth")),
            "eps_growth_yoy":              parse_percent(income.get("EPS Growth (YoY)")),
            # From balance sheet
            "shares_outstanding": parse_number(balance.get("Shares Outstanding",
                                                           balance.get("Common Stock Shares Outstanding"))),
            "total_debt":         parse_number(balance.get("Total Debt")),
            "net_cash":           _compute_net_cash(balance),
        }

        fin_cashflow = {
            "period_end": parse_date(cashflow_cols.get("_header")) or period_end,
            "operating_cash_flow": parse_number(cashflow_cols.get("Operating Cash Flow")),
            "investing_cash_flow": parse_number(cashflow_cols.get("Investing Cash Flow")),
            "financing_cash_flow": parse_number(cashflow_cols.get("Financing Cash Flow")),
            "net_cash_flow":       parse_number(cashflow_cols.get("Net Cash Flow")),
            "cap_ex":              parse_number(cashflow_cols.get("Capital Expenditures",
                                                                  cashflow_cols.get("CapEx"))),
            "free_cash_flow":      parse_number(cashflow_cols.get("Free Cash Flow")),
            "sbc":                 parse_number(cashflow_cols.get("Stock-Based Compensation")),
            "net_borrowing":       parse_number(cashflow_cols.get("Net Debt Issued/Repaid",
                                                                  cashflow_cols.get("Net Borrowing"))),
        }

        return {"fin_statement": fin_statement, "fin_cashflow": fin_cashflow}


def _compute_net_cash(balance: dict) -> Optional[object]:
    cash = parse_number(balance.get("Cash & Equivalents",
                                    balance.get("Cash And Short Term Investments")))
    debt = parse_number(balance.get("Total Debt"))
    if cash is None or debt is None:
        return None
    return cash - debt


async def _safe_fetch(fetcher: HttpFetcher, url: str) -> Optional[str]:
    try:
        _s, html = await fetcher.get(url)
        return html
    except Exception:
        return None
