"""GePNIC "Tenders by Organisation" pages (CPPP, IOCL), parsed from real pages
saved 2026-09-24, and the rotation that spreads organisations over runs."""

import pytest

from tender_radar.fetchers import rotation_slice
from tender_radar.normalize import extract_due_date
from tender_radar.parsers import is_captcha_page, parse_gepnic_org_list, parse_gepnic_org_tenders

CPPP = "https://etenders.gov.in/eprocure/app"
IOCL = "https://iocletenders.nic.in/nicgep/app"


def test_cppp_organisation_list(fixture_html):
    orgs = parse_gepnic_org_list(fixture_html("gepnic_org_list_cppp"), CPPP)
    assert len(orgs) == 78
    assert sum(o["count"] for o in orgs) == 1946
    assert orgs[1]["name"] == "ADVANCED WEAPONS AND EQUIPMENT INDIA LTD-AWEIL"
    assert orgs[1]["count"] == 14
    assert orgs[1]["href"].startswith(CPPP + "?component=%24DirectLink")


def test_iocl_is_one_organisation(fixture_html):
    orgs = parse_gepnic_org_list(fixture_html("gepnic_org_list_iocl"), IOCL)
    assert [(o["name"], o["count"]) for o in orgs] == [("IndianOil", 222)]


def test_organisation_tender_list(fixture_html):
    rows = parse_gepnic_org_tenders(fixture_html("gepnic_org_tenders_cppp"), "CPPP")
    assert len(rows) == 14  # matches the organisation's count on the list page
    first = rows[0]
    # "[title] [ref no][tender id]" is split into its three parts.
    assert first["raw_title"] == "Minor electrical work outside RFI Premises"
    assert first["refNo"] == "RFI/TE/RD2510/2026-27/EO (C)"
    assert first["stableKey"] == "gepnic-2026_AWEIL_291513_1"
    assert extract_due_date(first["dueDateHint"]) == "2026-10-09"
    assert first["organisation"].startswith("ADVANCED WEAPONS AND EQUIPMENT INDIA LTD-AWEIL")
    assert len({r["stableKey"] for r in rows}) == 14


def test_captcha_page_is_recognised(fixture_html):
    # Active Tenders asks for a captcha; the organisation list doesn't.
    assert is_captcha_page(fixture_html("gepnic_active_tenders_captcha"))
    assert not is_captcha_page(fixture_html("gepnic_org_list_cppp"))


@pytest.mark.parametrize(
    "slot, expected",
    [
        (0, [0, 1, 2]),
        (1, [3, 4, 5]),
        (2, [6, 0, 1]),  # wraps around
        (3, [2, 3, 4]),
    ],
)
def test_rotation_walks_through_every_organisation(slot, expected):
    assert rotation_slice(list(range(7)), 3, slot) == expected


def test_rotation_covers_everything_in_ceil_n_over_k_runs():
    orgs = list(range(78))
    seen = set()
    for slot in range(8):  # ceil(78 / 10)
        seen.update(rotation_slice(orgs, 10, slot))
    assert seen == set(orgs)


def test_small_lists_are_read_in_full_every_run():
    assert rotation_slice(["IndianOil"], 10, 5) == ["IndianOil"]
    assert rotation_slice([1, 2, 3], 0, 5) == [1, 2, 3]  # no orgsPerRun: all
