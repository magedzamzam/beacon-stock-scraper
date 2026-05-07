-- =============================================================================
-- Migration 002: Multi-broker trading integration
-- =============================================================================
-- Idempotent (CREATE IF NOT EXISTS, ON CONFLICT DO NOTHING). Safe to re-run.
-- =============================================================================

BEGIN;

-- ---------- 1. Broker registry --------------------------------------------
CREATE TABLE IF NOT EXISTS public.brokers (
    id                bigserial PRIMARY KEY,
    code              varchar(32)  UNIQUE NOT NULL,
    name              varchar(120) NOT NULL,
    kind              varchar(16)  NOT NULL CHECK (kind IN ('automated', 'manual')),
    adapter_class     varchar(120) NOT NULL,
    base_url          varchar(255),
    docs_url          varchar(255),
    credential_schema jsonb        NOT NULL DEFAULT '[]'::jsonb,
    is_enabled        boolean      NOT NULL DEFAULT true,
    created_at        timestamp    NOT NULL DEFAULT now()
);

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
CREATE TABLE IF NOT EXISTS public.trading_accounts (
    id                       bigserial PRIMARY KEY,
    user_id                  bigint    NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    broker_id                bigint    NOT NULL REFERENCES public.brokers(id) ON DELETE RESTRICT,
    label                    varchar(120) NOT NULL,
    currency                 varchar(8),
    credentials_encrypted    bytea,
    credentials_nonce        bytea,
    display_metadata         jsonb     NOT NULL DEFAULT '{}'::jsonb,
    is_active                boolean   NOT NULL DEFAULT true,
    last_connect_status      varchar(16),
    last_connect_error       text,
    last_connect_at          timestamp,
    created_at               timestamp NOT NULL DEFAULT now(),
    updated_at               timestamp NOT NULL DEFAULT now(),
    UNIQUE (user_id, broker_id, label)
);
CREATE INDEX IF NOT EXISTS ix_trading_accounts_user
    ON public.trading_accounts (user_id, is_active);

-- ---------- 3. Broker instruments (symbol mapping) ------------------------
CREATE TABLE IF NOT EXISTS public.broker_instruments (
    id                bigserial PRIMARY KEY,
    broker_id         bigint    NOT NULL REFERENCES public.brokers(id) ON DELETE CASCADE,
    broker_symbol     varchar(64) NOT NULL,
    broker_name       varchar(255),
    instrument_type   varchar(32),
    stock_id          bigint REFERENCES public.stocks(id) ON DELETE SET NULL,
    currency          varchar(8),
    min_qty           numeric(20, 6),
    is_tradeable      boolean   NOT NULL DEFAULT true,
    created_at        timestamp NOT NULL DEFAULT now(),
    updated_at        timestamp NOT NULL DEFAULT now(),
    UNIQUE (broker_id, broker_symbol)
);
CREATE INDEX IF NOT EXISTS ix_broker_instruments_stock
    ON public.broker_instruments (stock_id) WHERE stock_id IS NOT NULL;

-- ---------- 4. Broker orders ----------------------------------------------
CREATE TABLE IF NOT EXISTS public.broker_orders (
    id                bigserial PRIMARY KEY,
    account_id        bigint    NOT NULL REFERENCES public.trading_accounts(id) ON DELETE CASCADE,
    user_id           bigint    NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    stock_id          bigint REFERENCES public.stocks(id) ON DELETE SET NULL,
    broker_symbol     varchar(64),
    side              varchar(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type        varchar(8) NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP')),
    quantity          numeric(20, 6) NOT NULL CHECK (quantity > 0),
    limit_price       numeric(20, 6),
    stop_loss         numeric(20, 6),
    take_profit       numeric(20, 6),
    currency          varchar(8),
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
    raw               jsonb,
    fetched_at        timestamp NOT NULL DEFAULT now(),
    UNIQUE (account_id, broker_symbol)
);
CREATE INDEX IF NOT EXISTS ix_broker_positions_account
    ON public.broker_positions_snapshot (account_id, fetched_at DESC);

-- ---------- 6. Link manual portfolio_positions to a trading account ------
ALTER TABLE public.portfolio_positions
    ADD COLUMN IF NOT EXISTS account_id bigint
        REFERENCES public.trading_accounts(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_portfolio_positions_account
    ON public.portfolio_positions (account_id);

-- ---------- 7. updated_at triggers ---------------------------------------
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
