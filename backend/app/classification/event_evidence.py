"""
Semantic evidence contract for article event types.

The classifier and LLM merge can propose event types, but specific non-news
events are accepted only when the title/subtitle text contains positive
evidence for that semantic event. On doubt, callers should fall back to news.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


EVENT_CERTAINTIES = {"confirmed", "probable", "weak"}


@dataclass(frozen=True)
class Pattern:
    value: str
    word: bool = False


@dataclass(frozen=True)
class EventEvidenceRule:
    required_any: tuple[tuple[Pattern, ...], ...]
    blockers: tuple[Pattern, ...] = ()
    confirmed_any: tuple[Pattern, ...] = ()


@dataclass(frozen=True)
class EventEvidence:
    event_type: str
    valid: bool
    certainty: str


def phrase(value: str) -> Pattern:
    return Pattern(value)


def word(value: str) -> Pattern:
    return Pattern(value, word=True)


def _contains(text: str, pattern: Pattern) -> bool:
    if pattern.word:
        return bool(re.search(r"\b" + re.escape(pattern.value) + r"\b", text))
    return pattern.value in text


def _has_any(text: str, patterns: tuple[Pattern, ...]) -> bool:
    return any(_contains(text, pattern) for pattern in patterns)


def _matches_required_groups(text: str, groups: tuple[tuple[Pattern, ...], ...]) -> bool:
    return all(_has_any(text, group) for group in groups)


_DEATH_ACCIDENT = (
    phrase("נהרג"), phrase("נפטר"), phrase("תאונה קטלנית"),
)

_NEGOTIATION = (
    phrase('במו"מ'), phrase('מו"מ'), phrase("במו״מ"), phrase("מו״מ"),
    phrase("במשא ומתן"), phrase("מגעים"), phrase("שיחות"),
    phrase("מתקרב"), phrase("מתקרבת"), phrase("סיכם"), phrase("סיכמה"),
    phrase("על סף חתימה"), phrase("negotiations"), phrase("negotiation"),
    phrase("in talks"), phrase("advanced talks"), word("talks"),
)

_CANDIDATE = (
    phrase("מועמד"), phrase("מועמדת"), phrase("בודקת"), phrase("בודק"),
    phrase("על הכוונת"), phrase("עוקבת"), phrase("עוקב"),
    phrase("מעוניינת"), phrase("מעוניין"),
    phrase("עשוי להגיע"), phrase("עשויה להגיע"),
    phrase("המטרות הבאות"), phrase("המטרה הבאה"),
    phrase("monitoring"), phrase("candidate"), phrase("interested in"),
    phrase("wants"), phrase("want"), phrase("dreams of"), phrase("dreaming of"),
    word("target"),
)

_SIGNING_COMPLETE = (
    phrase("חתם"), phrase("חתמה"), phrase("חתמו"), phrase("החתים"),
    phrase("חתימה"), phrase("הצטרף"), phrase("הצטרפה"),
    phrase("לעונה נוספת"), phrase("מונה למאמן"), phrase("מונתה למאמן"),
    phrase("מונתה למאמנת"), phrase("מונה למאמנת"), phrase("מינוי"),
    phrase("הארכת חוזה"), phrase("האריך חוזה"), phrase("האריכה חוזה"),
    phrase("חוזה חדש"), phrase("signed"), phrase("signing"), word("signs"), word("sign"),
)

_RELEASE_COMPLETE = (
    phrase("שוחרר"), phrase("שוחררה"), phrase("שוחררו"),
    phrase("שחררה את"), phrase("שחרר את"), phrase("נפרדה מ"),
    phrase("released"), phrase("waived"), phrase("cut by"), phrase("roster cuts"),
)

_RELEASE_BLOCKERS = (
    phrase("לא שוחרר"), phrase("לא שוחררה"), phrase("לא שוחררו"),
    phrase("בית החולים"), phrase("hospital"), phrase("released from hospital"),
)

_TITLE_WIN_CHAMPION_NOUN = (
    phrase("אלוף"), phrase("אלופה"), phrase("אלופת"), phrase("אלופות"),
    phrase("הניפה"), phrase("הניף"), phrase("champion"), phrase("champions"),
)
_TITLE_WIN_VERB = (
    phrase("זוכה"), phrase("זכה"), phrase("זכתה"), phrase("זכו"),
    phrase("won"), phrase("wins"), phrase("win"), phrase("clinched"), phrase("clinches"),
)
_TITLE_WIN_OBJECT = (
    phrase("בגביע"), phrase("הגביע"), phrase("גביע"),
    phrase("בתואר"), phrase("תואר"), phrase("באליפות"),
    phrase("title"), phrase("trophy"), phrase("championship"),
)
_TITLE_WIN_BLOCKERS = _DEATH_ACCIDENT + _CANDIDATE + (
    phrase("wants the title"), phrase("want the title"),
    phrase("dreams of a title"), phrase("dreaming of a title"),
    phrase("title candidate"), phrase("title contender"),
)

_FINALS_CONTEXT = (
    phrase("גמר"), phrase("finals"), phrase("final"), phrase("championship game"),
    phrase("championship series"),
)
_RESULT_VERB = (
    phrase("ניצח"), phrase("ניצחה"), phrase("ניצחו"),
    phrase("הפסיד"), phrase("הפסידה"), phrase("הפסידו"),
    phrase("תוצאה"), phrase("beats"), phrase("beat"), phrase("defeats"),
    phrase("defeat"), phrase("won"), phrase("loses"), phrase("lost"), phrase("victory"),
)
_SCORE_OR_RESULT_CONTEXT = (
    phrase("תוצאה"), phrase("ניצחון"), phrase("הפסד"), phrase("result"),
    phrase("score"), phrase("victory"),
)

EVENT_EVIDENCE_RULES: dict[str, EventEvidenceRule] = {
    "signing": EventEvidenceRule(
        required_any=(_SIGNING_COMPLETE,),
        blockers=_NEGOTIATION + _CANDIDATE + _RELEASE_COMPLETE,
        confirmed_any=(
            phrase("חתם"), phrase("חתמה"), phrase("חתמו"),
            phrase("signed"), phrase("הצטרף"), phrase("הצטרפה"),
        ),
    ),
    "release": EventEvidenceRule(
        required_any=(_RELEASE_COMPLETE,),
        blockers=_RELEASE_BLOCKERS,
        confirmed_any=(phrase("שוחרר"), phrase("שוחררה"), phrase("released"), phrase("waived")),
    ),
    "negotiation": EventEvidenceRule(
        required_any=(_NEGOTIATION,),
        confirmed_any=(phrase('מו"מ'), phrase("מו״מ"), phrase("במשא ומתן"), phrase("negotiations")),
    ),
    "candidate": EventEvidenceRule(
        required_any=(_CANDIDATE,),
        confirmed_any=(phrase("מועמד"), phrase("מועמדת"), phrase("candidate")),
    ),
    "injury": EventEvidenceRule(
        required_any=((
            phrase("נפצע"), phrase("נפצעה"), phrase("פציעה"), phrase("ייעדר"),
            phrase("יעדר"), phrase("פצוע"), phrase("בספק"), phrase("קרע"),
            phrase("חבלה"), phrase("injured"), phrase("injury"), phrase("out for"),
        ),),
        blockers=_DEATH_ACCIDENT,
        confirmed_any=(phrase("פציעה"), phrase("injury"), phrase("injured")),
    ),
    "major_trade": EventEvidenceRule(
        required_any=((
            phrase("טרייד"), phrase("נסחר"), phrase("נסחרה"),
            phrase("הועבר"), phrase("הועברה"), phrase("traded"),
            phrase("trade deal"), word("trade"),
        ),),
        confirmed_any=(phrase("טרייד"), phrase("traded"), phrase("trade deal")),
    ),
    "title_win": EventEvidenceRule(
        required_any=(_TITLE_WIN_CHAMPION_NOUN,),
        blockers=_TITLE_WIN_BLOCKERS,
        confirmed_any=_TITLE_WIN_CHAMPION_NOUN,
    ),
    "finals_result": EventEvidenceRule(
        required_any=(_FINALS_CONTEXT,),
        blockers=_TITLE_WIN_BLOCKERS,
        confirmed_any=(phrase("גמר"), phrase("finals"), phrase("championship game")),
    ),
    "grand_slam_winner": EventEvidenceRule(
        required_any=(
            (
                phrase("grand slam"), phrase("גראנד סלאם"), phrase("roland garros"),
                phrase("רולאן גארוס"), phrase("french open"), phrase("wimbledon"),
                phrase("וימבלדון"), phrase("us open"), phrase("australian open"),
                phrase("אליפות אוסטרליה"),
            ),
            (
                phrase("winner"), phrase("wins"), phrase("won"),
                phrase("champion"), phrase("זוכה"), phrase("זכה"), phrase("זכתה"),
            ),
        ),
        confirmed_any=(phrase("winner"), phrase("champion"), phrase("זוכה"), phrase("זכה")),
    ),
    "playoff_result": EventEvidenceRule(
        required_any=((phrase("פלייאוף"), phrase("playoffs"), phrase("playoff")),),
        confirmed_any=(phrase("פלייאוף"), phrase("playoffs"), phrase("playoff")),
    ),
    "early_round_result": EventEvidenceRule(
        required_any=((
            phrase("סיבוב ראשון"), phrase("סיבוב שני"), phrase("סיבוב שלישי"),
            phrase("first round"), phrase("second round"), phrase("third round"),
            phrase("round of 16"), phrase("round of 32"),
        ),),
        confirmed_any=(phrase("סיבוב"), phrase("round")),
    ),
    "regular_season_result": EventEvidenceRule(
        required_any=((phrase("ליגה הרגילה"), phrase("regular season")),),
        confirmed_any=(phrase("regular season"), phrase("ליגה הרגילה")),
    ),
    "schedule": EventEvidenceRule(
        required_any=((
            phrase('לו"ז'), phrase("לוח משחקים"), phrase("שידורים"), phrase("שידור"),
            phrase("לקראת"), phrase("תאריכים"), phrase("schedule"), phrase("preview"),
            phrase("upcoming"), phrase("fixture"), phrase("fixtures"),
        ),),
        confirmed_any=(phrase('לו"ז'), phrase("לוח משחקים"), phrase("schedule"), phrase("fixtures")),
    ),
    "match_result": EventEvidenceRule(
        required_any=(_RESULT_VERB,),
        blockers=(
            phrase("לקראת"), phrase("preview"), phrase("upcoming"),
            phrase("schedule"), phrase("fixture"), phrase("fixtures"),
        ),
        confirmed_any=_SCORE_OR_RESULT_CONTEXT,
    ),
}

_EVENT_SPORT_COMPATIBILITY: dict[str, frozenset[str]] = {
    "grand_slam_winner": frozenset({"tennis"}),
    "early_round_result": frozenset({"tennis"}),
}

# title_win can also be proven by a win verb plus a championship object. Keeping
# this as an explicit extra rule prevents "wants/dreams of the title" from being
# treated as evidence just because the word "title" appears.
_TITLE_WIN_COMPOUND_RULE = EventEvidenceRule(
    required_any=(_TITLE_WIN_VERB, _TITLE_WIN_OBJECT),
    blockers=_TITLE_WIN_BLOCKERS,
    confirmed_any=_TITLE_WIN_VERB + _TITLE_WIN_OBJECT,
)


def validate_event_evidence(
    event_type: str,
    text: str,
    *,
    source: str = "rules",
    sport: str | None = None,
) -> EventEvidence:
    """Validate a proposed event type against the shared evidence table."""
    event_type = event_type or "news"
    if event_type == "news":
        return EventEvidence("news", True, "confirmed")

    allowed_sports = _EVENT_SPORT_COMPATIBILITY.get(event_type)
    if sport is not None and allowed_sports is not None and sport not in allowed_sports:
        return EventEvidence("news", False, "confirmed")

    normalized = (text or "").lower()
    rule = EVENT_EVIDENCE_RULES.get(event_type)
    if rule is None:
        return EventEvidence("news", False, "confirmed")

    valid = _rule_valid(rule, normalized)
    if not valid and event_type == "title_win":
        rule = _TITLE_WIN_COMPOUND_RULE
        valid = _rule_valid(rule, normalized)

    if not valid:
        return EventEvidence("news", False, "confirmed")

    certainty = _certainty_for(rule, normalized, source)
    return EventEvidence(event_type, True, certainty)


def _rule_valid(rule: EventEvidenceRule, text: str) -> bool:
    if _has_any(text, rule.blockers):
        return False
    return _matches_required_groups(text, rule.required_any)


def _certainty_for(rule: EventEvidenceRule, text: str, source: str) -> str:
    if source == "llm":
        return "weak"
    if _has_any(text, rule.confirmed_any):
        return "confirmed"
    return "probable"

