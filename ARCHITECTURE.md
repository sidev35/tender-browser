# How Tender Radar works

Tender Radar finds **EV-charging tenders** (government contracts for charging
stations, chargers and related work) on several tender websites, and shows
them in one place: the dashboard.

You don't need to know how to code to follow this page. The last section,
"Where things live", is for developers.

The diagrams are drawn with plain text characters, so they look the same in
any viewer. Follow the arrows (▼ and ──►) from the top; a label next to an
arrow (Yes / No) says when that path is taken.

---

## The big picture

Every 15 minutes, a small robot wakes up, visits the tender websites, keeps
only the EV-charging tenders, and saves them. The dashboard then shows what
the robot saved.

```	ext
┌──────────────────────────────────┐
│ Every 15 minutes, GitHub starts  │
│ the robot (the scraper)          │
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│ It visits each tender website    │
│ listed in sources.json           │
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│ It keeps only the EV-charging    │
│ tenders                          │
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│ It saves them in one data file   │
│ docs/data/tenders.json           │
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│ The dashboard reads that file    │
│ and shows the tenders            │
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│ You open the dashboard and       │
│ click a tender                   │
└──────────────────────────────────┘
```

- **The robot** is a program called the *scraper*. It runs for free on
  GitHub's computers, so nobody's laptop needs to be on.
- **The data file** is `docs/data/tenders.json`, one list of every tender
  found so far.
- **The dashboard** is the web page (`docs/index.html`). It only *reads* the
  data file; it never visits the tender websites itself.

---

## Where we look for tenders

The list of websites to check is kept in one file, `sources.json`. Each
website is checked in one of three ways, depending on how that site shows its
tenders.

```	ext
                            ┌─────────────────────────┐
                            │ sources.json            │
                            │ the list of websites    │
                            └────────────┬────────────┘
                                         ▼
                            ┌─────────────────────────┐
                            │ How does this website   │
                            │ show its tenders?       │
                            └────────────┬────────────┘
             ┌───────────────────────────┼───────────────────────────┐
     list on the page           must search for it        tender-listing company
             ▼                           ▼                           ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│ Read the list that's    │ │ Type 'charging station' │ │ Read its public         │
│ already on the page     │ │ into its search box,    │ │ 'charging station' page │
│                         │ │ click Search, then read │ │                         │
│                         │ │ the results             │ │                         │
│ Used for: IOCL, CPPP,   │ │ Used for: Gujarat,      │ │ Used for:               │
│ Rajasthan, MP, EESL     │ │ Telangana, Bihar        │ │ TenderDetail            │
└────────────┬────────────┘ └────────────┬────────────┘ └────────────┬────────────┘
             └───────────────────────────┼───────────────────────────┘
                                         ▼
                            ┌─────────────────────────┐
                            │ Rows of tenders:        │
                            │ title, date, value,     │
                            │ link                    │
                            └─────────────────────────┘
```

Things worth knowing:

- **Typos in `sources.json` are caught before anything runs.** If an entry
  has a misspelled field or an unknown type, the robot stops and lists
  exactly what's wrong, instead of quietly finding nothing.
- **Some websites are never checked.** A site is skipped if its rules say
  robots aren't allowed (for example GeM and Maharashtra), or if it's a paid
  service whose terms forbid copying its listings. `sources.json` records
  why for each one.
- **We're gentle with every site.** Each site is visited once per run, with
  a pause between sites, and pictures and videos are not downloaded, only
  the text of the page.
- **Government homepages only show their 10 newest tenders.** That's why the
  robot checks every 15 minutes: to catch each tender before newer ones push
  it off the list.
- **From TenderDetail, at most 10 new tenders are added per run.** The rest
  are picked up on the following runs, so the dashboard fills up gradually.

---

## How we decide a tender is relevant

A website lists all kinds of tenders (roads, schools, IT, ...). Each one goes
through the same checks:

```	ext
┌────────────────────────────────┐
│ A tender from a website        │
└────────────────┬───────────────┘
                 ▼
┌────────────────────────────────┐        ┌───────────┐
│ Does its title mention EV      │──No──► │ Ignored   │
│ charging? e.g. 'charging       │        └───────────┘
│ station', 'EV charger'         │
└────────────────┬───────────────┘
                 │ Yes
                 ▼
┌────────────────────────────────┐         ┌─────────────────────────────┐
│ Have we already saved          │──Yes──► │ Keep the saved one; refresh │
│ this tender?                   │         │ its title and value         │
└────────────────┬───────────────┘         └─────────────────────────────┘
                 │ No
                 ▼
┌────────────────────────────────┐
│ Give it a category from        │
│ config/categories.json         │
│ (or Other EV Charging)         │
└────────────────┬───────────────┘
                 ▼
┌────────────────────────────────┐
│ Saved as a NEW tender          │
│ (NEW badge, New pill)          │
└────────────────┬───────────────┘
                 ▼
┌────────────────────────────────┐         ┌───────────────────────┐
│ On every run: has its          │──Yes──► │ Removed from the list │
│ closing date passed?           │         └───────────────────────┘
└────────────────┬───────────────┘
                 │ No
                 ▼
┌────────────────────────────────┐
│ Stays on the dashboard         │
└────────────────────────────────┘
```

- **"Already saved?"** Every tender gets a fingerprint made from its website
  and title (or the site's own tender number). Seeing the same fingerprint
  again means it's not new, so nothing is shown twice.
- **The EV words and the categories** are lists in `config/categories.json`,
  a plain file anyone can edit without touching code (it explains its own
  format at the top). A tender that is clearly about EV charging but doesn't
  fit a specific category goes under **Other EV Charging** rather than being
  thrown away.
- **Tenders stay on the dashboard until they close**, even after the
  website itself has stopped listing them.

---

## What happens when you click a tender

Every card on the dashboard looks the same: category, title, website, value,
date first seen, and closing date. The button on it depends on the website.

```	ext
                  ┌────────────────────────────────┐
                  │ You click a tender card.       │
                  │ Does the website give a link   │
                  │ to this exact tender?          │
                  └────────────────┬───────────────┘
                 ┌─────────────────┴─────────────────┐
      Yes: TenderDetail, EESL             No: government portals
                 ▼                                   ▼
┌────────────────────────────────┐  ┌────────────────────────────────┐
│ View tender ↗                  │  │ Copy title & open portal ↗     │
│ opens that tender's own page   │  │ copies the title, opens the    │
└────────────────────────────────┘  │ website's search page          │
                                    └────────────────┬───────────────┘
                                                     ▼
                                    ┌────────────────────────────────┐
                                    │ You paste the title, type      │
                                    │ the captcha, and search        │
                                    └────────────────────────────────┘
```

Why the second case exists: government portals don't have permanent links
to single tenders (their links stop working for anyone else within seconds),
and most show a captcha, a "prove you're human" puzzle. The robot never
tries to get around a captcha, so a person does that one step.

### Finding what's new

Your browser remembers which tenders you've already seen. Anything found
since then gets a **NEW** badge, and the **New** pill (next to **All**) shows
just those tenders. Clicking the "New since last visit" tile opens it too.
**Mark as seen** clears them once you've looked.

---

## Optional: the email digest

If email is set up, the robot also sends a summary after a run: new tenders,
plus tenders closing within 7 days. To avoid flooding the inbox it sends at
most one email every 6 hours, even though it runs every 15 minutes.

```	ext
┌────────────────────────────┐
│ The robot finishes a run   │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐        ┌──────────┐
│ Anything new, or closing   │──No──► │ No email │
│ within 7 days?             │        └──────────┘
└──────────────┬─────────────┘
               │ Yes
               ▼
┌────────────────────────────┐         ┌──────────┐
│ Was an email sent in the   │──Yes──► │ No email │
│ last 6 hours?              │         └──────────┘
└──────────────┬─────────────┘
               │ No
               ▼
┌────────────────────────────┐
│ Email summary sent         │
└────────────────────────────┘
```

---

## Where things live (for developers)

| What | Where |
|---|---|
| Websites to check, and how | `sources.json` (checked on every run) |
| EV words and categories | `config/categories.json` (checked on every run) |
| Start the robot | `python scraper.py` (a thin entry point) |
| Robot's code | `tender_radar/` (module map below) |
| Saved tenders | `docs/data/tenders.json`, format in [DATA_FORMAT.md](DATA_FORMAT.md) |
| Dashboard | `docs/index.html` + `docs/css/app.css` + `docs/js/` (map below) |
| Robot's schedule | `.github/workflows/update-tenders.yml` |
| Tests (run on saved copies of real pages) | `tests/`, run with `python -m pytest` |
| Lint/format settings, commit hook | `pyproject.toml`, `.pre-commit-config.yaml` |
| How to make a change | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Email wording | `email_template.txt` |

Inside `tender_radar/`, in the order one run uses them:

```	ext
scraper.py
   │
   ▼
tender_radar/pipeline.py   run() does these steps, in order:
   │
   ├─ 1 ─► sources.py     read and check sources.json
   ├─ 2 ─► browser.py     start one shared headless browser
   ├─ 3 ─► fetchers.py    for each enabled source, load its page(s)
   │          └─────────► parsers/      page HTML ──► rows of tenders
   ├─ 4 ─► normalize.py   clean each row: title, due date, value, id
   ├─ 5 ─► matching.py    EV check + category  ◄── config/categories.json
   ├─ 6 ─► models.py      build each new Tender record
   ├─ 7 ─► store.py       merge, drop expired, save docs/data/tenders.json
   └─ 8 ─► notify.py      optional email digest

   config.py: settings (file paths, "closing soon" days, ...) used throughout
```

| Module | Job |
|---|---|
| `config.py` | Settings from environment variables (data path, "closing soon" days, show-all toggle, where `categories.json` is) |
| `sources.py` | Loads `sources.json` and checks it: known fields and types, required fields, valid patterns. Stops with a list of problems if anything is wrong |
| `browser.py` | `BrowserSession`: one headless browser per run (Microsoft Edge locally, Chromium in CI), a fresh context per source, images/fonts/media blocked |
| `fetchers.py` | One fetch function per source `type`, plus the `TYPE_FETCHERS` registry. A type that isn't registered can never be scraped |
| `parsers/` | Pure functions, HTML in and rows out: `tables.py` (GePNIC widget and search-results tables), `eesl.py`, `tenderdetail.py` |
| `normalize.py` | Stable id, due date, title cleanup (`titleRegex`), value (`valueRegex`) |
| `matching.py` | Loads and checks `config/categories.json`; decides if a title is EV-related and which category it gets |
| `models.py` | `Tender`: the one definition of a saved record (described in [DATA_FORMAT.md](DATA_FORMAT.md)) |
| `store.py` | Load existing tenders, drop expired ones, save |
| `notify.py` | Optional SendGrid email digest, throttled |
| `pipeline.py` | `scrape_source()` for one source, `run()` for a whole run |

All modules report through Python `logging` (`LOG_LEVEL=WARNING` shows only
problems), and public functions have type hints; the shared dict shapes are
named in `models.py` (`Source`, `Row`, `Record`).

### The dashboard (`docs/`)

`index.html` is only the page's layout. The look is in `css/app.css` and the
behaviour is split into small JavaScript modules, loaded by the browser with
no build step:

```	ext
index.html ──loads──► js/main.js    page state, auto-refresh, controls, theme
                        │
                        ├──► js/data.js      fetch data/tenders.json
                        ├──► js/render.js    stat tiles, banner, pills, grouped cards
                        │       └──► js/cards.js    one card + its button
                        └──► js/alerts.js    toasts, notifications, new/seen tracking

           js/util.js:  helpers (escaping, dates, short names) used by all of them
           css/app.css: the look (light and dark colours)
```

| File | Job |
|---|---|
| `index.html` | Layout only, plus a tiny script that applies the saved theme before the page draws |
| `css/app.css` | All styles; light and dark colours as CSS variables |
| `js/main.js` | Entry point: page state, loading and auto-refresh every 10 minutes, search/sort/theme/refresh wiring |
| `js/data.js` | Fetches `data/tenders.json` |
| `js/render.js` | Draws the page: stat tiles, "new since last visit" banner, pills (All, New, categories), grouped cards |
| `js/cards.js` | One card, and its button: open the tender, or copy the title and open the portal |
| `js/alerts.js` | Toasts, browser notifications, the bell button, remembering what you've already seen |
| `js/util.js` | Shared helpers: HTML escaping, dates, short names, safe `localStorage` |

The page must be served over http(s) (the scheduled site, or
`python -m http.server` locally); opened as a file it can't load its modules
or data.

**Adding a new website**, in short: check its `robots.txt` and terms of use
first; if it fits an existing `type`, add an entry to `sources.json` (the
scraper checks the entry and tells you if a field is wrong); otherwise write a
parser in `parsers/`, a fetcher in `fetchers.py`, register it in
`TYPE_FETCHERS`, and add a test with a saved copy of the page
(`tests/capture_fixture.py`). The step-by-step version is in
[CONTRIBUTING.md](CONTRIBUTING.md).
