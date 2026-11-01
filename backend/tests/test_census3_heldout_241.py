"""Census #3's sealed held-out half (#241).

The owner rates all 300 rows blind; ``rate_census.py seal`` then moves the held-out half's
ratings into their own file, so every development path (review, checks, calibration,
scoring) reads the fit half only. Pins: sealing refuses incomplete or out-of-sample
ratings; the page never reveals the split and never re-asks a sealed row; review excludes
held-out rows; and the committed census #3 files carry the pre-registered split.
"""

import argparse
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))  # for `scripts.*` (as test_208 does)

from app.qa import census_rating as cr  # noqa: E402
from scripts import rate_census  # noqa: E402

IDS = [f"rss_{i:03d}" for i in range(6)]
HELD = {"rss_001", "rss_004", "rss_005"}


def _census(tmp_path: Path) -> tuple[Path, Path]:
    sample = {
        "meta": {"seed": 11, cr.SEALED_META_KEY: {
            "ids": "held.json", "ratings": "held_ratings.json", "fit_raw": "fit_raw.json"}},
        "profiles": {"guy": {"items": [{"id": i, "title": f"t{i}", "engine_decision": "feed"} for i in IDS]}},
    }
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    (tmp_path / "held.json").write_text(json.dumps(sorted(HELD)), encoding="utf-8")
    ratings_path = tmp_path / "ratings.json"
    ratings = {i: "hide" for i in reversed(IDS)}  # rating order differs from id order
    ratings_path.write_text(json.dumps({"generated": "g", "seed": 11, "ratings": {"guy": ratings}}),
                            encoding="utf-8")
    return sample_path, ratings_path


def _seal(sample_path, ratings_path):
    rate_census.cmd_seal(argparse.Namespace(sample=str(sample_path), ratings=str(ratings_path), profile="guy"))


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_seal_ratings_splits_in_rating_order():
    ratings = {"b": "feed", "a": "hide", "c": "push"}
    fit, held = cr.seal_ratings(["a", "b", "c"], {"c"}, ratings)
    assert list(fit) == ["b", "a"] and held == {"c": "push"}


def test_seal_ratings_refuses_an_incomplete_rating():
    with pytest.raises(ValueError, match="not rated"):
        cr.seal_ratings(["a", "b"], {"b"}, {"a": "feed"})


def test_seal_ratings_refuses_out_of_sample_ids():
    # An out-of-sample row (e.g. an engine push outside the sample) never enters a census score.
    with pytest.raises(ValueError, match="outside the sample"):
        cr.seal_ratings(["a"], set(), {"a": "feed", "zzz": "push"})


def test_exclude_sealed_drops_only_held_out_ids():
    kept, dropped = cr.exclude_sealed({"a": "feed", "b": "hide"}, {"b", "x"})
    assert kept == {"a": "feed"} and dropped == 1


def test_an_unsealed_census_has_no_sealed_ids(tmp_path):
    assert cr.sealed_ids({"meta": {}}, tmp_path / "s.json") == set()
    assert cr.sealed_files({"meta": {}}, tmp_path / "s.json") is None


# ── rate_census.py seal / serve / review ──────────────────────────────────────

def test_seal_moves_held_out_ratings_to_the_sealed_file(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    _seal(sample_path, ratings_path)

    fit = json.loads(ratings_path.read_text(encoding="utf-8"))
    held = json.loads((tmp_path / "held_ratings.json").read_text(encoding="utf-8"))
    assert set(fit["ratings"]["guy"]) == set(IDS) - HELD
    assert set(held["ratings"]["guy"]) == HELD
    assert fit["seed"] == held["seed"] == 11 and "sealed" in held
    # The fit file still opens as the rating store (resume, merge-review) with the same seed.
    store = cr.RatingsStore(ratings_path, seed=11, profile="guy")
    assert set(store.ratings) == set(IDS) - HELD

    with pytest.raises(SystemExit, match="already sealed"):
        _seal(sample_path, ratings_path)


def test_seal_refuses_before_every_row_is_rated(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    raw = json.loads(ratings_path.read_text(encoding="utf-8"))
    del raw["ratings"]["guy"]["rss_002"]
    ratings_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SystemExit, match="not rated"):
        _seal(sample_path, ratings_path)
    assert not (tmp_path / "held_ratings.json").exists()


def test_page_asks_every_row_before_sealing_and_never_re_asks_a_sealed_one(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    before = rate_census.serve_items(sample, sample_path, "guy")
    assert [it["id"] for it in before] == IDS
    # Blind to the split: what reaches the browser is the allow-list, with no half marker.
    assert all(set(cr.rater_view(it)) == set(cr.RATER_FIELDS) for it in before)

    _seal(sample_path, ratings_path)
    after = rate_census.serve_items(sample, sample_path, "guy")
    assert {it["id"] for it in after} == set(IDS) - HELD
    store = cr.RatingsStore(ratings_path, seed=11, profile="guy")
    assert store.pending(after) == []  # nothing left to ask


def test_review_never_includes_held_out_rows(tmp_path):
    # Re-rating is for rows we may act on; the held-out half is never acted on. Even an
    # unsealed ratings file must not put a held-out row into the review.
    sample_path, ratings_path = _census(tmp_path)
    out = tmp_path / "review.json"
    rate_census.cmd_review(argparse.Namespace(
        sample=str(sample_path), ratings=str(ratings_path), out=str(out),
        snapshot=None, min_gap=2, profile="guy", final_heldout_eval=False))
    review_ids = {it["id"] for it in json.loads(out.read_text(encoding="utf-8"))["profiles"]["guy"]["items"]}
    assert review_ids == set(IDS) - HELD  # feed vs hide is a 2-notch gap on every row


# ── the committed census #3 files ─────────────────────────────────────────────

def test_committed_census3_split_is_the_pre_registered_one():
    sample_path = REPO / "docs" / "qa" / "census3_sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    ids = [it["id"] for it in sample["profiles"]["guy"]["items"]]
    held = cr.sealed_ids(sample, sample_path)
    assert len(ids) == 300 and len(held) == 150 and held <= set(ids)
    # The #237 split (census_calibration_fit.split, seed 237), restated so this test does not
    # import that script (it pins DATABASE_URL at import time).
    import random
    fit = set(random.Random(237).sample(sorted(ids), len(ids) // 2))
    assert held == set(ids) - fit
    # No item carries a half marker the page could leak.
    assert all("heldout" not in json.dumps(it) and "fit" not in it for it in sample["profiles"]["guy"]["items"])
