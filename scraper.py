"""
EV Charging Tender Scraper — Free / Official Government Portals
==================================================================

WHAT THIS DOES
--------------
Pulls the public "Latest Tenders" listings from portals that run on the
NIC "GePNIC" e-procurement engine (the same underlying system used by
CPPP/etenders.gov.in, most state e-procurement portals, and the Oil
Marketing Companies' e-tendering sites), filters them against your
EV-charging category keywords, and merges any new matches into
docs/data/tenders.json — the file the Tender Radar dashboard reads.

This is designed to run automatically via GitHub Actions
(.github/workflows/update-tenders.yml) on a schedule, with GitHub Pages
serving docs/index.html + docs/data/tenders.json as a live site. See
README.md for the one-time setup steps.

SOURCES
-------
Portals live in sources.json (repo root), not in this file — see that
file and README.md for how to add, remove, or disable one, and what
each field means. In short: a source only gets scraped if it's
"enabled": true AND its "type" has a registered parser in
TYPE_PARSERS below; paid aggregators and robots.txt-blocked portals
are listed there with types that deliberately have no parser, so they
can't start being scraped by accident.

RUNNING LOCALLY (optional, for testing)
----------------------------------------
    pip install requests beautifulsoup4 --break-system-packages
    python scraper.py

This updates docs/data/tenders.json in place. Open docs/index.html in a
browser via a local server (`python -m http.server` from the repo root,
then visit localhost:8000/docs/) to preview — opening the file directly
(file://) will not be able to fetch data/tenders.json due to browser
security rules around local files.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

from notify import send_digest

# Some Indian government sites (and some corporate/ISP networks with SSL
# inspection) present certificate chains that Python's default verifier
# rejects, even though the site is legitimate. We try a verified request
# first; only if that fails do we retry without verification, and we say
# so loudly rather than silently weakening security.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# 1. YOUR CATEGORY KEYWORDS
#    Edit these lists to tune what counts as a match. A tender matches a
#    category if ANY of its keywords appear in the tender title/description.
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "PPP / Concession / CPO Selection": [
        "dbfot", "boom model", "boot model", "ppp model", "public private partnership",
        "cpo selection", "selection of cpo", "charge point operator", "empanelment of agencies",
        "empanelment of cpo", "concession", "revenue share", "e-drive scheme",
        "public charging station", "public charging stations",
    ],
    "Charger Supply & Installation": [
        "dc fast charger", "dual gun", "ev charging station supply", "supply, installation",
        "supply and installation", "ev charging infrastructure", "ac ev charging",
        "solar powered ev charging", "kw charger", "commissioning of ev",
    ],
    "Infrastructure & Electrical Works": [
        "electrical infrastructure for ev", "power infrastructure for ev",
        "ht/lt infrastructure", "ht lt infrastructure", "ev bus charging",
        "car parking with ev charging", "retail outlet.*ev charging",
    ],
}

# A tender only needs to match ONE keyword from ANY category to be kept;
# it gets tagged with every category whose keywords it matches.
GENERIC_GATE_TERMS = ["ev charg", "electric vehicle charg", "charging station", "charging infrastructure"]


# ---------------------------------------------------------------------------
# 2. SOURCES
#    Loaded from sources.json (repo root) rather than hardcoded here, so you
#    can add/remove/disable a source without touching this file. See that
#    file's entries for the shape, and README.md for the full explanation of
#    each field (name/url/type/enabled/notes).
# ---------------------------------------------------------------------------

SOURCES_PATH = os.environ.get("TENDER_SOURCES_PATH", "sources.json")


def load_sources(path=None):
    path = path or SOURCES_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def fetch(url, timeout=20):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=True)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError:
        print(f"  [!] SSL verification failed for {url} — retrying without verification.")
        print("      This usually means your network (ISP/office firewall) is intercepting")
        print("      HTTPS traffic, or the government site's cert chain is misconfigured.")
        print("      Only do this if you trust the network you're on.")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp.text
        except Exception as e2:
            print(f"  [!] Still could not fetch {url}: {e2}")
            return None
    except Exception as e:
        print(f"  [!] Could not fetch {url}: {e}")
        return None


def parse_gepnic_table(html, source_name, base_url):
    """
    Parses the 'Latest Tenders' table found on NIC GePNIC-based portals.
    Structure: a table with columns like
    [S.No, Tender Title, Reference No, Closing Date, Bid Opening Date]
    This is intentionally forgiving — GePNIC installs differ slightly by
    department, so we scan all tables and pick rows that look like tenders.

    Also grabs the row's link (usually wrapping the title), if any. NOTE:
    GePNIC "DirectLink" URLs are session-scoped
    (?...&session=T&sp=<token>) — they may stop working once the scraper's
    session ends, so this is a best-effort deep link, not a guaranteed one.
    Callers should always have a working fallback (the portal's own listing
    page) for when it goes stale.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    # NIC GePNIC homepages render the real "latest tenders" widget as
    # <table id="activeTenders">, surrounded by dozens of unrelated layout
    # tables (nav/menus/banners). Scanning every table on the page — as this
    # used to do — picks up that surrounding chrome as bogus "tender rows"
    # (e.g. "Screen Reader Access 17-Sep-2026 Search | Active Tenders...").
    # Prefer the real table by id; only fall back to scanning everything for
    # a portal layout we don't recognize (parse_generic_table's use case).
    tables = [soup.find(id="activeTenders")] if soup.find(id="activeTenders") else soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            row_text = " | ".join(cells)
            # Heuristic: a tender row usually has a date-like string in it
            if re.search(r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", row_text):
                title = max(cells, key=len)  # longest cell is usually the title
                link = row.find("a", href=True)
                direct_url = urljoin(base_url, link["href"]) if link else None
                results.append({
                    "raw_title": title,
                    "raw_row": row_text,
                    "source": source_name,
                    "direct_url": direct_url,
                })
    return results


def parse_generic_table(html, source_name, base_url):
    """Fallback parser: same idea as GePNIC but looser, for other portal layouts."""
    return parse_gepnic_table(html, source_name, base_url)


# Maps a source's "type" (from sources.json) to the parser that knows how to
# read it. A type with no entry here (e.g. "blocked_by_robots_txt",
# "paid_aggregator", "unsupported") is deliberately unscrapable — this is a
# safety net so a source can't start being scraped just by someone flipping
# "enabled": true in sources.json; actually supporting a new source type
# requires adding a parser function and registering it here.
TYPE_PARSERS = {
    "gepnic_table": parse_gepnic_table,
    "generic_table": parse_generic_table,
}


def make_stable_id(source_name, title):
    """
    Government listings rarely give us a clean, guaranteed-unique reference
    number in a consistent spot, so we derive a stable id from the source +
    title text. Same tender text on a later run -> same id -> no duplicate
    added to the persistent data file. If the source text changes slightly
    between runs (e.g. a corrigendum edits the title), it will show up as a
    "new" entry — reviewing occasional near-duplicates by eye is a fair
    trade-off for not needing fragile per-portal reference-number parsing.
    """
    h = hashlib.sha1(f"{source_name}::{title}".encode("utf-8")).hexdigest()[:10]
    return f"AUTO-{h}"


def extract_due_date(row_text):
    """Best-effort extraction of a closing/due date from a raw table row."""
    m = re.search(r"(\d{1,2})[-/]([A-Za-z]{3})[-/](\d{2,4})", row_text)
    if m:
        day, mon, year = m.groups()
        year = ("20" + year) if len(year) == 2 else year
        try:
            return datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", row_text)
    if m:
        day, mon, year = m.groups()
        year = ("20" + year) if len(year) == 2 else year
        try:
            return datetime.strptime(f"{day}-{mon}-{year}", "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def matches_categories(title):
    title_l = title.lower()
    if not any(term in title_l for term in GENERIC_GATE_TERMS):
        return []
    matched = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, title_l):
                matched.append(category)
                break
    return matched


DATA_PATH = os.environ.get("TENDER_DATA_PATH", "docs/data/tenders.json")
DUE_SOON_DAYS = int(os.environ.get("DUE_SOON_DAYS", "7"))


def days_until(date_str):
    if not date_str:
        return None
    try:
        due = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return (due.date() - datetime.now().date()).days


def load_existing(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print(f"  [!] Could not read existing {path}, starting fresh.")
    return []


def run():
    existing = load_existing(DATA_PATH)
    existing_by_id = {t["id"]: t for t in existing if t.get("id")}
    new_count = 0
    new_records = []

    for source in load_sources():
        if not source.get("enabled"):
            continue
        parser = TYPE_PARSERS.get(source.get("type"))
        if not parser:
            print(f"Skipping {source['name']}: type '{source.get('type')}' isn't set up for "
                  f"automated scraping ({source.get('notes', 'no notes')}).")
            continue
        if not source.get("url"):
            print(f"Skipping {source['name']}: no URL configured in sources.json yet.")
            continue

        print(f"Checking {source['name']} ...")
        html = fetch(source["url"])
        if not html:
            continue
        rows = parser(html, source["name"], source["url"])

        matched_here = 0
        for row in rows:
            cats = matches_categories(row["raw_title"])
            if not cats:
                continue
            tid = make_stable_id(source["name"], row["raw_title"])
            if tid in existing_by_id:
                continue  # already tracked from a previous run
            record = {
                "id": tid,
                "desc": row["raw_title"],
                "location": None,
                "value": None,
                "dueDate": extract_due_date(row["raw_row"]),
                "category": cats[0],
                "source": source["name"],
                # Best-effort deep link into the specific tender; falls back to
                # the portal's own listing page (always works) if we couldn't
                # find one, or once the deep link's session token goes stale.
                "url": row["direct_url"] or source["url"],
                "firstSeen": datetime.now().strftime("%Y-%m-%d"),
            }
            existing_by_id[tid] = record
            new_records.append(record)
            matched_here += 1
            new_count += 1

        print(f"  -> {len(rows)} rows scanned, {matched_here} new match(es)")
        if rows and matched_here == 0:
            print("     (0 new matches can be normal — either nothing new mentions EV")
            print("      charging, or today's matches were already captured before.")
            print("      Sample of what was actually scanned:)")
            for r in rows[:3]:
                print(f"       - {r['raw_title'][:90]}")
        time.sleep(1)  # be polite between requests

    # Drop tenders whose due date has clearly passed, to keep the file from
    # growing forever. Keep anything with no parsed due date (safer to show
    # than silently hide).
    today = datetime.now().strftime("%Y-%m-%d")
    merged = [t for t in existing_by_id.values() if not t.get("dueDate") or t["dueDate"] >= today]

    os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {new_count} new match(es) this run. {len(merged)} total tenders now in {DATA_PATH}.")
    print(f"Run at: {datetime.now().isoformat()}")

    # Email digest: "new" tenders only ever appear in the run they were first
    # matched; "closing soon" tenders are re-included in every digest until
    # they pass, by design (see README) — so this will email on every run
    # for as long as at least one tender sits inside the closing-soon window.
    merged_ids = {t["id"] for t in merged}
    new_records = [r for r in new_records if r["id"] in merged_ids]
    due_soon_records = [
        t for t in merged
        if (d := days_until(t.get("dueDate"))) is not None and 0 <= d <= DUE_SOON_DAYS
    ]
    try:
        send_digest(new_records, due_soon_records)
    except Exception as e:
        print(f"  [!] Email digest failed (continuing without it): {e}")


if __name__ == "__main__":
    run()
