-- =============================================================================
-- Migration 016: Trading Bot — Milestone 2.
-- =============================================================================
-- Extends tg_channels with per-strategy params ported from the original bot's
-- strategy_config.json. These drive how signals from each channel will be
-- executed in Milestone 3 — but they're also useful as filtering metadata
-- right now (is_tradeable, is_trusted let the UI flag rows).
--
-- order_position_type  → 'MARKET' or 'LIMIT' (or 'STOP'). Defines how the
--                        eventual order is placed against the broker.
-- tp_strategy          → free-text directive like 'tp1, tp1, tp2, tp3' (one
--                        slice of the entry per token). Validated at execute
--                        time, not here.
-- is_tradeable         → false means "show the signal in the sidebar but
--                        never place trades" — equivalent to a paper channel.
-- is_trusted           → metadata flag. Future use: skip confidence scoring,
--                        downweight in dashboards, etc. Pure data for now.
-- image_url            → channel avatar / brand image shown next to signals.
--
-- All defaults preserve current behaviour: every existing channel becomes
-- a MARKET / tp1 / tradeable / trusted strategy. Re-running is idempotent.
-- =============================================================================
BEGIN;

ALTER TABLE public.tg_channels
    ADD COLUMN IF NOT EXISTS order_position_type VARCHAR(16) NOT NULL DEFAULT 'MARKET',
    ADD COLUMN IF NOT EXISTS tp_strategy         VARCHAR(120) NOT NULL DEFAULT 'tp1',
    ADD COLUMN IF NOT EXISTS is_tradeable        BOOLEAN     NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS is_trusted          BOOLEAN     NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS image_url           TEXT;

-- Helpful for admin views that filter to "active strategies only".
CREATE INDEX IF NOT EXISTS ix_tg_channels_tradeable
    ON public.tg_channels (is_tradeable) WHERE is_tradeable = TRUE;

COMMIT;
