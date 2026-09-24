# Contributing to Tender Radar

Read [ARCHITECTURE.md](ARCHITECTURE.md) first: it explains how the pieces fit
together. This page covers how to make a change safely.

## One-time setup

```bash
pip install -r requirements-dev.txt   # scraper + pytest, ruff, pre-commit
pre-commit install                    # run lint + tests on every `git commit`
```

The scraper drives the Microsoft Edge that's already on your machine, so no
browser download is needed (see `tender_radar/browser.py`).

## Everyday commands

| To... | Run |
|---|---|
| Run the scraper (updates `docs/data/tenders.json`) | `python scraper.py` |
| See only problems in its output | `LOG_LEVEL=WARNING python scraper.py` |
| Preview the dashboard | `python -m http.server`, then open `localhost:8000/docs/` |
| Run the tests (about a second, no network) | `python -m pytest` |
| Check and tidy the code | `ruff check . --fix` then `ruff format .` |
| Everything the commit hook runs | `pre-commit run --all-files` |

GitHub runs the same lint and tests on every push that touches code
(`.github/workflows/tests.yml`).

## Common changes

### Change which tenders count as EV-charging

Edit `config/categories.json`. No code change is needed, and the file explains
its own format at the top. Then run `python -m pytest`: if a test now fails,
check whether the change dropped or re-categorised a tender you care about.

### Add a new tender website

1. **Check you're allowed to scrape it.** Read its `robots.txt` and its terms
   of use. If either forbids automated access or reuse, don't scrape it: add
   it to `sources.json` with type `blocked_by_robots_txt` or
   `paid_aggregator` and explain why in `notes`.
2. **If it works like an existing source**, add an entry to `sources.json`
   with that `type` (see README "Managing sources" for the fields). The
   scraper checks the entry when it starts and tells you exactly what's
   wrong, e.g. a misspelled field.
3. **If it needs new parsing:**
   - write a parser in `tender_radar/parsers/` (HTML in, a list of rows out;
     row fields are listed in `parsers/__init__.py`);
   - write a fetcher in `tender_radar/fetchers.py` and register it in
     `TYPE_FETCHERS` under a new type name;
   - add the new type to the entry in `sources.json`.
4. **Save a real copy of the page and test against it:**
   ```bash
   python tests/capture_fixture.py "<source name>" <fixture_name>
   ```
   Then add tests to `tests/test_parsers.py` asserting what that page
   actually contains: row count, a title, the due date, the link.
5. Run the scraper once and check the new tenders on the dashboard.

### A website changed its layout

Its tests will start failing, or the scraper will report 0 rows. Re-capture
its fixture with `tests/capture_fixture.py`, fix the parser, and update the
expected values in `tests/test_parsers.py`.

### Change the dashboard

The page is `docs/index.html` (layout), `docs/css/app.css` (look) and
`docs/js/*.js` (behaviour; see the map in ARCHITECTURE.md). There's no build
step: edit, reload `localhost:8000/docs/`, and check the browser console for
errors. Anything scraped (titles, sources) must go through `escapeHtml()`
before being put into the page.

## Code conventions

- **Formatting and lint:** ruff, settings in `pyproject.toml` (line length
  110). The commit hook and CI enforce it.
- **Output:** use the module's `log` (`log = logging.getLogger(__name__)`),
  not `print`. `log.info` for progress, `log.warning` for problems, with the
  `[!]` prefix the rest of the output uses.
- **Type hints** on public functions. The shared dict shapes are named in
  `tender_radar/models.py`: `Source`, `Row`, `Record`.
- **Comments explain *why*,** especially anything learned from a real
  website ("confirmed live on Telangana's portal: ..."). Those notes are how
  the next person avoids repeating an investigation.
- **Known bugs** get a test marked `@pytest.mark.xfail(strict=True, reason=...)`
  instead of being left undocumented.

## Before you push

- [ ] `pre-commit run --all-files` passes (lint, format, tests)
- [ ] New or changed parsing has a fixture-based test
- [ ] Any new website was checked against its `robots.txt` and terms
- [ ] If you changed behaviour someone would notice, the relevant `.md` file
      is updated too
