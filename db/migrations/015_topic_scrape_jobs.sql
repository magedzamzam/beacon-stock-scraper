-- =============================================================================
-- Migration 015: replace bundled scrape jobs with 6 topic jobs.
-- =============================================================================
-- Previously:
--     job.scrape_daily   — overview page only
--     job.scrape_weekly  — financials + ratios + statistics + forecast + ratings
--
-- After this migration:
--     job.scrape_news, job.scrape_current_quote, job.scrape_financials,
--     job.scrape_technicals, job.scrape_ratios, job.scrape_forecast.
--
-- For app_settings:
--   - We DROP the two old rows. They no longer correspond to real jobs.
--     The new job keys will be seeded with defaults on the scheduler's first
--     tick (which calls _read_job_cfg() and writes a row if missing — that
--     code path is preserved). If a user customised the cron for daily/weekly,
--     they'll need to set them again on the new fine-grained jobs.
--
-- For job_runs:
--   - We KEEP the historical rows so the audit log doesn't lose context.
--     They just point at dead job keys, but the History UI still renders them.
--
-- Idempotent.
-- =============================================================================
BEGIN;

-- Drop the legacy job-settings rows. New jobs get seeded on first scheduler tick.
DELETE FROM public.app_settings
WHERE key IN ('job.scrape_daily', 'job.scrape_weekly');

COMMIT;
