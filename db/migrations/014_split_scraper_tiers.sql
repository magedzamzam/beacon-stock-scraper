-- =============================================================================
-- Migration 014: split the scraper into daily + weekly tiers.
-- =============================================================================
-- The previous tier ('job.scrape_news', news-only) is replaced by:
--     job.scrape_daily   — overview page (news + quote + today's OHLC row)
--     job.scrape_weekly  — financials, balance sheet, cashflow, ratios,
--                          forecast, ratings, statistics, history (if empty)
--
-- We preserve user-configured cron values for scrape_news (carry into
-- scrape_daily). The weekly tier is seeded with the default cron.
-- Idempotent.
-- =============================================================================
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. app_settings — carry the user's cron over
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- Only do the rename if the old key actually exists.
    IF EXISTS (SELECT 1 FROM public.app_settings WHERE key = 'job.scrape_news') THEN
        -- Rename in place. The user's cron + enabled flag + exchange filter
        -- become the new daily settings — that matches their intent.
        UPDATE public.app_settings SET key = 'job.scrape_daily'
            WHERE key = 'job.scrape_news';
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. job_runs history — rewrite legacy keys so audit log keeps working
-- ---------------------------------------------------------------------------
UPDATE public.job_runs SET job_key = 'job.scrape_daily'
    WHERE job_key = 'job.scrape_news';

COMMIT;
