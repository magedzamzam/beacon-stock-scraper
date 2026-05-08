-- =============================================================================
-- Migration 005: Live broker quotes
-- =============================================================================
-- Idempotent. Safe to re-run.
--
-- stock_broker_quotes -- one row per (stock_id, broker_id, broker_symbol)
--   captures the latest live price snapshot from a broker (Capital.com etc).
--   Refreshed hourly by the scheduler and on-demand from the stock detail page.
--   We keep it as a single 'latest' per pair (UPSERT on the natural key) to
--   avoid bloating the DB. Need history? Use stock_market_daily for EoD.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.stock_broker_quotes (
    id            bigserial    PRIMARY KEY,
    stock_id      bigint       NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    broker_id     bigint       NOT NULL REFERENCES public.brokers(id) ON DELETE CASCADE,
    broker_symbol varchar(64)  NOT NULL,
    bid           numeric(20, 6),
    offer         numeric(20, 6),    -- aka ask
    last_price    numeric(20, 6),    -- mid or last-trade depending on broker
    open_price    numeric(20, 6),
    high_price    numeric(20, 6),
    low_price     numeric(20, 6),
    close_price   numeric(20, 6),    -- previous close
    change_abs    numeric(20, 6),
    change_pct    numeric(12, 6),
    volume        numeric(24, 4),
    currency      varchar(8),
    market_status varchar(32),
    raw           jsonb,             -- entire broker payload for debugging
    fetched_at    timestamp    NOT NULL DEFAULT now(),
    UNIQUE (stock_id, broker_id)
);

CREATE INDEX IF NOT EXISTS ix_stock_broker_quotes_stock
    ON public.stock_broker_quotes (stock_id);

CREATE INDEX IF NOT EXISTS ix_stock_broker_quotes_fetched
    ON public.stock_broker_quotes (fetched_at DESC);


-- Seed the 5th scheduled job: hourly broker quote refresh
INSERT INTO public.app_settings (key, value, description) VALUES
    (
        'job.broker_quote_refresh',
        '{"enabled":true,"cron":"5 * * * *","exchanges":[],"description":"Refresh live broker quotes for stocks with a broker mapping"}'::jsonb,
        'Hourly broker quote refresh — pulls latest bid/offer/OHLC from Capital.com for mapped stocks.'
    )
ON CONFLICT (key) DO NOTHING;

COMMIT;
