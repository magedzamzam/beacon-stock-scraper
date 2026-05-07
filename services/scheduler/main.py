"""Beacon scheduler.

Triggers — once daily at 11:00 (timezone configurable, default Asia/Dubai):
    1) call scraper:  POST http://scraper:8001/scrape/all
       (returns immediately; scraper does the work in the background)
    2) wait until scraper finishes
    3) call recommender: POST http://recommender:8002/score/all/sync
    4) call recommender: POST http://recommender:8002/score/portfolio/sync

We deliberately use the SYNC endpoints for steps 3-4 so we get a deterministic
order: data first, scoring second.

The scrape itself is async-in-background, so we must poll the scraper's
audit table to know when it's done. We read scrape_runs.run_time and wait
until no new rows have been written for ~120 seconds.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select

from shared.db import SessionLocal, ScrapeRun
from shared.logging_setup import configure_logging
from shared.settings import get_settings

log = configure_logging("scheduler")
settings = get_settings()

SCRAPER_URL = "http://scraper:8001"
RECOMMENDER_URL = "http://recommender:8002"


async def wait_for_scraper_idle(idle_seconds: int = 120, max_minutes: int = 60):
    """Block until scrape_runs has had no new rows for `idle_seconds`."""
    deadline = time.time() + max_minutes * 60
    last_seen: datetime | None = None
    last_change = time.time()
    while time.time() < deadline:
        with SessionLocal() as s:
            latest = s.execute(select(func.max(ScrapeRun.run_time))).scalar()
        if latest != last_seen:
            last_seen = latest
            last_change = time.time()
        if time.time() - last_change >= idle_seconds:
            log.info("scraper_idle_detected", since=last_seen.isoformat() if last_seen else None)
            return
        await asyncio.sleep(15)
    log.warning("scraper_idle_timeout")


async def daily_pipeline():
    started = datetime.utcnow()
    log.info("daily_pipeline_start", at=started.isoformat())
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{SCRAPER_URL}/scrape/all")
            r.raise_for_status()
            log.info("scraper_triggered", body=r.json())
        await wait_for_scraper_idle()

        async with httpx.AsyncClient(timeout=60 * 30) as client:
            r1 = await client.post(f"{RECOMMENDER_URL}/score/all/sync")
            r1.raise_for_status()
            log.info("scoring_done", body=r1.json())
            r2 = await client.post(f"{RECOMMENDER_URL}/score/portfolio/sync")
            r2.raise_for_status()
            log.info("portfolio_scored", body=r2.json())
    except Exception as exc:
        log.exception("daily_pipeline_failed", error=str(exc))
    log.info("daily_pipeline_done", duration_s=(datetime.utcnow() - started).total_seconds())


def main():
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    minute, hour, dom, month, dow = settings.daily_scrape_cron.split()
    scheduler.add_job(
        daily_pipeline,
        CronTrigger(minute=minute, hour=hour, day=dom, month=month, day_of_week=dow,
                    timezone=settings.timezone),
        id="daily_pipeline", name="Daily scrape + score",
        replace_existing=True, misfire_grace_time=60 * 30,
    )
    scheduler.start()
    log.info("scheduler_started", cron=settings.daily_scrape_cron, tz=settings.timezone)
    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
