"""
Tender Radar: finds EV-charging tenders on government and aggregator portals
and saves them to docs/data/tenders.json, the file the dashboard reads.

Start with ARCHITECTURE.md (repo root) for the plain-language picture.
Module map, in the order a run uses them:

    config.py     settings from environment variables
    sources.py    load and check sources.json (which portals to check, and how)
    browser.py    the shared headless browser every page is loaded through
    fetchers.py   one fetcher per source "type": load page(s) -> parser
    parsers/      HTML -> rows (tables.py, eesl.py, tenderdetail.py)
    normalize.py  row text -> clean fields (id, title, due date, value)
    matching.py   is it an EV-charging tender, and which category?
                  (word lists in config/categories.json)
    models.py     Tender: the saved record's fields (see DATA_FORMAT.md)
    store.py      read/write tenders.json, drop expired tenders
    notify.py     optional email digest (SendGrid)
    pipeline.py   run(): ties the steps above together
"""

from .pipeline import run

__all__ = ["run"]
