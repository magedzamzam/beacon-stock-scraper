-- =============================================================================
-- Migration 011: Earnings calendar + share-structure columns.
-- =============================================================================
-- Adds:
--   * Four share-structure columns on stock_fin_statement:
--       shares_change_yoy, shares_change_qoq        (period-over-period dilution)
--       shares_insiders_pct, shares_institutional_pct (ownership concentration)
--     These describe capital structure at the time of the report. Slow-moving
--     (quarterly), so they live alongside the rest of the period snapshot.
--
--   * A new stock_earnings_calendar table:
--       one row per stock holding the latest known earnings dates +
--       intra-day timing (Before Open / After Close / During Market). Indexed
--       on next_earnings_date for the screener filter
--       ("earnings within N days").
--
-- Idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Share-structure columns on stock_fin_statement
-- ---------------------------------------------------------------------------
ALTER TABLE public.stock_fin_statement
    ADD COLUMN IF NOT EXISTS shares_change_yoy         NUMERIC(12, 6),
    ADD COLUMN IF NOT EXISTS shares_change_qoq         NUMERIC(12, 6),
    ADD COLUMN IF NOT EXISTS shares_insiders_pct       NUMERIC(12, 6),
    ADD COLUMN IF NOT EXISTS shares_institutional_pct  NUMERIC(12, 6);

COMMENT ON COLUMN public.stock_fin_statement.shares_change_yoy IS
    'Year-over-year change in shares outstanding, as percent. Negative = buyback.';
COMMENT ON COLUMN public.stock_fin_statement.shares_change_qoq IS
    'Quarter-over-quarter change in shares outstanding, as percent.';
COMMENT ON COLUMN public.stock_fin_statement.shares_insiders_pct IS
    'Pct of shares held by insiders. Retail % is derived: 100 - insiders - institutional.';
COMMENT ON COLUMN public.stock_fin_statement.shares_institutional_pct IS
    'Pct of shares held by institutional investors.';

-- ---------------------------------------------------------------------------
-- 2. Earnings calendar — one row per stock
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stock_earnings_calendar (
    stock_id              BIGINT       PRIMARY KEY
                                       REFERENCES public.stocks(id) ON DELETE CASCADE,
    last_earnings_date    DATE,
    next_earnings_date    DATE,
    earnings_time         VARCHAR(16),    -- Before Open | After Close | During Market | (null)
    est_revenue           NUMERIC(24, 4),
    est_revenue_growth_pct NUMERIC(12, 6),
    est_eps               NUMERIC(18, 6),
    -- Bookkeeping
    source                VARCHAR(32)  DEFAULT 'bulk_import',
    updated_at            TIMESTAMP    NOT NULL DEFAULT now()
);

-- Index for the screener filter — both upcoming (next > today) and
-- recent (last >= today - N). A composite isn't necessary because the
-- filter usually targets one of these columns at a time.
CREATE INDEX IF NOT EXISTS ix_stock_earnings_next
    ON public.stock_earnings_calendar (next_earnings_date)
    WHERE next_earnings_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_stock_earnings_last
    ON public.stock_earnings_calendar (last_earnings_date)
    WHERE last_earnings_date IS NOT NULL;

COMMENT ON TABLE public.stock_earnings_calendar IS
    'Latest known earnings calendar per stock — last reported date, next expected date, '
    'intra-day timing, and analyst estimates for the next event. Populated by the bulk '
    'CSV importer; one row per stock (UPSERT).';

COMMIT;
