-- =============================================================================
-- Migration 012: Alerts module.
-- =============================================================================
-- A small pluggable alert system:
--   alert_channels       — where alerts go (email/telegram/webhook/sms)
--   alert_rules          — what triggers alerts (5 named rule types + custom SQL)
--   alert_rule_channels  — m2m wiring
--   alert_events         — fired alerts audit log + dedup state
--
-- Rule type is a string ('verdict_change', 'score_threshold', 'earnings_soon',
-- 'price_change_pct', 'custom_sql'). Each rule's params live in jsonb so a
-- new rule type means a new Python class — no schema migration.
--
-- Idempotent: safe to re-run.
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS public.alert_channels (
    id           BIGSERIAL  PRIMARY KEY,
    user_id      BIGINT     NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name         VARCHAR(64) NOT NULL,
    channel_type VARCHAR(32) NOT NULL,   -- email | telegram | webhook | sms
    -- email:    {"to": "..."}
    -- telegram: {"bot_token": "...", "chat_id": "..."}
    -- webhook:  {"url": "...", "headers": {...}}
    -- sms:      {"twilio_sid": "...", "twilio_token": "...", "from": "+1...", "to": "+1..."}
    config       JSONB      NOT NULL,
    is_active    BOOLEAN    NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alert_channels_user
    ON public.alert_channels (user_id, is_active);

CREATE TABLE IF NOT EXISTS public.alert_rules (
    id                BIGSERIAL  PRIMARY KEY,
    user_id           BIGINT     NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name              VARCHAR(120) NOT NULL,
    rule_type         VARCHAR(32) NOT NULL,
    params            JSONB      NOT NULL DEFAULT '{}'::jsonb,
    stock_filter      JSONB,      -- {"stock_ids": [1,2,3]} or null = all active
    interval_seconds  INTEGER    NOT NULL DEFAULT 60,
    cooldown_seconds  INTEGER    NOT NULL DEFAULT 3600,
    is_enabled        BOOLEAN    NOT NULL DEFAULT TRUE,
    last_evaluated_at TIMESTAMP,
    last_error        TEXT,
    created_at        TIMESTAMP  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alert_rules_user_enabled
    ON public.alert_rules (user_id, is_enabled);
CREATE INDEX IF NOT EXISTS ix_alert_rules_eval_pending
    ON public.alert_rules (is_enabled, last_evaluated_at) WHERE is_enabled = TRUE;

CREATE TABLE IF NOT EXISTS public.alert_rule_channels (
    rule_id    BIGINT NOT NULL REFERENCES public.alert_rules(id)    ON DELETE CASCADE,
    channel_id BIGINT NOT NULL REFERENCES public.alert_channels(id) ON DELETE CASCADE,
    PRIMARY KEY (rule_id, channel_id)
);

CREATE TABLE IF NOT EXISTS public.alert_events (
    id        BIGSERIAL  PRIMARY KEY,
    rule_id   BIGINT     NOT NULL REFERENCES public.alert_rules(id) ON DELETE CASCADE,
    stock_id  BIGINT     REFERENCES public.stocks(id) ON DELETE SET NULL,
    fired_at  TIMESTAMP  NOT NULL DEFAULT now(),
    title     VARCHAR(200) NOT NULL,
    body      TEXT,
    -- {channel_id: {"status": "ok|failed", "error": "..."}}
    delivery  JSONB      NOT NULL DEFAULT '{}'::jsonb,
    snapshot  JSONB
);
CREATE INDEX IF NOT EXISTS ix_alert_events_rule_stock_fired
    ON public.alert_events (rule_id, stock_id, fired_at DESC);
CREATE INDEX IF NOT EXISTS ix_alert_events_fired
    ON public.alert_events (fired_at DESC);

COMMIT;
