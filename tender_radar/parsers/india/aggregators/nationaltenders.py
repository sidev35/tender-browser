"""Parser for NationalTenders' public keyword listing pages (nationaltenders.com)."""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ....models import Row
from ...common import CORRIGENDUM_PREFIX



def _cost(text: str) -> str | None:
    """The estimated cost in rupees ('1250000.00' -> '₹1250000'), or None when it is 0."""
    try:
        n = float(text.replace(",", ""))
    except ValueError:
        return None
    return f"₹{int(n)}" if n >= 1 else None


def parse_nationaltenders_list(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Parses a nationaltenders.com keyword listing page (/site/keyword/<keyword>).
    Public, no login, server-rendered (checked 2026-10-16; robots.txt allows
    all). The first page holds 10 results, so the source reads several keyword
    pages (sources.json "extraUrls"). Each result is a <div class="BidTenInfo">
    wrapping one link to the tender's own page, with
      - h3: the issuing organisation; below it "City, State, India"
      - "NTID <n>": NationalTenders' own id, used as the stable id key
      - "Closing Date : Tue 24th Nov, 2026"
      - p.Des: the description (cut with "..." when long); the link's title
        attribute holds a longer, lower-case copy, used when it says more
      - "Estimated Cost: <rupees>" (0 when undisclosed).
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("div.BidTenInfo"):
        link = card.select_one("a[href]")
        if not link:
            continue
        des = card.select_one("p.Des")
        title = des.get_text(" ", strip=True) if des else ""
        title = re.sub(r"^Tender Description\s*:\s*", "", title)
        attr = " ".join((link.get("title") or "").split())
        if title.endswith("..."):
            head = title[:-3].rstrip()
            title = attr if len(attr) > len(head) else head
        title = CORRIGENDUM_PREFIX.sub("", title or attr)
        if not title:
            continue
        txt = card.select_one("p.Txt")
        m = re.search(r"NTID\s*(\d+)", txt.get_text(" ", strip=True) if txt else "")
        ntid = m.group(1) if m else None
        due_iso = None
        red = card.select_one("ul.DateWrap span.Red")
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3}),\s+(\d{4})", red.get_text(" ", strip=True) if red else "")
        if m:
            try:
                due_iso = datetime.strptime(" ".join(m.groups()), "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        h3 = card.select_one(".LeftSide h3")
        org = h3.get_text(" ", strip=True) if h3 else None
        place = card.select_one(".LeftSide p")
        parts = [p.strip() for p in (place.get_text(" ", strip=True) if place else "").split(",") if p.strip()]
        if parts and parts[-1].lower() == "india":
            parts = parts[:-1]
        state = parts[-1] if parts else None
        cost = None
        key = card.select_one(".KeyValue")
        if key:
            m = re.search(r"Estimated Cost:\s*([\d,.]+)", key.get_text(" ", strip=True))
            cost = _cost(m.group(1)) if m else None
        results.append(
            {
                "raw_title": title,
                "raw_row": card.get_text(" | ", strip=True),
                "source": source_name,
                "refNo": None,
                "stableKey": f"nt-{ntid}" if ntid else None,
                "dueDateHint": due_iso,
                "value": cost,
                "organisation": org,
                "location": state,
                "docUrl": urljoin(base_url, link["href"]),
            }
        )
    return results
