# Improvement plan: making the code modular

A step-by-step plan for making Tender Radar easier to understand, review and
change. Each step is its own change that keeps the scraper's behaviour the
same; the tests from step 1 are how that's checked.

For how the system works today, see [ARCHITECTURE.md](ARCHITECTURE.md).

| Step | What | Status |
|---|---|---|
| 1 | Parser tests | ✅ Done (2026-09-24) |
| 2 | Split `scraper.py` into a package | ✅ Done (2026-09-24) |
| 3 | Move data out of the code | ✅ Done (2026-09-24) |
| 4 | Split `docs/index.html` | ✅ Done (2026-09-24) |
| 5 | Tooling and conventions | ✅ Done (2026-09-24) |

Suggested order: **1 → 2 → 4 → 3 → 5**. All five steps are done; what's
left is under "Open issues" at the bottom.

## Where it started

Almost everything was in two files: `scraper.py` (945 lines) and
`docs/index.html` (691 lines, with CSS and JavaScript inline). There were no
automated tests; every check was a one-off script run against saved HTML.

---

## 1. Add parser tests first ✅

This comes before any restructuring, so every later step can be checked
against the current behaviour.

- The parsers are pure functions that take HTML and return rows, which
  makes them easy to test.
- Save one real HTML page per source in `tests/fixtures/` and write `pytest`
  tests for them, e.g. "the Gujarat page gives 2 rows, this cleaned title,
  ₹2.55 Cr".
- Add a GitHub Actions job that runs the tests on every push. That would
  have caught the Gujarat `activeTenders` bug before it reached the
  dashboard.

**What was done:**
- `tests/fixtures/`: real pages from IOCL (GePNIC), EESL, TenderDetail,
  Telangana, Gujarat and Bihar, captured 2026-09-24.
- `tests/capture_fixture.py`: re-captures a source's page when its layout
  changes.
- 40 tests in `tests/test_parsers.py`, `tests/test_normalize.py` and
  `tests/test_scrape_source.py`. They run in about a second, with no network
  access.
- `.github/workflows/tests.yml`: runs them when code, tests or
  `sources.json` change.
- Checked that they catch real bugs: putting the old Gujarat bug back makes
  three tests fail.

## 2. Split `scraper.py` into a package ✅

Each file does one job, and `scraper.py` stays as a thin entry point, so the
workflow doesn't need to change.

```
tender_radar/
  browser.py        BrowserSession, Edge/Chromium choice
  sources.py        load sources.json
  parsers/          tables.py, eesl.py, tenderdetail.py  (HTML → rows)
  fetchers.py       TYPE_FETCHERS registry: source type → fetch + parser
  normalize.py      clean_title, extract_value, extract_due_date, make_stable_id
  matching.py       category and keyword matching
  store.py          load, prune and save tenders.json
  notify.py         email digest
  config.py         env settings (DATA_PATH, DUE_SOON_DAYS, SHOW_ALL…)
  pipeline.py       scrape_source() and run(): ties the steps together
scraper.py          just calls tender_radar.run()
```

Adding a source now means writing one parser file and one registry line.

**What was done:**
- Code moved as-is, including its explanatory comments; no behaviour
  changed. All 40 tests pass unchanged apart from their imports, and a full
  live run gave the same row counts from every source as before.
- Largest module is now 193 lines (`fetchers.py`); `scraper.py` is 24.
- One deviation from the original plan: the table parser is
  `parsers/tables.py`, not `gepnic.py`, because it also parses the Gujarat,
  Telangana and Bihar search results.
- `notify.py` moved into the package; it still reads `email_template.txt`
  and writes `digest_state.json` at the repo root.
- Schema validation of `sources.json` was left for step 3.

## 3. Move data out of the code ✅

- Put `CATEGORY_KEYWORDS` and the EV gate terms in `config/categories.json`,
  so non-developers can adjust matching without touching Python.
- Check `sources.json` against a schema when the scraper starts: required
  fields and known types. A mis-set source would then fail with a clear
  message instead of silently returning 0 rows.
- Document the tender record format once, as a `Tender` dataclass plus a
  short schema doc.

**What was done:**
- **`config/categories.json`** holds the EV gate terms, the categories (in
  order: the first match is the one a record gets) and the fallback
  category, with a plain-language explanation at the top of the file. It was
  generated from the old Python lists, so matching is unchanged.
  `matching.py` loads it and checks it (non-empty lists, valid patterns).
- **`sources.json` is checked on every run** (`tender_radar/sources.py`):
  unknown or misspelled fields, unknown types, missing names, duplicate
  names, `enabled` not true/false, bad or missing URLs, missing
  search selectors, patterns without a `(...)` group, and a bad
  `maxNewPerRun`. Every problem is listed in one message, the run stops
  before anything is fetched, and the data file is left untouched.
- **Both files also load when saved with a byte-order mark** (as Notepad and
  PowerShell do on Windows). Broken JSON says which line to look at. Found
  while testing: a BOM-saved file used to crash with a raw traceback.
- **`tender_radar/models.py`** defines `Tender`, the one definition of a saved
  record; the pipeline builds every new record through it.
  **[DATA_FORMAT.md](DATA_FORMAT.md)** explains each field in plain language.
- **New tests** (`tests/test_config_files.py`, plus two in
  `test_scrape_source.py`): the real `sources.json` and `categories.json`
  are valid, each common mistake gets its message, and every record already
  in `docs/data/tenders.json` has exactly the documented fields. 63 tests in
  total now.

## 4. Split `docs/index.html` ✅

No build step is needed; GitHub Pages serves these files as they are.
Loaded with `<script type="module">`, each file imports only what it uses.

```
docs/index.html      markup only (+ the tiny theme script that must run first)
docs/css/app.css     all styles
docs/js/main.js      page state, refresh, controls, theme, startup
docs/js/data.js      fetch tenders.json
docs/js/render.js    stats, banner, pills, grouped cards
docs/js/cards.js     one card + what clicking it does
docs/js/alerts.js    toasts, notifications, new/seen tracking, bell button
docs/js/util.js      escaping, dates, short names, safe localStorage
```

**What was done:**
- `index.html` went from 701 lines to 83. The CSS was moved by script, so
  it's byte-for-byte the same styles.
- Checked in a real browser: the new page is **pixel-identical** to the old
  one in light and dark themes, with no script errors or missing files.
  Search, category pills, both sort orders, both card buttons, theme
  memory and the refresh button all work.
- Deviation from the plan: a separate `render.js` for the whole page, so
  `cards.js` is only about a single card; and `util.js` for helpers several
  modules share.
- Removed the "paste tender data manually" popup: nothing could open it any
  more since its footer link was removed.
- Fixed an out-of-date empty-state message ("the scraper runs twice daily";
  it now states the real schedule).

## 5. Tooling and conventions ✅

- **`ruff`** for linting and formatting, plus a **pre-commit** hook, so
  every contributor's code looks the same.
- **Python `logging`** instead of `print`, so CI logs can show more or less
  detail without editing code.
- **Type hints** on the public functions.
- **Docs:** a short "Architecture" section in the README (see
  `ARCHITECTURE.md`), and a CONTRIBUTING page on how to add a new portal:
  check robots.txt and terms, capture a fixture, write the parser, add the
  test, add it to `sources.json`.

**What was done:**
- **ruff** (settings in `pyproject.toml`: Python 3.11, line length 110;
  rules for real bugs, import order, likely mistakes and modern syntax).
  It found 11 issues, all fixed, and the whole codebase was put into its
  standard format. That changed layout only; all tests pass unchanged.
- **pre-commit** (`.pre-commit-config.yaml`): ruff lint, ruff format and the
  tests run on every `git commit`, once someone runs `pre-commit install`.
  All three pass on the current code. CI (`tests.yml`) now also runs the
  lint and format check.
- **logging:** every `print` in `tender_radar/` is now `log.info` or
  `log.warning` (the `[!]` lines). `scraper.py` sets it up to print plain
  messages to stdout, so a run's output looks exactly as before;
  `LOG_LEVEL=WARNING` shows only problems. The debugging scripts
  (`debug_js_source.py`, `tests/capture_fixture.py`) still print: their
  output *is* the result.
- **Type hints** on every public function in `tender_radar/`, with the shared
  dict shapes named in `models.py`: `Source`, `Row`, `Record`.
- **[CONTRIBUTING.md](CONTRIBUTING.md):** setup, everyday commands, the
  checklist for adding a website (starting with robots.txt and terms), what
  to do when a site changes its layout, dashboard changes, conventions, and
  a before-you-push checklist.
- **Diagrams:** the flowcharts in ARCHITECTURE.md are now drawn with plain
  text characters instead of Mermaid, because Mermaid only displays as a
  diagram on GitHub; VS Code's preview and other viewers showed it as code.

## Coverage and schedule changes made along the way (2026-09-24)

- **IOCL and CPPP now read every active tender, not just the 10 newest.**
  GePNIC's "Tenders by Organisation" pages list each organisation's full
  tender list with no captcha (Active Tenders and Tenders by Closing Date
  need one). New source type `gepnic_by_organisation`
  (`parsers/gepnic_org.py`, `fetchers.fetch_gepnic_by_organisation`):
  - IOCL is one organisation (~220 tenders): 2 page loads a run.
  - CPPP has ~78 organisations (~1,950 tenders): each run reads the next
    `orgsPerRun` = 10 (rotation), covering all of them in about a day at
    ~11 page loads a run, with a 2-second pause between loads.
  - `maxNewPerRun` = 10 for each, so one run adds up to 10 from IOCL and 10
    from CPPP; the rest follow on later runs, as for TenderDetail.
  - Tenders are identified by the portal's own tender ID (e.g.
    `2026_AWEIL_291513_1`), and the reference number is kept.
  - A captcha makes that source stop for the run with a warning.
  - First live run: 222 IOCL and 295 CPPP tenders read in 39 seconds; none
    were EV-related yet (checked by hand: the nearest were "Mendha
    Chargaon Village" and "Turbo chargers").
- **Schedule: every 3 hours instead of every 15 minutes.** The 15 minutes was
  only for GePNIC's homepage widget, which never produced an EV match
  (history shows its only entries were non-EV, from when show-all mode was
  on), and GitHub ran the job every 3-5 hours in practice. Every source
  now shows its full current list, so nothing scrolls off between runs.
- Rajasthan and MP still use the homepage widget; they can move to
  `gepnic_by_organisation` the same way once IOCL and CPPP have run for a
  few days.

## Dashboard additions made along the way

- **New pill:** next to **All**, lists the tenders you haven't seen yet (the
  same ones the "New since last visit" tile counts, each with a NEW badge).
  Clicking that tile opens it; **Mark as seen** empties it.

---

## Open issues found along the way

- **Telangana reference numbers are wrong.** The parser picks up the
  department-name column instead. It's recorded as a known failing test
  (`xfail`) in `tests/test_parsers.py`, so fixing it makes that test flip
  and get noticed.
- **Bihar's search is occasionally read too early.** One run on 2026-09-24
  read 20 rows (apparently the unfiltered list, before the search results
  replaced it) instead of the usual 1; the next run was normal. Nothing wrong
  was saved, because the EV filter rejected those rows, but a run like that
  misses Bihar's real tender. The fix would be to wait for the results table
  to actually change after clicking Search, not just for its row count to
  settle (`fetchers.load_interactive_search_html`).
- **Some TenderDetail titles start with "…".** TenderDetail itself shortens
  long titles on its listing page (e.g. "...Vehicle Technology Laboratory In
  3 Government Engineering Colleges..."), so that's all the scraper sees.
  The full title is on each tender's own page, which the scraper doesn't
  open (one extra page load per tender).
- **Four paid-aggregator entries in `sources.json` need a decision.**
  TendersOnTime, Tendersniper, NationalTenders and Tender18 are set to type
  `tenderdetail_list` (three enabled). Their terms forbid scraping or
  republishing, and the TenderDetail parser doesn't match their page layouts
  anyway, so they'd load each site every run and most likely find nothing.
  Either set them back to `paid_aggregator` or give each its own parser.
