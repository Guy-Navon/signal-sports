"""
Committed sport evidence + unsupported-domain abstention (issue #113).

Two deterministic guards, both born from the #102 corpus QA, where near-identical
cross-source reports of the SAME story received contradictory sport facts:

1. COMMITTED SPORT VOCABULARY — "deterministic evidence first" was not actually enforced
   for sport. ``merge.py`` guardrail 2 only overrides the LLM when the LLM says *unknown*;
   if the rules resolved a sport and the LLM disagreed, **the LLM silently won**. So an
   article whose subtitle says "נבחרת העתודה … נבחרה ל**חמישיית הטורניר** … ב**אסיסטים**"
   (unmistakably basketball) was classified **football** because the LLM guessed football
   and nothing contradicted it. The words below are unambiguous, single-sport terms: when
   one is present, an LLM guess for the other sport is wrong by construction.

2. UNSUPPORTED DOMAIN — the taxonomy tracks basketball, football and tennis. It does NOT
   track MMA/UFC. Faced with a UFC report the LLM invented **football** (its own reason
   read: *"Football match result between Conor McGregor and Max Holloway in UFC"*), and
   two sources disagreed on the same fight. The correct behaviour for a sport we do not
   model is **abstention** (``sport="unknown"``), not a guess — abstention beats a wrong
   fact, and a wrong sport propagates into visibility, preference matching and push.

These lists are deliberately SMALL and high-precision. A term earns its place only if it
cannot plausibly appear in the other sport's coverage.
"""

# ── Committed basketball vocabulary ──────────────────────────────────────────
# Terms with no football usage. Deliberately EXCLUDED because they are shared:
#   "אסיסטים"/"אסיסט" (assists exist in football), "נקודות" (league points),
#   "גמר"/"אליפות" (any sport), "סנטר" (a football cross), "מדד".
_COMMITTED_BASKETBALL: tuple[str, ...] = (
    "כדורסל", "basketball",
    "יורוליג", "היורוליג", "euroleague", "יורוקאפ", "eurocup",
    "nba", "אן.בי.איי",
    "ריבאונד", "ריבאונדים", "rebound", "rebounds",
    "חמישיית הטורניר", "חמישיית העונה", "חמישייה הראשונה",
    "שלשות", "שלשה מהפינה", "three-pointer",
    "טריפל דאבל", "דאבל דאבל", "triple double",
    "ליגת ווינר", "ווינר סל", "ליגת העל בכדורסל",
    "הפגיז מהקשת",   # "מהקשת" alone is too generic ("קשת" = bow/arc/rainbow)
)

# ── Committed football vocabulary ────────────────────────────────────────────
# Kept intentionally narrow: only terms that cannot describe a basketball event.
_COMMITTED_FOOTBALL: tuple[str, ...] = (
    "כדורגל", "football", "soccer",
    "מונדיאל", "world cup",
    "ליגת האלופות", "champions league",
    "פנדל", "פנדלים", "penalty kick",
    "בעיטה חופשית", "offside",
    # REMOVED after a real false positive: "קרן" (corner kick) also means fund/ray/horn AND
    # is a SUBSTRING of "שקרן" (liar) — it turned a Maccabiah bar-mitzvah story and a
    # police-transcript story into FOOTBALL. "נבדל" (offside) is likewise the ordinary word
    # for "differs". A 3-letter token is far too dangerous for a substring scanner; a
    # committed term must be unambiguous AND substring-safe.
    "שוער", "goalkeeper",
    "פיפ\"א", "fifa", "uefa",
)

# ── Unsupported domains — must ABSTAIN, never guess ──────────────────────────
# Sports the taxonomy does not model. Presence of any of these means we cannot prove a
# supported sport, so the sport is unknown. (This does NOT hide the article; it only
# refuses to assert a sport we cannot support.)
_UNSUPPORTED_DOMAIN: tuple[str, ...] = (
    "ufc", "mma", "אם.אם.איי",
    "אמנויות לחימה", "קרב אלוף", "אוקטגון", "octagon",
    "איגרוף", "boxing", "מתאגרף",
)


def _has(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def has_committed_basketball(text: str) -> bool:
    """Unambiguous basketball evidence — an LLM 'football' guess against this is wrong."""
    return _has(text, _COMMITTED_BASKETBALL)


def has_committed_football(text: str) -> bool:
    """Unambiguous football evidence."""
    return _has(text, _COMMITTED_FOOTBALL)


def is_unsupported_sport(text: str) -> bool:
    """True for domains the taxonomy does not model (MMA/UFC/boxing) → abstain."""
    return _has(text, _UNSUPPORTED_DOMAIN)


def committed_sport(text: str) -> str | None:
    """The sport proven by committed vocabulary, or None.

    Returns None when BOTH sports' vocabulary is present — that is genuine ambiguity, and
    abstention (leaving the existing decision alone) beats picking a side.
    """
    if is_unsupported_sport(text):
        return None
    bb = has_committed_basketball(text)
    fb = has_committed_football(text)
    if bb and not fb:
        return "basketball"
    if fb and not bb:
        return "football"
    return None
