"""
The one definition of a saved tender record: what docs/data/tenders.json holds
and the dashboard (docs/js/) reads. DATA_FORMAT.md describes the same fields
in plain language; keep the two in step.

Field names are camelCase on purpose: they are the JSON keys the dashboard
uses, so the Python attribute and the stored key are always the same word.
"""

from dataclasses import asdict, dataclass, fields
from typing import Any, Literal

LinkType = Literal["direct", "search"]

# The plain dicts that flow through a run, named for type hints:
Source = dict[str, Any]  # one sources.json entry
Row = dict[str, Any]  # one tender as a parser found it (see parsers/__init__.py)
Record = dict[str, Any]  # one saved tender, as in tenders.json (Tender.to_dict())


@dataclass
class Tender:
    id: str  # stable fingerprint, "AUTO-<10 hex chars>" (normalize.make_stable_id)
    desc: str  # the tender's title, cleaned
    category: str  # first matching category from config/categories.json
    source: str  # sources.json "name" it came from
    url: str  # where the dashboard's button goes
    linkType: LinkType  # "direct": url is this exact tender; "search": url is the portal's search page
    firstSeen: str  # "yyyy-mm-dd" of the run that first found it
    dueDate: str | None = None  # closing date "yyyy-mm-dd", if the page showed one
    value: str | None = None  # formatted amount, e.g. "₹2.55 Cr", if disclosed
    refNo: str | None = None  # issuing authority's reference number, if found
    location: str | None = None  # state/city, if the page showed one

    def to_dict(self) -> Record:
        """The record as stored in tenders.json (same key order as before)."""
        d = asdict(self)
        return {key: d[key] for key in STORED_KEY_ORDER}


FIELD_NAMES = [f.name for f in fields(Tender)]

# Order keys are written in, kept from before this dataclass existed so the
# data file's diffs stay readable.
STORED_KEY_ORDER = [
    "id",
    "desc",
    "refNo",
    "location",
    "value",
    "dueDate",
    "category",
    "source",
    "url",
    "linkType",
    "firstSeen",
]
assert sorted(STORED_KEY_ORDER) == sorted(FIELD_NAMES)
