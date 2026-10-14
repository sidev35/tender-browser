"""Parsers for Australian state tender portals (static HTML lists)."""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Row


def _iso(text: str, fmt: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), fmt).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_vic_tenders(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Buying for Victoria search results (tenders.vic.gov.au/tender/search): a
    plain HTML table, one <tr data-tender-code=...> per tender with its
    code, status/type, title link, "Issued by: agency" and Opened/Closing
    dates ("Fri, 01 March 2030 2:00 pm"). The code is unique, so it is the
    stableKey. Only the date is kept (dueDateHint as yyyy-mm-dd): the
    portal's times are Australian, and the dashboard treats times as India time.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[Row] = []
    for tr in soup.find_all("tr", attrs={"data-tender-code": True}):
        link = tr.find("a", class_="tenderRowTitle")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        code = tr["data-tender-code"].strip()
        issuer = tr.find("span", class_="line-item-detail")
        organisation = re.sub(r"^Issued by:\s*", "", issuer.get_text(" ", strip=True)) if issuer else None
        closing = tr.find("span", class_="closing_date")
        due = _iso(closing.get_text(" ", strip=True), "%d %B %Y", r"\d{1,2} [A-Za-z]+ \d{4}") if closing else None
        rows.append(
            {
                "raw_title": title,
                "raw_row": f"{title} {organisation or ''}",
                "source": source_name,
                "refNo": code,
                "stableKey": code,
                "dueDateHint": due,
                "docUrl": urljoin(base_url, link["href"]),
                "organisation": organisation,
            }
        )
    return rows


def parse_tas_tenders(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Tasmania's "Open for bids" list (tenders.tas.gov.au/OpenForBids): a table
    where a header row "Closes: 20/10/2026, at 02:00 PM" precedes the tender's
    own row (title link, UNSPSC category, agency, opened date). The title
    often ends with the agency's reference in brackets.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[Row] = []
    closes: str | None = None
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        if th and "Closes" in th.get_text():
            closes = _iso(th.get_text(" ", strip=True), "%d/%m/%Y", r"\d{1,2}/\d{1,2}/\d{4}")
            continue
        link = tr.find("a", href=re.compile(r"/OpenForBids/Details/", re.I))
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        cells = tr.find_all("td")
        organisation = cells[2].get_text(" ", strip=True) if len(cells) > 2 else None
        ref = re.search(r"\(([^()]*\d[^()]*)\)\s*$", title)
        rows.append(
            {
                "raw_title": title,
                "raw_row": f"{title} {organisation or ''}",
                "source": source_name,
                "refNo": ref.group(1) if ref else None,
                "stableKey": urljoin(base_url, link["href"]),
                "dueDateHint": closes,
                "docUrl": urljoin(base_url, link["href"]),
                "organisation": organisation,
            }
        )
    return rows
