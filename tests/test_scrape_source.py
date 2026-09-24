"""scrape_source(): turning fetched rows into stored records, with a fake
fetcher instead of a browser."""

import json
import os

import pytest

from tender_radar import fetchers
from tender_radar.models import STORED_KEY_ORDER
from tender_radar.pipeline import scrape_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ev_row(n, **extra):
    return {
        "raw_title": f"EV charging station supply lot {n}",
        "raw_row": f"lot {n} | 05-Oct-2026",
        "refNo": None,
        **extra,
    }


@pytest.fixture
def run_source(monkeypatch):
    """run_source(rows, **source_fields) -> (existing_by_id, new_records)."""

    def run(rows, existing=None, **fields):
        monkeypatch.setitem(fetchers.TYPE_FETCHERS, "fake", lambda source, session: rows)
        src = {"name": "Fake portal", "url": "https://example.test/search", "type": "fake", **fields}
        existing_by_id = dict(existing or {})
        new_records = []
        scrape_source(src, session=None, existing_by_id=existing_by_id, new_records=new_records)
        return existing_by_id, new_records

    return run


def test_new_record_fields(run_source):
    _, new = run_source([ev_row(1)])
    (rec,) = new
    assert rec["desc"] == "EV charging station supply lot 1"
    assert rec["dueDate"] == "2026-10-05"
    assert rec["category"] == "Charger Supply & Installation"
    assert rec["source"] == "Fake portal"
    assert rec["url"] == "https://example.test/search"
    assert rec["linkType"] == "search"


def test_new_record_has_exactly_the_documented_fields(run_source):
    # models.Tender (and DATA_FORMAT.md) is the one definition of a record.
    _, new = run_source([ev_row(1)])
    assert list(new[0]) == STORED_KEY_ORDER


def test_saved_data_file_matches_the_record_format():
    # Every record already in docs/data/tenders.json has the documented fields.
    with open(os.path.join(ROOT, "docs", "data", "tenders.json"), encoding="utf-8") as f:
        records = json.load(f)
    for rec in records:
        assert set(rec) == set(STORED_KEY_ORDER), rec.get("id")
        assert rec["linkType"] in ("direct", "search")


def test_doc_url_makes_a_direct_link(run_source):
    _, new = run_source([ev_row(1, docUrl="https://example.test/tender/1.pdf")])
    assert new[0]["url"] == "https://example.test/tender/1.pdf"
    assert new[0]["linkType"] == "direct"


def test_non_ev_rows_are_skipped(run_source):
    _, new = run_source([{"raw_title": "Housekeeping contract", "raw_row": "05-Oct-2026"}])
    assert new == []


def test_max_new_per_run_defers_the_rest(run_source):
    rows = [ev_row(n) for n in range(25)]
    existing, first = run_source(rows, maxNewPerRun=10)
    assert len(first) == 10
    # Next run: the 10 already stored are skipped, the next 10 are added.
    _, second = run_source(rows, existing=existing, maxNewPerRun=10)
    assert len(second) == 10
    assert not {r["id"] for r in first} & {r["id"] for r in second}


def test_already_tracked_tender_is_refreshed_not_duplicated(run_source):
    existing, first = run_source([ev_row(1)])
    tid = first[0]["id"]
    # Same raw title (same id), but the source now has a title/value regex.
    existing, again = run_source(
        [ev_row(1)], existing=existing, titleRegex=r"(EV charging station supply)", valueRegex=r"lot (\d+)"
    )
    assert again == []
    assert existing[tid]["desc"] == "EV charging station supply"
    assert existing[tid]["value"] == "₹1"


def test_stable_key_overrides_title_for_the_id(run_source):
    # Two different tenders with the same title stay separate.
    rows = [ev_row(1, stableKey="td-1"), ev_row(1, stableKey="td-2")]
    _, new = run_source(rows)
    assert len({r["id"] for r in new}) == 2
