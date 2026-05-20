#!/usr/bin/env python3
"""Apply the 'Reporting today' patch to schemas.py + routers_stocks.py.

Idempotent — running twice does nothing the second time.

Usage:
    cd /path/to/beacon-screener
    python3 patch_reporting_today.py

After running:
    docker compose up -d --build api frontend
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMAS = ROOT / "services" / "api" / "schemas.py"
ROUTERS = ROOT / "services" / "api" / "routers_stocks.py"

EDITS = [
    # ---- schemas.py: add 2 fields to StockSummary ----
    (
        SCHEMAS,
        # find marker: last existing line of StockSummary, before StockDetail
        "    last_updated: Optional[datetime] = None\n\n\nclass StockDetail(StockSummary):",
        # replacement
        "    last_updated: Optional[datetime] = None\n"
        "    # Next earnings event — surfaced so the home page \"Reporting today\"\n"
        "    # table can show date + intra-day timing without an N+1 detail fetch.\n"
        "    next_earnings_date: Optional[date] = None\n"
        "    earnings_time: Optional[str] = None    # \"Before Open\" | \"After Close\" | \"During Market\" | null\n"
        "\n\nclass StockDetail(StockSummary):",
        # idempotency check — if this line is already in the file, skip
        "next_earnings_date: Optional[date] = None",
    ),
    # ---- routers_stocks.py: add 2 columns to _SUMMARY_COLS ----
    (
        ROUTERS,
        "    StockQuote.composite_score, StockQuote.verdict,\n"
        "    StockQuote.last_updated,\n"
        ")",
        "    StockQuote.composite_score, StockQuote.verdict,\n"
        "    StockQuote.last_updated,\n"
        "    # Surfaced for home-page \"Reporting today\" — outer-join already\n"
        "    # exists in the screener() base query for the earnings_within_days_* filters.\n"
        "    StockEarningsCalendar.next_earnings_date,\n"
        "    StockEarningsCalendar.earnings_time,\n"
        ")",
        "StockEarningsCalendar.next_earnings_date,",
    ),
    # ---- routers_stocks.py: pass them through in _row_to_summary ----
    (
        ROUTERS,
        "        verdict=r.verdict, last_updated=r.last_updated,\n"
        "    )",
        "        verdict=r.verdict, last_updated=r.last_updated,\n"
        "        next_earnings_date=getattr(r, \"next_earnings_date\", None),\n"
        "        earnings_time=getattr(r, \"earnings_time\", None),\n"
        "    )",
        "next_earnings_date=getattr(r,",
    ),
]


def main() -> int:
    failures: list[str] = []
    for path, old, new, already_done_marker in EDITS:
        if not path.exists():
            failures.append(f"missing file: {path}")
            continue
        text = path.read_text()
        if already_done_marker in text:
            print(f"  skip   {path.name}: already patched ({already_done_marker[:40]}…)")
            continue
        if old not in text:
            failures.append(
                f"could not find marker in {path}:\n"
                f"    {old.splitlines()[0]!r}"
            )
            continue
        if text.count(old) > 1:
            failures.append(
                f"marker is not unique in {path} — refusing to patch:\n"
                f"    {old.splitlines()[0]!r}"
            )
            continue
        path.write_text(text.replace(old, new, 1))
        print(f"  patch  {path.name}: applied")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nDone. Now rebuild:")
    print("  docker compose up -d --build api frontend")
    return 0


if __name__ == "__main__":
    sys.exit(main())
