"""Parser for Buying for Victoria (tenders.vic.gov.au). Tenders ACT runs on the same platform and layout, so it uses this too."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...models import Row
from .dates import iso


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
        due = iso(closing.get_text(" ", strip=True), "%d %B %Y", r"\d{1,2} [A-Za-z]+ \d{4}") if closing else None
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
