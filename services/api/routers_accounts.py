"""/accounts/* — user-owned trading account management."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db import Broker, TradingAccount, User
from brokers.crypto import encrypt_credentials, CryptoConfigError

from .auth import get_current_user, get_db


router = APIRouter(prefix="/accounts", tags=["accounts"])
_GATEWAY_URL = os.environ.get("BROKER_GATEWAY_URL", "http://broker_gateway:8004")


class TradingAccountIn(BaseModel):
    broker_code: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=120)
    currency: Optional[str] = Field(None, max_length=8)
    credentials: dict[str, Any] = Field(default_factory=dict)
    display_metadata: dict[str, Any] = Field(default_factory=dict)


class TradingAccountOut(BaseModel):
    id: int
    broker_code: str
    broker_name: str
    broker_kind: str
    label: str
    currency: Optional[str]
    is_active: bool
    last_connect_status: Optional[str]
    last_connect_error: Optional[str]
    last_connect_at: Optional[datetime]
    display_metadata: dict[str, Any]


class BrokerOut(BaseModel):
    id: int
    code: str
    name: str
    kind: str
    docs_url: Optional[str]
    credential_schema: list


def _to_out(acct: TradingAccount, broker: Broker) -> TradingAccountOut:
    return TradingAccountOut(
        id=acct.id, broker_code=broker.code, broker_name=broker.name,
        broker_kind=broker.kind, label=acct.label, currency=acct.currency,
        is_active=acct.is_active,
        last_connect_status=acct.last_connect_status,
        last_connect_error=acct.last_connect_error,
        last_connect_at=acct.last_connect_at,
        display_metadata=acct.display_metadata or {},
    )


def _validate_credentials(broker: Broker, creds: dict) -> None:
    schema = broker.credential_schema or []
    missing: list[str] = []
    for field in schema:
        if not field.get("required"):
            continue
        key = field.get("key")
        val = creds.get(key) if key else None
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field.get("label") or key or "?")
    if missing:
        raise HTTPException(400, f"Missing required fields: {', '.join(missing)}")


@router.get("/brokers", response_model=list[BrokerOut])
def list_brokers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(
        select(Broker).where(Broker.is_enabled.is_(True)).order_by(Broker.name)
    ).scalars().all()
    return [BrokerOut(
        id=b.id, code=b.code, name=b.name, kind=b.kind,
        docs_url=b.docs_url, credential_schema=b.credential_schema or [],
    ) for b in rows]


@router.get("", response_model=list[TradingAccountOut])
def list_my_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(TradingAccount, Broker)
        .join(Broker, TradingAccount.broker_id == Broker.id)
        .where(TradingAccount.user_id == user.id)
        .order_by(TradingAccount.created_at.desc())
    ).all()
    return [_to_out(acct, broker) for acct, broker in rows]


@router.post("", response_model=TradingAccountOut)
def create_account(
    body: TradingAccountIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    broker = db.execute(
        select(Broker).where(Broker.code == body.broker_code, Broker.is_enabled.is_(True))
    ).scalar_one_or_none()
    if broker is None:
        raise HTTPException(404, f"Unknown broker '{body.broker_code}'")
    _validate_credentials(broker, body.credentials)

    cipher: Optional[bytes] = None
    nonce: Optional[bytes] = None
    if broker.kind == "automated":
        try:
            cipher, nonce = encrypt_credentials(body.credentials)
        except CryptoConfigError as e:
            raise HTTPException(500, str(e))

    acct = TradingAccount(
        user_id=user.id, broker_id=broker.id, label=body.label,
        currency=body.currency, credentials_encrypted=cipher, credentials_nonce=nonce,
        display_metadata=body.display_metadata,
        is_active=True,
    )
    db.add(acct)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(409, f"Could not create account (label may already exist): {e}")
    db.refresh(acct)
    return _to_out(acct, broker)


@router.delete("/{account_id}")
def delete_account(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    db.delete(acct)
    db.commit()
    return {"deleted": account_id}


@router.post("/{account_id}/test")
async def test_connection(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{_GATEWAY_URL}/accounts/{account_id}/test")
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"broker_gateway unreachable: {e}")


@router.get("/{account_id}/info")
async def get_account_info(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = db.get(TradingAccount, account_id)
    if acct is None or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{_GATEWAY_URL}/accounts/{account_id}/info")
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"broker_gateway unreachable: {e}")
