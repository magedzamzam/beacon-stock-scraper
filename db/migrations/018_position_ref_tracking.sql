-- =============================================================================
-- Migration 018: Per-position tracking on broker_positions_snapshot.
-- =============================================================================
-- Until now broker_positions_snapshot was uniqued by (account_id, broker_symbol)
-- — meaning ONE row per symbol per account. That breaks the moment we open
-- multiple positions on the same symbol (which the M3 fanout does on every
-- signal: same XAU symbol, N positions, each with its own broker dealId).
--
-- This migration:
--   1. Adds broker_position_ref (Capital.com's positions[].dealId) so the
--      gateway can target a specific position for modify/close.
--   2. Adds stop_loss / take_profit columns so the UI can show what the
--      broker thinks SL/TP currently are (drifts from BrokerOrder values
--      once we start moving SL manually).
--   3. Widens the unique constraint to (account_id, broker_position_ref).
--      We do NOT enforce NOT NULL on the ref because old snapshot rows
--      written before this migration have no ref; they'll get rewritten
--      on the next refresh.
--   4. Drops the (account_id, broker_symbol) unique — multi-position
--      symbols are the whole point.
--
-- ROLLOUT NOTE: existing rows are emptied so the next refresh repopulates
-- with the dealId field correctly. TRUNCATE is safer than UPDATE-then-add
-- because partial-update collisions during the migration window would
-- block the new unique constraint.
-- =============================================================================
BEGIN;

-- Wipe stale rows so the next refresh from the broker repopulates cleanly.
-- These are CACHED snapshots, not source of truth — losing them is safe.
TRUNCATE TABLE public.broker_positions_snapshot;

-- 1) Drop the old unique constraint. Its auto-generated name varies between
-- environments; query pg_constraint to find and drop it generically.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname INTO constraint_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'broker_positions_snapshot'
      AND con.contype = 'u'
      AND pg_get_constraintdef(con.oid) LIKE '%(account_id, broker_symbol)%';
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.broker_positions_snapshot DROP CONSTRAINT %I',
                       constraint_name);
    END IF;
END$$;

-- 2) Add the new columns.
ALTER TABLE public.broker_positions_snapshot
    ADD COLUMN IF NOT EXISTS broker_position_ref VARCHAR(64),
    ADD COLUMN IF NOT EXISTS stop_loss           NUMERIC(20, 6),
    ADD COLUMN IF NOT EXISTS take_profit         NUMERIC(20, 6),
    ADD COLUMN IF NOT EXISTS opened_at           TIMESTAMP;

-- 3) New unique key. Partial-unique allows the ref to be temporarily NULL
-- (won't be after the wipe + next refresh, but kept defensive).
CREATE UNIQUE INDEX IF NOT EXISTS ux_broker_positions_snapshot_ref
    ON public.broker_positions_snapshot (account_id, broker_position_ref)
    WHERE broker_position_ref IS NOT NULL;

-- Useful access pattern for the new positions screen: list bot positions
-- for a given account, newest first.
CREATE INDEX IF NOT EXISTS ix_broker_positions_snapshot_account_fetched
    ON public.broker_positions_snapshot (account_id, fetched_at DESC);

COMMIT;
