"""Scraper microservice HTTP API.

Endpoints:
    GET  /healthz
    POST /scrape/all                      kick off a batch scrape
                                          body: {"mode": "daily"|"weekly",
                                                 "exchanges": ["adx",...]}
    POST /scrape/{exchange}/{ticker}      re-scrape one stock on demand
                                          query: ?mode=daily|weekly (default daily)

The scheduler calls /scrape/all with mode='daily' on the daily tick and
mode='weekly' on the weekly tick. 'full' is also accepted as a synonym for
'weekly' for backward-compat with the old API.
"""
from __future__ import annotations

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from shared.logging_setup import configure_logging
from .pipeline import scrape_all_active, scrape_by_ticker

log = configure_logging("scraper-api")
app = FastAPI(title="Beacon Scraper", version="2.0.0")

_VALID_MODES = {"daily", "weekly", "full"}


class ScrapeAllRequest(BaseModel):
    mode: str = "daily"
    exchanges: Optional[list[str]] = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/scrape/all")
async def scrape_all(background: BackgroundTasks,
                     req: Optional[ScrapeAllRequest] = None):
    """Kick off a scrape in the background and return immediately."""
    if req is None:
        req = ScrapeAllRequest()
    if req.mode not in _VALID_MODES:
        raise HTTPException(400, f"mode must be one of {_VALID_MODES}")
    background.add_task(scrape_all_active, mode=req.mode, exchanges=req.exchanges)
    return {
        "queued": True, "mode": req.mode,
        "exchanges": req.exchanges or "all",
    }


@app.post("/scrape/{exchange}/{ticker}")
async def scrape_single(exchange: str, ticker: str, mode: str = "daily"):
    if mode not in _VALID_MODES:
        raise HTTPException(400, f"mode must be one of {_VALID_MODES}")
    return await scrape_by_ticker(exchange, ticker, mode=mode)
