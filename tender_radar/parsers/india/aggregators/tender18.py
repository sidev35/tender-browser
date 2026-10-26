"""Parser for Tender18's public keyword listing pages (tender18.com)."""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ....models import Row
from ...common import CORRIGENDUM_PREFIX

MAX_TITLE = 300
VALUE_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*(cr|crore|l|lac|lakh|k|thousand)?\b", re.IGNORECASE)


def _value(text: str) -> str | None:
    """'1.46Cr' -> '₹1.46 Crore', '25L' -> '₹25 Lakh', '14K' -> '₹14,000'; 'Refer Document' -> None."""
    m = VALUE_RE.match(text or "")
    if not m or not re.search(r"[1-9]", m.group(1)):
        return None
    unit = (m.group(2) or "").lower()
    if unit in ("k", "thousand"):
        return f"₹{round(float(m.group(1).replace(',', '')) * 1000):,}"
    if unit in ("cr", "crore"):
        return f"₹{m.group(1)} Crore"
    if unit in ("l", "lac", "lakh"):
        return f"₹{m.group(1)} Lakh"
    return f"₹{m.group(1)}"


def _org(text: str | None) -> str | None:
    """'state bank of india SBI' -> 'State Bank Of India' (a trailing short code is dropped)."""
    if not text:
        return None
    words = text.split()
    if len(words) > 1 and words[-1].isupper() and len(words[-1]) <= 6:
        words = words[:-1]
    return " ".join(words).title()


def parse_tender18_list(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Parses a tender18.com keyword listing page (e.g.
    /all-india-tenders/keyword-tenders/ev-charging-tenders). Public, no login,
    server-rendered (checked 2026-10-16; robots.txt allows all). The first
    page holds 10 results; more load only through the page's own script, so
    the source reads several keyword pages instead (sources.json "extraUrls").
    Each result is a <div class="tender-card-container"> with
      - "T18 Ref No : <n>": Tender18's own id, used as the stable id key (not
        the issuing authority's ref no.)
      - a state link under "Location :" (/state-tenders/<state>-tenders)
      - a.tender-card-title-link: the title, linking to the tender's own page
      - "Agency / Dept", "Due Date" ("Oct 22, 2026") and "Tender Value"
        ("1.46Cr", or "Refer Document" when undisclosed).
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("div.tender-card-container"):
        title_link = card.select_one("a.tender-card-title-link")
        if not title_link:
            continue
        title = CORRIGENDUM_PREFIX.sub("", " ".join(title_link.get_text(" ", strip=True).split()))
        if len(title) > MAX_TITLE:  # some titles are a whole bill of quantities
            title = title[:MAX_TITLE].rsplit(" ", 1)[0].rstrip(" ,;") + "…"
        title = title[:1].upper() + title[1:]
        ref = None
        for label in card.select(".tender-card-header-label"):
            m = re.search(r"Ref No\s*:\s*(\d+)", label.get_text(" ", strip=True))
            if m:
                ref = m.group(1)
                break
        fields = {}
        for block in card.select("div.tender-card-info-block"):
            label = block.select_one(".tender-card-info-label")
            val = block.select_one(".tender-card-info-value")
            if label and val:
                fields[label.get_text(strip=True).rstrip(" :").lower()] = val.get_text(" ", strip=True)
        due_iso = None
        m = re.search(r"([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})", fields.get("due date", ""))
        if m:
            try:
                due_iso = datetime.strptime(" ".join(m.groups()), "%b %d %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        state = None
        for a in card.select("a.tendlist_redi_link"):
            if "/state-tenders/" in a.get("href", ""):
                state = a.get_text(" ", strip=True).title()
                break
        results.append(
            {
                "raw_title": title,
                "raw_row": card.get_text(" | ", strip=True),
                "source": source_name,
                "refNo": None,
                "stableKey": f"t18-{ref}" if ref else None,
                "dueDateHint": due_iso,
                "value": _value(fields.get("tender value", "")),
                "organisation": _org(fields.get("agency / dept")),
                "location": state,
                "docUrl": urljoin(base_url, title_link["href"]),
            }
        )
    return results
