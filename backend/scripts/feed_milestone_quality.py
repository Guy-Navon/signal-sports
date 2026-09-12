"""Read-only frozen-corpus milestone measurement, supplementary to the N05 gate.

Reports ARTICLE decisions and STORY notification units separately. Replays the
real planner enumeration with only freshness bypassed, because the entire
historical corpus predates the current feed window. Never plans an outbox event
or dispatches a notification. No scoring or clustering contracts are changed.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.feed_ground_truth import SessionLocal, _score_all


def measure():
    from app.notifications.planner import enumerate_push_stories
    ratings = json.loads((Path(__file__).resolve().parents[2] / "docs/qa/n05_ratings.json").read_text(encoding="utf8"))["ratings"]
    report = {"scope": "whole frozen RSS corpus, freshness bypassed for planner replay only; no sends", "profiles": {}}
    with SessionLocal() as session:
        feeds, total = _score_all(session)
        report["corpus_size"] = total
        for uid, feed in feeds.items():
            with patch("app.services.feed_service.fresh_only", side_effect=lambda articles: list(articles)):
                enumerated = enumerate_push_stories(session, uid)
            snapshots, _ = enumerated
            visible = [s for s in feed if s.decision != "hidden"]
            articles = {s.article.id: s for s in feed}
            stories = []
            for snapshot in snapshots:
                truths = {aid: ratings[uid][aid] for aid in snapshot.member_article_ids if aid in ratings[uid]}
                stories.append(asdict(snapshot) | {"ratings": truths, "approved": "push" in truths.values()})
            notified_members = {aid for story in stories for aid in story["member_article_ids"]}
            approved_ids = {aid for aid, truth in ratings[uid].items() if truth == "push"}
            # Original Guy approved notifications were the seven push-worthy
            # articles actually pushed in the starting snapshot, not all rated
            # push-worthy hidden stories. Report all uncovered ratings too.
            report["profiles"][uid] = {
                "visible_articles": len(visible),
                "cluster_cards": sum(s.cluster is not None for s in visible),
                "cluster_card_coverage": sum(s.cluster is not None for s in visible) / max(len(visible), 1),
                "visible_cluster_members": sum(s.article.cluster_id is not None for s in visible),
                "article_push_volume": sum(s.decision == "push" for s in feed),
                "story_push_volume": len(stories),
                "story_push_approved": sum(s["approved"] for s in stories),
                "story_push_precision": sum(s["approved"] for s in stories) / len(stories) if stories else None,
                "high_feed_rated_feed": sum(s.decision == "high_feed" and ratings[uid].get(s.article.id) == "feed" for s in feed),
                "uncovered_push_ratings": sorted(approved_ids - notified_members),
                "stories": stories,
                "rated_decisions": {aid: {"decision": articles[aid].decision,
                                          "event": articles[aid].article.event_type,
                                          "reasoning": articles[aid].reasoning,
                                          "contributions": articles[aid].contributions}
                                    for aid in ratings[uid] if aid in articles},
            }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = measure()
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf8")
    for uid, p in report["profiles"].items():
        print(uid, {k: v for k, v in p.items() if k not in {"stories", "rated_decisions"}})


if __name__ == "__main__":
    main()
