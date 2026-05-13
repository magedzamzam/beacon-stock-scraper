"""Scraper microservice — exposes a small HTTP API.

Endpoints:
    GET  /healthz
    POST /scrape/all                  -> kicks off a scrape (background task)
                                         body: {"mode": "daily"|"full",
                                                "exchanges": ["adx",...]}
    POST /scrape/{exchange}/{ticker}  -> on-demand re-scrape one stock

The scheduler now calls /scrape/all with different mode + exchange filters
for the daily-quotes job vs. the monthly-fundamentals job.
"""
from __future__ import annotations

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from shared.logging_setup import configure_logging
from .pipeline import scrape_all_active, scrape_by_ticker

log = configure_logging("scraper-api")
app = FastAPI(title="Beacon Scraper", version="1.0.0")


class ScrapeAllRequest(BaseModel):
    mode: str = "full"                          # "daily" or "full"
    exchanges: Optional[list[str]] = None       # None/[] means all


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/scrape/all")
async def scrape_all(background: BackgroundTasks, req: Optional[ScrapeAllRequest] = None):
    """Kick off a scrape in the background and return immediately.

    Without a body: full scrape, all exchanges (legacy behaviour).
    With a body: caller picks mode + exchange filter.
    """
    if req is None:
        req = ScrapeAllRequest()
    if req.mode not in ("daily", "full"):
        raise HTTPException(400, "mode must be 'daily' or 'full'")
    background.add_task(scrape_all_active, mode=req.mode, exchanges=req.exchanges)
    return {
        "queued": True, "mode": req.mode,
        "exchanges": req.exchanges or "all",
        "message": f"{req.mode.capitalize()} scrape started in background.",
    }


@app.post("/scrape/{exchange}/{ticker}")
async def scrape_single(exchange: str, ticker: str):
    if exchange.lower() not in {"adx", "dfm", "egx, nasdaq, nyse"}:
        raise HTTPException(400, "exchange must be one of: adx, dfm, egx, nasdaq, nyse")
    return await scrape_by_ticker(exchange, ticker)
