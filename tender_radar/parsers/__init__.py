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
"""

from .eesl import parse_eesl_tenders
from .gepnic_org import is_captcha_page, parse_gepnic_org_list, parse_gepnic_org_tenders
from .tables import parse_generic_table, parse_gepnic_table
from .tenderdetail import parse_tenderdetail_list

__all__ = [
    "is_captcha_page",
    "parse_eesl_tenders",
    "parse_generic_table",
    "parse_gepnic_org_list",
    "parse_gepnic_org_tenders",
    "parse_gepnic_table",
    "parse_tenderdetail_list",
]
