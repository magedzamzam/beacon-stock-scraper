-- =============================================================================
-- Migration 009: Bulk CSV import for stockanalysis.com exchange exports.
-- =============================================================================
-- Adds a per-import audit row and a per-stock raw payload row.
--
-- The bulk importer fans the 248-column CSV out across the parallel-schema
-- tables (stocks, stock_quotes, stock_history_quote, stock_fin_ratios,
-- stock_fin_statement, stock_fin_cashflow, stock_mkt_dividends,
-- stock_mkt_technicals).  But ~30 of the 248 columns don't have a structured
-- home yet (Z-Score, F-Score, 20MA, 150MA, insider ownership, etc.).  Rather
-- than dropping that data, we keep it as jsonb in stock_bulk_import_raw so
-- it's available for future migrations that add proper columns.
--
-- Idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- One row per import job.  The audit log shows when it ran, who triggered it,
-- which exchange, and the outcome.
CREATE TABLE IF NOT EXISTS public.stock_bulk_imports (
    id            BIGSERIAL  PRIMARY KEY,
    exchange_id   INTEGER    NOT NULL REFERENCES public.exchanges(id) ON DELETE RESTRICT,
    user_id       BIGINT     REFERENCES public.users(id) ON DELETE SET NULL,
    filename      TEXT,
    started_at    TIMESTAMP  NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    status        VARCHAR(16) NOT NULL DEFAULT 'running',  -- running | ok | failed
    rows_total    INTEGER    NOT NULL DEFAULT 0,
    rows_inserted INTEGER    NOT NULL DEFAULT 0,
    rows_updated  INTEGER    NOT NULL DEFAULT 0,
    rows_skipped  INTEGER    NOT NULL DEFAULT 0,
    rows_errored  INTEGER    NOT NULL DEFAULT 0,
    error_message TEXT,
    summary       JSONB
);

CREATE INDEX IF NOT EXISTS ix_stock_bulk_imports_started_at
    ON public.stock_bulk_imports (started_at DESC);

-- One row per (stock, import) holding the *raw* CSV payload.
-- Lets us recover or re-process columns that didn't have a destination at
-- import time without re-uploading the file.
CREATE TABLE IF NOT EXISTS public.stock_bulk_import_raw (
    id          BIGSERIAL  PRIMARY KEY,
    import_id   BIGINT     NOT NULL REFERENCES public.stock_bulk_imports(id) ON DELETE CASCADE,
    stock_id    BIGINT     REFERENCES public.stocks(id) ON DELETE CASCADE,
    ticker      VARCHAR(32) NOT NULL,
    raw_payload JSONB      NOT NULL,
    imported_at TIMESTAMP  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_stock_bulk_import_raw_stock
    ON public.stock_bulk_import_raw (stock_id, imported_at DESC);
CREATE INDEX IF NOT EXISTS ix_stock_bulk_import_raw_import
    ON public.stock_bulk_import_raw (import_id);

COMMIT;
