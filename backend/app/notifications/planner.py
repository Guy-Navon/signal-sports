"""
Production PUSH notification planner for the pilot profile (M7-6, #152).

Feed eligibility is the source of truth for PUSH decisions. The planner does
NOT reconstruct eligibility from article importance or a second ruleset — it
invokes exactly the canonical production path behind ``GET /api/feed/guy``
(learned profile, dismissed filtering, ``include_hidden=False``, cluster
collapse) and reads the story-level card decisions the user would see.

For every PUSH card it snapshots the story (full component membership from
the DB — not just the card's visible members — so identity covers suppressed
members too) and hands it to the M7-5 outbox, whose database uniqueness
decides created vs already-notified. The planner never mutates feed decisions
and never sends anything: delivery is M7-7's dispatcher.

GATING, both deliberate:
- no watermark → NO planning (fail-closed against activation floods; only the
  M7-10 guarded initialization sets a watermark);
- ``TELEGRAM_NOTIFICATIONS_ENABLED`` false → NO planning. Rollback semantics:
  disabling Telegram pauses planning entirely rather than accumulating a
  stale pending backlog that would flood on re-enable. A story from the
  disabled window notifies on re-enable only if it is STILL push-visible in
  the feed and was never notified — the feed's own horizon bounds staleness.

Ordering: the planner runs AFTER clustering (it must see today's components)
and BEFORE retention cleanup (M7-3) — planning must observe the full window
before anything is deleted.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.notifications.outbox import (
    ALREADY_NOTIFIED,
    CREATED,
    NO_WATERMARK,
    StorySnapshot,
    plan_story,
)

logger = logging.getLogger(__name__)


def telegram_enabled() -> bool:
    return os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false").strip().lower() == "true"


def pilot_profile_id() -> str:
    """The pilot is Guy-only by contract; the env var exists so tests and a
    future multi-profile milestone have one explicit seam, not a hardcode."""
    return os.getenv("TELEGRAM_NOTIFICATION_PROFILE", "guy")


def policy_version() -> str:
    return os.getenv("TELEGRAM_NOTIFICATION_POLICY_VERSION", "v1")


def _story_members(session: Session, scored) -> list[str]:
    """Full component membership for identity — from the DB, not the card.

    The card lists VISIBLE members only; identity must also cover members the
    user's preferences hid, or a hidden member resurfacing later would look
    like a new story.
    """
    if scored.cluster is not None:
        from app.repositories import cluster_repository
        members = cluster_repository.get_member_ids(session, scored.cluster.cluster_id)
        if members:
            return list(members)
    return [scored.article.id]


def _effective_decision(scored) -> str:
    """The story-level decision the user experiences: the CARD decision for a
    clustered story (max over visible members), the article's own otherwise."""
    return scored.cluster.decision if scored.cluster is not None else scored.decision


def enumerate_push_stories(session: Session,
                           profile_id: str) -> Optional[tuple[list, int]]:
    """Canonical enumeration of the profile's CURRENT push-tier stories.

    THE single implementation of "which stories are PUSH right now" — used by
    the per-cycle planner below AND by the M7-10 guarded activation
    initialization (scripts/init_notification_watermark.py). Both must see the
    exact same stories or the watermark would not suppress what the planner
    plans; extracting this function is what prevents a second ruleset.

    Returns (snapshots, ignored_non_push_count), or None if the profile does
    not exist. Read-only: builds the production feed, mutates nothing.
    """
    from app.repositories import (
        article_repository,
        feedback_repository,
        profile_repository,
    )
    from app.services.feed_service import build_feed
    from app.services.learning_service import dismissed_article_ids, with_learned

    profile = profile_repository.get_by_id(session, profile_id)
    if profile is None:
        return None

    articles = article_repository.get_rss_articles(session)
    events = feedback_repository.get_active_by_user(session, profile_id)
    dismissed = dismissed_article_ids(events)
    articles = [a for a in articles if a.id not in dismissed]
    feed = build_feed(articles, with_learned(profile, events),
                      include_hidden=False, session=session)

    snapshots: list[StorySnapshot] = []
    ignored_non_push = 0
    for scored in feed:
        if _effective_decision(scored) != "push":
            ignored_non_push += 1
            continue
        snapshots.append(StorySnapshot(
            member_article_ids=_story_members(session, scored),
            cluster_id=scored.cluster.cluster_id if scored.cluster else None,
            canonical_article_id=scored.article.id,
            canonical_headline=(scored.article.translated_title
                                or scored.article.title),
            source=getattr(scored.article, "source_display_name", None)
                   or scored.article.source,
            url=scored.article.url,
            tier="push",
            decision_provenance={
                "card_decision": "push",
                "displayed_article_id": scored.article.id,
                "displayed_reason": (scored.cluster.displayed_reason
                                     if scored.cluster else "unclustered"),
            },
        ))
    return snapshots, ignored_non_push


def plan_cycle_notifications(session: Session) -> dict:
    """Plan notification events for newly PUSH-eligible stories. Returns the
    cycle summary persisted on the scheduler cycle record."""
    if not telegram_enabled():
        return {"skipped": "telegram_disabled"}

    profile_id = pilot_profile_id()
    policy = policy_version()

    enumerated = enumerate_push_stories(session, profile_id)
    if enumerated is None:
        logger.error("notification planner: profile %r not found", profile_id)
        return {"error": f"profile_not_found:{profile_id}"}
    snapshots, ignored_non_push = enumerated

    summary = {
        "profile": profile_id,
        "policy_version": policy,
        "push_stories": len(snapshots),
        "created": [],                 # event ids
        "already_notified": 0,
        "ignored_non_push": ignored_non_push,
        "no_watermark": False,
    }

    for snapshot in snapshots:
        out = plan_story(session, profile_id=profile_id, policy_version=policy,
                         story=snapshot)
        if out.outcome == CREATED:
            summary["created"].append(out.event_id)
            logger.info("notification planned: %s (%s)",
                        out.event_id, snapshot.canonical_headline[:60])
        elif out.outcome == ALREADY_NOTIFIED:
            summary["already_notified"] += 1
        elif out.outcome == NO_WATERMARK:
            # Fail-closed: no watermark means activation initialization has not
            # run for this (profile, policy) — plan NOTHING this cycle.
            summary["no_watermark"] = True
            summary["created"] = []
            logger.info("notification planner: no watermark for (%s, %s) — "
                        "planning disabled until M7-10 initialization",
                        profile_id, policy)
            break

    return summary
