"""Adapter contract every broker integration must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import (
    AccountInfo, BrokerInstrument, BrokerOrder, BrokerPosition, BrokerQuote,
    OrderStatus, PlaceOrderRequest,
)


class BrokerAdapter(ABC):
    is_automated: bool = False

    def __init__(self, credentials: Optional[dict] = None,
                 display_metadata: Optional[dict] = None,
                 base_url: Optional[str] = None):
        self.credentials = credentials or {}
        self.display_metadata = display_metadata or {}
        self.base_url = base_url

    @abstractmethod
    async def healthcheck(self) -> dict: ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo: ...

    @abstractmethod
    async def list_positions(self) -> List[BrokerPosition]: ...

    @abstractmethod
    async def list_orders(self, status: Optional[OrderStatus] = None) -> List[BrokerOrder]: ...

    @abstractmethod
    async def place_order(self, req: PlaceOrderRequest) -> BrokerOrder: ...

    @abstractmethod
    async def cancel_order(self, broker_order_ref: str) -> bool: ...

    @abstractmethod
    async def search_instrument(self, query: str) -> List[BrokerInstrument]: ...

    async def get_quote(self, broker_symbol: str) -> BrokerQuote:
        """Live price snapshot for one instrument.

        Adapters that don't support live quotes (e.g. manual brokers) must
        raise NotImplementedError. This is intentionally not @abstractmethod
        so existing adapters keep working without modification.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support get_quote"
        )

    async def aclose(self) -> None:
        return None
