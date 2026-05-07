"""/admin/* — manual triggers + system status. Requires is_admin."""
from __future__ import annotations

import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from shared.db import (
    PortfolioPosition, ScrapeRun, Stock, StockRecommendation, User,
)
from .auth import get_current_user, get_db
from .schemas import AdminStatusOut, ScrapeRunOut

router = APIRouter(prefix="/admin", tags=["admin"])

_SCRAPER_URL = os.environ.get("SCRAPER_URL", "http://scraper:8001")
_RECOMMENDER_URL = os.environ.get("RECOMMENDER_URL", "http://recommender:8002")


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


@router.get("/status", response_model=AdminStatusOut)
def system_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    stock_count = db.scalar(
        select(func.count()).select_from(Stock).where(Stock.active.is_(True))
    ) or 0
    scored_today = db.scalar(
        select(func.count()).select_from(StockRecommendation)
        .where(StockRecommendation.score_date == date.today())
    ) or 0
    open_positions = db.scalar(
        select(func.count()).select_from(PortfolioPosition)
        .where(PortfolioPosition.is_open.is_(True))
    ) or 0
    last_scrape_at = db.scalar(select(func.max(ScrapeRun.run_time)))

    runs = db.execute(
        select(ScrapeRun, Stock.ticker)
        .outerjoin(Stock, Stock.id == ScrapeRun.stock_id)
        .order_by(desc(ScrapeRun.run_time)).limit(20)
    ).all()
    scrape_runs = [
        ScrapeRunOut(
            id=r[0].id, run_time=r[0].run_time, source=r[0].source,
            status=r[0].status, http_status=r[0].http_status,
            error_message=r[0].error_message, ticker=r[1],
        )
        for r in runs
    ]
    return AdminStatusOut(
        stock_count=stock_count, scored_today=scored_today,
        open_positions=open_positions, last_scrape_at=last_scrape_at,
        scrape_runs=scrape_runs,
    )


@router.post("/scrape-all")
async def trigger_scrape_all(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_SCRAPER_URL}/scrape/all")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.post("/score-all")
async def trigger_score_all(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_RECOMMENDER_URL}/score/all")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.post("/score-portfolio")
async def trigger_score_portfolio(_: User = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_RECOMMENDER_URL}/score/portfolio")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()
