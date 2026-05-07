# Beacon Screener

A self-hosted stock screener and portfolio coach for the **Dubai Financial
Market (DFM)**, **Abu Dhabi Securities Exchange (ADX)**, and **Egyptian
Exchange (EGX)**. Pulls fundamentals, technicals, valuation, and analyst data
from `stockanalysis.com` daily, scores every stock with a transparent
multi-factor model, and tells you what to **BUY**, **WATCH**, or **STAY AWAY**
from — plus what to do with what you already own.

```
                  ┌─────────────┐         ┌─────────────────┐
                  │  scheduler  │  daily  │     scraper     │
                  │  (cron)     ├────────▶│   :8001         │
                  └──────┬──────┘   11am  └────────┬────────┘
                         │                          │ writes
                         ▼                          ▼
                  ┌─────────────┐         ┌─────────────────┐
                  │ recommender │ scores  │   PostgreSQL    │
                  │   :8002     ├────────▶│ (db.magedzamzam)│
                  └─────────────┘         └────────┬────────┘
                                                   │ reads
                                          ┌────────▼────────┐    ┌──────────┐
                                          │      api        │◀──▶│ frontend │
                                          │     :8000       │    │  Next.js │
                                          └─────────────────┘    └──────────┘
                                                       ▲
                                                       │
                                                  ┌─────────┐
                                                  │  nginx  │
                                                  │  :80/443│
                                                  └─────────┘
```

## What you get

- **Daily scrape** at 11:00 Asia/Dubai over every active ticker in your
  `stocks` table — pulls 80+ fields per stock (price, valuation, financials,
  technical indicators like RSI/SMA50/SMA200, analyst targets, dividends,
  news headlines).
- **Transparent scoring**: a 7-factor weighted model (Fundamental, Valuation,
  Momentum, Technical, Analyst, Quality, Risk) with a verdict (`BUY`,
  `WATCH`, `STAY_AWAY`) and human-readable pros/cons. Tune the weights in
  `services/recommender/scoring.py`.
- **Portfolio coach**: add positions with entry price → daily verdict per
  position (`HOLD` / `BUY_MORE` / `TRIM` / `SELL` / `STOP_LOSS`) using both
  the stock score and your unrealised P/L.
- **Watchlists** for ideas you don't own yet.
- **Microservices** behind a single nginx — clean separation, independent
  scaling, easy to swap out individual pieces.
- **PWA-ready** Next.js 14 frontend with mobile bottom nav.

## Quick start

```bash
git clone https://github.com/<you>/beacon-screener.git
cd beacon-screener

# 1. Configure
cp .env.example .env
$EDITOR .env                    # set DB_PASSWORD, JWT_SECRET, PUBLIC_HOST

# 2. Apply database migration (creates auth/portfolio/scoring tables alongside
#    your existing stock schema — safe, additive, idempotent)
PGPASSWORD=$DB_PASSWORD psql -h db.magedzamzam.ae -U magedzamzam -d beacon \
    -f db/migrations/001_enhancements.sql

# 3. Build & start
docker compose up -d --build

# 4. Open it
open http://localhost              # or your PUBLIC_HOST

# 5. Register your first user, then promote to admin:
docker compose exec api python -c \
  "from shared.db import SessionLocal, User; \
   s=SessionLocal(); u=s.query(User).first(); u.is_admin=True; s.commit()"

# 6. Trigger the first scrape from the Admin tab (or):
make scrape && make score
```

## Oracle Linux 9 / RHEL / Rocky

```bash
sudo bash infra/oracle-linux/install.sh
```

That installs Docker CE, opens 80/443 in firewalld, creates a `beacon` service
user, drops a `systemd` unit so the stack auto-starts on boot. See
[`infra/oracle-linux/SELINUX.md`](infra/oracle-linux/SELINUX.md) if SELinux is
enforcing.

## Configuration

All config is via `.env` — no secrets in code. Highlights:

| Variable             | Default                | Notes                                       |
|----------------------|------------------------|---------------------------------------------|
| `DB_HOST`            | `db.magedzamzam.ae`    | PostgreSQL host                             |
| `DB_NAME`            | `beacon`               |                                             |
| `JWT_SECRET`         | (set me)               | `openssl rand -hex 48`                      |
| `DAILY_SCRAPE_CRON`  | `0 11 * * *`           | Asia/Dubai. APScheduler cron syntax.        |
| `SCRAPER_DELAY_SEC`  | `1.5`                  | Polite delay between requests               |
| `SCRAPER_CONCURRENCY`| `4`                    | Parallel requests in flight                 |
| `API_CORS_ORIGINS`   | `http://localhost:3000`| Comma-separated. Same-origin needs none.    |

## Layout

```
beacon-screener/
├── db/migrations/                Idempotent SQL migrations
├── services/
│   ├── shared/                   ORM models, settings, logging
│   ├── api/                      FastAPI public REST :8000
│   ├── scraper/                  stockanalysis.com pipeline :8001
│   ├── recommender/              Scoring engine :8002
│   └── scheduler/                APScheduler — runs daily pipeline
├── frontend/                     Next.js 14 (App Router) + Tailwind
├── infra/
│   ├── nginx/                    Reverse proxy + TLS
│   └── oracle-linux/             Bootstrap script + SELinux notes
├── .github/workflows/            CI + GHCR release
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Documentation

- [`docs/SCORING.md`](docs/SCORING.md) — Scoring model, weights, how to tune.
- [`docs/API.md`](docs/API.md) — REST endpoint reference.
- [`docs/SCHEMA.md`](docs/SCHEMA.md) — Tables added by migration 001.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — Suggested enhancements (sentiment NLP,
  alerts, peer comparison, sector rotation, backtest).

## Disclaimer

**This is not financial advice.** Verdicts are produced by a deterministic
rules-based scorer for educational and research use. Always do your own
due-diligence and consider consulting a licensed advisor.
