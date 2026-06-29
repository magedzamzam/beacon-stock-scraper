"""price_stream service entrypoint.

Loop:
  1. Ask broker_gateway for a streaming session (CST + security token).
  2. Connect to Capital.com's WebSocket, subscribe to OHLCMarketData
     (candles) + marketData (quotes) for the configured epics.
  3. Ping every PING_SECONDS to keep the 10-minute session alive.
  4. Persist ohlc.event -> intraday_bar, quote -> stream_quote.
  5. On any drop/error, back off and reconnect with a fresh session.

Config (env):
  STREAM_ACCOUNT_ID   trading_accounts.id that holds Capital.com creds (required)
  STREAM_EPICS        comma list of epics (default "GOLD")
  STREAM_RESOLUTION   OHLC resolution (default "MINUTE_5")
  BROKER_GATEWAY_URL  default http://broker_gateway:8004
  PING_SECONDS        keepalive ping interval (default 300; must be < 600)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import httpx
import websockets
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.db import IntradayBar, SessionLocal, StreamQuote
from .handlers import parse_ohlc_event, parse_quote_event

log = logging.getLogger("price_stream")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

WS_URL = "wss://api-streaming-capital.backend-capital.com/connect"
GATEWAY = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")
ACCOUNT_ID = os.environ.get("STREAM_ACCOUNT_ID")
EPICS = [e.strip() for e in os.environ.get("STREAM_EPICS", "GOLD").split(",") if e.strip()]
RESOLUTION = os.environ.get("STREAM_RESOLUTION", "MINUTE_5")
PING_SECONDS = min(int(os.environ.get("PING_SECONDS", "300")), 540)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _save_bar(row: dict) -> None:
    with SessionLocal() as s:
        stmt = pg_insert(IntradayBar.__table__).values(**row)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_intraday_bar",
            set_={
                "open_price": stmt.excluded.open_price,
                "high_price": stmt.excluded.high_price,
                "low_price": stmt.excluded.low_price,
                "close_price": stmt.excluded.close_price,
            },
        )
        s.execute(stmt)
        s.commit()


def _save_quote(row: dict) -> None:
    with SessionLocal() as s:
        stmt = pg_insert(StreamQuote.__table__).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "bid": stmt.excluded.bid, "offer": stmt.excluded.offer,
                "bid_qty": stmt.excluded.bid_qty, "ofr_qty": stmt.excluded.ofr_qty,
                "quote_ts": stmt.excluded.quote_ts,
                "received_at": stmt.excluded.received_at,
            },
        )
        s.execute(stmt)
        s.commit()


# ---------------------------------------------------------------------------
# Session + socket
# ---------------------------------------------------------------------------
async def _get_session() -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GATEWAY}/accounts/{ACCOUNT_ID}/stream_session")
        r.raise_for_status()
        return r.json()


async def _ping_loop(ws, cst: str, sec: str) -> None:
    cid = 1000
    while True:
        await asyncio.sleep(PING_SECONDS)
        cid += 1
        await ws.send(json.dumps({
            "destination": "ping", "correlationId": str(cid),
            "cst": cst, "securityToken": sec,
        }))
        log.debug("ping sent")


async def _subscribe(ws, cst: str, sec: str) -> None:
    await ws.send(json.dumps({
        "destination": "OHLCMarketData.subscribe", "correlationId": "1",
        "cst": cst, "securityToken": sec,
        "payload": {"epics": EPICS, "resolutions": [RESOLUTION], "type": "classic"},
    }))
    await ws.send(json.dumps({
        "destination": "marketData.subscribe", "correlationId": "2",
        "cst": cst, "securityToken": sec,
        "payload": {"epics": EPICS},
    }))
    log.info("subscribed epics=%s resolution=%s", EPICS, RESOLUTION)


async def _run_once() -> None:
    sess = await _get_session()
    cst, sec = sess["cst"], sess["security_token"]
    async with websockets.connect(WS_URL, ping_interval=None, max_queue=256) as ws:
        await _subscribe(ws, cst, sec)
        ping = asyncio.create_task(_ping_loop(ws, cst, sec))
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                dest = msg.get("destination")
                payload = msg.get("payload") or {}
                if dest == "ohlc.event":
                    row = parse_ohlc_event(payload)
                    if row:
                        _save_bar(row)
                elif dest == "quote":
                    row = parse_quote_event(payload)
                    if row:
                        _save_quote(row)
                elif msg.get("status") and msg.get("status") != "OK":
                    log.warning("ws status: %s", msg)
        finally:
            ping.cancel()


async def main() -> None:
    if not ACCOUNT_ID:
        log.error("STREAM_ACCOUNT_ID not set — nothing to stream. Exiting.")
        return
    backoff = 2
    while True:
        try:
            log.info("connecting (account=%s, gateway=%s)", ACCOUNT_ID, GATEWAY)
            await _run_once()
            backoff = 2  # clean exit of read loop — reconnect promptly
        except Exception as exc:  # noqa: BLE001 — keep the service alive
            log.warning("stream dropped: %s — reconnecting in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
