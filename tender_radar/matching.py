"""
Deciding whether a tender is about EV charging, and which category it goes
under. The word lists live in config/categories.json (not in code), so they
can be tuned without touching Python; that file explains its own format.
"""

import json
import re

from . import config


class CategoriesError(ValueError):
    """config/categories.json is missing something or has a bad entry."""


def load_categories(path: str | None = None) -> tuple[list[str], dict[str, list[str]], str]:
    """
    Reads and checks config/categories.json. Returns
    (gate_terms, categories, fallback_category), where categories keeps the
    file's order (the first matching category is the one a record gets).
    """
    path = path or config.CATEGORIES_PATH
    # utf-8-sig: also accepts files saved with a byte-order mark, which
    # Windows editors (Notepad, PowerShell) add and plain utf-8 rejects.
    try:
        with open(path, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        raise CategoriesError(
            f"{path} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno} "
            f"(often a missing or extra comma, or a missing quote)"
        ) from None
    except OSError as e:
        raise CategoriesError(f"Could not read {path}: {e}") from None

    problems = []
    gate = doc.get("evGateTerms")
    if not isinstance(gate, list) or not gate or not all(isinstance(t, str) and t.strip() for t in gate):
        problems.append('"evGateTerms" must be a non-empty list of words/phrases')
    fallback = doc.get("fallbackCategory")
    if not isinstance(fallback, str) or not fallback.strip():
        problems.append('"fallbackCategory" must be a category name')
    cats = doc.get("categories")
    if not isinstance(cats, dict) or not cats:
        problems.append('"categories" must map each category name to a list of phrases')
        cats = {}
    for name, phrases in cats.items():
        if not isinstance(phrases, list) or not phrases:
            problems.append(f'category "{name}" needs a non-empty list of phrases')
            continue
        for p in phrases:
            try:
                re.compile(p)
            except (re.error, TypeError) as e:
                problems.append(f'category "{name}": phrase {p!r} is not a valid pattern ({e})')
    if problems:
        raise CategoriesError(f"{path} has problems:\n  - " + "\n  - ".join(problems))
    return [t.lower() for t in gate], cats, fallback


# The first check: a title must contain at least one of these (plain text,
# not patterns) to count as an EV-charging tender at all. It's then tagged
# with every category whose phrases (regular expressions) it matches.
# Loaded once, when the package is imported.
GENERIC_GATE_TERMS, CATEGORY_KEYWORDS, FALLBACK_EV_CATEGORY = load_categories()


def matches_categories(title: str) -> list[str]:
    # Collapse any run of whitespace (double spaces, tabs, newlines) to a
    # single space before matching. Without this, a keyword like "ev charg"
    # silently fails to match text like "installation of EV  Charging
    # stations" (two spaces) — confirmed live on Telangana's portal, where
    # BeautifulSoup's get_text(" ", strip=True) joining adjacent text nodes
    # produces exactly that double space, so a genuine EV-charging tender
    # matched zero categories and would have been silently dropped entirely
    # (SHOW_ALL_TENDERS is off by default). Not portal-specific — any
    # source's markup could produce the same irregular spacing.
    title_l = " ".join(title.lower().split())
    if not any(term in title_l for term in GENERIC_GATE_TERMS):
        return []
    matched = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, title_l):
                matched.append(category)
                break
    # Passed the EV gate but no specific category's keywords: still a real
    # EV-charging tender, so keep it under a catch-all instead of dropping
    # it. Confirmed 2026-09-23 on TenderDetail: 31 of 50 "charging station"
    # results (e.g. "Electrical Infrastructure For Intermediate Charging
    # Station At Tuni Bus Station") matched the gate but no category.
    return matched or [FALLBACK_EV_CATEGORY]
