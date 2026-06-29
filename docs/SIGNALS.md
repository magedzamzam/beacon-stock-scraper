# Move Signals — volatility / expansion monitor

A configurable screen + API that flags symbols whose **next bar** is likely to
move at least a target amount from its open in **either direction**. It is a
"something is about to move" detector to monitor manually — **direction is not
predicted** (in testing it was a coin flip) and is added as a later layer.

## Where it lives

| Piece | Path |
|-------|------|
| Core scorer (pure, timeframe-agnostic) | `services/api/signals/move_signal.py` |
| API endpoints | `services/api/routers_signals.py` (`/signals/*`) |
| Screen | `frontend/app/signals/page.tsx` (sidebar → **Signals**) |
| Client | `api.scanMoveSignals` / `api.getMoveSignalConfig` in `frontend/lib/api.ts` |

## How the score works

The screener model that scored AUC ≈ 0.82 out-of-sample on intraday gold was
carried almost entirely by **volatility** features, so we encode that directly
instead of shipping a binary ML model:

1. `atr` = recent average true range = the volatility unit.
2. A single bar's max excursion from open has an ~exponential tail, so
   `p_base = exp(-target / atr)` — when normal range already approaches the
   target the odds are high; when the target dwarfs normal range they collapse.
3. `p_base` is nudged by an **acceleration** multiplier from the latest bar's
   range expansion and volume surge (dampened and capped).
4. `score = clamp(p_base × multiplier)`, and it **fires** when
   `score ≥ fire_threshold`.

## Endpoints

```
GET /signals/move/config        # defaults + form schema
GET /signals/move?target_mode=absolute&target_value=5&atr_period=14
                  &lookback=20&fire_threshold=0.5&exchange=DFM
                  &min_price=1&only_fired=true&limit=100
```

## Config knobs

- **target_mode**: `absolute` ($), `atr` (× ATR), `percent` (% of price).
- **target_value**: 5 by default (the "$5 move" ask).
- **atr_period**, **lookback**, **fire_threshold**.
- **exchange**, **min_price**, **only_fired**, **limit**.

## Caveats

- Bars are **daily** (`stock_history_quote`). The scorer is timeframe-agnostic
  (`compute_move_signal(bars, cfg)` takes any OHLCV list), so the same code can
  later be pointed at a 5-minute series (e.g. XAU through the broker gateway).
- A fixed **dollar** target means different things across a multi-price
  universe — prefer **atr** or **percent** mode when scanning many symbols at
  once. Absolute mode is kept as the default because it was the original ask.
- This predicts **magnitude, not direction**.

## Live streaming (Capital.com WebSocket — mainly Gold)

A `price_stream` service connects to Capital.com's WebSocket
(`wss://api-streaming-capital.backend-capital.com/connect`), subscribes to
`OHLCMarketData` (5-min candles) + `marketData` (quotes) for the configured
epics (default `GOLD`), and persists to `intraday_bar` / `stream_quote`. The
Signals screen shows a **Live — GOLD** panel that polls `/signals/move/live`
every 5s and runs the *same* scorer on the streamed closed bars.

```
price_stream  ──HTTP──►  broker_gateway /accounts/{id}/stream_session   (CST + token)
     │
     └──WSS──►  Capital.com  ──ohlc.event / quote──►  intraday_bar / stream_quote
                                                              │
                              GET /signals/move/live  ◄───────┘  (same compute_move_signal)
```

Auth is brokered through `broker_gateway` (the only service that decrypts
broker credentials). Config (env): `STREAM_ACCOUNT_ID` (required — a
`trading_accounts.id` with Capital.com creds), `STREAM_EPICS` (default `GOLD`),
`STREAM_RESOLUTION` (default `MINUTE_5`), `PING_SECONDS` (default 300, < 600).

Constraints from Capital.com: max 40 instruments per socket; 10-minute session
kept alive by pinging; stream drops if the active account is switched. Quotes
are broker bid/offer ticks (no exchange trade tape). Run migration
`019_intraday_stream.sql` before first start.
