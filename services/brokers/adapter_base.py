"""Adapter contract every broker integration must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import (
    AccountInfo, BrokerInstrument, BrokerOrder, BrokerPosition, BrokerQuote,
    ClosePositionResult, ModifyOrderRequest, ModifyPositionRequest,
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

    # ----- Position / order MUTATION operations --------------------------
    # These are NOT @abstractmethod by design: a freshly written adapter
    # should at least be able to read positions/orders. Mutating them is
    # a separate capability some brokers may not support (manual broker
    # certainly doesn't). Default = raise NotImplementedError so the
    # gateway can return a clean 501 / "not supported by this broker"
    # error rather than crashing.

    async def modify_position(self, req: ModifyPositionRequest) -> BrokerPosition:
        """Change SL/TP on an OPEN position. Returns the updated position
        as the broker reports it post-modify. Raise NotFoundError if the
        position doesn't exist.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support modify_position"
        )

    async def close_position(
        self, broker_position_ref: str,
        quantity: Optional["Decimal"] = None,   # type: ignore[name-defined]
    ) -> ClosePositionResult:
        """Close a single position by its broker ref.

        If quantity is provided, attempt a partial close (broker permitting).
        If None, close the whole position. Returns ClosePositionResult — the
        boolean alone isn't enough for the UI; we surface the fill price too.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support close_position"
        )

    async def close_all_positions(
        self, broker_symbol: Optional[str] = None,
    ) -> List[ClosePositionResult]:
        """Convenience: close every open position, optionally filtered by symbol.

        Default implementation calls list_positions then close_position in a
        loop. Adapters MAY override if the broker has a more efficient bulk
        endpoint (Capital.com does not — REST API is per-position only).
        """
        positions = await self.list_positions()
        if broker_symbol is not None:
            positions = [p for p in positions if p.broker_symbol == broker_symbol]

        results: List[ClosePositionResult] = []
        for p in positions:
            if not p.broker_position_ref:
                # Skip — can't close what we can't reference. Surface a row
                # with closed=False so the caller can see which were skipped.
                results.append(ClosePositionResult(
                    broker_position_ref="",
                    closed=False,
                    raw={"reason": f"no broker_position_ref on {p.broker_symbol}"},
                ))
                continue
            try:
                result = await self.close_position(p.broker_position_ref)
            except Exception as exc:
                result = ClosePositionResult(
                    broker_position_ref=p.broker_position_ref,
                    closed=False,
                    raw={"error": f"{type(exc).__name__}: {exc}"},
                )
            results.append(result)
        return results

    async def modify_order(self, req: ModifyOrderRequest) -> BrokerOrder:
        """Change levels on a PENDING working order. Use cancel_order to
        remove the order entirely.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support modify_order"
        )

    async def aclose(self) -> None:
        return None
