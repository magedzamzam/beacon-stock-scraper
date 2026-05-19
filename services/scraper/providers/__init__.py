"""Provider protocols and registry.

Each "topic" (news, current_quote, financials, technicals, ratios, forecast)
has a Protocol class defining what its provider must implement. Concrete
providers live under providers/<source>/<topic>.py and register themselves
in PROVIDERS below.

To swap a provider:
    1. Implement a new class matching the Protocol for that topic
    2. Register it in _SOURCES (or set TOPIC_PROVIDER env var to its key)
    3. Restart — no DB code changes, no scheduler changes

Topic → provider source per-deployment, read from env:
    NEWS_PROVIDER=stockanalysis (default)
    FINANCIALS_PROVIDER=stockanalysis
    ...etc.

If a topic has no env override, the default ("stockanalysis") is used.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

from ..fetcher import HttpFetcher


class StockContext:
    """Identifiers a provider needs to build URLs / API calls."""
    __slots__ = ("stock_id", "ticker", "exchange_code", "url_template")

    def __init__(self, stock_id: int, ticker: str, exchange_code: str,
                 url_template: str):
        self.stock_id = stock_id
        self.ticker = ticker
        self.exchange_code = exchange_code
        self.url_template = url_template


# ---------------------------------------------------------------------------
# Per-topic Protocols. Each fetch_* returns a plain dict for the writer,
# OR None for "couldn't fetch / page missing". Empty dict means "fetched
# fine but every field came back null" — different signal.
# ---------------------------------------------------------------------------
@runtime_checkable
class NewsProvider(Protocol):
    async def fetch_news(self, fetcher: HttpFetcher,
                         stock: StockContext) -> Optional[list[dict]]: ...


@runtime_checkable
class CurrentQuoteProvider(Protocol):
    async def fetch_current_quote(self, fetcher: HttpFetcher,
                                  stock: StockContext) -> Optional[dict]: ...


@runtime_checkable
class FinancialsProvider(Protocol):
    """Returns {fin_statement, fin_cashflow}."""
    async def fetch_financials(self, fetcher: HttpFetcher,
                               stock: StockContext) -> Optional[dict]: ...


@runtime_checkable
class TechnicalsProvider(Protocol):
    """Returns {technicals, dividends}."""
    async def fetch_technicals(self, fetcher: HttpFetcher,
                               stock: StockContext) -> Optional[dict]: ...


@runtime_checkable
class RatiosProvider(Protocol):
    async def fetch_ratios(self, fetcher: HttpFetcher,
                           stock: StockContext) -> Optional[dict]: ...


@runtime_checkable
class ForecastProvider(Protocol):
    """Returns {analyst_consensus, earnings_estimates}."""
    async def fetch_forecast(self, fetcher: HttpFetcher,
                             stock: StockContext) -> Optional[dict]: ...


# ---------------------------------------------------------------------------
# Registry (lazy-imported per source so one broken provider doesn't break
# the others)
# ---------------------------------------------------------------------------
def _load_stockanalysis_providers() -> dict:
    from .stockanalysis import (
        news, current_quote, financials, technicals, ratios, forecast,
    )
    return {
        "news":          news.StockAnalysisNewsProvider(),
        "current_quote": current_quote.StockAnalysisCurrentQuoteProvider(),
        "financials":    financials.StockAnalysisFinancialsProvider(),
        "technicals":    technicals.StockAnalysisTechnicalsProvider(),
        "ratios":        ratios.StockAnalysisRatiosProvider(),
        "forecast":      forecast.StockAnalysisForecastProvider(),
    }


_SOURCES = {
    "stockanalysis": _load_stockanalysis_providers,
}

_cache: dict[str, object] = {}


def get_provider(topic: str):
    if topic in _cache:
        return _cache[topic]
    env_key = f"{topic.upper()}_PROVIDER"
    source = os.environ.get(env_key, "stockanalysis").lower()
    loader = _SOURCES.get(source)
    if loader is None:
        raise RuntimeError(
            f"Unknown {env_key}={source!r}. Available: {list(_SOURCES)}"
        )
    providers = loader()
    if topic not in providers:
        raise RuntimeError(
            f"Source {source!r} does not implement topic {topic!r}. "
            f"Available topics: {list(providers)}"
        )
    _cache[topic] = providers[topic]
    return _cache[topic]
