"""
Debug helper: point this at a candidate JS-rendered tender portal to see
what its page actually looks like once JS has run — before wiring it into
sources.json.

Two modes:

1. Inspect mode (no --search) — same as before: dumps tables/links/text so
   we can see whether tender data is already present on page load.
       python debug_js_source.py "<url>"

2. Form-inspect mode (--search) — for portals that need a keyword typed
   into a search box and submitted (URL doesn't change, so this is a
   single-page app driven by a background AJAX call, not a plain link).
   Lists every visible <input> and <button>/submit element on the page
   with its id/name/placeholder/type/text, so we can pick out which one is
   the actual search box and which is the actual search button — without
   guessing and without risking typing into the wrong field (e.g. a login
   box) or clicking the wrong button.
       python debug_js_source.py "<url>" --search "charging station"

Uses the system's Microsoft Edge by default (same as scraper.py; see
tender_radar/browser.py), so no `playwright install` download is
needed. Set PLAYWRIGHT_CHROMIUM_CHANNEL=chromium to use Playwright's own
bundled Chromium instead, if it's been installed.

Requires: pip install playwright
"""

import sys

from playwright.sync_api import sync_playwright

from tender_radar.browser import playwright_launch_kwargs

# Windows' console defaults to cp1252, which can't encode plenty of
# characters that show up in real page text on these portals (arrows,
# rupee signs, Indian-language script). Without this, a single such
# character anywhere in a button label or table cell crashes the whole
# script with UnicodeEncodeError partway through — confirmed live against
# Telangana's portal, which uses a unicode arrow character. errors="replace"
# means we degrade to a "?" for anything truly unrepresentable rather than
# losing the entire run over one character.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def describe_element(el):
    tag = el.evaluate("e => e.tagName").lower()
    attrs = el.evaluate(
        "e => ({id: e.id, name: e.name, type: e.type, "
        "placeholder: e.placeholder, className: e.className, "
        "ariaLabel: e.getAttribute('aria-label'), title: e.title})"
    )
    text = (el.inner_text() or "").strip()[:40] if tag != "input" else ""
    parts = [f"<{tag}>"]
    if attrs.get("id"):
        parts.append(f"id={attrs['id']!r}")
    if attrs.get("name"):
        parts.append(f"name={attrs['name']!r}")
    if attrs.get("type"):
        parts.append(f"type={attrs['type']!r}")
    if attrs.get("placeholder"):
        parts.append(f"placeholder={attrs['placeholder']!r}")
    if attrs.get("className"):
        parts.append(f"class={attrs['className']!r}")
    if attrs.get("ariaLabel"):
        parts.append(f"aria-label={attrs['ariaLabel']!r}")
    if attrs.get("title"):
        parts.append(f"title={attrs['title']!r}")
    if text:
        parts.append(f"text={text!r}")
    return " ".join(parts)


def _safe_visible(el):
    try:
        return el.is_visible()
    except Exception:
        return False


def inspect_form_in(frame, label, search_term):
    inputs = [el for el in frame.query_selector_all("input") if _safe_visible(el)]
    buttons = [
        el
        for el in frame.query_selector_all("button, input[type=submit], a[role=button]")
        if _safe_visible(el)
    ]
    if not inputs and not buttons:
        return False
    print(f"\n=== {label} ===")
    print("--- Visible <input> elements ---")
    for el in inputs:
        print("  " + describe_element(el))
    print("--- Visible <button> / submit-like elements ---")
    for el in buttons:
        print("  " + describe_element(el))
    return True


def inspect_form(page, search_term):
    found_any = inspect_form_in(page, "Main page", search_term)

    for i, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        label = f"Iframe #{i} ({frame.url})"
        if inspect_form_in(frame, label, search_term):
            found_any = True

    if not found_any:
        print(
            "\nNo visible inputs/buttons found anywhere, including inside "
            "iframes. The page may still be loading, need a click to reveal "
            "the search form, or be blocking headless browsers. Diagnostics:"
        )
        print(f"  Rendered HTML length: {len(page.content())} chars")
        print(f"  Frames on page: {[f.url for f in page.frames]}")
        body_text = page.inner_text("body") if page.query_selector("body") else ""
        print(f"  First 500 chars of body text: {body_text[:500]!r}")
    else:
        print(
            f"\nOnce we know the right selectors, we'll fill the search box "
            f"with {search_term!r}, click the right button, wait for results, "
            f"and re-dump the tables the same way inspect mode does."
        )


def inspect(url, search_term=None, click_selector=None):
    with sync_playwright() as p:
        launch_kwargs = playwright_launch_kwargs()
        print(f"Using browser channel: {launch_kwargs.get('channel', 'bundled chromium')}")
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page()
        print(f"Loading {url} ...")
        # "networkidle" (no network activity for 500ms) hangs indefinitely on
        # some SPAs that keep a background connection alive (polling,
        # analytics beacon, etc.) — confirmed on Telangana's portal, which
        # timed out entirely under that strategy. "domcontentloaded" plus an
        # explicit extra wait is more reliable across different site
        # behaviors, at the cost of possibly not catching something that
        # renders unusually late.
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  [!] goto failed: {e}")
            browser.close()
            return
        page.wait_for_timeout(4000)

        print(f"\nPage title: {page.title()}")

        if click_selector:
            # Some portals (confirmed: Telangana's root page) put the real
            # search form inside a Bootstrap-style tab pane that only
            # becomes visible after its nav link is clicked — the pane
            # exists in the DOM on load but Playwright's is_visible() (and
            # therefore inspect_form's scan) skips everything inside it
            # until then. This mimics a real user clicking that tab first.
            print(f"Clicking {click_selector!r} to reveal its tab/panel ...")
            try:
                page.click(click_selector, timeout=10000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  [!] click failed: {e}")

        if search_term:
            inspect_form(page, search_term)
            browser.close()
            return

        links = page.query_selector_all("a")
        tender_links = []
        for a in links:
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()
            if "tender" in href.lower() or "tender" in text.lower():
                tender_links.append((text[:60], href))
        if tender_links:
            print(f"Found {len(tender_links)} tender-related link(s):")
            seen = set()
            for text, href in tender_links:
                key = (text, href)
                if key in seen:
                    continue
                seen.add(key)
                print(f"  [{text}] -> {href}")
            print()

        tables = page.query_selector_all("table")
        print(f"Found {len(tables)} <table> element(s) on the rendered page.\n")

        for i, table in enumerate(tables):
            rows = table.query_selector_all("tr")
            print(f"--- Table #{i} ({len(rows)} rows) ---")
            for row in rows[:2]:
                cells = row.query_selector_all("td, th")
                cell_texts = [c.inner_text().strip()[:60] for c in cells]
                print(f"  {cell_texts}")
            print()

        if not tables:
            print("No <table> elements found — the data may be in <div>/<li>")
            print("'card' elements instead. Dumping the first 6000 chars of")
            print("rendered body text so we can spot the pattern:\n")
            body_text = page.inner_text("body")
            print(body_text[:6000])

        browser.close()


def run_search_and_dump(url, term, input_sel, button_sel, click_selector=None):
    """
    Actually performs the search (fill + click, same as
    fetch_js_interactive_search in tender_radar/fetchers.py) and dumps EVERY row found in
    EVERY table afterward — not just a sample — so we can see exactly what
    landed in the DOM vs. what the real site showed you when you searched
    by hand. If the real site shows 3 results and this only shows 1 (or 0),
    the gap tells us whether it's a timing issue (not all rows rendered
    yet) or a row-shape issue (some rows don't look like what our parser
    expects).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(**playwright_launch_kwargs())
        page = browser.new_page()
        print(f"Loading {url} ...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        if click_selector:
            print(f"Clicking {click_selector!r} to reveal its tab/panel ...")
            try:
                page.click(click_selector, timeout=10000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  [!] click failed: {e}")
        print(f"Filling {input_sel!r} with {term!r} and clicking {button_sel!r} ...")
        page.fill(input_sel, term)
        page.click(button_sel)
        # Wait longer than the scraper does (4s) so we can tell whether a
        # longer wait would have caught more rows — that alone would
        # confirm a timing issue rather than a shape issue.
        page.wait_for_timeout(7000)

        tables = page.query_selector_all("table")
        print(f"\nFound {len(tables)} <table> element(s) after search.\n")
        for i, table in enumerate(tables):
            rows = table.query_selector_all("tr")
            print(f"--- Table #{i}: {len(rows)} <tr> total ---")
            for j, row in enumerate(rows):
                cells = row.query_selector_all("td, th")
                if not cells:
                    continue
                # Full, untruncated cell text — a previous [:70] slice here
                # cut real tender titles off mid-sentence (e.g. "Request for
                # Empanelment (RFE) For Empanelment of Agencies for Supply, "),
                # which made rows look malformed/incomplete when the parser
                # itself was actually fine. normalize whitespace (collapse
                # newlines/tabs from wrapped cells) so multi-line cells still
                # print as one readable line instead of raw \n\t noise.
                cell_texts = [" ".join(c.inner_text().split()) for c in cells]
                print(f"  row {j}: {cell_texts}")
            print()

        browser.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(
            "Usage:\n"
            '  python debug_js_source.py <url> [--search "term"] [--click "<css selector>"]\n'
            '  python debug_js_source.py <url> --search "term" '
            '--input "<css selector>" --button "<css selector>" [--click "<css selector>"]  '
            "(runs the real search and dumps every row found)\n"
            "\n"
            "  --click: use when the search form (or the results table, in "
            "inspect mode) sits inside a tab/panel that's hidden until its "
            "nav link is clicked (confirmed needed on Telangana's portal — "
            'its "Live Tenders" link is a tab trigger, not a page navigation).'
        )
        sys.exit(1)
    url = args[0]
    search_term = None
    if "--search" in args:
        idx = args.index("--search")
        if idx + 1 < len(args):
            search_term = args[idx + 1]
        else:
            print("--search needs a term after it")
            sys.exit(1)

    input_sel = None
    if "--input" in args:
        idx = args.index("--input")
        if idx + 1 < len(args):
            input_sel = args[idx + 1]

    button_sel = None
    if "--button" in args:
        idx = args.index("--button")
        if idx + 1 < len(args):
            button_sel = args[idx + 1]

    click_sel = None
    if "--click" in args:
        idx = args.index("--click")
        if idx + 1 < len(args):
            click_sel = args[idx + 1]
        else:
            print("--click needs a selector after it")
            sys.exit(1)

    if search_term and input_sel and button_sel:
        run_search_and_dump(url, search_term, input_sel, button_sel, click_sel)
    else:
        inspect(url, search_term, click_sel)
