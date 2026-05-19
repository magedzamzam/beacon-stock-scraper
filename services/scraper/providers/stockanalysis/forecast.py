"""Forecast/analyst provider — stockanalysis.com /forecast/ + /ratings/.

Writes:
    analyst_consensus    → stock_analyst_consensus (rating, count, target, upside)
    earnings_estimates   → stock_earnings_calendar (est_revenue, est_eps,
                            next_earnings_date — only the FORECAST portion;
                            last_earnings_date / earnings_time come from the
                            bulk CSV import or manual upload, as agreed).
"""
from __future__ import annotations

from typing import Optional

from ...fetcher import HttpFetcher
from .. import StockContext
from . import PAGE, build_url
from ._common import (
    extract_label_value_pairs, get_first, parse_date, parse_int,
    parse_number, parse_percent,
)


class StockAnalysisForecastProvider:
    async def fetch_forecast(self, fetcher: HttpFetcher,
                             stock: StockContext) -> Optional[dict]:
        html_forecast = await _safe_fetch(fetcher,
            build_url(stock.url_template, stock.ticker, PAGE["forecast"]))
        html_ratings = await _safe_fetch(fetcher,
            build_url(stock.url_template, stock.ticker, PAGE["ratings"]))

        if html_forecast is None and html_ratings is None:
            return None

        forecast_pairs = extract_label_value_pairs(html_forecast) if html_forecast else {}
        rating_pairs   = extract_label_value_pairs(html_ratings)  if html_ratings  else {}

        earnings_estimates = {
            "est_revenue":            parse_number(get_first(forecast_pairs,
                "Revenue Forecast", "Expected Revenue", "Forecasted Revenue")),
            "est_revenue_growth_pct": parse_percent(get_first(forecast_pairs,
                "Revenue Growth (YoY)", "Est. Rev. Growth")),
            "est_eps":                parse_number(get_first(forecast_pairs,
                "EPS Forecast", "Expected EPS", "Forecasted EPS")),
            "next_earnings_date":     parse_date(get_first(forecast_pairs,
                "Earnings Date", "Next Earnings", "Next Earnings Report")),
        }

        analyst_consensus = {
            "rating":             get_first(rating_pairs,
                "Consensus Rating", "Analyst Rating", "Rating"),
            "analyst_count":      parse_int(get_first(rating_pairs,
                "Analyst Count", "Number of Analysts")),
            "target_price":       parse_number(get_first(rating_pairs,
                "Price Target", "Average Price Target", "Consensus Target")),
            "implied_upside_pct": parse_percent(get_first(rating_pairs,
                "Implied Upside", "Upside")),
        }

        return {
            "earnings_estimates": earnings_estimates,
            "analyst_consensus":  analyst_consensus,
        }


async def _safe_fetch(fetcher: HttpFetcher, url: str) -> Optional[str]:
    try:
        _s, html = await fetcher.get(url)
        return html
    except Exception:
        return None
