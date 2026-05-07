# Roadmap — suggested enhancements

These are features the current architecture cleanly supports but that aren't
shipped yet. Each one slots into the existing service layout so you can pick
and choose.

## 1. News sentiment NLP
Fill `stock_news.sentiment_score` and `sentiment_label` with a small
HuggingFace finance-tuned model (e.g. `ProsusAI/finbert`) running inside
the scraper container, or as a 6th `sentiment` service. Then add a
`news_score` sub-score to the recommender (weight 0.05–0.10, rebalance
others). Store rolling 14-day average sentiment per stock in the
recommendation `reasoning` JSON for the UI tooltip.

## 2. Sector rotation signals
Aggregate `composite_score` per `(exchange, sector)` daily into a new
`sector_scores` table. Surface a ribbon on the dashboard highlighting the
top-5 / bottom-5 sectors, and let the screener filter for "stocks in cold
sectors heating up" (sector momentum positive but stock momentum still low).

## 3. Peer comparison
For each stock, auto-pick peers as the 5 nearest by industry + market-cap
inside the same exchange. Compute z-scores for `pe_ratio`, `ev_ebitda`,
`price_to_book`, `dividend_yield_pct` against that peer group. Show a small
peer table on the stock detail page; feed peer-relative valuation into the
Valuation sub-score.

## 4. Alert system
New table `user_alerts(user_id, stock_id, condition jsonb)` — examples:
`{"verdict_changes_to": "BUY"}`, `{"price_below": 12.5}`,
`{"rsi_above": 70}`. Add an `alerts` worker that runs at the end of the
daily pipeline, evaluates each condition, and pushes notifications via
SMTP, Telegram (`python-telegram-bot`), or webhook.

## 5. Backtest
Replay each daily `stock_recommendations` row and compute the forward
1m/3m/6m return. Materialise it into `recommendation_outcomes` and surface
a "model accuracy" panel on the Admin page (hit-rate of `BUY` verdicts vs.
benchmark, average forward return by verdict band).

## 6. Risk-adjusted portfolio metrics
Use `stock_performance_daily` to compute Sharpe / Sortino / max-drawdown on
the user's open positions vs. an equal-weighted DFM+ADX+EGX index. Display
on the portfolio page next to total P/L.

## 7. Currency normalisation
Snapshot the AED/EGP cross-rate daily, then convert all positions to a
single base currency for the totals card. Position rows still show native
currency.

## 8. Insider / institutional ownership
The `stock_management` and `stock_etf_holders` tables already exist —
expose them on the stock detail page once you start populating them.

## 9. Earnings calendar
Add `stock_corporate_actions` rows with `action_type='EARNINGS'` and a
future `action_date`. Surface a "Next earnings: in 6 days" badge on the
stock card and a calendar widget on the dashboard.

## 10. Mobile PWA + offline
The frontend already ships a manifest. Add a Workbox service-worker that
caches `/screener?...` JSON for offline browsing, and a `next-pwa` plugin
to register it. The bottom-tab nav is already mobile-tuned.

## 11. Data quality monitoring
A "freshness" column on `v_stock_overview` (`now() - last_updated`) +
admin alert when more than X% of stocks haven't been refreshed in 48h.
Useful when `stockanalysis.com` rate-limits or changes selectors.
