"""Measure whether the feed actually filters well — audit finding N05.

The suite proves the engine does what it was told. Nothing proves that what it
was told is right. This script closes that gap by comparing engine decisions
against a HUMAN-RATED ground truth over the real ingested corpus.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py baseline --out ../docs/qa/n05_baseline.json
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py sample   --out ../docs/qa/n05_sample.json
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py score    --ratings ../docs/qa/n05_ratings.json

Three commands:

``baseline``
    What the engine does today, no human input required: decision spread per
    profile, the full push list with its matched rule, push de-duplication, and
    the sport blind-spots where false negatives hide. Run this before and after
    any classification/relevance change.

``sample``
    Draws a STRATIFIED rating set. Uniform sampling would be ~84% hidden
    football and teach nothing, so each decision tier is its own stratum and
    ``hidden`` is sub-stratified by sport. Every stratum records the weight
    needed to project a rating back onto the whole corpus — without those
    weights the accuracy numbers would be a description of the sample, not of
    the feed.

``score``
    Compares the ratings to the decisions. Reports, per profile: agreement,
    false shows, false hides, and push precision — each as a weighted
    population estimate, with the raw sample counts alongside so the reader can
    see how much evidence sits behind every number.

Notes:
- Read-only. Never mutates the corpus DB, never opens a network connection,
  never triggers ingestion or a notification.
- Loads backend/.env exactly as app.main does, so the decisions measured are
  the ones production serves (CLUSTERING_ENABLED, PREFERENCE_ENGINE, ...).
  A measurement taken under different flags is measuring a different product.
- Scores ``include_hidden=True``: the feed-freshness window is a separate
  concern (M8) and the corpus is older than the window, so applying it would
  leave nothing to measure. This measures the RELEVANCE RULES, not freshness.
- Uses the raw persisted profile, without learned-feedback augmentation, so
  successive runs stay comparable regardless of QA clicking.
"""

import argparse
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

try:  # Match app.main: production flags must be in effect while measuring.
    from dotenv import load_dotenv

    load_dotenv(_BACKEND / ".env", override=False)
except ImportError:  # pragma: no cover - dotenv is a hard dependency in practice
    pass

from app.db.database import SessionLocal  # noqa: E402
from app.repositories import article_repository, profile_repository  # noqa: E402
from app.services.feed_service import active_engine, build_feed  # noqa: E402

PROFILE_IDS = ("guy", "casual_deni_fan")
TIERS = ("push", "high_feed", "feed", "low_feed", "hidden")
VISIBLE = ("push", "high_feed", "feed", "low_feed")

# How many to draw from each stratum. push is a census: it is the highest-stakes
# surface (it reaches a phone) and small enough to rate in full. hidden is
# sub-stratified because ~70% of it is football that is almost certainly hidden
# correctly — sampling it uniformly would spend the whole rating budget
# confirming the obvious instead of hunting false negatives.
SAMPLE_PLAN = {
    "push": None,  # None = take every one
    "high_feed": 30,
    "feed": 35,
    "low_feed": 25,
    "hidden:basketball": 30,
    "hidden:unknown": 20,
    "hidden:football": 15,
    "hidden:tennis": 8,
}

SEED = 20260905


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _title(article) -> str:
    return article.translated_title or article.title


def _stratum_of(scored) -> str:
    """Which sampling stratum a scored article belongs to."""
    if scored.decision != "hidden":
        return scored.decision
    return f"hidden:{scored.article.sport or 'unknown'}"


def _score_all(session):
    """{profile_id: [ScoredArticle]} over every RSS article, hidden included."""
    articles = article_repository.get_rss_articles(session)
    out = {}
    for user_id in PROFILE_IDS:
        profile = profile_repository.get_by_id(session, user_id)
        if profile is None:
            raise SystemExit(f"Profile '{user_id}' is missing from the corpus DB.")
        out[user_id] = build_feed(
            articles, profile, include_hidden=True, session=session
        )
    return out, len(articles)


def _run_meta(corpus_size: int) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "engine": active_engine(),
        "corpus_articles": corpus_size,
        "scope": (
            "Relevance rules over the whole ingested corpus, freshness window "
            "not applied, raw profiles without learned augmentation."
        ),
    }


# ── baseline ──────────────────────────────────────────────────────────────────


def _push_report(feed) -> dict:
    """Push discipline: how many, how many distinct stories, and on what rule."""
    pushes = [s for s in feed if s.decision == "push"]
    clustered = [s for s in pushes if s.cluster]
    return {
        "count": len(pushes),
        "carrying_a_cluster_card": len(clustered),
        # Every push that is not clustered is a separate phone notification, so
        # this is the number of times the user is interrupted, not the number of
        # things that happened.
        "matched_rules": dict(Counter(s.matched_event_rule for s in pushes)),
        "matched_topics": dict(Counter(s.matched_topic for s in pushes)),
        "items": [
            {
                "id": s.article.id,
                "title": _title(s.article),
                "source": s.article.source,
                "published_at": s.article.published_at,
                "matched_topic": s.matched_topic,
                "matched_event_rule": s.matched_event_rule,
                "clustered": bool(s.cluster),
            }
            for s in pushes
        ],
    }


def cmd_baseline(args) -> None:
    with SessionLocal() as session:
        feeds, corpus_size = _score_all(session)

    report = {"meta": _run_meta(corpus_size), "profiles": {}}
    for user_id, feed in feeds.items():
        by_tier = Counter(s.decision for s in feed)
        by_sport = defaultdict(Counter)
        for s in feed:
            by_sport[s.article.sport or "unknown"][s.decision] += 1

        visible = sum(by_tier[t] for t in VISIBLE)
        report["profiles"][user_id] = {
            "decisions": {t: by_tier.get(t, 0) for t in TIERS},
            "visible_total": visible,
            "visible_share": round(visible / max(corpus_size, 1), 4),
            # A tier that never fires is a tier that is not doing any work.
            "unused_tiers": [t for t in TIERS if by_tier.get(t, 0) == 0],
            "by_sport": {
                sport: {
                    "total": sum(counts.values()),
                    "hidden": counts.get("hidden", 0),
                    "hidden_share": round(
                        counts.get("hidden", 0) / max(sum(counts.values()), 1), 3
                    ),
                }
                for sport, counts in sorted(by_sport.items())
            },
            "push": _push_report(feed),
        }

    _write(args.out, report)
    _print_baseline(report)


def _print_baseline(report: dict) -> None:
    meta = report["meta"]
    print(f"engine={meta['engine']}  corpus={meta['corpus_articles']}  sha={meta['git_sha'][:7]}")
    for user_id, p in report["profiles"].items():
        print(f"\n── {user_id} ──")
        print("  " + "  ".join(f"{t}={p['decisions'][t]}" for t in TIERS))
        print(f"  visible {p['visible_total']} ({p['visible_share'] * 100:.1f}% of corpus)")
        if p["unused_tiers"]:
            print(f"  tiers that never fire: {', '.join(p['unused_tiers'])}")
        for sport, s in p["by_sport"].items():
            print(f"    {sport:11} total={s['total']:5} hidden={s['hidden']:5} ({s['hidden_share'] * 100:.0f}%)")
        push = p["push"]
        print(f"  push={push['count']}  clustered={push['carrying_a_cluster_card']}")
        if push["count"]:
            print(f"    rules: {push['matched_rules']}")


# ── sample ────────────────────────────────────────────────────────────────────


def cmd_sample(args) -> None:
    with SessionLocal() as session:
        feeds, corpus_size = _score_all(session)

    rng = random.Random(args.seed)
    out = {"meta": _run_meta(corpus_size) | {"seed": args.seed}, "profiles": {}}

    for user_id, feed in feeds.items():
        strata = defaultdict(list)
        for s in feed:
            strata[_stratum_of(s)].append(s)

        items, weights = [], {}
        for stratum, wanted in SAMPLE_PLAN.items():
            population = strata.get(stratum, [])
            if not population:
                weights[stratum] = {"population": 0, "sampled": 0, "weight": 0.0}
                continue
            take = len(population) if wanted is None else min(wanted, len(population))
            chosen = rng.sample(population, take)
            # Each rated item stands for this many corpus articles.
            weights[stratum] = {
                "population": len(population),
                "sampled": take,
                "weight": len(population) / take,
            }
            for s in chosen:
                items.append(
                    {
                        "id": s.article.id,
                        "stratum": stratum,
                        # The engine's answer travels with the sample so `score`
                        # can compare, but the rating surface must NOT show it —
                        # a rater who sees the answer is no longer ground truth.
                        "engine_decision": s.decision,
                        "matched_topic": s.matched_topic,
                        "matched_event_rule": s.matched_event_rule,
                        "title": _title(s.article),
                        "original_title": s.article.title,
                        "source": s.article.source,
                        "sport": s.article.sport,
                        "league": s.article.league,
                        "event_type": s.article.event_type,
                        "published_at": s.article.published_at,
                        "url": s.article.url,
                    }
                )

        rng.shuffle(items)  # Rate in mixed order; tier order would leak the answer.
        out["profiles"][user_id] = {"strata": weights, "items": items}

    _write(args.out, out)
    for user_id, p in out["profiles"].items():
        print(f"{user_id}: {len(p['items'])} items to rate")
        for stratum, w in p["strata"].items():
            if w["sampled"]:
                print(f"    {stratum:20} {w['sampled']:3} of {w['population']:5}  (x{w['weight']:.1f})")


# ── score ─────────────────────────────────────────────────────────────────────

# What the rater is asked for, mapped onto the product's decision ladder.
RATING_TO_TIER = {
    "push": "push",
    "high": "high_feed",
    "feed": "feed",
    "low": "low_feed",
    "hide": "hidden",
}
TIER_RANK = {"hidden": 0, "low_feed": 1, "feed": 2, "high_feed": 3, "push": 4}


def cmd_score(args) -> None:
    ratings = json.loads(Path(args.ratings).read_text(encoding="utf-8"))
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))

    report = {"meta": _run_meta(sample["meta"]["corpus_articles"]), "profiles": {}}
    report["meta"]["rated_against_sample"] = sample["meta"].get("generated_at")

    for user_id, block in sample["profiles"].items():
        given = ratings.get(user_id, {})
        by_id = {i["id"]: i for i in block["items"]}
        weights = {k: v["weight"] for k, v in block["strata"].items()}

        rated = [(by_id[aid], RATING_TO_TIER[v]) for aid, v in given.items() if aid in by_id]
        if not rated:
            report["profiles"][user_id] = {"rated": 0, "note": "no ratings supplied"}
            continue

        est = defaultdict(float)   # weighted population estimates
        raw = Counter()            # unweighted sample counts
        disagreements = []

        for item, truth in rated:
            engine = item["engine_decision"]
            w = weights.get(item["stratum"], 1.0)
            est["rated"] += w
            raw["rated"] += 1

            if engine == truth:
                est["exact"] += w
                raw["exact"] += 1
            else:
                # A false SHOW is noise the user must skip past; a false HIDE is
                # a story they never learn exists. They are not the same failure.
                if engine != "hidden" and truth == "hidden":
                    kind = "false_show"
                elif engine == "hidden" and truth != "hidden":
                    kind = "false_hide"
                elif TIER_RANK[engine] > TIER_RANK[truth]:
                    kind = "over_ranked"
                else:
                    kind = "under_ranked"
                est[kind] += w
                raw[kind] += 1
                disagreements.append(
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "stratum": item["stratum"],
                        "engine": engine,
                        "human": truth,
                        "kind": kind,
                        "matched_topic": item["matched_topic"],
                        "matched_event_rule": item["matched_event_rule"],
                    }
                )

        # Push precision is measured directly: push is sampled as a census, so
        # this is the true rate, not an estimate.
        pushes = [(i, t) for i, t in rated if i["engine_decision"] == "push"]
        justified = sum(1 for _, t in pushes if t == "push")

        total = est["rated"] or 1.0
        report["profiles"][user_id] = {
            "rated": raw["rated"],
            "sample_counts": dict(raw),
            "population_estimates": {
                k: round(est[k] / total, 4)
                for k in ("exact", "false_show", "false_hide", "over_ranked", "under_ranked")
            },
            "push_precision": {
                "rated": len(pushes),
                "agreed_push_worthy": justified,
                "precision": round(justified / len(pushes), 3) if pushes else None,
            },
            "disagreements": sorted(disagreements, key=lambda d: d["kind"]),
        }

    _write(args.out, report)
    _print_score(report)


def _print_score(report: dict) -> None:
    for user_id, p in report["profiles"].items():
        print(f"\n── {user_id} ──")
        if not p.get("rated"):
            print(f"  {p.get('note')}")
            continue
        print(f"  rated {p['rated']} items")
        for k, v in p["population_estimates"].items():
            print(f"    {k:14} {v * 100:5.1f}%   (sample n={p['sample_counts'].get(k, 0)})")
        pp = p["push_precision"]
        if pp["precision"] is not None:
            print(f"  push precision {pp['precision'] * 100:.0f}% ({pp['agreed_push_worthy']}/{pp['rated']})")
        print(f"  {len(p['disagreements'])} disagreements recorded")


# ── plumbing ──────────────────────────────────────────────────────────────────


def _json_default(value):
    """published_at arrives as a datetime; keep it ISO-8601 in the artifacts."""
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write(path, payload) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
        newline="",
    )
    print(f"\nwrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_base = sub.add_parser("baseline", help="what the engine does today")
    p_base.add_argument("--out")
    p_base.set_defaults(func=cmd_baseline)

    p_sample = sub.add_parser("sample", help="draw a stratified rating set")
    p_sample.add_argument("--out", required=True)
    p_sample.add_argument("--seed", type=int, default=SEED)
    p_sample.set_defaults(func=cmd_sample)

    p_score = sub.add_parser("score", help="compare human ratings to decisions")
    p_score.add_argument("--ratings", required=True)
    p_score.add_argument("--sample", required=True)
    p_score.add_argument("--out")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
