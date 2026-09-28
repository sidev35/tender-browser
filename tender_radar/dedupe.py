"""
Spotting the same tender listed by more than one source (e.g. Bihar's own
portal and TenderDetail both list Bihar's EV empanelment tender), so the
dashboard shows it once. Each source gives a tender its own id, so duplicates
are found by content instead:

  - titles equal after normalising (case, punctuation, a leading "..."), and
    closing dates equal, or missing on one side; or, for a title an
    aggregator cut short with "...", its complete words (at least 6) found
    inside the other title, with the same closing date; and
  - the two come from different sources, or both from an aggregator (which
    sometimes lists one tender twice). Two tenders from the same official
    portal are never merged: each has its own id there.

The official portal's copy is kept over an aggregator's (a type in
AGGREGATOR_TYPES), and fields it lacks (value, closing date, location, ref
no) are filled in from the copy that's dropped. Between two copies of the
same kind, the one saved first is kept.
"""

import re
from collections.abc import Iterable

from .models import Record, Source

# Source types that re-list other portals' tenders; see fetchers.TYPE_FETCHERS.
AGGREGATOR_TYPES = {"tenderdetail_list"}

# Filled in on the kept copy from the dropped one, when the kept copy lacks them.
FILLABLE_FIELDS = ("dueDate", "value", "location", "refNo")


def normalised_title(title: str) -> str:
    """ "...Supply Of EV Chargers, Lot-1" -> "supply of ev chargers lot 1" """
    text = re.sub(r"[^0-9a-z]+", " ", title.lower())
    return " ".join(text.split())


def _key(title: str) -> str:
    """normalised_title without spaces, so a missing space ("Operateand
    Maintain", seen on TenderDetail) still matches."""
    return normalised_title(title).replace(" ", "")


def _due_dates_agree(a: Record, b: Record) -> bool:
    return not a.get("dueDate") or not b.get("dueDate") or a["dueDate"] == b["dueDate"]


# A cut-off title fragment must be at least this long to be matched inside
# another title, so short generic phrases never cause a merge.
MIN_FRAGMENT_WORDS = 6


def _fragment(title: str) -> str | None:
    """
    For a title an aggregator cut short ("...Selection Of Charge Point
    Operator ... PM E-Drive Scheme On..."), its longest complete stretch of
    words: the words next to each "..." may be cut in half, so they're dropped.
    None if the title isn't cut, or what's left is too short to trust.
    """
    if "..." not in title and "…" not in title:
        return None
    pieces = re.split(r"\.\.\.+|…", title)
    words = max((normalised_title(p).split() for p in pieces), key=len)
    if pieces[0].strip() == "" or title.lstrip().startswith(("...", "…")):
        words = words[1:]
    if title.rstrip().endswith(("...", "…")):
        words = words[:-1]
    return "".join(words) if len(words) >= MIN_FRAGMENT_WORDS else None


class DuplicateIndex:
    """Finds, among saved records, one that is the same tender as a new one."""

    def __init__(self, records: Iterable[Record], sources: list[Source]):
        self._types = {s["name"]: s.get("type") for s in sources}
        self._by_title: dict[str, list[Record]] = {}
        for r in records:
            self.add(r)

    def is_aggregator(self, record: Record) -> bool:
        return self._types.get(record.get("source")) in AGGREGATOR_TYPES

    def add(self, record: Record) -> None:
        self._by_title.setdefault(_key(record["desc"]), []).append(record)

    def remove(self, record: Record) -> None:
        bucket = self._by_title.get(_key(record["desc"]), [])
        if record in bucket:
            bucket.remove(record)

    def _may_merge(self, record: Record, other: Record) -> bool:
        if other is record or other["id"] == record["id"]:
            return False
        return other.get("source") != record.get("source") or self.is_aggregator(record)

    def find(self, record: Record) -> Record | None:
        for other in self._by_title.get(_key(record["desc"]), []):
            if self._may_merge(record, other) and _due_dates_agree(record, other):
                return other
        # A title cut short by an aggregator: match its complete words inside
        # the other title, but only with the same (known) closing date.
        mine = _fragment(record["desc"])
        for bucket_title, others in self._by_title.items():
            for other in others:
                if not self._may_merge(record, other):
                    continue
                if not record.get("dueDate") or record.get("dueDate") != other.get("dueDate"):
                    continue
                theirs = _fragment(other["desc"])
                if (mine and mine in bucket_title) or (theirs and theirs in _key(record["desc"])):
                    return other
        return None

    def prefer(self, a: Record, b: Record) -> tuple[Record, Record]:
        """(kept, dropped): official over aggregator, else the one saved first."""
        if self.is_aggregator(a) != self.is_aggregator(b):
            return (b, a) if self.is_aggregator(a) else (a, b)
        return (a, b) if (a.get("firstSeen") or "") <= (b.get("firstSeen") or "") else (b, a)


def fill_missing(kept: Record, dropped: Record) -> None:
    for key in FILLABLE_FIELDS:
        if not kept.get(key) and dropped.get(key):
            kept[key] = dropped[key]
    # It has been tracked since whichever copy was found first.
    if dropped.get("firstSeen") and dropped["firstSeen"] < (kept.get("firstSeen") or "9999"):
        kept["firstSeen"] = dropped["firstSeen"]


def dedupe_records(records: Iterable[Record], sources: list[Source]) -> tuple[list[Record], list[Record]]:
    """Collapses duplicates among saved records. Returns (kept, dropped)."""
    index = DuplicateIndex([], sources)
    kept: list[Record] = []
    dropped: list[Record] = []
    for rec in records:
        other = index.find(rec)
        if other is None:
            index.add(rec)
            kept.append(rec)
            continue
        keep, drop = index.prefer(other, rec)
        fill_missing(keep, drop)
        if keep is rec:  # the new one wins: swap it in for the saved one
            index.remove(other)
            kept[kept.index(other)] = rec
            index.add(rec)
        dropped.append(drop)
    return kept, dropped
