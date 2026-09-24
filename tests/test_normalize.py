"""The small helpers that turn a parsed row into a stored tender record, plus
parser edge cases that are easier to pin down with tiny hand-written HTML."""

import pytest

from tender_radar.matching import FALLBACK_EV_CATEGORY, matches_categories
from tender_radar.normalize import clean_title, extract_due_date, extract_value, make_stable_id
from tender_radar.parsers import parse_gepnic_table

# --- extract_due_date --------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Closes 2026-09-28 16:00", "2026-09-28"),  # ISO (Bihar)
        ("08-Oct-2026 04:00 PM", "2026-10-08"),  # dd-Mon-yyyy (GePNIC)
        ("28/09/2026 02:00 PM", "2026-09-28"),  # dd/mm/yyyy (Telangana)
        ("Last Date : 03-10-2026 13:00:00", "2026-10-03"),  # dd-mm-yyyy (Gujarat)
        ("PRO No. 394/2026-27 | 03-10-2026", "2026-10-03"),  # fiscal-year "2026-27" isn't a date
        ("no date here", None),
        ("31-Feb-2026", None),  # impossible date
    ],
)
def test_extract_due_date(text, expected):
    assert extract_due_date(text) == expected


# --- clean_title / extract_value ---------------------------------------------


def test_clean_title_without_regex_only_collapses_whitespace():
    assert clean_title({}, "  EV  Charging\nstation ") == "EV Charging station"


def test_clean_title_falls_back_when_regex_does_not_match():
    src = {"titleRegex": r"Name Of Work\s*:\s*(.+)"}
    assert clean_title(src, "Plain title") == "Plain title"


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("25481341.00", "₹2.55 Cr"),
        ("2609000", "₹26.09 Lakh"),
        ("75,000", "₹75,000"),
        ("0.00", None),  # nProcure's "not disclosed"
    ],
)
def test_extract_value_formats_amounts(amount, expected):
    src = {"valueRegex": r"Value\s*:\s*([\d,]+(?:\.\d+)?)"}
    assert extract_value(src, f"Estimated Contract Value : {amount} Last Date") == expected


def test_extract_value_without_regex_is_none():
    assert extract_value({}, "Estimated Contract Value : 100000") is None


# --- matches_categories -------------------------------------------------------


def test_non_ev_title_is_dropped():
    assert matches_categories("Annual rate contract for housekeeping") == []


def test_specific_category_match():
    assert matches_categories("Selection of Charge Point Operator for EV charging stations") == [
        "PPP / Concession / CPO Selection",
        "Charger Supply & Installation",
    ]


def test_ev_title_with_no_category_gets_the_fallback():
    title = "Electrical Infrastructure For Intermediate Charging Station At Tuni Bus Station"
    assert matches_categories(title) == [FALLBACK_EV_CATEGORY]


def test_irregular_whitespace_still_matches():
    # Telangana's markup produced "EV  Charging" (two spaces).
    assert matches_categories("installation of EV  Charging stations") != []


# --- make_stable_id ----------------------------------------------------------


def test_stable_id_is_deterministic_and_source_specific():
    a = make_stable_id("Source A", "Same title")
    assert a == make_stable_id("Source A", "Same title")
    assert a != make_stable_id("Source B", "Same title")
    assert a.startswith("AUTO-")


# --- parse_gepnic_table edge cases --------------------------------------------

ROW = "<tr><td>1. EV charging station supply</td><td>REF/1</td><td>05-Oct-2026</td></tr>"


def test_real_active_tenders_table_takes_precedence():
    html = (
        "<table><tr><td>layout chrome</td><td>menu</td><td>01-Jan-2027</td></tr></table>"
        f'<table id="activeTenders">{ROW}</table>'
    )
    rows = parse_gepnic_table(html, "t")
    assert [r["raw_title"] for r in rows] == ["EV charging station supply"]


def test_active_tenders_id_on_a_div_does_not_hide_tables():
    # Gujarat nProcure regression (see test_parsers.test_gujarat_finds_both_results).
    html = f'<div id="activeTenders"></div><table>{ROW}</table>'
    assert len(parse_gepnic_table(html, "t")) == 1


def test_rows_without_a_date_are_skipped():
    html = "<table><tr><td>EV charging station</td><td>REF/1</td><td>no date</td></tr></table>"
    assert parse_gepnic_table(html, "t") == []
