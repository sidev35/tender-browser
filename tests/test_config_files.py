"""The two files people edit by hand, sources.json and config/categories.json,
are checked when the scraper starts. These tests keep the real files valid and
make sure common mistakes produce a clear message."""

import json
import os

import pytest

from tender_radar.matching import CategoriesError, load_categories
from tender_radar.sources import SourcesError, load_sources, validate_sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- The real files --------------------------------------------------------


def test_real_sources_json_is_valid():
    assert validate_sources(json.load(open(os.path.join(ROOT, "sources.json"), encoding="utf-8"))) == []


def test_real_categories_json_is_valid():
    gate, cats, fallback = load_categories(os.path.join(ROOT, "config", "categories.json"))
    assert "charging station" in gate
    assert list(cats)[0] == "PPP / Concession / CPO Selection"  # order decides a record's category
    assert fallback == "Other EV Charging"


# --- sources.json mistakes ---------------------------------------------------


def good_source(**overrides):
    src = {"name": "Portal", "url": "https://example.test/", "type": "gepnic_table", "enabled": True}
    src.update(overrides)
    return src


def test_a_good_source_has_no_problems():
    assert validate_sources([good_source()]) == []


@pytest.mark.parametrize(
    "source, expected",
    [
        (good_source(enable=True), 'unknown field "enable"'),
        (good_source(type="gepnic_tabel"), 'unknown type "gepnic_tabel"'),
        (good_source(enabled="yes"), '"enabled" must be true or false'),
        (good_source(url=None), 'needs a "url"'),
        (good_source(url="example.test"), "must start with http"),
        (good_source(type="js_interactive_search"), 'needs "searchInputSelector"'),
        (good_source(titleRegex="Name Of Work"), "needs a (...) group"),
        (good_source(valueRegex="(unclosed"), "not a valid pattern"),
        (good_source(maxNewPerRun=0), '"maxNewPerRun" must be a whole number'),
    ],
)
def test_common_mistakes_are_explained(source, expected):
    problems = validate_sources([source])
    assert any(expected in p for p in problems), problems


def test_disabled_or_not_scraped_sources_may_have_no_url():
    assert validate_sources([good_source(url=None, enabled=False)]) == []
    assert validate_sources([good_source(url=None, type="paid_aggregator")]) == []


def test_duplicate_names_are_rejected():
    problems = validate_sources([good_source(), good_source()])
    assert any("already has this name" in p for p in problems)


def test_load_sources_lists_every_problem(tmp_path):
    path = tmp_path / "sources.json"
    two_bad = [good_source(enable=True), good_source(name="B", type="nope")]
    path.write_text(json.dumps(two_bad), encoding="utf-8")
    with pytest.raises(SourcesError) as err:
        load_sources(str(path))
    assert "2 problem(s)" in str(err.value)


def test_file_saved_by_notepad_with_a_bom_still_loads(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([good_source()]), encoding="utf-8-sig")
    assert load_sources(str(path))[0]["name"] == "Portal"


def test_broken_json_says_where(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('[\n  {"name": "A"\n  "type": "x"}\n]', encoding="utf-8")  # missing comma
    with pytest.raises(SourcesError) as err:
        load_sources(str(path))
    assert "line 3" in str(err.value)


# --- categories.json mistakes ------------------------------------------------


def write_categories(tmp_path, **doc):
    base = {"evGateTerms": ["ev charg"], "fallbackCategory": "Other", "categories": {"A": ["ev charger"]}}
    base.update(doc)
    path = tmp_path / "categories.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    "doc, expected",
    [
        ({"evGateTerms": []}, '"evGateTerms" must be a non-empty list'),
        ({"categories": {"A": []}}, 'category "A" needs a non-empty list'),
        ({"categories": {"A": ["retail outlet.*(ev"]}}, "is not a valid pattern"),
        ({"fallbackCategory": ""}, '"fallbackCategory" must be a category name'),
    ],
)
def test_categories_mistakes_are_explained(tmp_path, doc, expected):
    with pytest.raises(CategoriesError) as err:
        load_categories(write_categories(tmp_path, **doc))
    assert expected in str(err.value)
