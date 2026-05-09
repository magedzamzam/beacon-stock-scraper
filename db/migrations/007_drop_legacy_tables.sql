-- =============================================================================
-- Migration 007: Round 4 — drop legacy tables, truncate new ones.
-- =============================================================================
-- DESTRUCTIVE.
--
-- Per the user's request, after this migration:
--   * All new (round-1) tables are TRUNCATEd (data wiped).
--   * All legacy tables that are no longer read or written are DROPped.
--   * The user runs a fresh scrape + broker quote refresh to repopulate
--     the new tables from scratch — proves the system is wired correctly
--     end-to-end with no fallbacks.
--
-- Idempotent. Safe to re-run.
-- =============================================================================

BEGIN;


-- ============================================================================
-- 1. TRUNCATE the new tables — fresh slate.
--    CASCADE drops dependent rows (none today, but future-proofing).
--    RESTART IDENTITY resets bigserial counters.
-- ============================================================================
TRUNCATE TABLE
    public.stock_quotes,
    public.stock_cur_quote,
    public.stock_history_quote,
    public.stock_fin_ratios,
    public.stock_fin_statement,
    public.stock_fin_cashflow,
    public.stock_mkt_dividends,
    public.stock_mkt_technicals,
    public.stock_scoring
RESTART IDENTITY CASCADE;


-- ============================================================================
-- 2. DROP legacy tables.
--
--    Mapping (old → new):
--      stock_latest_snapshot   → stock_quotes
--      stock_broker_quotes     → stock_cur_quote
--      stock_market_daily      → stock_history_quote
--      stock_valuation         → stock_fin_ratios
--      stock_financials        → stock_fin_statement + stock_fin_cashflow
--      stock_technicals        → stock_mkt_technicals
--      stock_performance_daily → stock_mkt_technicals (price_chg_*_pct cols)
--      stock_recommendations   → stock_scoring
--      stock_management        → dropped (was unused)
-- ============================================================================
DROP TABLE IF EXISTS public.stock_latest_snapshot   CASCADE;
DROP TABLE IF EXISTS public.stock_broker_quotes     CASCADE;
DROP TABLE IF EXISTS public.stock_market_daily      CASCADE;
DROP TABLE IF EXISTS public.stock_valuation         CASCADE;
DROP TABLE IF EXISTS public.stock_financials        CASCADE;
DROP TABLE IF EXISTS public.stock_technicals        CASCADE;
DROP TABLE IF EXISTS public.stock_performance_daily CASCADE;
DROP TABLE IF EXISTS public.stock_recommendations   CASCADE;
DROP TABLE IF EXISTS public.stock_management        CASCADE;


COMMIT;
