"""
Each source's parser run on a real page saved in tests/fixtures/ (captured
2026-09-24). Expected values are what that page actually contained; when a
fixture is re-captured, update them to match the new page.
"""

import pytest

from tender_radar.matching import matches_categories
from tender_radar.normalize import clean_title, extract_due_date, extract_value
from tender_radar.parsers import (
    parse_eesl_tenders,
    parse_generic_table,
    parse_gepnic_table,
    parse_tenderdetail_list,
)

GUJARAT = "Gujarat nProcure (keyword search)"
TELANGANA = "Telangana e-Procurement (keyword search)"
BIHAR = "Bihar e-Procurement 2.0 (keyword search)"


def due(row):
    """The due date run() would store for this row."""
    return extract_due_date(row.get("dueDateHint") or row["raw_row"])


# --- NIC GePNIC homepage widget (IOCL) ---------------------------------------


def test_gepnic_reads_the_ten_row_widget(fixture_html):
    rows = parse_gepnic_table(fixture_html("gepnic_iocl"), "IOCL")
    assert len(rows) == 10


def test_gepnic_row_fields(fixture_html):
    row = parse_gepnic_table(fixture_html("gepnic_iocl"), "IOCL")[0]
    # The site's "1. " row-number prefix is stripped from the title.
    assert row["raw_title"] == "IT HARDWARE REPLACEMENT AND CAMC TAS"
    # A ref no containing a fiscal-year "26-27" isn't mistaken for a date.
    assert row["refNo"] == "MnC/NR/UPSOII/OPS/PT-104/26-27"
    # First date in the row is the closing date (the second is bid opening).
    assert due(row) == "2026-10-08"


# --- EESL WordPress list -----------------------------------------------------


def test_eesl_reads_every_entry(fixture_html):
    rows = parse_eesl_tenders(fixture_html("eesl"), "EESL", "https://eeslindia.org/en/tenders/")
    assert len(rows) == 241
    # Two old notices on the page have no document link at all; they get
    # docUrl None (so run() falls back to the listing page), not a crash.
    assert sum(1 for r in rows if not r["docUrl"]) == 2


def test_eesl_ev_matches_link_to_their_pdfs(fixture_html):
    rows = parse_eesl_tenders(fixture_html("eesl"), "EESL", "https://eeslindia.org/en/tenders/")
    ev = [r for r in rows if matches_categories(r["raw_title"])]
    assert [r["docUrl"] for r in ev] == [
        "https://eeslindia.org/wp-content/uploads/2026/06/TenderDocument_EVCI.pdf",
        "https://eeslindia.org/wp-content/uploads/2025/10/RFP_EVCI_MH_252605_Signed.pdf",
    ]


# --- TenderDetail listing ----------------------------------------------------


@pytest.fixture
def tenderdetail_rows(fixture_html):
    return parse_tenderdetail_list(
        fixture_html("tenderdetail"),
        "TenderDetail",
        "https://www.tenderdetail.com/Indian-tender/charging-station-tenders",
    )


def test_tenderdetail_reads_all_cards_with_unique_ids(tenderdetail_rows):
    assert len(tenderdetail_rows) == 50
    # Titles repeat on this site, so ids must come from its own tender number.
    assert len({r["stableKey"] for r in tenderdetail_rows}) == 50


def test_tenderdetail_card_fields(tenderdetail_rows):
    row = next(r for r in tenderdetail_rows if r["stableKey"] == "td-57473059")
    assert row["raw_title"] == "Tender for E- Charging Station E-Rikshaw Stand"
    assert row["dueDateHint"] == "2026-10-08"
    assert row["value"] == "₹26.09 Lakh"
    assert row["location"] == "Uttar Pradesh"
    assert row["docUrl"] == (
        "https://www.tenderdetail.com/Indian-Tenders/TenderNotice/57473059/8fb357a01536d718df2ecbfc2c6b947c"
    )
    # TenderDetail's own number is not the issuing authority's ref no.
    assert row["refNo"] is None


def test_tenderdetail_drops_the_corrigendum_prefix(tenderdetail_rows):
    # The site lists an amended tender as "Corrigendum : <title>".
    assert not any(r["raw_title"].lower().startswith("corrigendum") for r in tenderdetail_rows)
    row = next(r for r in tenderdetail_rows if r["stableKey"] == "td-57366481")
    assert row["raw_title"] == "Bids Are invited for Ac Ev Charging Station (Q2)"


def test_tenderdetail_undisclosed_value_is_none(tenderdetail_rows):
    # Cards that say "Ref. Document" instead of an amount.
    assert sum(1 for r in tenderdetail_rows if r["value"]) == 35
    assert all(r["value"] is None or r["value"].startswith("₹") for r in tenderdetail_rows)


# --- Keyword-search portals (parsed with parse_generic_table) -----------------


def test_gujarat_finds_both_results(fixture_html):
    # Regression: nProcure has a <div id="activeTenders"> that used to be
    # mistaken for the GePNIC widget, hiding the real table (0 rows parsed).
    rows = parse_generic_table(fixture_html("gujarat_nprocure"), GUJARAT)
    assert len(rows) == 2


def test_gujarat_title_value_and_due_date(fixture_html, source):
    src = source(GUJARAT)
    rows = parse_generic_table(fixture_html("gujarat_nprocure"), GUJARAT)
    first, second = rows
    assert clean_title(src, first["raw_title"]) == (
        "Supply, Installation, Testing and Commissioning of Electrical Infrastructure "
        "from 11kV (HT) to 415 V (LT) under Phase-02 at the Charging Station at Gotri "
        "under PM eBus Sewa Scheme with Two (02) Years of O&M"
    )
    assert first["refNo"] == "PRO No. 394/2026-27"
    assert extract_value(src, first["raw_row"]) == "₹2.55 Cr"
    assert due(first) == "2026-10-03"
    # "Estimated Contract Value : 0.00" means not disclosed.
    assert extract_value(src, second["raw_row"]) is None
    assert due(second) == "2026-10-09"


def test_telangana_uses_the_closing_date_column(fixture_html):
    rows = parse_generic_table(fixture_html("telangana"), TELANGANA)
    assert len(rows) == 3
    assert rows[0]["raw_title"].startswith("Providing CC Pavement, washing plant")
    # Rows have several date-times; the "closing" header column picks the right one.
    assert rows[0]["dueDateHint"] == "28/09/2026 02:00 PM"
    assert [due(r) for r in rows] == ["2026-09-28", "2026-09-29", "2026-09-29"]


@pytest.mark.xfail(
    strict=True,
    reason="Known bug: Telangana's refNo picks up the department "
    "name column instead of the reference number.",
)
def test_telangana_ref_no_is_a_reference_number(fixture_html):
    rows = parse_generic_table(fixture_html("telangana"), TELANGANA)
    # Real reference numbers contain digits; department names don't.
    assert all(r["refNo"] is None or any(ch.isdigit() for ch in r["refNo"]) for r in rows)


def test_bihar_skips_serial_number_for_ref_no(fixture_html):
    rows = parse_generic_table(fixture_html("bihar"), BIHAR)
    assert len(rows) == 1
    row = rows[0]
    assert row["raw_title"].startswith("Request for Empanelment (RFE) For Empanelment of Agencies")
    # The plain "1" S.No column sits before it and must not be picked.
    assert row["refNo"] == "RFE Notice No. 7422"
    assert due(row) == "2026-09-28"
