"""Census #3 sealed held-out half (#241): hardening from the PR #400 review.

Extending a sealed census keeps its split; a raw fit copy for the like-for-like comparison;
a recoverable seal; sealed payloads refused by shared loaders; the page seals itself on the
last rating; held-out rows re-rated only at final evaluation; review for the Deni profile.
"""

import argparse
import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # for `scripts.*` (as test_208 does)

from app.qa import census_rating as cr  # noqa: E402
from scripts import rate_census  # noqa: E402

IDS = [f"rss_{i:03d}" for i in range(6)]
HELD = {"rss_001", "rss_004", "rss_005"}
SPEC = {"ids": "held.json", "ratings": "held_ratings.json", "fit_raw": "fit_raw.json"}


def _census(tmp_path: Path, rated: bool = True) -> tuple[Path, Path]:
    sample = {
        "meta": {"seed": 11, cr.SEALED_META_KEY: dict(SPEC)},
        "profiles": {"guy": {"items": [{"id": i, "title": f"t{i}", "engine_decision": "feed"} for i in IDS]}},
    }
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    (tmp_path / "held.json").write_text(json.dumps(sorted(HELD)), encoding="utf-8")
    ratings_path = tmp_path / "ratings.json"
    if rated:
        ratings = {i: "hide" for i in reversed(IDS)}
        ratings_path.write_text(json.dumps({"generated": "g", "seed": 11, "ratings": {"guy": ratings}}),
                                encoding="utf-8")
    return sample_path, ratings_path


def _seal(sample_path, ratings_path):
    rate_census.cmd_seal(argparse.Namespace(sample=str(sample_path), ratings=str(ratings_path), profile="guy"))


def _items(ids):
    return {"guy": {"items": [{"id": i} for i in ids]}}


def _fit(ratings_path):
    return json.loads(ratings_path.read_text(encoding="utf-8"))["ratings"]["guy"]


# ── B: extending a sealed census ──────────────────────────────────────────────

def test_build_refuses_to_overwrite_a_sealed_sample_without_carrying_the_split(tmp_path):
    sample_path, _ = _census(tmp_path)
    new_doc = {"meta": {"seed": 11}, "profiles": _items(IDS + ["rss_100"])}
    with pytest.raises(ValueError, match="--keep-sealed-from"):
        cr.carry_sealed_forward(new_doc, sample_path, None)


def test_build_carries_the_split_forward_and_new_rows_join_the_fit_half(tmp_path):
    sample_path, _ = _census(tmp_path)
    new_doc = {"meta": {"seed": 11}, "profiles": _items(IDS + ["rss_100"])}
    out = cr.carry_sealed_forward(new_doc, sample_path, sample_path)
    assert out["meta"][cr.SEALED_META_KEY] == SPEC
    assert cr.sealed_ids(out, sample_path) == HELD  # rss_100 is not held out: it is fit


def test_build_refuses_a_carried_split_the_new_sample_does_not_contain(tmp_path):
    sample_path, _ = _census(tmp_path)
    smaller = {"meta": {"seed": 11}, "profiles": _items(IDS[:2])}
    with pytest.raises(ValueError, match="held-out"):
        cr.carry_sealed_forward(smaller, sample_path, sample_path)


def test_build_refuses_to_carry_a_split_into_another_directory(tmp_path):
    sample_path, _ = _census(tmp_path)
    (tmp_path / "other").mkdir()
    new_doc = {"meta": {"seed": 11}, "profiles": _items(IDS)}
    with pytest.raises(ValueError, match="same directory"):
        cr.carry_sealed_forward(new_doc, tmp_path / "other" / "sample.json", sample_path)


def test_build_writes_a_fresh_unsealed_sample_freely(tmp_path):
    doc = {"meta": {"seed": 1}, "profiles": _items(IDS)}
    assert cr.carry_sealed_forward(doc, tmp_path / "absent.json", None) is doc


# ── F: clear errors, recoverable seal ─────────────────────────────────────────

def test_a_missing_held_out_ids_file_is_a_clear_error(tmp_path):
    sample_path, _ = _census(tmp_path)
    (tmp_path / "held.json").unlink()
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    with pytest.raises(FileNotFoundError, match="held-out ids file"):
        cr.sealed_ids(sample, sample_path)


def test_an_interrupted_seal_can_be_completed(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    full = json.loads(ratings_path.read_text(encoding="utf-8"))
    _seal(sample_path, ratings_path)
    ratings_path.write_text(json.dumps(full), encoding="utf-8")  # crash: fit file never rewritten
    (tmp_path / "fit_raw.json").unlink()
    _seal(sample_path, ratings_path)
    assert set(_fit(ratings_path)) == set(IDS) - HELD
    assert (tmp_path / "fit_raw.json").exists()
    with pytest.raises(SystemExit, match="already sealed"):
        _seal(sample_path, ratings_path)


def test_an_inconsistent_half_seal_is_refused(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    full = json.loads(ratings_path.read_text(encoding="utf-8"))
    _seal(sample_path, ratings_path)
    full["ratings"]["guy"]["rss_001"] = "push"  # differs from what the sealed file holds
    ratings_path.write_text(json.dumps(full), encoding="utf-8")
    with pytest.raises(SystemExit, match="differ"):
        _seal(sample_path, ratings_path)


# ── C: the like-for-like comparison and the final-evaluation re-rate ──────────

def test_seal_keeps_a_raw_copy_of_the_fit_half(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    _seal(sample_path, ratings_path)
    raw = json.loads((tmp_path / "fit_raw.json").read_text(encoding="utf-8"))
    assert raw["ratings"]["guy"] == _fit(ratings_path)
    assert "sealed" not in raw and raw["seed"] == 11


def test_held_out_rows_can_be_re_rated_only_at_final_evaluation(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    _seal(sample_path, ratings_path)
    out = tmp_path / "heldout_review.json"
    args = dict(sample=str(sample_path), ratings=str(tmp_path / "held_ratings.json"), out=str(out),
                snapshot=None, min_gap=2, profile="guy")
    with pytest.raises(SystemExit, match="SEALED"):
        rate_census.cmd_review(argparse.Namespace(**args, final_heldout_eval=False))
    rate_census.cmd_review(argparse.Namespace(**args, final_heldout_eval=True))
    review = json.loads(out.read_text(encoding="utf-8"))
    assert {it["id"] for it in review["profiles"]["guy"]["items"]} == HELD
    assert cr.SEALED_META_KEY not in review["meta"]  # a review sample is not a census


# ── D: shared loaders refuse a sealed payload ─────────────────────────────────

def test_sealed_payloads_are_refused_unless_final_evaluation():
    payload = {"seed": 1, "sealed": "HELD-OUT", "ratings": {"guy": {"a": "feed"}}}
    with pytest.raises(cr.SealedRatingsError):
        cr.refuse_sealed(payload, "x.json")
    assert cr.refuse_sealed(payload, "x.json", final_heldout_eval=True) is payload
    assert cr.refuse_sealed({"ratings": {}}, "fit.json") == {"ratings": {}}


def _run(*cmd):
    import subprocess

    return subprocess.run([sys.executable, *cmd], cwd=BACKEND, capture_output=True, text=True,
                          encoding="utf-8", timeout=300)


def test_eval_stats_and_rerun_diff_refuse_a_sealed_file_unless_final_evaluation(tmp_path):
    sealed = tmp_path / "held.json"
    sealed.write_text(json.dumps({"seed": 1, "sealed": "HELD-OUT", "ratings": {"guy": {"a": "push"}}}),
                      encoding="utf-8")
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"a": {"guy": "push", "deni": "hidden", "sport": "basketball", "event": "news",
                                      "comp": None, "comps": [], "ents": []}}), encoding="utf-8")
    eval_stats = str(BACKEND.parent / ".claude" / "skills" / "signal-quality-eval" / "scripts" / "eval_stats.py")

    refused = _run("-I", eval_stats, "census", str(snap), "--ratings", str(sealed))
    assert refused.returncode == 2 and "SEALED" in refused.stdout
    allowed = _run("-I", eval_stats, "census", str(snap), "--ratings", str(sealed), "--final-heldout-eval")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr

    rerun = str(BACKEND / "scripts" / "corpus_rerun_diff.py")
    refused = _run(rerun, "compare", str(snap), str(snap), "--ratings", str(sealed))
    assert refused.returncode != 0 and "SEALED" in refused.stderr
    allowed = _run(rerun, "compare", str(snap), str(snap), "--ratings", str(sealed), "--final-heldout-eval")
    assert allowed.returncode == 0, allowed.stderr[-2000:]


def test_merge_review_never_writes_into_the_sealed_file(tmp_path):
    sample_path, ratings_path = _census(tmp_path)
    _seal(sample_path, ratings_path)
    review = tmp_path / "rev.json"
    review.write_text(json.dumps({"ratings": {"guy": {"rss_001": "push"}}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="sealed"):
        rate_census.cmd_merge_review(argparse.Namespace(
            ratings=str(tmp_path / "held_ratings.json"), review=str(review), profile="guy"))


def test_llm_bakeoff_refuses_sealed_ratings(tmp_path):
    from scripts.llm_bakeoff import load_ratings

    sealed = tmp_path / "held.json"
    sealed.write_text(json.dumps({"sealed": "HELD-OUT", "ratings": {"guy": {"a": "feed"}}}), encoding="utf-8")
    with pytest.raises(cr.SealedRatingsError):
        load_ratings(sealed, None, "guy")
    assert load_ratings(sealed, None, "guy", final_heldout_eval=True) == {"a": "feed"}


# ── F: review for the Deni profile ────────────────────────────────────────────

def test_review_reads_the_deni_profile_from_a_snapshot(tmp_path):
    sample = {"meta": {"seed": 3}, "profiles": {"casual_deni_fan": {"items": [{"id": "a"}, {"id": "b"}]}}}
    sample_path = tmp_path / "s.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    ratings = tmp_path / "r.json"
    ratings.write_text(json.dumps({"seed": 3, "ratings": {"casual_deni_fan": {"a": "push", "b": "hide"}}}),
                       encoding="utf-8")
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"a": {"guy": "push", "deni": "hidden"}, "b": {"guy": "push", "deni": "hidden"}}),
                    encoding="utf-8")
    out = tmp_path / "rev.json"
    rate_census.cmd_review(argparse.Namespace(sample=str(sample_path), ratings=str(ratings), out=str(out),
                                              snapshot=str(snap), min_gap=2, profile="casual_deni_fan",
                                              final_heldout_eval=False))
    items = json.loads(out.read_text(encoding="utf-8"))["profiles"]["casual_deni_fan"]["items"]
    assert [it["id"] for it in items] == ["a"]  # gaps measured on the deni decision, not guy's


# ── D: the page seals itself on the last rating ───────────────────────────────

def test_the_page_seals_itself_when_the_last_row_is_rated(tmp_path):
    sample_path, ratings_path = _census(tmp_path, rated=False)
    srv = rate_census.make_server(sample_path, ratings_path, "guy", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=10).read())

    try:
        state = json.loads(urllib.request.urlopen(base + "/api/state", timeout=10).read())
        assert state["total"] == 6 and all(set(p) == set(cr.RATER_FIELDS) for p in state["pending"])
        for i in IDS[:-1]:
            post("/api/rate", {"id": i, "rating": "feed"})
        assert not (tmp_path / "held_ratings.json").exists()
        post("/api/rate", {"id": IDS[-1], "rating": "high"})
        assert set(json.loads((tmp_path / "held_ratings.json").read_text(encoding="utf-8"))["ratings"]["guy"]) == HELD
        assert set(_fit(ratings_path)) == set(IDS) - HELD
        undone = post("/api/undo", {})  # after the seal, undo touches the fit half only
        assert undone["id"] in set(IDS) - HELD
        assert set(_fit(ratings_path)) == set(IDS) - HELD - {undone["id"]}
    finally:
        srv.shutdown()
        srv.server_close()
