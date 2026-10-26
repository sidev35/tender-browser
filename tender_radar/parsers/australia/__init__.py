"""Australia: one parser per state portal."""

from .tasmania import parse_tas_tenders
from .victoria import parse_vic_tenders  # also reads Tenders ACT (same platform)

__all__ = ["parse_tas_tenders", "parse_vic_tenders"]
