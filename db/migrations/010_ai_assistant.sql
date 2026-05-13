-- =============================================================================
-- Migration 010: AI provider settings + compact prompt presets
-- =============================================================================
-- Adds per-user AI provider config and seeded prompt templates for the
-- stock and portfolio analysis flows.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.ai_provider_settings (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    provider_key    varchar(32) NOT NULL,
    provider_name   varchar(64) NOT NULL,
    enabled         boolean NOT NULL DEFAULT false,
    api_key         text,
    model_name      varchar(120),
    base_url        text,
    last_tested_at  timestamp,
    last_test_status varchar(16),
    last_test_error  text,
    updated_at      timestamp NOT NULL DEFAULT now(),
    updated_by      bigint REFERENCES public.users(id) ON DELETE SET NULL,
    CONSTRAINT ai_provider_settings_user_id_provider_key_key UNIQUE (user_id, provider_key)
);

CREATE INDEX IF NOT EXISTS ix_ai_provider_settings_user_id
    ON public.ai_provider_settings (user_id);

DROP TRIGGER IF EXISTS trg_ai_provider_settings_updated_at ON public.ai_provider_settings;
CREATE TRIGGER trg_ai_provider_settings_updated_at
    BEFORE UPDATE ON public.ai_provider_settings
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();

CREATE TABLE IF NOT EXISTS public.ai_prompt_templates (
    key               varchar(64) PRIMARY KEY,
    scope             varchar(32) NOT NULL,
    label             varchar(120) NOT NULL,
    description       text,
    system_prompt     text NOT NULL,
    max_output_tokens integer NOT NULL DEFAULT 256,
    updated_at        timestamp NOT NULL DEFAULT now()
);

INSERT INTO public.ai_prompt_templates
    (key, scope, label, description, system_prompt, max_output_tokens)
VALUES
    (
        'stock_brief',
        'stock',
        'Stock analysis',
        'Compact single-stock analysis with an independent verdict and reasons.',
        'You are an independent equity analyst. Form your own view of the stock using public knowledge of the company, sector, valuation norms, and macro context. Do NOT assume any third-party verdicts, scores, technical indicators, or analyst targets — none are provided. Return only valid JSON. Keep every field short. Use the fewest possible tokens. No markdown, no preamble, no commentary.',
        320
    ),
    (
        'portfolio_brief',
        'portfolio',
        'Portfolio analysis',
        'Compact portfolio review with independent per-position actions.',
        'You are an independent portfolio strategist. Evaluate each position on its own merits using public knowledge of the company, sector, and macro context. Identify concentration risk and diversification gaps. Do NOT assume any third-party verdicts or scores — none are provided. Return only valid JSON. Keep every field short. Use the fewest possible tokens. No markdown, no preamble, no commentary.',
        420
    )
ON CONFLICT (key) DO UPDATE
SET scope = EXCLUDED.scope,
    label = EXCLUDED.label,
    description = EXCLUDED.description,
    system_prompt = EXCLUDED.system_prompt,
    max_output_tokens = EXCLUDED.max_output_tokens,
    updated_at = now();

COMMIT;
