-- =============================================================================
-- Migration 008: Add per-exchange URL template for stockanalysis.com.
-- =============================================================================
-- Background:
--   stockanalysis.com uses two URL patterns:
--     * MENA / international:  /quote/{exchange_code}/{ticker}/
--     * US (NASDAQ/NYSE/AMEX): /stocks/{ticker}/  (no exchange in path)
--     * UK (LSE):              /quote/lon/{ticker}/
--
--   Hardcoding "/quote/<code>/" in the scraper fails the moment we add
--   any US ticker. Putting this on Stock would duplicate the same value
--   thousands of times per exchange. Putting it on Exchange is one row
--   per exchange and lets us add new markets without code changes.
--
-- Idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- Add the column. The template uses {ticker} as a placeholder.
-- Default '/quote/<code>/{ticker}/' so existing exchanges keep working.
ALTER TABLE public.exchanges
    ADD COLUMN IF NOT EXISTS stockanalysis_url_template TEXT;

-- Backfill existing rows. Use the exchange.code in the path for MENA / LSE-style
-- exchanges; anything in the US-pattern set gets the unprefixed /stocks/ path.
UPDATE public.exchanges
   SET stockanalysis_url_template = '/quote/' || lower(code) || '/{ticker}/'
 WHERE stockanalysis_url_template IS NULL
   AND lower(code) NOT IN ('nasdaq', 'nyse', 'amex');

UPDATE public.exchanges
   SET stockanalysis_url_template = '/stocks/{ticker}/'
 WHERE stockanalysis_url_template IS NULL
   AND lower(code) IN ('nasdaq', 'nyse', 'amex');

-- Going forward the column should never be NULL — every exchange we scrape
-- needs a template. Enforce it.
ALTER TABLE public.exchanges
    ALTER COLUMN stockanalysis_url_template SET NOT NULL;

COMMIT;
