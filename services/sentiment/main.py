"""Sentiment microservice — scores pending stock_news rows with FinBERT.

Endpoints
---------
GET  /healthz                Liveness probe.
POST /sentiment/score-pending  Score every news row where sentiment_label IS NULL,
                              up to a configurable per-call cap. Returns counts.
POST /sentiment/score/{news_id}  Re-score a single row (useful for testing).
POST /sentiment/test          Score raw text without touching the database.

The scheduler hits /sentiment/score-pending after each daily scrape so new
headlines are labelled before the recommender runs.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from shared.db import SessionLocal, StockNews
from shared.logging_setup import configure_logging

from .scorer import score_batch, score_text


log = configure_logging("sentiment-api")
app = FastAPI(title="Beacon Sentiment", version="1.0.0")

_DEFAULT_LIMIT = int(os.environ.get("SENTIMENT_DEFAULT_LIMIT", "200"))


class SentimentTestIn(BaseModel):
    text: str


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/sentiment/test")
def test(payload: SentimentTestIn):
    """Score one piece of text without touching the DB. Lazy-loads the model."""
    label, score = score_text(payload.text)
    return {"label": label, "score": score}


@app.post("/sentiment/score-pending")
def score_pending(limit: int | None = None):
    """Score the oldest news rows missing a sentiment label.

    Returns a dict with counts per label and the number of rows updated. Idempotent
    in the sense that re-running it on a fresh database is a no-op.
    """
    cap = limit if limit and limit > 0 else _DEFAULT_LIMIT

    with SessionLocal() as session:
        rows = session.execute(
            select(StockNews.id, StockNews.headline)
            .where(StockNews.sentiment_label.is_(None))
            .order_by(StockNews.scraped_at)
            .limit(cap)
        ).all()

    if not rows:
        return {"scored": 0, "labels": {}, "skipped_empty": 0}

    ids = [r.id for r in rows]
    headlines = [r.headline or "" for r in rows]

    log.info("sentiment_batch_start", count=len(ids))
    results = score_batch(headlines)

    labels: dict[str, int] = {}
    skipped_empty = 0
    now = datetime.utcnow()

    with SessionLocal() as session:
        for nid, headline, (label, score) in zip(ids, headlines, results):
            if not headline.strip():
                skipped_empty += 1
                continue
            session.execute(
                update(StockNews)
                .where(StockNews.id == nid)
                .values(
                    sentiment_label=label,
                    sentiment_score=Decimal(str(score)),
                    # don't bash scraped_at — it's the original ingestion time
                )
            )
            labels[label] = labels.get(label, 0) + 1
        session.commit()

    log.info("sentiment_batch_done", scored=len(ids) - skipped_empty, **labels)
    return {
        "scored": len(ids) - skipped_empty,
        "skipped_empty": skipped_empty,
        "labels": labels,
        "ts": now.isoformat(),
    }


@app.post("/sentiment/score/{news_id}")
def score_one_row(news_id: int):
    """Re-score a single news row by ID. Overwrites any existing sentiment."""
    with SessionLocal() as session:
        row = session.get(StockNews, news_id)
        if row is None:
            raise HTTPException(404, "News row not found")
        if not (row.headline and row.headline.strip()):
            raise HTTPException(400, "Empty headline")
        label, score = score_text(row.headline)
        row.sentiment_label = label
        row.sentiment_score = Decimal(str(score))
        session.commit()
        return {"id": news_id, "label": label, "score": score, "headline": row.headline}
