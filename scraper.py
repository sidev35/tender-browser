"""
EV Charging Tender Scraper — entry point.

    pip install -r requirements.txt
    python scraper.py

Checks every enabled portal in sources.json, keeps the EV-charging tenders,
and merges them into docs/data/tenders.json, the file the Tender Radar
dashboard (docs/index.html) reads. The scheduled GitHub Actions workflow
(.github/workflows/update-tenders.yml) runs exactly this.

The code lives in the tender_radar/ package; see ARCHITECTURE.md for how it
fits together, and tender_radar/__init__.py for the module map.

Uses the system's Microsoft Edge by default, so no `playwright install`
download is needed (see tender_radar/browser.py). To preview the dashboard
against local data, run `python -m http.server` from the repo root and visit
localhost:8000/docs/ — opening docs/index.html directly (file://) can't fetch
data/tenders.json due to browser security rules around local files.
"""

import logging
import os
import sys

# Plain messages on stdout, like print(), so the output reads the same.
# LOG_LEVEL=WARNING shows only problems; LOG_LEVEL=DEBUG shows more detail.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(message)s",
    stream=sys.stdout,
)

# A problem in config/categories.json (CategoriesError, a ValueError) or in
# sources.json (SourcesError) stops the run with its readable list of
# problems instead of a traceback, before anything is fetched or written.
try:
    from tender_radar import run
    from tender_radar.sources import SourcesError
except ValueError as e:
    sys.exit(f"[!] {e}")

if __name__ == "__main__":
    try:
        run()
    except SourcesError as e:
        sys.exit(f"[!] {e}\nNothing was scraped; data file left unchanged.")
