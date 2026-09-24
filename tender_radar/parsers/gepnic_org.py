"""
Parsers for a GePNIC portal's "Tenders by Organisation" pages (CPPP, IOCL and
every other NIC GePNIC portal share them). Unlike the homepage widget (only
the 10 newest tenders site-wide) and Active Tenders / Tenders by Closing Date
(behind a captcha), these list every active tender, with no captcha
(confirmed live 2026-09-24 on etenders.gov.in and iocletenders.nic.in):

  1. the organisation list: <table id="table"> rows of
     [S.No, Organisation Name, Tender Count], the count linking to...
  2. ...that organisation's tender list: <table id="table"> rows of
     [S.No, e-Published Date, Closing Date, Opening Date,
      Title and Ref.No./Tender ID, Organisation Chain], all on one page
     (CPPP's largest, NHAI with 412 tenders, isn't paginated).
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Row

# "[title] [ref no][2026_AWEIL_291513_1]": the square-bracketed parts of the
# "Title and Ref.No./Tender ID" cell.
_BRACKETED = re.compile(r"\[([^\[\]]*)\]")
_TENDER_ID = re.compile(r"^\d{4}_[A-Za-z0-9]+_\d+_\d+$")


def is_captcha_page(html: str) -> bool:
    """True if the page is asking for a captcha instead of showing a list."""
    soup = BeautifulSoup(html, "html.parser")
    return (
        soup.find("input", attrs={"name": "captchaText"}) is not None
        and soup.find("table", id="table") is None
    )


def parse_gepnic_org_list(html: str, base_url: str) -> list[dict]:
    """
    The organisation list: [{"name", "count", "href"}] for every organisation
    with at least one tender, in the page's order. href opens that
    organisation's tender list; it's tied to the browser session that loaded
    this page, so it must be opened in that same session.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table")
    orgs = []
    for tr in table.find_all("tr")[1:] if table else []:
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        count_text = cells[2].get_text(strip=True)
        link = cells[2].find("a", href=True)
        if count_text.isdigit() and int(count_text) > 0 and link:
            orgs.append(
                {
                    "name": cells[1].get_text(" ", strip=True),
                    "count": int(count_text),
                    "href": urljoin(base_url, link["href"]),
                }
            )
    return orgs


def parse_gepnic_org_tenders(html: str, source_name: str) -> list[Row]:
    """One organisation's tender list -> rows (see parsers/__init__.py)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table")
    results = []
    for tr in table.find_all("tr")[1:] if table else []:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 6:
            continue
        parts = [p.strip() for p in _BRACKETED.findall(cells[4])]
        tender_id = parts.pop() if parts and _TENDER_ID.match(parts[-1]) else None
        ref_no = parts.pop() if len(parts) >= 2 else None
        title = " ".join(parts) or cells[4]
        results.append(
            {
                "raw_title": title,
                "raw_row": " | ".join(cells),
                "source": source_name,
                "refNo": ref_no or None,
                "dueDateHint": cells[2],  # the Closing Date column
                # The portal's own tender id is unique; titles often aren't.
                "stableKey": f"gepnic-{tender_id}" if tender_id else None,
                "organisation": cells[5],
            }
        )
    return results
