"""
Settings, read once from environment variables (with defaults), so the rest
of the package never reads os.environ directly.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the dashboard's data file and the source list live (repo-relative,
# as the scheduled workflow runs from the repo root).
DATA_PATH = os.environ.get("TENDER_DATA_PATH", "docs/data/tenders.json")
SOURCES_PATH = os.environ.get("TENDER_SOURCES_PATH", "sources.json")

# The EV keyword lists and categories (see matching.py).
CATEGORIES_PATH = os.environ.get(
    "TENDER_CATEGORIES_PATH", os.path.join(REPO_ROOT, "config", "categories.json")
)

# How often the scheduled workflow runs, in hours. Sources that check a few
# organisations per run (orgsPerRun) move on to the next ones every this many
# hours, so keep it in step with the cron in update-tenders.yml.
ROTATION_HOURS = float(os.environ.get("TENDER_ROTATION_HOURS") or "3")

# "Closing soon" window for the email digest, in days.
DUE_SOON_DAYS = int(os.environ.get("DUE_SOON_DAYS") or "7")

# Toggle: when set, every scraped row is kept (tagged "General / All
# Tenders" if it doesn't match a real category) instead of being filtered
# out by matching.matches_categories(). Off by default, including in the
# scheduled GitHub Actions workflow: only EV-charging matches are kept.
# Set TENDER_SHOW_ALL=true to keep everything.
SHOW_ALL_TENDERS = os.environ.get("TENDER_SHOW_ALL", "false").lower() in ("1", "true", "yes")

# Sent as the browser's User-Agent on every page load.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
