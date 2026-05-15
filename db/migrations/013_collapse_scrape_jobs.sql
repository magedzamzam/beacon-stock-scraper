-- =============================================================================
-- Migration 013: Collapse scrape_daily_quotes + scrape_fundamentals into one
-- job_key: scrape_news.
-- =============================================================================
-- After the scraper was trimmed to news-only (everything except news now comes
-- from bulk CSV import), the two scrape jobs do identical work. This migration
-- consolidates them under "job.scrape_news":
--
--   * app_settings:  rename rows. If both old keys exist, prefer the
--                    'daily' settings (more conservative cron, fewer surprises).
--   * job_runs:      rewrite past run keys so the history UI still works.
--
-- Idempotent — safe to re-run.
-- =============================================================================
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. app_settings rows
-- ---------------------------------------------------------------------------
-- If both old keys exist, we keep job.scrape_daily_quotes' settings and drop
-- the fundamentals row. If only one of them exists, we promote it.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.app_settings WHERE key = 'job.scrape_news') THEN
        -- New key already in place — just clean up legacy keys.
        DELETE FROM public.app_settings
            WHERE key IN ('job.scrape_daily_quotes', 'job.scrape_fundamentals');
    ELSIF EXISTS (SELECT 1 FROM public.app_settings WHERE key = 'job.scrape_daily_quotes') THEN
        UPDATE public.app_settings SET key = 'job.scrape_news'
            WHERE key = 'job.scrape_daily_quotes';
        DELETE FROM public.app_settings WHERE key = 'job.scrape_fundamentals';
    ELSIF EXISTS (SELECT 1 FROM public.app_settings WHERE key = 'job.scrape_fundamentals') THEN
        UPDATE public.app_settings SET key = 'job.scrape_news'
            WHERE key = 'job.scrape_fundamentals';
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. job_runs history — rewrite legacy keys so the audit log keeps working.
-- ---------------------------------------------------------------------------
UPDATE public.job_runs SET job_key = 'job.scrape_news'
    WHERE job_key IN ('job.scrape_daily_quotes', 'job.scrape_fundamentals');

COMMIT;
