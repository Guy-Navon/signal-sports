"""Census calibration fit / held-out analysis (#237). Read-only.

Re-runs the deterministic pipeline (LLM and translation disabled) on every
census #2 article, scores it with Guy's SEED profile, and groups engine-vs-owner
gaps by (matched topic, event type) on a seeded FIT half. ``--candidate``
applies proposed event-affinity / never_show changes and reports FIT and
HOLD-OUT metrics, so only a bias found on one half and confirmed on the other
is proposed (docs/PREFERENCE_MODEL_V2.md, docs/qa/CENSUS_2026-10.md).

    python scripts/census_calibration_fit.py
    python scripts/census_calibration_fit.py --review ../docs/qa/census2_review_ratings.json
    python scripts/census_calibration_fit.py --candidate changes.json --show
    python scripts/census_calibration_fit.py --db data/snapshots/<snapshot>.db   # a dev snapshot

A candidate file is a JSON list of changes:
    {"kind": "event", "scope_ref": "team:maccabi_tlv_bb", "event_type": "candidate", "delta": -1}
    {"kind": "never_show", "scope": "...", "target_id": "...", "event_type": "..."}

Read-only by construction: the corpus is opened with SQLite ``mode=ro`` for the
article rows, and the app's own engine is pinned to an in-memory database
before any app import, so nothing here can write to any file. It never applies
a change; persisting one is a separate, reviewed apply_* script.

Integrated from the analysis script used for #237 (preserved 2026-10-13,
sha256 5d6d7a7a...dce3e); the metric definitions and the seeded split are
unchanged.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import logging
import os
import random
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

# Before ANY app import: no LLM, no translation, and an engine that cannot
# point at a real database (the articles are read through mode=ro below).
os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
os.environ["TRANSLATION_PROVIDER"] = "disabled"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
sys.path.insert(0, str(BACKEND))

E = {"hidden": 0, "low_feed": 1, "feed": 2, "high_feed": 3, "push": 4}
H = {"hide": 0, "low": 1, "feed": 2, "high": 3, "push": 4}
SPLIT_SEED = 237


def load_articles(db_path: Path, items: list[dict]) -> dict:
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config

    db = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    articles = {}
    try:
        for it in items:
            row = db.execute(
                "select source,url,title,coalesce(subtitle,'') from articles where id=?", (it["id"],)
            ).fetchone()
            if row is None or get_source_config(row[0]) is None:
                continue
            article, _, _ = ingestion_service._normalise(
                RawSourceItem(source_id=row[0], url=row[1], title=row[2], published_at=None, summary=row[3]),
                get_source_config(row[0]))
            articles[it["id"]] = article
    finally:
        db.close()
    return articles


def split(ids: list[str]) -> tuple[set, set]:
    ids = sorted(ids)
    fit = set(random.Random(SPLIT_SEED).sample(ids, len(ids) // 2))
    return fit, set(ids) - fit


def profile_with(base_profile, changes: list[dict]):
    from app.models.profile_v2 import EventAffinity, OverrideRule

    profile = copy.deepcopy(base_profile)
    v2 = profile.profile_v2
    for ch in changes:
        if ch["kind"] == "event":
            v2.event_affinities = [e for e in v2.event_affinities
                                   if not (e.scope_ref == ch["scope_ref"] and e.event_type == ch["event_type"])]
            if ch["delta"] != 0:
                v2.event_affinities.append(EventAffinity(
                    scope_ref=ch["scope_ref"], event_type=ch["event_type"], delta=ch["delta"]))
        elif ch["kind"] == "never_show":
            v2.overrides.append(OverrideRule(
                kind="never_show", scope=ch["scope"], target_id=ch["target_id"], event_type=ch["event_type"]))
        else:
            raise ValueError(f"unknown change kind: {ch.get('kind')!r}")
    return profile


def score_all(articles: dict, profile) -> dict:
    from app.services.preference_engine import score_article_v2

    out = {}
    for key, article in articles.items():
        result = score_article_v2(article, profile)
        out[key] = (result.decision, result.matched_topic, article.event_type)
    return out


def metrics(dec: dict, keys, ratings: dict) -> str:
    keys = [k for k in keys if k in ratings]
    if not keys:
        return "no rated rows"
    vis = [k for k in keys if dec[k][0] != "hidden"]
    w3 = [k for k in keys if ratings[k] in ("feed", "high", "push")]
    pushes = [k for k in keys if dec[k][0] == "push"]
    return (f"exact {sum(E[dec[k][0]] == H[ratings[k]] for k in keys)}/{len(keys)} | "
            f"mean|gap| {sum(abs(E[dec[k][0]] - H[ratings[k]]) for k in keys) / len(keys):.3f} | "
            f"shown prec {sum(ratings[k] != 'hide' for k in vis)}/{len(vis)} | "
            f"feed+ recall {sum(dec[k][0] != 'hidden' for k in w3)}/{len(w3)} | "
            f"push {sum(ratings[k] == 'push' for k in pushes)}/{len(pushes)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=BACKEND / "data" / "signal_sports.db",
                        help="corpus or snapshot, opened read-only (default: the canonical corpus)")
    parser.add_argument("--ratings", type=Path, default=REPO / "docs" / "qa" / "census2_ratings.json")
    parser.add_argument("--sample", type=Path, default=REPO / "docs" / "qa" / "census2_sample.json")
    parser.add_argument("--review", type=Path, help="re-rated rows that override --ratings")
    parser.add_argument("--candidate", type=Path, help="JSON list of proposed profile changes")
    parser.add_argument("--show", action="store_true", help="list each flipped row (with --candidate)")
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)

    from app.seed.seed_profiles import SEED_PROFILES

    if not args.db.is_file():
        print(f"no such database: {args.db}")
        return 1
    ratings = json.loads(args.ratings.read_text(encoding="utf-8"))["ratings"]["guy"]
    if args.review:
        rev = json.loads(args.review.read_text(encoding="utf-8"))["ratings"]["guy"]
        changed = {k: (ratings[k], v) for k, v in rev.items() if ratings.get(k) != v}
        print(f"review: {len(rev)} re-rated, {len(changed)} changed")
        ratings = {**ratings, **rev}
    items = json.loads(args.sample.read_text(encoding="utf-8"))["profiles"]["guy"]["items"]

    articles = load_articles(args.db, items)
    ids = sorted(articles)
    fit, hold = split(ids)
    base_profile = next(p for p in SEED_PROFILES if p.user_id == "guy")

    base = score_all(articles, base_profile)
    print(f"articles replayed: {len(ids)} (fit {len(fit)}, hold-out {len(hold)}); db: {args.db.name}")
    print("BASE  fit:", metrics(base, fit, ratings))
    print("BASE hold:", metrics(base, hold, ratings))

    groups = collections.defaultdict(list)
    for k in fit:
        decision, topic, event = base[k]
        if decision == "hidden" or topic is None or k not in ratings:
            continue
        groups[(topic, event)].append(E[decision] - H[ratings[k]])
    print("\nFIT-half shown groups (n>=3), mean(engine-owner):")
    for (topic, event), gaps in sorted(groups.items(), key=lambda x: -abs(sum(x[1]) / len(x[1]))):
        if len(gaps) >= 3:
            print(f"  {topic:24} {event:18} n={len(gaps):2} mean={sum(gaps) / len(gaps):+.2f}  "
                  f"over={sum(x > 0 for x in gaps)} under={sum(x < 0 for x in gaps)}")

    if args.candidate:
        changes = json.loads(args.candidate.read_text(encoding="utf-8"))
        cand = score_all(articles, profile_with(base_profile, changes))
        print("\nCAND  fit:", metrics(cand, fit, ratings))
        print("CAND hold:", metrics(cand, hold, ratings))
        flips = [k for k in ids if base[k][0] != cand[k][0]]
        print(f"flips: {len(flips)} (fit {len(set(flips) & fit)}, hold {len(set(flips) & hold)})")
        rated = [k for k in flips if k in ratings]
        better = sum(abs(E[cand[k][0]] - H[ratings[k]]) < abs(E[base[k][0]] - H[ratings[k]]) for k in rated)
        worse = sum(abs(E[cand[k][0]] - H[ratings[k]]) > abs(E[base[k][0]] - H[ratings[k]]) for k in rated)
        print(f"closer {better}, further {worse}")
        if args.show:
            titles = {i["id"]: i["title"] for i in items}
            for k in flips:
                print(f"   {base[k][0]:9}->{cand[k][0]:9} owner={ratings.get(k, '?'):5} {base[k][2]:10} {titles[k][:64]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
