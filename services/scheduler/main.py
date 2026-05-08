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
SENTIMENT_URL = "http://sentiment:8003"


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

        # Score sentiment on the headlines we just pulled. Long timeout because
        # the first run of the day may have a couple hundred unscored rows.
        try:
            async with httpx.AsyncClient(timeout=60 * 15) as client:
                rs = await client.post(f"{SENTIMENT_URL}/sentiment/score-pending")
                rs.raise_for_status()
                log.info("sentiment_done", body=rs.json())
        except Exception as exc:
            # Don't block scoring on sentiment failures — verdicts work without it.
            log.warning("sentiment_step_failed", error=str(exc))

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


async def snapshot_all_accounts():
    """Periodic capture of account balance snapshots.

    For automated accounts: hits broker_gateway /accounts/{id}/info to refresh
    balance, sums unrealized_pl from broker_positions_snapshot, derives equity.

    For manual accounts: pulls open positions from portfolio_positions, marks
    them with stock_latest_snapshot.last_close, sums to equity / unrealized.

    All errors are swallowed per-account so one bad credential doesn't stop
    the whole tick.
    """
    from decimal import Decimal
    from shared.db import (
        AccountBalanceSnapshot, Broker, BrokerPositionSnapshot,
        PortfolioPosition, Stock, StockLatestSnapshot, TradingAccount,
    )
    log.info("stats_snapshot_start")
    with SessionLocal() as s:
        accts = s.execute(
            select(TradingAccount, Broker)
            .join(Broker, TradingAccount.broker_id == Broker.id)
            .where(TradingAccount.is_active.is_(True))
        ).all()

    BROKER_GATEWAY_URL = "http://broker_gateway:8004"
    written = 0
    for (acct, broker) in accts:
        try:
            with SessionLocal() as s:
                if broker.kind == "manual":
                    rows = s.execute(
                        select(PortfolioPosition, Stock, StockLatestSnapshot)
                        .join(Stock, PortfolioPosition.stock_id == Stock.id)
                        .outerjoin(StockLatestSnapshot, StockLatestSnapshot.stock_id == Stock.id)
                        .where(PortfolioPosition.account_id == acct.id,
                               PortfolioPosition.is_open.is_(True))
                    ).all()
                    equity = Decimal("0")
                    unrealized = Decimal("0")
                    counted = 0
                    for (p, _stock, snap) in rows:
                        cur = snap.last_close if snap else None
                        if cur is None:
                            continue
                        equity += Decimal(str(cur)) * Decimal(str(p.quantity))
                        unrealized += (Decimal(str(cur)) - Decimal(str(p.avg_entry_price))) * Decimal(str(p.quantity))
                        counted += 1
                    s.add(AccountBalanceSnapshot(
                        account_id=acct.id,
                        balance=None, available=None,
                        equity=equity, unrealized_pl=unrealized,
                        open_position_count=counted, currency=acct.currency,
                        source="periodic",
                    ))
                else:
                    balance = available = None
                    currency = acct.currency
                    try:
                        async with httpx.AsyncClient(timeout=15) as client:
                            r = await client.get(f"{BROKER_GATEWAY_URL}/accounts/{acct.id}/info")
                            if r.status_code < 400:
                                info = r.json()
                                if info.get("balance") is not None:
                                    balance = Decimal(str(info["balance"]))
                                if info.get("available") is not None:
                                    available = Decimal(str(info["available"]))
                                if info.get("currency"):
                                    currency = info["currency"]
                    except Exception as exc:
                        log.warning("stats_snapshot_broker_unreachable",
                                    account_id=acct.id, error=str(exc))
                    pl_rows = s.execute(
                        select(BrokerPositionSnapshot.unrealized_pl)
                        .where(BrokerPositionSnapshot.account_id == acct.id)
                    ).scalars().all()
                    unrealized = sum((Decimal(str(x)) for x in pl_rows if x is not None), start=Decimal("0"))
                    pos_count = len(pl_rows)
                    equity = (balance + unrealized) if balance is not None else None
                    s.add(AccountBalanceSnapshot(
                        account_id=acct.id,
                        balance=balance, available=available,
                        equity=equity, unrealized_pl=unrealized,
                        open_position_count=pos_count, currency=currency,
                        source="periodic",
                    ))
                s.commit()
                written += 1
        except Exception as exc:
            log.warning("stats_snapshot_failed", account_id=acct.id, error=str(exc))
    log.info("stats_snapshot_done", written=written)


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
    # Account balance snapshots — every 6 hours.
    scheduler.add_job(
        snapshot_all_accounts,
        CronTrigger(hour="*/6", minute=15, timezone=settings.timezone),
        id="account_stats_snapshot", name="Account balance snapshot",
        replace_existing=True, misfire_grace_time=60 * 15,
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
