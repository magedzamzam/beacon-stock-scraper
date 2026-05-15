"""Rule evaluators.

Each rule type is a class that knows:
  - params_schema: for the admin UI to render a form
  - evaluate(): returns AlertTriggers — candidate fires the engine deduplicates
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.db import Stock, StockQuote, StockEarningsCalendar


@dataclass
class AlertTrigger:
    """A candidate fire. Engine dedup-by-cooldown decides what actually goes out."""
    stock_id: Optional[int]
    title: str
    body: Optional[str] = None
    snapshot: dict = field(default_factory=dict)


class RuleEvaluator:
    """Base. Subclasses override params_schema (class attr) and evaluate()."""
    params_schema: list[dict[str, Any]] = []

    def __init__(self, params: dict[str, Any]):
        self.params = params

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# verdict_change
# ---------------------------------------------------------------------------
class VerdictChangeRule(RuleEvaluator):
    """Fires when a stock's verdict transitions.

    Params:
        from_verdict (optional): only fire when previous verdict was this
        to_verdict   (optional): only fire when new verdict is this
        At least one must be set.

    Detection: compares stock_quotes.verdict (current state — recommender
    writes it on every score run) to the SECOND-newest stock_scoring row's
    verdict (the previous score, before current). If different and matches
    the from/to filters, fire.

    Note: the recommender appends a new stock_scoring row each run, so we
    have running history of verdicts even though stock_quotes is collapsed
    to one row per stock.
    """
    params_schema = [
        {"name": "from_verdict", "type": "select", "label": "Previous verdict",
         "required": False, "options": ["", "STRONG_BUY", "BUY", "WATCH", "AVOID"]},
        {"name": "to_verdict", "type": "select", "label": "New verdict",
         "required": False, "options": ["", "STRONG_BUY", "BUY", "WATCH", "AVOID"]},
    ]

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        from_v = (self.params.get("from_verdict") or "").upper() or None
        to_v = (self.params.get("to_verdict") or "").upper() or None
        if not (from_v or to_v):
            return []

        rows = session.execute(text("""
            WITH ranked AS (
                SELECT stock_id, verdict, scored_at,
                       row_number() OVER (PARTITION BY stock_id
                                          ORDER BY scored_at DESC) AS r
                FROM stock_scoring
            )
            SELECT q.stock_id, q.verdict AS current_verdict,
                   p.verdict AS prev_verdict, s.ticker, s.company_name,
                   q.current_price, q.composite_score
            FROM stock_quotes q
            JOIN stocks s ON s.id = q.stock_id
            LEFT JOIN ranked p ON p.stock_id = q.stock_id AND p.r = 2
            WHERE q.verdict IS NOT NULL
              AND p.verdict IS NOT NULL
              AND q.verdict <> p.verdict
        """)).all()

        out = []
        for r in rows:
            if from_v and r.prev_verdict != from_v:
                continue
            if to_v and r.current_verdict != to_v:
                continue
            out.append(AlertTrigger(
                stock_id=r.stock_id,
                title=f"{r.ticker} → {r.current_verdict} (was {r.prev_verdict})",
                body=(f"{r.company_name} ({r.ticker}) verdict changed from "
                      f"{r.prev_verdict} to {r.current_verdict}. "
                      f"Score: {r.composite_score}. Price: {r.current_price}."),
                snapshot={
                    "ticker": r.ticker,
                    "current_verdict": r.current_verdict,
                    "previous_verdict": r.prev_verdict,
                    "composite_score": float(r.composite_score) if r.composite_score is not None else None,
                    "current_price": float(r.current_price) if r.current_price is not None else None,
                },
            ))
        return out


# ---------------------------------------------------------------------------
# score_threshold
# ---------------------------------------------------------------------------
class ScoreThresholdRule(RuleEvaluator):
    """Fires for any stock currently at-or-above a composite score.

    'Currently at-or-above' semantics: if the cooldown is 1 hour, the same
    stock won't re-alert for 1 hour even if it stays above. For 'just crossed'
    semantics, use verdict_change instead.
    """
    params_schema = [
        {"name": "min_score", "type": "number", "label": "Minimum composite score",
         "required": True, "default": 80, "min": 0, "max": 100},
        {"name": "verdict", "type": "select", "label": "Also require verdict",
         "required": False, "options": ["", "STRONG_BUY", "BUY", "WATCH", "AVOID"]},
    ]

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        min_score = float(self.params.get("min_score") or 0)
        verdict = (self.params.get("verdict") or "").upper() or None

        q = (select(StockQuote, Stock.ticker, Stock.company_name)
             .join(Stock, Stock.id == StockQuote.stock_id)
             .where(StockQuote.composite_score >= min_score))
        if verdict:
            q = q.where(StockQuote.verdict == verdict)

        out = []
        for sq, ticker, company in session.execute(q).all():
            out.append(AlertTrigger(
                stock_id=sq.stock_id,
                title=f"{ticker} score {float(sq.composite_score):.0f} ≥ {min_score:.0f}",
                body=(f"{company} ({ticker}) scores {float(sq.composite_score):.1f} "
                      f"({sq.verdict}). Price: {sq.current_price}."),
                snapshot={
                    "ticker": ticker,
                    "composite_score": float(sq.composite_score) if sq.composite_score is not None else None,
                    "verdict": sq.verdict,
                    "current_price": float(sq.current_price) if sq.current_price is not None else None,
                },
            ))
        return out


# ---------------------------------------------------------------------------
# earnings_soon
# ---------------------------------------------------------------------------
class EarningsSoonRule(RuleEvaluator):
    """Fires for stocks with earnings within N days.

    Pair with a 24h cooldown for a "daily digest of upcoming earnings".
    """
    params_schema = [
        {"name": "days", "type": "number", "label": "Within next (days)",
         "required": True, "default": 3, "min": 0, "max": 90},
        {"name": "earnings_time", "type": "select", "label": "Earnings time",
         "required": False,
         "options": ["", "Before Open", "After Close", "During Market"]},
    ]

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        days = int(self.params.get("days") or 0)
        earnings_time = self.params.get("earnings_time") or None
        today = date.today()
        upper = today + timedelta(days=days)

        q = (select(StockEarningsCalendar, Stock.ticker, Stock.company_name)
             .join(Stock, Stock.id == StockEarningsCalendar.stock_id)
             .where(StockEarningsCalendar.next_earnings_date.between(today, upper)))
        if earnings_time:
            q = q.where(StockEarningsCalendar.earnings_time == earnings_time)

        out = []
        for ec, ticker, company in session.execute(q).all():
            d = (ec.next_earnings_date - today).days
            when = "today" if d == 0 else "tomorrow" if d == 1 else f"in {d} days"
            t_str = f" ({ec.earnings_time})" if ec.earnings_time else ""
            out.append(AlertTrigger(
                stock_id=ec.stock_id,
                title=f"{ticker} earnings {when}",
                body=(f"{company} ({ticker}) reports earnings "
                      f"{ec.next_earnings_date.isoformat()}{t_str}. "
                      f"Est. EPS: {ec.est_eps}."),
                snapshot={
                    "ticker": ticker,
                    "next_earnings_date": ec.next_earnings_date.isoformat(),
                    "earnings_time": ec.earnings_time,
                    "days_until": d,
                },
            ))
        return out


# ---------------------------------------------------------------------------
# price_change_pct
# ---------------------------------------------------------------------------
class PriceChangePctRule(RuleEvaluator):
    """Fires when today's price change crosses a threshold."""
    params_schema = [
        {"name": "threshold_pct", "type": "number", "label": "Threshold (%)",
         "required": True, "default": 5.0, "min": 0, "max": 100, "step": 0.1},
        {"name": "direction", "type": "select", "label": "Direction",
         "required": False, "default": "either",
         "options": ["either", "up", "down"]},
    ]

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        thr = float(self.params.get("threshold_pct") or 0)
        direction = (self.params.get("direction") or "either").lower()

        q = (select(StockQuote, Stock.ticker, Stock.company_name)
             .join(Stock, Stock.id == StockQuote.stock_id)
             .where(StockQuote.change_pct.is_not(None)))
        if direction == "up":
            q = q.where(StockQuote.change_pct >= thr)
        elif direction == "down":
            q = q.where(StockQuote.change_pct <= -thr)
        else:
            q = q.where((StockQuote.change_pct >= thr) | (StockQuote.change_pct <= -thr))

        out = []
        for sq, ticker, company in session.execute(q).all():
            chg = float(sq.change_pct)
            arrow = "▲" if chg > 0 else "▼"
            out.append(AlertTrigger(
                stock_id=sq.stock_id,
                title=f"{ticker} {arrow} {abs(chg):.1f}%",
                body=(f"{company} ({ticker}) moved {chg:+.2f}% today. "
                      f"Price: {sq.current_price} (prev close {sq.prev_close})."),
                snapshot={
                    "ticker": ticker,
                    "change_pct": chg,
                    "current_price": float(sq.current_price) if sq.current_price is not None else None,
                },
            ))
        return out


# ---------------------------------------------------------------------------
# custom_sql — power-user escape hatch
# ---------------------------------------------------------------------------
class CustomSqlRule(RuleEvaluator):
    """Run an admin-supplied SELECT; each row → an alert trigger.

    Must return columns named at minimum:
        stock_id (int, nullable)
        title    (text)
    Optional:
        body     (text)
        ticker   (text — used in dedup if stock_id is null)

    Safety: belt-and-suspenders — accept only SELECT/WITH, set the
    transaction READ ONLY at the DB level, cap rows at 500. Beacon is a
    single-trusted-admin tool; this is fine.
    """
    params_schema = [
        {"name": "sql", "type": "textarea", "label": "SQL (SELECT only)",
         "required": True,
         "placeholder": "SELECT s.id AS stock_id, s.ticker, 'Alert' AS title "
                        "FROM stocks s JOIN stock_quotes q ON q.stock_id = s.id "
                        "WHERE q.composite_score > 90"},
    ]

    def evaluate(self, session: Session) -> list[AlertTrigger]:
        sql = (self.params.get("sql") or "").strip()
        if not sql:
            return []
        first_token = sql.lstrip("(").split(None, 1)[0].upper() if sql else ""
        if first_token not in ("SELECT", "WITH"):
            raise ValueError("custom_sql must start with SELECT or WITH")

        session.execute(text("SET LOCAL TRANSACTION READ ONLY"))
        rows = session.execute(text(f"SELECT * FROM ({sql}) _x LIMIT 500")).mappings().all()

        out = []
        for r in rows:
            sid = r.get("stock_id")
            ticker = r.get("ticker") or "?"
            title = r.get("title") or f"Custom alert · {ticker}"
            body = r.get("body")
            snap = {}
            for k, v in r.items():
                if k in ("title", "body"):
                    continue
                if isinstance(v, (date, datetime)):
                    snap[k] = v.isoformat()
                else:
                    # JSONB needs JSON-safe values; convert Decimal/etc
                    try:
                        import json
                        json.dumps(v)
                        snap[k] = v
                    except (TypeError, ValueError):
                        snap[k] = str(v)
            out.append(AlertTrigger(
                stock_id=int(sid) if sid is not None else None,
                title=str(title)[:200],
                body=str(body) if body is not None else None,
                snapshot=snap,
            ))
        return out


RULE_REGISTRY: dict[str, type[RuleEvaluator]] = {
    "verdict_change":    VerdictChangeRule,
    "score_threshold":   ScoreThresholdRule,
    "earnings_soon":     EarningsSoonRule,
    "price_change_pct":  PriceChangePctRule,
    "custom_sql":        CustomSqlRule,
}

_LABELS = {
    "verdict_change":   "Verdict change",
    "score_threshold":  "Score threshold",
    "earnings_soon":    "Earnings soon",
    "price_change_pct": "Price change %",
    "custom_sql":       "Custom SQL",
}
_DESCRIPTIONS = {
    "verdict_change":   "Fires when a stock's verdict transitions (e.g. WATCH → BUY).",
    "score_threshold":  "Fires for stocks at-or-above a composite score.",
    "earnings_soon":    "Fires for stocks with earnings within N days.",
    "price_change_pct": "Fires when today's price change crosses a threshold.",
    "custom_sql":       "Power user: arbitrary SELECT; each row becomes a trigger.",
}


def get_rule_meta() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": _LABELS.get(key, key),
            "description": _DESCRIPTIONS.get(key, ""),
            "params_schema": cls.params_schema,
        }
        for key, cls in RULE_REGISTRY.items()
    ]
