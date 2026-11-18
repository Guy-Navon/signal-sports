"""Event-type proposals; every proposal is validated by event_evidence before it stands."""

import re

from app.classification.event_evidence import (
    PREVAILED_OVER_PATTERN,
    SUCCUMBED_TO_PATTERN,
    EventEvidence,
    reads_as_champion_epithet,
    validate_event_evidence,
)
from app.ingestion.classifier_rules.matching import _has, _has_word


# ── Event type detection ──────────────────────────────────────────────────────

_GRAND_SLAM_KW = (
    "grand slam", "גראנד סלאם",
    # Specific Grand Slam names: a win at any of these is grand_slam_winner
    "roland garros", "רולאן גארוס", "french open",
    "wimbledon", "וימבלדון",
    "us open", 'ארה"ב הפתוחה', 'ארה״ב הפתוחה',  # US Open in Hebrew (#225)
    "australian open", "אליפות אוסטרליה",
)
# Hebrew champion NOUNS are included here (#133) so a slam win phrased "סינר אלוף
# ווימבלדון" is PROPOSED at all — the proposal list must mirror the validation
# table (the #138 lesson). This layer is deliberately high-recall: the epithet /
# elimination / aspiration filtering is validation's job
# (`_has_grand_slam_win_evidence`), not this tuple's.
_GRAND_SLAM_WIN_KW = (
    "winner", "wins", "won", "champion", "זוכה", "זכה", "זכתה",
    "אלוף", "אלופה", "אלופת", "אלופות",
)

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
    "על סף סיכום",           # on the verge of agreement (#60, golden C9)
    # Anticipated completion is not completion (#138) — the #125 aspiration law applied
    # to transfers. "צפויה לצרף את X" (expected to add X) reports a deal in progress;
    # without these the signing keyword in a secondary clause wins and one source lands
    # on signing while the others land on negotiation for the SAME event (Storonski).
    "צפוי לצרף", "צפויה לצרף", "צפוי להצטרף", "צפויה להצטרף",
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

_RELEASE_KW = (
    "שוחרר", "שוחררה", "שוחררו",
    "שחררה את", "שחרר את",
    # Departure forms — the proposal list must mirror the validation table (#138).
    # The #113 fix taught VALIDATION the masculine "נפרד מ", but this proposal list
    # still knew only the feminine — so a masculine farewell was never PROPOSED as a
    # release, validated nothing, and fell through to news while another source's
    # feminine/explicit form became release: a cross-source event-state split on the
    # SAME event. "פרידה" covers the construct/definite forms ("מילות הפרידה",
    # "פוסט פרידה") that the contiguous "פרידה מ" phrase missed.
    "נפרדה מ", "נפרד מ", "נפרדו מ",
    "עוזב את", "עוזבת את", "פרידה",
    "released", "waived", "cut by", "roster cuts",
)

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
    # Proposal only: event_evidence keeps a "שידור" only when it announces a broadcast (#406).
    'לו"ז', "לוח משחקים", "שידורים", "שידור", "ישודר", "תשודר", "לקראת", "תאריכים",
    "schedule", "preview", "upcoming", "fixture", "fixtures",
)

_RESULT_KW = (
    "ניצח", "הפסיד", "הביס", "תוצאה",
    "beats", "beat", "defeats", "defeat", "won", "loses", "lost", "victory",
)
_REGULAR_SEASON_KW = ("ליגה הרגילה", "regular season")


def _detect_event_evidence(text: str, sport: str) -> EventEvidence:
    # Death/accident guard: prevent "נהרג"/"נפטר" articles from triggering title_win
    # via incidental championship words (e.g. "נהרג אלוף הגביע" → "news", not "title_win").
    if _has(text, *_DEATH_ACCIDENT_KW):
        return validate_event_evidence("news", text, source="rules")

    proposals: list[str] = []

    # Editorial formats are existing product types. Positive format evidence
    # prevents a background transaction in an analysis from claiming the story.
    for event in ("relocation", "analysis", "interview"):
        if validate_event_evidence(event, text, sport=sport).valid:
            proposals.append(event)

    # Club governance (#229) is proposed before the transfer cycle: an ownership deal
    # says "רכשה" / "סיכמו" and must not become a signing or a negotiation. Its
    # vocabulary is narrow enough (event_evidence._CLUB_GOVERNANCE) to go first.
    if validate_event_evidence("club_governance", text, sport=sport).valid:
        proposals.append("club_governance")

    # Grand slam winner: needs BOTH the tournament context AND a win signal.
    if sport == "tennis" and _has(text, *_GRAND_SLAM_KW) and _has(text, *_GRAND_SLAM_WIN_KW):
        proposals.append("grand_slam_winner")

    # Transfer-cycle events are proposed BEFORE championship events (issue #60):
    # a headline carrying both negotiation evidence and a champion epithet
    # ("מתקרב לאלופת איטליה") is a transfer story, not a title win.

    # Release / roster cut. Checked before signing so "released" does not become
    # a generic transaction.
    if _has(text, *_RELEASE_KW):
        proposals.append("release")

    # Negotiation — checked BEFORE signing because "על סף חתימה" (on the verge of
    # signing) contains "חתימה" which would otherwise trigger signing detection first.
    if _has(text, *_NEGOTIATION_KW) or any(_has_word(text, w) for w in _NEGOTIATION_WORD_KW):
        proposals.append("negotiation")

    # Signing
    if _has(text, *_SIGNING_KW) or any(_has_word(text, w) for w in _SIGNING_WORD_KW):
        proposals.append("signing")

    # Candidate / monitoring
    if _has(text, *_CANDIDATE_KW) or any(_has_word(text, w) for w in _CANDIDATE_WORD_KW):
        proposals.append("candidate")

    # Injury
    if _has(text, *_INJURY_KW):
        proposals.append("injury")

    # Trade
    if _has(text, *_TRADE_KW) or any(_has_word(text, w) for w in _TRADE_WORD_KW):
        proposals.append("major_trade")

    # Finals / championship result — proposals only; validation applies the
    # assertion-semantics contract (event_evidence, issue #60).
    if _has(text, *_FINALS_KW):
        proposals.append("finals_result")
    if _has(text, *_TITLE_WIN_UNAMBIGUOUS_KW):
        proposals.append("title_win")
    if _has(text, *_WIN_VERB_HE) and _has(text, *_WIN_CHAMPIONSHIP_CTX_KW):
        proposals.append("title_win")

    # Playoff
    if _has(text, *_PLAYOFF_KW):
        proposals.append("playoff_result")

    # Tennis early round
    if sport == "tennis" and _has(text, *_EARLY_ROUND_TENNIS_KW):
        proposals.append("early_round_result")

    # Regular season result
    if _has(text, *_REGULAR_SEASON_KW):
        proposals.append("regular_season_result")

    # Schedule / preview
    if _has(text, *_SCHEDULE_KW):
        proposals.append("schedule")

    # Generic match result
    if (_has(text, *_RESULT_KW) or re.search(PREVAILED_OVER_PATTERN, text)
            or re.search(SUCCUMBED_TO_PATTERN, text)):
        proposals.append("match_result")

    for proposal in proposals:
        evidence = validate_event_evidence(proposal, text, source="rules", sport=sport)
        if evidence.valid:
            return evidence

    return validate_event_evidence("news", text, source="rules", sport=sport)


def detect_article_event(title: str, subtitle: str, sport: str) -> EventEvidence:
    """Title-first event routing, shared by ingestion and targeted corrections."""
    title, subtitle = title.lower(), subtitle.lower()
    evidence = _detect_event_evidence(title, sport)
    if evidence.event_type != "news" or not subtitle:
        return evidence
    # Relocation may assert the coordinated franchise in the title and its
    # physical home move in the subtitle. Neither half alone proves the event.
    relocation = validate_event_evidence("relocation", title + " " + subtitle, sport=sport)
    evidence = relocation if relocation.valid else _detect_event_evidence(subtitle, sport)
    # A win word in the subtitle of a story about a champion describes that champion ("ניצחונו
    # הראשון כאלוף העולם"): it reports no game (#403, the #418 shape). Other events stand.
    if evidence.event_type == "match_result" and (
        reads_as_champion_epithet(title) or reads_as_champion_epithet(subtitle)
    ):
        return validate_event_evidence("news", title, source="rules", sport=sport)
    if evidence.certainty == "confirmed" and evidence.event_type != "news":
        return EventEvidence(evidence.event_type, True, "probable")
    return evidence
