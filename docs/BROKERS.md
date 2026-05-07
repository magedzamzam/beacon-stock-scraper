# Multi-broker integration

Beacon supports two flavours of trading account:

- **Automated brokers** (Capital.com today; Crypto.com / OKX / Equiti slot in the same way later) — Beacon connects to the broker's API to place orders, list positions, and pull account balances.
- **Manual brokers** (Thndr, "Other") — the user records trades they make elsewhere; Beacon tracks the positions in `portfolio_positions` / `broker_orders` but doesn't talk to anyone.

## Architecture

```
                                   nginx
                                     │
                                     ▼
                                +--------+
                       /api/*   |  api   | ──── /accounts, /orders, /instruments
                                +---┬----+
                                    │  internal HTTP (Docker network)
                                    ▼
                          +-------------------+
                          |  broker_gateway   |  (only service that decrypts creds)
                          +---------┬---------+
                                    │
                          ┌─────────┴──────────┐
                          ▼                    ▼
              CapitalComAdapter         ManualAdapter (no-op)
                          │
                          ▼
                  Capital.com REST API
```

### Why a separate service for `broker_gateway`

- **Secrets isolation.** `BROKER_SECRET_KEY` is mounted only into this container.
- **Failure isolation.** A Capital.com outage doesn't tank the screener API.
- **Clean home for future WebSocket position streams and webhook receivers.**

## Adding a new broker

1. Create `services/brokers/adapters/yourbroker.py` implementing `BrokerAdapter`.
2. Register it in `services/brokers/registry.py`.
3. `INSERT INTO brokers (code, name, kind, adapter_class, ...)` — UI picks it up automatically and renders the credential form from `credential_schema`.

## Database tables (migration 002)

| Table | Purpose |
|---|---|
| `brokers` | Registry of broker types we know how to talk to. |
| `trading_accounts` | A user's account at a specific broker. Encrypted credentials. |
| `broker_instruments` | Per-broker symbol mapping ↔ `stocks.id`. |
| `broker_orders` | Audit log for every order, automated or manual. |
| `broker_positions_snapshot` | Cached "what the broker says we hold" for automated accounts. |
| `portfolio_positions` (extended) | Now has an `account_id` FK so manual positions belong to a specific manual account. |

## Deploy steps

```bash
# 1. Generate the encryption key once
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# Put the output into .env as BROKER_SECRET_KEY=...
# IMPORTANT: lose this key and all stored broker credentials are unrecoverable.
# Back it up off-server (password manager).

# 2. Apply the migration
psql "$DATABASE_URL" -f db/migrations/002_brokers.sql

# 3. Build + start
docker compose up -d --build

# 4. Verify the new container is healthy
docker compose ps broker_gateway

# 5. As an end user: add a Capital.com account from /profile and click Test
```

## Testing the Capital.com adapter end-to-end

```bash
# After connecting an account in /profile, check from inside the api container:
docker compose exec api curl -s http://broker_gateway:8004/healthz
# {"ok": true}

docker compose exec api curl -s -X POST http://broker_gateway:8004/accounts/1/test
# {"ok": true, "message": "connected as 12345678", "currency": "USD", "balance": "1000.00"}

docker compose exec api curl -s http://broker_gateway:8004/accounts/1/positions
# [{"broker_symbol":"AAPL","quantity":"100",...}]
```

## Order flow

### Manual account

```
Frontend → POST /api/orders → api inserts directly into broker_orders
   status = FILLED, fill_price = limit_price, no broker call.
```

### Automated account

```
Frontend → POST /api/orders → api forwards to broker_gateway
   → broker_gateway decrypts creds → CapitalComAdapter.place_order
   → broker_gateway writes broker_orders row
   → api returns the result to the frontend
```

## Symbol mapping

Capital.com's instrument set differs from ours (e.g. EGX is not on Capital.com at all). When a user opens "Place order" on a stock detail page, the modal:

1. Loads the user's accounts.
2. Loads broker mappings for that stock from `broker_instruments`.
3. Greys out automated accounts that don't have a mapping.
4. For manual accounts, every stock is tradeable (user just records the trade).

Admins map symbols via the **Map symbol** button on stock detail pages. For automated brokers an inline catalog search calls the broker's API so admins don't need to memorise epics.
