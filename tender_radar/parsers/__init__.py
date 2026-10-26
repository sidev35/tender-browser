"""
Parsers: each takes a page's HTML and returns a list of "rows", one per
tender, as plain dicts. They never load pages themselves (that's fetchers.py),
which is what lets tests run them on saved HTML in tests/fixtures/.

Row fields (only raw_title and raw_row are always present):
    raw_title    the tender's title text, as found
    raw_row      all of the row's text, for date/value extraction
    source       the source's name
    refNo        the issuing authority's reference number, if found
    dueDateHint  the text of the closing-date cell, if the parser found one
    docUrl       a stable link to this exact tender, if the page has one
    stableKey    a unique id from the source, when titles aren't unique
    value, location   already-formatted fields, when the page has them
    organisation      the issuing organisation, when the page names it

Layout (one folder per country, one module per portal or site):
    australia/    victoria.py (also Tenders ACT), tasmania.py
    india/        gepnic_org.py, tables.py, eesl.py
        aggregators/   tenderdetail.py, tender18.py, nationaltenders.py
    common.py     small pieces shared between countries

Adding a country: make a folder with its parsers and an __init__.py that exports
them, then import the folder's names below.
"""

from .australia import parse_tas_tenders, parse_vic_tenders
from .india import (
    is_captcha_page,
    parse_eesl_tenders,
    parse_generic_table,
    parse_gepnic_org_list,
    parse_gepnic_org_tenders,
    parse_gepnic_table,
    parse_nationaltenders_list,
    parse_tender18_list,
    parse_tenderdetail_list,
)

__all__ = [
    "is_captcha_page",
    "parse_eesl_tenders",
    "parse_generic_table",
    "parse_gepnic_org_list",
    "parse_gepnic_org_tenders",
    "parse_gepnic_table",
    "parse_nationaltenders_list",
    "parse_tas_tenders",
    "parse_tender18_list",
    "parse_tenderdetail_list",
    "parse_vic_tenders",
]
