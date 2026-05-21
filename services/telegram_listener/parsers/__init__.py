"""Signal parsers — convert raw Telegram message text into structured signals.

One parser per `parser_key`. Each parser exposes:
    parse(text: str) -> Optional[ParsedSignal]

Add a new parser:
    1. Create a new module (e.g. forex_majors.py) with a parse() function
    2. Register it in PARSERS below
    3. Set tg_channels.parser_key to the new key when creating a channel

Ported from the original bot's Parser/local_message_parser.py — same regex,
same logic, same min-price filter. Kept verbatim where possible so behaviour
is bit-for-bit identical with the legacy parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import gold_xau


@dataclass
class ParsedSignal:
    symbol: str
    direction: str           # BUY | SELL
    entry_from: float
    entry_to: float
    sl: float
    tps: list[float] = field(default_factory=list)


PARSERS = {
    "gold_xau": gold_xau.parse,
}


def parse(parser_key: str, text: str) -> Optional[ParsedSignal]:
    """Look up the parser by key and run it. Returns None if no parser or
    if the parser couldn't extract a signal (noise message).
    """
    fn = PARSERS.get(parser_key)
    if fn is None:
        return None
    return fn(text)
