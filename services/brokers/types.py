"""Cross-cutting types for broker adapters.

Each adapter takes typed inputs and returns typed outputs so the gateway
layer never has to peek inside broker-specific shapes. If a broker's API
returns extra detail we want to keep around, we stash it in the ``raw``
field of BrokerPosition / BrokerOrder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    WORKING = "WORKING"     # accepted, sitting on broker's book (limit orders)
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class PlaceOrderRequest:
    """What the gateway hands an adapter to place an order."""
    broker_symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    # Optional adapter-specific extras (e.g. force_open for Capital.com)
    extras: dict = field(default_factory=dict)


@dataclass
class BrokerOrder:
    """An order as reported by a broker (or as we recorded it for manual)."""
    broker_order_ref: Optional[str]
    broker_symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    status: OrderStatus
    fill_price: Optional[Decimal] = None
    fill_quantity: Optional[Decimal] = None
    placed_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    currency: Optional[str] = None
    rejection_reason: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class BrokerPosition:
    """A single open position as the broker reports it."""
    broker_symbol: str
    quantity: Decimal
    avg_open_price: Optional[Decimal]
    current_price: Optional[Decimal]
    unrealized_pl: Optional[Decimal]
    unrealized_pl_pct: Optional[Decimal]
    currency: Optional[str]
    direction: Direction
    raw: Optional[dict] = None


@dataclass
class BrokerInstrument:
    """An instrument the broker offers, found via search/lookup."""
    broker_symbol: str
    name: str
    instrument_type: Optional[str]
    currency: Optional[str]
    min_qty: Optional[Decimal] = None


@dataclass
class AccountInfo:
    """Light-weight account info returned by the broker."""
    account_id: str
    balance: Optional[Decimal]
    available: Optional[Decimal]
    currency: Optional[str]
    raw: Optional[dict] = None


class BrokerError(Exception):
    """Base class for adapter-side errors. Subclasses indicate cause."""


class AuthError(BrokerError):
    """Credentials rejected (401, expired session, etc.)."""


class NotFoundError(BrokerError):
    """Symbol or order id not found."""


class RateLimitError(BrokerError):
    """Broker is rate-limiting us. Caller should back off."""


class NetworkError(BrokerError):
    """Connection issue, timeout, DNS failure, etc."""


def to_dec(x: Any) -> Optional[Decimal]:
    """Best-effort conversion to Decimal, or None for missing/garbage values."""
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x))
    except Exception:
        return None
