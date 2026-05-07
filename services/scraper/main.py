"""Scraper microservice — exposes a small HTTP API.

Endpoints:
    GET  /healthz
    POST /scrape/all                  -> kicks off a full daily scrape (background task)
    POST /scrape/{exchange}/{ticker}  -> on-demand re-scrape one stock

The scheduler service calls /scrape/all once a day. The frontend can call
/scrape/{exchange}/{ticker} on-demand to refresh a single stock.
"""
from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException

from shared.logging_setup import configure_logging
from .pipeline import scrape_all_active, scrape_by_ticker

log = configure_logging("scraper-api")
app = FastAPI(title="Beacon Scraper", version="1.0.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/scrape/all")
async def scrape_all(background: BackgroundTasks):
    """Kick off the full scrape in the background and return immediately."""
    background.add_task(scrape_all_active)
    return {"queued": True, "message": "Full scrape started in background."}


@app.post("/scrape/{exchange}/{ticker}")
async def scrape_single(exchange: str, ticker: str):
    if exchange.lower() not in {"adx", "dfm", "egx"}:
        raise HTTPException(400, "exchange must be one of: adx, dfm, egx")
    return await scrape_by_ticker(exchange, ticker)
