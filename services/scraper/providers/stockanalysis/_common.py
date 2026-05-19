"""Parsing primitives shared across stockanalysis.com provider modules.

Lives at this path because every stockanalysis page uses the same value
formats and the same two-column-table layout. New providers (Benzinga, etc.)
get their own _common.py — they have nothing to do with this one.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------
_SUFFIX_MULTIPLIER = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_BLANK = {"", "n/a", "na", "-", "—", "upgrade"}


def parse_number(raw: Optional[str]) -> Optional[Decimal]:
    """Parse '871.14B', '-1.49', '171,124', 'n/a' → Decimal | None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _BLANK:
        return None
    m = re.match(r"^\s*([+-]?[\d,]+\.?\d*)\s*([KMBT])?", s)
    if not m:
        return None
    num_str, suffix = m.group(1), m.group(2)
    try:
        value = Decimal(num_str.replace(",", ""))
    except InvalidOperation:
        return None
    if suffix:
        value *= Decimal(str(_SUFFIX_MULTIPLIER[suffix]))
    return value


def parse_percent(raw: Optional[str]) -> Optional[Decimal]:
    if raw is None:
        return None
    return parse_number(str(raw).replace("%", ""))


def parse_int(raw: Optional[str]) -> Optional[int]:
    n = parse_number(raw)
    return int(n) if n is not None else None


def parse_date(raw: Optional[str]) -> Optional[date]:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _BLANK:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_label_value_pairs(html_or_soup) -> dict[str, str]:
    """Walk every 2-column table; first occurrence of each label wins."""
    soup = (html_or_soup if isinstance(html_or_soup, BeautifulSoup)
            else make_soup(html_or_soup))
    out: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) == 2:
            label = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if label and value and label not in out:
                out[label] = value
    return out


def get_first(pairs: dict[str, str], *aliases: str) -> Optional[str]:
    """Return the first non-empty value for any label in `aliases`."""
    for a in aliases:
        if a in pairs and pairs[a]:
            return pairs[a]
    return None


def parse_day_range(raw: Optional[str]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """'170.50 - 175.30' → (high=175.30, low=170.50)."""
    if not raw:
        return (None, None)
    parts = re.split(r"\s*[-–]\s*", raw)
    if len(parts) != 2:
        return (None, None)
    lo, hi = parse_number(parts[0]), parse_number(parts[1])
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return (hi, lo)


def read_financial_table(html: str) -> dict[str, dict[str, str]]:
    """Parse a multi-column financial table into {col_header: {row_label: cell}}.

    Each inner dict has a synthetic `_header` key holding the column-header
    text (e.g. '2024-12-31' or 'TTM'). stockanalysis renders one big table per
    financials sub-page — the first matching table wins.
    """
    soup = make_soup(html)
    out: dict[str, dict[str, str]] = {}
    for table in soup.find_all("table"):
        thead = table.find("thead")
        tbody = table.find("tbody")
        if not thead or not tbody:
            continue
        header_cells = thead.find_all(["th", "td"])
        if len(header_cells) < 3:
            continue
        col_names = [c.get_text(strip=True) for c in header_cells[1:]]
        for name in col_names:
            if name and name not in out:
                out[name] = {"_header": name}
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            row_label = cells[0].get_text(strip=True)
            if not row_label:
                continue
            for i, name in enumerate(col_names):
                if i + 1 >= len(cells):
                    break
                value = cells[i + 1].get_text(strip=True)
                if name and value:
                    out[name][row_label] = value
        if out:
            break
    return out


def pick_latest_column(cols: dict[str, dict[str, str]]) -> dict[str, str]:
    """Prefer the 'TTM' column; fall back to the last column (most recent FY)."""
    if "TTM" in cols:
        return cols["TTM"]
    if cols:
        return list(cols.values())[-1]
    return {}
