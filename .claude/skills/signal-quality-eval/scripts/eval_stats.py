"""Uncertainty and paired-comparison statistics for Signal Sports evaluations. Read-only.

The repo's evaluation tools report counts and point estimates. This helper adds what a
before/after claim needs on top of them: sample sizes, Wilson 95% intervals, an exact
McNemar test on the rows whose correctness changed, and per-slice breakdowns that refuse
to report slices too small to mean anything. Standard library only.

    python eval_stats.py wilson 37 52
    python eval_stats.py census AFTER.json --ratings ../../../../docs/qa/census2_ratings.json
    python eval_stats.py census AFTER.json --before BEFORE.json --ratings <ratings.json> \
        [--profile guy|casual_deni_fan] [--split fit|heldout] [--ids ids.txt] \
        [--slice sport|event|source --db <copy.db>]
    python eval_stats.py prf pairs.json [--slice source] [--min-n 10]
    python eval_stats.py selftest

``census`` consumes snapshots written by ``backend/scripts/corpus_rerun_diff.py snapshot``
and owner ratings in the census/N05 format ({"ratings": {"guy": {article_id: hide|low|feed|high|push}}}).
Its metric definitions are imported from that script (``census_metrics``), so they cannot drift.

``prf`` consumes a JSON list of {"id", "label", "pred", ...optional slice fields} records —
for example a facts field (event_type, sport) against human labels. Records whose label is null
are reported as unlabeled and excluded; nothing is imputed.

Nothing here opens a database for writing: ``--db`` (source slicing only) is opened with
SQLite ``mode=ro``.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

Z95 = 1.959963984540054

# Snapshot field per profile (corpus_rerun_diff stores "guy" / "deni").
SNAPSHOT_FIELD = {"guy": "guy", "casual_deni_fan": "deni"}


# ── pure statistics ───────────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials; None when n == 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for b (right→wrong) vs c (wrong→right) discordant rows."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def fmt_rate(k: int, n: int) -> str:
    ci = wilson(k, n)
    if ci is None:
        return "n=0 (no evidence)"
    return f"{k}/{n} = {k / n:.1%}  [95% CI {ci[0]:.1%} to {ci[1]:.1%}]"


def fmt_rate_min(k: int, n: int, min_n: int) -> str:
    """Like fmt_rate, but refuses to estimate from fewer than min_n trials."""
    return fmt_rate(k, n) if n >= min_n else f"{k}/{n} (n < {min_n}, not estimated)"


def prf(records: list[dict]) -> dict:
    """Per-class precision/recall/F1 plus accuracy over labeled records."""
    labeled = [r for r in records if r.get("label") is not None]
    classes = sorted({r["label"] for r in labeled} | {r["pred"] for r in labeled})
    per_class = {}
    for cls in classes:
        tp = sum(r["label"] == cls and r["pred"] == cls for r in labeled)
        fp = sum(r["label"] != cls and r["pred"] == cls for r in labeled)
        fn = sum(r["label"] == cls and r["pred"] != cls for r in labeled)
        p = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = 2 * p * rec / (p + rec) if p and rec else (0.0 if p is not None and rec is not None else None)
        per_class[cls] = {"tp": tp, "fp": fp, "fn": fn, "support": tp + fn,
                          "precision": p, "recall": rec, "f1": f1}
    supported = [v["f1"] for v in per_class.values() if v["support"] and v["f1"] is not None]
    correct = sum(r["label"] == r["pred"] for r in labeled)
    confusion = Counter((r["label"], r["pred"]) for r in labeled if r["label"] != r["pred"])
    return {
        "labeled": len(labeled),
        "unlabeled": len(records) - len(labeled),
        "correct": correct,
        "per_class": per_class,
        "macro_f1": sum(supported) / len(supported) if supported else None,
        "top_confusions": confusion.most_common(10),
    }


def visibility_error(decision: str, rating: str) -> bool:
    """A false show (owner said hide, engine showed it) or a false hide (owner wanted it at
    feed or above, engine hid it). Matches census_metrics: shown_precision treats any non-hide
    rating as acceptable to show; feed_plus_recall counts feed/high/push as wanted."""
    false_show = decision != "hidden" and rating == "hide"
    false_hide = decision == "hidden" and rating in ("feed", "high", "push")
    return false_show or false_hide


# ── commands ──────────────────────────────────────────────────────────────────

def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_ids(path: str | None) -> set[str] | None:
    if not path:
        return None
    text = Path(path).read_text(encoding="utf-8").strip()
    return set(json.loads(text)) if text.startswith("[") else {ln.strip() for ln in text.splitlines() if ln.strip()}


def _source_map(db: str) -> dict[str, str]:
    uri = f"file:{Path(db).resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        return dict(conn.execute("select id, source from articles").fetchall())


def _print_census(label: str, m: dict) -> None:
    print(f"  {label}: rated {m['rated']}")
    print(f"    exact notch       {fmt_rate(m['exact'], m['rated'])}")
    for key in ("shown_precision", "feed_plus_recall", "push_precision", "push_recall"):
        k, n = m[key]
        print(f"    {key:<17} {fmt_rate(k, n)}")


def cmd_wilson(args) -> int:
    print(fmt_rate(args.k, args.n))
    return 0


def cmd_census(args) -> int:
    from corpus_rerun_diff import ENGINE_NOTCH, OWNER_NOTCH, census_metrics

    field = SNAPSHOT_FIELD[args.profile]
    ratings = _load_json(args.ratings)["ratings"].get(args.profile)
    if not ratings:
        print(f"no ratings for profile {args.profile!r} in {args.ratings}")
        return 1
    total_rated = len(ratings)
    if args.review:
        ratings = {**ratings, **_load_json(args.review)["ratings"].get(args.profile, {})}
    ids = _load_ids(args.ids)
    if ids is not None:
        ratings = {k: v for k, v in ratings.items() if k in ids}
    after = _load_json(args.snapshot)
    before = _load_json(args.before) if args.before else None
    common = set(after) & (set(before) if before else set(after))
    ratings = {k: v for k, v in ratings.items() if k in common}
    restriction = " (restricted by --ids)" if ids is not None else ""
    if args.split:
        # The #237 seeded split, imported so it cannot drift. census_calibration_fit splits the
        # census sample items that load from the DB; a snapshot of the same DB holds exactly those
        # rows (both skip rows without a source config), so the halves match.
        from census_calibration_fit import split
        profiles = _load_json(args.sample)["profiles"]
        if args.profile not in profiles:
            print(f"--split: {args.sample} has no items for profile {args.profile!r}")
            return 2
        items = profiles[args.profile]["items"]
        fit, hold = split([it["id"] for it in items if it["id"] in after])
        half = fit if args.split == "fit" else hold
        ratings = {k: v for k, v in ratings.items() if k in half}
        restriction += f" ({args.split} half of the seeded #237 split: fit {len(fit)}, held-out {len(hold)})"
    print(f"profile {args.profile}: {len(ratings)} of {total_rated} rated rows evaluated{restriction}; "
          f"the rest are absent from the snapshot(s) or filtered out")

    m_after = census_metrics(after, ratings, field)
    if before is not None:
        _print_census("before", census_metrics(before, ratings, field))
    _print_census("after" if before is not None else "snapshot", m_after)

    if before is not None:
        print("  paired change on the same rows (exact McNemar, two-sided):")
        for name, wrong in (
            ("visibility error", lambda snap, k: visibility_error(snap[k][field], ratings[k])),
            ("exact-notch miss", lambda snap, k: ENGINE_NOTCH[snap[k][field]] != OWNER_NOTCH[ratings[k]]),
        ):
            b = sum((not wrong(before, k)) and wrong(after, k) for k in ratings)
            c = sum(wrong(before, k) and (not wrong(after, k)) for k in ratings)
            print(f"    {name:<17} got worse {b}, got better {c}, p = {mcnemar_exact(b, c):.3g}"
                  f"{'  (no discordant rows: no evidence either way)' if b + c == 0 else ''}")

    if args.slice:
        if args.slice == "source":
            if not args.db:
                print("--slice source needs --db <corpus copy or snapshot> (opened read-only)")
                return 2
            value_of = _source_map(args.db).get
        else:
            key = {"sport": "sport", "event": "event"}[args.slice]
            value_of = lambda k: after[k].get(key)  # noqa: E731 - slice by the AFTER facts
        groups: dict[str, dict] = defaultdict(dict)
        for k, v in ratings.items():
            groups[str(value_of(k))][k] = v
        print(f"  by {args.slice} (after-snapshot values; slices with n < {args.min_n} are not estimated):")
        for value, sub in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if len(sub) < args.min_n:
                print(f"    {value:<20} n={len(sub)}  insufficient n")
                continue
            m = census_metrics(after, sub, field)
            print(f"    {value:<20} n={len(sub)}  "
                  f"shown_precision {fmt_rate_min(*m['shown_precision'], args.min_n)}; "
                  f"feed_plus_recall {fmt_rate_min(*m['feed_plus_recall'], args.min_n)}")
    return 0


def cmd_prf(args) -> int:
    records = _load_json(args.pairs)
    res = prf(records)
    print(f"labeled {res['labeled']}, unlabeled (excluded, not imputed) {res['unlabeled']}")
    print(f"accuracy {fmt_rate(res['correct'], res['labeled'])}")
    print(f"macro F1 {res['macro_f1']:.3f}" if res["macro_f1"] is not None else "macro F1 n/a")
    for cls, v in sorted(res["per_class"].items(), key=lambda kv: -kv[1]["support"]):
        head = f"  {cls:<22} support {v['support']:>4}"
        if v["f1"] is None:
            print(f"{head}  (F1 undefined: no predictions or no support for this class)")
            continue
        print(f"{head}  P {fmt_rate(v['tp'], v['tp'] + v['fp'])}"
              f"  R {fmt_rate(v['tp'], v['tp'] + v['fn'])}  F1 {v['f1']:.3f}")
    if res["top_confusions"]:
        print("top confusions (label -> pred):")
        for (lab, pred), n in res["top_confusions"]:
            print(f"  {lab} -> {pred}: {n}")
    if args.slice:
        groups: dict[str, list] = defaultdict(list)
        for r in records:
            if r.get("label") is not None:
                groups[str(r.get(args.slice))].append(r)
        print(f"by {args.slice} (n < {args.min_n} not estimated):")
        for value, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if len(rs) < args.min_n:
                print(f"  {value:<20} n={len(rs)}  insufficient n")
            else:
                correct = sum(r["label"] == r["pred"] for r in rs)
                print(f"  {value:<20} accuracy {fmt_rate(correct, len(rs))}")
    return 0


def cmd_selftest(_args) -> int:
    """Checks against hand-computed values (worked by hand, not by this code)."""
    lo, hi = wilson(8, 10)
    assert abs(lo - 0.4902) < 5e-4 and abs(hi - 0.9433) < 5e-4, (lo, hi)
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and abs(hi - 0.2775) < 5e-4, (lo, hi)
    assert wilson(0, 0) is None
    assert abs(mcnemar_exact(1, 9) - 22 / 1024) < 1e-12       # 2 * (C(10,0)+C(10,1)) / 2^10
    assert mcnemar_exact(3, 3) == 1.0                           # 2 * 42/64 > 1 -> capped
    assert mcnemar_exact(0, 0) == 1.0
    res = prf([{"label": "a", "pred": "a"}, {"label": "a", "pred": "b"},
               {"label": "b", "pred": "b"}, {"label": "b", "pred": "b"},
               {"label": "b", "pred": "a"}, {"label": None, "pred": "a"}])
    assert res["labeled"] == 5 and res["unlabeled"] == 1 and res["correct"] == 3
    assert res["per_class"]["a"]["f1"] == 0.5
    assert abs(res["per_class"]["b"]["f1"] - 2 / 3) < 1e-12
    assert abs(res["macro_f1"] - (0.5 + 2 / 3) / 2) < 1e-12
    assert visibility_error("hidden", "feed") and visibility_error("feed", "hide")
    assert not visibility_error("low_feed", "low") and not visibility_error("hidden", "low")
    print("selftest: all checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("wilson", help="Wilson 95%% interval for k of n")
    p.add_argument("k", type=int)
    p.add_argument("n", type=int)
    p.set_defaults(func=cmd_wilson)

    p = sub.add_parser("census", help="owner-rating metrics with intervals; paired test with --before")
    p.add_argument("snapshot", help="corpus_rerun_diff snapshot (the 'after' side)")
    p.add_argument("--before", help="corpus_rerun_diff snapshot of the baseline")
    p.add_argument("--ratings", required=True)
    p.add_argument("--review", help="re-rated rows that override --ratings (census #2 owner review)")
    p.add_argument("--profile", choices=sorted(SNAPSHOT_FIELD), default="guy")
    p.add_argument("--ids", help="restrict to these article ids (JSON list or one per line)")
    p.add_argument("--split", choices=["fit", "heldout"],
                   help="restrict to one half of census_calibration_fit.py's seeded split (census #2)")
    p.add_argument("--sample", default=str(REPO / "docs" / "qa" / "census2_sample.json"),
                   help="census sample file the split is drawn from (default: census #2)")
    p.add_argument("--slice", choices=["sport", "event", "source"])
    p.add_argument("--db", help="corpus copy/snapshot for --slice source (read-only)")
    p.add_argument("--min-n", type=int, default=10)
    p.set_defaults(func=cmd_census)

    p = sub.add_parser("prf", help="per-class precision/recall/F1 from label/pred records")
    p.add_argument("pairs")
    p.add_argument("--slice")
    p.add_argument("--min-n", type=int, default=10)
    p.set_defaults(func=cmd_prf)

    p = sub.add_parser("selftest", help="verify the statistics against hand-computed values")
    p.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
