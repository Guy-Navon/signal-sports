"""
Language detection for RSS article titles and URLs.

Detection priority:
  1. URL path segment (e.g. /it/, /el/, /tr/)
  2. Unicode script of the title characters (Hebrew, Greek, Cyrillic)
  3. Source config default (caller-supplied fallback)
"""

from typing import Optional

_URL_LANG_MAP: dict[str, str] = {
    "/he/": "he",
    "/en/": "en",
    "/it/": "it",
    "/el/": "el",
    "/tr/": "tr",
    "/es/": "es",
    "/fr/": "fr",
    "/de/": "de",
    "/pt/": "pt",
    "/ru/": "ru",
    "/sr/": "sr",
    "/pl/": "pl",
    "/cs/": "cs",
    "/nl/": "nl",
}

# Unicode codepoint ranges for script detection
_HE_START, _HE_END = 0x0590, 0x05FF
_GREEK_START, _GREEK_END = 0x0370, 0x03FF
_CYRILLIC_START, _CYRILLIC_END = 0x0400, 0x04FF


def detect_from_url(url: str) -> Optional[str]:
    """Return ISO 639-1 code inferred from a URL path segment, or None."""
    url_lower = url.lower()
    for path, lang in _URL_LANG_MAP.items():
        if path in url_lower:
            return lang
    return None


def detect_from_text(text: str) -> Optional[str]:
    """Return ISO 639-1 code inferred from Unicode script of the text, or None.

    Checks only the first 40 characters to keep it fast.
    Returns the script whose characters appear most in that window.
    Falls back to None when no strong signal is found.
    """
    sample = text[:40]
    he_count = gr_count = cy_count = 0
    for ch in sample:
        cp = ord(ch)
        if _HE_START <= cp <= _HE_END:
            he_count += 1
        elif _GREEK_START <= cp <= _GREEK_END:
            gr_count += 1
        elif _CYRILLIC_START <= cp <= _CYRILLIC_END:
            cy_count += 1

    if he_count > 0 and he_count >= gr_count and he_count >= cy_count:
        return "he"
    if gr_count > 0 and gr_count >= he_count and gr_count >= cy_count:
        return "el"
    if cy_count > 0:
        return "ru"
    return None


def detect_language(url: str, title: str, default: str) -> str:
    """Detect the language of an article.

    Args:
        url:     Article URL — checked for language path segments first.
        title:   Article title — checked for Unicode script signals second.
        default: Fallback when both checks are inconclusive (typically the
                 source config language).

    Returns:
        ISO 639-1 language code string.
    """
    lang = detect_from_url(url)
    if lang is not None:
        return lang
    lang = detect_from_text(title)
    if lang is not None:
        return lang
    return default
