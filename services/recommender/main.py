"""Recommender microservice."""
from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException
from sqlalchemy import select

from shared.db import Exchange, SessionLocal, Stock
from shared.logging_setup import configure_logging
from .pipeline import score_all, score_one, score_portfolio

log = configure_logging("recommender-api")
app = FastAPI(title="Beacon Recommender", version="1.1.0")


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


@app.post("/score/single/{exchange}/{ticker}")
def score_single(exchange: str, ticker: str):
    """Re-score one stock immediately. Used after admin overrides."""
    with SessionLocal() as session:
        row = session.execute(
            select(Stock.id)
            .join(Exchange, Stock.exchange_id == Exchange.id)
            .where(Exchange.code == exchange.lower(), Stock.ticker == ticker.upper())
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Stock not found")
    return score_one(row)
