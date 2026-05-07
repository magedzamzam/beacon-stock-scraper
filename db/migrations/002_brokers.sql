-- =============================================================================
-- Migration 002: Multi-broker trading integration
-- =============================================================================
-- Adds the schema needed to support:
--   * Multiple broker integrations (Capital.com, Thndr, ...) per user
--   * Encrypted credential storage for automated brokers
--   * Symbol mapping from broker-native epics to our stocks table
--   * Order placement (live + manual) with full audit trail
--   * Periodic snapshots of broker-reported positions
--
-- Design notes:
--   * brokers row defines the *kind* of broker (registry). One row per protocol.
--   * trading_accounts is per-user and per-broker. Users can have multiple
--     accounts of the same broker (e.g. live + demo on Capital.com).
--   * broker_instruments maps (broker, broker_symbol) <-> stocks.id when the
--     broker actually carries that stock. NULL stock_id is allowed for
--     instruments the broker offers but we don't track (commodities, FX).
--   * broker_orders is the canonical order log for *all* accounts. For manual
--     accounts these are user-entered records; for automated they originate
--     from API calls with a broker_order_ref linking back to the broker.
--   * broker_positions_snapshot is a periodically-refreshed view of the
--     broker's reported positions, used to surface drift vs. our local math.
-- =============================================================================

BEGIN;

-- ---------- 1. Broker registry --------------------------------------------
-- The kind column drives runtime behavior:
--   'automated' = we connect to an API to place/track orders
--   'manual'    = user enters trades they made elsewhere; we just track them
--
-- adapter_class is the Python class name in services/brokers/adapters/ that
-- implements the BrokerAdapter interface for this broker. Adding a new
-- broker = inserting a row + dropping a class.

CREATE TABLE IF NOT EXISTS public.brokers (
    id                bigserial PRIMARY KEY,
    code              varchar(32)  UNIQUE NOT NULL,           -- 'capital_com', 'thndr', 'manual_generic'
    name              varchar(120) NOT NULL,                  -- 'Capital.com'
    kind              varchar(16)  NOT NULL CHECK (kind IN ('automated', 'manual')),
    adapter_class     varchar(120) NOT NULL,                  -- 'CapitalComAdapter'
    base_url          varchar(255),                           -- API host, e.g. 'api-capital.backend-capital.com'
    docs_url          varchar(255),
    -- credential_schema documents which fields the adapter needs.
    -- Used by the UI to render the right form. Example:
    --   [{"key":"account_username","label":"Email","type":"email","required":true},
    --    {"key":"account_password","label":"Password","type":"password","required":true},
    --    {"key":"api_key","label":"API key","type":"password","required":true}]
    credential_schema jsonb        NOT NULL DEFAULT '[]'::jsonb,
    is_enabled        boolean      NOT NULL DEFAULT true,
    created_at        timestamp    NOT NULL DEFAULT now()
);

-- Seed the brokers we know about today. Future brokers go in similar inserts.
INSERT INTO public.brokers (code, name, kind, adapter_class, base_url, docs_url, credential_schema)
VALUES
  ('capital_com', 'Capital.com', 'automated', 'CapitalComAdapter',
   'api-capital.backend-capital.com',
   'https://capital.com/en-ae/trading-platforms/api-development-guide',
   '[{"key":"account_username","label":"Account email","type":"email","required":true},
     {"key":"account_password","label":"Password","type":"password","required":true},
     {"key":"api_key","label":"API key","type":"password","required":true},
     {"key":"is_demo","label":"Demo account","type":"boolean","required":false,"default":false}]'::jsonb),
  ('thndr', 'Thndr', 'manual', 'ManualAdapter', NULL,
   'https://thndr.com/',
   '[{"key":"display_account_id","label":"Thndr account ID (optional)","type":"text","required":false}]'::jsonb),
  ('manual_generic', 'Other (manual)', 'manual', 'ManualAdapter', NULL, NULL,
   '[{"key":"broker_name","label":"Broker name","type":"text","required":true},
     {"key":"display_account_id","label":"Account ID (optional)","type":"text","required":false}]'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- ---------- 2. Trading accounts -------------------------------------------
-- One row per (user, broker, label). credentials_encrypted holds AES-GCM
-- ciphertext of a JSON blob; the encryption key lives only in the
-- broker_gateway container's env, never in the DB.
--
-- last_connect_status and last_connect_error give the UI something to render
-- without needing to actually contact the broker on every page load.

CREATE TABLE IF NOT EXISTS public.trading_accounts (
    id                       bigserial PRIMARY KEY,
    user_id                  bigint    NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    broker_id                bigint    NOT NULL REFERENCES public.brokers(id) ON DELETE RESTRICT,
    label                    varchar(120) NOT NULL,                       -- 'Capital live', 'Thndr real'
    currency                 varchar(8),                                  -- account base currency, e.g. 'USD'
    -- Encrypted JSON blob of credentials. NULL for manual accounts.
    credentials_encrypted    bytea,
    -- IV/nonce used for AES-GCM. 12 bytes.
    credentials_nonce        bytea,
    -- non-secret display fields the user typed (e.g. Thndr account ID)
    display_metadata         jsonb     NOT NULL DEFAULT '{}'::jsonb,
    is_active                boolean   NOT NULL DEFAULT true,
    last_connect_status      varchar(16),                                 -- 'ok','auth_failed','network_error',NULL
    last_connect_error       text,
    last_connect_at          timestamp,
    created_at               timestamp NOT NULL DEFAULT now(),
    updated_at               timestamp NOT NULL DEFAULT now(),
    UNIQUE (user_id, broker_id, label)
);

CREATE INDEX IF NOT EXISTS ix_trading_accounts_user
    ON public.trading_accounts (user_id, is_active);

-- ---------- 3. Broker instruments (symbol mapping) ------------------------
-- For each (broker, broker_symbol) we record:
--   * the broker's display name for the instrument
--   * an optional FK to our stocks table (if it's something we screen)
--   * is_tradeable so admins can disable a mapping without deleting it
--
-- The same broker_symbol can map to a stock OR to no stock at all (e.g.
-- "GOLD" on Capital.com — tradeable, but not in our screener).
--
-- Lookups go both ways:
--   stock_id -> list of (broker, broker_symbol) the stock is tradeable on
--   (broker, broker_symbol) -> stock_id, if any

CREATE TABLE IF NOT EXISTS public.broker_instruments (
    id                bigserial PRIMARY KEY,
    broker_id         bigint    NOT NULL REFERENCES public.brokers(id) ON DELETE CASCADE,
    broker_symbol     varchar(64) NOT NULL,                                -- Capital.com epic, e.g. 'AAPL', 'GOLD'
    broker_name       varchar(255),                                        -- broker's display name
    instrument_type   varchar(32),                                         -- 'STOCK','COMMODITY','FX','CRYPTO','INDEX'
    stock_id          bigint REFERENCES public.stocks(id) ON DELETE SET NULL,
    currency          varchar(8),                                          -- the broker's quote currency for it
    min_qty           numeric(20, 6),                                      -- broker minimum dealing size, when known
    is_tradeable      boolean   NOT NULL DEFAULT true,
    created_at        timestamp NOT NULL DEFAULT now(),
    updated_at        timestamp NOT NULL DEFAULT now(),
    UNIQUE (broker_id, broker_symbol)
);

CREATE INDEX IF NOT EXISTS ix_broker_instruments_stock
    ON public.broker_instruments (stock_id) WHERE stock_id IS NOT NULL;

-- ---------- 4. Broker orders ----------------------------------------------
-- Single audit log for every order placed through any account, automated or
-- manual. Manual accounts get rows here too — that's how a user records
-- "I bought 100 shares on Thndr yesterday at 12.34". When account is
-- automated, broker_order_ref links back to the broker's deal id.
--
-- We deliberately keep status simple: PENDING (just submitted), WORKING
-- (sitting on broker's book — limit orders), FILLED, CANCELLED, REJECTED.
-- Manual orders go straight to FILLED.

CREATE TABLE IF NOT EXISTS public.broker_orders (
    id                bigserial PRIMARY KEY,
    account_id        bigint    NOT NULL REFERENCES public.trading_accounts(id) ON DELETE CASCADE,
    user_id           bigint    NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    stock_id          bigint REFERENCES public.stocks(id) ON DELETE SET NULL,
    -- broker_symbol is denormalized so manual orders + non-stock instruments
    -- still have meaningful data even if stock_id is null.
    broker_symbol     varchar(64),
    side              varchar(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type        varchar(8) NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP')),
    quantity          numeric(20, 6) NOT NULL CHECK (quantity > 0),
    limit_price       numeric(20, 6),
    stop_loss         numeric(20, 6),
    take_profit       numeric(20, 6),
    -- prices are in the *broker's* quote currency for that instrument
    currency          varchar(8),
    -- For automated orders, broker_order_ref is the broker's deal reference.
    -- For manual orders this stays NULL.
    broker_order_ref  varchar(120),
    status            varchar(16) NOT NULL DEFAULT 'PENDING'
                          CHECK (status IN ('PENDING','WORKING','FILLED','CANCELLED','REJECTED')),
    fill_price        numeric(20, 6),
    fill_quantity     numeric(20, 6),
    rejection_reason  text,
    notes             text,
    placed_at         timestamp NOT NULL DEFAULT now(),
    filled_at         timestamp,
    last_synced_at    timestamp,
    created_at        timestamp NOT NULL DEFAULT now(),
    updated_at        timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_broker_orders_account
    ON public.broker_orders (account_id, status, placed_at DESC);

CREATE INDEX IF NOT EXISTS ix_broker_orders_user_recent
    ON public.broker_orders (user_id, placed_at DESC);

CREATE INDEX IF NOT EXISTS ix_broker_orders_broker_ref
    ON public.broker_orders (broker_order_ref) WHERE broker_order_ref IS NOT NULL;

-- ---------- 5. Broker positions snapshot ----------------------------------
-- Cache of "what the broker says we hold right now" for AUTOMATED accounts.
-- Refreshed when the user opens the portfolio page (with a 60s freshness
-- cap to avoid hammering the broker's API on every render). For manual
-- accounts we don't snapshot — the user IS the source of truth, and the
-- portfolio_positions table already serves that role.

CREATE TABLE IF NOT EXISTS public.broker_positions_snapshot (
    id                bigserial PRIMARY KEY,
    account_id        bigint    NOT NULL REFERENCES public.trading_accounts(id) ON DELETE CASCADE,
    stock_id          bigint REFERENCES public.stocks(id) ON DELETE SET NULL,
    broker_symbol     varchar(64) NOT NULL,
    quantity          numeric(20, 6) NOT NULL,
    avg_open_price    numeric(20, 6),
    current_price     numeric(20, 6),
    unrealized_pl     numeric(20, 6),
    unrealized_pl_pct numeric(8, 4),
    currency          varchar(8),
    direction         varchar(8) CHECK (direction IN ('LONG','SHORT')),
    -- raw is the broker's response payload, kept for debugging / future fields
    raw               jsonb,
    fetched_at        timestamp NOT NULL DEFAULT now(),
    UNIQUE (account_id, broker_symbol)
);

CREATE INDEX IF NOT EXISTS ix_broker_positions_account
    ON public.broker_positions_snapshot (account_id, fetched_at DESC);

-- ---------- 6. Link manual portfolio_positions to a trading account ------
-- Existing portfolio_positions rows pre-date trading accounts. We add an
-- optional FK so going forward each manual position is attached to one
-- specific manual trading account. NULL means "legacy / unattached".

ALTER TABLE public.portfolio_positions
    ADD COLUMN IF NOT EXISTS account_id bigint
        REFERENCES public.trading_accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_portfolio_positions_account
    ON public.portfolio_positions (account_id);

-- ---------- 7. updated_at triggers (keep timestamps honest) ---------------
-- Postgres doesn't auto-update updated_at; we add a small trigger function
-- and attach it to the new tables. If your existing tables already have a
-- trigger function with the same name, this is a no-op replace.

CREATE OR REPLACE FUNCTION public.set_updated_at_now()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_trading_accounts_updated_at ON public.trading_accounts;
CREATE TRIGGER trg_trading_accounts_updated_at
    BEFORE UPDATE ON public.trading_accounts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();

DROP TRIGGER IF EXISTS trg_broker_instruments_updated_at ON public.broker_instruments;
CREATE TRIGGER trg_broker_instruments_updated_at
    BEFORE UPDATE ON public.broker_instruments
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();

DROP TRIGGER IF EXISTS trg_broker_orders_updated_at ON public.broker_orders;
CREATE TRIGGER trg_broker_orders_updated_at
    BEFORE UPDATE ON public.broker_orders
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();

COMMIT;
