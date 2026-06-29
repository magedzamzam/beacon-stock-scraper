"""Move-signal endpoints — a configurable "next bar may move >= $X" monitor.

    GET /signals/move/config   -> defaults + param schema for the UI form
    GET /signals/move          -> scan the universe, return firing symbols

Reads the existing DAILY OHLC series (stock_history_quote). The scorer
itself is timeframe-agnostic, so the same endpoint can later be pointed at a
5-minute series (e.g. XAU via the broker gateway) without changing the math.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db import Exchange, IntradayBar, Stock, StockHistoryQuote, StreamQuote, User

from .auth import get_current_user, get_db
from .signals import (
    Bar, MoveSignalConfig, PARAMS_SCHEMA, compute_move_signal,
)

signals_router = APIRouter(prefix="/signals", tags=["signals"])


@signals_router.get("/move/config")
def move_signal_config(_: User = Depends(get_current_user)):
    """Defaults + form schema so the UI can render the config panel."""
    return {"defaults": MoveSignalConfig().__dict__, "schema": PARAMS_SCHEMA}


@signals_router.get("/move")
def scan_move_signals(
    target_mode: str = Query("absolute", pattern="^(absolute|atr|percent)$"),
    target_value: float = Query(5.0, gt=0),
    atr_period: int = Query(14, ge=2, le=200),
    lookback: int = Query(20, ge=3, le=500),
    fire_threshold: float = Query(0.50, ge=0.0, le=1.0),
    exchange: Optional[str] = Query(None, description="Exchange code filter, e.g. DFM"),
    min_price: Optional[float] = Query(None, ge=0),
    only_fired: bool = Query(True, description="Return only symbols at/over the fire threshold"),
    limit: int = Query(100, ge=1, le=1000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scan active stocks and score each one's next-bar move probability."""
    cfg = MoveSignalConfig(
        target_mode=target_mode, target_value=target_value,
        atr_period=atr_period, lookback=lookback, fire_threshold=fire_threshold,
    )
    need_rows = max(atr_period, lookback) + 2

    # ---- in-scope stocks (+ exchange code) ---------------------------------
    meta_q = (
        select(Stock.id, Stock.ticker, Stock.company_name,
               Stock.currency, Exchange.code.label("exchange_code"))
        .join(Exchange, Exchange.id == Stock.exchange_id)
        .where(Stock.active.is_(True))
    )
    if exchange:
        meta_q = meta_q.where(Exchange.code == exchange.upper())
    meta = {r.id: r for r in db.execute(meta_q).all()}
    if not meta:
        return {"config": cfg.__dict__, "count": 0, "scanned": 0, "signals": []}

    # ---- last `need_rows` daily bars per stock, one windowed query ---------
    rn = func.row_number().over(
        partition_by=StockHistoryQuote.stock_id,
        order_by=StockHistoryQuote.trading_date.desc(),
    ).label("rn")
    sub = (
        select(
            StockHistoryQuote.stock_id.label("sid"),
            StockHistoryQuote.trading_date.label("td"),
            StockHistoryQuote.open_price, StockHistoryQuote.high_price,
            StockHistoryQuote.low_price, StockHistoryQuote.close_price,
            StockHistoryQuote.volume, rn,
        )
        .where(StockHistoryQuote.stock_id.in_(list(meta.keys())))
        .subquery()
    )
    rows = db.execute(
        select(
            sub.c.sid, sub.c.td, sub.c.open_price, sub.c.high_price,
            sub.c.low_price, sub.c.close_price, sub.c.volume,
        ).where(sub.c.rn <= need_rows).order_by(sub.c.sid, sub.c.td.asc())
    ).all()

    # group ascending by stock
    by_stock: dict[int, list[Bar]] = {}
    for r in rows:
        if r.open_price is None or r.high_price is None or r.low_price is None or r.close_price is None:
            continue
        by_stock.setdefault(r.sid, []).append(Bar(
            open=float(r.open_price), high=float(r.high_price),
            low=float(r.low_price), close=float(r.close_price),
            volume=float(r.volume) if r.volume is not None else None,
        ))

    out: list[dict] = []
    scanned = 0
    for sid, bars in by_stock.items():
        res = compute_move_signal(bars, cfg)
        if res.insufficient_data:
            continue
        scanned += 1
        last_close = bars[-1].close
        if min_price is not None and last_close < min_price:
            continue
        if only_fired and not res.fired:
            continue
        m = meta[sid]
        row = res.as_dict()
        row.update({
            "stock_id": sid, "ticker": m.ticker, "company_name": m.company_name,
            "exchange_code": m.exchange_code, "currency": m.currency,
            "last_close": round(last_close, 4),
        })
        out.append(row)

    out.sort(key=lambda d: d["score"], reverse=True)
    return {
        "config": cfg.__dict__,
        "scanned": scanned,
        "count": len(out),
        "signals": out[:limit],
    }


@signals_router.get("/move/live")
def move_signal_live(
    symbol: str = Query("GOLD", description="Streamed epic, e.g. GOLD"),
    resolution: str = Query("MINUTE_5"),
    price_type: str = Query("bid", pattern="^(bid|ask)$"),
    target_mode: str = Query("absolute", pattern="^(absolute|atr|percent)$"),
    target_value: float = Query(5.0, gt=0),
    atr_period: int = Query(14, ge=2, le=200),
    lookback: int = Query(20, ge=3, le=500),
    fire_threshold: float = Query(0.50, ge=0.0, le=1.0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Live move-signal for a streamed instrument (default GOLD).

    Reads candles persisted by the price_stream service and runs the SAME
    scorer used for daily stocks. The most recent (still-forming) bar is
    dropped so the signal only uses closed bars.
    """
    cfg = MoveSignalConfig(
        target_mode=target_mode, target_value=target_value,
        atr_period=atr_period, lookback=lookback, fire_threshold=fire_threshold,
    )
    need_rows = max(atr_period, lookback) + 2

    rows = db.execute(
        select(
            IntradayBar.bar_ts, IntradayBar.open_price, IntradayBar.high_price,
            IntradayBar.low_price, IntradayBar.close_price, IntradayBar.volume,
        )
        .where(IntradayBar.symbol == symbol,
               IntradayBar.resolution == resolution,
               IntradayBar.price_type == price_type)
        .order_by(IntradayBar.bar_ts.desc())
        .limit(need_rows + 1)
    ).all()
    rows = list(reversed(rows))  # ascending

    quote_row = db.get(StreamQuote, symbol)
    quote = None
    if quote_row is not None:
        quote = {
            "bid": float(quote_row.bid) if quote_row.bid is not None else None,
            "offer": float(quote_row.offer) if quote_row.offer is not None else None,
            "quote_ts": quote_row.quote_ts,
            "received_at": quote_row.received_at,
        }

    # Drop the most recent bar (still forming) so only closed bars feed the scorer.
    closed = rows[:-1] if len(rows) >= 2 else []
    bars = [Bar(open=float(r.open_price), high=float(r.high_price),
                low=float(r.low_price), close=float(r.close_price),
                volume=float(r.volume) if r.volume is not None else None)
            for r in closed
            if None not in (r.open_price, r.high_price, r.low_price, r.close_price)]

    res = compute_move_signal(bars, cfg)
    return {
        "symbol": symbol,
        "resolution": resolution,
        "price_type": price_type,
        "config": cfg.__dict__,
        "bars_used": len(bars),
        "last_closed_bar_ts": closed[-1].bar_ts if closed else None,
        "forming_bar_ts": rows[-1].bar_ts if rows else None,
        "quote": quote,
        "signal": res.as_dict(),
    }
