"""Cross-cutting types for broker adapters."""
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
    WORKING = "WORKING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class PlaceOrderRequest:
    broker_symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    extras: dict = field(default_factory=dict)


@dataclass
class BrokerOrder:
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
    broker_symbol: str
    quantity: Decimal
    avg_open_price: Optional[Decimal]
    current_price: Optional[Decimal]
    unrealized_pl: Optional[Decimal]
    unrealized_pl_pct: Optional[Decimal]
    currency: Optional[str]
    direction: Direction
    # Capital.com positions[].dealId (or equivalent on other brokers). The
    # only way to target a SPECIFIC position when multiple positions exist
    # on the same symbol — which is the default state of any signal-driven
    # fanout. Optional only because manual-broker positions have no ref.
    broker_position_ref: Optional[str] = None
    # Live SL/TP as reported by the broker. Differs from order-time values
    # once the user starts moving SL manually or partial closes happen.
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    opened_at: Optional[datetime] = None
    raw: Optional[dict] = None


@dataclass
class ModifyPositionRequest:
    """Change SL/TP on an OPEN position. None = leave unchanged.

    The semantics are intentionally "leave unchanged" not "remove" — to
    explicitly remove a stop, the caller passes Decimal('0') or a sentinel
    the adapter recognises. Most use cases just want to move SL up.
    """
    broker_position_ref: str
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@dataclass
class ModifyOrderRequest:
    """Change levels on a PENDING working order (not yet filled)."""
    broker_order_ref: str
    limit_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@dataclass
class ClosePositionResult:
    """Outcome of a close operation. The boolean answer isn't enough — we
    also want fill price + size so the UI can show "closed 0.5 lot @ 4452"
    rather than just 'OK'.
    """
    broker_position_ref: str
    closed: bool
    closed_quantity: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    realized_pl: Optional[Decimal] = None
    raw: Optional[dict] = None


@dataclass
class BrokerInstrument:
    broker_symbol: str
    name: str
    instrument_type: Optional[str]
    currency: Optional[str]
    min_qty: Optional[Decimal] = None


@dataclass
class BrokerQuote:
    """Live quote from a broker for one tradable instrument."""
    broker_symbol: str
    bid: Optional[Decimal] = None
    offer: Optional[Decimal] = None       # aka ask
    last_price: Optional[Decimal] = None  # mid or last-trade
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None  # previous close
    change_abs: Optional[Decimal] = None
    change_pct: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    currency: Optional[str] = None
    market_status: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class AccountInfo:
    account_id: str
    balance: Optional[Decimal]
    available: Optional[Decimal]
    currency: Optional[str]
    raw: Optional[dict] = None


class BrokerError(Exception): ...
class AuthError(BrokerError): ...
class NotFoundError(BrokerError): ...
class RateLimitError(BrokerError): ...
class NetworkError(BrokerError): ...


def to_dec(x: Any) -> Optional[Decimal]:
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x))
    except Exception:
        return None
