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

3. A SHARED COMPETITION NAME (#407) — "ליגת האלופות" / "champions league" names both the
   UEFA Champions League and the FIBA Basketball Champions League, so it fails the rule above
   and is not committed vocabulary by itself. It takes the sport the text proves through a
   named basketball entity or a basketball scoreline (``basketball_named_cue``), and is
   football otherwise: 65 of the 72 corpus rows that say it were football.
"""

import re
from typing import Optional

from app.taxonomy import resolve_entities
from app.taxonomy.resolver import normalize_alias_text

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
    # The Basketball Champions League by a name no football competition has (#407).
    # "bcl" is left out: a 3-letter token is not substring-safe (has_bcl_abbreviation).
    'ליגת האלופות של פיב"א', "ליגת האלופות של פיב״א", "ליגת האלופות של פיבא",
    "basketball champions league", "fiba champions league",
)

# ── Committed football vocabulary ────────────────────────────────────────────
# Kept intentionally narrow: only terms that cannot describe a basketball event.
_COMMITTED_FOOTBALL: tuple[str, ...] = (
    "כדורגל", "football", "soccer",
    "מונדיאל", "world cup",
    # "ליגת האלופות" / "champions league" are NOT here (#407): the Basketball Champions
    # League shares the name. See SHARED_CHAMPIONS_LEAGUE_NAMES below.
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


# ── A competition name shared by two sports (#407) ───────────────────────────
SHARED_CHAMPIONS_LEAGUE_NAMES: tuple[str, ...] = ("ליגת האלופות", "champions league")

# A basketball scoreline: "A:B", both sides 50-199 and different (#345). Football and tennis
# never get there; handball tops out in the 40s ("21:43"); a kick-off time has an hour below
# 24 ("19:30"); a game cannot end level, and "50:50" reports odds. Colon only, because a
# hyphen also writes ranges ("60-70 אלף"); a colon wrapped in RTL marks
# ("87\u200f:\u200f92") does not match either, a fail-safe miss.
_BASKETBALL_SCORELINE = re.compile(r"(?<![\d:.,])(\d{2,3}):(\d{2,3})(?![\d:])")


def has_basketball_scoreline(text: str) -> bool:
    pairs = ((int(a), int(b)) for a, b in _BASKETBALL_SCORELINE.findall(text))
    return any(50 <= a <= 199 and 50 <= b <= 199 and a != b for a, b in pairs)


def names_its_sport(ent, text_norm: str, multiword_people: bool = False) -> bool:
    """A self-resolved entity proves its sport: a person by name; a team only
    through a multi-word alias present in the text (#345). One-word team aliases are
    substring hits on town names and nicknames ("באילת" = Hapoel Eilat's town, "ספרס" =
    Tottenham in football copy, "העמק" inside "מגדל העמק"), so they prove nothing.

    ``multiword_people`` holds a person to the same multi-word rule (#407): a one-word
    person alias can be a substring hit too ("deni" inside "denied", #415)."""
    if ent.kind != "team" and not multiword_people:
        return True
    return any(
        " " in alias and alias in text_norm
        for alias in (normalize_alias_text(a) for a in ent.aliases)
    )


def basketball_named_cue(
    text: str, extra_entities=(), multiword_people: bool = False,
) -> Optional[str]:
    """A deterministic basketball cue the text itself carries (None if there is none):
    a basketball entity the resolver finds with NO sport context, named in a form that
    proves its sport, or a basketball scoreline.

    Any entity of another sport the text names (or that the caller passes in
    ``extra_entities``) is a contradiction, and then nothing is a cue.
    ``multiword_people``: see ``names_its_sport``.
    """
    self_resolved = resolve_entities(text, None).resolved
    named = [ent for ent in (*self_resolved, *extra_entities) if ent is not None]
    if any(ent.sport != "basketball" for ent in named):
        return None
    text_norm = normalize_alias_text(text)
    for ent in self_resolved:
        if ent.sport == "basketball" and names_its_sport(ent, text_norm, multiword_people):
            return f"text_entity:{ent.id}"
    if has_basketball_scoreline(text):
        return "basketball_scoreline"
    return None


def has_shared_champions_league_name(text: str) -> bool:
    return _has(text, SHARED_CHAMPIONS_LEAGUE_NAMES)


# "BCL" as a whole Latin word ("ב-BCL", "the BCL"), never inside one ("abcl"). A 3-letter
# token is not substring-safe, so it is matched with boundaries and kept out of the
# committed vocabulary.
_BCL_ABBREVIATION = re.compile(r"(?<![a-z0-9])bcl(?![a-z0-9])")


def has_bcl_abbreviation(text: str) -> bool:
    return _BCL_ABBREVIATION.search(text.lower()) is not None


# The only VOCABULARY that reads the shared name as basketball: the qualified FIBA names
# and the sport's own name. Other committed basketball words are not enough: football copy
# says "כבש מריבאונד" (scored from a rebound). Everything else goes through
# basketball_named_cue, which checks for a contradicting entity.
_SHARED_NAME_BASKETBALL_VOCABULARY: tuple[str, ...] = (
    'ליגת האלופות של פיב"א', "ליגת האלופות של פיב״א", "ליגת האלופות של פיבא",
    "basketball champions league", "fiba champions league",
    "כדורסל", "basketball",
)


def shared_champions_league_sport(text: str) -> str:
    """The sport the bare "ליגת האלופות" / "champions league" names in ``text``.

    Basketball when the text proves basketball: a qualified FIBA name or the word
    basketball, with no committed football vocabulary; or a named basketball cue (a
    multi-word basketball name or a basketball scoreline, and no other-sport entity).
    Football otherwise: the corpus prior, and the safe side for a user who follows
    basketball (a wrong basketball reading would leak a UEFA story into basketball
    interests).
    """
    lowered = text.lower()
    if _has(lowered, _SHARED_NAME_BASKETBALL_VOCABULARY) and not has_committed_football(lowered):
        return "basketball"
    if basketball_named_cue(lowered, multiword_people=True) is not None:
        return "basketball"
    return "football"


def committed_sport(text: str) -> str | None:
    """The sport proven by committed vocabulary, or None.

    Returns None when BOTH sports' vocabulary is present — that is genuine ambiguity, and
    abstention (leaving the existing decision alone) beats picking a side. A shared
    competition name (#407) counts for the sport ``shared_champions_league_sport`` gives it.
    """
    if is_unsupported_sport(text):
        return None
    bb = has_committed_basketball(text)
    fb = has_committed_football(text)
    if has_shared_champions_league_name(text):
        if shared_champions_league_sport(text) == "basketball":
            bb = True
        else:
            fb = True
    if bb and not fb:
        return "basketball"
    if fb and not bb:
        return "football"
    return None
