"""Async HTTP client with retry, throttling, and clean User-Agent.

Why we throttle: stockanalysis.com is a free site. Hammering it gets us
blocked and is rude. We add a small per-request delay and concurrency cap.
"""
from __future__ import annotations

import asyncio
import httpx
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt, wait_exponential,
)

from shared.settings import get_settings

_settings = get_settings()


class HttpFetcher:
    def __init__(self, concurrency: int | None = None, delay_sec: float | None = None):
        self._sem = asyncio.Semaphore(concurrency or _settings.scraper_concurrency)
        self._delay = delay_sec if delay_sec is not None else _settings.scraper_request_delay_sec
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=_settings.scraper_timeout_sec,
            headers={
                "User-Agent": _settings.scraper_user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def get(self, url: str) -> tuple[int, str]:
        assert self._client is not None, "use as async-context-manager"
        async with self._sem:
            await asyncio.sleep(self._delay)
            response = await self._client.get(url)
            response.raise_for_status()
            return response.status_code, response.text
