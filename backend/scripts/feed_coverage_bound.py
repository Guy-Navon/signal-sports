"""Read-only coverage oracle for #208 — how much recall is reachable via FACTS COVERAGE.

The companion to `feed_recall_bound.py`. That script answered "what if every
event type were perfect?" and found the honest floor is 14.217% — above the 12%
target that had been set for #191, because it was derived from a wrong model.

The model was wrong because **visibility needs a SCOPE MATCH — an entity or
competition the profile follows — AND an event rule.** Counting how much `news`
rows contribute to false hide and assuming a corrected event type would surface
them ignores the first half. #190 had already measured it: of 25 competition-less
false hides, 24 had no resolved entity whatsoever.

So this script varies the other axis, and then both:

  coverage-only  keep the stored event type, attach each scope Guy actually
                 follows, ask whether the row becomes visible
  combined       vary scope AND event together — the true ceiling of facts work

INTENTIONALLY OPTIMISTIC, AND NOT A PROPOSAL. Attaching a scope an article does
not support is exactly as much a fabricated fact as relabelling a radio segment
`title_win`, which the event oracle correctly refused. The output therefore names
the rescuing scope for every row so each one can be judged by hand. A bound tells
you whether the work is worth scoping; it never tells you what to write.

Read-only: no DB writes, no network, no ingestion, no notifications.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/feed_coverage_bound.py --out ../docs/qa/n208_coverage_bound.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROFILE_ID = "guy"


def main() -> int:
    from scripts.feed_ground_truth import SessionLocal, _score_all
    from app.classification.validation import ALLOWED_EVENT_TYPES
    from app.repositories import profile_repository
    from app.services.preference_engine import score_article_v2
    from app.taxonomy.competitions import COMPETITIONS
    from app.taxonomy.entities import ENTITIES

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    qa = Path(__file__).resolve().parents[2] / "docs/qa"
    sample = json.loads((qa / "n05_sample.json").read_text(encoding="utf8"))["profiles"][PROFILE_ID]
    ratings = json.loads((qa / "n05_ratings.json").read_text(encoding="utf8"))["ratings"][PROFILE_ID]
    items = {i["id"]: i for i in sample["items"]}
    weights = {k: v["weight"] for k, v in sample["strata"].items()}
    denominator = sum(weights[items[aid]["stratum"]] for aid in ratings if aid in items)

    with SessionLocal() as session:
        feeds, _ = _score_all(session)
        profile = profile_repository.get_by_id(session, PROFILE_ID)
        v2 = profile.profile_v2

        # Only scopes the profile treats POSITIVELY can rescue a row. football and
        # tennis sit at level -1: those rows already HAVE a scope match, which is
        # why the event oracle could still move some of them and why they are not
        # a coverage problem.
        positive = [a for a in v2.scope_affinities if a.level > 0]
        scopes = [(a.scope, a.target_id) for a in positive]

        def with_scope(article, scope, target_id):
            """Return a copy of the article as if it had resolved this scope."""
            if scope == "competition":
                comp = COMPETITIONS.get(target_id)
                if comp is None:
                    return None
                return article.model_copy(update={
                    "primary_competition": target_id,
                    "league": comp.display_en,
                    "sport": comp.sport,
                })
            entity = ENTITIES.get(target_id)
            if entity is None:
                return None
            return article.model_copy(update={
                "entity_ids": sorted(set(article.entity_ids or []) | {target_id}),
                "entities": sorted(set(article.entities or []) | {entity.legacy_name}),
                "sport": entity.sport,
            })

        rows = []
        for scored in feeds[PROFILE_ID]:
            article = scored.article
            if scored.decision != "hidden":
                continue
            if ratings.get(article.id, "hide") == "hide" or article.id not in items:
                continue

            coverage_hits, combined_hits = [], []
            for scope, target_id in scopes:
                candidate = with_scope(article, scope, target_id)
                if candidate is None:
                    continue
                if score_article_v2(candidate, profile).decision != "hidden":
                    coverage_hits.append(target_id)
                for event in sorted(ALLOWED_EVENT_TYPES):
                    probe = candidate.model_copy(update={"event_type": event})
                    if score_article_v2(probe, profile).decision != "hidden":
                        combined_hits.append(f"{target_id}+{event}")
                        break

            rows.append({
                "id": article.id,
                "title": article.translated_title or article.title,
                "sport": article.sport,
                "event_type": article.event_type,
                "entity_ids": list(article.entity_ids or []),
                "primary_competition": article.primary_competition,
                "human_rating": ratings[article.id],
                "stratum": items[article.id]["stratum"],
                "weight": weights[items[article.id]["stratum"]],
                "rescued_by_coverage_only": coverage_hits,
                "rescued_by_coverage_and_event": sorted({h.split("+")[0] for h in combined_hits}),
            })

    total_fh = sum(r["weight"] for r in rows)

    def floor(key):
        remaining = sum(r["weight"] for r in rows if not r[key])
        return round(remaining / denominator, 5)

    report = {
        "scope": (
            "Optimistic upper bound on recall reachable by FACTS COVERAGE for the "
            "'guy' profile, over the hand-rated sample. Not a proposal: attaching a "
            "scope an article does not support is a fabricated fact."
        ),
        "profile": PROFILE_ID,
        "weighted_denominator": round(denominator, 4),
        "false_hide_now": round(total_fh / denominator, 5),
        "floor_coverage_only": floor("rescued_by_coverage_only"),
        "floor_coverage_and_event": floor("rescued_by_coverage_and_event"),
        "positive_scopes_tried": [t for _, t in scopes],
        "rows": sorted(rows, key=lambda r: -r["weight"]),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="")

    print(f"false hide now                    {report['false_hide_now'] * 100:6.2f}%")
    print(f"floor, coverage only              {report['floor_coverage_only'] * 100:6.2f}%")
    print(f"floor, coverage + event           {report['floor_coverage_and_event'] * 100:6.2f}%")
    print(f"\n{len(rows)} false hides; "
          f"{sum(1 for r in rows if r['rescued_by_coverage_only'])} rescued by coverage alone, "
          f"{sum(1 for r in rows if r['rescued_by_coverage_and_event'])} by coverage+event, "
          f"{sum(1 for r in rows if not r['rescued_by_coverage_and_event'])} unreachable")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
