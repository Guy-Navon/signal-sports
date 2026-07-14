"""
D5 (#125) — `title_win` false positives.

Driven by `feed_dedup_cases.json`: articles frozen verbatim from Guy's REAL ranked feed, where
three stories were classified as actual title wins while nobody had won anything.

Each was admitted by a DIFFERENT branch of the evidence contract, so this is three distinct
class bugs, not one:

  1. CANCELLED transfer   → CHAMPION_ASSERTION. The subtitle says "נשיא אלופת [איטליה]" —
                            a champion noun describing a THIRD PARTY's role (Inter's *president*).
                            Meanwhile the story itself is "מבוטלת" — the deal is OFF.
  2. OPENING TRAINING     → TROPHY_VERB "הניף". The crowd "והניף את השחקנים" — lifted the
                            PLAYERS. A lift with no trophy is not a title.
  3. ASPIRATIONAL KANE    → TROPHY_VERB "הניף", matched as a SUBSTRING of "להניף" (the
                            infinitive, "TO lift"). He has won nothing; his brother hopes.

The fixes are class rules — a lift needs a trophy, an infinitive/wish is never a completed
event, a cancelled thing did not happen, a role noun marks an epithet. No headline patches.
"""

import json
from pathlib import Path

import pytest

from app.classification.event_evidence import (
    _has_champion_assertion,
    _has_title_win_evidence,
    validate_event_evidence,
)

FIXTURES = Path(__file__).parent / "fixtures" / "feed_dedup_cases.json"


@pytest.fixture(scope="module")
def cases():
    with FIXTURES.open(encoding="utf-8") as fh:
        return json.load(fh)


def _group(cases, gid):
    return next(g for g in cases["title_win_false_positives"] if g["id"] == gid)


def _text(article) -> str:
    return f"{article['title']} {article.get('subtitle', '')}"


def _articles(cases, gid):
    return _group(cases, gid)["articles"]


# ── The three frozen false positives ─────────────────────────────────────────

class TestFrozenFalsePositives:
    """Every frozen FP must be demoted, via the exact path the real classifier takes."""

    @pytest.mark.parametrize(
        "gid",
        ["titlewin_cancelled_transfer", "titlewin_opening_training", "titlewin_aspirational_kane"],
    )
    def test_no_frozen_false_positive_survives(self, cases, gid):
        for a in _articles(cases, gid):
            expected = a.get("expected_event_type", "news")
            got = validate_event_evidence("title_win", _text(a), source="llm")
            assert (got.event_type == "title_win") == (expected == "title_win"), (
                f"[{a['source']}] {a['title'][:60]!r} → {got.event_type} (expected {expected})"
            )

    def test_a_cancelled_deal_is_not_a_title_win(self, cases):
        """The story is 'עסקת ענאן חלאילי לאינטר מבוטלת' — the transfer is CANCELLED."""
        a = _articles(cases, "titlewin_cancelled_transfer")[0]
        assert "מבוטלת" in _text(a)
        assert not _has_title_win_evidence(_text(a))

    def test_a_role_noun_marks_the_champion_word_as_a_third_party_epithet(self, cases):
        """'נשיא אלופת …' = 'the PRESIDENT OF the champions of …'. The champion word describes
        someone else's job title; nobody in this story just won anything."""
        a = _articles(cases, "titlewin_cancelled_transfer")[0]
        assert "נשיא אלופת" in _text(a)
        assert not _has_champion_assertion(_text(a))
        # …and the rule generalises beyond this one article.
        assert not _has_champion_assertion("מאמן אלופת אירופה: נשחק בלי לחץ")
        assert not _has_champion_assertion("אוהדי אלופת המדינה חגגו בכיכר")

    def test_lifting_the_players_is_not_lifting_a_trophy(self, cases):
        """'הקהל … והניף את השחקנים' at an opening training session. A lift is title evidence
        only when what is lifted is a TROPHY."""
        a = next(
            x for x in _articles(cases, "titlewin_opening_training")
            if "הניף" in _text(x)
        )
        assert "הניף" in _text(a) and "גביע" not in _text(a)
        assert not _has_title_win_evidence(_text(a))

    def test_an_infinitive_is_never_a_completed_title_win(self, cases):
        """'מגיע לאחי הארי קיין להניף את גביע העולם' — he DESERVES TO lift the World Cup.
        The bug: the past-tense 'הניף' is a substring of the infinitive 'להניף', and a trophy
        noun ('גביע העולם') really is present — so the compound fired on pure aspiration."""
        a = _articles(cases, "titlewin_aspirational_kane")[0]
        text = _text(a)
        assert "להניף" in text and "גביע" in text, "the trap needs both halves present"
        assert not _has_title_win_evidence(text)

    def test_the_contrast_article_was_always_correct(self, cases):
        """The walla version of the SAME training story never claimed a title. It must stay
        `news` — proving the fix did not simply blunt the whole rule."""
        contrast = [
            a for a in _articles(cases, "titlewin_opening_training")
            if a.get("expected_event_type", "news") == "news" and "הניף" not in _text(a)
        ]
        assert contrast, "the contrast card is part of the frozen evidence"
        for a in contrast:
            assert validate_event_evidence("title_win", _text(a), source="llm").event_type == "news"


# ── Positive controls: a real title win must still be a title win ────────────

class TestGenuineTitleWinsSurvive:
    """The whole risk of a false-positive fix is silently killing the true positives."""

    @pytest.mark.parametrize("text", [
        "מכבי תל אביב זכתה באליפות הליגה",
        "אולימפיאקוס זכה בתואר אחרי שלוש שנים",
        "הפועל ירושלים הניפה את גביע המדינה אחרי ניצחון דרמטי",
        "ריאל מדריד הוכתרה כאלופת יורוליג",
        "הפועל תל אביב הוכתרה כאלופת המדינה",
        "מכבי חיפה אלופת המדינה",
        "Real Madrid lifted the EuroLeague trophy after a dramatic final",
        "Panathinaikos crowned champions of Greece",
    ])
    def test_real_title_wins_still_validate(self, text):
        assert _has_title_win_evidence(text), f"KILLED A TRUE POSITIVE: {text}"
        assert validate_event_evidence("title_win", text, source="llm").event_type == "title_win"

    def test_a_lift_WITH_a_trophy_still_counts(self):
        """The narrow half of the lift rule: the verb still works, it just needs its object."""
        assert _has_title_win_evidence("הפועל הניפה את הגביע")
        assert not _has_title_win_evidence("הקהל הניף את השחקנים")

    def test_the_construct_crowning_form_is_covered(self):
        """A pre-existing gap this fix closes: the crowning list held only the ABSOLUTE forms
        ('הוכתרה כאלופה'), so the ordinary CONSTRUCT form ('הוכתרה כאלופת יורוליג' — crowned
        champion-OF the EuroLeague) matched nothing and a genuine title win was missed."""
        assert _has_title_win_evidence("ריאל מדריד הוכתרה כאלופת יורוליג")

    def test_crowning_still_requires_a_champion_noun(self):
        """'הוכתר' alone is not a title — you can be crowned the scoring king."""
        assert not _has_title_win_evidence("דונצ'יץ' הוכתר כמלך הסלים של העונה")


# ── Title locality: the loophole the live corpus exposed ─────────────────────

class TestTitleWinMustBeAssertedInTheTitle:
    """The three frozen FPs were only PART of the harm.

    Auditing every `title_win` in the live corpus showed 8 of 10 were false. The other five
    all failed the same way: a championship word sitting in a SUBTITLE clause as an epithet
    for a third party — "מול אנגליה אלופת העולם" (against England, the world champions),
    "אלופת תורכמניסטן ארקדאג" (the team Hapoel Haifa will FACE) — while the headline was
    about a coach's message, a training camp, or a broken running record.

    Structurally an epithet is indistinguishable from a real assertion; only its POSITION
    separates them. #60 already built the title-first ladder but used it only to cap
    CERTAINTY, leaving the event valid. Certainty separated the corpus perfectly (every
    genuine win was `confirmed`/title-asserted; every false one was `probable`/subtitle-only)
    — the signal was there, it just was not enforced.
    """

    def _finalize(self, title: str, subtitle: str, sport: str = "football"):
        from app.classification.facts import ArticleFacts
        from app.classification.llm_result import LLMClassificationResult
        from app.ingestion.ingestion_service import _apply_post_facts_event_validation

        result = LLMClassificationResult(
            sport=sport, league=None, entities=[], event_type="title_win",
            importance="very_high", confidence=0.9, reason="test",
        )
        result.event_certainty = "probable"
        facts = ArticleFacts(
            sport=sport, league=None, entities=[], primary_competition=None,
            article_competitions=[], entity_ids=[],
        )
        return _apply_post_facts_event_validation(
            result, facts=facts,
            title_lower=title.lower(), subtitle_lower=subtitle.lower(),
            source_id="test_source",
        )

    def test_title_win_is_registered_as_title_local(self):
        from app.classification.event_evidence import TITLE_LOCAL_EVENT_TYPES

        assert "title_win" in TITLE_LOCAL_EVENT_TYPES

    @pytest.mark.parametrize("title,subtitle", [
        # A champion EPITHET for the opponent, in a story about a coach's message.
        ("מה יהיה בלי מסי? מאמן ארגנטינה העביר לשחקנים מסר חד וברור",
         "סקאלוני יודע שמול אנגליה אלופת העולם תצטרך להיראות טוב יותר"),
        # A champion epithet for a team they will FACE, in a story about a training camp.
        ("הפועל חיפה תפגוש את הקבוצה הכי מושחתת בעולם",
         "ביום רביעי תשחק מול אלופת תורכמניסטן ארקדאג"),
        # A broken RECORD is not a title.
        ("ערב היסטורי: מתן עברי ניפץ את השיא הישראלי",
         "הרץ קבע 3:34.51 דקות ושיפר את שיאו הקודם"),
    ])
    def test_subtitle_only_championship_vocabulary_is_not_a_title_win(self, title, subtitle):
        assert self._finalize(title, subtitle).event_type == "news"

    def test_a_title_asserted_win_survives_the_gate(self, cases):
        """The positive control at the PIPELINE level: the real Sinner headline must still
        come out of the gate as a title_win — and keep `confirmed` certainty."""
        out = self._finalize(
            "סינר שוב אלוף ווימבלדון: ניצח את זברב והגן על התואר",
            "האיטלקי חזר מפיגור מערכה בדרך לניצחון דומיננטי", sport="tennis",
        )
        assert out.event_type == "title_win"
        assert out.event_certainty == "confirmed"

    def test_non_title_local_events_still_only_cap_certainty(self):
        """The stronger rule must apply ONLY to title-local types. A signing reported in the
        subtitle is still a real signing — it just cannot claim `confirmed` (#60)."""
        from app.classification.facts import ArticleFacts
        from app.classification.llm_result import LLMClassificationResult
        from app.ingestion.ingestion_service import _apply_post_facts_event_validation

        result = LLMClassificationResult(
            sport="basketball", league=None, entities=[], event_type="signing",
            importance="high", confidence=0.9, reason="test",
        )
        result.event_certainty = "probable"
        facts = ArticleFacts(
            sport="basketball", league=None, entities=[], primary_competition=None,
            article_competitions=[], entity_ids=[],
        )
        out = _apply_post_facts_event_validation(
            result, facts=facts,
            title_lower="ההודעה הרשמית הגיעה",
            subtitle_lower="מכבי תל אביב חתמה עם השחקן לשלוש שנים",
            source_id="test_source",
        )
        assert out.event_type == "signing", "a subtitle-only signing is still a signing"
        assert out.event_certainty == "probable", "but it cannot be confirmed (#60)"


# ── Existing guards must not regress ─────────────────────────────────────────

class TestPriorTitleWinGuardsHold:
    def test_medal_placement_is_still_not_a_title(self):
        """#63: a bronze medal is a placement, not a title win."""
        assert not _has_title_win_evidence("מכבי זכתה במדליית ארד")

    def test_a_candidate_is_still_not_a_winner(self):
        assert not _has_title_win_evidence("מכבי תל אביב מועמדת לזכות באליפות")

    def test_a_competition_name_is_still_not_evidence(self):
        """'ליגת האלופות' contains a champion noun and means nothing about winning."""
        assert not _has_title_win_evidence("מכבי תל אביב תפתח את ליגת האלופות מול פנאתינייקוס")
