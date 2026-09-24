"""Parser for TenderDetail's public keyword listing pages (tenderdetail.com)."""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Row

CORRIGENDUM_PREFIX = re.compile(r"^\s*corrigendum\s*[:\-–]\s*", re.IGNORECASE)


def parse_tenderdetail_list(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Parses a tenderdetail.com keyword listing page (e.g.
    /Indian-tender/charging-station-tenders) — a paid aggregator, but this
    listing is public with no login (confirmed live 2026-09-23; robots.txt
    allows all). Plain server-rendered HTML, no JS needed: each result is a
    <div class="tc tender-card"> (~50 on the page) with
      - a "#<number>" tag badge: TenderDetail's own tender id. Used as the
        stable id key (titles repeat across tenders here, e.g. several
        "Bids Are Invited For Procurement Of Charging Station ..."), but NOT
        as refNo — it's the aggregator's number, not the issuing authority's,
        so pasting it into an official portal's search would find nothing.
      - "Closes Mon DD, YYYY" closing date
      - a value like "₹ 26.09 Lakh", or "Ref. Document" when undisclosed
      - the state in .tc-state
      - a.tc-title linking to the tender's stable notice page, used as url.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("div.tender-card"):
        title_link = card.select_one("a.tc-title")
        if not title_link:
            continue
        # An amended tender is listed as "Corrigendum : <real title>"; the
        # prefix isn't part of the tender's title (confirmed 2026-09-24:
        # 8 of 50 saved TenderDetail titles had it).
        title = CORRIGENDUM_PREFIX.sub("", title_link.get_text(" ", strip=True))
        td_id = next(
            (
                t.get_text(strip=True)[1:]
                for t in card.select(".tc-tags")
                if re.fullmatch(r"#\d+", t.get_text(strip=True))
            ),
            None,
        )
        due_iso = None
        closes = card.select_one(".td-urgent")
        m = re.search(
            r"Closes\s+([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})",
            closes.get_text(" ", strip=True) if closes else "",
        )
        if m:
            try:
                due_iso = datetime.strptime(" ".join(m.groups()), "%b %d %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        value_el = card.select_one(".tv-urgent")
        value = " ".join(value_el.get_text(" ", strip=True).split()) if value_el else ""
        if not re.search(r"\d", value):
            value = None  # "Ref. Document" = value not disclosed
        state_el = card.select_one(".tc-state")
        results.append(
            {
                "raw_title": title,
                "raw_row": card.get_text(" | ", strip=True),
                "source": source_name,
                "refNo": None,
                "stableKey": f"td-{td_id}" if td_id else None,
                "dueDateHint": due_iso,
                "value": value.replace("₹ ", "₹") if value else None,
                "location": state_el.get_text(" ", strip=True) if state_el else None,
                "docUrl": urljoin(base_url, title_link["href"]),
            }
        )
    return results
