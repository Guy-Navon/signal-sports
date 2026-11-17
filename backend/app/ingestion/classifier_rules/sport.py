"""Sport detection: committed vocabulary, source hints, and club-name disambiguation."""

from typing import Optional

from app.classification.sport_guards import (
    committed_sport,
    has_bcl_abbreviation,
    has_shared_champions_league_name,
    is_unsupported_sport,
    shared_champions_league_sport,
)
from app.ingestion.classifier_rules.matching import _BASKETBALL_ONLY_SOURCES, _has
from app.taxonomy import entities_by_sport


# ── Hebrew sport disambiguation helpers ──────────────────────────────────────
# These are thin named wrappers that make the disambiguation logic in _detect_sport
# and _detect_entities transparent and independently testable.

# Defined ahead of the keyword sets they reference; the sets are declared just below.
# Python resolves the names at call time, not at function-definition time, so the
# forward references are safe as long as no one calls these before the sets exist.

def _has_football_maccabi_context(text: str) -> bool:
    """True if title names an explicit football Maccabi club.

    Must be called BEFORE the generic "מכבי" basketball check so that
    מכבי נתניה / מכבי חיפה etc. do not trigger basketball classification.
    """
    return _has(text, *_FOOTBALL_MACCABI_KW)


# Exact phrase forms for Maccabi Tel Aviv and Hapoel Tel Aviv.
# Titles using ONLY these full forms (without sport context words) are ambiguous
# and tagged ambiguous_club. Short standalone forms like "מכבי" do not match.
_MACCABI_TLV_KW = (
    "מכבי תל אביב",
    'מכבי ת"א',
    "מכבי ת״א",
    "maccabi tel aviv",
)
_HAPOEL_TLV_KW = (
    "הפועל תל אביב",
    'הפועל ת"א',
    "הפועל ת״א",
    "hapoel tel aviv",
)

# Context words that confirm basketball sport — used to resolve ambiguous club names.
_BASKETBALL_CTX_KW = (
    "כדורסל",                                    # basketball explicit
    "גארד", "פורוורד", "סנטר",                   # Hebrew basketball positions
    "guard", "forward", "center", "point guard",  # English basketball positions
    "יורוליג", "היורוליג",                        # EuroLeague in Hebrew
    "יורוקאפ",                                     # EuroCup in Hebrew
    "euroleague", "eurocup",                       # English league names
    "nba",
    "ווינר סל", "ליגת העל סל", "ליגת ווינר",     # Israeli Basketball League
    # Israeli basketball cups (#230) — mirror facts._COMPETITION_KEYWORDS; bare
    # "סופרקאפ" is excluded there for cross-sport/cross-country collisions.
    "גביע ווינר", "גביע וינר",
    "סופרקאפ החברתי", "סופר קאפ החברתי", "סופרקאפ הישראלי", "סופר קאפ הישראלי",
    "קטש", "עודד קטש", "kattash",                # Maccabi TLV head coach
    "הפועל חולון",                               # Hapoel Holon Basketball (unambiguous)
    # NOTE: "הפועל ירושלים" was removed here (taxonomy PR) — the club exists in
    # BOTH sports, so its name is an entity mention, not basketball evidence.
    # Treating it as basketball context forced football articles into basketball.
    "בני הרצליה",                                # Bnei Herzliya Basketball (unambiguous)
    "גמר סל",                                     # basketball final
    # Additional IBL clubs for disambiguation of Maccabi/Hapoel TLV articles
    "הפועל אילת",       # Hapoel Eilat Basketball (IBL)
    "גלבוע", "גלבוע עליון", "גלבוע גליל",  # Galil Gilboa Basketball (IBL)
    "עמק יזרעאל",       # Emek Yizrael Basketball (IBL)
    # Basketball stats and positions for disambiguation
    "רכז",              # point guard (Hebrew position name)
    "ריבאונדים",         # rebounds (basketball statistic)
    "חולון",            # Holon — short form of Hapoel Holon Basketball
)

# Context words that confirm football sport — used to resolve ambiguous club names.
_FOOTBALL_CTX_KW = (
    "כדורגל",                           # football explicit
    "חלוץ",                              # striker
    "בלם",                               # stopper/central defender
    "שוער",                              # goalkeeper
    "קשר",                               # midfielder
    "שער",                               # goal (football-specific in sports context)
    "בלומפילד",                          # Bloomfield Stadium (football only)
    "ליגת העל",                           # Israeli Premier League (football)
    # Transfer-fee vocabulary (issue #62): "דמי מעבר/דמי המעבר" is football-
    # typical in Israeli coverage (basketball uses באי-אאוט/דמי שחרור). Corpus
    # false-positive check: the only hits were the two misclassified football
    # Glazer articles (golden C2/C2-sibling). Risk: a rare basketball transfer
    # using the phrase would lean football — accepted; hint evidence (weight
    # 100) still outranks this context keyword wherever a URL category exists.
    "דמי מעבר", "דמי המעבר",
    "מונדיאל",                           # World Cup
    "fifa", "uefa",
    # "ליגת האלופות" / "champions league" are not here (#407): the name is shared with
    # the Basketball Champions League. _has_*_context() add it for the sport the text proves.
    "premier league",
    "bundesliga", "la liga", "serie a", "ligue 1",
)


def _has_maccabi_tel_aviv_phrase(text: str) -> bool:
    """True if title contains an explicit full-name Maccabi Tel Aviv form."""
    return _has(text, *_MACCABI_TLV_KW)


def _has_hapoel_tel_aviv_phrase(text: str) -> bool:
    """True if title contains an explicit full-name Hapoel Tel Aviv form."""
    return _has(text, *_HAPOEL_TLV_KW)


def _shared_name_context(text: str) -> Optional[str]:
    """The sport the shared "ליגת האלופות" name confirms in ``text`` (#407), or None."""
    if not has_shared_champions_league_name(text):
        return None
    return shared_champions_league_sport(text)


def _has_basketball_context(text: str) -> bool:
    """True if title contains words that confirm basketball sport."""
    return _has(text, *_BASKETBALL_CTX_KW) or _shared_name_context(text) == "basketball"


def _has_football_context(text: str) -> bool:
    """True if title contains words that confirm football sport."""
    return _has(text, *_FOOTBALL_CTX_KW) or _shared_name_context(text) == "football"


# ── Sport detection ───────────────────────────────────────────────────────────

_BASKETBALL_KW = (
    "basketball", "כדורסל", "nba", "euroleague", "eurocup", "יורוליג", "יורוקאפ",
    "acb", "bsl", "lba", "lnb",   # "bcl" is matched as a whole word (#407): _detect_sport
    # NOTE (issue #28): bare club-family names "מכבי" / "maccabi" were REMOVED here.
    # They are family markers, not sport evidence — a football מכבי story (מכבי חיפה,
    # or a bare "מכבי" whose subtitle says "שוער") must not be forced to basketball.
    # This was the last entity→basketball bias path; sport now comes from explicit
    # keywords / competitions / evidence-weighted resolution. Full-name Maccabi TLV
    # forms are still handled (with sport context) via _MACCABI_TLV_KW.
    "ווינר סל", "ליגת העל סל",  # Israeli Basketball League explicit markers
    # Israeli basketball clubs — allow sport inference without "כדורסל" keyword
    "בני הרצליה",               # Bnei Herzliya basketball
    # Oded Kattash — Maccabi Tel Aviv head coach; his name alone is a strong basketball signal
    "קטש", "עודד קטש", "kattash", "oded kattash",
    # Hebrew NBA team nicknames (not city names — those are too generic)
    "וויזארדס", "הורנטס", "בלייזרס", "ניקס", "סלטיקס", "לייקרס",
    "באקס", "סאנס", "נאגטס", "מאברס", "ספרס", "רוקטס", "ראפטורס", "גריזליס",
    "mvp",  # unambiguously basketball in Israeli sports context
    # Israeli Basketball League clubs — direct sport detection without "כדורסל" keyword
    "גלבוע", "גלבוע גליל", "גלבוע עליון",  # Galil Gilboa Basketball (IBL)
    "עמק יזרעאל",  # Emek Yizrael Basketball (IBL)
    "הפועל אילת",  # Hapoel Eilat Basketball (IBL)
    # NBA star names (Hebrew) — unambiguous basketball signal
    "לברון", "לברון ג'יימס",  # LeBron James
)
_FOOTBALL_KW = (
    "football", "soccer", "כדורגל", "fifa", "uefa",
    "premier league", "la liga",
    "bundesliga", "serie a", "ligue 1",
    "מונדיאל",                  # World Cup in Hebrew
    # Israeli football clubs — unambiguously football
    'בית"ר', "בית״ר",           # Beitar Jerusalem
    "הפועל באר שבע",            # Hapoel Beer Sheva (football)
    # Note: הפועל תל אביב forms are NOT here — they are disambiguated explicitly
    # in _detect_sport because הפועל תל אביב also refers to a basketball club.
    # Football-specific positions — direct sport detection when no club name present
    "חלוץ",    # striker (football position, also already in _FOOTBALL_CTX_KW)
    "שוער",    # goalkeeper
)

# Maccabi clubs that are FOOTBALL — must be checked BEFORE _BASKETBALL_KW
# because "מכבי" appears in _BASKETBALL_KW and would win the sport check first.
# Derived from the taxonomy registry (single source of entity truth): every
# football club in the מכבי family whose alias is not shared with a basketball
# entity (which excludes the ambiguous "מכבי תל אביב" forms).
def _derive_football_maccabi_kw() -> tuple[str, ...]:
    basketball_aliases = {
        a.lower() for e in entities_by_sport("basketball") for a in e.aliases
    }
    kw: list[str] = []
    for entity in entities_by_sport("football"):
        if entity.family != "מכבי":
            continue
        for alias in entity.aliases:
            lowered = alias.lower()
            if lowered not in basketball_aliases and lowered not in kw:
                kw.append(lowered)
    return tuple(kw)


_FOOTBALL_MACCABI_KW = _derive_football_maccabi_kw()
_TENNIS_KW = (
    "tennis", "טניס", "wimbledon", "וימבלדון",
    "roland garros", "רולאן גארוס", "french open",
    "us open", "australian open",
    "grand slam", "גראנד סלאם",
    "atp", "wta",
    "אליפות אוסטרליה",              # Australian Open in Hebrew
    'ארה"ב הפתוחה', 'ארה״ב הפתוחה', # US Open in Hebrew
    # Top players whose names strongly imply tennis context
    "אלקאראז", "אלקראס",            # Alcaraz
    "ג'וקוביץ", "ג׳וקוביץ",         # Djokovic
    "סינר",                          # Sinner
)

# "גראנד סלאם" is also a judo tour (IJF Grand Slam) — #225: "מדליית גראנד סלאם ראשונה
# לכרם פרימו" was classified tennis. A tennis slam awards no medals, so the phrase is
# tennis evidence only without judo/medal context. Every other tennis keyword is kept.
_GRAND_SLAM_PHRASES = ("grand slam", "גראנד סלאם")
_NON_TENNIS_SLAM_CONTEXT = ("ג'ודו", "ג׳ודו", "ג'ודא", "ג׳ודא", "judo", "מדלי", "medal", "פודיום")


def tennis_keywords_for(text: str) -> tuple[str, ...]:
    """The tennis sport keywords that count as evidence for this (lowercased) text."""
    if any(ctx in text for ctx in _NON_TENNIS_SLAM_CONTEXT):
        return tuple(kw for kw in _TENNIS_KW if kw not in _GRAND_SLAM_PHRASES)
    return _TENNIS_KW


def _detect_sport(text: str, source_id: str, source_sport_hint: str | None = None) -> str:
    # Unsupported domain (issue #113) — MMA/UFC/boxing are not modelled by the taxonomy.
    # Abstain rather than guess: a wrong sport propagates into visibility, preference
    # matching and push. Checked FIRST, ahead of even the source hint — a UFC report filed
    # under a section hint is still not a sport we model.
    if is_unsupported_sport(text):
        return "unknown"
    # Committed, unambiguous sport vocabulary (issue #113). Checked BEFORE the source hint:
    # a hint may FILL a missing sport, but it must never override strong contradictory
    # evidence in the text itself. A football report filed under a basketball section is
    # still a football report, and the URL is the weaker signal.
    _committed = committed_sport(text)
    if _committed is not None:
        return _committed
    # Source URL category hint (e.g. Israel Hayom /sport/israeli-basketball/).
    if source_sport_hint:
        return source_sport_hint
    if source_id in _BASKETBALL_ONLY_SOURCES:
        return "basketball"
    if _has(text, *tennis_keywords_for(text)):
        return "tennis"
    # Explicit football Maccabi clubs must be checked before the Maccabi TLV
    # phrase check — מכבי נתניה / מכבי חיפה etc. are definitively football.
    if _has_football_maccabi_context(text):
        return "football"
    # Maccabi Tel Aviv (full-name form): requires sport context to resolve.
    # False positives are worse than misses — only classify when confident.
    if _has_maccabi_tel_aviv_phrase(text):
        if _has_basketball_context(text):
            return "basketball"
        if _has_football_context(text):
            return "football"
        return "unknown"  # ambiguous_club — tagged in classify()
    # Hapoel Tel Aviv (full-name form): requires sport context to resolve.
    if _has_hapoel_tel_aviv_phrase(text):
        if _has_basketball_context(text):
            return "basketball"
        if _has_football_context(text):
            return "football"
        return "unknown"  # ambiguous_club — tagged in classify()
    # Generic keyword fallback (handles standalone "מכבי", English sources, etc.)
    if _has(text, *_BASKETBALL_KW) or has_bcl_abbreviation(text):
        return "basketball"
    if _has(text, *_FOOTBALL_KW):
        return "football"
    return "unknown"
