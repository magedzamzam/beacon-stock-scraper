-- =============================================================================
-- Migration 015: Trading Bot — Milestone 1 schema.
-- =============================================================================
-- Telegram listener + signal parser tables. Bot listens on configured channels,
-- writes raw messages to tg_raw_messages, parser reads new rows and emits
-- structured tg_signals.
--
--   tg_channels       — channels the listener subscribes to
--   tg_raw_messages   — every message captured (the "queue"; parser polls FOR UPDATE
--                       SKIP LOCKED so multiple workers don't double-process)
--   tg_signals        — parsed signals; pulled from tg_raw_messages
--
-- Listener credentials (Telegram api_id, api_hash, session) live in app_settings
-- under keys 'tgbot.api_id', 'tgbot.api_hash', 'tgbot.session_string'. Settings
-- already supports JSONB and encryption-at-rest — no new credential table needed.
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS public.tg_channels (
    id              BIGSERIAL    PRIMARY KEY,
    channel_id      BIGINT       NOT NULL UNIQUE,
    channel_username VARCHAR(80),
    channel_title   VARCHAR(160) NOT NULL,
    is_enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Parser variant to use. 'gold_xau' is the only one ported in this milestone;
    -- future strategies (forex pairs, indices) will add new keys.
    parser_key      VARCHAR(32)  NOT NULL DEFAULT 'gold_xau',
    notes           TEXT,
    last_message_at TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tg_channels_enabled
    ON public.tg_channels (is_enabled);

CREATE TABLE IF NOT EXISTS public.tg_raw_messages (
    id              BIGSERIAL    PRIMARY KEY,
    channel_id      BIGINT       NOT NULL,
    channel_title   VARCHAR(160),
    tg_message_id   BIGINT       NOT NULL,
    sender_id       BIGINT,
    message_text    TEXT,
    received_at     TIMESTAMP    NOT NULL DEFAULT now(),
    processed_at    TIMESTAMP,
    -- Parser bookkeeping. 'pending' → 'signal' (was a signal) | 'noise' (not a
    -- signal) | 'failed' (parser crashed; investigate via parse_error)
    parse_status    VARCHAR(16)  NOT NULL DEFAULT 'pending',
    parse_error     TEXT,
    UNIQUE (channel_id, tg_message_id)
);
CREATE INDEX IF NOT EXISTS ix_tg_raw_messages_pending
    ON public.tg_raw_messages (parse_status, id)
    WHERE parse_status = 'pending';
CREATE INDEX IF NOT EXISTS ix_tg_raw_messages_received
    ON public.tg_raw_messages (received_at DESC);

CREATE TABLE IF NOT EXISTS public.tg_signals (
    id              BIGSERIAL    PRIMARY KEY,
    raw_message_id  BIGINT       NOT NULL REFERENCES public.tg_raw_messages(id) ON DELETE CASCADE,
    channel_id      BIGINT       NOT NULL,
    channel_title   VARCHAR(160),
    signal_time     TIMESTAMP    NOT NULL DEFAULT now(),
    symbol          VARCHAR(32)  NOT NULL,
    direction       VARCHAR(8)   NOT NULL,   -- BUY | SELL
    entry_from      NUMERIC(18, 6) NOT NULL,
    entry_to        NUMERIC(18, 6) NOT NULL,
    sl              NUMERIC(18, 6) NOT NULL,
    tps             JSONB        NOT NULL DEFAULT '[]'::jsonb,   -- list of numbers
    parser_key      VARCHAR(32)  NOT NULL,
    -- Lifecycle for later milestones — populated by trade-execution layer.
    -- For Milestone 1, every row stays 'NEW'.
    status          VARCHAR(16)  NOT NULL DEFAULT 'NEW',
    -- Original message kept inline so the UI sidebar can show it without an extra join.
    raw_text        TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tg_signals_time
    ON public.tg_signals (signal_time DESC);
CREATE INDEX IF NOT EXISTS ix_tg_signals_channel
    ON public.tg_signals (channel_id, signal_time DESC);
-- Defense in depth — same raw message can't produce two signal rows.
CREATE UNIQUE INDEX IF NOT EXISTS ux_tg_signals_raw_message
    ON public.tg_signals (raw_message_id);

COMMIT;
