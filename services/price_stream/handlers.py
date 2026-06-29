"""Pure parsing of Capital.com WebSocket payloads into DB-ready dicts.

Kept free of I/O so it can be unit-tested without a socket or DB.

Reference payloads (from Capital.com docs):

  ohlc.event:
    {"resolution":"MINUTE_5","epic":"GOLD","type":"classic","priceType":"bid",
     "t":1671714000000,"h":134.95,"l":134.85,"o":134.86,"c":134.88}

  quote:
    {"epic":"GOLD","product":"CFD","bid":93.87,"bidQty":4976.0,
     "ofr":93.9,"ofrQty":5000.0,"timestamp":1660297190627}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _ts(ms: Any) -> Optional[datetime]:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_ohlc_event(payload: dict) -> Optional[dict]:
    """ohlc.event payload -> intraday_bar upsert dict (or None if unusable)."""
    epic = payload.get("epic")
    bar_ts = _ts(payload.get("t"))
    if not epic or bar_ts is None:
        return None
    o, h, l, c = (payload.get(k) for k in ("o", "h", "l", "c"))
    if None in (o, h, l, c):
        return None
    return {
        "symbol": epic,
        "resolution": payload.get("resolution") or "MINUTE_5",
        "price_type": (payload.get("priceType") or "bid").lower(),
        "bar_ts": bar_ts,
        "open_price": float(o),
        "high_price": float(h),
        "low_price": float(l),
        "close_price": float(c),
    }


def parse_quote_event(payload: dict) -> Optional[dict]:
    """quote payload -> stream_quote upsert dict (or None if unusable)."""
    epic = payload.get("epic")
    if not epic:
        return None
    bid, ofr = payload.get("bid"), payload.get("ofr")
    if bid is None and ofr is None:
        return None
    return {
        "symbol": epic,
        "bid": float(bid) if bid is not None else None,
        "offer": float(ofr) if ofr is not None else None,
        "bid_qty": float(payload["bidQty"]) if payload.get("bidQty") is not None else None,
        "ofr_qty": float(payload["ofrQty"]) if payload.get("ofrQty") is not None else None,
        "quote_ts": _ts(payload.get("timestamp")),
    }
