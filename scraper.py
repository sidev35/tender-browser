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
"enabled": true AND its "type" has a registered fetcher in
TYPE_FETCHERS below; paid aggregators and robots.txt-blocked portals
are listed there with types that deliberately have no fetcher, so they
can't start being scraped by accident.

The only registered GePNIC fetcher is "gepnic_table": the free
homepage widget, 10 most-recently-posted tenders site-wide. A deeper,
paginated approach was tried and abandoned — see fetch_gepnic_homepage's
docstring for why (it self-triggers anti-bot captcha under real,
repeated automated use).

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

# Playwright is only needed for sources whose tender listing is rendered
# client-side via JavaScript (confirmed by manual check: a plain
# requests.get() on those pages returns just the page shell — a "Loading..."
# placeholder where the real table would be, no actual rows). It's an
# optional dependency: a checkout that only runs the plain-HTML GePNIC/EESL
# sources doesn't need it installed at all.
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def playwright_launch_kwargs():
    """
    Headless launch options for p.chromium.launch(). Defaults to driving the
    system's installed Microsoft Edge (channel "msedge"), because this
    machine's network blocks Playwright's own Chromium download
    (cdn.playwright.dev). Without that default, a plain `python scraper.py`
    tried the never-downloaded bundled Chromium and failed with Playwright's
    "please run `playwright install`" banner.
    Set PLAYWRIGHT_CHROMIUM_CHANNEL=chromium to use the bundled Chromium
    instead; the GitHub Actions workflow does this, since its runner
    installs that browser. Any other value is passed through as the channel
    (e.g. "chrome").
    """
    channel = (os.environ.get("PLAYWRIGHT_CHROMIUM_CHANNEL") or "msedge").strip()
    kwargs = {"headless": True}
    if channel.lower() != "chromium":
        kwargs["channel"] = channel
    return kwargs

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
        "dbfot", "boom model", "boot model", "boot basis", "boom basis", "ppp model",
        "ppp basis", "hybrid annuity", "public private partnership",
        "cpo selection", "selection of cpo", "selection of charge point operator",
        "charge point operator", "charge point operators", "empanelment of agencies",
        "empanelment of cpo", "empanelment of charge point operator", "concession",
        "revenue share", "e-drive scheme", "public charging station", "public charging stations",
    ],
    "Charger Supply & Installation": [
        "dc fast charger", "ac charger", "dual gun", "ev charger", "ev chargers",
        "ev charging station", "ev charging stations", "ev charging point",
        "ev charging points", "electric vehicle charger", "electric vehicle chargers",
        "electric vehicle charging station", "ev charging station supply",
        "supply, installation", "supply and installation", "ev charging infrastructure",
        "ac ev charging", "solar powered ev charging", "kw charger", "fast charging station",
        "charging point", "charging points", "evse", "commissioning of ev",
        "battery swapping", "battery swapping station", "battery swapping stations",
        "e-mobility", "pm e-drive", "pm e drive", "fame scheme",
    ],
    "Infrastructure & Electrical Works": [
        "electrical infrastructure for ev", "power infrastructure for ev",
        "ht/lt infrastructure", "ht lt infrastructure", "ev bus charging",
        "car parking with ev charging", "retail outlet.*ev charging",
        "ev charging bay", "ev charging yard", "ev parking",
    ],
}

# A tender only needs to match ONE keyword from ANY category to be kept;
# it gets tagged with every category whose keywords it matches.
GENERIC_GATE_TERMS = [
    "ev charg", "electric vehicle charg", "e-vehicle charg", "charging station",
    "charging infrastructure", "charging point", "ev station", "ev infrastructure", "evse",
    "battery swapping", "e-mobility", "pm e-drive", "pm e drive", "fame scheme",
]

# Category for a tender that passes GENERIC_GATE_TERMS but none of
# CATEGORY_KEYWORDS — see matches_categories().
FALLBACK_EV_CATEGORY = "Other EV Charging"


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


def parse_gepnic_table(html, source_name):
    """
    Parses the 'Latest Tenders' table found on NIC GePNIC-based portals.
    Structure: a table with columns like
    [S.No, Tender Title, Reference No, Closing Date, Bid Opening Date]
    This is intentionally forgiving — GePNIC installs differ slightly by
    department, so we scan all tables and pick rows that look like tenders.

    Does NOT try to capture the row's own "DirectLink" — confirmed live
    (2026-09-18) that these are tied to the scraper's own session and show
    "Stale Session" for literally anyone else who opens one, even seconds
    later. The dashboard instead links every matched tender to the
    portal's own search page (source["searchUrl"], set in scraper.py's
    caller) — stable, session-independent, and where a real visitor can
    search the tender's title themselves and solve the page's captcha.
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
    date_pattern = re.compile(r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}")
    # Stricter than date_pattern above: matches only when the WHOLE cell is a
    # date/timestamp (e.g. "21-Sep-2026 03:00 PM"), not just contains a
    # date-like substring anywhere. Needed because plenty of real reference
    # numbers embed a fiscal-year-style substring like "26-27" (e.g.
    # "PWD/Div8/ASW/2001/21/26-27/L1") that date_pattern.search() would
    # otherwise misfire on, wrongly excluding a genuine ref number from
    # candidacy below.
    full_date_cell_pattern = re.compile(
        r"^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}(\s+\d{1,2}:\d{2}\s*[AP]M)?$", re.IGNORECASE
    )
    # Match the id only on a <table>: Gujarat nProcure (js_interactive_search)
    # also has an element with id="activeTenders", but it's a <div> with no
    # rows, and matching it by bare id hid the real results table there —
    # confirmed 2026-09-23: 2 real matches rendered, 0 parsed.
    active_table = soup.find("table", id="activeTenders")
    tables = [active_table] if active_table else soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        # Best-effort: if this table has a real header row, find which
        # column is the actual closing/end date — so extract_due_date() can
        # be pointed at that ONE cell instead of guessing from the whole
        # row's text. Needed because a row can contain several date-shaped
        # strings (e.g. Telangana's rows have Published / Bid Start / Bid
        # Closing date-times, plus a reference number that itself embeds an
        # unrelated notice date) — scanning the flattened row text left-to-
        # right silently grabs the wrong one. Falls back to None (today's
        # existing whole-row-text behavior, unchanged) when no such header
        # is found, so portals without a recognizable header row — or
        # without this ambiguity in the first place — aren't affected.
        closing_col_idx = None
        if rows:
            header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
            for idx, h in enumerate(header_cells):
                h_l = h.lower()
                if "closing" in h_l or "end date" in h_l:
                    closing_col_idx = idx
                    break
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            row_text = " | ".join(cells)
            # Heuristic: a tender row usually has a date-like string in it
            if date_pattern.search(row_text):
                # The site's own table renders the title cell as "N. <actual
                # title>" (N = that row's position in ITS table, not a stable
                # tender property). Strip it for comparison purposes — but
                # compare every candidate cell *normalized* the same way, not
                # the raw cell against the already-stripped title, or the
                # still-prefixed title cell itself always looks "different"
                # from the stripped title and gets wrongly picked as the
                # reference number, before the loop ever reaches the real one.
                def strip_prefix(c):
                    return re.sub(r"^\s*\d+\.\s*", "", c).strip()

                title = strip_prefix(max(cells, key=len))  # longest cell is usually the title
                # Best-effort: the reference number is the remaining
                # short, non-date, non-title cell (e.g. "1/WKS/04/26-Gl" or a
                # numeric tender id) — gives users a second, more precise
                # value to paste into the portal's "Tender Ref No" search
                # field alongside the title. None if no such cell exists
                # (some portal layouts just don't have a distinct one).
                # Also skips cells that are PURELY digits: confirmed on
                # Bihar's js_interactive_search table that a plain S.No
                # column ("1", "2", ...) sits ahead of the real reference
                # number in cell order and would otherwise get picked
                # first — a genuine reference number almost always mixes
                # letters and digits (or at least isn't just a small row
                # index), so this is a safe general filter, not a
                # Bihar-specific hack.
                ref_no = next(
                    (c for c in cells
                     if strip_prefix(c).lower() != title.lower()
                     and c.strip()
                     and not full_date_cell_pattern.match(c.strip())
                     and not c.strip().isdigit()),
                    None,
                )
                if ref_no:
                    ref_no = strip_prefix(ref_no) or None
                due_date_hint = (
                    cells[closing_col_idx]
                    if closing_col_idx is not None and closing_col_idx < len(cells)
                    else None
                )
                results.append({
                    "raw_title": title,
                    "raw_row": row_text,
                    "source": source_name,
                    "refNo": ref_no,
                    "dueDateHint": due_date_hint,
                })
    return results


def parse_generic_table(html, source_name):
    """Fallback parser: same idea as GePNIC but looser, for other portal layouts."""
    return parse_gepnic_table(html, source_name)


def fetch_gepnic_homepage(source):
    """
    The free homepage "activeTenders" widget — the 10 most-recently-posted
    tenders site-wide. This is a single lightweight GET, confirmed stable
    under repeated real use.

    A much bigger paginated view exists (NIC GePNIC's "Tenders by Closing
    Date" report, filtered to a 7/14-day window) and looked promising —
    hundreds of tenders, no captcha, on first check. It was built and
    tested, then dropped: after the handful of automated requests that
    testing involved, every portal started demanding a captcha on that same
    endpoint that had been captcha-free minutes earlier. That's adaptive
    bot-detection kicking in from request *pattern* (a rapid paginated
    crawl), not a permanent block — but it means the deep-pagination
    approach is self-defeating for real, scheduled automation: run it
    for real (hundreds of requests, twice a day) and it would very likely
    wall itself off the same way. This project won't try to work around
    that (rotating IPs, spacing requests across hours to look less
    automated, etc.) — seeing this widget is the ceiling for automated,
    always-on coverage of these portals; see README for how to search the
    full listing yourself by hand instead.
    """
    html = fetch(source["url"])
    if not html:
        return []
    return parse_gepnic_table(html, source["name"])


def parse_eesl_tenders(html, source_name, base_url):
    """
    Parses eeslindia.org's "Tenders" page — a plain WordPress page, not a
    GePNIC portal. Every tender/notice the site has ever posted sits as its
    own <div class="current_latest_boxs ..."> on this single static page
    (confirmed live 2026-09-22: ~240 entries, oldest seen from 2021) — so
    unlike the GePNIC homepage widget, there's no rolling top-10 window for
    a match to rotate off of between scheduled checks.

    Two box shapes actually occur on the page:
      - title text directly in the box div, with its "Documents/Links" PDF
        link in a following SIBLING <div class="panel"> (not nested inside
        the box) — most entries.
      - no separate title: the box div directly wraps a single <a>, whose
        link text doubles as the title — seen on older/simpler notices.
    get_text() on the box div alone covers both shapes. The PDF link found
    is a genuine stable document URL (unlike GePNIC's session-bound
    DirectLink), so callers use it directly as the tender's url instead of
    falling back to source["searchUrl"].

    No structured closing/due date exists on this page for either shape —
    any date is inside the linked PDF itself, which this doesn't open.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for box in soup.find_all("div", class_="current_latest_boxs"):
        title = box.get_text(" ", strip=True)
        if not title:
            continue
        link = box.find("a", href=True)
        if not link:
            panel = box.find_next_sibling("div", class_="panel")
            if panel:
                link = panel.find("a", href=True)
        doc_url = urljoin(base_url, link["href"]) if link else None
        results.append({
            "raw_title": title,
            "raw_row": title,
            "source": source_name,
            "refNo": None,
            "docUrl": doc_url,
        })
    return results


def fetch_eesl_tenders(source):
    html = fetch(source["url"])
    if not html:
        return []
    return parse_eesl_tenders(html, source["name"], source["url"])


def parse_tenderdetail_list(html, source_name, base_url):
    """
    Parses a tenderdetail.com keyword listing page (e.g.
    /Indian-tender/charging-station-tenders) — a paid aggregator, but this
    listing is public with no login (confirmed live 2026-09-23; robots.txt
    allows all). Plain server-rendered HTML, no JS needed: each result is a
    <div class="tc tender-card"> (~50 on the page) with
      - a "#<number>" tag badge: TenderDetail's own tender id. Used as the
        stable id key (titles repeat across tenders here, e.g. several
        "Bids Are Invited For Procurement Of Charging Station ..."), but NOT
        as refNo — it's the aggregator's number, not the issuing authority's,
        so pasting it into an official portal's search would find nothing.
      - "Closes Mon DD, YYYY" closing date
      - a value like "₹ 26.09 Lakh", or "Ref. Document" when undisclosed
      - the state in .tc-state
      - a.tc-title linking to the tender's stable notice page, used as url.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("div.tender-card"):
        title_link = card.select_one("a.tc-title")
        if not title_link:
            continue
        title = title_link.get_text(" ", strip=True)
        td_id = next(
            (t.get_text(strip=True)[1:] for t in card.select(".tc-tags")
             if re.fullmatch(r"#\d+", t.get_text(strip=True))),
            None,
        )
        due_iso = None
        closes = card.select_one(".td-urgent")
        m = re.search(r"Closes\s+([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})",
                      closes.get_text(" ", strip=True) if closes else "")
        if m:
            try:
                due_iso = datetime.strptime(" ".join(m.groups()), "%b %d %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        value_el = card.select_one(".tv-urgent")
        value = " ".join(value_el.get_text(" ", strip=True).split()) if value_el else ""
        if not re.search(r"\d", value):
            value = None  # "Ref. Document" = value not disclosed
        state_el = card.select_one(".tc-state")
        results.append({
            "raw_title": title,
            "raw_row": card.get_text(" | ", strip=True),
            "source": source_name,
            "refNo": None,
            "stableKey": f"td-{td_id}" if td_id else None,
            "dueDateHint": due_iso,
            "value": value.replace("₹ ", "₹") if value else None,
            "location": state_el.get_text(" ", strip=True) if state_el else None,
            "docUrl": urljoin(base_url, title_link["href"]),
        })
    return results


def fetch_tenderdetail_list(source):
    """
    One plain GET of the whole listing page per run — there's no pagination
    on it. Load balancing is done in run() instead, via this
    source's "maxNewPerRun" in sources.json: only that many not-yet-seen
    tenders are added per run, so the rest trickle in as "new" over the
    next scheduled runs instead of all at once.
    """
    html = fetch(source["url"])
    if not html:
        return []
    return parse_tenderdetail_list(html, source["name"], source["url"])


def fetch_js_rendered_table(source):
    """
    For portals that render their tender listing client-side via JavaScript
    instead of in the server-sent HTML (confirmed via manual check before
    ever setting a source to this type — do NOT default a new source to
    this "just in case"). Launches a real headless browser, loads the page,
    lets its JS run, waits a moment for anything that renders after the
    network goes quiet, then hands the fully rendered HTML to the same
    forgiving row-scanning parser the plain-HTML sources use.

    Meaningfully heavier than fetch()/fetch_gepnic_homepage: a full browser
    launch + page load + JS execution per source, typically several seconds
    each (vs. a sub-second plain GET), and it needs
    `pip install playwright && playwright install --with-deps chromium`
    locally, plus the matching install step in
    .github/workflows/update-tenders.yml for the scheduled run. Given the
    workflow runs every 15 minutes, weigh whether a source actually needs
    this before adding it — each js_rendered_table source adds real time
    and CI minutes to every single run, not just a one-off cost.

    Uses the system's Microsoft Edge by default, not a downloaded browser;
    see playwright_launch_kwargs().
    """
    if not PLAYWRIGHT_AVAILABLE:
        print(f"  [!] Skipping {source['name']}: playwright not installed. "
              f"Run `pip install playwright`.")
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**playwright_launch_kwargs())
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(source["url"], timeout=30000, wait_until="networkidle")
            # "networkidle" alone isn't always enough on portals that poll
            # or lazy-render just after the network goes quiet — give any
            # late-arriving rows a moment to actually paint.
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  [!] Could not render {source['name']} with headless browser: {e}")
        return []
    return parse_generic_table(html, source["name"])


def fetch_js_interactive_search(source):
    """
    For portals whose keyword search is a single-page app: the URL never
    changes, so there's no request we can just build (unlike
    fetch_js_rendered_table, which is for pages that already show a table
    on load). Instead this actually drives a headless browser like a user
    would — types the configured keyword into the search box, clicks the
    search button, waits for the results to render, then reads the table.

    Requires two extra fields per source in sources.json (found by manual
    inspection with debug_js_source.py's --search mode — don't guess these):
      - "searchInputSelector": a Playwright/CSS selector for the keyword
        input box
      - "searchButtonSelector": a Playwright/CSS selector for the button
        that actually submits the search (not just any visible button —
        confirmed on Bihar's portal that most of the visible buttons on
        the page are unrelated UI chrome)
    Optional:
      - "searchKeyword": defaults to "ev charging station" if not set
      - "preClickSelector": a selector to click once, right after the
        initial page load, BEFORE filling the search box. Needed when the
        real search form only exists on a page reached via an in-page
        navigation, and loading that page's URL directly fails — confirmed
        on Telangana's portal: a direct GET to TenderDetailsHome.html gets
        redirected to a session-timeout page, but loading the site's root
        ("url" in sources.json) and clicking its "More..." link
        (#viewCurrentall) reaches the same page successfully because the
        session/referrer state that link sets up isn't present on a cold
        direct load. Use debug_js_source.py's --click flag against the
        root page to find/verify this selector before adding it here.

    Same operational cost/setup notes as fetch_js_rendered_table (headless
    browser per run, optional playwright dependency, Edge by default via
    playwright_launch_kwargs()) — see that function's docstring.
    """
    if not PLAYWRIGHT_AVAILABLE:
        print(f"  [!] Skipping {source['name']}: playwright not installed. "
              f"Run `pip install playwright`.")
        return []
    input_sel = source.get("searchInputSelector")
    button_sel = source.get("searchButtonSelector")
    if not input_sel or not button_sel:
        print(f"  [!] Skipping {source['name']}: js_rendered_interactive_search "
              f"needs 'searchInputSelector' and 'searchButtonSelector' set in "
              f"sources.json (use debug_js_source.py --search to find them).")
        return []
    keyword = source.get("searchKeyword", "ev charging station")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**playwright_launch_kwargs())
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(source["url"], timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            pre_click_sel = source.get("preClickSelector")
            if pre_click_sel:
                page.click(pre_click_sel, timeout=10000)
                page.wait_for_timeout(2000)
            page.fill(input_sel, keyword)
            page.click(button_sel)
            # Poll instead of a fixed sleep, but guard against the false-
            # stability trap: the results table can briefly sit at the same
            # row count (e.g. just its header row, mid-AJAX) across two 1s
            # checks before the real rows paint in, which would otherwise
            # make this exit after ~1-2s with an incomplete table. So we
            # require the SAME non-trivial count (>1, i.e. more than just a
            # header row) to hold for two checks in a row before trusting it.
            stable_count = 0
            prev_count = -1
            for _ in range(12):  # checks every 1s, up to ~12s
                page.wait_for_timeout(1000)
                count = page.evaluate("document.querySelectorAll('table tr').length")
                if count == prev_count and count > 1:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_count = 0
                prev_count = count
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  [!] Could not run search for {source['name']}: {e}")
        return []
    # TEMP DEBUG (2026-09-23): Gujarat nProcure is returning 0 rows despite
    # the stability-poll running to completion with no error. This prints
    # what the poll actually saw vs. what BeautifulSoup finds afterward, to
    # tell apart "poll exited on the wrong/unrelated table" from "rows are
    # there but parse_gepnic_table's date-pattern row filter rejects them"
    # (the same failure mode that under-counted Bihar). Remove once Gujarat
    # and Bihar are both confirmed returning their full real result counts.
    debug_soup = BeautifulSoup(html, "html.parser")
    debug_tables = debug_soup.find_all("table")
    print(f"  [debug] {len(debug_tables)} <table> element(s) in captured HTML; "
          f"row counts: {[len(t.find_all('tr')) for t in debug_tables]}")
    for ti, t in enumerate(debug_tables):
        trs = t.find_all("tr")
        if len(trs) < 2:
            continue  # header-only or empty table, not worth dumping
        print(f"  [debug] table #{ti} sample rows:")
        for tr in trs[:4]:
            cells = [c.get_text(' ', strip=True)[:220] for c in tr.find_all(['td', 'th'])]
            print(f"    {cells}")
    result = parse_generic_table(html, source["name"])
    print(f"  [debug] parse_generic_table extracted {len(result)} candidate row(s) "
          f"(before category filtering)")
    return result


# Maps a source's "type" (from sources.json) to the function that fetches
# and returns its rows. A type with no entry here (e.g.
# "blocked_by_robots_txt", "paid_aggregator", "unsupported") is deliberately
# unscrapable — this is a safety net so a source can't start being scraped
# just by someone flipping "enabled": true in sources.json; actually
# supporting a new source type requires adding a function and registering
# it here.
def fetch_generic_homepage(source):
    """Fallback for a non-GePNIC portal homepage: same idea, looser heuristic."""
    html = fetch(source["url"])
    if not html:
        return []
    return parse_generic_table(html, source["name"])


TYPE_FETCHERS = {
    "gepnic_table": fetch_gepnic_homepage,
    "generic_table": fetch_generic_homepage,
    "eesl_wp_list": fetch_eesl_tenders,
    "js_rendered_table": fetch_js_rendered_table,
    "js_interactive_search": fetch_js_interactive_search,
    "tenderdetail_list": fetch_tenderdetail_list,
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
    # ISO format (yyyy-mm-dd, optionally with a time) — seen on Bihar's
    # eProc 2.0 portal (js_interactive_search source), unlike GePNIC's
    # dd-Mon-yyyy / dd/mm/yyyy. Checked first since it's the most specific
    # pattern (4-digit year first is unambiguous, unlike 2-digit-year
    # dd/mm/yyyy which could theoretically collide with other formats).
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", row_text)
    if m:
        year, mon, day = m.groups()
        try:
            return datetime.strptime(f"{year}-{mon}-{day}", "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass  # fall through to the other patterns below
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
    # Collapse any run of whitespace (double spaces, tabs, newlines) to a
    # single space before matching. Without this, a keyword like "ev charg"
    # silently fails to match text like "installation of EV  Charging
    # stations" (two spaces) — confirmed live on Telangana's portal, where
    # BeautifulSoup's get_text(" ", strip=True) joining adjacent text nodes
    # produces exactly that double space, so a genuine EV-charging tender
    # matched zero categories and would have been silently dropped entirely
    # (SHOW_ALL_TENDERS is off by default). Not portal-specific — any
    # source's markup could produce the same irregular spacing.
    title_l = " ".join(title.lower().split())
    if not any(term in title_l for term in GENERIC_GATE_TERMS):
        return []
    matched = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, title_l):
                matched.append(category)
                break
    # Passed the EV gate but no specific category's keywords: still a real
    # EV-charging tender, so keep it under a catch-all instead of dropping
    # it. Confirmed 2026-09-23 on TenderDetail: 31 of 50 "charging station"
    # results (e.g. "Electrical Infrastructure For Intermediate Charging
    # Station At Tuni Bus Station") matched the gate but no category.
    return matched or [FALLBACK_EV_CATEGORY]


DATA_PATH = os.environ.get("TENDER_DATA_PATH", "docs/data/tenders.json")
DUE_SOON_DAYS = int(os.environ.get("DUE_SOON_DAYS") or "7")

# Toggle: when set, every scraped row is kept (tagged "General / All
# Tenders" if it doesn't match a real category) instead of being filtered
# out by matches_categories(). Currently defaulted ON, including in the
# scheduled GitHub Actions workflow — the live dashboard is intentionally
# showing every scraped tender, not just EV-charging matches, for now.
# Set TENDER_SHOW_ALL=false to go back to EV-only filtering.
# SHOW_ALL_TENDERS = os.environ.get("TENDER_SHOW_ALL", "true").lower() in ("1", "true", "yes")
SHOW_ALL_TENDERS = os.environ.get("TENDER_SHOW_ALL", "false").lower() in ("1", "true", "yes")


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
    if SHOW_ALL_TENDERS:
        print("TENDER_SHOW_ALL is on — keeping every scraped tender, not just EV-charging matches.\n")
    existing = load_existing(DATA_PATH)
    existing_by_id = {t["id"]: t for t in existing if t.get("id")}
    new_count = 0
    new_records = []

    for source in load_sources():
        if not source.get("enabled"):
            continue
        fetch_rows = TYPE_FETCHERS.get(source.get("type"))
        if not fetch_rows:
            print(f"Skipping {source['name']}: type '{source.get('type')}' isn't set up for "
                  f"automated scraping ({source.get('notes', 'no notes')}).")
            continue
        if not source.get("url"):
            print(f"Skipping {source['name']}: no URL configured in sources.json yet.")
            continue

        print(f"Checking {source['name']} ...")
        rows = fetch_rows(source)

        # Optional per-source cap on how many not-yet-seen tenders to add in
        # one run. The rest aren't lost: they're still unseen next run, so
        # they get added (and show as new) then, in batches of this size.
        max_new = source.get("maxNewPerRun")
        matched_here = 0
        deferred = 0
        for row in rows:
            cats = matches_categories(row["raw_title"])
            if not cats:
                if not SHOW_ALL_TENDERS:
                    continue
                cats = ["General / All Tenders"]
            # stableKey: a fetcher-provided unique id (e.g. TenderDetail's own
            # tender number) for sources where titles aren't unique.
            tid = make_stable_id(source["name"], row.get("stableKey") or row["raw_title"])
            if tid in existing_by_id:
                continue  # already tracked from a previous run
            if max_new and matched_here >= max_new:
                deferred += 1
                continue
            record = {
                "id": tid,
                "desc": row["raw_title"],
                "refNo": row.get("refNo"),
                "location": row.get("location"),
                "value": row.get("value"),
                "dueDate": extract_due_date(row.get("dueDateHint") or row["raw_row"]),
                "category": cats[0],
                "source": source["name"],
                # Prefer a real per-tender document URL when the fetcher
                # found one (e.g. eesl_wp_list's stable PDF links) — falls
                # back to the portal's own search page for sources like
                # GePNIC, where the per-tender "DirectLink" is tied to the
                # scraper's own session and shows "Stale Session" to anyone
                # else (confirmed live), so a real visitor has to search the
                # title themselves and solve the page's captcha instead.
                "url": row.get("docUrl") or source.get("searchUrl") or source["url"],
                "firstSeen": datetime.now().strftime("%Y-%m-%d"),
            }
            existing_by_id[tid] = record
            new_records.append(record)
            matched_here += 1
            new_count += 1

        print(f"  -> {len(rows)} rows scanned, {matched_here} new match(es)")
        if deferred:
            print(f"     ({deferred} more new match(es) held back by maxNewPerRun={max_new} "
                  f"— they'll be added on later runs)")
        if rows and matched_here == 0:
            print("     (0 new matches can be normal — either nothing new mentions EV")
            print("      charging, or today's matches were already captured before.")
            print("      Sample of what was actually scanned:)")
            for r in rows[:3]:
                print(f"       - {r['raw_title'][:90]}")
        time.sleep(1)  # be polite between sources

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
