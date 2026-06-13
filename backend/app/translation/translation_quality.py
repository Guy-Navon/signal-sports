"""
Translation quality guardrails.

Runs after a provider returns a result to catch common failure modes:
empty output, unchanged text, model commentary, or output that contains
mostly Latin characters (model returned the original instead of translating).
"""

import unicodedata

_EXPLANATION_PREFIXES = (
    "הנה התרגום",
    "תרגום:",
    "הכותרת בעברית",
    "הכותרת המתורגמת",
    "here is",
    "here's",
    "translation:",
    "translated:",
)

# If the Latin-letter fraction in the result exceeds this threshold the model
# likely returned the original text rather than a Hebrew translation.
_MAX_LATIN_RATIO = 0.6

# If the translated title is more than this multiple of the original length,
# the model likely added explanation text alongside the headline.
_MAX_LENGTH_RATIO = 3.0


def latin_ratio(text: str) -> float:
    """Return the fraction of Unicode letters that are Latin script."""
    letters = [c for c in text if unicodedata.category(c).startswith("L")]
    if not letters:
        return 0.0
    latin_count = sum(
        1 for c in letters
        if unicodedata.name(c, "").startswith("LATIN")
    )
    return latin_count / len(letters)


def contains_model_explanation(text: str) -> bool:
    """Return True if the text opens with a known model commentary phrase."""
    lowered = text.strip().lower()
    return any(lowered.startswith(p.lower()) for p in _EXPLANATION_PREFIXES)


def looks_like_hebrew_translation(translated: str, original: str) -> bool:
    """Return True if *translated* looks like a valid Hebrew headline.

    Rejects:
    - empty or whitespace-only string
    - identical to the original (no translation occurred)
    - starts with model explanation text
    - predominantly Latin characters
    - suspiciously long compared to the original
    """
    if not translated or not translated.strip():
        return False
    if translated.strip() == original.strip():
        return False
    if contains_model_explanation(translated):
        return False
    if latin_ratio(translated) > _MAX_LATIN_RATIO:
        return False
    if original and len(translated) > len(original) * _MAX_LENGTH_RATIO:
        return False
    return True
