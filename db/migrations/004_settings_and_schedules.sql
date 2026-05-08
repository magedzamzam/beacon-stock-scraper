-- =============================================================================
-- Migration 004: Configurable scheduler & app settings
-- =============================================================================
-- Idempotent. Safe to re-run.
--
--  1. app_settings  — key/JSON values. One row per setting key. Today we use
--     it to store per-job schedules; tomorrow it can hold any other config
--     the admin UI exposes.
--
--  2. job_runs      — audit log of scheduled job executions. Lets the admin
--     see when each job last ran and the result.
--
--  Seed rows establish four scheduled jobs with sensible defaults.
-- =============================================================================

BEGIN;

-- ---------- 1. App settings ----------------------------------------------
CREATE TABLE IF NOT EXISTS public.app_settings (
    key         varchar(120) PRIMARY KEY,
    value       jsonb        NOT NULL,
    description text,
    updated_at  timestamp    NOT NULL DEFAULT now(),
    updated_by  bigint       REFERENCES public.users(id) ON DELETE SET NULL
);

-- Trigger to keep updated_at fresh on UPDATE
CREATE OR REPLACE FUNCTION public.set_updated_at_now()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_app_settings_updated_at ON public.app_settings;
CREATE TRIGGER trg_app_settings_updated_at
    BEFORE UPDATE ON public.app_settings
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();

-- ---------- 2. Job runs audit --------------------------------------------
CREATE TABLE IF NOT EXISTS public.job_runs (
    id            bigserial PRIMARY KEY,
    job_key       varchar(64)  NOT NULL,
    started_at    timestamp    NOT NULL DEFAULT now(),
    finished_at   timestamp,
    -- 'ok', 'failed', 'skipped' (job disabled at execution time),
    -- 'running' for in-progress rows (cleared on completion).
    status        varchar(16)  NOT NULL DEFAULT 'running',
    -- 'scheduled' or 'manual' so admins can tell auto from button-click.
    triggered_by  varchar(16)  NOT NULL DEFAULT 'scheduled',
    user_id       bigint REFERENCES public.users(id) ON DELETE SET NULL,
    duration_s    numeric(10, 2),
    summary       jsonb,
    error_message text
);

CREATE INDEX IF NOT EXISTS ix_job_runs_key_time
    ON public.job_runs (job_key, started_at DESC);


-- ---------- 3. Seed default job schedules --------------------------------
-- Each value is a JSON object with the schema:
--   {
--     "enabled":     bool,
--     "cron":        string ("min hour dom month dow"),
--     "exchanges":   string[]   (empty = all)
--     "description": string
--   }
--
-- ON CONFLICT DO NOTHING preserves any existing customisations.

INSERT INTO public.app_settings (key, value, description) VALUES
    (
        'job.scrape_daily_quotes',
        '{"enabled":true,"cron":"0 16 * * *","exchanges":[],"description":"Daily light scrape: OHLC + technicals + analyst consensus"}'::jsonb,
        'Light daily scrape — runs end of day to capture closes, RSI/SMA, analyst targets.'
    ),
    (
        'job.scrape_fundamentals',
        '{"enabled":true,"cron":"0 3 1 * *","exchanges":[],"description":"Monthly heavy scrape: revenue, EPS, balance sheet, growth metrics"}'::jsonb,
        'Monthly heavy scrape — pulls fundamentals that change quarterly. First day of each month.'
    ),
    (
        'job.score_recompute',
        '{"enabled":true,"cron":"30 16 * * *","exchanges":[],"description":"Recompute composite scores after the daily quote scrape"}'::jsonb,
        'Daily score recompute — runs 30 minutes after the daily quotes job.'
    ),
    (
        'job.account_stats_snapshot',
        '{"enabled":true,"cron":"15 */6 * * *","exchanges":[],"description":"Snapshot trading account balances every 6 hours"}'::jsonb,
        'Every 6 hours — captures balance/equity/P-L for charts and history.'
    )
ON CONFLICT (key) DO NOTHING;

COMMIT;
