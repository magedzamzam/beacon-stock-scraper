-- =============================================================================
-- Migration 019: Intraday streaming (Capital.com WebSocket — mainly Gold).
-- =============================================================================
-- A long-lived price_stream service subscribes to Capital.com's WebSocket
-- (OHLCMarketData + marketData) and persists:
--   1. intraday_bar  — streamed OHLC candles per (symbol, resolution,
--      price_type, bar_ts). The forming bar is upserted on every event; it is
--      "closed" once a newer bar_ts arrives. The move-signal reads the closed
--      bars and runs the SAME scorer used for daily stocks.
--   2. stream_quote  — latest bid/offer tick per symbol, for live display.
--
-- Symbols are Capital.com epics (free-form, NOT tied to the stocks table) so
-- this works for GOLD / FX / indices that aren't in the MENA screener.
-- =============================================================================

CREATE TABLE IF NOT EXISTS intraday_bar (
    id           BIGSERIAL,
    symbol       VARCHAR(64)  NOT NULL,
    resolution   VARCHAR(16)  NOT NULL,           -- MINUTE, MINUTE_5, ...
    price_type   VARCHAR(8)   NOT NULL DEFAULT 'bid',  -- bid | ask
    bar_ts       TIMESTAMPTZ  NOT NULL,           -- candle start time
    open_price   NUMERIC(20, 6),
    high_price   NUMERIC(20, 6),
    low_price    NUMERIC(20, 6),
    close_price  NUMERIC(20, 6),
    volume       NUMERIC(24, 4),
    received_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_intraday_bar UNIQUE (symbol, resolution, price_type, bar_ts)
);

CREATE INDEX IF NOT EXISTS ix_intraday_bar_lookup
    ON intraday_bar (symbol, resolution, price_type, bar_ts DESC);

CREATE TABLE IF NOT EXISTS stream_quote (
    symbol       VARCHAR(64)  NOT NULL,
    bid          NUMERIC(20, 6),
    offer        NUMERIC(20, 6),
    bid_qty      NUMERIC(24, 4),
    ofr_qty      NUMERIC(24, 4),
    quote_ts     TIMESTAMPTZ,
    received_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol)
);
