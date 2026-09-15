"""Census rating tool (docs/tasks/RATING_SURFACE.md) — the pure half.

Pins: the rater never sees an engine field; order is a seeded shuffle, not tier
order; the store saves after every mutation, resumes, never re-asks, and undo
pops the most recent rating. No test touches the corpus (conftest pins a temp
DB and CLASSIFICATION_PROVIDER=disabled; this module never opens a DB at all).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for `scripts.*` (as test_208 does)

from app.models.article import Article
from app.models.scoring import ScoredArticle
from app.qa import census_rating as cr


def _article(i: int, day: str, **over) -> Article:
    base = dict(
        id=f"rss_{i:04d}",
        source="sport5_sport",
        source_display_name="Sport5",
        url=f"https://example.test/{i}",
        title=f"כותרת {i}",
        subtitle=f"תת-כותרת {i}",
        published_at=datetime.fromisoformat(f"{day}T10:00:00+00:00"),
        sport="basketball",
        league="EuroLeague",
        event_type="signing",
        importance="high",
    )
    base.update(over)
    return Article(**base)


def _scored(i, day, decision="feed", **over) -> ScoredArticle:
    return ScoredArticle(
        article=_article(i, day, **over),
        decision=decision,
        matched_topic="maccabi",
        matched_event_rule="signing",
    )


# ── cohort + shape ────────────────────────────────────────────────────────────

def test_is_fresh_is_inclusive_of_the_cutoff_day():
    since = "2026-08-01"
    assert cr.is_fresh(datetime(2026, 8, 1, tzinfo=timezone.utc), since)
    assert not cr.is_fresh(datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc), since)
    assert cr.is_fresh("2026-09-13T16:00:00+00:00", since)
    assert not cr.is_fresh(None, since)


def test_build_census_excludes_the_frozen_corpus_and_is_one_stratum_at_weight_one():
    feed = [_scored(1, "2026-07-30"), _scored(2, "2026-08-01"), _scored(3, "2026-09-13", "hidden")]
    doc = cr.build_census({"guy": feed}, since="2026-08-01", seed=7, corpus_articles=3)

    block = doc["profiles"]["guy"]
    assert {it["id"] for it in block["items"]} == {"rss_0002", "rss_0003"}
    assert block["strata"] == {"census": {"population": 2, "sampled": 2, "weight": 1.0}}
    assert doc["meta"]["seed"] == 7 and doc["meta"]["since"] == "2026-08-01"


def test_census_item_matches_the_n05_sample_shape_the_scorer_reads():
    item = cr.census_item(_scored(1, "2026-08-02", "high_feed"))
    # Every key feed_ground_truth.cmd_sample emits must be present.
    for key in ("id", "stratum", "engine_decision", "matched_topic", "matched_event_rule",
                "title", "original_title", "source", "sport", "league", "event_type",
                "published_at", "url"):
        assert key in item, key
    assert item["stratum"] == "census"
    assert item["engine_decision"] == "high_feed"
    assert item["published_at"] == "2026-08-02T10:00:00+00:00"  # ISO string, JSON-safe
    json.dumps(item)


def test_order_is_a_seeded_shuffle_not_tier_order():
    # 30 items, tiers assigned in blocks: a tier-ordered output would be sorted.
    tiers = ["push"] * 5 + ["high_feed"] * 5 + ["feed"] * 10 + ["hidden"] * 10
    feed = [_scored(i, "2026-08-10", t) for i, t in enumerate(tiers)]
    a = cr.build_census({"guy": feed}, since="2026-08-01", seed=1, corpus_articles=30)
    b = cr.build_census({"guy": feed}, since="2026-08-01", seed=1, corpus_articles=30)
    c = cr.build_census({"guy": feed}, since="2026-08-01", seed=2, corpus_articles=30)

    order_a = [it["id"] for it in a["profiles"]["guy"]["items"]]
    assert order_a == [it["id"] for it in b["profiles"]["guy"]["items"]]  # reproducible
    assert order_a != [it["id"] for it in c["profiles"]["guy"]["items"]]  # seed matters
    decisions = [it["engine_decision"] for it in a["profiles"]["guy"]["items"]]
    assert decisions != tiers and decisions != sorted(tiers)  # no tier blocks


# ── the blind-rating invariant ────────────────────────────────────────────────

def test_rater_view_carries_no_engine_field():
    item = cr.census_item(_scored(1, "2026-08-02", "push"))
    view = cr.rater_view(item)
    assert set(view) == set(cr.RATER_FIELDS)
    for forbidden in cr.ENGINE_FIELDS:
        assert forbidden not in view
    assert view["title"] == "כותרת 1" and view["subtitle"] == "תת-כותרת 1"


def test_rater_view_is_an_allow_list_so_new_engine_fields_stay_hidden():
    item = cr.census_item(_scored(1, "2026-08-02")) | {"brand_new_engine_score": 0.93}
    assert "brand_new_engine_score" not in cr.rater_view(item)


# ── the store: save-every-time, resume, undo ─────────────────────────────────

def test_store_writes_the_scorer_file_shape_after_every_rating(tmp_path):
    path = tmp_path / "census_ratings.json"
    store = cr.RatingsStore(path, seed=7, profile="guy")
    assert not path.exists()

    store.rate("rss_0001", "feed")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["seed"] == 7 and raw["ratings"] == {"guy": {"rss_0001": "feed"}}
    assert "generated" in raw

    store.rate("rss_0002", "hide")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["ratings"]["guy"] == {"rss_0001": "feed", "rss_0002": "hide"}


def test_store_rejects_a_rating_outside_the_scale(tmp_path):
    store = cr.RatingsStore(tmp_path / "r.json", seed=7, profile="guy")
    with pytest.raises(ValueError):
        store.rate("rss_0001", "maybe")
    assert store.ratings == {}


def test_store_resumes_and_never_reasks_a_rated_item(tmp_path):
    path = tmp_path / "r.json"
    items = [{"id": f"rss_{i}"} for i in range(5)]
    first = cr.RatingsStore(path, seed=7, profile="guy")
    first.rate("rss_0", "push")
    first.rate("rss_1", "low")

    resumed = cr.RatingsStore(path, seed=7, profile="guy")  # "restart"
    assert resumed.ratings == {"rss_0": "push", "rss_1": "low"}
    assert [it["id"] for it in resumed.pending(items)] == ["rss_2", "rss_3", "rss_4"]
    assert resumed.generated == first.generated  # one run, one timestamp


def test_store_refuses_to_mix_seeds(tmp_path):
    path = tmp_path / "r.json"
    cr.RatingsStore(path, seed=7, profile="guy").rate("rss_0", "feed")
    with pytest.raises(ValueError):
        cr.RatingsStore(path, seed=8, profile="guy")


def test_undo_pops_the_most_recent_rating_and_persists(tmp_path):
    path = tmp_path / "r.json"
    store = cr.RatingsStore(path, seed=7, profile="guy")
    store.rate("rss_0", "push")
    store.rate("rss_1", "low")

    assert store.undo() == "rss_1"
    assert store.last() == ("rss_0", "push")
    assert json.loads(path.read_text(encoding="utf-8"))["ratings"]["guy"] == {"rss_0": "push"}
    assert store.undo() == "rss_0"
    assert store.undo() is None


def test_rerating_moves_the_item_to_the_top_of_the_undo_stack(tmp_path):
    store = cr.RatingsStore(tmp_path / "r.json", seed=7, profile="guy")
    store.rate("rss_0", "feed")
    store.rate("rss_1", "feed")
    store.rate("rss_0", "hide")  # e.g. undo-then-rate, or a deliberate change
    assert store.last() == ("rss_0", "hide")
    assert store.undo() == "rss_0"
    assert store.last() == ("rss_1", "feed")


def test_rating_keys_cover_the_scorer_vocabulary():
    from scripts import feed_ground_truth

    assert set(cr.RATINGS) == set(feed_ground_truth.RATING_TO_TIER)
    assert set(cr.RATING_KEYS) == {"1", "2", "3", "4", "5"}
