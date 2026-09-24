"""
The list of portals to check lives in sources.json (repo root), not in code,
so a source can be added, removed or disabled without touching Python. See
README.md for what each field means.

A source only gets scraped if it's "enabled": true AND its "type" has a
fetcher in fetchers.TYPE_FETCHERS. Paid aggregators and robots.txt-blocked
portals are listed with types that deliberately have no fetcher, so they
can't start being scraped by accident.

load_sources() also checks the file (validate_sources) and stops with a clear
list of problems, so a typo like "enable": true or a misspelled type fails
loudly instead of silently scraping nothing.
"""

import json
import re

from . import config
from .fetchers import NON_SCRAPED_TYPES, TYPE_FETCHERS
from .models import Source

# Every field a source may have. Anything else is almost certainly a typo.
FIELDS = {
    "name": "shown on the dashboard; must be unique",
    "url": "page the scraper loads (null if there's none yet)",
    "type": "how to read the page: a fetchers.TYPE_FETCHERS key, or a not-scraped type",
    "enabled": "true/false",
    "notes": "free text: why it's set up this way",
    "searchUrl": "page the dashboard opens for 'search' links (defaults to url)",
    "maxNewPerRun": "most new tenders to add per run from this source",
    "searchInputSelector": "js_interactive_search: the keyword box",
    "searchButtonSelector": "js_interactive_search: the Search button",
    "searchKeyword": "js_interactive_search: what to search for",
    "preClickSelector": "js_interactive_search: something to click before searching",
    "titleRegex": "pattern whose first group is the real title",
    "valueRegex": "pattern whose first group is the rupee amount",
}


class SourcesError(ValueError):
    """sources.json has one or more invalid entries."""


def validate_sources(sources: object) -> list[str]:
    """Returns a list of human-readable problems (empty if the file is fine)."""
    if not isinstance(sources, list):
        return ["the file must be a JSON list of sources: [ {...}, {...} ]"]
    problems = []
    known_types = set(TYPE_FETCHERS) | NON_SCRAPED_TYPES
    seen_names = set()
    for i, src in enumerate(sources, start=1):
        if not isinstance(src, dict):
            problems.append(f"entry #{i} must be an object {{...}}")
            continue
        label = f'entry #{i} ("{src.get("name", "no name")}")'

        for key in src:
            if key not in FIELDS:
                problems.append(f'{label}: unknown field "{key}" (a typo? known fields: {", ".join(FIELDS)})')

        name = src.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f'{label}: "name" is required')
        elif name in seen_names:
            problems.append(f"{label}: another source already has this name")
        else:
            seen_names.add(name)

        if not isinstance(src.get("enabled"), bool):
            problems.append(f'{label}: "enabled" must be true or false')

        stype = src.get("type")
        if stype not in known_types:
            problems.append(f'{label}: unknown type "{stype}" (known: {", ".join(sorted(known_types))})')

        url = src.get("url")
        if url is not None and not (isinstance(url, str) and re.match(r"https?://", url)):
            problems.append(f'{label}: "url" must start with http:// or https://, or be null')
        if src.get("enabled") is True and stype in TYPE_FETCHERS and not url:
            problems.append(f'{label}: an enabled source of type "{stype}" needs a "url"')

        if stype == "js_interactive_search":
            for key in ("searchInputSelector", "searchButtonSelector"):
                if not src.get(key):
                    problems.append(f'{label}: type js_interactive_search needs "{key}"')

        for key in ("titleRegex", "valueRegex"):
            if key in src:
                try:
                    if re.compile(src[key]).groups < 1:
                        problems.append(f'{label}: "{key}" needs a (...) group around the part to keep')
                except (re.error, TypeError) as e:
                    problems.append(f'{label}: "{key}" is not a valid pattern ({e})')

        if "maxNewPerRun" in src:
            m = src["maxNewPerRun"]
            if not isinstance(m, int) or isinstance(m, bool) or m < 1:
                problems.append(f'{label}: "maxNewPerRun" must be a whole number, 1 or more')
    return problems


def load_sources(path: str | None = None) -> list[Source]:
    path = path or config.SOURCES_PATH
    # utf-8-sig: also accepts files saved with a byte-order mark, which
    # Windows editors (Notepad, PowerShell) add and plain utf-8 rejects.
    try:
        with open(path, encoding="utf-8-sig") as f:
            sources = json.load(f)
    except json.JSONDecodeError as e:
        raise SourcesError(
            f"{path} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno} "
            f"(often a missing or extra comma, or a missing quote)"
        ) from None
    problems = validate_sources(sources)
    if problems:
        raise SourcesError(f"{path} has {len(problems)} problem(s):\n  - " + "\n  - ".join(problems))
    return sources
