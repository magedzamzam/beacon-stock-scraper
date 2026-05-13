"""Beacon scheduler — DB-driven configuration with live reload.

Job schedules live in app_settings (one row per 'job.<name>'). Every 60s
this service re-reads them and updates the APScheduler triggers via
replace_existing=True. Admin UI edits propagate without restart.

Each scheduled run writes a row to job_runs so the admin can audit it.

Job kinds today:
    job.scrape_daily_quotes      -> POST /scrape/all (mode='daily')  on scraper
    job.scrape_fundamentals      -> POST /scrape/all (mode='full')   on scraper
    job.score_recompute          -> POST /score/all/sync             on recommender
                                    + POST /score/portfolio/sync
    job.account_stats_snapshot   -> in-process (snapshot_all_accounts)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from shared.db import (
    AccountBalanceSnapshot, AppSetting, Broker, BrokerPositionSnapshot, JobRun,
    PortfolioPosition, SessionLocal, Stock, TradingAccount,
)
from shared.logging_setup import configure_logging
from shared.settings import get_settings

log = configure_logging("scheduler")
settings = get_settings()

SCRAPER_URL = os.environ.get("SCRAPER_URL", "http://scraper:8001")
RECOMMENDER_URL = os.environ.get("RECOMMENDER_URL", "http://recommender:8002")
BROKER_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")

# Default crons mirror routers_settings.KNOWN_JOBS so a fresh DB without
# seeded settings still gets reasonable behaviour.
DEFAULT_JOBS = {
    "job.scrape_daily_quotes": "0 16 * * *",
    "job.scrape_fundamentals": "0 3 1 * *",
    "job.score_recompute":     "30 16 * * *",
    "job.account_stats_snapshot": "15 */6 * * *",
    "job.broker_quote_refresh": "5 * * * *",
}


# --------------------------------------------------------------------------
# job_runs audit helpers
# --------------------------------------------------------------------------
def _start_run(job_key: str) -> tuple[int, datetime]:
    """Insert a 'running' row and return (id, started_at)."""
    with SessionLocal() as s:
        run = JobRun(job_key=job_key, status="running", triggered_by="scheduled")
        s.add(run)
        s.commit()
        s.refresh(run)
        return run.id, run.started_at


def _finish_run(run_id: int, started: datetime, status: str,
                summary: Optional[dict] = None, error: Optional[str] = None):
    finished = datetime.utcnow()
    duration = Decimal(str((finished - started).total_seconds())).quantize(Decimal("0.01"))
    with SessionLocal() as s:
        run = s.get(JobRun, run_id)
        if run is None:
            return
        run.finished_at = finished
        run.duration_s = duration
        run.status = status
        run.summary = summary
        run.error_message = error
        s.commit()


# --------------------------------------------------------------------------
# Job implementations
# --------------------------------------------------------------------------
async def _scrape_with_mode(mode: str, exchanges: list[str]):
    payload = {"mode": mode, "exchanges": exchanges or None}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{SCRAPER_URL}/scrape/all", json=payload)
        r.raise_for_status()
        return r.json()


async def run_scrape_daily_quotes():
    """Light daily scrape: OHLC + technicals + analyst + news."""
    cfg = _read_job_cfg("job.scrape_daily_quotes")
    if not cfg.get("enabled", True):
        return
    rid, started = _start_run("job.scrape_daily_quotes")
    try:
        summary = await _scrape_with_mode("daily", cfg.get("exchanges") or [])
        _finish_run(rid, started, "ok", summary=summary)
    except Exception as exc:
        log.exception("scrape_daily_quotes_failed", error=str(exc))
        _finish_run(rid, started, "failed", error=str(exc))


async def run_scrape_fundamentals():
    """Heavy monthly scrape: full fundamentals + valuation."""
    cfg = _read_job_cfg("job.scrape_fundamentals")
    if not cfg.get("enabled", True):
        return
    rid, started = _start_run("job.scrape_fundamentals")
    try:
        summary = await _scrape_with_mode("full", cfg.get("exchanges") or [])
        _finish_run(rid, started, "ok", summary=summary)
    except Exception as exc:
        log.exception("scrape_fundamentals_failed", error=str(exc))
        _finish_run(rid, started, "failed", error=str(exc))


async def run_score_recompute():
    """Recompute composite scores (all + portfolio)."""
    cfg = _read_job_cfg("job.score_recompute")
    if not cfg.get("enabled", True):
        return
    rid, started = _start_run("job.score_recompute")
    try:
        async with httpx.AsyncClient(timeout=60 * 30) as client:
            r1 = await client.post(f"{RECOMMENDER_URL}/score/all/sync")
            r1.raise_for_status()
            r2 = await client.post(f"{RECOMMENDER_URL}/score/portfolio/sync")
            r2.raise_for_status()
        _finish_run(rid, started, "ok",
                    summary={"all": r1.json(), "portfolio": r2.json()})
    except Exception as exc:
        log.exception("score_recompute_failed", error=str(exc))
        _finish_run(rid, started, "failed", error=str(exc))


async def run_account_stats_snapshot():
    """In-process snapshot of every active trading account."""
    cfg = _read_job_cfg("job.account_stats_snapshot")
    if not cfg.get("enabled", True):
        return
    rid, started = _start_run("job.account_stats_snapshot")
    try:
        with SessionLocal() as s:
            accts = s.execute(
                select(TradingAccount, Broker)
                .join(Broker, TradingAccount.broker_id == Broker.id)
                .where(TradingAccount.is_active.is_(True))
            ).all()

        written = 0
        for (acct, broker) in accts:
            try:
                with SessionLocal() as s:
                    if broker.kind == "manual":
                        # Round 3: read canonical price from stock_quotes
                        from shared.db import StockQuote as _SQ
                        rows = s.execute(
                            select(PortfolioPosition, Stock, _SQ)
                            .join(Stock, PortfolioPosition.stock_id == Stock.id)
                            .outerjoin(_SQ, _SQ.stock_id == Stock.id)
                            .where(PortfolioPosition.account_id == acct.id,
                                   PortfolioPosition.is_open.is_(True))
                        ).all()
                        equity = Decimal("0"); unrealized = Decimal("0"); counted = 0
                        for (p, _stock, snap) in rows:
                            cur = snap.current_price if snap else None
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
        _finish_run(rid, started, "ok", summary={"written": written})
    except Exception as exc:
        log.exception("account_stats_snapshot_failed", error=str(exc))
        _finish_run(rid, started, "failed", error=str(exc))


async def run_broker_quote_refresh():
    """Hourly refresh of live quotes for stocks with a broker mapping.

    Uses the broker_gateway's batch endpoint: one HTTP call per broker (one
    Capital.com session login per broker) instead of N calls. Before this
    change, ~200 mappings = ~200 session POSTs and Capital.com 429'd the
    whole batch.
    """
    cfg = _read_job_cfg("job.broker_quote_refresh")
    if not cfg.get("enabled", True):
        return
    rid, started = _start_run("job.broker_quote_refresh")
    try:
        from collections import defaultdict
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from shared.db import (
            BrokerInstrument,
            StockCurQuote, StockHistoryQuote, StockQuote,
        )

        with SessionLocal() as s:
            mappings = s.execute(
                select(BrokerInstrument)
                .where(BrokerInstrument.is_tradeable.is_(True),
                       BrokerInstrument.stock_id.is_not(None),
                       BrokerInstrument.broker_symbol.is_not(None))
            ).scalars().all()
            # (stock_id, broker_id, broker_symbol)
            mapping_data = [(m.stock_id, m.broker_id, m.broker_symbol) for m in mappings]

        # Bucket by broker_id: one batch request per broker
        by_broker: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for stock_id, broker_id, broker_symbol in mapping_data:
            by_broker[broker_id].append((stock_id, broker_symbol))

        # Early exit when there's nothing to do — otherwise the audit row
        # says "updated: 0" with no explanation and looks like a silent bug.
        if not mapping_data:
            _finish_run(rid, started, "ok", summary={
                "updated": 0, "failed": 0, "total": 0, "brokers": 0,
                "note": "No tradeable broker instruments to refresh.",
            })
            return

        ok = failed = 0
        broker_diag: dict[int, dict] = {}
        # Generous timeout — a 200-symbol batch through Capital.com can take
        # tens of seconds because the adapter fetches one quote at a time.
        async with httpx.AsyncClient(timeout=300) as client:
            for broker_id, items in by_broker.items():
                symbols = [sym for (_sid, sym) in items]
                if not symbols:
                    continue
                sym_to_stock = {sym: sid for (sid, sym) in items}
                diag = {"symbols": len(symbols), "ok": 0, "failed": 0}
                broker_diag[broker_id] = diag

                try:
                    r = await client.post(
                        f"{BROKER_GATEWAY_URL}/brokers/{broker_id}/quotes/batch",
                        json={"symbols": symbols},
                    )
                    if r.status_code >= 400:
                        log.warning("batch_quote_failed",
                                    broker_id=broker_id, status=r.status_code,
                                    body=r.text[:200])
                        diag["failed"] = len(symbols)
                        diag["http_status"] = r.status_code
                        diag["error"] = r.text[:300]
                        failed += len(symbols)
                        continue
                    batch = r.json()
                except Exception as exc:
                    log.warning("batch_quote_exception",
                                broker_id=broker_id, error=str(exc))
                    diag["failed"] = len(symbols)
                    diag["error"] = f"{type(exc).__name__}: {exc}"
                    failed += len(symbols)
                    continue

                quotes = batch.get("quotes", {})
                errors = batch.get("errors", {})
                diag["broker_errors"] = len(errors)
                if errors:
                    sample = list(errors.items())[:5]
                    diag["error_samples"] = {k: v for k, v in sample}

                for symbol, payload in quotes.items():
                    stock_id = sym_to_stock.get(symbol)
                    if stock_id is None:
                        continue

                    def _dec(k, p=payload):
                        v = p.get(k)
                        return Decimal(str(v)) if v is not None else None

                    cq_values = {
                        "stock_id": stock_id, "broker_id": broker_id,
                        "broker_symbol": symbol,
                        "bid": _dec("bid"), "offer": _dec("offer"),
                        "last_price": _dec("last_price"),
                        "open_price": _dec("open_price"),
                        "high_price": _dec("high_price"),
                        "low_price": _dec("low_price"),
                        "close_price": _dec("close_price"),
                        "broker_change_abs": _dec("change_abs"),
                        "broker_change_pct": _dec("change_pct"),
                        "volume": _dec("volume"),
                        "currency": payload.get("currency"),
                        "market_status": payload.get("market_status"),
                        "fetched_at": datetime.utcnow(),
                    }
                    try:
                        with SessionLocal() as s:
                            cq_stmt = pg_insert(StockCurQuote).values(**cq_values).on_conflict_do_update(
                                index_elements=["stock_id", "broker_id"],
                                set_={k: v for k, v in cq_values.items()
                                      if k not in ("stock_id", "broker_id", "broker_symbol")},
                            )
                            s.execute(cq_stmt)

                            # Refresh canonical stock_quotes (preserve score/verdict)
                            last_price = cq_values["last_price"]
                            if last_price is not None:
                                hist = s.execute(
                                    select(StockHistoryQuote.close_price)
                                    .where(StockHistoryQuote.stock_id == stock_id,
                                           StockHistoryQuote.close_price.is_not(None))
                                    .order_by(StockHistoryQuote.trading_date.desc()).limit(2)
                                ).all()
                                prev_close = hist[1].close_price if len(hist) >= 2 else None
                                ch_abs = ch_pct = None
                                if prev_close is not None and prev_close != 0:
                                    ch_abs = last_price - prev_close
                                    ch_pct = (ch_abs / prev_close) * 100
                                sq_record = {
                                    "stock_id": stock_id,
                                    "current_price": last_price,
                                    "prev_close": prev_close,
                                    "change_abs": ch_abs,
                                    "change_pct": ch_pct,
                                    "price_source": "broker",
                                    "price_fetched_at": cq_values["fetched_at"],
                                    "last_updated": datetime.utcnow(),
                                }
                                sq_stmt = pg_insert(StockQuote).values(**sq_record).on_conflict_do_update(
                                    index_elements=["stock_id"],
                                    set_={k: v for k, v in sq_record.items() if k != "stock_id"},
                                )
                                s.execute(sq_stmt)
                            s.commit()
                        ok += 1
                        diag["ok"] += 1
                    except Exception as exc:
                        log.warning("quote_db_failed",
                                    stock_id=stock_id, symbol=symbol, error=str(exc))
                        failed += 1
                        diag["failed"] += 1
                        diag.setdefault("db_error", f"{type(exc).__name__}: {exc}")

                # Per-symbol broker errors come back inside the batch payload
                for symbol, msg in errors.items():
                    log.warning("quote_broker_error",
                                broker_id=broker_id, symbol=symbol, error=msg)
                    failed += 1
                    diag["failed"] += 1

        _finish_run(rid, started, "ok",
                    summary={"updated": ok, "failed": failed,
                             "total": len(mapping_data),
                             "brokers": len(by_broker),
                             "broker_diagnostics": broker_diag})
    except Exception as exc:
        log.exception("broker_quote_refresh_failed", error=str(exc))
        _finish_run(rid, started, "failed", error=str(exc))


JOB_HANDLERS = {
    "job.scrape_daily_quotes": run_scrape_daily_quotes,
    "job.scrape_fundamentals": run_scrape_fundamentals,
    "job.score_recompute": run_score_recompute,
    "job.account_stats_snapshot": run_account_stats_snapshot,
    "job.broker_quote_refresh": run_broker_quote_refresh,
}


# --------------------------------------------------------------------------
# DB-driven scheduling
# --------------------------------------------------------------------------
def _read_job_cfg(key: str) -> dict:
    """Return the current config for a job key. Falls back to defaults."""
    with SessionLocal() as s:
        row = s.get(AppSetting, key)
        if row is None or not row.value:
            return {"enabled": True, "cron": DEFAULT_JOBS.get(key), "exchanges": []}
        v = row.value
        return {
            "enabled": bool(v.get("enabled", True)),
            "cron": v.get("cron") or DEFAULT_JOBS.get(key),
            "exchanges": v.get("exchanges") or [],
        }


def _apply_job_to_scheduler(scheduler: AsyncIOScheduler, key: str):
    """Add or update one APScheduler job from current DB config.

    Disabled jobs are removed entirely so they don't fire.
    """
    cfg = _read_job_cfg(key)
    handler = JOB_HANDLERS[key]
    cron_str = cfg.get("cron") or DEFAULT_JOBS.get(key)
    if not cfg.get("enabled", True):
        if scheduler.get_job(key):
            scheduler.remove_job(key)
            log.info("job_disabled", key=key)
        return
    parts = cron_str.split()
    if len(parts) != 5:
        log.warning("job_invalid_cron", key=key, cron=cron_str)
        return
    minute, hour, dom, month, dow = parts
    try:
        scheduler.add_job(
            handler,
            CronTrigger(minute=minute, hour=hour, day=dom, month=month,
                        day_of_week=dow, timezone=settings.timezone),
            id=key, name=key, replace_existing=True,
            misfire_grace_time=60 * 15,
        )
    except Exception as exc:
        log.warning("job_apply_failed", key=key, cron=cron_str, error=str(exc))


def reload_all_jobs(scheduler: AsyncIOScheduler):
    for key in JOB_HANDLERS:
        _apply_job_to_scheduler(scheduler, key)


async def reload_loop(scheduler: AsyncIOScheduler):
    """Re-read app_settings every 60 seconds so admin edits take effect."""
    while True:
        try:
            await asyncio.sleep(60)
            reload_all_jobs(scheduler)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.warning("reload_loop_error", error=str(exc))


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------
async def _async_main():
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    reload_all_jobs(scheduler)
    scheduler.start()
    log.info("scheduler_started", tz=settings.timezone, jobs=list(JOB_HANDLERS.keys()))
    asyncio.create_task(reload_loop(scheduler))
    # Run forever
    while True:
        await asyncio.sleep(3600)


def main():
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
