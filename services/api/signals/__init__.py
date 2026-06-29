"""Move-signal package — volatility-expansion detector.

A transparent, configurable re-implementation of the volatility-clustering
signal that scored AUC ~0.82 out-of-sample on intraday XAUUSD: "what is the
probability that the NEXT bar moves >= $X from its open in *either*
direction". The model's predictive power was carried almost entirely by
volatility features (ATR, recent range / max-excursion, range expansion,
volume surge), so we encode those directly rather than ship a binary ML
model into the API container. Every knob is configurable so different
scenarios can be tested from the UI.

Direction is intentionally NOT predicted here (it was a coin flip in
testing) — this is a "something is about to move" detector to monitor
manually; the direction layer is added later.
"""
from .move_signal import (
    Bar,
    MoveSignalConfig,
    MoveSignalResult,
    compute_move_signal,
    PARAMS_SCHEMA,
)

__all__ = [
    "Bar",
    "MoveSignalConfig",
    "MoveSignalResult",
    "compute_move_signal",
    "PARAMS_SCHEMA",
]
