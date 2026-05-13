"""Admin-only endpoints for app settings + scheduled job management.

Endpoints:
    GET    /admin/settings            list all known scheduled jobs + recent runs
    PUT    /admin/settings/{key}      replace a setting value
    POST   /admin/settings/{key}/run  trigger a job manually (returns immediately)
    GET    /admin/settings/runs       recent job execution audit log

Only the four 'job.<name>' settings are surfaced in the UI today, but the
table is generic so any future config can ride on the same plumbing.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import AppSetting, JobRun, User
from shared.logging_setup import configure_logging

from .auth import get_db
from .routers_admin import require_admin


log = configure_logging("api-settings")
settings_router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

_SCRAPER_URL = os.environ.get("SCRAPER_URL", "http://scraper:8001")
_RECOMMENDER_URL = os.environ.get("RECOMMENDER_URL", "http://recommender:8002")


# Each entry describes a scheduled job to the UI. cron field validation is
# light: we let APScheduler reject malformed crons at apply-time.
KNOWN_JOBS: dict[str, dict[str, Any]] = {
    "job.scrape_daily_quotes": {
        "label": "Daily quote scrape",
        "purpose": "OHLC + technicals + analyst consensus + news. Light, fast.",
        "supports_exchanges": True,
        "default_cron": "0 16 * * *",
    },
    "job.scrape_fundamentals": {
        "label": "Monthly fundamentals scrape",
        "purpose": "Revenue, EPS, balance sheet, growth metrics. Heavy.",
        "supports_exchanges": True,
        "default_cron": "0 3 1 * *",
    },
    "job.score_recompute": {
        "label": "Recompute composite scores",
        "purpose": "Re-runs scoring after a data update. Cheap.",
        "supports_exchanges": False,
        "default_cron": "30 16 * * *",
    },
    "job.account_stats_snapshot": {
        "label": "Account balance snapshots",
        "purpose": "Captures balance/equity for charts. Every 6h.",
        "supports_exchanges": False,
        "default_cron": "15 */6 * * *",
    },
    "job.broker_quote_refresh": {
        "label": "Broker live quote refresh",
        "purpose": "Hourly: pulls bid/offer/OHLC from brokers for stocks with a mapping.",
        "supports_exchanges": False,
        "default_cron": "5 * * * *",
    },
}


class JobConfig(BaseModel):
    enabled: bool = True
    cron: str = Field(..., min_length=5)
    exchanges: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class JobOut(BaseModel):
    key: str
    label: str
    purpose: str
    supports_exchanges: bool
    config: JobConfig
    last_run: Optional[dict] = None


def _job_to_out(db: Session, key: str, meta: dict) -> JobOut:
    """Build a JobOut from DB state for one job key."""
    row = db.get(AppSetting, key)
    if row is None:
        cfg = JobConfig(enabled=True, cron=meta["default_cron"], exchanges=[])
    else:
        v = row.value or {}
        cfg = JobConfig(
            enabled=bool(v.get("enabled", True)),
            cron=v.get("cron") or meta["default_cron"],
            exchanges=v.get("exchanges") or [],
            description=v.get("description"),
        )
    last = db.execute(
        select(JobRun)
        .where(JobRun.job_key == key)
        .order_by(desc(JobRun.started_at))
        .limit(1)
    ).scalar_one_or_none()
    last_dict = None
    if last is not None:
        last_dict = {
            "started_at": last.started_at, "finished_at": last.finished_at,
            "status": last.status, "triggered_by": last.triggered_by,
            "duration_s": float(last.duration_s) if last.duration_s is not None else None,
            "error_message": last.error_message, "summary": last.summary,
        }
    return JobOut(
        key=key, label=meta["label"], purpose=meta["purpose"],
        supports_exchanges=meta["supports_exchanges"],
        config=cfg, last_run=last_dict,
    )


@settings_router.get("", response_model=list[JobOut])
def list_jobs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_job_to_out(db, key, meta) for key, meta in KNOWN_JOBS.items()]


@settings_router.put("/{key}", response_model=JobOut)
def update_job(
    key: str, body: JobConfig,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if key not in KNOWN_JOBS:
        raise HTTPException(404, f"Unknown setting key '{key}'")
    parts = body.cron.split()
    if len(parts) != 5:
        raise HTTPException(400, "cron must be 5 fields: 'minute hour day month dow'")

    new_value = {
        "enabled": body.enabled, "cron": body.cron,
        "exchanges": body.exchanges or [],
        "description": body.description,
    }
    stmt = pg_insert(AppSetting).values(
        key=key, value=new_value, description=KNOWN_JOBS[key]["purpose"],
        updated_at=datetime.utcnow(), updated_by=user.id,
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={
            "value": new_value,
            "updated_at": datetime.utcnow(),
            "updated_by": user.id,
        },
    )
    db.execute(stmt)
    db.commit()
    log.info("setting_updated", key=key, by=user.email)
    return _job_to_out(db, key, KNOWN_JOBS[key])


@settings_router.post("/{key}/run")
async def run_job(
    key: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger a scheduled job manually. Returns immediately; check
    /admin/settings to see the run audit row."""
    if key not in KNOWN_JOBS:
        raise HTTPException(404, f"Unknown job '{key}'")

    setting = db.get(AppSetting, key)
    cfg = (setting.value or {}) if setting else {}
    exchanges = cfg.get("exchanges") or []

    run = JobRun(job_key=key, status="running", triggered_by="manual", user_id=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    started = run.started_at

    summary = None
    error = None
    try:
        if key == "job.scrape_daily_quotes":
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{_SCRAPER_URL}/scrape/all",
                    json={"mode": "daily", "exchanges": exchanges or None},
                )
                r.raise_for_status()
                summary = r.json()
        elif key == "job.scrape_fundamentals":
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{_SCRAPER_URL}/scrape/all",
                    json={"mode": "full", "exchanges": exchanges or None},
                )
                r.raise_for_status()
                summary = r.json()
        elif key == "job.score_recompute":
            async with httpx.AsyncClient(timeout=60 * 30) as client:
                r1 = await client.post(f"{_RECOMMENDER_URL}/score/all/sync")
                r1.raise_for_status()
                r2 = await client.post(f"{_RECOMMENDER_URL}/score/portfolio/sync")
                r2.raise_for_status()
                summary = {"all": r1.json(), "portfolio": r2.json()}
        elif key == "job.broker_quote_refresh":
            # Calls broker_gateway's batch endpoint once per broker, then fans
            # the responses out to stock_cur_quote + stock_quotes.
            # Mirrors scheduler logic but runs in-process for instant manual refresh.
            from collections import defaultdict
            from decimal import Decimal as _D
            from sqlalchemy.dialects.postgresql import insert as _pg_insert
            from shared.db import (
                BrokerInstrument, StockCurQuote, StockHistoryQuote, StockQuote,
            )

            mapping_data = db.execute(
                select(BrokerInstrument.stock_id, BrokerInstrument.broker_id,
                       BrokerInstrument.broker_symbol)
                .where(BrokerInstrument.is_tradeable.is_(True),
                       BrokerInstrument.stock_id.is_not(None),
                       BrokerInstrument.broker_symbol.is_not(None))
            ).all()

            # If there are no tradeable mappings we can stop early and tell
            # the operator clearly — otherwise the job mysteriously reports
            # success with zero updates.
            if not mapping_data:
                summary = {
                    "updated": 0, "failed": 0, "total": 0, "brokers": 0,
                    "note": "No tradeable broker instruments. "
                            "Either no broker is connected, or the "
                            "broker_instruments rows for this user are "
                            "missing / have is_tradeable=False.",
                }
            else:
                # Bucket by broker_id — one batch call per broker
                by_broker: dict[int, list[tuple[int, str]]] = defaultdict(list)
                for (stock_id, broker_id, broker_symbol) in mapping_data:
                    by_broker[broker_id].append((stock_id, broker_symbol))

                ok_n = failed_n = 0
                # Per-broker diagnostics so we can see which broker failed and how.
                broker_diag: dict[int, dict[str, Any]] = {}
                gateway_url = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
                async with httpx.AsyncClient(timeout=300) as client:
                    for broker_id, items in by_broker.items():
                        symbols = [sym for (_sid, sym) in items]
                        if not symbols:
                            continue
                        sym_to_stock = {sym: sid for (sid, sym) in items}
                        diag = {"symbols": len(symbols), "ok": 0, "failed": 0}
                        broker_diag[broker_id] = diag
                        batch: Optional[dict] = None
                        try:
                            rq = await client.post(
                                f"{gateway_url}/brokers/{broker_id}/quotes/batch",
                                json={"symbols": symbols},
                            )
                            if rq.status_code >= 400:
                                diag["failed"] = len(symbols)
                                diag["http_status"] = rq.status_code
                                diag["error"] = rq.text[:300]
                                failed_n += len(symbols)
                                continue
                            batch = rq.json()
                        except Exception as exc:
                            diag["failed"] = len(symbols)
                            diag["error"] = f"{type(exc).__name__}: {exc}"
                            failed_n += len(symbols)
                            continue

                        quotes = batch.get("quotes", {})
                        errors = batch.get("errors", {})
                        diag["broker_errors"] = len(errors)
                        if errors:
                            # Keep a small sample so the UI shows what went wrong
                            sample = list(errors.items())[:5]
                            diag["error_samples"] = {k: v for k, v in sample}
                        failed_n += len(errors)
                        diag["failed"] += len(errors)

                        for symbol, payload in quotes.items():
                            stock_id = sym_to_stock.get(symbol)
                            if stock_id is None:
                                continue

                            def _dec(k, p=payload):
                                v = p.get(k)
                                return _D(str(v)) if v is not None else None

                            cur_values = {
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
                                cq_stmt = _pg_insert(StockCurQuote).values(**cur_values).on_conflict_do_update(
                                    index_elements=["stock_id", "broker_id"],
                                    set_={k: v for k, v in cur_values.items()
                                          if k not in ("stock_id", "broker_id", "broker_symbol")},
                                )
                                db.execute(cq_stmt)

                                last_p = cur_values["last_price"]
                                if last_p is not None:
                                    hist = db.execute(
                                        select(StockHistoryQuote.close_price)
                                        .where(StockHistoryQuote.stock_id == stock_id,
                                               StockHistoryQuote.close_price.is_not(None))
                                        .order_by(StockHistoryQuote.trading_date.desc()).limit(2)
                                    ).all()
                                    prev_c = hist[1].close_price if len(hist) >= 2 else None
                                    ch_a = ch_p = None
                                    if prev_c is not None and prev_c != 0:
                                        ch_a = last_p - prev_c
                                        ch_p = (ch_a / prev_c) * 100
                                    sq_record = {
                                        "stock_id": stock_id,
                                        "current_price": last_p,
                                        "prev_close": prev_c,
                                        "change_abs": ch_a,
                                        "change_pct": ch_p,
                                        "price_source": "broker",
                                        "price_fetched_at": cur_values["fetched_at"],
                                        "last_updated": datetime.utcnow(),
                                    }
                                    sq_stmt = _pg_insert(StockQuote).values(**sq_record).on_conflict_do_update(
                                        index_elements=["stock_id"],
                                        set_={k: v for k, v in sq_record.items() if k != "stock_id"},
                                    )
                                    db.execute(sq_stmt)
                                db.commit()
                                ok_n += 1
                                diag["ok"] += 1
                            except Exception as db_exc:
                                db.rollback()
                                failed_n += 1
                                diag["failed"] += 1
                                # First DB error per broker — useful when bulk
                                # of failures share the same cause.
                                diag.setdefault(
                                    "db_error",
                                    f"{type(db_exc).__name__}: {db_exc}",
                                )

                summary = {"updated": ok_n, "failed": failed_n,
                           "total": len(mapping_data), "brokers": len(by_broker),
                           "broker_diagnostics": broker_diag}
        elif key == "job.account_stats_snapshot":
            # The scheduler holds the actual implementation; manual trigger
            # via API would require HTTP-based dispatch we haven't built. Mark
            # 'skipped' explicitly rather than silently succeed.
            run.status = "skipped"
            run.finished_at = datetime.utcnow()
            run.duration_s = (run.finished_at - started).total_seconds()
            run.summary = {"note": "Snapshots run on the scheduler tick (every 6h)."}
            db.commit()
            return {"status": "skipped",
                    "message": "Account snapshots run on the next scheduler tick."}
    except Exception as exc:
        error = str(exc)

    finished = datetime.utcnow()
    db_run = db.get(JobRun, run_id)
    if db_run is not None:
        db_run.finished_at = finished
        db_run.duration_s = (finished - started).total_seconds()
        db_run.status = "ok" if error is None else "failed"
        db_run.error_message = error
        db_run.summary = summary
        db.commit()
    return {
        "status": "ok" if error is None else "failed",
        "summary": summary, "error": error,
    }


@settings_router.get("/runs")
def list_runs(
    job_key: Optional[str] = None,
    limit: int = 50,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = select(JobRun)
    if job_key:
        q = q.where(JobRun.job_key == job_key)
    q = q.order_by(desc(JobRun.started_at)).limit(min(limit, 200))
    rows = db.execute(q).scalars().all()
    return [{
        "id": r.id, "job_key": r.job_key,
        "started_at": r.started_at, "finished_at": r.finished_at,
        "status": r.status, "triggered_by": r.triggered_by,
        "duration_s": float(r.duration_s) if r.duration_s is not None else None,
        "summary": r.summary, "error_message": r.error_message,
    } for r in rows]
