"""Census #3 targeted checks (#241; scripts/census_checks.py) — the pure half.

Each check must pick exactly the rows its question is about, so the owner reads the right
list. No DB: rows are plain dicts, and the executive resolver is the real taxonomy one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for `scripts.*` (as test_208 does)

from scripts.census_checks import (  # noqa: E402
    club_governance_check,
    cup_check,
    exec_check,
    resolve_executives,
    run_checks,
    stored_snapshot,
    subtitle_ahead_check,
)


def _row(i, title="כותרת", subtitle="", event_type="news", decision="feed", competitions=()):
    return {
        "id": f"rss_{i}", "title": title, "subtitle": subtitle, "source": "walla_sport",
        "event_type": event_type, "decision": decision, "matched_event_rule": None,
        "entity_ids": [], "competitions": list(competitions),
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


def test_stored_snapshot_is_readable_by_the_census_metrics():
    # eval_stats.py census and rate_census.py review --snapshot read this shape; the metric
    # definitions come from corpus_rerun_diff, so feed it the real function.
    from scripts.corpus_rerun_diff import census_metrics

    rows = [_row(1, decision="push"), _row(2, decision="hidden"), _row(3, decision="feed")]
    for r in rows:
        r["sport"] = "basketball"
    snap = stored_snapshot(rows)
    assert snap["rss_1"] == {"guy": "push", "sport": "basketball", "event": "news"}
    m = census_metrics(snap, {"rss_1": "push", "rss_2": "feed", "rss_3": "hide"})
    assert m["push_recall"] == (1, 1) and m["feed_plus_recall"] == (1, 2) and m["shown_precision"] == (1, 2)
    assert set(stored_snapshot(rows, "casual_deni_fan")["rss_1"]) == {"deni", "sport", "event"}


def test_run_checks_annotates_sample_membership_and_owner_rating():
    rows = [_row(1, event_type="club_governance", decision="push"),
            _row(2, event_type="club_governance", decision="feed")]
    report = run_checks(rows, {"rss_1", "rss_2"}, {"rss_1": "push"}, lambda text, source: [])
    assert report["cohort"] == 2
    gov = report["club_governance"]
    assert gov["n"] == 2 and gov["decisions"] == {"push": 1, "feed": 1} and gov["owner"] == {"push": 1}
    assert gov["pushes"][0]["owner"] == "push" and gov["pushes"][0]["in_sample"] is True
