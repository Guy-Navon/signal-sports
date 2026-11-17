"""Keyword-match helpers and source defaults shared by every rule family."""

import re


# ── Sources that produce only basketball content ──────────────────────────────

# Hebrew sources are general sports (not basketball-only) — do NOT include walla_sport here.
_BASKETBALL_ONLY_SOURCES = frozenset({"eurohoops", "sportando"})


# ── Keyword helpers ───────────────────────────────────────────────────────────

def _has(text: str, *keywords: str) -> bool:
    return any(kw in text for kw in keywords)


def _has_word(text: str, word: str) -> bool:
    """Word-boundary match — avoids 'sign' matching 'signal'."""
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))
