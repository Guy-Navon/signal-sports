"""Read-only G1 event-only oracle; intentionally ignores semantic evidence.

An optimistic bound, NOT a proposal to rewrite facts. Tries every allowed event
while preserving sport, entities, competitions and profile. Report identifies
football rows only rescued by calling them unrelated exceptional events.
Set DATABASE_URL to the frozen pre-change backup before invoking this script.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from scripts.feed_ground_truth import SessionLocal, _score_all
    from app.classification.validation import ALLOWED_EVENT_TYPES
    from app.repositories import profile_repository
    from app.services.preference_engine import score_article_v2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    qa = Path(__file__).resolve().parents[2] / "docs/qa"
    sample = json.loads((qa / "n05_sample.json").read_text(encoding="utf8"))["profiles"]["guy"]
    ratings = json.loads((qa / "n05_ratings.json").read_text(encoding="utf8"))["ratings"]["guy"]
    items = {i["id"]: i for i in sample["items"]}
    weights = {k: v["weight"] for k, v in sample["strata"].items()}
    denominator = sum(weights[items[aid]["stratum"]] for aid in ratings if aid in items)
    rows = []
    with SessionLocal() as session:
        feeds, _ = _score_all(session)
        profile = profile_repository.get_by_id(session, "guy")
        for scored in feeds["guy"]:
            article = scored.article
            if scored.decision != "hidden" or ratings.get(article.id, "hide") == "hide":
                continue
            if article.id not in items:
                continue
            events = []
            for event in sorted(ALLOWED_EVENT_TYPES):
                candidate = article.model_copy(update={"event_type": event})
                if score_article_v2(candidate, profile).decision != "hidden":
                    events.append(event)
            rows.append({"id": article.id, "title": article.title, "subtitle": article.subtitle,
                         "sport": article.sport, "event": article.event_type,
                         "entity_ids": article.entity_ids, "primary_competition": article.primary_competition,
                         "rating": ratings[article.id], "weight": weights[items[article.id]["stratum"]],
                         "visible_if_event": events})
    report = {"scope": "Optimistic event-only oracle, not semantically valid corrections",
              "weighted_denominator": denominator,
              "false_hide_before": sum(r["weight"] for r in rows) / denominator,
              "oracle_floor": sum(r["weight"] for r in rows if not r["visible_if_event"]) / denominator,
              "floor_without_football_relabeling": sum(r["weight"] for r in rows if not r["visible_if_event"] or r["sport"] == "football") / denominator,
              "rows": rows}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print({k: v for k, v in report.items() if k != "rows"})


if __name__ == "__main__":
    main()
