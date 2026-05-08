-- =============================================================================
-- Migration 003: Admin enhancements + account balance history
-- =============================================================================
-- Idempotent. Safe to re-run.
--
--  1. stocks.is_scraping_enabled -- gate scraper independent of "active"
--     New stocks created via the admin UI default to FALSE so we don't
--     hammer stockanalysis.com on unverified slugs. Existing rows are
--     backfilled to TRUE so current behaviour is preserved.
--
--  2. account_balance_snapshots -- timeseries of broker-reported & manual
--     account stats. Captured periodically by the scheduler AND lazily when
--     the user opens an account view (latest snapshot is freshness-checked).
-- =============================================================================

BEGIN;

-- ---------- 1. Scraping enable flag ---------------------------------------
ALTER TABLE public.stocks
    ADD COLUMN IF NOT EXISTS is_scraping_enabled boolean NOT NULL DEFAULT true;

-- After the column exists, decide on default for *future* rows:
-- existing migration default keeps backwards compat (true). New admin-created
-- rows explicitly pass false at INSERT time (see routers_admin.py).

CREATE INDEX IF NOT EXISTS ix_stocks_scraping_enabled
    ON public.stocks (is_scraping_enabled) WHERE is_scraping_enabled IS TRUE;

-- ---------- 2. Account balance history -----------------------------------
-- One row per (account, capture event). Manual accounts have NULL balance
-- (they're not held at a broker), but DO have equity computed from the
-- mark-to-market sum of their open portfolio_positions.
CREATE TABLE IF NOT EXISTS public.account_balance_snapshots (
    id              bigserial PRIMARY KEY,
    account_id      bigint        NOT NULL REFERENCES public.trading_accounts(id) ON DELETE CASCADE,
    -- Cash held at the broker. NULL for manual accounts.
    balance         numeric(20, 6),
    available       numeric(20, 6),
    -- Equity = balance + sum(unrealized_pl on open positions).
    -- For manual accounts where we don't have cash: equity = sum(qty * mark).
    equity          numeric(20, 6),
    unrealized_pl   numeric(20, 6),
    open_position_count int,
    currency        varchar(8),
    -- 'periodic' for scheduler captures, 'on_demand' for UI-driven captures,
    -- 'event' for captures triggered by a position add/close.
    source          varchar(16)   NOT NULL DEFAULT 'periodic',
    fetched_at      timestamp     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_account_balance_snapshots_account_time
    ON public.account_balance_snapshots (account_id, fetched_at DESC);

COMMIT;
