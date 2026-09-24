"""
Saves the HTML a source's parser sees as a test fixture.

    python tests/capture_fixture.py "Gujarat nProcure (keyword search)" gujarat_nprocure

loads that sources.json entry the same way scraper.py does (including running
the keyword search for js_interactive_search sources) and writes
tests/fixtures/<fixture_name>.html. Re-run it when a portal changes its layout,
then update the expected values in tests/test_parsers.py to match.

One page load per run; only for sources scraper.py is allowed to scrape.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tender_radar.browser import BrowserSession  # noqa: E402
from tender_radar.fetchers import TYPE_FETCHERS, load_interactive_search_html  # noqa: E402
from tender_radar.sources import load_sources  # noqa: E402

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_html(source, session):
    source_type = source.get("type")
    if source_type == "js_interactive_search":
        return load_interactive_search_html(source, session)
    if source_type == "js_rendered_table":
        return session.get_html(source["url"], wait_until="networkidle", settle_ms=2000)
    return session.get_html(source["url"])


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    source_name, fixture_name = sys.argv[1], sys.argv[2]
    source = next((s for s in load_sources() if s["name"] == source_name), None)
    if source is None:
        sys.exit(f"No source named {source_name!r} in sources.json.")
    if source.get("type") not in TYPE_FETCHERS:
        sys.exit(f"{source_name!r} has type {source.get('type')!r}, which scraper.py doesn't scrape.")

    with BrowserSession() as session:
        html = load_html(source, session)
    if not html:
        sys.exit("Could not load the page; nothing saved.")

    os.makedirs(FIXTURES_DIR, exist_ok=True)
    path = os.path.join(FIXTURES_DIR, f"{fixture_name}.html")
    stamp = datetime.now().strftime("%Y-%m-%d")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"<!-- Test fixture: {source_name} ({source['url']}), captured {stamp} "
            f"with tests/capture_fixture.py -->\n"
        )
        f.write(html)
    print(f"Saved {path} ({len(html):,} chars)")


if __name__ == "__main__":
    main()
