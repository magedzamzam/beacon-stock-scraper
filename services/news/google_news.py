"""Google News RSS adapter.

Why RSS over HTML scraping
--------------------------
Google publishes a stable XML endpoint at:
    https://news.google.com/rss/search?q=<query>&hl=...&gl=...&ceid=...

It returns the same items the UI does, with no JS rendering, no rate-limit
captcha for moderate traffic, and a format that hasn't changed in years.
We feed each stock's company name as the query (an exact-match phrase plus
"stock" to disambiguate) and pull at most ``items_cap`` headlines per call.

What we extract
---------------
For each <item> in the RSS feed we collect:
    headline      <title>
    url           <link>          (Google News redirect URL — keep as-is)
    news_date     <pubDate>       (RFC 822 -> python date)
    source_code   <source>        (e.g. "Reuters", "Bloomberg")

We deliberately ignore <description> for now (the user asked for headlines
only). When they want richer text, just plumb it through to ``stock_news.summary``.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, date
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional
from urllib.parse import quote_plus


GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"


@dataclass
class NewsItem:
    headline: str
    url: Optional[str]
    source_code: Optional[str]
    news_date: Optional[date]


def build_query(company_name: str, ticker: str, exchange_code: str,
                window: str = "7d") -> str:
    """Build a Google News search query for a single ticker.

    We use:
      - the full company name in quotes (exact-match) — the most reliable
        anchor for headlines because tickers like "TAQA" or "WAHA" are too
        generic on their own and produce noise (medical, sports, etc.)
      - plus the bare word "stock" so we lean toward financial coverage
      - plus a ``when:7d`` time window so daily runs only fetch fresh items

    Examples:
        '"Al Waha Capital" stock when:7d'
        '"Commercial International Bank" stock when:7d'
    """
    name = company_name.strip()
    # Strip common suffixes that often hurt search precision
    for suffix in (" PJSC", " P.J.S.C", " PSC", " QSC", " S.A.E", " (S.A.E)",
                   " Holding", " Group"):
        if name.upper().endswith(suffix.upper()):
            name = name[: -len(suffix)].strip()
    return f'"{name}" stock when:{window}'


def build_rss_url(query: str, gl: str = "AE", hl: str = "en", ceid: str = "AE:en") -> str:
    """Construct the full RSS URL for a Google News search.

    gl  – geographic location bias (AE/EG/etc.)
    hl  – interface language
    ceid – combined country/edition code

    For ADX/DFM tickers we use AE:en. For EGX, callers should pass gl=EG and
    ceid=EG:en so Egyptian outlets are weighted higher in results.
    """
    return (
        f"{GOOGLE_NEWS_BASE}?q={quote_plus(query)}"
        f"&hl={quote_plus(hl)}&gl={quote_plus(gl)}&ceid={quote_plus(ceid)}"
    )


def _strip_source_from_title(title: str) -> tuple[str, Optional[str]]:
    """Google News appends ' - <Source Name>' to most titles. Split it.

    Example:
        'Al Waha posts record dividend - Reuters'
            -> ('Al Waha posts record dividend', 'Reuters')

    If we can't find a clean split we return the original title and None
    (the source then comes from the explicit <source> element instead).
    """
    m = re.match(r"^(.*?)\s+-\s+([^-]+)$", title)
    if m and len(m.group(2)) <= 60:
        return m.group(1).strip(), m.group(2).strip()
    return title.strip(), None


def parse_rss(xml_text: str, items_cap: int = 10) -> list[NewsItem]:
    """Parse a Google News RSS document into a list of NewsItem.

    Robust against:
      - missing optional elements (source, link, pubDate)
      - malformed pubDate strings (skip the date, keep the headline)
      - empty channel (returns [])
    """
    if not xml_text or not xml_text.strip():
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    out: list[NewsItem] = []
    for item in channel.findall("item")[:items_cap]:
        title_el = item.find("title")
        if title_el is None or not (title_el.text or "").strip():
            continue
        title_raw = title_el.text.strip()

        # Try the explicit <source> element first; fall back to "headline - Source"
        source_el = item.find("source")
        explicit_source = source_el.text.strip() if (source_el is not None and source_el.text) else None
        cleaned_title, sniffed_source = _strip_source_from_title(title_raw)
        source_code = explicit_source or sniffed_source

        url_el = item.find("link")
        url = url_el.text.strip() if (url_el is not None and url_el.text) else None

        date_el = item.find("pubDate")
        news_date: Optional[date] = None
        if date_el is not None and date_el.text:
            try:
                dt = parsedate_to_datetime(date_el.text.strip())
                if dt is not None:
                    news_date = dt.date()
            except (TypeError, ValueError):
                pass

        out.append(NewsItem(
            headline=cleaned_title[:500],  # belt-and-suspenders against pathological titles
            url=url,
            source_code=(source_code or None) and source_code[:32],
            news_date=news_date,
        ))
    return out


def gl_for_exchange(exchange_code: str) -> tuple[str, str]:
    """Pick Google's gl/ceid pair best suited to a given exchange."""
    code = (exchange_code or "").lower()
    if code == "egx":
        return "EG", "EG:en"
    return "AE", "AE:en"      # adx, dfm
