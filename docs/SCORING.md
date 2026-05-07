# Scoring methodology

Beacon's scoring is deterministic and transparent — every verdict is the
output of seven sub-scores combined with documented weights. Tune anything
in [`services/recommender/scoring.py`](../services/recommender/scoring.py).

## Sub-scores (each 0–100)

| Sub-score    | Weight | What it measures                                                                  |
|--------------|--------|-----------------------------------------------------------------------------------|
| Fundamental  | 0.20   | Revenue growth YoY, net-income growth, operating-margin level                     |
| Valuation    | 0.20   | P/E vs. industry peers, EV/EBITDA, P/B, PEG                                       |
| Momentum     | 0.15   | 1m / 3m / 6m / YTD price returns                                                  |
| Technical    | 0.15   | RSI in healthy range, price vs. SMA-50 & SMA-200, golden-cross flag               |
| Analyst      | 0.15   | Consensus rating, average price target upside, # of covering analysts             |
| Quality      | 0.15   | ROE, ROA, debt-to-equity, current ratio, Altman Z, Piotroski F                    |
| Risk         | 0.20   | Beta, 30-day volatility, dividend cut history, 52-week drawdown — **subtracted**  |

## Composite

```
composite = 0.20·F + 0.20·V + 0.15·M + 0.15·T + 0.15·A + 0.15·Q − 0.20·R
clamped to [0, 100]
```

## Verdict thresholds

| Composite | Verdict     | Meaning                                                          |
|-----------|-------------|------------------------------------------------------------------|
| ≥ 70      | `BUY`       | Strong across most factors; few major red flags                  |
| 45–69     | `WATCH`     | Mixed signals — interesting but wait for confirmation            |
| < 45      | `STAY_AWAY` | Significant red flags — avoid until something fundamental changes|

These thresholds plus all sub-score weights live in `WEIGHTS` and
`VERDICT_THRESHOLDS` constants — change them and the next scoring run picks
up the new model. Bump `MODEL_VERSION` so old recommendations remain
attributable to the prior model.

## Position-level verdicts

For stocks you own, the recommender combines the stock verdict with your
unrealised P/L:

| Condition                                                          | Position verdict |
|--------------------------------------------------------------------|------------------|
| stock = `STAY_AWAY` and P/L ≤ −15%                                 | `STOP_LOSS`      |
| stock = `STAY_AWAY` (no stop trigger)                              | `SELL`           |
| stock = `BUY` and P/L < +5% and composite ≥ 75                     | `BUY_MORE`       |
| P/L ≥ +30% and stock ≠ `BUY`                                       | `TRIM`           |
| stock = `BUY` (otherwise)                                          | `HOLD`           |
| anything else                                                      | `HOLD`           |

The reasoning string for each position is stored in JSON inside
`position_recommendations.reasoning` so you can inspect it via the API.

## Why this design

- **Deterministic & explainable.** Every sub-score function generates pros
  and cons strings — no black-box LLM judgement at the recommendation layer.
- **Additive.** New factors slot in by adding a sub-score function, an entry
  in `WEIGHTS`, and re-normalising. No existing logic changes.
- **Bounded.** Each input metric is clamped to a sensible range before
  scoring so a single outlier (e.g., P/E of 9,000 from a one-off charge)
  cannot dominate.
- **Auditable.** `stock_recommendations.reasoning` JSONB + `model_version`
  let you replay any historic verdict and see exactly why.

## Tuning checklist

1. Edit `WEIGHTS` in `services/recommender/scoring.py` — must sum to 1.0
   for the positive factors (`Risk` is subtracted with its own weight).
2. Edit verdict cutoffs in `verdict_for(composite)`.
3. Bump `MODEL_VERSION` (e.g. `"v1.2"`).
4. Restart the recommender: `docker compose restart recommender`.
5. Rescore: from the Admin tab or `make score`.

## Caveats

- Frontier-market data on `stockanalysis.com` is sometimes thin — when a
  sub-score's inputs are missing it falls back to a neutral 50, recorded in
  the `reasoning` JSON.
- The model has **no** look-ahead protection yet — when you backtest, use
  point-in-time fundamentals, not the latest snapshot.
