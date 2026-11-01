"""Census #3 targeted checks (#241; scripts/census_checks.py) — the pure half.

Each check must pick exactly the rows its question is about, so the owner reads the right
list. No DB: rows are plain dicts, and the executive resolver is the real taxonomy one.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for `scripts.*` (as test_208 does)

from scripts.census_checks import (  # noqa: E402
    classification_path,
    club_governance_check,
    cup_check,
    exec_check,
    metrics_by_path,
    resolve_executives,
    run_checks,
    stored_snapshot,
    subtitle_ahead_check,
    usable_ratings,
)


def _row(i, title="כותרת", subtitle="", event_type="news", decision="feed", competitions=(),
         path="rules_only"):
    return {
        "id": f"rss_{i}", "title": title, "subtitle": subtitle, "source": "walla_sport",
        "sport": "basketball", "event_type": event_type, "decision": decision,
        "matched_event_rule": None, "entity_ids": [], "competitions": list(competitions), "path": path,
    }


def test_club_governance_lists_only_its_pushes():
    rows = [_row(1, event_type="club_governance", decision="push"),
            _row(2, event_type="club_governance", decision="high_feed"),
            _row(3, event_type="signing", decision="push")]
    governance, pushes = club_governance_check(rows)
    assert [r["id"] for r in governance] == ["rss_1", "rss_2"]
    assert [r["id"] for r in pushes] == ["rss_1"]


def test_cups_by_competition_or_by_name_and_hidden_ones_flagged():
    rows = [_row(1, competitions=["comp:ibl", "comp:winner_cup"], decision="feed"),
            _row(2, title="מכבי זכתה בסופרקאפ", decision="hidden"),
            _row(3, subtitle="רבע גמר גביע ווינר", decision="low_feed"),
            _row(4, title="גביע המדינה בכדורגל", decision="hidden"),       # football: not this check
            _row(5, competitions=["comp:eurocup"], decision="hidden")]     # EuroCup is a league
    cups, hidden = cup_check(rows)
    assert [r["id"] for r in cups] == ["rss_1", "rss_2", "rss_3"]
    assert [r["id"] for r in hidden] == ["rss_2"]


def test_subtitle_only_ahead_flags_rows_still_typed_schedule():
    rows = [_row(1, title="לקראת הדרבי", event_type="schedule", decision="hidden"),  # title: a fixture
            _row(2, subtitle="לקראת העונה", event_type="schedule", decision="hidden"),
            _row(3, subtitle="לקראת העונה", event_type="news", decision="hidden"),
            _row(4, subtitle="בלי שום רמז", event_type="schedule", decision="hidden")]
    ahead, still_schedule = subtitle_ahead_check(rows)
    assert [r["id"] for r in ahead] == ["rss_2", "rss_3"]
    assert [r["id"] for r in still_schedule] == ["rss_2"]


def test_executives_use_the_real_resolver_and_keep_title_and_subtitle_apart():
    rows = [_row(1, title='ריצ\'רד דיץ: "ההודעה מטעה"'),
            _row(2, title="מכבי ת\"א הודיעה", subtitle="שמעון מזרחי הגיב"),
            _row(3, title="רטקו מלאדיץ' נבחר"),        # "דיץ" inside a word: not Dietz
            _row(4, title="אבי מזרחי חזר לאימונים")]   # bare surname: not the chairman
    found = {r["id"]: r for r in exec_check(rows, resolve_executives)}
    assert set(found) == {"rss_1", "rss_2"}
    assert found["rss_1"]["exec_in_title"] == ["exec:richard_dietz"]
    assert found["rss_2"]["exec_in_title"] == [] and found["rss_2"]["exec_in_subtitle"] == ["exec:shimon_mizrahi"]


def test_stored_snapshot_covers_sample_rows_only_and_feeds_the_census_metrics():
    # eval_stats.py census and rate_census.py review --snapshot read this shape; the metric
    # definitions come from corpus_rerun_diff, so feed it the real function.
    from scripts.corpus_rerun_diff import census_metrics

    rows = [_row(1, decision="push"), _row(2, decision="hidden"), _row(3, decision="feed"),
            _row(9, decision="push")]                       # outside the sample
    snap = stored_snapshot(rows, {"rss_1", "rss_2", "rss_3"})
    assert set(snap) == {"rss_1", "rss_2", "rss_3"}
    assert snap["rss_1"] == {"guy": "push", "sport": "basketball", "event": "news", "path": "rules_only"}
    m = census_metrics(snap, {"rss_1": "push", "rss_2": "feed", "rss_3": "hide", "rss_9": "push"})
    # The out-of-sample push rating cannot meet a decision through the snapshot.
    assert m["rated"] == 3 and m["push_recall"] == (1, 1)
    assert m["feed_plus_recall"] == (1, 2) and m["shown_precision"] == (1, 2)
    assert set(stored_snapshot(rows, {"rss_1"}, "casual_deni_fan")["rss_1"]) == {"deni", "sport", "event", "path"}


def test_usable_ratings_refuses_out_of_sample_rows():
    with pytest.raises(ValueError, match="outside the sample"):
        usable_ratings({"rss_1": "feed", "rss_9": "push"}, {"rss_1"}, set())


def test_usable_ratings_drops_held_out_unless_final_evaluation():
    ratings = {"rss_1": "feed", "rss_2": "hide"}
    assert usable_ratings(ratings, {"rss_1", "rss_2"}, {"rss_2"}) == ({"rss_1": "feed"}, 1)
    assert usable_ratings(ratings, {"rss_1", "rss_2"}, {"rss_2"}, final_heldout_eval=True) == (ratings, 0)


def test_classification_path_groups_the_stored_values():
    assert classification_path("llm") == classification_path("llm+rules_guardrail") == "llm_success"
    assert classification_path("rules") == classification_path(None) == "rules_only"
    assert classification_path("rules_fallback_after_llm_failure") == "fallback_llm_failure"
    assert classification_path("rules_fallback_low_confidence") == "fallback_low_confidence"
    assert classification_path("something_new") == "other"


def test_metrics_by_path_reports_every_metric_for_all_rows_and_each_path():
    rows = [_row(1, decision="push", path="llm_success"),
            _row(2, decision="hidden", path="fallback_llm_failure"),
            _row(3, decision="feed", path="fallback_llm_failure"),
            _row(4, decision="hidden", path="rules_only")]
    snap = stored_snapshot(rows, {r["id"] for r in rows})
    ratings = {"rss_1": "push", "rss_2": "high", "rss_3": "feed", "rss_4": "hide"}
    by_path = metrics_by_path(snap, ratings)
    assert list(by_path) == ["all", "llm_success", "rules_only", "fallback_llm_failure"]
    assert by_path["all"]["rated"] == 4 and by_path["all"]["exact"] == 3
    failure = by_path["fallback_llm_failure"]
    assert failure["rated"] == 2 and failure["feed_plus_recall"] == (1, 2)  # the wanted row it hid
    assert failure["shown_precision"] == (1, 1) and failure["push_recall"] == (0, 0)
    for m in by_path.values():
        assert set(m) == {"rated", "exact", "shown_precision", "feed_plus_recall", "push_precision", "push_recall"}


def test_run_checks_annotates_sample_membership_and_owner_rating():
    rows = [_row(1, event_type="club_governance", decision="push"),
            _row(2, event_type="club_governance", decision="feed")]
    report = run_checks(rows, {"rss_1", "rss_2"}, {"rss_1": "push"}, lambda text, source: [])
    assert report["cohort"] == 2
    gov = report["club_governance"]
    assert gov["n"] == 2 and gov["decisions"] == {"push": 1, "feed": 1} and gov["owner"] == {"push": 1}
    assert gov["pushes"][0]["owner"] == "push" and gov["pushes"][0]["in_sample"] is True
