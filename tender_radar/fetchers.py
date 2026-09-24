"""
Fetchers: one per source "type" in sources.json. Each takes (source, session),
loads the page(s) through the shared BrowserSession, and hands the HTML to a
parser, returning its rows.

TYPE_FETCHERS at the bottom is the registry. A type with no entry there (e.g.
"blocked_by_robots_txt", "paid_aggregator", "unsupported") is deliberately
unscrapable — this is a safety net so a source can't start being scraped just
by someone flipping "enabled": true in sources.json; actually supporting a new
source type requires adding a function and registering it here.
"""

import logging
import time
from collections.abc import Callable

from . import config
from .browser import BrowserSession
from .models import Row, Source
from .parsers import (
    is_captcha_page,
    parse_eesl_tenders,
    parse_generic_table,
    parse_gepnic_org_list,
    parse_gepnic_org_tenders,
    parse_gepnic_table,
    parse_tenderdetail_list,
)

log = logging.getLogger(__name__)


def fetch_gepnic_homepage(source: Source, session: BrowserSession) -> list[Row]:
    """
    The free homepage "activeTenders" widget — the 10 most-recently-posted
    tenders site-wide. This is a single page load, confirmed stable
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
    automated, etc.).

    Full coverage without that crawl came later: see
    fetch_gepnic_by_organisation (IOCL and CPPP use it since 2026-09-24).
    This widget fetcher remains for portals not moved over yet (Rajasthan, MP).
    """
    html = session.get_html(source["url"])
    if not html:
        return []
    return parse_gepnic_table(html, source["name"])


def rotation_slice(items: list, per_run: int, slot: int) -> list:
    """
    The `per_run` items to check in rotation slot `slot`: consecutive slots
    walk through the whole list (wrapping around), so every item is covered
    every ceil(len(items) / per_run) slots. All items if they fit in one run.
    """
    if per_run <= 0 or len(items) <= per_run:
        return list(items)
    start = (slot * per_run) % len(items)
    return (items + items)[start : start + per_run]


def current_rotation_slot() -> int:
    """Changes every config.ROTATION_HOURS, i.e. once per scheduled run."""
    return int(time.time() // (config.ROTATION_HOURS * 3600))


# Pause between page loads within one source, to keep the load on a portal gentle.
ORG_PAGE_PAUSE_SECONDS = 2


def fetch_gepnic_by_organisation(source: Source, session: BrowserSession) -> list[Row]:
    """
    Every active tender of a NIC GePNIC portal, through its public, captcha-free
    "Tenders by Organisation" pages (see parsers/gepnic_org.py): the homepage
    widget only ever shows the 10 newest tenders site-wide, and the full
    listings (Active Tenders, Tenders by Closing Date) are behind a captcha.

    One run loads the organisation list (source["url"]), then the tender
    lists of at most "orgsPerRun" organisations (default: all of them),
    taking the next ones on each scheduled run (rotation_slice) so a portal
    with many organisations (CPPP: 78) is covered over about a day at ~11
    page loads per run, instead of 80 loads every run. That pattern (a rapid
    crawl) is what made these portals start demanding a captcha before, see
    fetch_gepnic_homepage. How many new tenders are then added per run is
    capped separately by "maxNewPerRun", as for every source.

    If a captcha appears anyway, this stops for the run and says so; it never
    tries to get past one.
    """
    page = session.open(source["url"], settle_ms=1500)
    if page is None:
        return []
    rows: list[Row] = []
    try:
        html = page.content()
        if is_captcha_page(html):
            log.warning(
                f"  [!] {source['name']}: the organisation list asks for a captcha; skipping this run."
            )
            return []
        orgs = parse_gepnic_org_list(html, source["url"])
        chosen = rotation_slice(orgs, source.get("orgsPerRun", 0), current_rotation_slot())
        log.info(
            f"  {len(orgs)} organisation(s) with {sum(o['count'] for o in orgs)} active tender(s); "
            f"reading {len(chosen)} this run: {', '.join(o['name'][:40] for o in chosen)}"
        )
        for org in chosen:
            time.sleep(ORG_PAGE_PAUSE_SECONDS)
            # The count link only works in the session that loaded the list,
            # which is this page's browser context.
            page.goto(org["href"], timeout=30000, wait_until="domcontentloaded")
            org_html = page.content()
            if is_captcha_page(org_html):
                log.warning(f"  [!] {source['name']}: a captcha appeared; stopping this source for this run.")
                break
            rows.extend(parse_gepnic_org_tenders(org_html, source["name"]))
    except Exception as e:
        log.warning(f"  [!] Could not read {source['name']}'s organisation pages: {e}")
    finally:
        page.context.close()
    return rows


def fetch_generic_homepage(source: Source, session: BrowserSession) -> list[Row]:
    """Fallback for a non-GePNIC portal homepage: same idea, looser heuristic."""
    html = session.get_html(source["url"])
    if not html:
        return []
    return parse_generic_table(html, source["name"])


def fetch_eesl_tenders(source: Source, session: BrowserSession) -> list[Row]:
    html = session.get_html(source["url"])
    if not html:
        return []
    return parse_eesl_tenders(html, source["name"], source["url"])


def fetch_tenderdetail_list(source: Source, session: BrowserSession) -> list[Row]:
    """
    One page load of the whole listing page per run — there's no pagination
    on it. Load balancing is done in pipeline.scrape_source() instead, via
    this source's "maxNewPerRun" in sources.json: only that many not-yet-seen
    tenders are added per run, so the rest trickle in as "new" over the
    next scheduled runs instead of all at once.
    """
    html = session.get_html(source["url"])
    if not html:
        return []
    return parse_tenderdetail_list(html, source["name"], source["url"])


def fetch_js_rendered_table(source: Source, session: BrowserSession) -> list[Row]:
    """
    For portals that render their tender listing client-side via JavaScript
    after the page loads (confirmed via manual check before ever setting a
    source to this type). Same page load as every other source, but waits
    for the network to go quiet, plus a short settle, before reading the
    HTML, so the rows the page's own JS fetches have time to paint.
    """
    # "networkidle" alone isn't always enough on portals that poll or
    # lazy-render just after the network goes quiet — give any
    # late-arriving rows a moment to actually paint.
    html = session.get_html(source["url"], wait_until="networkidle", settle_ms=2000)
    if not html:
        return []
    return parse_generic_table(html, source["name"])


def fetch_js_interactive_search(source: Source, session: BrowserSession) -> list[Row]:
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
    """
    html = load_interactive_search_html(source, session)
    if not html:
        return []
    return parse_generic_table(html, source["name"])


def load_interactive_search_html(source: Source, session: BrowserSession) -> str | None:
    """
    Runs the source's keyword search (see fetch_js_interactive_search) and
    returns the results page's HTML, or None. Separate from the parsing so
    tests/capture_fixture.py can save exactly the HTML the parser sees.
    """
    input_sel = source.get("searchInputSelector")
    button_sel = source.get("searchButtonSelector")
    if not input_sel or not button_sel:
        log.warning(
            f"  [!] Skipping {source['name']}: js_rendered_interactive_search "
            f"needs 'searchInputSelector' and 'searchButtonSelector' set in "
            f"sources.json (use debug_js_source.py --search to find them)."
        )
        return None
    keyword = source.get("searchKeyword", "ev charging station")
    page = session.open(source["url"], settle_ms=2000)
    if page is None:
        return None
    try:
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
        return page.content()
    except Exception as e:
        log.warning(f"  [!] Could not run search for {source['name']}: {e}")
        return None
    finally:
        page.context.close()


TYPE_FETCHERS: dict[str, Callable[[Source, BrowserSession], list[Row]]] = {
    "gepnic_table": fetch_gepnic_homepage,
    "gepnic_by_organisation": fetch_gepnic_by_organisation,
    "generic_table": fetch_generic_homepage,
    "eesl_wp_list": fetch_eesl_tenders,
    "js_rendered_table": fetch_js_rendered_table,
    "js_interactive_search": fetch_js_interactive_search,
    "tenderdetail_list": fetch_tenderdetail_list,
}

# Types a sources.json entry may use to record a portal that is deliberately
# NOT scraped. They have no fetcher on purpose (see the module docstring).
NON_SCRAPED_TYPES = {"paid_aggregator", "blocked_by_robots_txt", "unsupported"}

# Source types whose fetcher always provides a per-tender URL. Only used to
# fill in linkType on records saved before that field existed.
DIRECT_LINK_TYPES = {"eesl_wp_list", "tenderdetail_list"}
