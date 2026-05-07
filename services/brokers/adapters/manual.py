"""Manual broker adapter — Thndr, "Other (manual)", anything we don't connect to.

We model these as adapters too so the gateway has one uniform interface.
For manual accounts every read returns empty (the broker_gateway doesn't
talk to Thndr's API), and every "place_order" call should be intercepted
upstream — manual orders are written directly to broker_orders by the API
service. This adapter exists to satisfy the contract and make sure the
gateway never crashes if it's invoked on a manual account by mistake.
"""
from __future__ import annotations

from typing import List, Optional

from ..adapter_base import BrokerAdapter
from ..types import (
    AccountInfo, BrokerError, BrokerInstrument, BrokerOrder, BrokerPosition,
    OrderStatus, PlaceOrderRequest,
)


class ManualAdapter(BrokerAdapter):
    is_automated = False

    async def healthcheck(self) -> dict:
        return {"ok": True, "message": "manual account (no live connection)"}

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            account_id=str(self.display_metadata.get("display_account_id") or "manual"),
            balance=None, available=None, currency=None, raw=None,
        )

    async def list_positions(self) -> List[BrokerPosition]:
        return []

    async def list_orders(self, status: Optional[OrderStatus] = None) -> List[BrokerOrder]:
        return []

    async def place_order(self, req: PlaceOrderRequest) -> BrokerOrder:
        raise BrokerError(
            "Manual accounts don't place live orders. The API service should "
            "record manual trades directly in the broker_orders table."
        )

    async def cancel_order(self, broker_order_ref: str) -> bool:
        return False

    async def search_instrument(self, query: str) -> List[BrokerInstrument]:
        return []
