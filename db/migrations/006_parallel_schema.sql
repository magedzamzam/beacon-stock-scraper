-- =============================================================================
-- Migration 006: Parallel new schema (non-destructive)
-- =============================================================================
-- Round 1 of the parallel-tables migration plan.
--
-- WHAT THIS DOES:
--   * Creates 10 NEW tables alongside the existing ones
--   * Best-effort backfill from existing tables where data is available
--   * Does NOT drop or rename anything that exists today
--   * Does NOT modify the scraper, API, or frontend (those follow in later rounds)
--
-- WHAT IT DOES NOT DO:
--   * Old tables (stock_market_daily, stock_latest_snapshot, stock_broker_quotes,
--     stock_valuation, stock_performance_daily, stock_technicals (legacy),
--     stock_financials (legacy), stock_recommendations, stock_management) remain
--     populated by the existing scraper. Backfill copies what we can; ongoing
--     writes to the new tables are wired up in later rounds.
--
-- ROLLBACK:
--   To roll back this migration, run the matching DROP TABLE statements for
--   the 10 new tables. No existing data is mutated.
--
-- Safe to re-run: every CREATE uses IF NOT EXISTS; every INSERT uses ON CONFLICT
-- DO NOTHING. Re-running won't duplicate or corrupt.
-- =============================================================================

BEGIN;


-- ============================================================================
-- 1. stock_quotes — denormalised "current state" per stock.
--    Single row per stock; the canonical row that the screener and stock
--    detail header read from. Recomputed by the scraper, the broker quote
--    refresher, and the recommender.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_quotes (
    stock_id            bigint        PRIMARY KEY REFERENCES public.stocks(id) ON DELETE CASCADE,
    -- Canonical price block (single source of truth)
    current_price       numeric(20, 6),
    prev_close          numeric(20, 6),
    change_abs          numeric(20, 6),
    change_pct          numeric(12, 6),
    -- 'broker' (live), 'scrape' (delayed), or NULL when no data
    price_source        varchar(16),
    price_fetched_at    timestamp,
    -- Denormalised for fast list rendering
    market_cap          numeric(24, 4),
    currency            varchar(8),
    -- Most-recent ratios from stock_fin_ratios (avoids joining on every screener row)
    pe_ratio            numeric(18, 6),
    pe_forward          numeric(18, 6),
    dividend_yield_pct  numeric(12, 6),
    -- Most-recent technicals (from stock_mkt_technicals)
    rsi_14              numeric(10, 4),
    week_52_high        numeric(18, 6),
    week_52_low         numeric(18, 6),
    -- Analyst consensus (from stock_analyst_consensus latest)
    analyst_target      numeric(18, 6),
    analyst_upside_pct  numeric(12, 6),
    -- Composite score / verdict (from stock_scoring)
    composite_score     numeric(6, 2),
    verdict             varchar(16),
    last_updated        timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stock_quotes_verdict ON public.stock_quotes(verdict);
CREATE INDEX IF NOT EXISTS ix_stock_quotes_score   ON public.stock_quotes(composite_score DESC);


-- ============================================================================
-- 2. stock_cur_quote — live broker quote(s) per (stock, broker).
--    Replaces stock_broker_quotes in later rounds. Multiple brokers can cover
--    the same stock; this row is the broker's last bid/offer/OHLC.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_cur_quote (
    id                  bigserial      PRIMARY KEY,
    stock_id            bigint         NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    broker_id           bigint         NOT NULL REFERENCES public.brokers(id) ON DELETE CASCADE,
    broker_symbol       varchar(64)    NOT NULL,
    bid                 numeric(20, 6),
    offer               numeric(20, 6),
    last_price          numeric(20, 6),
    open_price          numeric(20, 6),
    high_price          numeric(20, 6),
    low_price           numeric(20, 6),
    close_price         numeric(20, 6),
    volume              numeric(24, 4),
    -- Broker-reported change (often vs day-open, NOT prev close — don't use
    -- as canonical; the canonical change is on stock_quotes).
    broker_change_abs   numeric(20, 6),
    broker_change_pct   numeric(12, 6),
    currency            varchar(8),
    market_status       varchar(32),
    raw                 jsonb,
    fetched_at          timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, broker_id)
);
CREATE INDEX IF NOT EXISTS ix_stock_cur_quote_fetched ON public.stock_cur_quote(fetched_at DESC);


-- ============================================================================
-- 3. stock_history_quote — daily OHLC + volume time series.
--    One row per (stock, trading_date). NO broker_id (per-exchange).
--    Replaces stock_market_daily in later rounds.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_history_quote (
    id              bigserial      PRIMARY KEY,
    stock_id        bigint         NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    trading_date    date           NOT NULL,
    open_price      numeric(18, 6),
    high_price      numeric(18, 6),
    low_price       numeric(18, 6),
    close_price     numeric(18, 6),
    volume          bigint,
    market_cap      numeric(24, 4),
    -- Day-over-day change vs the prior trading_date's close
    change_pct      numeric(12, 6),
    source          varchar(32),     -- 'scrape' | 'broker:capital.com' | etc.
    scraped_at      timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, trading_date)
);
CREATE INDEX IF NOT EXISTS ix_stock_history_quote_lookup
    ON public.stock_history_quote(stock_id, trading_date DESC);


-- ============================================================================
-- 4. stock_fin_ratios — valuation ratios time series.
--    One row per (stock, period_end). period_end = most-recent reporting date
--    these ratios were computed against (TTM ratios use the latest quarter end).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_fin_ratios (
    id                  bigserial    PRIMARY KEY,
    stock_id            bigint       NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    period_end          date         NOT NULL,
    period_type         varchar(16)  NOT NULL DEFAULT 'TTM',  -- 'TTM' | 'ANNUAL' | 'QUARTER'
    -- Core valuation
    pe_ratio            numeric(18, 6),
    pe_forward          numeric(18, 6),
    ps_ratio            numeric(18, 6),     -- price / sales
    pb_ratio            numeric(18, 6),     -- price / book
    p_fcf_ratio         numeric(18, 6),     -- price / free cash flow
    peg_ratio           numeric(18, 6),     -- pe / earnings growth
    ev_sales            numeric(18, 6),
    ev_ebitda           numeric(18, 6),
    -- Quality (return on capital)
    roe                 numeric(12, 6),     -- return on equity %
    roa                 numeric(12, 6),     -- return on assets %
    roic                numeric(12, 6),     -- return on invested capital %
    -- Per-share / dilution
    sbc_revenue_ratio   numeric(12, 6),     -- SBC / revenue % (matters for tech)
    fcf_per_share       numeric(18, 6),
    -- Snapshot of price / market cap used to compute these (so ratios are auditable)
    snapshot_price      numeric(20, 6),
    snapshot_market_cap numeric(24, 4),
    scraped_at          timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, period_end, period_type)
);


-- ============================================================================
-- 5. stock_fin_statement — P&L items + growth metrics, time series.
--    One row per (stock, period_end, period_type).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_fin_statement (
    id                          bigserial    PRIMARY KEY,
    stock_id                    bigint       NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    period_end                  date         NOT NULL,
    period_type                 varchar(16)  NOT NULL DEFAULT 'TTM',  -- 'TTM' | 'ANNUAL' | 'QUARTER'
    last_report_date            date,
    -- P&L line items
    revenue                     numeric(24, 4),
    gross_profit                numeric(24, 4),
    operating_income            numeric(24, 4),
    net_income                  numeric(24, 4),
    ebitda                      numeric(24, 4),
    income_tax                  numeric(24, 4),
    eps_diluted                 numeric(18, 6),
    -- Growth metrics (derived; carried alongside so screener can filter without recomputing)
    revenue_growth_yoy          numeric(12, 6),
    revenue_growth_3y           numeric(12, 6),     -- 3-year CAGR
    revenue_growth_5y           numeric(12, 6),     -- 5-year CAGR
    gross_profit_growth_yoy     numeric(12, 6),
    operating_income_growth_yoy numeric(12, 6),
    net_income_growth_yoy       numeric(12, 6),
    eps_growth_yoy              numeric(12, 6),
    eps_growth_3y               numeric(12, 6),
    eps_growth_5y               numeric(12, 6),
    -- Quality flags
    profitable_years            smallint,           -- profitable years in last 10 (0..10)
    is_estimate                 boolean      NOT NULL DEFAULT false,
    scraped_at                  timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, period_end, period_type, is_estimate)
);


-- ============================================================================
-- 6. stock_fin_cashflow — cashflow items, time series.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_fin_cashflow (
    id                      bigserial    PRIMARY KEY,
    stock_id                bigint       NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    period_end              date         NOT NULL,
    period_type             varchar(16)  NOT NULL DEFAULT 'TTM',
    operating_cash_flow     numeric(24, 4),
    investing_cash_flow     numeric(24, 4),
    financing_cash_flow     numeric(24, 4),
    net_cash_flow           numeric(24, 4),
    cap_ex                  numeric(24, 4),
    free_cash_flow          numeric(24, 4),
    sbc                     numeric(24, 4),     -- stock-based compensation (lives here, not statement)
    fcf_minus_sbc           numeric(24, 4),     -- "true" FCF after dilution cost
    net_borrowing           numeric(24, 4),
    is_estimate             boolean      NOT NULL DEFAULT false,
    scraped_at              timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, period_end, period_type, is_estimate)
);


-- ============================================================================
-- 7. stock_mkt_dividends — dividend metrics, "current state" only.
--    One row per stock — refreshed on each scrape.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_mkt_dividends (
    stock_id                bigint        PRIMARY KEY REFERENCES public.stocks(id) ON DELETE CASCADE,
    dividend_yield_pct      numeric(12, 6),
    dividend_per_share      numeric(18, 6),     -- TTM total
    last_dividend_amount    numeric(18, 6),     -- most recent payment
    ex_dividend_date        date,
    payout_ratio_pct        numeric(12, 6),     -- div / earnings (sustainability)
    payout_frequency        varchar(32),        -- 'QUARTERLY' | 'ANNUAL' | 'SEMI_ANNUAL' | 'MONTHLY'
    div_growth_yoy          numeric(12, 6),
    div_growth_3y           numeric(12, 6),
    div_growth_5y           numeric(12, 6),
    growth_years_streak     smallint,           -- consecutive years of dividend INCREASES
    payment_years_streak    smallint,           -- consecutive years of any dividend payment
    scraped_at              timestamp NOT NULL DEFAULT now()
);


-- ============================================================================
-- 8. stock_mkt_technicals — technical indicators time series.
--    One row per (stock, trading_date).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_mkt_technicals (
    id                          bigserial    PRIMARY KEY,
    stock_id                    bigint       NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    trading_date                date         NOT NULL,
    -- Indicators
    rsi_14                      numeric(10, 4),
    sma_50                      numeric(18, 6),
    sma_200                     numeric(18, 6),
    ema_20                      numeric(18, 6),
    macd                        numeric(18, 6),
    macd_signal                 numeric(18, 6),
    atr_14                      numeric(18, 6),
    volatility_30d              numeric(12, 6),
    above_sma_50                boolean,
    above_sma_200               boolean,
    golden_cross                boolean,
    -- Price-change windows (no 1d here; that lives on stock_quotes.change_pct)
    price_chg_1m_pct            numeric(12, 6),
    price_chg_3m_pct            numeric(12, 6),
    price_chg_6m_pct            numeric(12, 6),
    price_chg_1y_pct            numeric(12, 6),
    price_chg_3y_pct            numeric(12, 6),
    price_chg_5y_pct            numeric(12, 6),
    -- Total return (includes dividends)
    total_ret_1y_pct            numeric(12, 6),
    total_ret_3y_pct            numeric(12, 6),
    total_ret_5y_pct            numeric(12, 6),
    -- Annualised
    ret_cagr_3y_pct             numeric(12, 6),
    ret_cagr_5y_pct             numeric(12, 6),
    -- 52-week range
    week_52_high                numeric(18, 6),
    week_52_low                 numeric(18, 6),
    week_52_high_change_pct     numeric(12, 6),     -- % off 52w high
    week_52_low_change_pct      numeric(12, 6),     -- % above 52w low
    -- All-time
    ath_price                   numeric(18, 6),
    ath_change_pct              numeric(12, 6),     -- % off all-time high
    -- Liquidity
    volume_daily                bigint,
    dollar_volume_daily         numeric(24, 4),
    avg_dollar_volume_30d       numeric(24, 4),
    -- Risk
    beta                        numeric(12, 6),
    scraped_at                  timestamp NOT NULL DEFAULT now(),
    UNIQUE (stock_id, trading_date)
);


-- ============================================================================
-- 9. stock_scoring — composite + per-component scores, with audit fields.
--    Append-only history (one row per scoring run); the latest row is what
--    gets denormalised onto stock_quotes.composite_score / verdict.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.stock_scoring (
    id                  bigserial      PRIMARY KEY,
    stock_id            bigint         NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    -- Composite + verdict
    composite_score     numeric(6, 2),
    verdict             varchar(16),
    -- Per-component scores (each 0-100 or NULL)
    score_valuation     numeric(6, 2),
    score_growth        numeric(6, 2),
    score_quality       numeric(6, 2),
    score_momentum      numeric(6, 2),
    score_income        numeric(6, 2),
    score_risk          numeric(6, 2),
    -- Explainability
    pros                jsonb,         -- list of strings, e.g. ["strong dividend growth", "low PE"]
    cons                jsonb,
    risk_flags          jsonb,         -- e.g. ["negative FCF 3 years", "yield > 12% (trap)"]
    -- Audit
    model_version       varchar(32),
    inputs_snapshot     jsonb,         -- raw inputs the model saw, for reproducibility
    updated_at          timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stock_scoring_stock_updated
    ON public.stock_scoring(stock_id, updated_at DESC);


-- ============================================================================
-- 10. BACKFILL — best-effort copy from the existing tables.
--     All inserts use ON CONFLICT DO NOTHING so re-running is safe.
-- ============================================================================

-- 10a. stock_quotes <- stock_latest_snapshot (+ best-of broker)
INSERT INTO public.stock_quotes (
    stock_id, current_price, prev_close, change_abs, change_pct,
    price_source, price_fetched_at,
    market_cap, currency,
    pe_ratio, dividend_yield_pct,
    week_52_high, week_52_low,
    analyst_target, analyst_upside_pct,
    composite_score, verdict, last_updated
)
SELECT
    s.id,
    COALESCE(bq.last_price, sls.last_close),
    NULL::numeric,                                  -- prev_close: filled by next round's recompute
    NULL::numeric,
    sls.last_change_pct,
    CASE
        WHEN bq.last_price IS NOT NULL THEN 'broker'
        WHEN sls.last_close IS NOT NULL THEN 'scrape'
        ELSE NULL
    END,
    COALESCE(bq.fetched_at, sls.last_updated),
    sls.market_cap, s.currency,
    sls.pe_ratio, sls.dividend_yield_pct,
    -- 52w from stock_market_daily latest row (snapshot doesn't have these, but market_daily does)
    md.week_52_high, md.week_52_low,
    sls.analyst_target, sls.analyst_upside_pct,
    sls.composite_score, sls.verdict,
    COALESCE(bq.fetched_at, sls.last_updated, now())
FROM public.stocks s
LEFT JOIN public.stock_latest_snapshot sls ON sls.stock_id = s.id
LEFT JOIN LATERAL (
    SELECT last_price, fetched_at FROM public.stock_broker_quotes
    WHERE stock_id = s.id ORDER BY fetched_at DESC LIMIT 1
) bq ON true
LEFT JOIN LATERAL (
    SELECT week_52_high, week_52_low FROM public.stock_market_daily
    WHERE stock_id = s.id ORDER BY trading_date DESC LIMIT 1
) md ON true
WHERE sls.stock_id IS NOT NULL OR bq.last_price IS NOT NULL
ON CONFLICT (stock_id) DO NOTHING;


-- 10b. stock_cur_quote <- stock_broker_quotes (most recent row per pair)
INSERT INTO public.stock_cur_quote (
    stock_id, broker_id, broker_symbol,
    bid, offer, last_price,
    open_price, high_price, low_price, close_price, volume,
    broker_change_abs, broker_change_pct,
    currency, market_status, raw, fetched_at
)
SELECT DISTINCT ON (stock_id, broker_id)
    stock_id, broker_id, broker_symbol,
    bid, offer, last_price,
    open_price, high_price, low_price, close_price, volume,
    change_abs, change_pct,
    currency, market_status, raw, fetched_at
FROM public.stock_broker_quotes
ORDER BY stock_id, broker_id, fetched_at DESC
ON CONFLICT (stock_id, broker_id) DO NOTHING;


-- 10c. stock_history_quote <- stock_market_daily (OHLC + volume + market_cap)
INSERT INTO public.stock_history_quote (
    stock_id, trading_date,
    open_price, high_price, low_price, close_price,
    volume, market_cap, source, scraped_at
)
SELECT
    stock_id, trading_date,
    open_price, high_price, low_price, close_price,
    volume, market_cap, 'scrape', scraped_at
FROM public.stock_market_daily
ON CONFLICT (stock_id, trading_date) DO NOTHING;

-- Compute change_pct vs the previous trading_date for each backfilled row.
WITH ordered AS (
    SELECT id, stock_id, trading_date, close_price,
           LAG(close_price) OVER (PARTITION BY stock_id ORDER BY trading_date) AS prev_close
    FROM public.stock_history_quote
)
UPDATE public.stock_history_quote h
SET change_pct = ((o.close_price - o.prev_close) / o.prev_close) * 100
FROM ordered o
WHERE h.id = o.id
  AND o.prev_close IS NOT NULL
  AND o.prev_close <> 0
  AND o.close_price IS NOT NULL
  AND h.change_pct IS NULL;


-- 10d. stock_fin_ratios <- stock_valuation + stock_market_daily latest
--      One row per (stock_id, fiscal_year) from stock_valuation.
--      period_end = December 31 of fiscal_year, period_type = 'ANNUAL'.
INSERT INTO public.stock_fin_ratios (
    stock_id, period_end, period_type,
    pe_ratio, pe_forward, ps_ratio, pb_ratio, ev_sales, ev_ebitda,
    snapshot_price, scraped_at
)
SELECT
    v.stock_id,
    make_date(v.fiscal_year, 12, 31),
    'ANNUAL',
    v.pe, NULL, NULL, v.price_to_book, v.ev_sales, v.ev_ebitda,
    NULL, v.scraped_at
FROM public.stock_valuation v
ON CONFLICT (stock_id, period_end, period_type) DO NOTHING;

-- And copy the latest stock_market_daily TTM ratios into a fresh TTM row.
INSERT INTO public.stock_fin_ratios (
    stock_id, period_end, period_type,
    pe_ratio, pe_forward, scraped_at
)
SELECT DISTINCT ON (stock_id)
    stock_id, trading_date, 'TTM',
    pe_ratio, forward_pe, scraped_at
FROM public.stock_market_daily
WHERE pe_ratio IS NOT NULL OR forward_pe IS NOT NULL
ORDER BY stock_id, trading_date DESC
ON CONFLICT (stock_id, period_end, period_type) DO NOTHING;


-- 10e. stock_fin_statement <- stock_financials
INSERT INTO public.stock_fin_statement (
    stock_id, period_end, period_type,
    revenue, operating_income, net_income, ebitda, is_estimate, scraped_at
)
SELECT
    f.stock_id,
    COALESCE(f.source_date, make_date(f.fiscal_year, 12, 31)),
    f.period_type,
    f.revenue, f.operating_income, f.net_income, f.ebitda,
    f.is_estimate, f.scraped_at
FROM public.stock_financials f
WHERE f.statement_type IN ('INCOME', 'MIXED')
ON CONFLICT (stock_id, period_end, period_type, is_estimate) DO NOTHING;


-- 10f. stock_fin_cashflow <- stock_financials
INSERT INTO public.stock_fin_cashflow (
    stock_id, period_end, period_type,
    operating_cash_flow, free_cash_flow, is_estimate, scraped_at
)
SELECT
    f.stock_id,
    COALESCE(f.source_date, make_date(f.fiscal_year, 12, 31)),
    f.period_type,
    f.operating_cash_flow, f.free_cash_flow,
    f.is_estimate, f.scraped_at
FROM public.stock_financials f
WHERE f.statement_type IN ('CASHFLOW', 'MIXED')
   OR f.operating_cash_flow IS NOT NULL OR f.free_cash_flow IS NOT NULL
ON CONFLICT (stock_id, period_end, period_type, is_estimate) DO NOTHING;


-- 10g. stock_mkt_dividends <- stock_market_daily (most recent row per stock)
INSERT INTO public.stock_mkt_dividends (
    stock_id, dividend_yield_pct, dividend_per_share,
    ex_dividend_date, payout_ratio_pct, payout_frequency,
    div_growth_yoy, scraped_at
)
SELECT DISTINCT ON (stock_id)
    stock_id, dividend_yield_pct, dividend,
    ex_dividend_date, payout_ratio_pct, payout_frequency,
    dividend_growth_pct, scraped_at
FROM public.stock_market_daily
WHERE dividend_yield_pct IS NOT NULL OR dividend IS NOT NULL
ORDER BY stock_id, trading_date DESC
ON CONFLICT (stock_id) DO NOTHING;


-- 10h. stock_mkt_technicals <- stock_technicals + stock_market_daily 52w + stock_performance_daily
INSERT INTO public.stock_mkt_technicals (
    stock_id, trading_date,
    macd, macd_signal, golden_cross,
    week_52_high, week_52_low,
    beta, scraped_at
)
SELECT
    t.stock_id, t.trading_date,
    t.macd, t.macd_signal, t.golden_cross,
    md.week_52_high, md.week_52_low,
    md.beta, t.scraped_at
FROM public.stock_technicals t
LEFT JOIN public.stock_market_daily md
       ON md.stock_id = t.stock_id AND md.trading_date = t.trading_date
ON CONFLICT (stock_id, trading_date) DO NOTHING;


-- 10i. stock_scoring <- stock_recommendations (history)
--      Old table has 7 component scores cut differently from the new schema's 6:
--        old fundamental_score   -> approximated by new score_quality
--        old valuation_score     -> new score_valuation
--        old momentum_score      -> new score_momentum
--        old technical_score     -> approximated by new score_momentum (already mapped)
--        old analyst_score       -> no direct new column (stored in inputs_snapshot)
--        old quality_score       -> new score_quality (already mapped)
--        old risk_score          -> new score_risk
--        old reasoning (jsonb)   -> stored in inputs_snapshot (cleanly separated)
--      score_growth and score_income on the new table stay NULL until rescored.
INSERT INTO public.stock_scoring (
    stock_id, composite_score, verdict,
    score_valuation, score_quality, score_momentum, score_risk,
    inputs_snapshot, model_version, updated_at
)
SELECT
    stock_id, composite_score, verdict,
    valuation_score,
    -- prefer quality_score; fall back to fundamental_score if quality is null
    COALESCE(quality_score, fundamental_score),
    -- prefer momentum_score; fall back to technical_score
    COALESCE(momentum_score, technical_score),
    risk_score,
    jsonb_build_object(
        'reasoning', reasoning,
        'analyst_score', analyst_score,
        'fundamental_score', fundamental_score,
        'technical_score', technical_score,
        'score_date', score_date
    ),
    model_version, scraped_at
FROM public.stock_recommendations sr
-- Re-run guard: only seed history rows if this stock has no scoring rows yet.
WHERE NOT EXISTS (
    SELECT 1 FROM public.stock_scoring s2 WHERE s2.stock_id = sr.stock_id
);


COMMIT;

-- =============================================================================
-- ROLLBACK SCRIPT (run manually if you want to revert this migration):
--
-- DROP TABLE IF EXISTS public.stock_scoring          CASCADE;
-- DROP TABLE IF EXISTS public.stock_mkt_technicals   CASCADE;
-- DROP TABLE IF EXISTS public.stock_mkt_dividends    CASCADE;
-- DROP TABLE IF EXISTS public.stock_fin_cashflow     CASCADE;
-- DROP TABLE IF EXISTS public.stock_fin_statement    CASCADE;
-- DROP TABLE IF EXISTS public.stock_fin_ratios       CASCADE;
-- DROP TABLE IF EXISTS public.stock_history_quote    CASCADE;
-- DROP TABLE IF EXISTS public.stock_cur_quote        CASCADE;
-- DROP TABLE IF EXISTS public.stock_quotes           CASCADE;
-- =============================================================================
