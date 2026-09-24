"""Parser for EESL's tenders page (eeslindia.org), a WordPress list."""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Row


def parse_eesl_tenders(html: str, source_name: str, base_url: str) -> list[Row]:
    """
    Parses eeslindia.org's "Tenders" page — a plain WordPress page, not a
    GePNIC portal. Every tender/notice the site has ever posted sits as its
    own <div class="current_latest_boxs ..."> on this single static page
    (confirmed live 2026-09-22: ~240 entries, oldest seen from 2021) — so
    unlike the GePNIC homepage widget, there's no rolling top-10 window for
    a match to rotate off of between scheduled checks.

    Two box shapes actually occur on the page:
      - title text directly in the box div, with its "Documents/Links" PDF
        link in a following SIBLING <div class="panel"> (not nested inside
        the box) — most entries.
      - no separate title: the box div directly wraps a single <a>, whose
        link text doubles as the title — seen on older/simpler notices.
    get_text() on the box div alone covers both shapes. The PDF link found
    is a genuine stable document URL (unlike GePNIC's session-bound
    DirectLink), so callers use it directly as the tender's url instead of
    falling back to source["searchUrl"].

    No structured closing/due date exists on this page for either shape —
    any date is inside the linked PDF itself, which this doesn't open.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for box in soup.find_all("div", class_="current_latest_boxs"):
        title = box.get_text(" ", strip=True)
        if not title:
            continue
        link = box.find("a", href=True)
        if not link:
            panel = box.find_next_sibling("div", class_="panel")
            if panel:
                link = panel.find("a", href=True)
        doc_url = urljoin(base_url, link["href"]) if link else None
        results.append(
            {
                "raw_title": title,
                "raw_row": title,
                "source": source_name,
                "refNo": None,
                "docUrl": doc_url,
            }
        )
    return results
