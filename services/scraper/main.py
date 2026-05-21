"""Scraper microservice HTTP API.

One endpoint per topic — called by the scheduler on cron, or by an admin
manually. Background-task pattern so the caller doesn't block on the
batch run.

Endpoints:
    GET  /healthz
    POST /scrape/news        body: {"exchanges": ["adx",...]}  (optional)
    POST /scrape/current_quote
    POST /scrape/financials
    POST /scrape/technicals
    POST /scrape/ratios
    POST /scrape/forecast
    POST /scrape/one/{topic}/{exchange}/{ticker}    on-demand single stock
"""
from __future__ import annotations

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from shared.logging_setup import configure_logging
from .pipelines import (
    run_current_quote, run_financials, run_forecast, run_news,
    run_one_topic, run_ratios, run_technicals,
)

log = configure_logging("scraper-api")
app = FastAPI(title="Beacon Scraper", version="3.0.0")


class ScrapeRequest(BaseModel):
    exchanges: Optional[list[str]] = None


# Topic → batch entry point
_TOPICS = {
    "news":          run_news,
    "current_quote": run_current_quote,
    "financials":    run_financials,
    "technicals":    run_technicals,
    "ratios":        run_ratios,
    "forecast":      run_forecast,
}


@app.get("/healthz")
def healthz():
    return {"ok": True, "topics": list(_TOPICS.keys())}


@app.post("/scrape/{topic}")
async def scrape_topic(topic: str, background: BackgroundTasks,
                       req: Optional[ScrapeRequest] = None):
    """Kick off a batch scrape for one topic in the background."""
    if topic not in _TOPICS:
        raise HTTPException(404, f"unknown topic '{topic}'. "
                                  f"Valid: {list(_TOPICS)}")
    fn = _TOPICS[topic]
    exchanges = req.exchanges if req else None
    background.add_task(fn, exchanges=exchanges)
    return {"queued": True, "topic": topic, "exchanges": exchanges or "all"}


@app.post("/scrape/one/{topic}/{exchange}/{ticker}")
async def scrape_one(topic: str, exchange: str, ticker: str):
    """Synchronous single-stock scrape. Useful for manual debugging."""
    if topic not in _TOPICS:
        raise HTTPException(404, f"unknown topic '{topic}'. "
                                  f"Valid: {list(_TOPICS)}")
    return await run_one_topic(topic, exchange, ticker)