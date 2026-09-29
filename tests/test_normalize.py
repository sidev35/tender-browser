"""The small helpers that turn a parsed row into a stored tender record, plus
parser edge cases that are easier to pin down with tiny hand-written HTML."""

import pytest

from tender_radar.matching import FALLBACK_EV_CATEGORY, matches_categories
from tender_radar.normalize import (
    clean_title,
    exact_title_prefix,
    extract_due_date,
    extract_value,
    make_stable_id,
    search_text,
)
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


# --- search_text / exact_title_prefix ------------------------------------------


def test_title_prefix_stops_before_a_line_break_the_portal_keeps():
    # Gujarat's own copy has "Operate\nand"; a pasted search can't match past it.
    raw = "Selection of Charge Point Operator (CPO) for Design, Build, Finance, Operate\nand Maintain EVPCS"
    assert (
        exact_title_prefix(raw)
        == "Selection of Charge Point Operator (CPO) for Design, Build, Finance, Operate"
    )


def test_title_prefix_stops_before_a_double_space_and_at_100_chars():
    assert exact_title_prefix("Request for Selection  for Charge Point Operators") is None  # too short left
    long = (
        "Supply, Installation, Testing and Commissioning of Electrical Infrastructure "
        "from 11kV (HT) to 415 V (LT) under Phase-02"
    )
    prefix = exact_title_prefix(long)
    assert len(prefix) <= 100 and long.startswith(prefix) and not prefix.endswith(" ")


@pytest.mark.parametrize(
    "source, row, expected",
    [
        (
            {"searchKeyword": "charging station", "searchBy": "tenderId"},
            {"tenderId": "736408", "raw_title": "x"},
            "736408",
        ),
        (
            {"searchKeyword": "charging station", "searchBy": "tenderId"},
            {"raw_title": "x"},
            "charging station",
        ),
        ({"searchKeyword": "charging station"}, {"tenderId": "736408", "raw_title": "x"}, "charging station"),
        (
            {
                "searchKeyword": "charging station",
                "searchBy": "titlePrefix",
                "titleRegex": r"Name Of Work\s*:\s*(.+)",
            },
            {"raw_title": "VMC Tender Id :1 Name Of Work : Supply of EV chargers for the Gotri depot"},
            "Supply of EV chargers for the Gotri depot",
        ),
        ({}, {"raw_title": "Anything"}, None),  # no keyword: the card copies the title
        # "title": copy the full title (Bihar), even though it has a keyword and a tender ID.
        (
            {"searchKeyword": "charging stations", "searchBy": "title"},
            {"tenderId": "7", "raw_title": "x"},
            None,
        ),
    ],
)
def test_search_text_by_source_setting(source, row, expected):
    assert search_text(source, row) == expected


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


BATTERY = "Battery, BESS & Power Electronics"


@pytest.mark.parametrize(
    "title",
    [
        "Bids invited Battery Tester (Q3)",
        "Bids invited Battery Pack Tester 600 A, 1000V, 2 Channels",
        "Tender Epc Package Bess (400Mwh) Implementation",
        "Supply of Truck Mounted Mobile Battery Energy Storage System",
        "Supply and Installation UPS Energy Storage System",
        "Energy Management System for the substation",
        "Power Conversion System for BESS",
        "Supply of 10 kW solar inverter",
        "Tender Supply Installation Commissioning Hydrogen Electrolyser",
        "Procurement of E-Rickshaw with battery charger",
        "Supply of 3W charger for electric three wheelers",
    ],
)
def test_battery_and_power_electronics_tenders_are_kept(title):
    assert matches_categories(title) == [BATTERY]


@pytest.mark.parametrize(
    "title",
    [
        "Supply of 1.5 Ton 3 Star Inverter Split Air Conditioners",  # an AC, not an inverter
        "Bids invited 1.8Tr/2Tr Inverter Type Split Ac",
        "Replacement of Non- Inverter Type Led Batten Fittings",
        "Civil maintenance works inside battery area at Gujarat refinery",  # just "battery"
        "Supply of 100 Pcs of LED lamps",  # "Pcs" = pieces
        "108 EMS ambulance services",  # emergency medical services
        "Bids invited Split Ac ( Inverter Type) 2 Ton Capacity",  # AC named before "inverter"
        "Bids Are invited for Portable Inverter Dc Welding Machine",
        "Recertification Energy Management System (EnMS) ISO 50001",  # a certification service
        "Bids invited Inverter Based Led Street Light (V2)",
    ],
)
def test_look_alikes_are_not_kept(title):
    assert matches_categories(title) == []


def test_an_ev_tender_mentioning_bess_stays_an_ev_tender():
    # The EV categories come first.
    assert matches_categories("EV charging station with BESS") == ["Charger Supply & Installation"]


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
