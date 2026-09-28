"""The same tender listed by more than one source is kept once, official first."""

import pytest

from tender_radar import fetchers
from tender_radar.dedupe import DuplicateIndex, dedupe_records, normalised_title
from tender_radar.pipeline import scrape_source

SOURCES = [
    {"name": "Bihar e-Procurement", "type": "js_interactive_search"},
    {"name": "Telangana e-Procurement", "type": "js_interactive_search"},
    {"name": "TenderDetail", "type": "tenderdetail_list"},
]


def rec(id_, source, desc="Empanelment of agencies for EV charging stations", **extra):
    base = {
        "id": id_,
        "desc": desc,
        "source": source,
        "dueDate": "2026-09-28",
        "firstSeen": "2026-09-22",
        "value": None,
        "location": None,
        "refNo": None,
        "url": f"https://{id_}",
        "linkType": "search",
    }
    return {**base, **extra}


def test_title_normalisation_ignores_case_punctuation_and_leading_dots():
    assert normalised_title("...Supply Of EV Chargers, Lot-1") == normalised_title(
        "supply of ev chargers lot 1"
    )


def test_official_copy_is_kept_and_filled_in_from_the_aggregator():
    official = rec("B1", "Bihar e-Procurement")
    aggregator = rec("T1", "TenderDetail", value="₹34.25 Lakh", location="Bihar", linkType="direct")
    kept, dropped = dedupe_records([aggregator, official], SOURCES)
    assert [r["id"] for r in kept] == ["B1"]
    assert [r["id"] for r in dropped] == ["T1"]
    assert kept[0]["value"] == "₹34.25 Lakh"  # filled in from TenderDetail
    assert kept[0]["location"] == "Bihar"
    assert kept[0]["url"] == "https://B1"  # but the official link stays


def test_a_missing_due_date_still_matches_and_gets_filled_in():
    official = rec("B1", "Telangana e-Procurement", dueDate=None)
    aggregator = rec("T1", "TenderDetail", dueDate="2026-09-28")
    kept, _ = dedupe_records([official, aggregator], SOURCES)
    assert [(r["id"], r["dueDate"]) for r in kept] == [("B1", "2026-09-28")]


def test_different_due_dates_are_different_tenders():
    kept, dropped = dedupe_records(
        [rec("B1", "Bihar e-Procurement"), rec("T1", "TenderDetail", dueDate="2026-10-15")], SOURCES
    )
    assert len(kept) == 2 and dropped == []


def test_same_title_on_one_official_portal_is_not_merged():
    # Each has its own tender id on that portal, e.g. two lots with one title.
    kept, _ = dedupe_records([rec("B1", "Bihar e-Procurement"), rec("B2", "Bihar e-Procurement")], SOURCES)
    assert len(kept) == 2


def test_an_aggregator_listing_one_tender_twice_is_merged():
    kept, _ = dedupe_records(
        [
            rec("T2", "TenderDetail", firstSeen="2026-09-24"),
            rec("T1", "TenderDetail", firstSeen="2026-09-23"),
        ],
        SOURCES,
    )
    assert [r["id"] for r in kept] == ["T1"]  # the one saved first


def test_first_seen_is_the_earliest_of_the_copies():
    official = rec("B1", "Bihar e-Procurement", firstSeen="2026-09-25")
    aggregator = rec("T1", "TenderDetail", firstSeen="2026-09-22")
    kept, _ = dedupe_records([official, aggregator], SOURCES)
    assert kept[0]["firstSeen"] == "2026-09-22"


OFFICIAL_VADODARA = (
    "Selection of Charge Point Operator (CPO) for Design, Build, Finance, Operate and Maintain "
    "Electric Vehicle Public Charging Stations (EVPCS) at Approved Locations across Vadodara City "
    "under category A & B , in accordance with PM E- Drive Scheme"
)
CUT_VADODARA = (
    "...Selection Of Charge Point Operator (Cpo) For Design, Build, Finance, Operate And Maintain "
    "Electric Vehicle Public Charging Stations (Evpcs) At Approved Locations Across Vadodara City "
    "Under Category A & B, In Accordance With Pm E-Drive Scheme On..."
)


def test_a_title_cut_short_by_the_aggregator_matches_the_official_one():
    # Real case from 2026-09-28: Gujarat's portal and TenderDetail's shortened copy.
    sources = SOURCES + [{"name": "Gujarat nProcure", "type": "js_interactive_search"}]
    official = rec("G1", "Gujarat nProcure", desc=OFFICIAL_VADODARA, dueDate="2026-10-09")
    cut = rec("T1", "TenderDetail", desc=CUT_VADODARA, dueDate="2026-10-09")
    kept, _ = dedupe_records([cut, official], sources)
    assert [r["id"] for r in kept] == ["G1"]


def test_a_cut_title_needs_the_same_closing_date():
    sources = SOURCES + [{"name": "Gujarat nProcure", "type": "js_interactive_search"}]
    official = rec("G1", "Gujarat nProcure", desc=OFFICIAL_VADODARA, dueDate="2026-10-09")
    for due in ("2026-10-20", None):
        cut = rec("T1", "TenderDetail", desc=CUT_VADODARA, dueDate=due)
        kept, _ = dedupe_records([official, cut], sources)
        assert len(kept) == 2, due


def test_a_missing_space_in_one_copy_still_matches():
    # TenderDetail listed one copy as "...Operateand Maintain...".
    official = rec(
        "B1", "Bihar e-Procurement", desc="Design, Build, Operate and Maintain EV charging stations"
    )
    typo = rec("T1", "TenderDetail", desc="Design, Build, Operateand Maintain EV charging stations")
    kept, _ = dedupe_records([typo, official], SOURCES)
    assert [r["id"] for r in kept] == ["B1"]


def test_a_short_cut_fragment_is_not_trusted():
    official = rec("B1", "Bihar e-Procurement", desc="Supply of EV chargers for depots in Patna division")
    cut = rec("T1", "TenderDetail", desc="...Supply of EV chargers...")
    kept, _ = dedupe_records([official, cut], SOURCES)
    assert len(kept) == 2


# --- During a run (scrape_source) ----------------------------------------------


@pytest.fixture
def run_rows(monkeypatch):
    """run_rows(source, rows, saved) -> (existing_by_id, new_records)."""

    def run(source, rows, saved):
        monkeypatch.setitem(fetchers.TYPE_FETCHERS, source["type"], lambda s, session: rows)
        existing_by_id = {r["id"]: r for r in saved}
        new_records = []
        index = DuplicateIndex(saved, SOURCES)
        scrape_source(source, None, existing_by_id, new_records, index)
        return existing_by_id, new_records

    return run


ROW = {"raw_title": "Empanelment of agencies for EV charging stations", "raw_row": "due 2026-09-28"}


def test_aggregator_copy_of_a_saved_official_tender_is_not_new(run_rows):
    source = {
        "name": "TenderDetail",
        "type": "tenderdetail_list",
        "url": "https://td.test",
        "maxNewPerRun": 1,
    }
    saved = [rec("B1", "Bihar e-Procurement")]
    other = {"raw_title": "Supply of EV chargers", "raw_row": "due 2026-10-01"}
    existing, new = run_rows(source, [{**ROW, "stableKey": "td-1", "value": "₹1 Cr"}, other], saved)
    # Saved: the official copy plus the one genuinely new tender; no TenderDetail copy of it.
    assert sorted(r["desc"] for r in existing.values()) == [ROW["raw_title"], "Supply of EV chargers"]
    assert existing["B1"]["source"] == "Bihar e-Procurement"
    assert [r["desc"] for r in new] == ["Supply of EV chargers"]  # the duplicate didn't use up the 1 slot
    assert existing["B1"]["value"] == "₹1 Cr"


def test_official_copy_replaces_a_saved_aggregator_copy(run_rows):
    source = {"name": "Bihar e-Procurement", "type": "js_interactive_search", "url": "https://bihar.test"}
    saved = [rec("T1", "TenderDetail", linkType="direct")]
    existing, new = run_rows(source, [ROW], saved)
    assert "T1" not in existing
    assert [r["source"] for r in existing.values()] == ["Bihar e-Procurement"]
    assert new == []  # the tender itself isn't new, so it isn't emailed as new
