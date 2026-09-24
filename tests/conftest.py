"""Shared test helpers. Tests never touch the network: parsers run on saved
HTML in tests/fixtures/ (refresh those with tests/capture_fixture.py)."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

from tender_radar.sources import load_sources  # noqa: E402


@pytest.fixture
def fixture_html():
    """fixture_html("gujarat_nprocure") -> that fixture file's HTML."""

    def load(name):
        with open(os.path.join(FIXTURES_DIR, f"{name}.html"), encoding="utf-8") as f:
            return f.read()

    return load


@pytest.fixture
def source():
    """source("Gujarat nProcure (keyword search)") -> that sources.json entry."""
    sources = {s["name"]: s for s in load_sources(os.path.join(ROOT, "sources.json"))}
    return lambda name: sources[name]
