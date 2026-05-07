# Database schema additions (migration 001)

The migration is **additive and idempotent** — it only adds new tables and
columns alongside your existing schema (`exchanges`, `stocks`,
`stock_market_daily`, `stock_performance_daily`, `stock_valuation`,
`stock_financials`, `stock_analyst_consensus`, `stock_management`,
`stock_etf_holders`, `stock_news`, `scrape_runs`). Run it as many times as
you like; every statement is wrapped in `IF NOT EXISTS` / `ON CONFLICT DO
NOTHING`.

## New tables

| Table                       | Purpose                                                                  |
|-----------------------------|--------------------------------------------------------------------------|
| `users`                     | Auth — email, bcrypt password, `is_admin`                                |
| `watchlists`                | Per-user named lists                                                     |
| `watchlist_items`           | Stocks inside a watchlist                                                |
| `portfolio_positions`       | Open or closed holdings (qty, avg entry, notes)                          |
| `portfolio_trades`          | Append-only ledger backing each position                                 |
| `stock_recommendations`     | Daily 7-factor scoring + verdict + reasoning JSON                        |
| `position_recommendations`  | Per-position daily verdicts (`HOLD`/`BUY_MORE`/`TRIM`/`SELL`/`STOP_LOSS`) |
| `stock_technicals`          | RSI(14), SMA50/200, EMA20, MACD, ATR, volatility flags                   |
| `stock_disclosures`         | Placeholder for regulatory filings (DFM/ADX/EGX disclosure feeds)        |
| `stock_corporate_actions`   | Splits / dividends / capital changes                                     |
| `stock_latest_snapshot`     | Denormalised cache that powers the screener page (one row per stock)     |

## New columns

- `stock_news.summary`, `stock_news.sentiment_score`, `stock_news.sentiment_label`

## New views

- `v_stock_overview` — joins `stocks`, `exchanges`, and
  `stock_latest_snapshot`. The screener API uses it directly, so adding a
  column to the snapshot is the only change needed to expose it on the UI.

## Seeded rows

Three exchanges are inserted on first run if they are not already present:

| code | name                              | country |
|------|-----------------------------------|---------|
| adx  | Abu Dhabi Securities Exchange     | UAE     |
| dfm  | Dubai Financial Market            | UAE     |
| egx  | Egyptian Exchange                 | Egypt   |

## Reapplying

```bash
make migrate            # uses values from .env

# or manually:
PGPASSWORD=... psql -h db.magedzamzam.ae -U magedzamzam -d beacon \
    -f db/migrations/001_enhancements.sql
```

Future schema changes go in `db/migrations/002_*.sql`, `003_*.sql`, etc., and
should follow the same idempotent pattern.
