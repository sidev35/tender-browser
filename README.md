# Tender Radar — EV Charging Infrastructure Tender Tracker

Live dashboard: https://sidev35.github.io/tender-browser/

New here? Start with **[ARCHITECTURE.md](ARCHITECTURE.md)**, a plain-language
picture of how everything fits together. **[IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md)**
tracks the ongoing clean-up of the code. **[DATA_FORMAT.md](DATA_FORMAT.md)**
describes each field of a saved tender, and **[CONTRIBUTING.md](CONTRIBUTING.md)**
is how to make a change (setup, tests, adding a website).

## How it works

`.github/workflows/update-tenders.yml` runs `scraper.py` **every 15
minutes**. It pulls each portal's free "latest tenders" homepage
listing, filters it against the category keywords in `config/categories.json`,
and commits any new matches into `docs/data/tenders.json` — which
`docs/index.html` (the dashboard, served by GitHub Pages) reads live.
The refresh icon on the dashboard re-fetches that file on demand; it
also polls automatically every 10 minutes while open and shows
in-page + browser notifications for new matches and tenders closing
within 7 days. The **New** pill (next to **All**) lists the tenders you
haven't seen yet.

**Why every 15 minutes:** each portal's free listing is only its 10
most-recently-posted tenders, site-wide (see "Known ceiling" below) —
a rolling window that rotates as new tenders get posted. Checking
that often is how a genuine EV-charging match gets caught before it
scrolls off, rather than checking so rarely that most tenders never
show up in the window at the moment we happen to look.

**Matched tenders stay on the dashboard after they scroll off the
source's own 10-latest window** — this isn't a separate "pinning"
feature, it falls out of how `scraper.py` merges results: each run
loads the *existing* `docs/data/tenders.json`, only ever adds tenders
it hasn't seen before (by a stable id), and only drops one once its
due date has actually passed. So a tender matched on one run is still
there on the next, and the one after that, whether or not it's still
sitting in the source portal's own top-10 — until it closes.

## Known ceiling — and why it isn't automated further

Every source's free listing is capped at those 10 latest tenders.
Each portal also has a real, much bigger "Tenders by Closing Date"
report (hundreds of tenders, fully paginated) that looked like a free
win — no captcha, on first check. It was built and tested here, then
deliberately removed: a handful of automated requests into that
pagination was enough to make every one of these portals start
demanding a captcha on that same endpoint. That's the site's own
bot-detection reacting to *request pattern* (a rapid paginated crawl),
not a permanent block — but it means running that at real scale
(hundreds of requests, every 15 minutes) would almost certainly wall
itself off the same way. This project doesn't try to work around a
captcha once one appears (no OCR-solving, no request-spacing tricks
to look less automated) — so the 10-latest homepage widget, checked
frequently, is the practical ceiling for hands-off automation here.

**Each card's button depends on whether the tender can be linked
directly.** TenderDetail and EESL give a stable link to each tender, so
the button is **View tender ↗** and opens it. GePNIC's own per-tender
"DirectLink" is tied to the *scraper's* session and shows "Stale
Session" to literally anyone else who opens it, even seconds later
(confirmed live), and the keyword-search portals have no per-tender
link at all. For those, the button is **Copy title & open portal ↗**:
one click copies the tender's title and opens the portal's search page
(`sources.json`'s `searchUrl`, a stable URL, not session-scoped) in a
new tab. From there: paste, enter the captcha shown, search — that's a
real person completing the one step (the captcha) this project won't
automate around. Each record's `linkType` (`direct` or `search`) tells
the dashboard which button to show.

For GeM/CESL — not scraped at all, see "Managing sources" below — just
use their own search bar directly on the site. Of the paid aggregators,
only TenderDetail is scraped: its public "charging station" listing page,
whose terms allow internal use (see its `sources.json` notes), at most 10
new tenders per run. For the others, whose terms forbid scraping, use their
own keyword-alert features.

## Email digest setup (optional)

Each scraper run can also email a digest via SendGrid. This repo is
public, so none of this configuration lives in a committed file —
it's all GitHub Actions secrets/variables, injected as env vars into
the workflow.

1. **Create a SendGrid account** (free tier: 100 emails/day) and verify
   a **single sender** address under Settings → Sender Authentication —
   that address is what you'll use as `NOTIFY_FROM_EMAIL`.
2. **Create an API key** under Settings → API Keys (Restricted Access →
   Mail Send is enough).
3. In this repo, go to **Settings → Secrets and variables → Actions**:
   - Under **Secrets**, add `SENDGRID_API_KEY` = the API key from step 2.
   - Under **Variables**, add:
     - `NOTIFY_FROM_EMAIL` = the verified sender address from step 1
     - `NOTIFY_RECIPIENTS` = comma-separated list of who should get the digest
     - `DUE_SOON_DAYS` (optional) = override the 7-day "closing soon" window
     - `MIN_HOURS_BETWEEN_DIGESTS` (optional) = override the 6-hour minimum gap between emails (see below)

Once configured, the workflow's "Run scraper" step passes these through
to `scraper.py`, which calls `tender_radar/notify.py` at the end of each run.

**What triggers an email:**
- **New tenders** — included once, in the run they were first matched.
- **Closing soon** — every tender within `DUE_SOON_DAYS` is re-included
  in *every* digest until it closes (by design, so it keeps nagging
  rather than notifying once and going quiet).
- If neither list has anything, no email is sent.

**Throttled independently of the scraper's 15-minute schedule**: since
"closing soon" would otherwise re-send on every single run, `tender_radar/notify.py`
tracks the last successful send in `digest_state.json` (committed
alongside `docs/data/tenders.json`) and skips sending — while still
updating the dashboard data normally — if less than
`MIN_HOURS_BETWEEN_DIGESTS` (default 6) has passed. So you get at most
a handful of emails a day, not one every 15 minutes.

If the secrets/variables aren't set, `tender_radar/notify.py` prints why and skips
sending — the scraper's core job (updating `tenders.json`) never fails
because of a missing or broken email config.

The email content is built from `email_template.txt` — edit that file
to change wording/formatting; placeholders (`{{NEW_COUNT}}`,
`{{NEW_SECTION}}`, `{{DUE_SOON_SECTION}}`, etc.) are filled in by
`tender_radar/notify.py`.

## Running the scraper locally

```bash
pip install -r requirements.txt
python scraper.py
```

Without the SendGrid env vars set, this updates `docs/data/tenders.json`
locally and skips the email step (with a printed explanation). Set
`LOG_LEVEL=WARNING` to see only problems in the output. To
preview the dashboard against local data, serve the repo root
(`python -m http.server`, then visit `localhost:8000/docs/`) — opening
`docs/index.html` directly via `file://` can't fetch `data/tenders.json`
due to browser security rules.

**To tune what counts as a match**, edit the word lists in
`config/categories.json` (no code change needed; the file explains its own
format at the top). The scraper checks the file when it starts and says
exactly what's wrong if an entry is invalid.

**`TENDER_SHOW_ALL` controls whether every scraped tender is kept**, or
only ones matching those categories. Non-matching tenders get tagged
`"General / All Tenders"` instead of being dropped when this is on.

This **defaults to `false`** (EV-charging matches only), including in the
scheduled GitHub Actions workflow. To change the default, edit
`SHOW_ALL_TENDERS` in `tender_radar/config.py` (and push) — or override it for a
single local run either way:

```bash
TENDER_SHOW_ALL=false python scraper.py   # EV-only, this run only
TENDER_SHOW_ALL=true python scraper.py    # show everything, this run only
```

Matches already saved from a run stay in `tenders.json` until manually
removed or their due date passes, same merge behavior as any other
tender — so switching the default doesn't retroactively filter what's
already on the dashboard.

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest            # tests
ruff check . && ruff format --check .   # lint + formatting
pre-commit install          # optional: run all of this on every commit
```

The tests never touch the network: each source's parser runs on a real
page saved in `tests/fixtures/`, and the expected titles, dates, values
and links are what that page contained. They also run on GitHub Actions
(`.github/workflows/tests.yml`) whenever code, tests or `sources.json`
change.

When a portal changes its layout, re-capture its fixture and update the
expected values in `tests/test_parsers.py`:

```bash
python tests/capture_fixture.py "Gujarat nProcure (keyword search)" gujarat_nprocure
```

A test marked `xfail` is a known bug, documented rather than hidden. Once
it's fixed the test starts passing, and pytest flags it so the marker
gets removed.

## Managing sources (`sources.json`)

Every portal Tender Radar knows about — scraped or not — lives in
`sources.json` at the repo root, not in the code. The scraper checks the
file every time it starts: a misspelled field (`"enable"`), an unknown
`type`, a missing required field or an invalid pattern stops the run with a
list of exactly what's wrong, before anything is fetched or saved. Each entry:

```json
{
  "name": "IOCL e-Tendering",
  "url": "https://iocletenders.nic.in/nicgep/app",
  "searchUrl": "https://iocletenders.nic.in/nicgep/app?page=FrontEndAdvancedSearch&service=page",
  "type": "gepnic_table",
  "enabled": true,
  "notes": "Free/official. NIC GePNIC engine, no login required."
}
```

- **`searchUrl`** — where matched tenders link to on the dashboard: a
  stable, session-independent search page a real visitor can use (see
  "Known ceiling" above for why this is used instead of a per-tender
  deep link). Falls back to `url` if omitted for a source that doesn't
  have one.
- **`enabled`** — the on/off switch. Set to `false` to stop checking a
  source without deleting it.
- **`type`** — which fetcher reads it. Only types with a registered
  fetcher in `TYPE_FETCHERS` (`tender_radar/fetchers.py`) are ever actually
  scraped, **regardless of `enabled`** — this is a deliberate safety
  net. Right now that's just `"gepnic_table"` (the NIC GePNIC engine
  used by IOCL, CPPP/etenders.gov.in, and the Rajasthan/Madhya Pradesh
  state portals — all currently `enabled`). Everything else in the
  file — `"blocked_by_robots_txt"` (GeM, CESL, and Maharashtra's
  mahatenders.gov.in — all three disallow automated access via
  robots.txt), `"paid_aggregator"` (TenderDetail, TendersOnTime,
  Tendersniper, NationalTenders, Tender18 — scraping a paid product
  you subscribe to likely breaches its ToS) and `"unsupported"` (NHAI,
  Telangana, Bihar, Gujarat nProcure — no confirmed free listing URL
  on the standard GePNIC layout yet) — is listed for visibility but
  intentionally can't be scraped until you deliberately add support
  for it.
- **To add a free/official portal once you've confirmed its listing
  URL** (e.g. a state e-procurement site): add an entry with
  `"type": "gepnic_table"` and `"enabled": true` — no code changes
  needed, since it reuses the existing GePNIC fetcher.
- **If you later get paid API access** to one of the aggregators:
  that needs an actual fetcher for however that API responds — add a
  function to `tender_radar/fetchers.py`, register it in `TYPE_FETCHERS` under a new
  type name (e.g. `"tenderdetail_api"`), then flip that source's
  `type`/`enabled` in `sources.json`. Until then, leave paid
  aggregators as `"paid_aggregator"` / `enabled: false` and keep using
  their own keyword/email alerts.
- **To drop a source entirely**, just delete its entry.
