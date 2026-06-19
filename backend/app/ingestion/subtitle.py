"""
Subtitle extraction and cleaning for RSS feed entries.
Provides extra context to the LLM classifier beyond the headline alone.
"""

import html
import re
from typing import Optional


def extract_subtitle(entry) -> Optional[str]:
    """
    Extract the best available subtitle/summary from a feedparser entry.
    Priority: summary > description > subtitle > content[0].value
    Returns cleaned text, or None if nothing useful is found.
    """
    raw: Optional[str] = None

    for attr in ("summary", "description", "subtitle"):
        candidate = getattr(entry, attr, None)
        if candidate:
            raw = candidate
            break

    if not raw:
        content = getattr(entry, "content", None)
        if content and isinstance(content, list):
            first = content[0]
            raw = first.get("value") if isinstance(first, dict) else None

    if not raw:
        return None

    return clean_subtitle(raw)


def clean_subtitle(text: str, max_chars: int = 500) -> Optional[str]:
    """
    Strip HTML tags, unescape entities, collapse whitespace, truncate.
    Returns None if the result is empty after cleaning.
    """
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:max_chars]
