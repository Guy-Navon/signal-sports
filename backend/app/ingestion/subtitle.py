"""
Subtitle extraction and cleaning for RSS feed entries.
Provides extra context to the LLM classifier beyond the headline alone, and
is displayed in the Feed/Debug UI as a short excerpt under the headline.
"""

import html
import re
from typing import Optional

# A sentence end is punctuation followed by whitespace or end-of-string —
# this deliberately excludes decimals like "1.88" (period followed by a
# digit, not whitespace), so cutting never lands inside a number.
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")

# Below this, a "sentence boundary" cut would be a degenerate first word or
# two; prefer the hard character cut instead.
_MIN_SENTENCE_CUT = 20


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


def clean_subtitle(text: str, max_chars: int = 240) -> Optional[str]:
    """
    Strip HTML tags, unescape entities, collapse whitespace, and trim to a
    short excerpt (roughly the first one or two sentences, up to max_chars).

    Many RSS feeds put the article's opening paragraph in <description>
    rather than a hand-written deck — a blunt character cut left the
    excerpt reading like unfinished body text. When a sentence boundary
    exists inside the budget, cut there instead; otherwise fall back to a
    hard cut at max_chars.

    Returns None if the result is empty after cleaning.
    """
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    matches = list(_SENTENCE_END_RE.finditer(window))
    if matches and matches[-1].end() >= _MIN_SENTENCE_CUT:
        return window[: matches[-1].end()]
    return window
