"""Technicals provider — stockanalysis.com /statistics/.

Writes:
    technicals  → stock_mkt_technicals (RSI, SMA, 52w, beta, returns, ATH)
    dividends   → stock_mkt_dividends  (yield, payout, growth streaks)
"""
from __future__ import annotations

from typing import Optional

from ...fetcher import HttpFetcher
from .. import StockContext
from . import PAGE, build_url
from ._common import (
    extract_label_value_pairs, get_first, parse_date, parse_day_range,
    parse_int, parse_number, parse_percent,
)


class StockAnalysisTechnicalsProvider:
    async def fetch_technicals(self, fetcher: HttpFetcher,
                               stock: StockContext) -> Optional[dict]:
        url = build_url(stock.url_template, stock.ticker, PAGE["statistics"])
        try:
            _s, html = await fetcher.get(url)
        except Exception:
            return None

        pairs = extract_label_value_pairs(html)
        week_52_high, week_52_low = parse_day_range(get_first(pairs, "52-Week Range"))

        technicals = {
            "rsi_14":   parse_number(get_first(pairs, "RSI (14)", "RSI")),
            "sma_50":   parse_number(get_first(pairs, "50-Day Moving Average", "SMA 50")),
            "sma_200":  parse_number(get_first(pairs, "200-Day Moving Average", "SMA 200")),
            "atr_14":   parse_number(get_first(pairs, "ATR (14)")),
            "volatility_30d": parse_percent(get_first(pairs, "Volatility (30-Day)", "30-Day Volatility")),
            "beta":     parse_number(get_first(pairs, "Beta (5Y)", "Beta")),
            "week_52_high": week_52_high,
            "week_52_low":  week_52_low,
            "week_52_high_change_pct": parse_percent(get_first(pairs, "52-Week Change")),
            "ath_price":      parse_number(get_first(pairs, "All-Time High")),
            "ath_change_pct": parse_percent(get_first(pairs, "Change from ATH")),
            "price_chg_1m_pct": parse_percent(get_first(pairs, "1-Month Return", "Performance (1M)")),
            "price_chg_3m_pct": parse_percent(get_first(pairs, "3-Month Return", "Performance (3M)")),
            "price_chg_6m_pct": parse_percent(get_first(pairs, "6-Month Return", "Performance (6M)")),
            "price_chg_1y_pct": parse_percent(get_first(pairs, "1-Year Return", "Performance (1Y)")),
            "price_chg_3y_pct": parse_percent(get_first(pairs, "3-Year Return", "Performance (3Y)")),
            "price_chg_5y_pct": parse_percent(get_first(pairs, "5-Year Return", "Performance (5Y)")),
            "volume_daily":    parse_int(get_first(pairs, "Volume")),
            "avg_dollar_volume_30d": parse_number(get_first(pairs,
                "Average Volume (30 Days)", "Avg. Volume")),
        }

        dividends = {
            "dividend_yield_pct": parse_percent(get_first(pairs, "Dividend Yield")),
            "dividend_per_share": parse_number(get_first(pairs, "Dividend", "Dividend Per Share")),
            "ex_dividend_date":   parse_date(get_first(pairs, "Ex-Dividend Date")),
            "payout_ratio_pct":   parse_percent(get_first(pairs, "Payout Ratio")),
            "payout_frequency":   get_first(pairs, "Payout Frequency"),
            "div_growth_yoy":     parse_percent(get_first(pairs, "Dividend Growth (YoY)", "Div. Growth")),
            "div_growth_3y":      parse_percent(get_first(pairs, "Dividend Growth (3Y)")),
            "div_growth_5y":      parse_percent(get_first(pairs, "Dividend Growth (5Y)")),
            "growth_years_streak":  parse_int(get_first(pairs, "Years of Growth", "Growth Streak")),
            "payment_years_streak": parse_int(get_first(pairs, "Years of Payments", "Payment Streak")),
        }

        return {"technicals": technicals, "dividends": dividends}
