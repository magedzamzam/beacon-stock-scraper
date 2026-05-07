-- =============================================================================
-- Beacon Screener — Schema Enhancements (Migration 001)
-- =============================================================================
-- This migration is IDEMPOTENT and additive. It does not drop or alter your
-- existing tables. It only ADDs new tables and new columns to support:
--   • Daily recommendation scoring (BUY / WATCH / STAY AWAY)
--   • Portfolio management (HOLD / SELL / BUY MORE)
--   • Watchlists per user
--   • News, disclosures, corporate-actions placeholders
--   • Technical indicators (RSI, MAs, ATR) used by the recommender
--   • Caching of latest snapshot per stock for fast UI lookups
-- =============================================================================

-- ---------- 1. Users (lightweight; for portfolio + watchlist) ----------------
CREATE TABLE IF NOT EXISTS public.users (
    id            bigserial PRIMARY KEY,
    email         varchar(255) UNIQUE NOT NULL,
    display_name  varchar(120),
    password_hash varchar(255) NOT NULL,
    is_admin      boolean DEFAULT false,
    created_at    timestamp DEFAULT now(),
    last_login_at timestamp
);

-- ---------- 2. Watchlists ----------------------------------------------------
CREATE TABLE IF NOT EXISTS public.watchlists (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name        varchar(120) NOT NULL DEFAULT 'Default',
    created_at  timestamp DEFAULT now(),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS public.watchlist_items (
    id           bigserial PRIMARY KEY,
    watchlist_id bigint NOT NULL REFERENCES public.watchlists(id) ON DELETE CASCADE,
    stock_id     bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    note         text,
    added_at     timestamp DEFAULT now(),
    UNIQUE(watchlist_id, stock_id)
);

-- ---------- 3. Portfolio (positions) -----------------------------------------
CREATE TABLE IF NOT EXISTS public.portfolio_positions (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    stock_id        bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    quantity        numeric(20,6) NOT NULL CHECK (quantity > 0),
    avg_entry_price numeric(18,6) NOT NULL CHECK (avg_entry_price > 0),
    entry_date      date,
    notes           text,
    is_open         boolean DEFAULT true,
    created_at      timestamp DEFAULT now(),
    updated_at      timestamp DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user
    ON public.portfolio_positions(user_id, is_open);

-- Trade ledger (for averaging-down and history)
CREATE TABLE IF NOT EXISTS public.portfolio_trades (
    id           bigserial PRIMARY KEY,
    position_id  bigint NOT NULL REFERENCES public.portfolio_positions(id) ON DELETE CASCADE,
    trade_type   varchar(8)  NOT NULL CHECK (trade_type IN ('BUY','SELL')),
    quantity     numeric(20,6) NOT NULL,
    price        numeric(18,6) NOT NULL,
    trade_date   date NOT NULL,
    fees         numeric(18,6) DEFAULT 0,
    notes        text,
    created_at   timestamp DEFAULT now()
);

-- ---------- 4. Recommendation scores (daily, per stock) ----------------------
CREATE TABLE IF NOT EXISTS public.stock_recommendations (
    id                 bigserial PRIMARY KEY,
    stock_id           bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    score_date         date NOT NULL,
    -- Component sub-scores 0..100
    fundamental_score  numeric(6,2),
    valuation_score    numeric(6,2),
    momentum_score     numeric(6,2),
    technical_score    numeric(6,2),
    analyst_score      numeric(6,2),
    quality_score      numeric(6,2),
    risk_score         numeric(6,2),  -- higher = riskier (penalty)
    -- Final composite 0..100 and verdict
    composite_score    numeric(6,2),
    verdict            varchar(16) NOT NULL CHECK (verdict IN ('BUY','WATCH','STAY_AWAY')),
    reasoning          jsonb,         -- structured explanation, e.g. {"pros":[...], "cons":[...]}
    model_version      varchar(32) DEFAULT 'v1',
    scraped_at         timestamp DEFAULT now(),
    UNIQUE(stock_id, score_date)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_stock_date
    ON public.stock_recommendations(stock_id, score_date DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_verdict
    ON public.stock_recommendations(score_date DESC, verdict);

-- ---------- 5. Per-position recommendations (HOLD / SELL / BUY MORE) ---------
CREATE TABLE IF NOT EXISTS public.position_recommendations (
    id                bigserial PRIMARY KEY,
    position_id       bigint NOT NULL REFERENCES public.portfolio_positions(id) ON DELETE CASCADE,
    score_date        date NOT NULL,
    current_price     numeric(18,6),
    unrealized_pl_pct numeric(12,4),
    verdict           varchar(16) NOT NULL CHECK (verdict IN ('HOLD','SELL','BUY_MORE','TRIM','STOP_LOSS')),
    confidence        numeric(5,2),  -- 0..100
    reasoning         jsonb,
    scraped_at        timestamp DEFAULT now(),
    UNIQUE(position_id, score_date)
);

-- ---------- 6. Technical indicators (rolling, snapshot per day) -------------
CREATE TABLE IF NOT EXISTS public.stock_technicals (
    id              bigserial PRIMARY KEY,
    stock_id        bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    trading_date    date NOT NULL,
    rsi_14          numeric(10,4),
    sma_50          numeric(18,6),
    sma_200         numeric(18,6),
    ema_20          numeric(18,6),
    macd            numeric(18,6),
    macd_signal     numeric(18,6),
    atr_14          numeric(18,6),
    volatility_30d  numeric(12,6),
    above_sma_50    boolean,
    above_sma_200   boolean,
    golden_cross    boolean,           -- 50 SMA above 200 SMA
    scraped_at      timestamp DEFAULT now(),
    UNIQUE(stock_id, trading_date)
);

-- ---------- 7. Disclosures (regulatory filings; placeholder, fill later) -----
CREATE TABLE IF NOT EXISTS public.stock_disclosures (
    id              bigserial PRIMARY KEY,
    stock_id        bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    disclosure_date date,
    disclosure_type varchar(64),      -- e.g. 'EARNINGS','BOARD_CHANGE','MATERIAL_EVENT','DIVIDEND'
    title           text NOT NULL,
    summary         text,
    sentiment_score numeric(5,2),     -- -100..100, optional NLP analysis
    importance      varchar(16),      -- LOW / MEDIUM / HIGH / CRITICAL
    source          varchar(64),      -- 'DFM','ADX','EGX','OTHER'
    url             text,
    scraped_at      timestamp DEFAULT now(),
    UNIQUE(stock_id, disclosure_date, title)
);

CREATE INDEX IF NOT EXISTS idx_disclosures_stock_date
    ON public.stock_disclosures(stock_id, disclosure_date DESC);

-- ---------- 8. Corporate actions (dividends, splits, AGM) -------------------
CREATE TABLE IF NOT EXISTS public.stock_corporate_actions (
    id            bigserial PRIMARY KEY,
    stock_id      bigint NOT NULL REFERENCES public.stocks(id) ON DELETE CASCADE,
    action_date   date NOT NULL,
    action_type   varchar(32) NOT NULL,   -- DIVIDEND / SPLIT / RIGHTS / BONUS / AGM
    details       jsonb,
    scraped_at    timestamp DEFAULT now(),
    UNIQUE(stock_id, action_date, action_type)
);

-- ---------- 9. News sentiment enrichment -------------------------------------
ALTER TABLE public.stock_news
    ADD COLUMN IF NOT EXISTS summary text,
    ADD COLUMN IF NOT EXISTS sentiment_score numeric(5,2),  -- -100..100
    ADD COLUMN IF NOT EXISTS sentiment_label varchar(16);   -- BULLISH / NEUTRAL / BEARISH

-- ---------- 10. Latest snapshot cache (denormalized for fast UI) ------------
CREATE TABLE IF NOT EXISTS public.stock_latest_snapshot (
    stock_id            bigint PRIMARY KEY REFERENCES public.stocks(id) ON DELETE CASCADE,
    last_close          numeric(18,6),
    last_change_pct     numeric(12,6),
    market_cap          numeric(24,4),
    pe_ratio            numeric(18,6),
    dividend_yield_pct  numeric(12,6),
    week_52_high        numeric(18,6),
    week_52_low         numeric(18,6),
    rsi_14              numeric(10,4),
    analyst_target      numeric(18,6),
    analyst_upside_pct  numeric(12,6),
    composite_score     numeric(6,2),
    verdict             varchar(16),
    last_updated        timestamp DEFAULT now()
);

-- ---------- 11. Helpful views ------------------------------------------------
CREATE OR REPLACE VIEW public.v_stock_overview AS
SELECT
    s.id              AS stock_id,
    s.ticker,
    s.company_name,
    s.sector,
    s.industry,
    s.country,
    s.currency,
    e.code            AS exchange_code,
    e.name            AS exchange_name,
    snap.last_close,
    snap.last_change_pct,
    snap.market_cap,
    snap.pe_ratio,
    snap.dividend_yield_pct,
    snap.composite_score,
    snap.verdict,
    snap.last_updated
FROM public.stocks s
JOIN public.exchanges e ON e.id = s.exchange_id
LEFT JOIN public.stock_latest_snapshot snap ON snap.stock_id = s.id
WHERE s.active IS TRUE;

-- =============================================================================
-- Seed exchanges if empty (DFM, ADX, EGX)
-- =============================================================================
INSERT INTO public.exchanges (code, name, country)
VALUES
    ('adx', 'Abu Dhabi Securities Exchange', 'United Arab Emirates'),
    ('dfm', 'Dubai Financial Market',         'United Arab Emirates'),
    ('egx', 'Egyptian Exchange',              'Egypt')
ON CONFLICT DO NOTHING;
