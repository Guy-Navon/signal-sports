"""Per-sport false-hide reporting (#208).

The headline `false_hide` figure can no longer resolve recall work. Hidden-football
rows carry a sampling weight of ~55.9 against ~4.2 for basketball, so **one**
football rating moves the total by ~3.9pp while one basketball row moves it by
~0.29pp. Measured on the real corpus, 2 football rows are 43% of Guy's remaining
false hide while 23 basketball rows are 36% — so improving Israeli basketball
coverage is nearly invisible in the total.

The breakdown is reported, deliberately NOT gated: a per-sport threshold would
need its own evidence and its own baseline.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.feed_ground_truth import _build_report  # noqa: E402


def _sample(items, strata):
    return {
        "meta": {"corpus_articles": 1000, "generated_at": "2026-01-01T00:00:00+00:00"},
        "profiles": {"guy": {"strata": strata, "items": items}},
    }


def _item(aid, sport, stratum, decision="hidden"):
    return {
        "id": aid, "stratum": stratum, "engine_decision": decision,
        "matched_topic": None, "matched_event_rule": None,
        "title": aid, "original_title": aid, "source": "s",
        "sport": sport, "league": None, "event_type": "news",
        "published_at": None, "url": "u",
    }


STRATA = {
    "hidden:football": {"population": 800, "sampled": 10, "weight": 80.0},
    "hidden:basketball": {"population": 100, "sampled": 25, "weight": 4.0},
}


def test_one_football_row_outweighs_many_basketball_rows():
    """The whole reason this breakdown exists."""
    items = [_item("f1", "football", "hidden:football")]
    items += [_item(f"b{i}", "basketball", "hidden:basketball") for i in range(5)]
    ratings = {"guy": {i["id"]: "feed" for i in items}}

    by_sport = _build_report(_sample(items, STRATA), ratings)["profiles"]["guy"]["false_hide_by_sport"]

    assert by_sport["football"]["rows"] == 1
    assert by_sport["basketball"]["rows"] == 5
    # 80.0 vs 5 x 4.0 = 20.0 — one football row outweighs five basketball rows.
    assert by_sport["football"]["share_of_corpus"] > by_sport["basketball"]["share_of_corpus"]
    # Heaviest sport first, so the reader sees what actually drives the number.
    assert list(by_sport) == ["football", "basketball"]


def test_counts_only_false_hides():
    """A shown row, or one the rater agreed to hide, is not a false hide."""
    items = [
        _item("hidden_wanted", "basketball", "hidden:basketball"),
        _item("hidden_agreed", "basketball", "hidden:basketball"),
        _item("shown", "basketball", "hidden:basketball", decision="feed"),
    ]
    ratings = {"guy": {"hidden_wanted": "feed", "hidden_agreed": "hide", "shown": "feed"}}

    by_sport = _build_report(_sample(items, STRATA), ratings)["profiles"]["guy"]["false_hide_by_sport"]

    assert by_sport["basketball"]["rows"] == 1


def test_wanted_rows_separates_genuinely_wanted_from_barely():
    """`low` still counts as a false hide, but it is not what recall work is for."""
    items = [
        _item("a", "basketball", "hidden:basketball"),
        _item("b", "basketball", "hidden:basketball"),
        _item("c", "basketball", "hidden:basketball"),
    ]
    ratings = {"guy": {"a": "feed", "b": "high", "c": "low"}}

    bucket = _build_report(_sample(items, STRATA), ratings)["profiles"]["guy"]["false_hide_by_sport"]["basketball"]

    assert bucket["rows"] == 3
    assert bucket["wanted_rows"] == 2


def test_missing_sport_is_reported_not_dropped():
    """`sport=unknown` is a real bucket (#194), not an absence to hide."""
    items = [_item("u", None, "hidden:basketball")]
    ratings = {"guy": {"u": "feed"}}

    by_sport = _build_report(_sample(items, STRATA), ratings)["profiles"]["guy"]["false_hide_by_sport"]

    assert by_sport["unknown"]["rows"] == 1


def test_no_false_hides_yields_an_empty_breakdown():
    items = [_item("a", "basketball", "hidden:basketball")]
    ratings = {"guy": {"a": "hide"}}

    report = _build_report(_sample(items, STRATA), ratings)["profiles"]["guy"]

    assert report["false_hide_by_sport"] == {}


@pytest.mark.parametrize("rating", ["feed", "high", "push"])
def test_every_wanted_rating_counts_as_wanted(rating):
    items = [_item("a", "basketball", "hidden:basketball")]
    bucket = _build_report(
        _sample(items, STRATA), {"guy": {"a": rating}}
    )["profiles"]["guy"]["false_hide_by_sport"]["basketball"]
    assert bucket["wanted_rows"] == 1
