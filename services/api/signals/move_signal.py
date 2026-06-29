"""Pure, timeframe-agnostic move-signal scorer.

No DB, no I/O — feed it a list of OHLC(V) bars (daily for stocks today,
5-minute for XAU later) and a config, get back a probability-like score and
the factor breakdown. Keeping it pure makes it trivial to unit-test and to
reuse from the scheduler / an intraday feed without change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from typing import Optional


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


@dataclass
class MoveSignalConfig:
    """All tunable knobs. Defaults reproduce the "> $5 next bar" ask."""
    # How the target move is expressed:
    #   "absolute" -> target_value is dollars   ($5)
    #   "atr"      -> target_value is an ATR multiple (e.g. 1.5 * ATR)
    #   "percent"  -> target_value is % of last close (e.g. 1.0 == 1%)
    target_mode: str = "absolute"
    target_value: float = 5.0
    atr_period: int = 14
    lookback: int = 20            # bars for range / excursion / volume stats
    fire_threshold: float = 0.50  # min score (0..1) to count as a "fire"
    max_expansion_bonus: float = 1.6  # cap on the acceleration multiplier


# Mirrors the alerts/rules.py params_schema convention so the UI can render a
# form generically.
PARAMS_SCHEMA: list[dict] = [
    {"name": "target_mode", "type": "select", "label": "Target mode",
     "required": True, "default": "absolute",
     "options": ["absolute", "atr", "percent"]},
    {"name": "target_value", "type": "number", "label": "Target value ($ / ATRx / %)",
     "required": True, "default": 5.0, "min": 0.01, "step": 0.1},
    {"name": "atr_period", "type": "number", "label": "ATR period",
     "required": True, "default": 14, "min": 2, "max": 200},
    {"name": "lookback", "type": "number", "label": "Lookback (bars)",
     "required": True, "default": 20, "min": 3, "max": 500},
    {"name": "fire_threshold", "type": "number", "label": "Fire threshold (0-1)",
     "required": True, "default": 0.50, "min": 0.0, "max": 1.0, "step": 0.05},
]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
@dataclass
class MoveSignalResult:
    fired: bool = False
    score: float = 0.0            # 0..1, probability-like
    target_abs: float = 0.0       # resolved $ target for the next bar
    atr: float = 0.0              # volatility unit ($)
    p_base: float = 0.0           # tail probability before acceleration bump
    range_expansion: float = 1.0  # latest bar range / mean range (>1 = expanding)
    vol_surge: float = 1.0        # latest volume / mean volume (>1 = heavier)
    rsi: Optional[float] = None   # context only — NOT a driver
    reason: str = ""
    insufficient_data: bool = False

    def as_dict(self) -> dict:
        return {
            "fired": self.fired,
            "score": round(self.score, 4),
            "target_abs": round(self.target_abs, 4),
            "atr": round(self.atr, 4),
            "p_base": round(self.p_base, 4),
            "range_expansion": round(self.range_expansion, 3),
            "vol_surge": round(self.vol_surge, 3),
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "reason": self.reason,
            "insufficient_data": self.insufficient_data,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _atr(bars: list[Bar], period: int) -> float:
    """Simple-average True Range over the last `period` bars (transparent;
    a Wilder smoothing would be marginally different and less obvious)."""
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    window = trs[-period:]
    return sum(window) / len(window)


def _rsi(bars: list[Bar], period: int = 14) -> Optional[float]:
    if len(bars) <= period:
        return None
    gains = losses = 0.0
    for i in range(len(bars) - period, len(bars)):
        d = bars[i].close - bars[i - 1].close
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def compute_move_signal(bars: list[Bar], cfg: MoveSignalConfig) -> MoveSignalResult:
    """Score the probability that the NEXT bar moves >= target from its open.

    Model (transparent, theory-grounded):
      * `atr` is the recent typical bar range (volatility unit).
      * A single bar's max excursion from open has an approximately
        exponential tail, so  P(excursion >= T) ~= exp(-T / atr).  That is
        the parameter-free `p_base`: when normal range already ~ the target,
        odds are high; when the target dwarfs normal range, odds collapse.
      * `p_base` is then nudged by an *acceleration* multiplier built from
        range expansion and volume surge in the latest bar — i.e. is
        volatility ramping right now — capped by `max_expansion_bonus`.
      * Direction is deliberately ignored.
    """
    need = max(cfg.atr_period, cfg.lookback) + 2
    if len(bars) < need:
        return MoveSignalResult(insufficient_data=True,
                                reason=f"need >= {need} bars, got {len(bars)}")

    last = bars[-1]
    atr = _atr(bars, cfg.atr_period)
    if atr <= 0:
        return MoveSignalResult(insufficient_data=True, reason="ATR is zero")

    # Resolve the dollar target for the next bar.
    mode = (cfg.target_mode or "absolute").lower()
    if mode == "atr":
        target_abs = cfg.target_value * atr
    elif mode == "percent":
        target_abs = cfg.target_value / 100.0 * last.close
    else:
        target_abs = cfg.target_value

    # Tail probability from the exponential-excursion model.
    p_base = _clamp(exp(-target_abs / atr), 0.0, 0.99)

    # Acceleration: is volatility ramping in the most recent bar?
    win = bars[-cfg.lookback:]
    mean_range = sum(b.high - b.low for b in win) / len(win)
    range_expansion = (last.high - last.low) / mean_range if mean_range > 0 else 1.0

    vols = [b.volume for b in win if b.volume is not None]
    if last.volume is not None and len(vols) >= 3:
        mean_vol = sum(vols) / len(vols)
        vol_surge = last.volume / mean_vol if mean_vol > 0 else 1.0
    else:
        vol_surge = 1.0

    # Dampened, capped multiplier (sqrt/4th-root so a single wild bar doesn't
    # blow the score up). Neutral == 1.0.
    factor = 1.0
    factor *= min(max(range_expansion, 0.0001), 2.0) ** 0.5
    factor *= min(max(vol_surge, 0.0001), 4.0) ** 0.25
    factor = _clamp(factor, 0.6, cfg.max_expansion_bonus)

    score = _clamp(p_base * factor, 0.0, 0.99)
    fired = score >= cfg.fire_threshold

    bits = [f"ATR≈${atr:.2f} vs target ${target_abs:.2f} → base {p_base*100:.0f}%"]
    if range_expansion >= 1.15:
        bits.append(f"range expanding ×{range_expansion:.1f}")
    if vol_surge >= 1.3:
        bits.append(f"volume ×{vol_surge:.1f}")
    reason = "; ".join(bits)

    return MoveSignalResult(
        fired=fired, score=score, target_abs=target_abs, atr=atr, p_base=p_base,
        range_expansion=range_expansion, vol_surge=vol_surge,
        rsi=_rsi(bars), reason=reason,
    )
