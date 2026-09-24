"""
Small helpers that turn a parsed row's raw text into clean record fields:
the tender's id, due date, title and value.
"""

import hashlib
import re
from datetime import datetime

from .models import Source


def make_stable_id(source_name: str, title: str) -> str:
    """
    Government listings rarely give us a clean, guaranteed-unique reference
    number in a consistent spot, so we derive a stable id from the source +
    title text. Same tender text on a later run -> same id -> no duplicate
    added to the persistent data file. If the source text changes slightly
    between runs (e.g. a corrigendum edits the title), it will show up as a
    "new" entry — reviewing occasional near-duplicates by eye is a fair
    trade-off for not needing fragile per-portal reference-number parsing.
    """
    h = hashlib.sha1(f"{source_name}::{title}".encode()).hexdigest()[:10]
    return f"AUTO-{h}"


def extract_due_date(row_text: str) -> str | None:
    """Best-effort extraction of a closing/due date from a raw table row."""
    # ISO format (yyyy-mm-dd, optionally with a time) — seen on Bihar's
    # eProc 2.0 portal (js_interactive_search source), unlike GePNIC's
    # dd-Mon-yyyy / dd/mm/yyyy. Checked first since it's the most specific
    # pattern (4-digit year first is unambiguous, unlike 2-digit-year
    # dd/mm/yyyy which could theoretically collide with other formats).
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", row_text)
    if m:
        year, mon, day = m.groups()
        try:
            return datetime.strptime(f"{year}-{mon}-{day}", "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass  # fall through to the other patterns below
    m = re.search(r"(\d{1,2})[-/]([A-Za-z]{3})[-/](\d{2,4})", row_text)
    if m:
        day, mon, year = m.groups()
        year = ("20" + year) if len(year) == 2 else year
        try:
            return datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", row_text)
    if m:
        day, mon, year = m.groups()
        year = ("20" + year) if len(year) == 2 else year
        try:
            return datetime.strptime(f"{day}-{mon}-{year}", "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def days_until(date_str: str | None) -> int | None:
    """Days from today until a "yyyy-mm-dd" date (negative if past), or None."""
    if not date_str:
        return None
    try:
        due = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return (due.date() - datetime.now().date()).days


def clean_title(source: Source, raw_title: str) -> str:
    """
    Applies the source's optional "titleRegex" (sources.json): a regex whose
    first group is the real tender title inside a longer cell. Needed where a
    portal packs several fields into one cell — confirmed on Gujarat
    nProcure, whose "Tender Brief" cell reads "VMC-Water works Tender Id
    :345346 Name Of Work : <title> Corrigendum : ... Estimated Contract
    Value : ... Last Date & Time For Submission : ...". Falls back to the
    raw text when the source has no titleRegex or it doesn't match.
    """
    pattern = source.get("titleRegex")
    if pattern:
        m = re.search(pattern, raw_title, re.IGNORECASE | re.DOTALL)
        if m and m.group(1).strip():
            raw_title = m.group(1)
    return " ".join(raw_title.split())


def extract_value(source: Source, raw_row: str) -> str | None:
    """
    Applies the source's optional "valueRegex" (sources.json): a regex whose
    first group is a plain rupee amount in the row text (e.g. Gujarat
    nProcure's "Estimated Contract Value : 25481341.00"), formatted the way
    TenderDetail shows values ("₹2.55 Cr", "₹26.09 Lakh"). None when the
    source has no valueRegex, it doesn't match, or the amount is 0 (nProcure
    uses 0.00 for "not disclosed").
    """
    pattern = source.get("valueRegex")
    m = re.search(pattern, raw_row, re.IGNORECASE) if pattern else None
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if amount <= 0:
        return None
    if amount >= 1e7:
        return f"₹{amount / 1e7:.2f} Cr"
    if amount >= 1e5:
        return f"₹{amount / 1e5:.2f} Lakh"
    return f"₹{amount:,.0f}"
