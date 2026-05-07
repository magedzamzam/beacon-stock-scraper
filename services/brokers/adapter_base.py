"""Adapter contract every broker integration must implement.

Adapter lifecycle
-----------------
The gateway constructs an adapter with a ``credentials`` dict that has been
decrypted from the database. The adapter is responsible for:

  * Establishing/refreshing any session with the broker on demand.
  * Translating between our normalized types (BrokerOrder, BrokerPosition...)
    and the broker's native shapes.
  * Mapping broker errors to the BrokerError hierarchy in types.py — never
    leak HTTP exceptions or library-specific errors past this layer.

Adapters MUST be safe to instantiate cheaply (no network in __init__). Any
expensive setup happens in ``ensure_session`` so accounts that are merely
listed don't pay the cost of a Capital.com login round-trip.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import (
    AccountInfo, BrokerInstrument, BrokerOrder, BrokerPosition,
    OrderStatus, PlaceOrderRequest,
)


class BrokerAdapter(ABC):
    """Adapter interface. One instance per (account, request) is fine; adapters
    should NOT hold long-lived state outside of cached sessions."""

    # Subclasses set this to True for live brokers, False for manual/no-op.
    is_automated: bool = False

    def __init__(self, credentials: Optional[dict] = None,
                 display_metadata: Optional[dict] = None,
                 base_url: Optional[str] = None):
        self.credentials = credentials or {}
        self.display_metadata = display_metadata or {}
        self.base_url = base_url

    # ----- liveness / debugging -----
    @abstractmethod
    async def healthcheck(self) -> dict:
        """Return a dict with at least {ok: bool, message: str}."""

    # ----- account / positions -----
    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        ...

    @abstractmethod
    async def list_positions(self) -> List[BrokerPosition]:
        ...

    # ----- orders -----
    @abstractmethod
    async def list_orders(self, status: Optional[OrderStatus] = None) -> List[BrokerOrder]:
        """List orders. status=None means 'open' (PENDING + WORKING)."""

    @abstractmethod
    async def place_order(self, req: PlaceOrderRequest) -> BrokerOrder:
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_ref: str) -> bool:
        ...

    # ----- instruments -----
    @abstractmethod
    async def search_instrument(self, query: str) -> List[BrokerInstrument]:
        """Find instruments by free-text query. Used by admins to discover
        the broker's epic for a stock during ticker mapping."""

    async def aclose(self) -> None:
        """Release any held connections. Default no-op; override if needed."""
        return None
