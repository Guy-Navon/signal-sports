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
    hword: bool = False   # Hebrew word: match only at a Hebrew word boundary
    regex: bool = False   # value is a raw regular expression


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


def hword(value: str) -> Pattern:
    return Pattern(value, hword=True)


def regex(value: str) -> Pattern:
    return Pattern(value, regex=True)


_HEBREW_LETTERS = set("אבגדהוזחטיכךלמםנןסעפףצץקרשת")

# Single prepositional/article prefix letters that may legitimately attach to a
# Hebrew word (ב/ל/מ/כ/ה), optionally preceded by ו (and) or ש (that).
_HEBREW_PREFIX_LETTERS = set("בלמכה")
_HEBREW_CONJ_LETTERS = set("וש")


def _is_hebrew_word_occurrence(text: str, idx: int, needle: str) -> bool:
    """True when ``needle`` at ``idx`` is a standalone Hebrew word, allowing
    only a legitimate prepositional prefix chain ([ו|ש] [ב|ל|מ|כ|ה]?).

    Blocks substring hits inside larger words: "זכו" inside "לזכות" is blocked
    by the trailing letter; "גמר" inside "נגמר" is blocked by the illegal
    prefix; "גמר" inside "לגמרי" is blocked by the trailing letter; "בגמר" and
    "ובגמר" are accepted.
    """
    end = idx + len(needle)
    if end < len(text) and text[end] in _HEBREW_LETTERS:
        return False
    # Walk back over an allowed prefix chain.
    i = idx
    if i > 0 and text[i - 1] in _HEBREW_PREFIX_LETTERS:
        i -= 1
    if i > 0 and text[i - 1] in _HEBREW_CONJ_LETTERS:
        i -= 1
    return i == 0 or text[i - 1] not in _HEBREW_LETTERS


def _find_hebrew_word(text: str, needle: str) -> bool:
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            return False
        if _is_hebrew_word_occurrence(text, idx, needle):
            return True
        start = idx + 1


def _contains(text: str, pattern: Pattern) -> bool:
    if pattern.regex:
        return bool(re.search(pattern.value, text))
    if pattern.word:
        return bool(re.search(r"\b" + re.escape(pattern.value) + r"\b", text))
    if pattern.hword:
        return _find_hebrew_word(text, pattern.value)
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
    phrase("על סף חתימה"), phrase("על סף סיכום"),  # on the verge of agreement (#60)
    phrase("negotiations"), phrase("negotiation"),
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

# ── title_win assertion semantics (issue #60) ────────────────────────────────
# A championship WORD is not championship EVIDENCE. title_win is accepted only
# for (a) a champion-noun ASSERTION (the noun used as a predicate, not as an
# epithet for the reigning champion), (b) a trophy-lift verb, or (c) a
# win-verb + championship-object compound at Hebrew word boundaries.

# Trophy-lift verbs — an actual crowning moment; sufficient alone.
_TITLE_WIN_TROPHY_VERBS = (
    phrase("הניפה"), phrase("הניף"), phrase("הוכתרה כאלופה"), phrase("הוכתר כאלוף"),
)
_TITLE_WIN_VERB = (
    hword("זוכה"), hword("זכה"), hword("זכתה"), hword("זכו"),
    word("won"), word("wins"), word("win"), phrase("clinched"), phrase("clinches"),
)
_TITLE_WIN_OBJECT = (
    phrase("בגביע"), phrase("הגביע"), hword("גביע"),
    phrase("בתואר"), hword("תואר"), phrase("באליפות"),
    word("title"), word("trophy"), phrase("championship"),
)
# Medal-placement blockers (#63 product decision): winning silver/bronze at a
# championship is an achievement, not a title win. Gold is deliberately NOT
# blocked — gold at a championship IS winning it. Class rule, not an
# article-specific patch: "זכתה במדליית הארד באליפות" must not validate while
# "זכתה במדליית הזהב באליפות" / "זכתה באליפות" still do.
_MEDAL_PLACEMENT = (
    phrase("מדליית ארד"), phrase("מדליית הארד"), phrase("מדלית ארד"),
    phrase("מדליית כסף"), phrase("מדליית הכסף"), phrase("מדלית כסף"),
    phrase("bronze medal"), phrase("silver medal"),
)

_TITLE_WIN_BLOCKERS = _DEATH_ACCIDENT + _CANDIDATE + _MEDAL_PLACEMENT + (
    phrase("wants the title"), phrase("want the title"),
    phrase("dreams of a title"), phrase("dreaming of a title"),
    phrase("title candidate"), phrase("title contender"),
)

# Hebrew champion nouns considered for the assertion analysis.
_CHAMPION_NOUNS_HE = ("אלוף", "אלופה", "אלופת", "אלופות")
_CHAMPION_NOUNS_EN = ("champion", "champions")

# Words that mark the champion noun as an OBJECT/reference (epithet), not a
# predicate assertion: "את אלופת העולם" (the object marker), "של האלופה", …
_CHAMPION_EPITHET_PRECEDERS_HE = frozenset({
    "את", "של", "על", "עם", "מול", "נגד", "אצל", "לקראת", "בפני", "כמו",
    "אחרי", "לפני",
})
_CHAMPION_EPITHET_PRECEDERS_EN = frozenset({
    "the", "of", "against", "vs", "with", "former", "defending", "reigning",
})

# Competition NAMES that contain champion vocabulary. Their spans are masked
# before the assertion analysis — a competition's name is never title_win
# evidence. Registered competitions come from the shared keyword table
# (imported below); this tuple adds real competition names not (yet) in the
# registry. It is a list of NAMES, not per-headline patches.
_UNREGISTERED_CHAMPION_TERM_COMPETITIONS = (
    "אלוף האלופים",   # Israeli Super Cup ("Champion of Champions")
    "מגן האלופים",    # Community Shield style naming
    "גביע האלופות",   # historical European Champions Cup naming
)


def _champion_term_competition_names() -> tuple[str, ...]:
    """All known competition-name phrases containing a champion noun."""
    try:  # deferred import — competition keywords live with the facts stage
        from app.classification.facts import _COMPETITION_KEYWORDS
        registered = tuple(
            kw
            for kws in _COMPETITION_KEYWORDS.values()
            for kw in kws
            if any(noun in kw for noun in _CHAMPION_NOUNS_HE + _CHAMPION_NOUNS_EN)
        )
    except ImportError:  # pragma: no cover — circular-import safety
        registered = ()
    return registered + _UNREGISTERED_CHAMPION_TERM_COMPETITIONS


def _mask_competition_names(text: str) -> str:
    """Blank out competition-name spans so their vocabulary cannot become
    event evidence ("ליגת האלופות", "אלוף האלופים")."""
    for name in _champion_term_competition_names():
        idx = text.find(name)
        while idx != -1:
            text = text[:idx] + (" " * len(name)) + text[idx + len(name):]
            idx = text.find(name, idx + 1)
    return text


def _preceding_word(text: str, idx: int) -> str:
    """The whitespace-delimited token immediately before position ``idx``."""
    left = text[:idx].rstrip()
    if not left:
        return ""
    return left.split()[-1]


def _has_champion_assertion(text: str) -> bool:
    """True when a champion noun is used as a bare predicate assertion.

    Valid:   "ניו יורק אלופת ה-NBA"  (X [is] champion of Y — a title win)
    Invalid: "האלופה חזרה מהאימון"    (definite article → reigning-champion epithet)
             "מתקרב לאלופת איטליה"    (prepositional prefix → epithet)
             "מנסים להכתים את אלופת העולם" (object marker → epithet)
    """
    masked = _mask_competition_names(text)
    for noun in _CHAMPION_NOUNS_HE:
        start = 0
        while True:
            idx = masked.find(noun, start)
            if idx == -1:
                break
            start = idx + 1
            end = idx + len(noun)
            # Whole bare word: no attached Hebrew letter on either side —
            # any prefix (ה/ל/ב/מ/כ/ו/ש) marks a reference, not an assertion.
            if idx > 0 and masked[idx - 1] in _HEBREW_LETTERS:
                continue
            if end < len(masked) and masked[end] in _HEBREW_LETTERS:
                continue
            if _preceding_word(masked, idx) in _CHAMPION_EPITHET_PRECEDERS_HE:
                continue
            return True
    for noun in _CHAMPION_NOUNS_EN:
        for m in re.finditer(r"\b" + noun + r"\b", masked):
            if _preceding_word(masked, m.start()) in _CHAMPION_EPITHET_PRECEDERS_EN:
                continue
            return True
    return False


def _has_title_win_evidence(text: str) -> bool:
    """The full title_win evidence contract (assertion OR trophy OR compound)."""
    if _has_any(text, _TITLE_WIN_BLOCKERS):
        return False
    if _has_any(text, _TITLE_WIN_TROPHY_VERBS):
        return True
    if _has_champion_assertion(text):
        return True
    masked = _mask_competition_names(text)
    return _has_any(masked, _TITLE_WIN_VERB) and _has_any(masked, _TITLE_WIN_OBJECT)


# finals_result requires BOTH a finals context AND a result signal (issue #60):
# a knockout-stage preview or feature mentioning "גמר" is not a finals result.
_FINALS_CONTEXT = (
    hword("גמר"), phrase("finals"), word("final"), phrase("championship game"),
    phrase("championship series"),
)
_RESULT_VERB = (
    phrase("ניצח"), phrase("ניצחה"), phrase("ניצחו"),
    phrase("הפסיד"), phrase("הפסידה"), phrase("הפסידו"),
    phrase("הביס"), phrase("הביסה"),   # routed/crushed — a genuine result verb (#60)
    phrase("תוצאה"), phrase("beats"), phrase("beat"), phrase("defeats"),
    phrase("defeat"), word("won"), phrase("loses"), phrase("lost"), phrase("victory"),
)
_RESULT_SIGNAL = _RESULT_VERB + (
    phrase("ניצחון"), phrase("הפסד"),
    phrase("מנצח"),      # present-tense win forms (מנצח/מנצחת/מנצחים)
    regex(r"\d+[:-]\d+"),  # an explicit score ("2:2", "4-1") is a result signal
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
    # title_win is validated by _has_title_win_evidence() (assertion semantics,
    # issue #60) — this entry exists so the event type is known to the table;
    # required_any is replaced by the custom check in validate_event_evidence.
    "title_win": EventEvidenceRule(
        required_any=((),),
        blockers=_TITLE_WIN_BLOCKERS,
        confirmed_any=_TITLE_WIN_TROPHY_VERBS + _TITLE_WIN_VERB,
    ),
    "finals_result": EventEvidenceRule(
        required_any=(_FINALS_CONTEXT, _RESULT_SIGNAL),
        blockers=_TITLE_WIN_BLOCKERS,
        confirmed_any=(hword("גמר"), phrase("finals"), phrase("championship game")),
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

    if event_type == "title_win":
        # Assertion semantics (issue #60): champion-noun assertion, trophy
        # verb, or win-verb + championship-object compound — never a champion
        # word alone, an epithet, or a competition name.
        if not _has_title_win_evidence(normalized):
            return EventEvidence("news", False, "confirmed")
        # Validity is now assertion-strict, so a rules-sourced title_win is
        # confirmed by construction; LLM proposals remain weak per contract.
        return EventEvidence("title_win", True, "weak" if source == "llm" else "confirmed")

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

