"""Parser for Tasmania Tenders (tenders.tas.gov.au, "Open for bids")."""

import calendar
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...models import Row
from .dates import iso


def parse_tas_tenders(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Tasmania's "Open for bids" list (tenders.tas.gov.au/OpenForBids): a table
    where a header row "Closes: 20/10/2026, at 02:00 PM" precedes the tender's
    own row (title link, UNSPSC category, agency, opened date). The title
    often ends with the agency's reference in brackets.

    The "Future opportunities" list has the same shape, with a header row
    "Indicative Tender Date: Jun 2026" instead: only a month, so the last day
    of that month stands in as the date, which lets the tender expire once
    that month has passed instead of sitting in the data for ever.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[Row] = []
    closes: str | None = None
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        if th and "Closes" in th.get_text():
            closes = iso(th.get_text(" ", strip=True), "%d/%m/%Y", r"\d{1,2}/\d{1,2}/\d{4}")
            continue
        if th and "Indicative" in th.get_text():
            m = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", th.get_text(" ", strip=True))
            closes = None
            if m:
                try:
                    month = datetime.strptime(m.group(1)[:3], "%b").month
                    year = int(m.group(2))
                    closes = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
                except ValueError:
                    pass
            continue
        link = tr.find("a", href=re.compile(r"/(OpenForBids|FutureOpportunity)/Details/", re.I))
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
