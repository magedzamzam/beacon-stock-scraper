# REST API

Base URL behind nginx: `/api`. Direct (dev): `http://localhost:8000`.

All endpoints except the auth pair require a `Bearer` token in the
`Authorization` header. Tokens are issued by `/auth/login` and
`/auth/register`, expire after `JWT_EXPIRE_HOURS`, and are signed with
`JWT_SECRET` (HS256).

## Auth

| Method | Path                | Body                                                    | Returns                |
|--------|---------------------|---------------------------------------------------------|------------------------|
| POST   | `/auth/register`    | `{ email, password, display_name? }`                    | `{ access_token, user }` |
| POST   | `/auth/login`       | `application/x-www-form-urlencoded` `username=&password=` | `{ access_token, user }` |
| GET    | `/auth/me`          | —                                                       | `User`                 |

## Stocks

| Method | Path                                              | Notes                                                    |
|--------|---------------------------------------------------|----------------------------------------------------------|
| GET    | `/stocks`                                         | Query params: `q, exchange, sector, industry, verdict, min_score, max_pe, min_dividend, sort_by, sort_dir, limit, offset` |
| GET    | `/stocks/filters`                                 | Returns the option lists for filter dropdowns            |
| GET    | `/stocks/{exchange}/{ticker}`                     | Full detail (fundamentals, technicals, analyst)          |
| GET    | `/stocks/{exchange}/{ticker}/score`               | Latest scoring breakdown with pros/cons                  |
| GET    | `/stocks/{exchange}/{ticker}/price-history?days=` | Daily close + volume series                              |
| GET    | `/stocks/{exchange}/{ticker}/news?limit=`         | News headlines from `stock_news`                         |
| POST   | `/stocks/{exchange}/{ticker}/refresh`             | Trigger an on-demand scrape via the scraper service      |

## Watchlists

| Method | Path                                              |
|--------|---------------------------------------------------|
| GET    | `/watchlists`                                     |
| POST   | `/watchlists`                                     |
| DELETE | `/watchlists/{id}`                                |
| POST   | `/watchlists/{id}/items`                          |
| DELETE | `/watchlists/{id}/items/{item_id}`                |

## Portfolio

| Method | Path                          | Notes                                                   |
|--------|-------------------------------|---------------------------------------------------------|
| GET    | `/portfolio`                  | Open positions + per-position verdicts and totals       |
| POST   | `/portfolio`                  | `{ stock_id, quantity, avg_entry_price, entry_date?, notes? }` |
| DELETE | `/portfolio/{id}`             | Soft close (`is_open=false`)                            |

## Admin (requires `is_admin`)

| Method | Path                       | Notes                                              |
|--------|----------------------------|----------------------------------------------------|
| GET    | `/admin/status`            | Counts + last 20 scrape runs                       |
| POST   | `/admin/scrape-all`        | Proxy to scraper                                   |
| POST   | `/admin/score-all`         | Proxy to recommender (runs in background)          |
| POST   | `/admin/score-portfolio`   | Score every open position now                      |

## Error format

```json
{ "detail": "human-readable message" }
```

`401` triggers an automatic redirect to `/login` from the frontend.

## Internal services

The two backend services are not exposed by nginx. The api and scheduler
talk to them via the internal Docker network:

- `http://scraper:8001`     `POST /scrape/all`, `POST /scrape/{exchange}/{ticker}`
- `http://recommender:8002` `POST /score/all`, `POST /score/portfolio`,
  `POST /score/all/sync`, `POST /score/portfolio/sync`
