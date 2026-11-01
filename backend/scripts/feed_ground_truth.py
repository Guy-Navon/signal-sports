"""Measure whether the feed actually filters well — audit finding N05.

The suite proves the engine does what it was told. Nothing proves that what it
was told is right. This script closes that gap by comparing engine decisions
against a HUMAN-RATED ground truth over the real ingested corpus.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py baseline --out ../docs/qa/n05_baseline.json
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py sample   --out ../docs/qa/n05_sample.json
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py score    --ratings ../docs/qa/n05_ratings.json
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py gate              # N05 regression gate (#189)
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py gate --census     # census gate, stored facts (#254)
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py gate --census --facts rerun   # census gate, rules-only rerun

``gate`` is described in docs/RELEVANCE_CONTRACT.md §Quality gate; the census
checks live in app/qa/census_gate.py.

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

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.qa import census_gate, feed_quality_gate  # noqa: E402
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


def _refresh_decisions(sample: dict) -> None:
    """Replace the sample's frozen decisions with the engine's current ones.

    Strata and weights are left exactly as drawn. An article's stratum records
    where it was SAMPLED from, which is what the weights describe; re-deriving
    it from the new decision would silently change the sampling design and make
    the population estimates wrong.
    """
    with SessionLocal() as session:
        feeds, _ = _score_all(session)
    for user_id, block in sample["profiles"].items():
        current = {s.article.id: s for s in feeds.get(user_id, [])}
        moved = 0
        for item in block["items"]:
            scored = current.get(item["id"])
            if scored is None:
                continue
            if scored.decision != item["engine_decision"]:
                moved += 1
            item["engine_decision"] = scored.decision
            item["matched_topic"] = scored.matched_topic
            item["matched_event_rule"] = scored.matched_event_rule
        print(f"{user_id}: {moved} of {len(block['items'])} rated items changed decision")


def _score_ratings(ratings_path: str, sample_path: str, live: bool) -> tuple[dict, dict]:
    """Score the ratings and return ``(report, {profile: {id: decision}})``.

    The per-item decision map is what the gate needs and the report does not
    carry: the report lists only DISAGREEMENTS, so two opposite flips would net
    to "no change" in the aggregates while the feed actually moved.
    """
    raw = json.loads(Path(ratings_path).read_text(encoding="utf-8"))
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))

    # The rating page exports {generated, seed, ratings}; a hand-written file may
    # just be {profile: {id: rating}}. Accept either rather than fail quietly.
    ratings = raw.get("ratings", raw)
    if "seed" in raw and raw["seed"] != sample["meta"].get("seed"):
        raise SystemExit(
            f"Ratings were made against seed {raw['seed']} but this sample is "
            f"{sample['meta'].get('seed')} — they describe different item sets."
        )
    for user_id in ratings:
        if user_id not in sample["profiles"]:
            raise SystemExit(f"Ratings name a profile the sample does not have: {user_id}")

    if live:
        # The sample froze the decisions that were current when it was drawn.
        # Re-scoring the same articles against the engine as it stands NOW is
        # what answers "did my change improve things?" — same people, same
        # ratings, same strata and weights, new decisions.
        _refresh_decisions(sample)

    # Restricted to RATED items: an unrated item has no ground truth, so a flip
    # there is not evidence of anything the gate can reason about.
    decisions = {
        user_id: {
            item["id"]: item["engine_decision"]
            for item in block["items"]
            if item["id"] in ratings.get(user_id, {})
        }
        for user_id, block in sample["profiles"].items()
    }

    report = _build_report(sample, ratings)
    return report, decisions


def _build_report(sample: dict, ratings: dict) -> dict:
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

        # The visible tiers are sampled as a census too, and this is the number
        # that actually describes the product. Overall accuracy is dominated by
        # the hidden majority — on a profile that hides 98% of the corpus,
        # agreeing with "hidden" scores ~98% while saying nothing about whether
        # the feed is any good. Precision here is over what the user is SHOWN.
        shown = [(i, t) for i, t in rated if i["engine_decision"] != "hidden"]
        kept = sum(1 for _, t in shown if t != "hidden")

        total = est["rated"] or 1.0

        # False hide BY SPORT (#208). The headline figure cannot resolve recall
        # work any more: hidden-football rows carry a sampling weight of ~55.9
        # against ~4.2 for basketball, so ONE football rating moves the total by
        # ~3.9pp while one basketball row moves it by ~0.29pp — a 13x difference.
        # Measured on the current corpus, two football rows are 43% of Guy's
        # remaining false hide while 23 basketball rows are 36%. Improving Israeli
        # basketball coverage is therefore almost invisible in the total. Reported,
        # deliberately NOT gated: a per-sport threshold would need its own evidence.
        fh_by_sport: dict[str, dict] = {}
        for item, truth in rated:
            if item["engine_decision"] != "hidden" or truth == "hidden":
                continue
            sport = item.get("sport") or "unknown"
            bucket = fh_by_sport.setdefault(sport, {"rows": 0, "weight": 0.0, "wanted_rows": 0})
            bucket["rows"] += 1
            bucket["weight"] += weights.get(item["stratum"], 1.0)
            if truth in ("feed", "high_feed", "push"):
                bucket["wanted_rows"] += 1
        for sport, bucket in fh_by_sport.items():
            bucket["share_of_corpus"] = round(bucket.pop("weight") / total, 4)

        report["profiles"][user_id] = {
            "rated": raw["rated"],
            "sample_counts": dict(raw),
            "false_hide_by_sport": dict(sorted(
                fh_by_sport.items(), key=lambda kv: -kv[1]["share_of_corpus"]
            )),
            "shown_precision": {
                "shown": len(shown),
                "worth_showing": kept,
                "precision": round(kept / len(shown), 3) if shown else None,
                "note": "census of the visible tiers; not an estimate",
            },
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

    return report


def cmd_score(args) -> None:
    report, _ = _score_ratings(args.ratings, args.sample, args.live)
    _write(args.out, report)
    _print_score(report)


def _print_score(report: dict) -> None:
    for user_id, p in report["profiles"].items():
        print(f"\n── {user_id} ──")
        if not p.get("rated"):
            print(f"  {p.get('note')}")
            continue
        print(f"  rated {p['rated']} items")
        sp = p["shown_precision"]
        if sp["precision"] is not None:
            print(f"  shown precision {sp['precision'] * 100:.0f}% "
                  f"({sp['worth_showing']}/{sp['shown']} of what the user sees is wanted)")
        for k, v in p["population_estimates"].items():
            print(f"    {k:14} {v * 100:5.1f}%   (sample n={p['sample_counts'].get(k, 0)})")
        by_sport = p.get("false_hide_by_sport") or {}
        if by_sport:
            print("  false hide by sport (reported, not gated):")
            for sport, b in by_sport.items():
                print(f"    {sport:11} {b['share_of_corpus'] * 100:5.2f}%  "
                      f"({b['rows']} rows, {b['wanted_rows']} rated feed+)")
        pp = p["push_precision"]
        if pp["precision"] is not None:
            print(f"  push precision {pp['precision'] * 100:.0f}% ({pp['agreed_push_worthy']}/{pp['rated']})")
        print(f"  {len(p['disagreements'])} disagreements recorded")


# ── gate ──────────────────────────────────────────────────────────────────────

_REPO = _BACKEND.parent
_QA = _REPO / "docs" / "qa"
DEFAULT_BASELINE = _QA / "n05_gate_baseline.json"
DEFAULT_N05_RATINGS = _QA / "n05_ratings.json"
DEFAULT_N05_SAMPLE = _QA / "n05_sample.json"

# The census gate (#254) starts on census #2 alone. Census #3 (#241) is added by
# passing a second --ratings/--sample pair and regenerating the baseline. Census
# #2's blind review is listed so the baseline records it: its 58 values are
# already folded into census2_ratings.json, so applying it changes 0 rows.
DEFAULT_CENSUS_BASELINES = {
    "stored": _QA / "census_gate_baseline.json",
    "rerun": _QA / "census_gate_rerun_baseline.json",
}
DEFAULT_CENSUS_RATINGS = (_QA / "census2_ratings.json",)
DEFAULT_CENSUS_SAMPLES = (_QA / "census2_sample.json",)
DEFAULT_CENSUS_REVIEWS = (_QA / "census2_review_ratings.json",)


def cmd_gate(args) -> None:
    """The regression gate: score live, compare to the frozen baseline, exit 0/1.

    Always scores ``--live``. Scoring against the decisions frozen into the
    sample would compare the baseline to itself and pass unconditionally.
    """
    # Validate the invocation BEFORE scoring: the run below reads the whole
    # corpus, and learning about a typo'd flag after that wait is pure friction.
    accepted = list(args.accept or [])
    if accepted and not args.reason:
        raise SystemExit(
            "--accept requires --reason. An accepted regression must carry an "
            "argument, otherwise it is just a silently relaxed threshold."
        )
    if args.census:
        _cmd_census_gate(args, accepted)
        return
    if args.review or args.facts != "stored":
        raise SystemExit("--review and --facts apply to the census gate only (add --census).")
    if len(args.ratings or []) > 1 or len(args.sample or []) > 1:
        raise SystemExit("The N05 gate takes one --ratings and one --sample.")
    ratings_path = (args.ratings or [str(DEFAULT_N05_RATINGS)])[0]
    sample_path = (args.sample or [str(DEFAULT_N05_SAMPLE)])[0]
    baseline_path = Path(args.baseline or DEFAULT_BASELINE)
    if not args.update_baseline and not baseline_path.exists():
        raise SystemExit(
            f"No baseline at {baseline_path}. Create one deliberately with:\n"
            f"  scripts/feed_ground_truth.py gate --update-baseline"
        )

    report, decisions = _score_ratings(ratings_path, sample_path, live=True)

    if args.update_baseline:
        baseline = feed_quality_gate.build_baseline(report, decisions)
        _write(baseline_path, baseline)
        print(
            "\nBaseline REWRITTEN. This is a deliberate act: every future change is "
            "now measured against these numbers.\n"
            "Commit it with the reasoning, and state both directions in the message."
        )
        _print_score(report)
        return

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    try:
        verdict = feed_quality_gate.evaluate(
            baseline, report, decisions, accepted=accepted, accept_reason=args.reason
        )
    except feed_quality_gate.GateInputError as exc:
        raise SystemExit(f"Cannot compare: {exc}")

    print(feed_quality_gate.format_verdict(verdict))

    if args.out:
        _write(args.out, {"meta": report["meta"], "verdict": verdict.as_dict()})

    if not verdict.passed:
        sys.exit(1)


# ── census gate (#254) ────────────────────────────────────────────────────────


def _repo_rel(path) -> str:
    """Repo-relative POSIX path for the baseline record; absolute if outside."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(_REPO.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _census_input_paths(args, baseline: dict | None) -> tuple[list, list, list]:
    """Explicit flags win; else the files the baseline was built from; else census #2.

    Returned as absolute paths: flags are relative to the working directory, the
    baseline's records are relative to the repository root.
    """
    if args.ratings or args.sample or args.review:
        ratings, samples = list(args.ratings or []), list(args.sample or [])
        if len(ratings) != len(samples) or not ratings:
            raise SystemExit(
                "The census gate pairs each --ratings with a --sample, in order "
                f"(got {len(ratings)} ratings, {len(samples)} samples)."
            )
        return (
            [Path(p).resolve() for p in ratings],
            [Path(p).resolve() for p in samples],
            [Path(p).resolve() for p in args.review or []],
        )
    if baseline is not None:
        inputs = baseline["inputs"]
        return (
            [_REPO / c["ratings"] for c in inputs["censuses"]],
            [_REPO / c["sample"] for c in inputs["censuses"]],
            [_REPO / r["path"] for r in inputs["reviews"]],
        )
    return list(DEFAULT_CENSUS_RATINGS), list(DEFAULT_CENSUS_SAMPLES), list(DEFAULT_CENSUS_REVIEWS)


def _load_census(ratings: list, samples: list, reviews: list):
    sources = [
        census_gate.CensusSource(_repo_rel(r), _repo_rel(s), _read_json(r), _read_json(s))
        for r, s in zip(ratings, samples)
    ]
    review_sources = [census_gate.ReviewSource(_repo_rel(p), _read_json(p)) for p in reviews]
    try:
        return census_gate.merge_census(sources, review_sources)
    except feed_quality_gate.GateInputError as exc:
        raise SystemExit(f"Cannot build the census: {exc}")


def _rerun_articles(articles) -> list:
    """Rules-only reclassification of ``articles`` in memory: no LLM, no translation,
    no DB writes. Mirrors ``scripts/corpus_rerun_diff.py snapshot`` so the numbers are
    comparable with a rerun diff. An article whose source has no config is dropped,
    which the census metrics then report as a row without a decision."""
    import logging
    import os

    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
    os.environ["TRANSLATION_PROVIDER"] = "disabled"
    logging.disable(logging.CRITICAL)
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config

    out = []
    for stored in articles:
        cfg = get_source_config(stored.source)
        if cfg is None:
            continue
        fresh, _, _ = ingestion_service._normalise(
            RawSourceItem(source_id=stored.source, url=stored.url, title=stored.title,
                          published_at=None, summary=stored.subtitle or ""),
            cfg,
        )
        out.append(fresh.model_copy(update={"id": stored.id, "published_at": stored.published_at}))
    return out


def _census_decisions(article_ids, profiles, facts: str) -> tuple[dict, int]:
    """Current decisions, per profile, over the census article ids only.

    ``stored`` scores the persisted facts (what the corpus serves). ``rerun`` scores
    a rules-only reclassification of the same rows, which is the only way a
    classifier or taxonomy change shows up before a backfill. Both use the
    persisted profiles from the DB."""
    wanted = set(article_ids)
    with SessionLocal() as session:
        if facts == "stored":
            feeds, corpus_size = _score_all(session)
        else:
            corpus = article_repository.get_rss_articles(session)
            corpus_size = len(corpus)
            rerun = _rerun_articles([a for a in corpus if a.id in wanted])
            feeds = {}
            for user_id in PROFILE_IDS:
                profile = profile_repository.get_by_id(session, user_id)
                if profile is None:
                    raise SystemExit(f"Profile '{user_id}' is missing from the corpus DB.")
                feeds[user_id] = build_feed(rerun, profile, include_hidden=True)
    decisions = {
        user_id: {s.article.id: s.decision for s in feed if s.article.id in wanted}
        for user_id, feed in feeds.items()
        if user_id in profiles
    }
    return decisions, corpus_size


def _print_census_metrics(baseline: dict) -> None:
    for user_id, block in baseline["profiles"].items():
        m = block.get("metrics")
        print(f"\n-- {user_id} --  {len(block['decisions'])} census decisions")
        if not m:
            print("  canary: decisions frozen for the drift check (no ratings)")
            continue
        print(f"  rated {m['rated']}")
        print(f"  shown precision  {m['shown_precision']}  ({m['worth_showing']}/{m['shown']})")
        print(f"  feed+ recall     {m['feed_plus_recall']}  ({m['feed_plus_shown']}/{m['feed_plus']})")
        print(f"  push precision   {m['push_precision']}  ({m['push_agreed']}/{m['push_fired']})")
        print(f"  push recall      {m['push_recall']}  ({m['push_recalled']}/{m['push_wanted']})")
        print(f"  >=2-notch gaps   {m['two_notch']}   gap histogram {m['gap_histogram']}")


def _cmd_census_gate(args, accepted: list) -> None:
    """The census gate: same contract as the N05 gate, census checks (#254)."""
    baseline_path = Path(args.baseline or DEFAULT_CENSUS_BASELINES[args.facts])
    baseline = None
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    elif not args.update_baseline:
        raise SystemExit(
            f"No census baseline at {baseline_path}. Create one deliberately with:\n"
            f"  scripts/feed_ground_truth.py gate --census --facts {args.facts} --update-baseline"
        )

    merged = _load_census(*_census_input_paths(args, baseline))
    if baseline is not None and not args.update_baseline:
        drift_profiles = baseline["policy"]["drift_must_be_zero"]
    else:
        drift_profiles = list(census_gate.DEFAULT_DRIFT_PROFILES)
    decisions, corpus_size = _census_decisions(
        merged.article_ids, set(merged.ratings) | set(drift_profiles), args.facts
    )
    # The file name only: which corpus copy was read, without a local path.
    meta = _run_meta(corpus_size) | {"database": Path(DATABASE_URL.split("///", 1)[-1]).name}
    print(f"census gate on {args.facts} facts, baseline {baseline_path.name}")

    if args.update_baseline:
        try:
            fresh = census_gate.build_baseline(merged, decisions, meta=meta, facts=args.facts)
        except feed_quality_gate.GateInputError as exc:
            raise SystemExit(f"Cannot build the baseline: {exc}")
        _write(baseline_path, fresh)
        print(
            "\nCensus baseline REWRITTEN. Every future change is now measured "
            "against these numbers. Commit it with the reasoning in the message."
        )
        _print_census_metrics(fresh)
        return

    try:
        verdict = census_gate.evaluate(
            baseline, merged, decisions, accepted=accepted, accept_reason=args.reason,
            facts=args.facts,
        )
    except feed_quality_gate.GateInputError as exc:
        raise SystemExit(f"Cannot compare: {exc}")

    print(census_gate.format_verdict(verdict))
    if args.out:
        _write(args.out, {"meta": meta, "inputs": merged.inputs, "verdict": verdict.as_dict()})
    if not verdict.passed:
        sys.exit(1)


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
    p_score.add_argument(
        "--live", action="store_true",
        help="score the ratings against the engine's CURRENT decisions instead "
             "of the ones frozen into the sample — the before/after gate",
    )
    p_score.set_defaults(func=cmd_score)

    p_gate = sub.add_parser(
        "gate",
        help="regression gate: score live against the committed baseline (exit 1 on regression)",
    )
    p_gate.add_argument(
        "--census", action="store_true",
        help="run the census gate (#254) instead of the N05 gate",
    )
    p_gate.add_argument(
        "--facts", choices=census_gate.FACTS_SOURCES, default="stored",
        help="--census only: score the STORED facts (relevance/profile changes) or a "
             "rules-only RERUN of the census rows (classifier/taxonomy changes); "
             "each has its own baseline",
    )
    p_gate.add_argument(
        "--ratings", action="append",
        help="ratings JSON (N05 default: n05_ratings.json). With --census: repeatable, "
             "paired in order with --sample; default = the inputs the baseline records",
    )
    p_gate.add_argument(
        "--sample", action="append",
        help="sample JSON (N05 default: n05_sample.json). With --census: repeatable",
    )
    p_gate.add_argument(
        "--review", action="append",
        help="--census only: a blind re-review ratings file whose ratings win (repeatable)",
    )
    p_gate.add_argument(
        "--baseline",
        help="baseline JSON (default n05_gate_baseline.json; census_gate_baseline.json with --census)",
    )
    p_gate.add_argument("--out", help="write the verdict as JSON")
    p_gate.add_argument(
        "--accept", action="append", metavar="CHECK_ID",
        help="accept a specific failing check (repeatable). Requires --reason.",
    )
    p_gate.add_argument(
        "--reason", help="why the accepted regression is the right call",
    )
    p_gate.add_argument(
        "--update-baseline", action="store_true",
        help="REWRITE the baseline from this run instead of checking against it",
    )
    p_gate.set_defaults(func=cmd_gate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
