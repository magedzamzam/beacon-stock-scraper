"""Scoring engine — v2.0 (Sector-Aware, Enhanced Risk, New Indicators).

Philosophy
----------
Every component score lives on a 0..100 scale. We then combine them into a
weighted composite score, and bucket the composite into BUY / WATCH / STAY_AWAY.

The weights are tunable in WEIGHTS below. Each scoring function is small and
pure so it is easy to test, audit, and tweak.

Sub-scores
----------
  fundamental_score : profitability + growth (revenue, margins, ROE, EPS)
  valuation_score   : fair price (PE, PB, EV/EBITDA, P/S, EV/Sales, PEG, dividend)
  momentum_score    : returns over multiple horizons (1m / 3m / 6m / 1y)
  technical_score   : RSI sweet-spot, price vs SMA50/SMA200, 52w position
  analyst_score     : consensus rating + upside vs target price
  quality_score     : balance-sheet strength (debt/equity, current ratio, FCF)
  risk_score        : penalty (high beta, drawdown, low free-float, cash position,
                     earnings volatility, concentration risk)

Composite = sum(weight_i * sub_score_i) - weight_risk * (risk - 30)

Sector Awareness
----------------
Every metric that varies materially by sector is scored relative to sector
benchmarks (see SECTOR_GUIDELINES).  This prevents e.g. praising a bank for
"low D/E" or penalising a software company for "high P/E".

Model version
-------------
Bump MODEL_VERSION whenever weights, thresholds, or sub-score logic change so
historical recommendations stay attributable to the model that produced them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


MODEL_VERSION = "v2.0"

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

# ---------------------------------------------------------------------------
# 1.1  Sector Guidelines — Net Margin, Debt/Equity, P/E Ratio
# ---------------------------------------------------------------------------
# Sources: NYU Stern margin data, fullratio.com D/E by industry,
#          CSIMarket sector valuations, aggregated 2024-2026 market data.
#
# Each entry: (median_net_margin_pct, median_debt_to_equity, median_pe_ratio,
#              pe_cheap_threshold, pe_expensive_threshold)
#
# "cheap"  = below this P/E the stock is considered attractively valued
#            (sector-adjusted; e.g. Tech 18 vs Utilities 12)
# "expensive" = above this P/E the stock is considered overvalued
#
# For null/empty/unknown sectors we fall back to broad-market medians.
# ---------------------------------------------------------------------------

SECTOR_GUIDELINES = {
    # sector_name: (net_margin_med, d_e_med, pe_med, pe_cheap, pe_expensive)
    "Energy":               (8.0,   0.70,  11.0,  7.0,  18.0),
    "Consumer Discretionary":(6.5,   0.85,  18.0,  12.0, 28.0),
    "Technology":           (15.0,  0.35,  25.0,  18.0, 38.0),
    "Industrials":          (7.5,   0.65,  17.0,  11.0, 26.0),
    "Healthcare":           (10.0,  0.45,  20.0,  14.0, 30.0),
    "Communication Services":(10.0, 0.80,  16.0,  10.0, 24.0),
    "Financials":           (18.0,  1.20,  12.0,  8.0,  18.0),
    "Consumer Staples":     (7.0,   0.75,  19.0,  13.0, 28.0),
    "Real Estate":          (22.0,  1.40,  14.0,  9.0,  22.0),
    "Materials":            (7.0,   0.60,  15.0,  10.0, 24.0),
    "Utilities":            (10.0,  1.30,  16.0,  11.0, 24.0),
}

# Broad-market fallback (used when sector is None, empty, or unrecognised)
MARKET_MEDIAN = (9.0, 0.65, 18.0, 11.0, 28.0)


def _sector_guidelines(sector: Optional[str]):
    """Return the guideline tuple for a given sector (or market fallback)."""
    if not sector:
        return MARKET_MEDIAN
    return SECTOR_GUIDELINES.get(sector.strip(), MARKET_MEDIAN)


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
    # sector
    sector: Optional[str] = None

    # fundamentals
    revenue_growth_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    eps_growth_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None          # NEW v2.0
    revenue_growth_3y_cagr: Optional[float] = None     # NEW v2.0
    earnings_volatility: Optional[float] = None        # NEW v2.0 (std dev YoY EPS)

    # valuation
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ps_ratio: Optional[float] = None                   # NEW v2.0 — stock_fin_ratios.ps_ratio
    ev_sales: Optional[float] = None                   # NEW v2.0 — stock_fin_ratios.ev_sales
    peg_ratio: Optional[float] = None                  # NEW v2.0 — stock_fin_ratios.peg_ratio
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
    analyst_rating: Optional[str] = None
    analyst_count: Optional[int] = None
    analyst_upside_pct: Optional[float] = None

    # quality
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    fcf_yield: Optional[float] = None
    roic_pct: Optional[float] = None                   # NEW v2.0
    cfo_to_net_income: Optional[float] = None          # NEW v2.0
    interest_coverage: Optional[float] = None          # NEW v2.0

    # risk
    beta: Optional[float] = None
    free_float_pct: Optional[float] = None
    cash_per_share: Optional[float] = None
    altman_z_score: Optional[float] = None             # NEW v2.0
    insider_ownership_pct: Optional[float] = None      # NEW v2.0


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
    data_completeness_pct: float = 0.0                 # NEW v2.0
    confidence: str = "MEDIUM"                         # NEW v2.0


# ---------------------------------------------------------------------------
# 1.1  Sector-aware helpers
# ---------------------------------------------------------------------------

def _sector_adjusted_pe_score(pe: float, sector: Optional[str]) -> float:
    """Return a 0..100 score for P/E relative to sector norms."""
    _, _, _, cheap, expensive = _sector_guidelines(sector)
    if pe < 0:
        return 30.0   # negative earnings = distressed
    if pe < cheap * 0.6:
        # Very cheap — possible value trap or one-off earnings spike
        return 70.0
    # Linear interpolation: cheap = 85, median = 60, expensive = 25
    if pe <= cheap:
        return 85.0 - (pe - cheap * 0.6) / (cheap * 0.4) * 15.0
    elif pe <= expensive:
        return 85.0 - (pe - cheap) / (expensive - cheap) * 60.0
    else:
        return max(10.0, 25.0 - (pe - expensive) / expensive * 15.0)


def _sector_adjusted_de_score(de: float, sector: Optional[str]) -> float:
    """Return a 0..100 score for Debt/Equity relative to sector norms."""
    _, med, _, _, _ = _sector_guidelines(sector)
    if de < 0:
        return 5.0   # negative equity = insolvency risk
    # Below median = good, above 2x median = bad
    if de <= med * 0.5:
        return 95.0
    elif de <= med:
        return 85.0 - (de - med * 0.5) / (med * 0.5) * 20.0
    elif de <= med * 2:
        return 65.0 - (de - med) / med * 35.0
    else:
        return max(5.0, 30.0 - (de - med * 2) / (med * 2) * 25.0)


def _sector_adjusted_margin_comment(margin: float, sector: Optional[str],
                                    pros: list[str], cons: list[str]) -> None:
    """Append sector-aware margin pros/cons."""
    med, _, _, _, _ = _sector_guidelines(sector)
    if margin > med * 1.5:
        pros.append(f"Above-sector net margin ({margin:.1f}% vs {med:.1f}% median)")
    elif margin < med * 0.4:
        cons.append(f"Below-sector net margin ({margin:.1f}% vs {med:.1f}% median)")


# ---------------------------------------------------------------------------
# Sub-scoring functions — each returns 0..100
# ---------------------------------------------------------------------------

def score_fundamental(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.revenue_growth_pct is not None:
        s = 50 + min(50, m.revenue_growth_pct * 1.5)
        parts.append(clamp(s))
        if m.revenue_growth_pct > 15:
            pros.append(f"Strong revenue growth ({m.revenue_growth_pct:.1f}%)")
        elif m.revenue_growth_pct < 0:
            cons.append(f"Revenue declining ({m.revenue_growth_pct:.1f}%)")

    if m.net_margin_pct is not None:
        med, _, _, _, _ = _sector_guidelines(m.sector)
        # Cap reward when margin > 50% (financial/investment company anomaly)
        if m.net_margin_pct > 50:
            s = 80.0
        else:
            s = clamp(m.net_margin_pct * 3)
        parts.append(s)
        _sector_adjusted_margin_comment(m.net_margin_pct, m.sector, pros, cons)
        if m.net_margin_pct < 5:
            cons.append(f"Thin net margin ({m.net_margin_pct:.1f}%)")

    if m.roe_pct is not None:
        s = clamp(m.roe_pct * 4)  # 25% ROE = 100
        parts.append(s)
        if m.roe_pct > 15:
            pros.append(f"ROE {m.roe_pct:.1f}% — strong")
        elif m.roe_pct < 5:
            cons.append(f"ROE {m.roe_pct:.1f}% — weak")

    if m.eps_growth_pct is not None:
        s = 50 + min(50, m.eps_growth_pct * 1.2)
        parts.append(clamp(s))

    # NEW v2.0 — Gross margin (moat proxy)
    if m.gross_margin_pct is not None:
        if m.gross_margin_pct > 50:
            s = 95.0
            pros.append(f"Wide gross margin ({m.gross_margin_pct:.1f}%) — pricing power")
        elif m.gross_margin_pct > 30:
            s = 75.0
        elif m.gross_margin_pct > 15:
            s = 55.0
        else:
            s = 30.0
            cons.append(f"Thin gross margin ({m.gross_margin_pct:.1f}%)")
        parts.append(s)

    # NEW v2.0 — 3Y revenue CAGR (sustainability)
    if m.revenue_growth_3y_cagr is not None:
        s = 50 + min(50, m.revenue_growth_3y_cagr * 1.5)
        parts.append(clamp(s))
        if m.revenue_growth_3y_cagr > 12:
            pros.append(f"Consistent 3Y revenue CAGR ({m.revenue_growth_3y_cagr:.1f}%)")
        elif m.revenue_growth_3y_cagr < 0:
            cons.append(f"Revenue shrinking over 3Y ({m.revenue_growth_3y_cagr:.1f}%)")

    # NEW v2.0 — Earnings volatility (penalty for erratic earnings)
    if m.earnings_volatility is not None:
        # Lower volatility = higher score.  0% vol = 100, 50% vol = 20
        s = clamp(100 - m.earnings_volatility * 1.6)
        parts.append(s)
        if m.earnings_volatility > 40:
            cons.append(f"High earnings volatility ({m.earnings_volatility:.1f}%)")

    return sum(parts) / len(parts) if parts else 50.0


def score_valuation(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    # P/E — sector-aware
    if m.pe_ratio is not None and m.pe_ratio > 0:
        s = _sector_adjusted_pe_score(m.pe_ratio, m.sector)
        parts.append(s)
        _, _, _, cheap, expensive = _sector_guidelines(m.sector)
        if m.pe_ratio < cheap:
            pros.append(f"Cheap P/E ({m.pe_ratio:.1f} vs sector cheap {cheap:.0f})")
        elif m.pe_ratio > expensive:
            cons.append(f"Expensive P/E ({m.pe_ratio:.1f} vs sector expensive {expensive:.0f})")

    # P/B
    if m.pb_ratio is not None and m.pb_ratio > 0:
        s = 100 - clamp((m.pb_ratio - 1) * 20)
        parts.append(clamp(s))
        if m.pb_ratio < 1.0:
            pros.append(f"Below book value (P/B {m.pb_ratio:.2f})")
        elif m.pb_ratio > 5:
            cons.append(f"High P/B ({m.pb_ratio:.2f})")

    # EV/EBITDA
    if m.ev_ebitda is not None and m.ev_ebitda > 0:
        s = 100 - clamp((m.ev_ebitda - 6) * 4)
        parts.append(clamp(s))

    # NEW v2.0 — P/S (critical for unprofitable growth stocks)
    if m.ps_ratio is not None and m.ps_ratio > 0:
        # P/S < 2 = great, 2-5 = fair, 5-10 = pricey, >10 = expensive
        if m.ps_ratio < 2:
            s = 90.0
            pros.append(f"Low P/S ({m.ps_ratio:.1f})")
        elif m.ps_ratio < 5:
            s = 75.0 - (m.ps_ratio - 2) / 3 * 20.0
        elif m.ps_ratio < 10:
            s = 55.0 - (m.ps_ratio - 5) / 5 * 30.0
        else:
            s = 25.0 - min(15.0, (m.ps_ratio - 10) / 10 * 15.0)
            cons.append(f"High P/S ({m.ps_ratio:.1f})")
        parts.append(clamp(s))

    # NEW v2.0 — EV/Sales
    if m.ev_sales is not None and m.ev_sales > 0:
        if m.ev_sales < 2:
            s = 90.0
        elif m.ev_sales < 5:
            s = 75.0 - (m.ev_sales - 2) / 3 * 20.0
        elif m.ev_sales < 10:
            s = 55.0 - (m.ev_sales - 5) / 5 * 30.0
        else:
            s = 25.0 - min(15.0, (m.ev_sales - 10) / 10 * 15.0)
        parts.append(clamp(s))

    # NEW v2.0 — PEG Ratio
    if m.peg_ratio is not None and m.peg_ratio > 0:
        # PEG < 1 = undervalued growth, 1-2 = fair, >2 = overvalued
        if m.peg_ratio < 0.8:
            s = 95.0
            pros.append(f"Attractive PEG ({m.peg_ratio:.2f})")
        elif m.peg_ratio < 1.0:
            s = 85.0 - (m.peg_ratio - 0.8) / 0.2 * 10.0
        elif m.peg_ratio < 2.0:
            s = 75.0 - (m.peg_ratio - 1.0) / 1.0 * 35.0
        else:
            s = 40.0 - min(30.0, (m.peg_ratio - 2.0) / 2.0 * 30.0)
            cons.append(f"High PEG ({m.peg_ratio:.2f})")
        parts.append(clamp(s))

    # Dividend yield
    if m.dividend_yield_pct is not None:
        s = clamp(m.dividend_yield_pct * 12)  # 8% yield = 96
        parts.append(s)
        if m.dividend_yield_pct >= 5:
            pros.append(f"Attractive dividend yield ({m.dividend_yield_pct:.2f}%)")
        # NEW v2.0 — flag unsustainably high yields (>12% often = dividend trap)
        if m.dividend_yield_pct > 12:
            cons.append(f"Very high yield ({m.dividend_yield_pct:.2f}%) — possible dividend trap")

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
        if m.return_1y > 25:
            pros.append(f"Strong 1Y momentum (+{m.return_1y:.1f}%)")
        elif m.return_1y < -15:
            cons.append(f"Weak 1Y momentum ({m.return_1y:.1f}%)")

    return clamp(sum(parts) / max(1, len(parts))) if parts else 50.0


def score_technical(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    if m.rsi_14 is not None:
        # 30-70 healthy zone, <30 oversold (potential bounce), >70 overbought
        if m.rsi_14 < 30:
            s = 75
            pros.append(f"Oversold RSI ({m.rsi_14:.0f})")
        elif m.rsi_14 > 70:
            s = 30
            cons.append(f"Overbought RSI ({m.rsi_14:.0f})")
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
        if s >= 75:
            pros.append(f"Analyst consensus: {m.analyst_rating}")
        elif s <= 25:
            cons.append(f"Analyst consensus: {m.analyst_rating}")

    # Auto-correct fraction-vs-percent
    upside = _normalise_pct(m.analyst_upside_pct)
    if upside is not None:
        s = clamp(50 + upside * 1.5)
        parts.append(s)
        if upside > 20:
            pros.append(f"Analyst upside +{upside:.1f}%")
        elif upside < -10:
            cons.append(f"Analyst downside {upside:.1f}%")

    if m.analyst_count is not None and m.analyst_count >= 5:
        if parts:
            avg = sum(parts) / len(parts)
            return clamp(avg + 5)
    return sum(parts) / len(parts) if parts else 50.0


def score_quality(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    parts: list[float] = []

    # Debt/Equity — sector-aware
    if m.debt_to_equity is not None:
        s = _sector_adjusted_de_score(m.debt_to_equity, m.sector)
        parts.append(s)
        _, med, _, _, _ = _sector_guidelines(m.sector)
        if m.debt_to_equity < 0:
            cons.append("Negative equity — solvency risk")
        elif m.debt_to_equity < med * 0.5:
            pros.append(f"Low leverage (D/E {m.debt_to_equity:.2f} vs sector {med:.2f})")
        elif m.debt_to_equity > med * 2:
            cons.append(f"High leverage (D/E {m.debt_to_equity:.2f} vs sector {med:.2f})")

    if m.current_ratio is not None:
        if 1.5 <= m.current_ratio <= 3.5:
            s = 85
        elif m.current_ratio < 1.0:
            s = 25
        else:
            s = 60
        parts.append(s)
        if m.current_ratio < 1:
            cons.append(f"Liquidity tight (current ratio {m.current_ratio:.2f})")

    if m.fcf_yield is not None:
        if m.fcf_yield > 0.08:
            s = 100.0
            pros.append(f"Strong cash generator (FCF Yield {m.fcf_yield:.1%})")
        elif m.fcf_yield > 0.03:
            s = 70.0
        elif 0 <= m.fcf_yield <= 0.03:
            s = 40.0
            cons.append(f"Lean cash flow (FCF Yield {m.fcf_yield:.1%})")
        else:
            s = 10.0
            cons.append("Negative Free Cash Flow — burning capital")
        parts.append(s)

    # NEW v2.0 — ROIC (better than ROE, not gamed by leverage)
    if m.roic_pct is not None:
        if m.roic_pct > 15:
            s = 95.0
            pros.append(f"High ROIC ({m.roic_pct:.1f}%) — capital efficient")
        elif m.roic_pct > 10:
            s = 80.0
        elif m.roic_pct > 5:
            s = 60.0
        elif m.roic_pct > 0:
            s = 35.0
        else:
            s = 10.0
            cons.append(f"Negative ROIC ({m.roic_pct:.1f}%) — destroying value")
        parts.append(s)

    # NEW v2.0 — CFO / Net Income (earnings quality)
    if m.cfo_to_net_income is not None:
        if m.cfo_to_net_income >= 1.0:
            s = 90.0
            pros.append("Earnings backed by cash (CFO/NI ≥ 1.0)")
        elif m.cfo_to_net_income >= 0.8:
            s = 70.0
        elif m.cfo_to_net_income >= 0.5:
            s = 45.0
            cons.append(f"Earnings partially non-cash (CFO/NI {m.cfo_to_net_income:.2f})")
        else:
            s = 15.0
            cons.append("Earnings not backed by cash — accrual risk")
        parts.append(s)

    # NEW v2.0 — Interest Coverage
    if m.interest_coverage is not None:
        if m.interest_coverage > 10:
            s = 95.0
            pros.append(f"Strong interest coverage ({m.interest_coverage:.1f}x)")
        elif m.interest_coverage > 5:
            s = 80.0
        elif m.interest_coverage > 2:
            s = 55.0
        elif m.interest_coverage > 1:
            s = 25.0
            cons.append(f"Tight interest coverage ({m.interest_coverage:.1f}x)")
        else:
            s = 5.0
            cons.append(f"Cannot cover interest ({m.interest_coverage:.1f}x) — distress")
        parts.append(s)

    return sum(parts) / len(parts) if parts else 50.0


# ---------------------------------------------------------------------------
# 1.2  New Risk Score — Convex Penalty, Multi-Dimensional
# ---------------------------------------------------------------------------
# Old risk: linear subtraction with (risk - 30) baseline.
# New risk: each component scored 0..100, then combined with convex weighting
# so that multiple risk factors compound non-linearly.
#
# Components:
#   A. Market risk      — beta, drawdown
#   B. Liquidity risk   — free float
#   C. Solvency risk    — cash position, Altman Z, interest coverage
#   D. Volatility risk  — earnings volatility, 52w range
#   E. Governance risk  — low insider ownership
#
# Final risk = weighted average of components, then passed through a convex
# transform:  risk_final = 30 + (risk_raw - 30) * convex_factor
# where convex_factor = 1.0 + 0.5 * max(0, (risk_raw - 50) / 50)
# This means: moderate risk gets mild penalty, high risk gets SEVERE penalty.
# ---------------------------------------------------------------------------

def score_risk(m: StockMetrics, pros: list[str], cons: list[str]) -> float:
    """Risk = penalty. Higher = riskier (subtracted from composite).

    v2.0: Convex penalty curve — risk compounds non-linearly.
    """
    components: list[float] = []
    weights: list[float] = []

    # ---- A. Market Risk (beta + drawdown) ----
    market_risk_parts: list[float] = []
    if m.beta is not None:
        s = clamp(abs(m.beta - 1) * 30)
        market_risk_parts.append(s)
        if abs(m.beta) > 1.5:
            cons.append(f"High beta ({m.beta:.2f})")

    if m.last_close and m.week_52_high:
        drawdown = (m.week_52_high - m.last_close) / m.week_52_high * 100
        if drawdown > 40:
            market_risk_parts.append(85)
            cons.append(f"Severe drawdown ({drawdown:.0f}% from 52w high)")
        elif drawdown > 30:
            market_risk_parts.append(70)
            cons.append(f"Deep drawdown ({drawdown:.0f}% from 52w high)")
        elif drawdown > 15:
            market_risk_parts.append(40)
        else:
            market_risk_parts.append(15)

    if market_risk_parts:
        components.append(sum(market_risk_parts) / len(market_risk_parts))
        weights.append(0.25)

    # ---- B. Liquidity Risk (free float) ----
    if m.free_float_pct is not None:
        if m.free_float_pct < 10:
            s = 85
            cons.append(f"Very low free float ({m.free_float_pct:.1f}%)")
        elif m.free_float_pct < 15:
            s = 70
            cons.append(f"Low free float ({m.free_float_pct:.1f}%)")
        elif m.free_float_pct < 25:
            s = 40
        else:
            s = 15
        components.append(s)
        weights.append(0.15)

    # ---- C. Solvency Risk (cash position + Altman Z + interest coverage) ----
    solvency_parts: list[float] = []

    if m.cash_per_share is not None and m.last_close:
        cash_position_pct = (m.cash_per_share / m.last_close) * 100
        if cash_position_pct < -50:
            s = 95.0
            cons.append(f"Critical net debt ({cash_position_pct:.1f}% of price)")
        elif cash_position_pct < -20:
            s = 75.0
            cons.append(f"Heavy net debt ({cash_position_pct:.1f}% of price)")
        elif cash_position_pct < -10:
            s = 55.0
            cons.append(f"Significant leverage ({cash_position_pct:.1f}% of price)")
        elif cash_position_pct < 0:
            s = 30.0
        else:
            s = 5.0
            pros.append(f"Net cash positive ({m.cash_per_share:.2f}/share)")
        solvency_parts.append(s)

    # NEW v2.0 — Altman Z-Score
    if m.altman_z_score is not None:
        if m.altman_z_score > 2.99:
            s = 10.0  # safe
        elif m.altman_z_score > 1.81:
            s = 50.0  # grey zone
        else:
            s = 90.0  # distress zone
            cons.append(f"Altman Z-Score distress ({m.altman_z_score:.2f})")
        solvency_parts.append(s)

    # Interest coverage already in quality, but double-count here with lower weight
    # if it's very bad (< 1.5x)
    if m.interest_coverage is not None and m.interest_coverage < 1.5:
        solvency_parts.append(80.0)
        cons.append(f"Interest coverage critical ({m.interest_coverage:.1f}x)")

    if solvency_parts:
        components.append(sum(solvency_parts) / len(solvency_parts))
        weights.append(0.30)

    # ---- D. Volatility Risk (earnings volatility + 52w range) ----
    vol_parts: list[float] = []
    if m.earnings_volatility is not None and m.earnings_volatility > 30:
        vol_parts.append(min(100.0, 50 + m.earnings_volatility))

    if m.week_52_high and m.week_52_low and m.week_52_high > m.week_52_low:
        yr_range = (m.week_52_high - m.week_52_low) / m.week_52_low * 100
        if yr_range > 80:
            vol_parts.append(70.0)
        elif yr_range > 50:
            vol_parts.append(45.0)
        else:
            vol_parts.append(20.0)

    if vol_parts:
        components.append(sum(vol_parts) / len(vol_parts))
        weights.append(0.15)

    # ---- E. Governance Risk (insider ownership) ----
    if m.insider_ownership_pct is not None:
        # Low insider ownership = misaligned incentives
        if m.insider_ownership_pct < 5:
            s = 60.0
            cons.append(f"Low insider ownership ({m.insider_ownership_pct:.1f}%)")
        elif m.insider_ownership_pct < 15:
            s = 35.0
        else:
            s = 10.0
            pros.append(f"Strong insider ownership ({m.insider_ownership_pct:.1f}%)")
        components.append(s)
        weights.append(0.15)

    # ---- Combine with convex transform ----
    if not components:
        return 30.0

    # Weighted average of components
    risk_raw = sum(c * w for c, w in zip(components, weights)) / sum(weights)

    # Convex transform: moderate risk stays moderate, high risk escalates fast
    excess = max(0, risk_raw - 50)
    convex_factor = 1.0 + 0.6 * (excess / 50)  # at risk=100, factor=1.6
    risk_final = 30 + (risk_raw - 30) * convex_factor

    return clamp(risk_final)


# ---------------------------------------------------------------------------
# Data completeness & confidence
# ---------------------------------------------------------------------------

def _compute_completeness(m: StockMetrics) -> tuple[float, str]:
    """Return (completeness_pct, confidence_label).

    Counts how many of the ~30 key metrics are non-None.
    """
    key_fields = [
        m.sector,
        m.revenue_growth_pct, m.net_margin_pct, m.roe_pct, m.eps_growth_pct,
        m.gross_margin_pct, m.revenue_growth_3y_cagr, m.earnings_volatility,
        m.pe_ratio, m.pb_ratio, m.ev_ebitda, m.ps_ratio, m.ev_sales,
        m.peg_ratio, m.dividend_yield_pct,
        m.return_1m, m.return_3m, m.return_6m, m.return_1y,
        m.rsi_14, m.last_close, m.sma_50, m.sma_200,
        m.week_52_high, m.week_52_low,
        m.analyst_rating, m.analyst_count, m.analyst_upside_pct,
        m.debt_to_equity, m.current_ratio, m.fcf_yield,
        m.roic_pct, m.cfo_to_net_income, m.interest_coverage,
        m.beta, m.free_float_pct, m.cash_per_share,
        m.altman_z_score, m.insider_ownership_pct,
    ]
    present = sum(1 for f in key_fields if f is not None)
    total = len(key_fields)
    pct = round(present / total * 100, 1)

    if pct >= 80:
        confidence = "HIGH"
    elif pct >= 55:
        confidence = "MEDIUM"
    elif pct >= 30:
        confidence = "LOW"
    else:
        confidence = "VERY_LOW"

    return pct, confidence


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

    # v2.0: Convex risk penalty
    excess_risk = max(0, risk - 30)
    convex_factor = 1.0 + 0.5 * (excess_risk / 70)  # at risk=100, factor=1.5
    risk_penalty = WEIGHTS["risk"] * excess_risk * convex_factor

    composite = (
        WEIGHTS["fundamental"] * fund +
        WEIGHTS["valuation"]   * val  +
        WEIGHTS["momentum"]    * mom  +
        WEIGHTS["technical"]   * tech +
        WEIGHTS["analyst"]     * ana  +
        WEIGHTS["quality"]     * qual
    ) - risk_penalty
    composite = clamp(composite)

    if composite >= 70:
        verdict = "BUY"
    elif composite >= 45:
        verdict = "WATCH"
    else:
        verdict = "STAY_AWAY"

    # v2.0: data completeness
    completeness, confidence = _compute_completeness(m)

    return ScoreResult(
        fundamental=round(fund, 2), valuation=round(val, 2), momentum=round(mom, 2),
        technical=round(tech, 2), analyst=round(ana, 2), quality=round(qual, 2),
        risk=round(risk, 2), composite=round(composite, 2),
        verdict=verdict, pros=pros[:8], cons=cons[:8],
        data_completeness_pct=completeness,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Per-position recommendation (HOLD / SELL / BUY MORE / TRIM / STOP_LOSS)
# ---------------------------------------------------------------------------
@dataclass
class PositionContext:
    avg_entry_price: float
    current_price: float
    stock_score: ScoreResult
    holding_days: Optional[int] = None  # NEW v2.0


def recommend_position(ctx: PositionContext) -> dict:
    pl_pct = (ctx.current_price - ctx.avg_entry_price) / ctx.avg_entry_price * 100
    s = ctx.stock_score

    reasoning: list[str] = [f"Unrealized P/L: {pl_pct:+.2f}%"]
    if ctx.holding_days is not None:
        reasoning.append(f"Holding period: {ctx.holding_days} days")
    confidence = 60.0

    # v2.0: Graduated stop-loss framework
    if pl_pct <= -20:
        verdict = "STOP_LOSS"
        confidence = 90
        reasoning.append("Down >20% — hard stop triggered regardless of score.")
    elif pl_pct <= -15 and s.verdict == "STAY_AWAY":
        verdict = "STOP_LOSS"
        confidence = 85
        reasoning.append("Down >15% AND stock scores STAY_AWAY — cut losses.")
    elif pl_pct <= -10 and s.verdict == "STAY_AWAY":
        verdict = "SELL"
        confidence = 75
        reasoning.append("Down >10% with STAY_AWAY score — exit before deeper losses.")
    elif pl_pct >= 30 and s.verdict in ("WATCH", "STAY_AWAY"):
        verdict = "TRIM"
        confidence = 70
        reasoning.append("Up >30% but score has weakened — take partial profits.")
    # v2.0: Time-decay trim for long holds with good gains but weakening score
    elif (ctx.holding_days and ctx.holding_days > 365 and
          pl_pct > 20 and s.verdict == "WATCH"):
        verdict = "TRIM"
        confidence = 65
        reasoning.append(f"Held {ctx.holding_days}d, up {pl_pct:.1f}%, score weakened — trim.")
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