"""Recommender microservice."""
from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI

from shared.logging_setup import configure_logging
from .pipeline import score_all, score_portfolio

log = configure_logging("recommender-api")
app = FastAPI(title="Beacon Recommender", version="1.0.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/score/all")
def trigger_score_all(background: BackgroundTasks):
    background.add_task(score_all)
    return {"queued": True}


@app.post("/score/portfolio")
def trigger_score_portfolio(background: BackgroundTasks):
    background.add_task(score_portfolio)
    return {"queued": True}


@app.post("/score/all/sync")
def score_all_sync():
    """Synchronous variant — returns counts. Used by the scheduler."""
    return score_all()


@app.post("/score/portfolio/sync")
def score_portfolio_sync():
    return score_portfolio()
