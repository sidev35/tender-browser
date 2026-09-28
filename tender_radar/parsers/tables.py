"""
Parser for tender listings shown as an HTML <table>: the NIC GePNIC homepage
widget (IOCL, CPPP, Rajasthan, MP) and the keyword-search results tables of
Gujarat nProcure, Telangana and Bihar.
"""

import re

from bs4 import BeautifulSoup

from ..models import Row
from ..normalize import format_rupees

# Header text -> what the column holds, checked in this order (first match
# wins). Seen live 2026-09-28:
#   Telangana: Tender ID | Enquiry/IFB/Tender Notice Number | Name of Work |
#              Estimated Contract Value
#   Bihar:     Tender/RFQ ID | Tender Description | Reference No.
#   Gujarat:   IFB/Tender Notice No. | Tender Brief
COLUMN_NAMES = [
    ("tenderId", re.compile(r"\b(tender|rfq)\s*(/\s*rfq\s*)?id\b", re.IGNORECASE)),
    ("refNo", re.compile(r"reference\s*no|tender\s*notice|ifb", re.IGNORECASE)),
    ("title", re.compile(r"name\s*of\s*work|tender\s*description|tender\s*brief|\btitle\b", re.IGNORECASE)),
    ("value", re.compile(r"(estimated|contract)\s*(contract\s*)?value", re.IGNORECASE)),
]


def named_columns(header_cells: list[str]) -> dict[str, int]:
    """{"tenderId": 1, "title": 4, ...} for header cells that name a known column."""
    found: dict[str, int] = {}
    for idx, header in enumerate(header_cells):
        for name, pattern in COLUMN_NAMES:
            if name not in found and pattern.search(header):
                found[name] = idx
                break
    return found


def _cell(cells: list[str], columns: dict[str, int], name: str) -> str | None:
    """The text of the column named `name` (see named_columns), or None."""
    idx = columns.get(name)
    if idx is None or idx >= len(cells):
        return None
    return cells[idx].strip() or None


def parse_gepnic_table(html: str, source_name: str) -> list[Row]:
    """
    Parses the 'Latest Tenders' table found on NIC GePNIC-based portals.
    Structure: a table with columns like
    [S.No, Tender Title, Reference No, Closing Date, Bid Opening Date]
    This is intentionally forgiving — GePNIC installs differ slightly by
    department, so we scan all tables and pick rows that look like tenders.

    Does NOT try to capture the row's own "DirectLink" — confirmed live
    (2026-09-18) that these are tied to the scraper's own session and show
    "Stale Session" for literally anyone else who opens one, even seconds
    later. The dashboard instead links every matched tender to the
    portal's own search page (source["searchUrl"], set by
    pipeline.scrape_source) — stable, session-independent, and where a real
    visitor can search the tender's title themselves and solve the page's
    captcha.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    # NIC GePNIC homepages render the real "latest tenders" widget as
    # <table id="activeTenders">, surrounded by dozens of unrelated layout
    # tables (nav/menus/banners). Scanning every table on the page — as this
    # used to do — picks up that surrounding chrome as bogus "tender rows"
    # (e.g. "Screen Reader Access 17-Sep-2026 Search | Active Tenders...").
    # Prefer the real table by id; only fall back to scanning everything for
    # a portal layout we don't recognize (parse_generic_table's use case).
    date_pattern = re.compile(r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}")
    # Stricter than date_pattern above: matches only when the WHOLE cell is a
    # date/timestamp (e.g. "21-Sep-2026 03:00 PM"), not just contains a
    # date-like substring anywhere. Needed because plenty of real reference
    # numbers embed a fiscal-year-style substring like "26-27" (e.g.
    # "PWD/Div8/ASW/2001/21/26-27/L1") that date_pattern.search() would
    # otherwise misfire on, wrongly excluding a genuine ref number from
    # candidacy below.
    full_date_cell_pattern = re.compile(
        r"^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}(\s+\d{1,2}:\d{2}\s*[AP]M)?$", re.IGNORECASE
    )
    # Match the id only on a <table>: Gujarat nProcure (js_interactive_search)
    # also has an element with id="activeTenders", but it's a <div> with no
    # rows, and matching it by bare id hid the real results table there —
    # confirmed 2026-09-23: 2 real matches rendered, 0 parsed.
    active_table = soup.find("table", id="activeTenders")
    tables = [active_table] if active_table else soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        # Best-effort: if this table has a real header row, find which
        # column is the actual closing/end date — so extract_due_date() can
        # be pointed at that ONE cell instead of guessing from the whole
        # row's text. Needed because a row can contain several date-shaped
        # strings (e.g. Telangana's rows have Published / Bid Start / Bid
        # Closing date-times, plus a reference number that itself embeds an
        # unrelated notice date) — scanning the flattened row text left-to-
        # right silently grabs the wrong one. Falls back to None (today's
        # existing whole-row-text behavior, unchanged) when no such header
        # is found, so portals without a recognizable header row — or
        # without this ambiguity in the first place — aren't affected.
        closing_col_idx = None
        columns: dict[str, int] = {}
        if rows:
            header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
            for idx, h in enumerate(header_cells):
                h_l = h.lower()
                if "closing" in h_l or "end date" in h_l:
                    closing_col_idx = idx
                    break
            columns = named_columns(header_cells)
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            row_text = " | ".join(cells)
            # Heuristic: a tender row usually has a date-like string in it
            if date_pattern.search(row_text):
                # The site's own table renders the title cell as "N. <actual
                # title>" (N = that row's position in ITS table, not a stable
                # tender property). Strip it for comparison purposes — but
                # compare every candidate cell *normalized* the same way, not
                # the raw cell against the already-stripped title, or the
                # still-prefixed title cell itself always looks "different"
                # from the stripped title and gets wrongly picked as the
                # reference number, before the loop ever reaches the real one.
                def strip_prefix(c: str) -> str:
                    return re.sub(r"^\s*\d+\.\s*", "", c).strip()

                # A column named like a title wins; else the longest cell is usually the title.
                title = strip_prefix(_cell(cells, columns, "title") or max(cells, key=len))
                # Best-effort: the reference number is the remaining
                # short, non-date, non-title cell (e.g. "1/WKS/04/26-Gl" or a
                # numeric tender id) — gives users a second, more precise
                # value to paste into the portal's "Tender Ref No" search
                # field alongside the title. None if no such cell exists
                # (some portal layouts just don't have a distinct one).
                # Also skips cells that are PURELY digits: confirmed on
                # Bihar's js_interactive_search table that a plain S.No
                # column ("1", "2", ...) sits ahead of the real reference
                # number in cell order and would otherwise get picked
                # first — a genuine reference number almost always mixes
                # letters and digits (or at least isn't just a small row
                # index), so this is a safe general filter, not a
                # Bihar-specific hack.
                ref_no = next(
                    (
                        c
                        for c in cells
                        if strip_prefix(c).lower() != title.lower()
                        and c.strip()
                        and not full_date_cell_pattern.match(c.strip())
                        and not c.strip().isdigit()
                    ),
                    None,
                )
                if ref_no:
                    ref_no = strip_prefix(ref_no) or None
                # A column named like a reference number wins over the guess
                # above: Telangana's first column is the department name, which
                # the guess used to pick (the known Telangana refNo bug).
                ref_no = _cell(cells, columns, "refNo") or ref_no
                due_date_hint = (
                    cells[closing_col_idx]
                    if closing_col_idx is not None and closing_col_idx < len(cells)
                    else None
                )
                results.append(
                    {
                        "raw_title": title,
                        "raw_row": row_text,
                        "source": source_name,
                        "refNo": ref_no,
                        "dueDateHint": due_date_hint,
                        # The portal's own tender id, when a column is named
                        # like one (Telangana "Tender ID", Bihar "Tender/RFQ
                        # ID"): searching it on the portal finds exactly this
                        # tender. Not used as the record's id, so tenders
                        # already saved keep theirs.
                        "tenderId": _cell(cells, columns, "tenderId"),
                        "value": format_rupees(_cell(cells, columns, "value")),
                    }
                )
    return results


def parse_generic_table(html: str, source_name: str) -> list[Row]:
    """Fallback parser: same idea as GePNIC but looser, for other portal layouts."""
    return parse_gepnic_table(html, source_name)
