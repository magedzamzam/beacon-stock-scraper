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
from .routers_accounts import router as accounts_router
from .routers_orders import (
    orders_router, positions_router, instruments_router,
)
from .routers_stats import stats_router
from .routers_settings import settings_router
from .routers_ai import router as ai_router
from .routers_alerts import alerts_router
from .routers_trading_bot import trading_bot_router
from .routers_broker_quotes import broker_quotes_router

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
# IMPORTANT: broker_quotes_router uses /stocks/{stock_id}/* routes which would
# otherwise be shadowed by stocks_router's /stocks/{exchange}/{ticker}. Register
# it FIRST so FastAPI matches it before the wildcard.
app.include_router(broker_quotes_router)
app.include_router(stocks_router)
app.include_router(watchlists_router)
app.include_router(portfolio_router)
app.include_router(accounts_router)
app.include_router(orders_router)
app.include_router(positions_router)
app.include_router(instruments_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(ai_router)
app.include_router(alerts_router)
app.include_router(trading_bot_router)
app.include_router(admin_router)
