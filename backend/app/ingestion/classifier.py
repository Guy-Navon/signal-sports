"""
Deterministic keyword-based article classifier.

No LLM. No external calls. Fully testable as a pure function.

Design notes:
- Checks title text only (summary ignored for now).
- Optional url is used for URL-path-based league inference (e.g. EuroCup vs EuroLeague).
- Hebrew and English keywords live in the same lists; lowercased before matching.
- Source ID is used to apply basketball-only defaults for Eurohoops/Sportando.
- Confidence is additive: each matched signal contributes a fixed increment.
- When unsure, sport="unknown", event_type="news", confidence<=0.5.
"""

import re
from dataclasses import dataclass
from typing import Optional


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


# ── Sport detection ───────────────────────────────────────────────────────────

_BASKETBALL_KW = (
    "basketball", "כדורסל", "nba", "euroleague", "eurocup", "יורוליג",
    "acb", "bsl", "lba", "lnb",
    "maccabi", "מכבי",          # almost always basketball
    "ווינר סל", "ליגת העל סל",  # Israeli Basketball League explicit markers
    # Israeli basketball clubs — allow sport inference without "כדורסל" keyword
    "בני הרצליה",               # Bnei Herzliya basketball
    # Hebrew NBA team nicknames (not city names — those are too generic)
    "וויזארדס", "הורנטס", "בלייזרס", "ניקס", "סלטיקס", "לייקרס",
    "באקס", "סאנס", "נאגטס", "מאברס", "ספרס", "רוקטס", "ראפטורס", "גריזליס",
)
_FOOTBALL_KW = (
    "football", "soccer", "כדורגל", "fifa", "uefa",
    "champions league", "premier league", "la liga",
    "bundesliga", "serie a", "ligue 1",
    "מונדיאל",                  # World Cup in Hebrew
    # Israeli football clubs — unambiguously football
    'בית"ר', "בית״ר",           # Beitar Jerusalem
    'הפועל ת"א', "הפועל ת״א",   # Hapoel Tel Aviv (football)
    "הפועל תל אביב",
    "הפועל באר שבע",            # Hapoel Beer Sheva (football)
)

# Maccabi clubs that are FOOTBALL — must be checked BEFORE _BASKETBALL_KW
# because "מכבי" appears in _BASKETBALL_KW and would win the sport check first.
_FOOTBALL_MACCABI_KW = (
    "מכבי חיפה",    # Maccabi Haifa (football)
    "maccabi haifa",
)
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


def _detect_sport(text: str, source_id: str) -> str:
    if source_id in _BASKETBALL_ONLY_SOURCES:
        return "basketball"
    if _has(text, *_TENNIS_KW):
        return "tennis"
    # Football Maccabi clubs (e.g. מכבי חיפה) must be checked before the generic
    # "מכבי" basketball keyword — otherwise the basketball check wins first.
    if _has(text, *_FOOTBALL_MACCABI_KW):
        return "football"
    if _has(text, *_BASKETBALL_KW):
        return "basketball"
    if _has(text, *_FOOTBALL_KW):
        return "football"
    return "unknown"


# ── League detection ──────────────────────────────────────────────────────────

# EuroCup must be checked before EuroLeague: some titles mention "Euroleague"
# while covering EuroCup news, and the URL or title keyword "eurocup" is authoritative.
_EUROCUP_KW = ("eurocup", "euro cup", "fiba europe cup")

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
)
_EUROLEAGUE_KW = ("euroleague", "יורוליג", "היורוליג")
# Direct textual mentions of the Israeli Basketball League
_ISRAELI_BBALL_DIRECT_KW = (
    "ליגת ווינר", "ליגת העל בכדורסל", "ליגה לאומית",
    "ווינר סל", "ליגת העל סל",
    "winner league", "ligat winner",
    "israeli basketball league", "super league basketball",
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

_MACCABI_KW = (
    'מכבי ת"א', "מכבי תל אביב", 'מכבי ת״א',
    "maccabi tel aviv", "maccabi",
    # Standalone Hebrew "מכבי" — catches short-form headlines (e.g. "מכבי ניצחה בגמר").
    # Trade-off: may also match other Maccabi clubs (Netanya, Haifa football) when
    # sport detection has already resolved to basketball.
    "מכבי",
)
_DENI_KW = (
    "דני אבדיה", "אבדיה",
    "deni avdija", "avdija",
    # "דני" alone is intentionally NOT included — it's a common Hebrew name
    # that would cause false positives (e.g. a footballer named Danny).
    # "אבדיה" (Avdija) is distinctive enough for short-form references.
)


def _detect_entities(text: str) -> list[str]:
    entities: list[str] = []
    if _has(text, *_MACCABI_KW):
        entities.append("Maccabi Tel Aviv Basketball")
    if _has(text, *_DENI_KW):
        entities.append("Deni Avdija")
    return entities


# ── Event type detection ──────────────────────────────────────────────────────

_GRAND_SLAM_KW = ("grand slam", "גראנד סלאם")
_GRAND_SLAM_WIN_KW = ("winner", "wins", "won", "champion", "זוכה", "זכה", "זכתה")

_SIGNING_KW = (
    "חתם", "חתמה", "חתמו", "החתים", "חתימה",
    "הצטרף", "הצטרפה",       # joined / signed and joined
    "signed", "signing",
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
_WINNER_SUFFIX_KW = ("אלוף", "אלופה", "champion", "champions", "title", "clinches", "זוכה", "זכה", "זכתה", "זכו")

_PLAYOFF_KW = ("פלייאוף", "playoffs", "playoff")

_EARLY_ROUND_TENNIS_KW = (
    "סיבוב ראשון", "סיבוב שני", "סיבוב שלישי",
    "first round", "second round", "third round",
    "round of 16", "round of 32",
)

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
    # Grand slam winner: needs BOTH the tournament context AND a win signal
    if sport == "tennis" and _has(text, *_GRAND_SLAM_KW) and _has(text, *_GRAND_SLAM_WIN_KW):
        return "grand_slam_winner"

    # Finals / championship result
    if _has(text, *_FINALS_KW) or _has(text, *_WINNER_SUFFIX_KW):
        if _has(text, *_FINALS_KW):
            return "finals_result"
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
) -> ClassificationResult:
    """Classify an article title using deterministic keyword rules.

    Args:
        title:     Article title in Hebrew or English.
        source_id: Internal source ID for source-specific defaults.
        language:  "he" or "en".
        url:       Article URL — used for URL-path-based league inference
                   (e.g. detecting EuroCup vs EuroLeague from /eurocup/ path).

    Returns:
        ClassificationResult with all fields populated.
    """
    text = title.lower()

    sport = _detect_sport(text, source_id)
    entities = _detect_entities(text)

    # Entity-based sport inference: all currently tracked entities are basketball.
    # Titles that name a tracked entity without explicit sport keywords (common in
    # Hebrew headlines) still resolve to the correct sport.
    if sport == "unknown" and entities:
        sport = "basketball"

    # Drop basketball entities if sport resolved to football.
    # Prevents "מכבי חיפה" (football club) from being tagged as Maccabi Tel Aviv Basketball.
    if sport == "football":
        entities = [e for e in entities if e != "Maccabi Tel Aviv Basketball"]

    league = _detect_league(text, sport, url=url)

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
        and _has(text, *_ISRAELI_BBALL_CONTEXT_KW)
    ):
        league = "Israeli Basketball League"

    event_type = _detect_event_type(text, sport)
    importance = _assign_importance(event_type, entities, league)
    confidence = _assign_confidence(sport, league, entities, event_type, source_id)
    tags = _collect_tags(sport, league, entities, event_type)

    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities,
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        tags=tags,
    )
