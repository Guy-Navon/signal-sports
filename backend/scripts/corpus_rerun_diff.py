"""Before/after effect of a classification or relevance change on the WHOLE corpus.

Stored rows keep their old facts until a backfill, so a feed diff shows nothing for a
classifier change. This re-runs the deterministic ingestion path (`_normalise`, LLM and
translation disabled) over every corpus row IN MEMORY and scores both seed profiles —
no DB writes, no network.

Typical use (from backend/), comparing a working tree against main:

    .venv\\Scripts\\python.exe scripts/corpus_rerun_diff.py snapshot --out %TEMP%\\new.json
    git stash
    .venv\\Scripts\\python.exe scripts/corpus_rerun_diff.py snapshot --out %TEMP%\\old.json
    git stash pop
    .venv\\Scripts\\python.exe scripts/corpus_rerun_diff.py compare %TEMP%\\old.json %TEMP%\\new.json \\
        --ratings ../docs/qa/census2_ratings.json

`compare` reports changed facts, every decision flip (with the owner's census rating when
one exists), push and visible counts per profile, and census metrics on both sides. Only
rows present in both snapshots are compared: the worker may insert rows between runs.
Rules-only is an approximation of production (which also uses the LLM) — say so when
quoting numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

FACT_FIELDS = ("sport", "event", "comp", "comps", "ents")
DECISION_FIELDS = ("guy", "deni")
ENGINE_NOTCH = {"hidden": 0, "low_feed": 1, "feed": 2, "high_feed": 3, "push": 4}
OWNER_NOTCH = {"hide": 0, "low": 1, "feed": 2, "high": 3, "push": 4}


# ── pure helpers (tested) ─────────────────────────────────────────────────────

def diff_snapshots(old: dict, new: dict) -> dict:
    """Rows changed and decision flips between two snapshots (common keys only)."""
    common = sorted(set(old) & set(new))
    changed = [k for k in common
               if any(old[k][f] != new[k][f] for f in FACT_FIELDS + DECISION_FIELDS)]
    flips = [k for k in changed if any(old[k][f] != new[k][f] for f in DECISION_FIELDS)]
    counts = {
        p: {
            "push": (sum(old[k][p] == "push" for k in common), sum(new[k][p] == "push" for k in common)),
            "visible": (sum(old[k][p] != "hidden" for k in common), sum(new[k][p] != "hidden" for k in common)),
        }
        for p in DECISION_FIELDS
    }
    return {"common": len(common), "changed": changed, "flips": flips, "counts": counts}


def census_metrics(snapshot: dict, ratings: dict, profile: str = "guy") -> dict:
    """Owner-rating agreement on the rows rated in a census."""
    ids = [k for k in ratings if k in snapshot]
    dec = {k: snapshot[k][profile] for k in ids}
    visible = [k for k in ids if dec[k] != "hidden"]
    wanted = [k for k in ids if ratings[k] in ("feed", "high", "push")]
    pushes = [k for k in ids if dec[k] == "push"]
    owner_push = [k for k in ids if ratings[k] == "push"]
    return {
        "rated": len(ids),
        "exact": sum(ENGINE_NOTCH[dec[k]] == OWNER_NOTCH[ratings[k]] for k in ids),
        "shown_precision": (sum(ratings[k] != "hide" for k in visible), len(visible)),
        "feed_plus_recall": (sum(dec[k] != "hidden" for k in wanted), len(wanted)),
        "push_precision": (sum(ratings[k] == "push" for k in pushes), len(pushes)),
        "push_recall": (sum(dec[k] == "push" for k in owner_push), len(owner_push)),
    }


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_snapshot(args) -> None:
    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
    os.environ["TRANSLATION_PROVIDER"] = "disabled"
    import logging
    logging.disable(logging.CRITICAL)
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config
    from app.seed.seed_profiles import SEED_PROFILES
    from app.services.preference_engine import score_article_v2

    profiles = {p.user_id: p for p in SEED_PROFILES}
    db = Path(args.db).resolve().as_posix()
    rows = sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(
        "select id, source, url, title, coalesce(subtitle, '') from articles").fetchall()
    out = {}
    for aid, src, url, title, sub in rows:
        cfg = get_source_config(src)
        if cfg is None:
            continue
        a, _, _ = ingestion_service._normalise(
            RawSourceItem(source_id=src, url=url, title=title, published_at=None, summary=sub), cfg)
        out[aid] = {
            "sport": a.sport, "event": a.event_type, "cert": a.event_certainty,
            "comp": a.primary_competition, "comps": a.article_competitions, "ents": a.entity_ids,
            "guy": score_article_v2(a, profiles["guy"]).decision,
            "deni": score_article_v2(a, profiles["casual_deni_fan"]).decision,
            "title": title,
        }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} rows -> {args.out}")


def cmd_compare(args) -> None:
    old = json.loads(Path(args.old).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    ratings = {}
    if args.ratings:
        ratings = json.loads(Path(args.ratings).read_text(encoding="utf-8"))["ratings"]["guy"]
    d = diff_snapshots(old, new)
    print(f"rows compared: {d['common']}  changed: {len(d['changed'])}  decision flips: {len(d['flips'])}")
    for f in FACT_FIELDS:
        print(f"  {f} changed: {sum(old[k][f] != new[k][f] for k in d['changed'])}")
    print("--- decision flips")
    for k in d["flips"]:
        o, n = old[k], new[k]
        print(f"  guy {o['guy']}->{n['guy']} | deni {o['deni']}->{n['deni']} | owner={ratings.get(k, '-'):5} "
              f"| {o['event']}->{n['event']} | {o['title'][:70]}")
    print("--- fact-only changes")
    for k in d["changed"]:
        if k in d["flips"]:
            continue
        diffs = [f"{f}:{old[k][f]}->{new[k][f]}" for f in ("sport", "event", "comp", "ents") if old[k][f] != new[k][f]]
        print(f"  {' '.join(diffs)[:110]} | {old[k]['title'][:55]}")
    for p, c in d["counts"].items():
        print(f"{p}: push {c['push'][0]} -> {c['push'][1]} | visible {c['visible'][0]} -> {c['visible'][1]}")
    if ratings:
        for label, snap in (("old", old), ("new", new)):
            print(f"census ({label}): {census_metrics(snap, ratings)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_snap = sub.add_parser("snapshot", help="rerun the deterministic pipeline over every row")
    p_snap.add_argument("--out", required=True)
    p_snap.add_argument("--db", default=str(_BACKEND / "data" / "signal_sports.db"))
    p_snap.set_defaults(func=cmd_snapshot)
    p_cmp = sub.add_parser("compare", help="diff two snapshots")
    p_cmp.add_argument("old")
    p_cmp.add_argument("new")
    p_cmp.add_argument("--ratings", help="census ratings JSON for owner-agreement metrics")
    p_cmp.set_defaults(func=cmd_compare)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
