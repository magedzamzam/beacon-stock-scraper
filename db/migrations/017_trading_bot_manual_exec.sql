-- =============================================================================
-- Migration 017: Trading Bot — Milestone 3 (manual execution).
-- =============================================================================
-- bot_trades links a parsed signal to one or more broker_orders that were
-- placed for it. The "for it" is intentional — the same signal can be
-- traded multiple times (different accounts, different TPs, even by accident).
--
-- We also seed default bot-global settings used by the lot-sizing calculator
-- on the trade form. All seeds use ON CONFLICT DO NOTHING so re-running
-- this migration on an environment where the admin already tuned the values
-- doesn't blow them away.
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS public.bot_trades (
    id              BIGSERIAL    PRIMARY KEY,
    signal_id       BIGINT       NOT NULL REFERENCES public.tg_signals(id) ON DELETE CASCADE,
    order_id        BIGINT       NOT NULL REFERENCES public.broker_orders(id) ON DELETE CASCADE,
    user_id         BIGINT       NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    account_id      BIGINT       NOT NULL REFERENCES public.trading_accounts(id) ON DELETE CASCADE,
    -- Which TP level the trade aimed at, e.g. 'TP1' / 'TP2' / 'TP3', or NULL
    -- when the user placed the order without a TP (rare but possible).
    tp_level        VARCHAR(8),
    -- Risk % of capital the user requested at trade time. Stored for audit
    -- so we can later analyse "did the risk discipline actually work".
    risk_pct        NUMERIC(6, 3),
    -- The mode at trade time. Always 'manual' for Milestone 3 — future
    -- automated mode will write 'auto'.
    trade_mode      VARCHAR(16) NOT NULL DEFAULT 'manual',
    notes           TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bot_trades_signal ON public.bot_trades (signal_id);
CREATE INDEX IF NOT EXISTS ix_bot_trades_user_created
    ON public.bot_trades (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Bot settings — defaults seeded only if missing.
-- ---------------------------------------------------------------------------
-- Format note: app_settings.value is JSONB, so number literals stay numbers
-- and strings need double-quoting.
INSERT INTO public.app_settings (key, value, description) VALUES
    ('tgbot.risk_pct_per_trade',     '1.0'::jsonb,
        'Default risk per trade as % of account capital. Used to seed the trade form.'),
    ('tgbot.max_risk_pct_per_trade', '5.0'::jsonb,
        'Hard cap on per-trade risk %. The trade form refuses higher values.'),
    ('tgbot.min_lot_size',           '0.01'::jsonb,
        'Smallest order size the form will allow. Floor at the broker minimum.'),
    ('tgbot.lot_step',               '0.01'::jsonb,
        'Lot increment (step size). Computed lot is rounded down to this.'),
    ('tgbot.default_tp_level',       '"TP1"'::jsonb,
        'Which TP the form picks by default when the signal has multiple. TP1..TP8.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
