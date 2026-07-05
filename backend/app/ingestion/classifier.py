"""
Deterministic keyword-based article classifier.

No LLM. No external calls. Fully testable as a pure function.

Design notes:
- Primary signal is the article title. Optional subtitle fills gaps when title is
  ambiguous or produces sport=unknown / no entities / generic event_type="news".
- Subtitle never overrides an already-resolved sport value from the title.
- Optional url is used for URL-path-based league inference (e.g. EuroCup vs EuroLeague).
- Hebrew and English keywords live in the same lists; lowercased before matching.
- Source ID is used to apply basketball-only defaults for Eurohoops/Sportando.
- Confidence is additive: each matched signal contributes a fixed increment.
- When unsure, sport="unknown", event_type="news", confidence<=0.5.
"""

import re
from dataclasses import dataclass
from typing import Optional

from app.taxonomy import (
    EntityResolution,
    entities_by_sport,
    entity_by_id,
    legacy_sport,
    resolve_entities,
)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    sport: str                  # basketball | football | tennis | unknown
    league: Optional[str]       # NBA | EuroLeague | EuroCup | Israeli Basketball League | …
    entities: list[str]         # Maccabi Tel Aviv Basketball | Deni Avdija | …
    event_type: str             # signing | negotiation | injury | … | news
    importance: str             # very_low | low | medium | high | very_high
    confidence: float           # 0.0 – 1.0
    tags: list[str]             # keyword hits for debugging / display


# ── Sources that produce only basketball content ──────────────────────────────

# Hebrew sources are general sports (not basketball-only) — do NOT include walla_sport here.
_BASKETBALL_ONLY_SOURCES = frozenset({"eurohoops", "sportando"})


# ── Keyword helpers ───────────────────────────────────────────────────────────

def _has(text: str, *keywords: str) -> bool:
    return any(kw in text for kw in keywords)


def _has_word(text: str, word: str) -> bool:
    """Word-boundary match — avoids 'sign' matching 'signal'."""
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))


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


def _has_kattash_context(text: str) -> bool:
    """True if title references Oded Kattash — a strong Maccabi TLV basketball signal."""
    return _has(text, "קטש", "עודד קטש", "kattash", "oded kattash")


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
    "מונדיאל",                           # World Cup
    "fifa", "uefa",
    "champions league", "ליגת האלופות",
    "premier league",
    "bundesliga", "la liga", "serie a", "ligue 1",
)


def _has_maccabi_tel_aviv_phrase(text: str) -> bool:
    """True if title contains an explicit full-name Maccabi Tel Aviv form."""
    return _has(text, *_MACCABI_TLV_KW)


def _has_hapoel_tel_aviv_phrase(text: str) -> bool:
    """True if title contains an explicit full-name Hapoel Tel Aviv form."""
    return _has(text, *_HAPOEL_TLV_KW)


def _has_basketball_context(text: str) -> bool:
    """True if title contains words that confirm basketball sport."""
    return _has(text, *_BASKETBALL_CTX_KW)


def _has_football_context(text: str) -> bool:
    """True if title contains words that confirm football sport."""
    return _has(text, *_FOOTBALL_CTX_KW)


def _has_hapoel_tel_aviv_basketball_context(text: str) -> bool:
    return _has_hapoel_tel_aviv_phrase(text) and _has_basketball_context(text)


def _has_hapoel_tel_aviv_football_context(text: str) -> bool:
    return _has_hapoel_tel_aviv_phrase(text) and _has_football_context(text)


# ── Sport detection ───────────────────────────────────────────────────────────

_BASKETBALL_KW = (
    "basketball", "כדורסל", "nba", "euroleague", "eurocup", "יורוליג", "יורוקאפ",
    "acb", "bsl", "lba", "lnb",
    "maccabi", "מכבי",          # almost always basketball
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
    "champions league", "premier league", "la liga",
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


def _detect_sport(text: str, source_id: str, source_sport_hint: str | None = None) -> str:
    # Source URL category hint (e.g. Israel Hayom /sport/israeli-basketball/) — highest priority.
    if source_sport_hint:
        return source_sport_hint
    if source_id in _BASKETBALL_ONLY_SOURCES:
        return "basketball"
    if _has(text, *_TENNIS_KW):
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
    if _has(text, *_BASKETBALL_KW):
        return "basketball"
    if _has(text, *_FOOTBALL_KW):
        return "football"
    return "unknown"


# ── League detection ──────────────────────────────────────────────────────────

# EuroCup must be checked before EuroLeague: some titles mention "Euroleague"
# while covering EuroCup news, and the URL or title keyword "eurocup" is authoritative.
_EUROCUP_KW = ("eurocup", "euro cup", "fiba europe cup", "יורוקאפ")

_NBA_DIRECT_KW = ("nba", "אן.בי.איי")
_NBA_TEAM_KW = (
    "celtics", "heat", "lakers", "warriors", "bulls", "nets", "knicks",
    "bucks", "76ers", "suns", "nuggets", "clippers", "mavericks", "mavs",
    "spurs", "rockets", "thunder", "blazers", "trail blazers", "raptors",
    "magic", "pistons", "cavaliers", "pacers", "hawks", "hornets", "wizards",
    "grizzlies", "timberwolves", "jazz", "pelicans", "kings",
    "סלטיקס", 'הית"', "לייקרס", "בולס", "נטס", "ניקס", "באקס",
    "סאנס", "נאגטס", "מאברס", "ספרס", "רוקטס", "בלייזרס", "ראפטורס",
    "וויזארדס", "הורנטס", "גריזליס",
    # Additional Hebrew NBA team names (spec PR 8)
    "וושינגטון",    # Washington Wizards
    "פורטלנד",      # Portland Trail Blazers
    "שארלוט",       # Charlotte Hornets
    # NBA star names (Hebrew) — infer NBA when no team name in title
    "לברון", "לברון ג'יימס",  # LeBron James
)
_EUROLEAGUE_KW = ("euroleague", "יורוליג", "היורוליג")
# Direct textual mentions of the Israeli Basketball League.
# "הפועל תל אביב" is included here because, once sport is already resolved to
# basketball, an article naming Hapoel Tel Aviv must be about their basketball
# club — which plays in the Israeli Basketball League (or EuroLeague, but that
# is checked first and wins if the EuroLeague keyword is present).
_ISRAELI_BBALL_DIRECT_KW = (
    "ליגת ווינר", "ליגת העל בכדורסל", "ליגה לאומית",
    "ווינר סל", "ליגת העל סל",
    "winner league", "ligat winner",
    "israeli basketball league", "super league basketball",
    "הפועל תל אביב",   # Hapoel Tel Aviv basketball club — Israeli Basketball League
    # IBL clubs — when seen in basketball-resolved context, implies Israeli Basketball League
    "בני הרצליה",      # Bnei Herzliya Basketball
    "הפועל חולון",     # Hapoel Holon Basketball
    "הפועל ירושלים",   # Hapoel Jerusalem Basketball
    "הפועל אילת",      # Hapoel Eilat Basketball
    "גלבוע גליל", "גלבוע עליון",  # Galil Gilboa Basketball
    "עמק יזרעאל",      # Emek Yizrael Basketball
)
# Context keywords that, combined with a Maccabi entity, strongly imply Israeli domestic play.
_ISRAELI_BBALL_CONTEXT_KW = (
    "holon", "hapoel holon",
    "חולון", "הפועל חולון",
    "tel aviv derby", "דרבי תל אביבי",
    "winner league", "ligat winner",
    "israeli basketball", "israel basketball",
    "israeli league", "israel league",
    "hapoel jerusalem", "הפועל ירושלים",
    "hapoel tel aviv", "הפועל תל אביב",
    "eilat", "אילת",
    "bnei herzliya", "בני הרצליה",
    "rishon lezion", "rishon", "ראשון לציון", "ראשון",
    "petah tikva", "kiryat motzkin",
    "binyamina",
    "גליל", "נס ציונה",
    "עירוני רמת גן",
)
_ACB_KW = ("acb", "liga acb")
_BSL_KW = ("bsl", "turkish basketball")
_GREEK_KW = ("greek basket", "greek league", "basket league")
_LBA_KW = ("lba", "lega basket", "italian basketball")
_LNB_KW = ("lnb", "pro a", "french basketball")

_WIMBLEDON_KW = ("wimbledon", "וימבלדון")
_ROLAND_GARROS_KW = ("roland garros", "french open", "רולאן גארוס")
_US_OPEN_KW = ("us open",)
_AUSTRALIAN_OPEN_KW = ("australian open",)


def _detect_league(text: str, sport: str, url: str = "") -> Optional[str]:
    if sport == "basketball":
        url_lower = url.lower()
        # EuroCup: check title AND URL before EuroLeague to avoid misclassification.
        # e.g. "Euroleague names teams for expanded EuroCup field" → EuroCup, not EuroLeague.
        if _has(text, *_EUROCUP_KW) or "eurocup" in url_lower or "/eurocup/" in url_lower:
            return "EuroCup"
        if _has(text, *_NBA_DIRECT_KW) or _has(text, *_NBA_TEAM_KW):
            return "NBA"
        if _has(text, *_EUROLEAGUE_KW):
            return "EuroLeague"
        if _has(text, *_ISRAELI_BBALL_DIRECT_KW):
            return "Israeli Basketball League"
        if _has(text, *_ACB_KW):
            return "Spanish ACB"
        if _has(text, *_BSL_KW):
            return "Turkish BSL"
        if _has(text, *_GREEK_KW):
            return "Greek Basket League"
        if _has(text, *_LBA_KW):
            return "Italian LBA"
        if _has(text, *_LNB_KW):
            return "French LNB"
    elif sport == "tennis":
        if _has(text, *_WIMBLEDON_KW):
            return "Wimbledon"
        if _has(text, *_ROLAND_GARROS_KW):
            return "Roland Garros"
        if _has(text, *_US_OPEN_KW):
            return "US Open"
        if _has(text, *_AUSTRALIAN_OPEN_KW):
            return "Australian Open"
    elif sport == "football":
        if _has(text, "ליגת העל") or _has(text, "israeli premier", "hapoel", "beitar", "maccabi haifa"):
            return "Israeli Premier League"
        if _has(text, "champions league", "ליגת האלופות"):
            return "UEFA Champions League"
        if _has(text, "premier league"):
            return "Premier League"
        if _has(text, "la liga", "לה ליגה"):
            return "La Liga"
        if _has(text, "bundesliga"):
            return "Bundesliga"
    return None


# ── Entity detection ──────────────────────────────────────────────────────────

_DENI_KW = (
    "דני אבדיה", "אבדיה",
    "deni avdija", "avdija",
    # "דני" alone is intentionally NOT included — it's a common Hebrew name
    # that would cause false positives (e.g. a footballer named Danny).
    # "אבדיה" (Avdija) is distinctive enough for short-form references.
)


def _sport_context_for_resolver(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
) -> Optional[str]:
    """Sport evidence for entity resolution.

    Priority: explicit override (already-resolved sport) > basketball-only
    source > context keywords. Conflicting or absent evidence → None, which
    makes the resolver abstain on cross-sport club names.
    """
    if sport_override in ("basketball", "football"):
        return sport_override
    if source_id in _BASKETBALL_ONLY_SOURCES:
        return "basketball"
    basketball = _has_basketball_context(text)
    football = _has_football_context(text) or _has_football_maccabi_context(text)
    if basketball and not football:
        return "basketball"
    if football and not basketball:
        return "football"
    return None


def _resolve_text_entities(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
) -> EntityResolution:
    """Run the taxonomy resolver with the sport evidence available to the classifier."""
    return resolve_entities(
        text,
        sport_context=_sport_context_for_resolver(text, source_id, sport_override),
    )


def _resolution_to_legacy_entities(resolution: EntityResolution) -> list[str]:
    """Convert resolved taxonomy entities to legacy display names.

    Coach mentions imply their current team (Kattash → Maccabi TLV Basketball) —
    a taxonomy data fact replacing the old hardcoded rule. The coach's own name
    is not emitted, matching pre-taxonomy behavior.
    """
    entities: list[str] = []
    for entity in resolution.resolved:
        if entity.kind == "coach":
            team = entity_by_id(entity.team_id) if entity.team_id else None
            if team and team.legacy_name not in entities:
                entities.append(team.legacy_name)
            continue
        if entity.legacy_name not in entities:
            entities.append(entity.legacy_name)
    return entities


def _detect_entities(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
) -> list[str]:
    """Canonical entity detection via the taxonomy resolver.

    Contract (taxonomy PR):
    - Full-name aliases only; longest match wins ("מכבי רמת גן" can never
      resolve to Maccabi Tel Aviv).
    - Bare family names ("מכבי", "הפועל", "עירוני", 'בית"ר') never resolve to
      a specific team.
    - Cross-sport club names (מכבי תל אביב, הפועל ירושלים…) resolve only with
      sport evidence; otherwise the mention abstains and classify() tags the
      article ambiguous_club.
    """
    return _resolution_to_legacy_entities(
        _resolve_text_entities(text, source_id, sport_override)
    )


def _filter_entities_for_sport(entities: list[str], sport: str) -> list[str]:
    """Drop entities whose taxonomy sport contradicts the resolved article sport.

    Entities unknown to the taxonomy (legacy_sport → None) pass through.
    """
    if sport not in ("basketball", "football"):
        return entities
    return [e for e in entities if legacy_sport(e) in (None, sport)]


# ── Event type detection ──────────────────────────────────────────────────────

_GRAND_SLAM_KW = (
    "grand slam", "גראנד סלאם",
    # Specific Grand Slam names: a win at any of these is grand_slam_winner
    "roland garros", "רולאן גארוס", "french open",
    "wimbledon", "וימבלדון",
    "us open",
    "australian open", "אליפות אוסטרליה",
)
_GRAND_SLAM_WIN_KW = ("winner", "wins", "won", "champion", "זוכה", "זכה", "זכתה")

_SIGNING_KW = (
    "חתם", "חתמה", "חתמו", "החתים", "חתימה",
    "הצטרף", "הצטרפה",       # joined / signed and joined
    "signed", "signing",
    "לעונה נוספת",   # for another season — contract extension
    "מונה למאמן",    # appointed as head coach
    # Feminine forms — "למאמנת" uses regular nun (נ U+05E0) while "למאמן" ends
    # with final nun (ן U+05DF), so the masculine keyword is NOT a substring of
    # the feminine form (same Unicode issue as the אלוף/אלופת fix in PR 11).
    "מונתה למאמן",   # appointed (feminine subject) as head coach — PR 13
    "מונתה למאמנת",  # appointed (feminine subject) as head coach (feminine) — PR 13
    "מונה למאמנת",   # appointed as head coach (feminine role) — PR 13
    "מינוי",         # appointment / designation
    "הארכת חוזה",    # contract extension (noun form) — PR 13
    "האריך חוזה",    # extended contract (masculine) — PR 13
    "האריכה חוזה",   # extended contract (feminine) — PR 13
    "חוזה חדש",      # new contract — PR 13
    # Intentionally NOT included (false-positive risk — PR 13):
    #   "שוחרר" alone — collides with hospital-release in injury coverage
    #   "עזב" alone — generic departure wording, often opinion/recap pieces
    #   "מאמן חדש" alone — presentation/opinion pieces, not a signing event
)
_SIGNING_WORD_KW = ("signs", "sign")   # word boundary to avoid "signal"

_NEGOTIATION_KW = (
    'במו"מ', 'מו"מ', 'במו״מ', 'מו״מ',
    "במשא ומתן", "מגעים", "שיחות",
    "מתקרב", "מתקרבת",      # approaching / close to
    "סיכם", "סיכמה",         # finalised/agreed (often precedes signing)
    "על סף חתימה",           # on the verge of signing
    "negotiations", "negotiation", "in talks", "advanced talks",
)
_NEGOTIATION_WORD_KW = ("talks",)

_CANDIDATE_KW = (
    "מועמד", "מועמדת", "בודקת", "בודק",
    "על הכוונת", "עוקבת", "עוקב",
    "מעוניינת", "מעוניין",   # interested in
    "עשוי להגיע", "עשויה להגיע",  # may arrive
    "monitoring", "candidate", "interested in",
    "המטרות הבאות", "המטרה הבאה",  # the next targets / the next target
)
_CANDIDATE_WORD_KW = ("target",)

_INJURY_KW = (
    "נפצע", "נפצעה", "פציעה", "ייעדר", "יעדר", "פצוע",
    "בספק",                  # in doubt (fitness doubt)
    "קרע",                   # tear (muscle/ligament tear)
    "חבלה",                  # bruise / contusion
    "injured", "injury", "out for",
)
_TRADE_KW = (
    "טרייד", "נסחר", "נסחרה",
    "הועבר", "הועברה",       # was transferred
    "traded", "trade deal",
)
_TRADE_WORD_KW = ("trade",)

_FINALS_KW = ("גמר", "finals", "championship", "אליפות")

# title_win detection — split into two sets to avoid false positives.
# Unambiguous championship words: any of these alone is sufficient for title_win.
_TITLE_WIN_UNAMBIGUOUS_KW = (
    "אלוף", "אלופה",
    "אלופת",   # construct state feminine: "אלופת ה-NBA" — ף (U+05E3) ≠ פ (U+05E4)
    "אלופות",  # plural feminine: "אלופות הליגה"
    "הניפה", "הניף",  # lifted/raised a trophy
    "champion", "champions", "title", "trophy", "clinches", "clinched",
)
# Hebrew "won" verbs — too broad alone ("זכה לביקורת", "זכו ברגע").
# Only trigger title_win when paired with an explicit championship context word.
_WIN_VERB_HE = ("זוכה", "זכה", "זכתה", "זכו")
# Championship context required when only win-verbs are present.
# Intentionally excludes "גמר" — a final ≠ a title win.
_WIN_CHAMPIONSHIP_CTX_KW = (
    "בגביע", "הגביע", "גביע",
    "בתואר", "תואר",
    "באליפות",
)

_PLAYOFF_KW = ("פלייאוף", "playoffs", "playoff")

_EARLY_ROUND_TENNIS_KW = (
    "סיבוב ראשון", "סיבוב שני", "סיבוב שלישי",
    "first round", "second round", "third round",
    "round of 16", "round of 32",
)

_DEATH_ACCIDENT_KW = ("נהרג", "נפטר", "תאונה קטלנית")

_SCHEDULE_KW = (
    'לו"ז', "לוח משחקים", "שידורים", "שידור", "לקראת", "תאריכים",
    "schedule", "preview", "upcoming", "fixture", "fixtures",
)

_RESULT_KW = (
    "ניצח", "הפסיד", "תוצאה",
    "beats", "beat", "defeats", "defeat", "won", "loses", "lost", "victory",
)
_REGULAR_SEASON_KW = ("ליגה הרגילה", "regular season")


def _detect_event_type(text: str, sport: str) -> str:
    # Death/accident guard: prevent "נהרג"/"נפטר" articles from triggering title_win
    # via incidental championship words (e.g. "נהרג אלוף הגביע" → "news", not "title_win").
    if _has(text, *_DEATH_ACCIDENT_KW):
        return "news"

    # Grand slam winner: needs BOTH the tournament context AND a win signal
    if sport == "tennis" and _has(text, *_GRAND_SLAM_KW) and _has(text, *_GRAND_SLAM_WIN_KW):
        return "grand_slam_winner"

    # Finals / championship result
    if _has(text, *_FINALS_KW):
        return "finals_result"
    if _has(text, *_TITLE_WIN_UNAMBIGUOUS_KW):
        return "title_win"
    if _has(text, *_WIN_VERB_HE) and _has(text, *_WIN_CHAMPIONSHIP_CTX_KW):
        return "title_win"

    # Negotiation — checked BEFORE signing because "על סף חתימה" (on the verge of
    # signing) contains "חתימה" which would otherwise trigger signing detection first.
    if _has(text, *_NEGOTIATION_KW) or any(_has_word(text, w) for w in _NEGOTIATION_WORD_KW):
        return "negotiation"

    # Signing
    if _has(text, *_SIGNING_KW) or any(_has_word(text, w) for w in _SIGNING_WORD_KW):
        return "signing"

    # Candidate / monitoring
    if _has(text, *_CANDIDATE_KW) or any(_has_word(text, w) for w in _CANDIDATE_WORD_KW):
        return "candidate"

    # Injury
    if _has(text, *_INJURY_KW):
        return "injury"

    # Trade
    if _has(text, *_TRADE_KW) or any(_has_word(text, w) for w in _TRADE_WORD_KW):
        return "major_trade"

    # Playoff
    if _has(text, *_PLAYOFF_KW):
        return "playoff_result"

    # Tennis early round
    if sport == "tennis" and _has(text, *_EARLY_ROUND_TENNIS_KW):
        return "early_round_result"

    # Regular season result
    if _has(text, *_REGULAR_SEASON_KW):
        return "regular_season_result"

    # Schedule / preview
    if _has(text, *_SCHEDULE_KW):
        return "schedule"

    # Generic match result
    if _has(text, *_RESULT_KW):
        return "match_result"

    return "news"


# ── Importance assignment ─────────────────────────────────────────────────────

_VERY_HIGH_EVENTS = frozenset({"grand_slam_winner", "finals_result", "title_win"})
_HIGH_EVENTS = frozenset({"signing", "negotiation", "injury", "major_trade", "major_transfer"})
_HIGH_LEAGUES = frozenset({"NBA", "EuroLeague"})
_HIGH_ENTITIES = frozenset({"Maccabi Tel Aviv Basketball", "Deni Avdija"})
_LOW_EVENTS = frozenset({"schedule", "early_round_result"})


def _assign_importance(
    event_type: str,
    entities: list[str],
    league: Optional[str],
) -> str:
    if event_type in _VERY_HIGH_EVENTS:
        return "very_high"

    has_high_entity = any(e in _HIGH_ENTITIES for e in entities)

    if event_type in _HIGH_EVENTS:
        if has_high_entity or league in _HIGH_LEAGUES:
            return "high"
        return "medium"

    if event_type in _LOW_EVENTS:
        return "low"

    # Generic news with no tracked entity: downgrade to low.
    # Reduces noise from generic NBA filler that has no signal keyword.
    if event_type == "news" and not has_high_entity:
        return "low"

    return "medium"


# ── Confidence assignment ─────────────────────────────────────────────────────

def _assign_confidence(
    sport: str,
    league: Optional[str],
    entities: list[str],
    event_type: str,
    source_id: str,
) -> float:
    score = 0.40
    if sport != "unknown":
        score += 0.15
    if source_id in _BASKETBALL_ONLY_SOURCES and sport == "basketball":
        score += 0.05  # source context confirms sport
    if league:
        score += 0.15
    if entities:
        score += 0.15
    if event_type != "news":
        score += 0.10
    return round(min(score, 0.95), 2)


# ── Tag collection ────────────────────────────────────────────────────────────

def _collect_tags(
    sport: str,
    league: Optional[str],
    entities: list[str],
    event_type: str,
) -> list[str]:
    tags: list[str] = []
    if sport != "unknown":
        tags.append(sport)
    if league:
        tags.append(league)
    tags.extend(entities)
    if event_type != "news":
        tags.append(event_type)
    return tags


# ── Public interface ──────────────────────────────────────────────────────────

def classify(
    title: str,
    source_id: str = "",
    language: str = "en",
    url: str = "",
    subtitle: str | None = None,
    source_sport_hint: str | None = None,
) -> ClassificationResult:
    """Classify an article title using deterministic keyword rules.

    Args:
        title:             Article title in Hebrew or English.
        source_id:         Internal source ID for source-specific defaults.
        language:          "he" or "en".
        url:               Article URL — used for URL-path-based league inference
                           (e.g. detecting EuroCup vs EuroLeague from /eurocup/ path).
        subtitle:          Optional subtitle/description text. Title is always the primary
                           signal. Subtitle may fill sport=unknown, add missing entities,
                           improve league detection, or refine event_type="news" when the
                           title context is insufficient. Subtitle never overrides an
                           already-resolved sport value from the title.
        source_sport_hint: Pre-computed sport hint from the article URL for sources with
                           reliable category URL schemes (e.g. Israel Hayom). When set,
                           overrides keyword-based sport detection in the deterministic path.

    Returns:
        ClassificationResult with all fields populated.
    """
    text = title.lower()
    sub_text = subtitle.lower() if subtitle else ""

    sport = _detect_sport(text, source_id, source_sport_hint=source_sport_hint)

    _basketball_only_src = source_id in _BASKETBALL_ONLY_SOURCES
    title_resolution = _resolve_text_entities(text, source_id)
    entities = _resolution_to_legacy_entities(title_resolution)

    # Ambiguous club mention: the resolver found a cross-sport club name it could
    # not disambiguate (e.g. "מכבי תל אביב" / "הפועל ירושלים" with no sport
    # evidence). Abstain — no entity, ambiguous_club tag, LLM gate force-calls.
    # Basketball-only sources are never ambiguous — they only cover basketball.
    is_ambiguous_club = not _basketball_only_src and bool(title_resolution.ambiguous)

    # Entity-based sport inference: when all resolved entities agree on one
    # sport, that sport is taxonomy evidence (previously a basketball-only bias).
    if sport == "unknown" and entities and not is_ambiguous_club:
        entity_sports = {legacy_sport(e) for e in entities} - {None}
        if len(entity_sports) == 1:
            sport = next(iter(entity_sports))

    # Cross-sport entity post-filter — defensive; entity resolution should already
    # agree with sport detection, but this prevents stray entities if they diverge.
    entities = _filter_entities_for_sport(entities, sport)

    # Sport detection may have resolved the sport (source hint, explicit sport
    # keywords) even when mixed context words made entity resolution abstain
    # (e.g. "ליגת העל בכדורסל" contains both football and basketball markers).
    # Re-resolve the ambiguous mention with the resolved sport as taxonomy evidence.
    if is_ambiguous_club and sport in ("basketball", "football"):
        for name in _detect_entities(text, source_id, sport_override=sport):
            if name not in entities:
                entities.append(name)
        if entities:
            is_ambiguous_club = False

    # ── Subtitle gap-filling ───────────────────────────────────────────────────
    # Title is always the primary signal. Subtitle fills gaps only:
    #   sport=unknown → try subtitle for sport detection
    #   entities=[]  → try subtitle for entity detection
    # Subtitle cannot change an already-resolved sport value.
    # Football Maccabi clubs must still be checked first (same priority as in title).
    if sub_text:
        # Sport gap: subtitle fills sport only when title produced unknown.
        if sport == "unknown":
            if _has_football_maccabi_context(sub_text):
                sport = "football"
            else:
                sub_sport = _detect_sport(sub_text, source_id)
                if sub_sport != "unknown":
                    sport = sub_sport
                elif _has_basketball_context(sub_text):
                    # Catch basketball context keywords not covered by _detect_sport
                    # (e.g. "הפועל ירושלים", position names like "גארד").
                    sport = "basketball"
                elif _has_football_context(sub_text):
                    sport = "football"

            # When subtitle resolved sport for an ambiguous-club title, re-resolve
            # the title's entities using that sport as taxonomy evidence.
            if sport != "unknown" and is_ambiguous_club:
                for name in _detect_entities(text, source_id, sport_override=sport):
                    if name not in entities:
                        entities.append(name)
                if entities:
                    is_ambiguous_club = False  # ambiguity resolved via subtitle

            # Re-apply entity-based sport inference and the cross-sport post-filter
            # after subtitle may have modified sport or entities.
            if sport == "unknown" and entities and not is_ambiguous_club:
                entity_sports = {legacy_sport(e) for e in entities} - {None}
                if len(entity_sports) == 1:
                    sport = next(iter(entity_sports))
            entities = _filter_entities_for_sport(entities, sport)

        # Entity gap: subtitle adds entities when title produced none.
        if not entities:
            sub_entities = _detect_entities(
                sub_text, source_id,
                sport_override=sport if sport in ("basketball", "football") else None,
            )
            entities = _filter_entities_for_sport(sub_entities, sport)

    league = _detect_league(text, sport, url=url)

    # League gap from subtitle: when title produced no league, try subtitle.
    if league is None and sub_text:
        league = _detect_league(sub_text, sport)

    # Entity-based league inference: Deni Avdija is an NBA player.
    # Titles that mention him without "NBA" (common in Hebrew news) still map to NBA.
    if sport == "basketball" and league is None and "Deni Avdija" in entities:
        league = "NBA"

    # Entity + Israeli context → Israeli Basketball League.
    # Example: "Maccabi sweeps Holon to set up Tel Aviv derby Finals" → Israeli Basketball League.
    if (
        sport == "basketball"
        and league is None
        and "Maccabi Tel Aviv Basketball" in entities
        and (_has(text, *_ISRAELI_BBALL_CONTEXT_KW) or _has(sub_text, *_ISRAELI_BBALL_CONTEXT_KW))
    ):
        league = "Israeli Basketball League"

    event_type = _detect_event_type(text, sport)

    # Event type gap: subtitle refines generic "news" to a more specific event type.
    if event_type == "news" and sub_text:
        sub_event_type = _detect_event_type(sub_text, sport)
        if sub_event_type != "news":
            event_type = sub_event_type

    importance = _assign_importance(event_type, entities, league)
    confidence = _assign_confidence(sport, league, entities, event_type, source_id)
    tags = _collect_tags(sport, league, entities, event_type)
    if is_ambiguous_club:
        tags.append("ambiguous_club")

    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities,
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        tags=tags,
    )


# ── Public helpers for post-classification enrichment ─────────────────────────

def has_maccabi_tel_aviv_phrase(text: str) -> bool:
    """True if text contains a full-name Maccabi Tel Aviv form.

    Public wrapper — use in ingestion_service after LLM merge to check whether
    entity injection is applicable.
    """
    return _has_maccabi_tel_aviv_phrase(text)


def compute_importance(event_type: str, entities: list[str], league: Optional[str]) -> str:
    """Public wrapper for _assign_importance.

    Use when entities change after initial classification (e.g., post-LLM entity injection).
    """
    return _assign_importance(event_type, entities, league)


def enrich_maccabi_entity_after_sport_resolve(
    entities: list[str],
    title_lower: str,
    sport: str,
) -> list[str]:
    """Inject Maccabi Tel Aviv Basketball entity if sport was resolved to basketball post-classify.

    Deprecated in PR 13 — kept as a Maccabi-only wrapper around
    enrich_basketball_entities_after_sport_resolve() for backward compatibility.

    Returns a new list if enriched; returns the same object if no change (identity check safe).
    """
    if (
        sport != "basketball"
        or "Maccabi Tel Aviv Basketball" in entities
        or "Maccabi Tel Aviv Football" in entities
        or _has_football_maccabi_context(title_lower)
        or not _has_maccabi_tel_aviv_phrase(title_lower)
    ):
        return entities
    return [*entities, "Maccabi Tel Aviv Basketball"]


# Basketball club entities injectable post-merge when the LLM resolved
# sport=basketball for a title that names the club but had no sport context
# keywords (the ambiguous_club gap). Derived from the taxonomy registry:
# all unguarded Israeli Basketball League clubs, with their full-name aliases.
def _derive_basketball_enrichment_phrases() -> dict[str, tuple[str, ...]]:
    phrases: dict[str, tuple[str, ...]] = {}
    for entity in entities_by_sport("basketball"):
        if entity.kind != "team" or entity.guarded:
            continue
        if entity.domestic_competition != "comp:ibl":
            continue
        phrases[entity.legacy_name] = tuple(entity.aliases)
    return phrases


_BASKETBALL_ENRICHMENT_PHRASES: dict[str, tuple[str, ...]] = (
    _derive_basketball_enrichment_phrases()
)


def enrich_basketball_entities_after_sport_resolve(
    entities: list[str],
    title_lower: str,
    sport: str,
) -> tuple[list[str], list[str]]:
    """Inject basketball club entities after the final sport is resolved to basketball.

    Generalizes the Maccabi-only enrichment (PR 13). classify() leaves entities empty
    for ambiguous_club titles with no sport context; the LLM resolves sport=basketball
    but the merge does not retroactively add entities. This corrects that gap for all
    clubs in _BASKETBALL_ENRICHMENT_PHRASES.

    Guards:
    - only when sport == "basketball" (never football, never unknown)
    - never when a football Maccabi club is named in the title
    - for non-Maccabi clubs, additionally never when generic football context is present
      (extra-conservative second layer; the Maccabi path keeps its original semantics)
    - entity must not already be present

    Returns (entities, injected). When nothing is injected, `entities` is the
    same object that was passed in (identity check safe) and `injected` is [].
    """
    if sport != "basketball" or _has_football_maccabi_context(title_lower):
        return entities, []

    injected: list[str] = []
    for canonical, phrases in _BASKETBALL_ENRICHMENT_PHRASES.items():
        if canonical in entities or canonical in injected:
            continue
        if not _has(title_lower, *phrases):
            continue
        if canonical == "Maccabi Tel Aviv Basketball":
            # Preserve original Maccabi-only exclusion exactly.
            if "Maccabi Tel Aviv Football" in entities:
                continue
        else:
            # Non-Maccabi clubs: skip when generic football context is present.
            if _has_football_context(title_lower):
                continue
        injected.append(canonical)

    if not injected:
        return entities, []
    return [*entities, *injected], injected
