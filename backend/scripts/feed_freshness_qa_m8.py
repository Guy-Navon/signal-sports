"""
M8-5 (#175) — real-data before/after QA for the 36h feed freshness window.

Runs against a FROZEN copy of the production database (never the live corpus)
and compares, for BOTH permanent profiles, the exact production consumer path
(learned profile, dismissed filtering, include_hidden=False, cluster collapse)
with FEED_FRESHNESS_ENABLED off vs on. Read-only: builds feeds, writes nothing
to the DB. Also enumerates push-tier stories through the planner's canonical
enumeration (the notification eligibility surface) in both modes.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/feed_freshness_qa_m8.py [frozen_db_path]

Output: JSON report to stdout + docs/qa artifacts are written by the caller.
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

DB = sys.argv[1] if len(sys.argv) > 1 else "data/qa_freshness_m8_frozen.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{DB}"
# Production configuration for the comparison (the frozen copy carries the
# production corpus; these mirror the production .env).
os.environ["CLUSTERING_ENABLED"] = "true"
os.environ.setdefault("PREFERENCE_ENGINE", "v2")
os.environ["FEED_MAX_AGE_HOURS"] = "36"

from app.db.database import SessionLocal, init_db  # noqa: E402

PROFILES = ["guy", "casual_deni_fan"]
NOW = datetime.now(tz=timezone.utc)
CUTOFF = NOW - timedelta(hours=36)


def _consumer_feed(session, profile_id):
    """The exact production consumer path (same as GET /api/feed/{id})."""
    from app.repositories import (article_repository, feedback_repository,
                                  profile_repository)
    from app.services.feed_service import build_feed
    from app.services.learning_service import dismissed_article_ids, with_learned
    profile = profile_repository.get_by_id(session, profile_id)
    articles = article_repository.get_rss_articles(session)
    events = feedback_repository.get_active_by_user(session, profile_id)
    dismissed = dismissed_article_ids(events)
    articles = [a for a in articles if a.id not in dismissed]
    return build_feed(articles, with_learned(profile, events),
                      include_hidden=False, session=session)


def _age_hours(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (NOW - dt).total_seconds() / 3600.0


def _card_decision(s):
    return s.cluster.decision if s.cluster is not None else s.decision


def _snapshot(feed):
    """Card-level snapshot + article-level decision map."""
    cards = []
    for s in feed:
        cards.append({
            "displayed_id": s.article.id,
            "cluster_id": s.cluster.cluster_id if s.cluster else None,
            "decision": _card_decision(s),
            "article_decision": s.decision,
            "source": s.article.source,
            "published_at": s.article.published_at.isoformat(),
            "age_hours": round(_age_hours(s.article.published_at), 1),
            "title": (s.article.translated_title or s.article.title)[:70],
        })
    return cards


def _push_stories(session, profile_id):
    from app.notifications.planner import enumerate_push_stories
    out = enumerate_push_stories(session, profile_id)
    if out is None:
        return []
    snapshots, _ = out
    return [{"canonical": s.canonical_article_id,
             "headline": s.canonical_headline[:70],
             "members": sorted(s.member_article_ids)} for s in snapshots]


def main():
    init_db()
    report = {"db": DB, "now_utc": NOW.isoformat(), "cutoff_utc": CUTOFF.isoformat(),
              "profiles": {}}

    with SessionLocal() as session:
        for pid in PROFILES:
            os.environ["FEED_FRESHNESS_ENABLED"] = "false"
            before_feed = _consumer_feed(session, pid)
            before = _snapshot(before_feed)
            before_push = _push_stories(session, pid)

            os.environ["FEED_FRESHNESS_ENABLED"] = "true"
            after_feed = _consumer_feed(session, pid)
            after = _snapshot(after_feed)
            after_push = _push_stories(session, pid)
            os.environ["FEED_FRESHNESS_ENABLED"] = "false"

            after_ids = {c["displayed_id"] for c in after}
            removed = [c for c in before if c["displayed_id"] not in after_ids
                       and c["age_hours"] > 36]
            # A before-card whose displayed member expired but whose CLUSTER
            # survives with a fresh member = canonical replacement, not removal.
            after_by_cluster = {c["cluster_id"]: c for c in after if c["cluster_id"]}
            canonical_replaced = []
            truly_removed = []
            for c in removed:
                surviving = after_by_cluster.get(c["cluster_id"]) if c["cluster_id"] else None
                if surviving is not None:
                    canonical_replaced.append({"cluster": c["cluster_id"],
                                               "old": c["displayed_id"],
                                               "new": surviving["displayed_id"]})
                else:
                    truly_removed.append(c)

            # Decision drift among still-fresh articles: same displayed id in
            # both feeds must carry the identical card + article decision.
            before_by_id = {c["displayed_id"]: c for c in before}
            drift = []
            for c in after:
                b = before_by_id.get(c["displayed_id"])
                if b and (b["decision"] != c["decision"]
                          or b["article_decision"] != c["article_decision"]):
                    drift.append({"id": c["displayed_id"],
                                  "before": b["decision"], "after": c["decision"]})

            # Fresh cards that disappeared entirely (must be none).
            lost_fresh = [c for c in before
                          if c["age_hours"] <= 36 and c["displayed_id"] not in after_ids
                          and not any(r["cluster"] == c["cluster_id"]
                                      for r in canonical_replaced)]

            before_push_keys = {tuple(p["members"]) for p in before_push}
            after_push_keys = {tuple(p["members"]) for p in after_push}
            expired_push_suppressed = [p for p in before_push
                                       if tuple(p["members"]) not in after_push_keys]

            report["profiles"][pid] = {
                "visible_cards_before": len(before),
                "visible_cards_after": len(after),
                "oldest_visible_before_h": max((c["age_hours"] for c in before), default=None),
                "oldest_visible_after_h": max((c["age_hours"] for c in after), default=None),
                "removed_over_36h": len(removed),
                "removed_per_tier": dict(Counter(c["decision"] for c in truly_removed)),
                "removed_per_source": dict(Counter(c["source"] for c in truly_removed)),
                "canonical_replaced": canonical_replaced,
                "clusters_hidden_all_expired": len({c["cluster_id"] for c in truly_removed
                                                    if c["cluster_id"]}),
                "clusters_retained_mixed_age": len(canonical_replaced),
                "decision_drift_fresh": drift,
                "fresh_cards_lost": lost_fresh,
                "push_stories_before": len(before_push),
                "push_stories_after": len(after_push),
                "expired_push_suppressed": expired_push_suppressed,
                "after_age_distribution": dict(Counter(
                    "0-12h" if c["age_hours"] <= 12 else
                    ("12-24h" if c["age_hours"] <= 24 else
                     ("24-36h" if c["age_hours"] <= 36 else ">36h!"))
                    for c in after)),
                "after_tier_distribution": dict(Counter(c["decision"] for c in after)),
            }

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
