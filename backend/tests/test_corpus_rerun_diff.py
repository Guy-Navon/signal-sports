"""The pure halves of scripts/corpus_rerun_diff.py: snapshot diffing and census metrics."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "corpus_rerun_diff", Path(__file__).resolve().parents[1] / "scripts" / "corpus_rerun_diff.py"
)
crd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(crd)


def _row(event="news", guy="hidden", deni="hidden", **kw):
    base = {"sport": "basketball", "event": event, "cert": "confirmed", "comp": None,
            "comps": [], "ents": [], "guy": guy, "deni": deni, "title": "t"}
    base.update(kw)
    return base


def test_diff_separates_fact_changes_from_decision_flips():
    old = {"a": _row(), "b": _row(), "c": _row(guy="feed")}
    new = {"a": _row(event="signing"),        # fact only
           "b": _row(guy="feed"),             # decision flip
           "c": _row(guy="feed")}             # unchanged
    d = crd.diff_snapshots(old, new)
    assert d["changed"] == ["a", "b"]
    assert d["flips"] == ["b"]
    assert d["counts"]["guy"]["visible"] == (1, 2)


def test_diff_compares_only_rows_present_in_both():
    # The worker inserts rows between the two snapshot runs.
    old = {"a": _row()}
    new = {"a": _row(), "late": _row(guy="push")}
    d = crd.diff_snapshots(old, new)
    assert d["common"] == 1
    assert d["counts"]["guy"]["push"] == (0, 0)


def test_census_metrics():
    snap = {"a": _row(guy="push"), "b": _row(guy="feed"), "c": _row(guy="hidden"), "d": _row(guy="low_feed")}
    ratings = {"a": "push", "b": "high", "c": "feed", "d": "hide", "unscored": "feed"}
    m = crd.census_metrics(snap, ratings)
    assert m["rated"] == 4
    assert m["exact"] == 1                      # only a (push == push)
    assert m["shown_precision"] == (2, 3)       # a, b wanted; d not
    assert m["feed_plus_recall"] == (2, 3)      # a, b shown; c hidden
    assert m["push_precision"] == (1, 1)
    assert m["push_recall"] == (1, 1)
