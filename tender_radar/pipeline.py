"""
One scraper run, start to finish:

    sources.json -> for each enabled source: fetch rows -> keep EV matches
    -> merge into tenders.json -> drop expired -> save -> email digest

scrape_source() handles one source; run() is the whole run.
"""

import logging
import time
from datetime import datetime

from . import config, fetchers
from .browser import BrowserSession
from .matching import matches_categories
from .models import Record, Source, Tender
from .normalize import clean_title, days_until, extract_due_date, extract_value, make_stable_id
from .notify import send_digest
from .sources import load_sources
from .store import backfill_link_types, drop_expired, load_existing, save

log = logging.getLogger(__name__)


def scrape_source(
    source: Source, session: BrowserSession, existing_by_id: dict[str, Record], new_records: list[Record]
) -> None:
    """Fetches one source and merges its matches into existing_by_id."""
    fetch_rows = fetchers.TYPE_FETCHERS.get(source.get("type"))
    if not fetch_rows:
        log.info(
            f"Skipping {source['name']}: type '{source.get('type')}' isn't set up for "
            f"automated scraping ({source.get('notes', 'no notes')})."
        )
        return
    if not source.get("url"):
        log.info(f"Skipping {source['name']}: no URL configured in sources.json yet.")
        return

    log.info(f"Checking {source['name']} ...")
    rows = fetch_rows(source, session)

    # Optional per-source cap on how many not-yet-seen tenders to add in
    # one run. The rest aren't lost: they're still unseen next run, so
    # they get added (and show as new) then, in batches of this size.
    max_new = source.get("maxNewPerRun")
    matched_here = 0
    deferred = 0
    for row in rows:
        title = clean_title(source, row["raw_title"])
        value = row.get("value") or extract_value(source, row["raw_row"])
        # The id stays keyed on the raw text (or stableKey, a fetcher-provided
        # unique id such as TenderDetail's own tender number, for sources
        # where titles aren't unique), so tightening a source's title
        # cleanup later doesn't turn already-tracked tenders into "new" ones.
        tid = make_stable_id(source["name"], row.get("stableKey") or row["raw_title"])
        if tid in existing_by_id:
            # Pick up improved title/value extraction on already-tracked tenders.
            existing_by_id[tid]["desc"] = title
            if value:
                existing_by_id[tid]["value"] = value
            continue  # already tracked from a previous run
        cats = matches_categories(title)
        if not cats:
            if not config.SHOW_ALL_TENDERS:
                continue
            cats = ["General / All Tenders"]
        if max_new and matched_here >= max_new:
            deferred += 1
            continue
        record = Tender(
            id=tid,
            desc=title,
            refNo=row.get("refNo"),
            location=row.get("location"),
            value=value,
            dueDate=extract_due_date(row.get("dueDateHint") or row["raw_row"]),
            category=cats[0],
            source=source["name"],
            # Prefer a real per-tender document URL when the fetcher
            # found one (e.g. eesl_wp_list's stable PDF links) — falls
            # back to the portal's own search page for sources like
            # GePNIC, where the per-tender "DirectLink" is tied to the
            # scraper's own session and shows "Stale Session" to anyone
            # else (confirmed live), so a real visitor has to search the
            # title themselves and solve the page's captcha instead.
            url=row.get("docUrl") or source.get("searchUrl") or source["url"],
            # "direct": url opens this exact tender. "search": url is the
            # portal's search/listing page, so the dashboard copies the
            # title for the visitor to search with.
            linkType="direct" if row.get("docUrl") else "search",
            firstSeen=datetime.now().strftime("%Y-%m-%d"),
        ).to_dict()
        existing_by_id[tid] = record
        new_records.append(record)
        matched_here += 1

    log.info(f"  -> {len(rows)} rows scanned, {matched_here} new match(es)")
    if deferred:
        log.info(
            f"     ({deferred} more new match(es) held back by maxNewPerRun={max_new} "
            f"— they'll be added on later runs)"
        )
    if rows and matched_here == 0:
        log.info(
            "     (0 new matches can be normal — either nothing new mentions EV\n"
            "      charging, or today's matches were already captured before.\n"
            "      Sample of what was actually scanned:)"
        )
        for r in rows[:3]:
            log.info(f"       - {clean_title(source, r['raw_title'])[:90]}")


def run() -> None:
    if config.SHOW_ALL_TENDERS:
        log.info("TENDER_SHOW_ALL is on — keeping every scraped tender, not just EV-charging matches.\n")
    existing = load_existing(config.DATA_PATH)
    existing_by_id = {t["id"]: t for t in existing if t.get("id")}
    new_records = []
    sources = load_sources()

    session = BrowserSession()
    try:
        session.start()
    except Exception as e:
        log.error(
            f"[!] Could not start the headless browser ({e}).\n"
            "    Locally this uses Microsoft Edge by default; in CI, PLAYWRIGHT_CHROMIUM_CHANNEL=chromium\n"
            "    plus `playwright install chromium`. Nothing was scraped; data file left unchanged."
        )
        raise SystemExit(1) from None
    try:
        for source in sources:
            if source.get("enabled"):
                scrape_source(source, session, existing_by_id, new_records)
                time.sleep(1)  # be polite between sources
    finally:
        session.close()

    backfill_link_types(existing_by_id.values(), sources, fetchers.DIRECT_LINK_TYPES)
    merged = drop_expired(existing_by_id.values())
    save(config.DATA_PATH, merged)

    log.info(
        f"\nDone. {len(new_records)} new match(es) this run. "
        f"{len(merged)} total tenders now in {config.DATA_PATH}."
    )
    log.info(f"Run at: {datetime.now().isoformat()}")

    # Email digest: "new" tenders only ever appear in the run they were first
    # matched; "closing soon" tenders are re-included in every digest until
    # they pass, by design (see README) — so this will email on every run
    # for as long as at least one tender sits inside the closing-soon window.
    merged_ids = {t["id"] for t in merged}
    new_records = [r for r in new_records if r["id"] in merged_ids]
    due_soon_records = [
        t
        for t in merged
        if (d := days_until(t.get("dueDate"))) is not None and 0 <= d <= config.DUE_SOON_DAYS
    ]
    try:
        send_digest(new_records, due_soon_records)
    except Exception as e:
        log.warning(f"  [!] Email digest failed (continuing without it): {e}")
