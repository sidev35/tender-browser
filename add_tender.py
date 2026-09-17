"""
Add a single tender to docs/data/tenders.json by hand — for a tender you
found by manually searching a portal (see README's "Manually checking a
portal yourself" section) that the automated scraper's free "latest 10"
view didn't happen to catch.

Not meant to be run standalone day-to-day: it's driven by the "Add tender
manually" GitHub Action (repo Actions tab -> that workflow -> Run workflow),
which passes the form fields in as the env vars read below and commits the
result. Reuses scraper.py's id/dedup logic so a manually-added tender and a
later auto-scraped one for the same thing don't end up duplicated.
"""

import json
import os
from datetime import datetime

from scraper import DATA_PATH, load_existing, make_stable_id


def run():
    desc = os.environ.get("TENDER_DESC", "").strip()
    if not desc:
        raise SystemExit("Description is required.")
    category = os.environ.get("TENDER_CATEGORY", "").strip()
    if not category:
        raise SystemExit("Category is required.")

    location = os.environ.get("TENDER_LOCATION", "").strip() or None
    value = os.environ.get("TENDER_VALUE", "").strip() or None
    due_date = os.environ.get("TENDER_DUE_DATE", "").strip() or None
    source = os.environ.get("TENDER_SOURCE", "").strip() or "Manually added"
    url = os.environ.get("TENDER_URL", "").strip() or None

    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            raise SystemExit(f"Due date '{due_date}' must be in YYYY-MM-DD format.")

    existing = load_existing(DATA_PATH)
    tid = make_stable_id(source, desc)
    if any(t.get("id") == tid for t in existing):
        print(f"Already tracked as {tid} — skipping duplicate, nothing to do.")
        return

    record = {
        "id": tid,
        "desc": desc,
        "location": location,
        "value": value,
        "dueDate": due_date,
        "category": category,
        "source": source,
        "url": url,
        "firstSeen": datetime.now().strftime("%Y-%m-%d"),
    }
    existing.append(record)

    os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"Added {tid}: {desc[:80]}")


if __name__ == "__main__":
    run()
