"""News provider — stockanalysis.com overview page."""
from __future__ import annotations

import re
from typing import Optional

from ...fetcher import HttpFetcher
from .. import StockContext
from . import PAGE, build_url
from ._common import make_soup


class StockAnalysisNewsProvider:
    """Extract news headlines from the overview page."""

    async def fetch_news(self, fetcher: HttpFetcher,
                         stock: StockContext) -> Optional[list[dict]]:
        url = build_url(stock.url_template, stock.ticker, PAGE["overview"])
        try:
            _status, html = await fetcher.get(url)
        except Exception:
            return None

        soup = make_soup(html)
        items: list[dict] = []
        seen: set[str] = set()
        # News block: each headline lives inside an <h3> with an <a> child.
        # The 'X ago - Source' line appears as the next text sibling.
        for h3 in soup.find_all("h3"):
            a = h3.find("a")
            if not a:
                continue
            headline = a.get_text(strip=True)
            href = a.get("href")
            if not headline or not href or headline in seen:
                continue
            seen.add(headline)
            source = None
            sibling = h3.find_next(string=re.compile(r"ago\s*-\s*"))
            if sibling:
                m = re.search(r"-\s*(.+?)$", sibling.strip())
                if m:
                    source = m.group(1).strip()
            items.append({
                "headline": headline,
                "url": href,
                "source_code": source,
            })
        return items
