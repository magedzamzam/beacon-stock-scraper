"""/auth/* — register, login, current user."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from shared.db import User, Watchlist
from .auth import (
    create_access_token, get_current_user, get_db, hash_password, verify_password,
)
from .schemas import AuthResponse, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id, user.email),
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=req.email,
        display_name=req.display_name or req.email.split("@")[0],
        password_hash=hash_password(req.password),
    )
    db.add(user); db.flush()
    db.add(Watchlist(user_id=user.id, name="Default"))
    db.commit(); db.refresh(user)
    return _build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    user.last_login_at = datetime.utcnow()
    db.commit(); db.refresh(user)
    return _build_auth_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
