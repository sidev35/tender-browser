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

WHY ONLY THESE SOURCES FOR NOW
-------------------------------
- GeM (bidplus.gem.gov.in) and CESL's e-procurement portal
  (cesl.eproc.in) both disallow automated access via robots.txt.
  Don't scrape these — use their aggregator/keyword-alert features
  instead (TenderDetail, TendersOnTime, etc., which you already pay for).
- NHAI doesn't run a separate stable listing URL; its tenders flow
  through CPPP/etenders.gov.in (already covered) and GeM.
- State portals and Smart City SPVs vary site-by-site; add them to
  SOURCES below once you confirm each one's listing URL.

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
#    Each source is a GePNIC-style "Latest Tenders" listing page that is
#    fetchable without login. Add more state/PSU portals here once verified.
# ---------------------------------------------------------------------------

SOURCES = [
    {
        "name": "IOCL e-Tendering",
        "url": "https://iocletenders.nic.in/nicgep/app",
        "type": "gepnic_table",
    },
    {
        "name": "CPPP / etenders.gov.in",
        "url": "https://etenders.gov.in/eprocure/app",
        "type": "gepnic_table",
    },
    # NHAI deliberately left out: it doesn't run its own separate GePNIC
    # listing at a stable public URL — its tenders are published through
    # CPPP/etenders.gov.in (already covered above) and GeM (blocked, see
    # note at top of file). If you find a dedicated NHAI e-tendering URL,
    # add it here following the pattern below.
    #
    # Example of how to add a state portal once you've confirmed its
    # listing URL:
    # {
    #     "name": "Maharashtra e-Tendering (mahatenders.gov.in)",
    #     "url": "https://mahatenders.gov.in/nicgep/app",
    #     "type": "gepnic_table",
    # },
]

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


def parse_gepnic_table(html, source_name):
    """
    Parses the 'Latest Tenders' table found on NIC GePNIC-based portals.
    Structure: a table with columns like
    [S.No, Tender Title, Reference No, Closing Date, Bid Opening Date]
    This is intentionally forgiving — GePNIC installs differ slightly by
    department, so we scan all tables and pick rows that look like tenders.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            row_text = " | ".join(cells)
            # Heuristic: a tender row usually has a date-like string in it
            if re.search(r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", row_text):
                title = max(cells, key=len)  # longest cell is usually the title
                results.append({
                    "raw_title": title,
                    "raw_row": row_text,
                    "source": source_name,
                })
    return results


def parse_generic_table(html, source_name):
    """Fallback parser: same idea as GePNIC but looser, for other portal layouts."""
    return parse_gepnic_table(html, source_name)


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

    for source in SOURCES:
        print(f"Checking {source['name']} ...")
        html = fetch(source["url"])
        if not html:
            continue
        parser = parse_gepnic_table if source["type"] == "gepnic_table" else parse_generic_table
        rows = parser(html, source["name"])

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
