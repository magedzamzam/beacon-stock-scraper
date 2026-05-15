"""Scoring engine.

Philosophy
----------
Every component score lives on a 0..100 scale. We then combine them into a
weighted composite score, and bucket the composite into BUY / WATCH / STAY_AWAY.

The weights are tunable in WEIGHTS below. Each scoring function is small and
pure so it is easy to test, audit, and tweak.

Sub-scores
----------
  fundamental_score : profitability + growth (revenue, margins, ROE)
  valuation_score   : are we paying a fair price (PE, PB, EV/EBITDA, dividend)
  momentum_score    : returns over multiple horizons (1m / 6m / 1y)
  technical_score   : RSI sweet-spot, price vs SMA50/SMA200
  analyst_score     : consensus rating + upside vs target price
  quality_score     : balance-sheet strength (debt/equity, current ratio, cash)
  risk_score        : penalty (high beta, drawdown, low free-float)

Composite = sum(weight_i * sub_score_i) - weight_risk * risk_score

Model version
-------------
Bump MODEL_VERSION whenever weights, thresholds, or sub-score logic change so
historical recommendations stay attributable to the model that produced them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


MODEL_VERSION = "v1.1"

WEIGHTS = {
    "fundamental": 0.20,
    "valuation":   0.20,
    "momentum":    0.15,
    "technical":   0.15,
    "analyst":     0.15,
    "quality":     0.15,
    # risk is subtracted; magnitude controls penalty strength
    "risk":        0.20,
}


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def to_float(x) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _normalise_pct(x: Optional[float]) -> Optional[float]:
    """Defensive percent-vs-fraction normalisation.

    Many ingestion paths get this wrong: they compute (target - price) / price
    which yields 0.14 (a fraction), then store it in a column whose downstream
    consumers expect it to mean "14 percent". When abs(x) <= 1 we treat it as a
    fraction and multiply by 100. This is safe because no real analyst-upside
    value is ever between -1% and +1% for a stock anyone screens (and if it is,
    a single-percent rounding error doesn't change the verdict).
    """
    if x is None:
        return None
    return x * 100 if -1.0 <= x <= 1.0 else x


@dataclass
class StockMetrics:
    """All metrics needed to score one stock. Anything unknown is None."""
    # fundamentals
    revenue_growth_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    eps_growth_pct: Optional[float] = None
    # valuation
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    # momentum
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    # technical
    rsi_14: Optional[float] = None
    last_close: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    # analyst
    analyst_rating: Optional[str] = None  # 'Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell'
    analyst_count: Optional[int] = None
    analyst_upside_pct: Optional[float] = None
    # quality
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    fcf_yield: Optional[float] = None
    # risk
    beta: Optional[float] = None
    free_float_pct: Optional[float] = None
    cash_per_share: Optional[float] = None


@dataclass
class ScoreResult:
    fundamental: float = 50.0
    valuation:   float = 50.0
    momentum:    float = 50.0
    technical:   float = 50.0
    analyst:     float = 50.0
    quality:     float = 50.0
    risk:        float = 50.0
    composite:   float = 50.0
    verdict:     str = "WATCH"
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-scoring functions — each returns 0..100
# ---------------------------------------------------------------------------
def score_fundamental(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.revenue_growth_pct is not None:
        s = 50 + min(50, m.revenue_growth_pct * 1.5)
        parts.append(clamp(s))
        if m.revenue_growth_pct > 15: pros.append(f"Strong revenue growth ({m.revenue_growth_pct:.1f}%)")
        elif m.revenue_growth_pct < 0: cons.append(f"Revenue declining ({m.revenue_growth_pct:.1f}%)")

    if m.net_margin_pct is not None:
        # 33% margin = 100 by default; cap reward when margin > 50% which
        # almost always indicates a financial / investment company whose net
        # margin isn't comparable to industrial peers (e.g. WAHA's investment-
        # gain-driven 65% margin).
        if m.net_margin_pct > 50:
            s = 80.0
        else:
            s = clamp(m.net_margin_pct * 3)
        parts.append(s)
        if 20 < m.net_margin_pct <= 50: pros.append(f"High net margin ({m.net_margin_pct:.1f}%)")
        elif m.net_margin_pct < 5: cons.append(f"Thin net margin ({m.net_margin_pct:.1f}%)")

    if m.roe_pct is not None:
        s = clamp(m.roe_pct * 4)  # 25% ROE = 100
        parts.append(s)
        if m.roe_pct > 15: pros.append(f"ROE {m.roe_pct:.1f}% — strong")
        elif m.roe_pct < 5: cons.append(f"ROE {m.roe_pct:.1f}% — weak")

    if m.eps_growth_pct is not None:
        s = 50 + min(50, m.eps_growth_pct * 1.2)
        parts.append(clamp(s))

    return sum(parts) / len(parts) if parts else 50.0


def score_valuation(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.pe_ratio is not None and m.pe_ratio > 0:
        # PE of 15 ≈ 80, PE of 30 ≈ 50, PE of 60 ≈ 20.
        # Cap "too cheap" reward — PE under ~5 usually indicates one-off
        # earnings spikes or distress; don't max the score on those.
        if m.pe_ratio < 5:
            s = 75.0
        else:
            s = 100 - clamp((m.pe_ratio - 10) * 2)
        parts.append(clamp(s))
        if 5 <= m.pe_ratio < 12: pros.append(f"Cheap on P/E ({m.pe_ratio:.1f})")
        elif m.pe_ratio > 35: cons.append(f"Expensive on P/E ({m.pe_ratio:.1f})")

    if m.pb_ratio is not None and m.pb_ratio > 0:
        s = 100 - clamp((m.pb_ratio - 1) * 20)
        parts.append(clamp(s))
        if m.pb_ratio < 1.0: pros.append(f"Below book value (P/B {m.pb_ratio:.2f})")
        elif m.pb_ratio > 5: cons.append(f"High P/B ({m.pb_ratio:.2f})")

    if m.ev_ebitda is not None and m.ev_ebitda > 0:
        s = 100 - clamp((m.ev_ebitda - 6) * 4)
        parts.append(clamp(s))

    if m.dividend_yield_pct is not None:
        s = clamp(m.dividend_yield_pct * 12)  # 8% yield = 96
        parts.append(s)
        if m.dividend_yield_pct >= 5: pros.append(f"Attractive dividend yield ({m.dividend_yield_pct:.2f}%)")

    return sum(parts) / len(parts) if parts else 50.0


def score_momentum(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []
    for label, val, weight in [
        ("1M", m.return_1m, 0.15), ("3M", m.return_3m, 0.20),
        ("6M", m.return_6m, 0.30), ("1Y", m.return_1y, 0.35),
    ]:
        if val is None:
            continue
        # +30% = 100, 0% = 50, -30% = 0
        s = clamp(50 + val * (50 / 30))
        parts.append(s * weight * 4)  # *4 to scale weights back to 0..100

    if m.return_1y is not None:
        if m.return_1y > 25: pros.append(f"Strong 1Y momentum (+{m.return_1y:.1f}%)")
        elif m.return_1y < -15: cons.append(f"Weak 1Y momentum ({m.return_1y:.1f}%)")

    return clamp(sum(parts) / max(1, len(parts))) if parts else 50.0


def score_technical(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.rsi_14 is not None:
        # 30-70 healthy zone, <30 oversold (potential bounce), >70 overbought
        if m.rsi_14 < 30:
            s = 75; pros.append(f"Oversold RSI ({m.rsi_14:.0f})")
        elif m.rsi_14 > 70:
            s = 30; cons.append(f"Overbought RSI ({m.rsi_14:.0f})")
        else:
            s = 60
        parts.append(s)

    if m.last_close and m.sma_50 and m.sma_200:
        above_50 = m.last_close > m.sma_50
        above_200 = m.last_close > m.sma_200
        golden = m.sma_50 > m.sma_200
        s = 50 + (15 if above_50 else -15) + (15 if above_200 else -15) + (10 if golden else -10)
        parts.append(clamp(s))
        if above_50 and above_200 and golden:
            pros.append("Above 50/200-day SMA with golden cross")
        elif not above_200 and not golden:
            cons.append("Below 200-day SMA, death-cross territory")

    if m.last_close and m.week_52_high and m.week_52_low:
        rng = m.week_52_high - m.week_52_low
        if rng > 0:
            pos = (m.last_close - m.week_52_low) / rng  # 0..1
            s = 30 + pos * 40   # near low → 30, near high → 70
            parts.append(clamp(s))

    return sum(parts) / len(parts) if parts else 50.0


def score_analyst(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []
    rating_map = {
        "strong buy": 95, "buy": 80, "outperform": 75,
        "hold": 50, "neutral": 50,
        "underperform": 25, "sell": 15, "strong sell": 5,
    }
    if m.analyst_rating:
        s = rating_map.get(m.analyst_rating.lower(), 50)
        parts.append(s)
        if s >= 75: pros.append(f"Analyst consensus: {m.analyst_rating}")
        elif s <= 25: cons.append(f"Analyst consensus: {m.analyst_rating}")

    # Auto-correct fraction-vs-percent: incoming 0.14 means "14%", not "0.14%".
    upside = _normalise_pct(m.analyst_upside_pct)
    if upside is not None:
        # +30% upside = 95, 0% = 50, -20% = 10
        s = clamp(50 + upside * 1.5)
        parts.append(s)
        if upside > 20: pros.append(f"Analyst upside +{upside:.1f}%")
        elif upside < -10: cons.append(f"Analyst downside {upside:.1f}%")

    if m.analyst_count is not None and m.analyst_count >= 5:
        # boost confidence when many analysts cover the name
        if parts:
            avg = sum(parts) / len(parts)
            return clamp(avg + 5)
    return sum(parts) / len(parts) if parts else 50.0


def score_quality(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.debt_to_equity is not None:
        # Negative-equity (insolvency) — deeply punitive.
        if m.debt_to_equity < 0:
            s = 5.0
            cons.append("Negative equity — solvency risk")
        else:
            # 0 = 100, 1 = 60, 2 = 30, 3+ = 10
            s = clamp(100 - m.debt_to_equity * 30)
            if m.debt_to_equity < 0.3: pros.append(f"Low leverage (D/E {m.debt_to_equity:.2f})")
            elif m.debt_to_equity > 2: cons.append(f"High leverage (D/E {m.debt_to_equity:.2f})")
        parts.append(s)

    if m.current_ratio is not None:
        # 1.5-3 sweet spot
        if 1.5 <= m.current_ratio <= 3.5: s = 85
        elif m.current_ratio < 1.0: s = 25
        else: s = 60
        parts.append(s)
        if m.current_ratio < 1: cons.append(f"Liquidity tight (current ratio {m.current_ratio:.2f})")
        
    if m.fcf_yield is not None:
        if fcf_yield > 0.08:
            # Strong: > 8% yield
            s = 100.0
            pros.append(f"Strong cash generator (FCF Yield {fcf_yield:.1%})")
        elif fcf_yield > 0.03:
            # Neutral/Stable: 3% - 8%
            s = 70.0
        elif 0 <= fcf_yield <= 0.03:
            # Weak: 0% - 3%
            s = 40.0
            cons.append(f"Lean cash flow (FCF Yield {fcf_yield:.1%})")
        else:
            # Critical: Negative FCF
            s = 10.0
            cons.append(f"Negative Free Cash Flow — burning capital")
            
        parts.append(s)

    return sum(parts) / len(parts) if parts else 50.0


def score_risk(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    """Risk = penalty. Higher = riskier (we will SUBTRACT this from composite)."""
    parts: list[float] = []

    if m.beta is not None:
        s = clamp(abs(m.beta - 1) * 30)
        parts.append(s)
        if abs(m.beta) > 1.5: cons.append(f"High beta ({m.beta:.2f})")

    if m.free_float_pct is not None:
        # under 15% free float = illiquid risk
        if m.free_float_pct < 15:
            parts.append(70); cons.append(f"Low free float ({m.free_float_pct:.1f}%)")
        elif m.free_float_pct < 25:
            parts.append(40)
        else:
            parts.append(15)

    if m.last_close and m.week_52_high:
        drawdown = (m.week_52_high - m.last_close) / m.week_52_high * 100
        if drawdown > 30:
            parts.append(70); cons.append(f"Drawdown {drawdown:.0f}% from 52w high")
        elif drawdown > 15:
            parts.append(40)
        else:
            parts.append(15)
    
    if m.cash_per_share is not None and m.last_close:
        # Calculate Net Cash as a % of Stock Price
        # A negative percentage means debt exceeds cash
        cash_position_pct = (m.cash_per_share / m.last_close) * 100
        
        if cash_position_pct < -50:
            # Critical: Debt is > 50% of the market cap
            s = 90.0
            cons.append(f"Heavy net debt (Net Cash/Price: {cash_position_pct:.1f}%)")
        elif cash_position_pct < -10:
            # Weak/High Risk: Significant leverage
            s = 60.0
            cons.append(f"Significant leverage (Net Cash/Price: {cash_position_pct:.1f}%)")
        elif cash_position_pct < 0:
            # Neutral: Manageable debt
            s = 30.0
        else:
            # Strong: Company is debt-free (Net Cash Positive)
            s = 5.0
            pros.append(f"Net cash positive ({m.cash_per_share:.2f}/share)")
            
        parts.append(s)
        
    return sum(parts) / len(parts) if parts else 30.0


# ---------------------------------------------------------------------------
# Final composite
# ---------------------------------------------------------------------------
def compute_score(m: StockMetrics) -> ScoreResult:
    pros: list[str] = []
    cons: list[str] = []

    fund = score_fundamental(m, pros, cons)
    val  = score_valuation(m, pros, cons)
    mom  = score_momentum(m, pros, cons)
    tech = score_technical(m, pros, cons)
    ana  = score_analyst(m, pros, cons)
    qual = score_quality(m, pros, cons)
    risk = score_risk(m, pros, cons)

    composite = (
        WEIGHTS["fundamental"] * fund +
        WEIGHTS["valuation"]   * val  +
        WEIGHTS["momentum"]    * mom  +
        WEIGHTS["technical"]   * tech +
        WEIGHTS["analyst"]     * ana  +
        WEIGHTS["quality"]     * qual
    ) - WEIGHTS["risk"] * (risk - 30)  # subtract excess-risk
    composite = clamp(composite)

    if composite >= 70:
        verdict = "BUY"
    elif composite >= 45:
        verdict = "WATCH"
    else:
        verdict = "STAY_AWAY"

    return ScoreResult(
        fundamental=round(fund, 2), valuation=round(val, 2), momentum=round(mom, 2),
        technical=round(tech, 2), analyst=round(ana, 2), quality=round(qual, 2),
        risk=round(risk, 2), composite=round(composite, 2),
        verdict=verdict, pros=pros[:8], cons=cons[:8],
    )


# ---------------------------------------------------------------------------
# Per-position recommendation (HOLD / SELL / BUY MORE / TRIM / STOP_LOSS)
# ---------------------------------------------------------------------------
@dataclass
class PositionContext:
    avg_entry_price: float
    current_price: float
    stock_score: ScoreResult


def recommend_position(ctx: PositionContext) -> dict:
    pl_pct = (ctx.current_price - ctx.avg_entry_price) / ctx.avg_entry_price * 100
    s = ctx.stock_score

    reasoning: list[str] = [f"Unrealized P/L: {pl_pct:+.2f}%"]
    confidence = 60.0

    # Hard rules
    if pl_pct <= -15 and s.verdict == "STAY_AWAY":
        verdict = "STOP_LOSS"
        confidence = 85
        reasoning.append("Down >15% AND stock now scores STAY_AWAY — cut losses.")
    elif pl_pct >= 30 and s.verdict in ("WATCH", "STAY_AWAY"):
        verdict = "TRIM"
        confidence = 70
        reasoning.append("Up >30% but score has weakened — take partial profits.")
    elif s.verdict == "STAY_AWAY":
        verdict = "SELL"
        confidence = 75
        reasoning.append("Stock now flagged STAY_AWAY — exit.")
    elif s.verdict == "BUY" and pl_pct < 5 and s.composite >= 75:
        verdict = "BUY_MORE"
        confidence = 70
        reasoning.append(f"BUY signal (score {s.composite}) and entry still attractive.")
    elif s.verdict == "BUY":
        verdict = "HOLD"
        confidence = 75
        reasoning.append("Fundamentals & technicals still constructive — keep.")
    else:
        verdict = "HOLD"
        confidence = 55
        reasoning.append("Score is WATCH — wait for clearer signal.")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "unrealized_pl_pct": round(pl_pct, 2),
        "reasoning": {"notes": reasoning, "pros": s.pros, "cons": s.cons},
    }