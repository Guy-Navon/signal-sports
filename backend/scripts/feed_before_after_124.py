"""#124 — ranked-feed before/after on a frozen snapshot. READ-ONLY on articles;
requires the snapshot to already carry story_anchors + persisted clusters.

BEFORE = the flat feed (CLUSTERING_ENABLED=false), the production default that
exposed the duplicate-card / duplicate-push failures.
AFTER  = the collapsed feed (CLUSTERING_ENABLED=true), same articles, same
scores — collapse is presentation only, so any article-level decision drift is
a personalization regression and is reported as a blocking finding.

Usage: python scripts/feed_before_after_124.py <snapshot-db>
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

db = Path(sys.argv[1]).resolve()
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from app.db.database import SessionLocal                                   # noqa: E402
from app.repositories import (                                             # noqa: E402
    article_repository, feedback_repository, profile_repository,
)
from app.services.feed_service import build_feed                           # noqa: E402
from app.services.learning_service import dismissed_article_ids, with_learned  # noqa: E402

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def p(*a):
    print(*a, file=OUT)


def groups():
    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        return {g["id"]: {x["id"] for x in g["articles"]}
                for g in json.load(fh)["duplicate_groups"]}


def capture(session, user_id: str, clustering: str):
    os.environ["CLUSTERING_ENABLED"] = clustering
    profile = profile_repository.get_by_id(session, user_id)
    articles = article_repository.get_rss_articles(session)
    events = feedback_repository.get_active_by_user(session, user_id)
    dismissed = dismissed_article_ids(events)
    articles = [a for a in articles if a.id not in dismissed]
    return build_feed(articles, with_learned(profile, events),
                      include_hidden=False, session=session)


def main():
    tg = groups()
    with SessionLocal() as session:
        for user in ("guy", "casual_deni_fan"):
            flat = capture(session, user, "false")
            coll = capture(session, user, "true")

            p("=" * 96)
            p(f"PROFILE: {user}")
            p("=" * 96)

            def stats(items, label):
                per_tier = Counter(s.decision for s in items)
                pushes = [s for s in items if s.decision == "push"]
                p(f"  {label:<10} cards={len(items):<4} tiers={dict(per_tier)} "
                  f"pushes={len(pushes)}")
                return per_tier, pushes

            stats(flat, "BEFORE")
            stats(coll, "AFTER")

            # Personalization regression: collapse must not change any article's
            # own decision. Compare decisions for articles present in both.
            flat_dec = {s.article.id: s.decision for s in flat}
            drift = []
            for s in coll:
                if s.article.id in flat_dec and s.decision != flat_dec[s.article.id]:
                    drift.append((s.article.id, flat_dec[s.article.id], s.decision))
            p(f"  article-level decision drift: {len(drift)}"
              + (f"  {drift}" if drift else "  (collapse is presentation-only)"))

            # Target groups: how many separate cards before vs after; canonical.
            p(f"  {'group':<28} {'before':>6} {'after':>5}  canonical (displayed)")
            for gid, members in sorted(tg.items()):
                b = sum(1 for s in flat if s.article.id in members)
                cards = [s for s in coll if s.article.id in members]
                canon = ""
                for s in cards:
                    if s.cluster is not None:
                        canon = f"{s.article.source}:{s.article.id[:14]}"
                pushes_b = sum(1 for s in flat
                               if s.article.id in members and s.decision == "push")
                pushes_a = sum(1 for s in cards if s.decision == "push")
                p(f"  {gid:<28} {b:>6} {len(cards):>5}  {canon}"
                  f"{'  pushes ' + str(pushes_b) + '->' + str(pushes_a) if pushes_b or pushes_a else ''}")

            # No distinct story disappears: every flat VISIBLE article must be
            # either present or folded into a card of a cluster it belongs to.
            coll_ids = {s.article.id for s in coll}
            folded = set()
            for s in coll:
                if s.cluster is not None:
                    folded |= {m.article_id for m in s.cluster.members}
            lost = [i for i in flat_dec
                    if i not in coll_ids and i not in folded]
            p(f"  stories lost (visible before, absent+unfolded after): {len(lost)}"
              + (f"  {lost}" if lost else ""))
            p("")
    OUT.flush()


if __name__ == "__main__":
    main()
