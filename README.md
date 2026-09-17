# Tender Radar — EV Charging Infrastructure Tender Tracker

Live dashboard: https://sidev35.github.io/tender-browser/

## How it works

`.github/workflows/update-tenders.yml` runs `scraper.py` twice daily
(08:30 and 20:30 IST). It pulls listings from free/official govt & PSU
tender portals, filters them against the category keywords in
`scraper.py`, and commits any new matches into `docs/data/tenders.json`
— which `docs/index.html` (the dashboard, served by GitHub Pages) reads
live. The refresh icon on the dashboard re-fetches that file on demand;
it also polls automatically every 10 minutes while open and shows
in-page + browser notifications for new matches and tenders closing
within 7 days.

## Manually checking a portal yourself

The automated scraper's free access to each portal (see "Managing
sources" below) is limited to that portal's 10 most-recently-posted
tenders site-wide — their real keyword search exists but is
CAPTCHA-gated, so it isn't automated. You, as a human, can still use
that real search directly (the CAPTCHA is trivial to solve by hand)
to check the *full* current tender set, not just the latest 10:

- CPPP / etenders.gov.in: https://etenders.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page
- IOCL e-Tendering: https://iocletenders.nic.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page
- Rajasthan e-Tendering: https://eproc.rajasthan.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page
- Madhya Pradesh e-Tendering: https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page

On each, type a keyword (e.g. `electric vehicle` or `charging
station`) into **Tender Title**, enter the captcha shown, and submit.
For GeM/CESL, just use their own search bar directly on the site.

**If you find a real match this way that the dashboard doesn't show**,
use the "Add tender manually" GitHub Action (repo's **Actions** tab →
that workflow → **Run workflow**) to add it — fill in the form
(description, category, due date, location, value, source, URL) and it
commits straight into `docs/data/tenders.json`, live on the dashboard
within a minute or two. It dedupes against the same
source+description the automated scraper would use, so if the
scraper later independently finds the same tender, it won't double up.

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

Once configured, the workflow's "Run scraper" step passes these through
to `scraper.py`, which calls `notify.py` at the end of each run.

**What triggers an email:**
- **New tenders** — included once, in the run they were first matched.
- **Closing soon** — every tender within `DUE_SOON_DAYS` is re-included
  in *every* digest until it closes (by design, so it keeps nagging
  rather than notifying once and going quiet). In practice this means
  you'll get an email on every run for as long as at least one tender
  sits inside that window.
- If neither list has anything, no email is sent.

If the secrets/variables aren't set, `notify.py` prints why and skips
sending — the scraper's core job (updating `tenders.json`) never fails
because of a missing or broken email config.

The email content is built from `email_template.txt` — edit that file
to change wording/formatting; placeholders (`{{NEW_COUNT}}`,
`{{NEW_SECTION}}`, `{{DUE_SOON_SECTION}}`, etc.) are filled in by
`notify.py`.

## Running the scraper locally

```bash
pip install -r requirements.txt
python scraper.py
```

Without the SendGrid env vars set, this updates `docs/data/tenders.json`
locally and skips the email step (with a printed explanation). To
preview the dashboard against local data, serve the repo root
(`python -m http.server`, then visit `localhost:8000/docs/`) — opening
`docs/index.html` directly via `file://` can't fetch `data/tenders.json`
due to browser security rules.

**To tune what counts as a match**, edit `CATEGORY_KEYWORDS` near the
top of `scraper.py`.

## Managing sources (`sources.json`)

Every portal Tender Radar knows about — scraped or not — lives in
`sources.json` at the repo root, not in `scraper.py`. Each entry:

```json
{
  "name": "IOCL e-Tendering",
  "url": "https://iocletenders.nic.in/nicgep/app",
  "type": "gepnic_table",
  "enabled": true,
  "notes": "Free/official. NIC GePNIC engine, no login required."
}
```

- **`enabled`** — the on/off switch. Set to `false` to stop checking a
  source without deleting it.
- **`type`** — which parser reads it. Only types with a registered
  parser in `scraper.py`'s `TYPE_PARSERS` dict are ever actually
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
- **Known ceiling on every `gepnic_table` source**: its free listing
  is only the portal's 10 most-recently-posted tenders, site-wide —
  there's no free "page 2." A real keyword search exists on these
  portals but is CAPTCHA-gated (confirmed live), so it isn't
  automated. For a single organisation (IOCL) or a single state
  (Rajasthan, MP), 10-latest is a reasonably useful window since they
  don't publish that many tenders a day. For a huge nationwide feed
  like CPPP/etenders.gov.in, a niche keyword match is genuinely
  unlikely to still be in the top 10 by the time a scheduled run
  checks — that's a real coverage gap, not a bug. The paid
  aggregators already listed above solve this (that's what you pay
  them for) — lean on their own keyword alerts for the sources this
  scraper structurally can't cover for free.
- **To add a free/official portal once you've confirmed its listing
  URL** (e.g. a state e-procurement site): add an entry with
  `"type": "gepnic_table"` and `"enabled": true` — no code changes
  needed, since it reuses the existing GePNIC parser.
- **If you later get paid API access** to one of the aggregators:
  that needs an actual parser for however that API responds — add a
  function to `scraper.py`, register it in `TYPE_PARSERS` under a new
  type name (e.g. `"tenderdetail_api"`), then flip that source's
  `type`/`enabled` in `sources.json`. Until then, leave paid
  aggregators as `"paid_aggregator"` / `enabled: false` and keep using
  their own keyword/email alerts.
- **To drop a source entirely**, just delete its entry.
