"""Capital.com adapter — async, idiomatic.

Wraps the Capital.com REST API per the v1 documentation:
  https://capital.com/en-ae/trading-platforms/api-development-guide
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, List, Optional

import httpx

from ..adapter_base import BrokerAdapter
from ..types import (
    AccountInfo, AuthError, BrokerError, BrokerInstrument, BrokerOrder,
    BrokerPosition, BrokerQuote, Direction, NetworkError, NotFoundError, OrderSide,
    OrderStatus, OrderType, PlaceOrderRequest, RateLimitError, to_dec,
)


_LIVE_HOST = "api-capital.backend-capital.com"
_DEMO_HOST = "demo-api-capital.backend-capital.com"
_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _map_status(capital_status: str) -> OrderStatus:
    s = (capital_status or "").upper()
    if s in ("ACCEPTED", "FILLED", "EXECUTED"):
        return OrderStatus.FILLED
    if s in ("REJECTED", "ERROR"):
        return OrderStatus.REJECTED
    if s in ("CANCELLED", "DELETED"):
        return OrderStatus.CANCELLED
    if s in ("OPEN", "WORKING", "PENDING_OPEN"):
        return OrderStatus.WORKING
    return OrderStatus.PENDING


class CapitalComAdapter(BrokerAdapter):
    is_automated = True

    def __init__(self, credentials=None, display_metadata=None, base_url=None):
        super().__init__(credentials, display_metadata, base_url)
        self._cst: Optional[str] = None
        self._sec_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._session_lock = asyncio.Lock()

    @property
    def _host(self) -> str:
        if self.base_url:
            return self.base_url
        if bool(self.credentials.get("is_demo")):
            return _DEMO_HOST
        return _LIVE_HOST

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"https://{self._host}",
                timeout=_DEFAULT_TIMEOUT,
                headers={"User-Agent": "beacon-screener/1.0"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_session(self) -> None:
        if self._cst and self._sec_token:
            return
        async with self._session_lock:
            if self._cst and self._sec_token:
                return
            client = await self._get_client()
            try:
                resp = await client.post(
                    "/api/v1/session",
                    json={
                        "identifier": self.credentials.get("account_username", ""),
                        "password": self.credentials.get("account_password", ""),
                    },
                    headers={"X-CAP-API-KEY": self.credentials.get("api_key", "")},
                )
            except httpx.RequestError as exc:
                raise NetworkError(f"Capital.com unreachable: {exc}") from exc

            if resp.status_code == 401:
                raise AuthError("Capital.com rejected the credentials")
            if resp.status_code == 429:
                raise RateLimitError("Capital.com rate-limited the session call")
            if resp.status_code >= 400:
                raise BrokerError(f"Session failed: HTTP {resp.status_code} {resp.text[:200]}")

            cst = resp.headers.get("CST")
            sec = resp.headers.get("X-SECURITY-TOKEN")
            if not cst or not sec:
                raise AuthError("Capital.com session response missing CST/X-SECURITY-TOKEN")
            self._cst = cst
            self._sec_token = sec

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._sec_token or "",
            "Content-Type": "application/json",
        }

    async def _request(self, method, path, json=None, params=None, _retry_on_401=True):
        await self._ensure_session()
        client = await self._get_client()
        try:
            resp = await client.request(method, path, json=json, params=params, headers=self._auth_headers())
        except httpx.RequestError as exc:
            raise NetworkError(f"Capital.com network error: {exc}") from exc

        if resp.status_code == 401 and _retry_on_401:
            self._cst = None
            self._sec_token = None
            return await self._request(method, path, json=json, params=params, _retry_on_401=False)
        if resp.status_code == 404:
            raise NotFoundError(f"Capital.com 404 on {path}")
        if resp.status_code == 429:
            raise RateLimitError("Capital.com rate-limited")
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:300]
            raise BrokerError(f"Capital.com {resp.status_code}: {detail}")

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return resp.text

    async def healthcheck(self) -> dict:
        try:
            info = await self.get_account_info()
            return {"ok": True, "message": f"connected as {info.account_id}",
                    "currency": info.currency,
                    "balance": str(info.balance) if info.balance is not None else None}
        except AuthError as e:
            return {"ok": False, "message": f"auth failed: {e}"}
        except BrokerError as e:
            return {"ok": False, "message": str(e)}

    async def get_account_info(self) -> AccountInfo:
        data = await self._request("GET", "/api/v1/accounts")
        accounts = data.get("accounts") or []
        if not accounts:
            raise NotFoundError("Capital.com returned no accounts")
        a = accounts[0]
        bal = a.get("balance") or {}
        return AccountInfo(
            account_id=str(a.get("accountId") or ""),
            balance=to_dec(bal.get("balance")),
            available=to_dec(bal.get("available")),
            currency=bal.get("currency") or a.get("currency"),
            raw=a,
        )

    async def list_positions(self) -> List[BrokerPosition]:
        data = await self._request("GET", "/api/v1/positions")
        out: List[BrokerPosition] = []
        for p in data.get("positions", []):
            pos = p.get("position") or {}
            mkt = p.get("market") or {}
            direction = (pos.get("direction") or "BUY").upper()
            out.append(BrokerPosition(
                broker_symbol=str(mkt.get("epic") or pos.get("epic") or ""),
                quantity=to_dec(pos.get("size")) or Decimal("0"),
                avg_open_price=to_dec(pos.get("level")),
                current_price=to_dec(mkt.get("bid") if direction == "BUY" else mkt.get("offer")),
                unrealized_pl=to_dec(pos.get("upl") or pos.get("profit")),
                unrealized_pl_pct=None,
                currency=pos.get("currency") or mkt.get("currency"),
                direction=Direction.LONG if direction == "BUY" else Direction.SHORT,
                raw=p,
            ))
        return out

    async def list_orders(self, status: Optional[OrderStatus] = None) -> List[BrokerOrder]:
        data = await self._request("GET", "/api/v1/workingorders")
        out: List[BrokerOrder] = []
        for w in data.get("workingOrders", []):
            wo = w.get("workingOrderData") or {}
            mkt = w.get("marketData") or {}
            side = OrderSide.BUY if (wo.get("direction") or "").upper() == "BUY" else OrderSide.SELL
            ot_raw = (wo.get("orderType") or "LIMIT").upper()
            ot = OrderType.LIMIT if ot_raw == "LIMIT" else (OrderType.STOP if ot_raw == "STOP" else OrderType.MARKET)
            out.append(BrokerOrder(
                broker_order_ref=str(wo.get("dealId") or ""),
                broker_symbol=str(wo.get("epic") or mkt.get("epic") or ""),
                side=side, order_type=ot,
                quantity=to_dec(wo.get("orderSize")) or Decimal("0"),
                limit_price=to_dec(wo.get("orderLevel")),
                stop_loss=to_dec(wo.get("stopLevel")),
                take_profit=to_dec(wo.get("limitLevel")),
                status=OrderStatus.WORKING,
                currency=wo.get("currencyCode") or mkt.get("currency"),
                raw=w,
            ))
        if status is not None:
            out = [o for o in out if o.status == status]
        return out

    async def place_order(self, req: PlaceOrderRequest) -> BrokerOrder:
        if req.order_type == OrderType.MARKET:
            payload = {"epic": req.broker_symbol, "direction": req.side.value, "size": float(req.quantity)}
            if req.stop_loss is not None: payload["stopLevel"] = float(req.stop_loss)
            if req.take_profit is not None: payload["profitLevel"] = float(req.take_profit)
            data = await self._request("POST", "/api/v1/positions", json=payload)
        else:
            ot = "LIMIT" if req.order_type == OrderType.LIMIT else "STOP"
            level = req.limit_price
            if level is None:
                raise BrokerError("limit_price is required for LIMIT/STOP orders")
            payload = {
                "epic": req.broker_symbol, "direction": req.side.value, "size": float(req.quantity),
                "type": ot, "level": float(level),
            }
            if req.stop_loss is not None: payload["stopLevel"] = float(req.stop_loss)
            if req.take_profit is not None: payload["profitLevel"] = float(req.take_profit)
            data = await self._request("POST", "/api/v1/workingorders", json=payload)

        deal_ref = data.get("dealReference")
        if not deal_ref:
            raise BrokerError(f"Capital.com place_order missing dealReference: {data}")

        confirm = await self._request("GET", f"/api/v1/confirms/{deal_ref}")
        status = _map_status(confirm.get("status") or confirm.get("dealStatus"))
        return BrokerOrder(
            broker_order_ref=str(confirm.get("dealId") or deal_ref),
            broker_symbol=str(confirm.get("epic") or req.broker_symbol),
            side=req.side, order_type=req.order_type,
            quantity=to_dec(confirm.get("size")) or req.quantity,
            limit_price=req.limit_price,
            stop_loss=to_dec(confirm.get("stopLevel") or req.stop_loss),
            take_profit=to_dec(confirm.get("profitLevel") or req.take_profit),
            status=status,
            fill_price=to_dec(confirm.get("level")),
            fill_quantity=to_dec(confirm.get("size")) if status == OrderStatus.FILLED else None,
            currency=confirm.get("currency"),
            rejection_reason=confirm.get("reason") if status == OrderStatus.REJECTED else None,
            raw=confirm,
        )

    async def cancel_order(self, broker_order_ref: str) -> bool:
        try:
            data = await self._request("DELETE", f"/api/v1/workingorders/{broker_order_ref}")
            ref = data.get("dealReference")
            if not ref:
                return False
            confirm = await self._request("GET", f"/api/v1/confirms/{ref}")
            return _map_status(confirm.get("status")) == OrderStatus.CANCELLED
        except NotFoundError:
            return False

    async def search_instrument(self, query: str) -> List[BrokerInstrument]:
        data = await self._request("GET", "/api/v1/markets", params={"searchTerm": query})
        out: List[BrokerInstrument] = []
        for m in data.get("markets", []):
            out.append(BrokerInstrument(
                broker_symbol=str(m.get("epic") or ""),
                name=str(m.get("instrumentName") or m.get("epic") or ""),
                instrument_type=m.get("instrumentType"),
                currency=m.get("currency"),
                min_qty=to_dec(m.get("minDealSize")),
            ))
        return out

    async def get_quote(self, broker_symbol: str) -> BrokerQuote:
        """Live quote for one Capital.com epic.

        GET /api/v1/markets/{epic} returns 'instrument' (metadata) and
        'snapshot' (the live block). We pull both into a BrokerQuote.
        """
        if not broker_symbol:
            raise BrokerError("broker_symbol (epic) is required")
        data = await self._request("GET", f"/api/v1/markets/{broker_symbol}")
        snap = data.get("snapshot") or {}
        instr = data.get("instrument") or {}

        bid = to_dec(snap.get("bid"))
        offer = to_dec(snap.get("offer"))
        # Mid is a reasonable 'last' for spot markets when no last-trade is given.
        last = None
        if bid is not None and offer is not None:
            last = (bid + offer) / Decimal(2)

        # Capital.com gives netChange (absolute) and percentageChange. Derive
        # the previous close from last - netChange when both are present.
        net_change = to_dec(snap.get("netChange"))
        prev_close = None
        if last is not None and net_change is not None:
            prev_close = last - net_change

        return BrokerQuote(
            broker_symbol=broker_symbol,
            bid=bid, offer=offer, last_price=last,
            high_price=to_dec(snap.get("high")),
            low_price=to_dec(snap.get("low")),
            close_price=prev_close,
            change_abs=net_change,
            change_pct=to_dec(snap.get("percentageChange")),
            currency=instr.get("currency"),
            market_status=snap.get("marketStatus"),
            raw=data,
        )
