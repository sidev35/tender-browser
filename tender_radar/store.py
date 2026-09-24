"""
Reading and writing docs/data/tenders.json, the file the dashboard reads.
"""

import json
import logging
import os
from collections.abc import Iterable
from datetime import datetime

from .models import Record, Source

log = logging.getLogger(__name__)


def load_existing(path: str) -> list[Record]:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning(f"  [!] Could not read existing {path}, starting fresh.")
    return []


def backfill_link_types(
    records: Iterable[Record], sources: list[Source], direct_link_types: set[str]
) -> None:
    """Sets linkType on records saved before that field existed."""
    source_types = {s["name"]: s.get("type") for s in sources}
    for t in records:
        if "linkType" not in t:
            t["linkType"] = "direct" if source_types.get(t.get("source")) in direct_link_types else "search"


def drop_expired(records: Iterable[Record]) -> list[Record]:
    """
    Drops tenders whose due date has clearly passed, to keep the file from
    growing forever. Keeps anything with no parsed due date (safer to show
    than silently hide).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return [t for t in records if not t.get("dueDate") or t["dueDate"] >= today]


def save(path: str, records: list[Record]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
