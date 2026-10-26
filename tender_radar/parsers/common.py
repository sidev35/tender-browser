"""Pieces shared by parsers of more than one country."""

import re

# "Corrigendum : ...", "Corrigendum - ..." and "Corrigendum Tender For ...": an amended tender is
# listed under its own title with this prefix in front, which isn't part of the title.
CORRIGENDUM_PREFIX = re.compile(r"^\s*corrigendum\b\s*[:\-–]?\s*", re.IGNORECASE)
