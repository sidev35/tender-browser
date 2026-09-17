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
top of `scraper.py`. **To add a new source**, add an entry to `SOURCES`,
following the commented example.
