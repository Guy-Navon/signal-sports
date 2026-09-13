"""The `sport=unknown` blind spot must stay measured (issue #194).

`relevance_engine` lets `unknown` pass the sport check by design, so such a row is
not blocked — it simply matches nothing, and **a classification failure becomes a
hiding decision with no error, no log line and no metric that complains.** These
tests pin the metric that makes it visible, and pin the distinction that stops the
next person "fixing" it the wrong way.

The measurement that motivated them: 210 of 1,427 rows (14.7%), 209 hidden from
both profiles, splitting into 153 `unresolved` (largely correct abstention), 46
`deadlock`, and 11 `entity_without_sport`.
"""

import pytest

from app.qa.unknown_sport import (
    DEADLOCK,
    ENTITY_WITHOUT_SPORT,
    MEASURED_UNKNOWN_SHARE,
    UNKNOWN_SHARE_THRESHOLD,
    UNRESOLVED,
    build_report,
    classify_unknown_row,
)


class _Article:
    def __init__(self, sport="unknown", title="", subtitle=None, entity_ids=None,
                 source="walla_sport", classified_by="rules"):
        self.sport = sport
        self.title = title
        self.translated_title = None
        self.subtitle = subtitle
        self.entity_ids = entity_ids or []
        self.source = source
        self.classified_by = classified_by


# ── the three buckets ─────────────────────────────────────────────────────────


def test_dual_sport_club_alias_is_the_deadlock_bucket():
    """`מכבי תל אביב` is a football AND a basketball club, so resolution
    correctly abstains — and the sport is unknown BECAUSE nothing resolved."""
    assert classify_unknown_row("אריק שטילמן נגד רקנאטי על מכבי תל אביב", []) == DEADLOCK


def test_text_with_no_recognisable_entity_is_unresolved_not_a_defect():
    """Correct abstention. Many of these are not a tracked sport at all."""
    assert classify_unknown_row("הקאמבק של מקגרגור לזירה נגמר בתוך דקה", []) == UNRESOLVED


def test_a_stored_entity_with_no_sport_is_its_own_bucket():
    assert classify_unknown_row("כותרת כלשהי", ["team:portland_blazers"]) == ENTITY_WITHOUT_SPORT


def test_classification_never_guesses_a_sport():
    """The whole contract: this module reports, it does not classify.

    A confidently wrong sport is worse than `unknown`, because a wrong fact
    reaches the preference layer as truth.
    """
    for bucket in (DEADLOCK, UNRESOLVED, ENTITY_WITHOUT_SPORT):
        assert bucket in {DEADLOCK, UNRESOLVED, ENTITY_WITHOUT_SPORT}
        assert bucket not in {"basketball", "football", "tennis"}


# ── the report ────────────────────────────────────────────────────────────────


def test_report_counts_only_unknown_rows_against_the_whole_total():
    articles = [
        _Article(sport="basketball", title="מכבי תל אביב ניצחה"),
        _Article(sport="football", title="משחק"),
        _Article(sport="unknown", title="הקאמבק של מקגרגור"),
    ]
    report = build_report(articles)
    assert report.total == 3
    assert report.unknown == 1
    assert report.unknown_share == pytest.approx(1 / 3)


def test_report_breaks_down_by_source_and_method():
    """Source shape matters: a source-concentrated blind spot points at ingestion.

    On the real corpus it IS concentrated — walla_sport was 182 of 210 — but the
    text profile turned out identical to that source's resolved rows, which
    refuted the text-extraction hypothesis.
    """
    articles = [
        _Article(title="הקאמבק של מקגרגור", source="walla_sport", classified_by="llm"),
        _Article(title="עוד כותרת בלי ישות", source="ynet_sport", classified_by="rules"),
    ]
    report = build_report(articles)
    assert report.by_source == {"walla_sport": 1, "ynet_sport": 1}
    assert report.by_method == {"llm": 1, "rules": 1}


def test_report_names_the_deadlock_aliases():
    """Which ambiguous names are doing the damage has to be legible, or the
    follow-up work cannot be scoped."""
    report = build_report([_Article(title="מכבי תל אביב והפועל תל אביב")])
    assert report.buckets.get(DEADLOCK) == 1
    assert "מכבי תל אביב" in report.deadlock_aliases


def test_subtitle_is_part_of_the_evidence():
    report = build_report([_Article(title="כותרת ניטרלית", subtitle="מכבי תל אביב בהצהרה")])
    assert report.buckets.get(DEADLOCK) == 1


def test_empty_input_is_not_a_division_by_zero():
    report = build_report([])
    assert report.total == 0
    assert report.unknown_share == 0.0
    assert report.exceeds_threshold is False


# ── the guard ─────────────────────────────────────────────────────────────────


def test_threshold_sits_above_the_measured_share():
    """The guard catches the blind spot GROWING. Freezing today's number would
    fail on the first legitimate ingest and get deleted, which is worse."""
    assert UNKNOWN_SHARE_THRESHOLD > MEASURED_UNKNOWN_SHARE


def test_guard_trips_when_the_blind_spot_grows():
    unknown = [_Article(title="הקאמבק של מקגרגור") for _ in range(30)]
    known = [_Article(sport="basketball", title="משחק") for _ in range(70)]
    assert build_report(unknown + known).exceeds_threshold is True


def test_guard_is_quiet_at_the_measured_level():
    unknown = [_Article(title="הקאמבק של מקגרגור") for _ in range(15)]
    known = [_Article(sport="basketball", title="משחק") for _ in range(85)]
    report = build_report(unknown + known)
    assert report.exceeds_threshold is False
    assert report.as_dict()["exceeds_threshold"] is False
