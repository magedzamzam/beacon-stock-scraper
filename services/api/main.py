"""Beacon public API — main entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.logging_setup import configure_logging
from shared.settings import get_settings

from .routers_admin import router as admin_router
from .routers_auth import router as auth_router
from .routers_portfolio import router as portfolio_router
from .routers_stocks import router as stocks_router
from .routers_watchlists import router as watchlists_router

log = configure_logging("api")
settings = get_settings()

app = FastAPI(
    title="Beacon Screener API",
    version="1.0.0",
    description="DFM / ADX / EGX stock screener with BUY/WATCH/STAY_AWAY signals.",
)

origins = [o.strip() for o in settings.api_cors_origins.split(",")] if settings.api_cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"ok": True}

app.include_router(auth_router)
app.include_router(stocks_router)
app.include_router(watchlists_router)
app.include_router(portfolio_router)
app.include_router(admin_router)
