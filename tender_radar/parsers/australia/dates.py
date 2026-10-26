"""Date helper shared by the Australian portal parsers."""

import re
from datetime import datetime


def iso(text: str, fmt: str, pattern: str) -> str | None:
    """Finds `pattern` in text and returns it as yyyy-mm-dd (read with `fmt`), or None."""
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), fmt).strftime("%Y-%m-%d")
    except ValueError:
        return None
