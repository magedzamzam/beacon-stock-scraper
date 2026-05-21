"""Gold (XAUUSD) signal parser.

Ported from the original bot's Parser/local_message_parser.py. Same regex,
same gate, same direction-aware sort. Returns a ParsedSignal or None.

Gate (all four must be present in the message):
    - Direction:  BUY | SELL
    - Symbol:     XAUUSD | XAU/USD | XAU | GOLD
    - Take profit: TP | TP1..N | TAKE PROFIT
    - Stop loss:   SL | STOP LOSS | STOPLOSS

Assignment logic:
    Numbers before the first TP/SL mention are candidate ENTRY prices.
    Numbers after that mention are SL + TPs.
    Numbers < min_price (2000) are ignored — pure XAU/USD assumption,
    so anything below that is a pip count or a price ratio, not gold.

For BUY: entry list sorted DESC (higher = entry_from); risk list sorted
         ASC (lowest = SL, rest ascending = TPs above).
For SELL: entry list sorted ASC (lower = entry_from); risk list sorted
          DESC (highest = SL, rest descending = TPs below).
"""
from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from . import ParsedSignal


_RE_DIR     = re.compile(r"\b(BUY|SELL)\b", re.I)
_RE_HAS_SYM = re.compile(r"\b(XAUUSD|XAU/USD|XAU|GOLD)\b", re.I)
_RE_HAS_TP  = re.compile(r"\b(TP\d*|TAKE\s*PROFIT)\b", re.I)
_RE_HAS_SL  = re.compile(r"\b(SL|STOP\s*LOSS|STOPLOSS)\b", re.I)
_RE_NUM     = re.compile(r"\d+\.?\d*")

_MIN_PRICE = 2000.0

# Telegram superscripts seen in real signals — normalise to digits before parsing.
_SUPERSCRIPT = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
})


def _fix_text(message: str) -> str:
    return message.upper().translate(_SUPERSCRIPT)


def parse(message: str) -> Optional["ParsedSignal"]:
    # Local import avoids a circular dependency with the package __init__.
    from . import ParsedSignal

    text = _fix_text(message)

    m_dir = _RE_DIR.search(text)
    m_tp = _RE_HAS_TP.search(text)
    m_sl = _RE_HAS_SL.search(text)

    # Gate: ALL four markers must appear, else it's noise.
    if not (m_dir and _RE_HAS_SYM.search(text) and m_tp and m_sl):
        return None

    direction = m_dir.group(1).upper()
    symbol = "XAUUSD"   # normalised alias — all four match patterns map here.

    # Split message at the EARLIER of the first TP / first SL mention.
    # Numbers before that split = candidate entries; numbers after = SL + TPs.
    tp_index = m_tp.start()
    sl_index = m_sl.start()
    split_index = tp_index if tp_index < sl_index else sl_index

    entry_str = text[:split_index]
    risk_str = text[split_index:]

    entry_nums = [float(n) for n in _RE_NUM.findall(entry_str) if float(n) > _MIN_PRICE]
    risk_nums = [float(n) for n in _RE_NUM.findall(risk_str) if float(n) > _MIN_PRICE]

    # Need at least 1 entry, 1 SL, and 1 TP.
    if not entry_nums or len(risk_nums) < 2:
        return None

    if direction == "BUY":
        # Higher entry is entry_from for BUY (e.g. "BUY 2400-2395" → from 2400 to 2395).
        entry_sorted = sorted(entry_nums, reverse=True)
        # SL is the LOWEST risk price; TPs are above (ascending).
        risk_sorted = sorted(risk_nums)
    else:   # SELL
        # Lower entry is entry_from for SELL.
        entry_sorted = sorted(entry_nums)
        # SL is the HIGHEST risk price; TPs are below (descending).
        risk_sorted = sorted(risk_nums, reverse=True)

    entry_from = entry_sorted[0]
    entry_to = entry_sorted[1] if len(entry_sorted) > 1 else entry_sorted[0]
    sl = risk_sorted[0]
    tps = risk_sorted[1:]

    # Sanity check: SL on the correct side of entry. If a parsing quirk put
    # them backwards (e.g. SL above entry for BUY), reject — the signal is
    # malformed or we extracted the wrong numbers.
    if direction == "BUY" and sl >= entry_to:
        return None
    if direction == "SELL" and sl <= entry_to:
        return None

    return ParsedSignal(
        symbol=symbol,
        direction=direction,
        entry_from=entry_from,
        entry_to=entry_to,
        sl=sl,
        tps=tps,
    )
