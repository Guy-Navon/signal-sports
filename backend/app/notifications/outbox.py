"""
Stable story notification identity + durable outbox (M7-5, #151).

THE LOAD-BEARING INVARIANT:

    Once Guy has been notified about a story, no later cluster expansion,
    canonical replacement or duplicate source article may create another
    notification for that same story.

WHY LINEAGE, NOT CLUSTER IDS. Inspection of the Milestone 6 clustering
persistence proved cluster ids are stable under APPEND but not under
evolution: `reconcile_scope` preserves ids only through overlap
reconciliation — an anchor change (an earlier article joining) or a component
merge retires an id and mints a new one, and `anchor_article_id` is nullable
under pruning. Article URLs, headlines and canonical article ids are all
explicitly forbidden keys (a canonical can be replaced; a URL can be
republished). What IS immutable forever is the ARTICLE ID
(`rss_` + sha1(url)) — a republished URL maps back to the same id and is
URL-deduped away.

So a notified story's identity is its MEMBER LINEAGE: creating an event
inserts every current component member into ``notification_story_members``,
where ``UNIQUE(profile_id, policy_version, article_id)`` is the enforcement.
The database, not an application ``exists()`` check, is what makes a
duplicate event impossible:

  - a second source joins the story        → its NEW article attaches to the
    existing event's lineage (reason="expansion"); no new event;
  - the component's cluster id churns      → members didn't; conflicts prove
    the story was already notified;
  - the canonical article changes          → no new members at all;
  - two previously-notified components
    later merge                            → members conflict against TWO
    events; NO message; the merge is recorded on both events' lineage notes;
  - retention deletes old member articles  → lineage rows have no FK to
    ``articles`` and survive as the notification system's memory;
  - the same source republishes a URL      → same article id, same lineage row.

WATERMARK. Enabling Telegram must not flood historical PUSH stories: the
planner refuses to plan for a profile with no ``notification_watermarks``
row, and the guarded activation initialization plants ``suppressed_watermark``
events (WITH lineage) for every story already eligible at activation — so
they can never notify later, and the suppression itself is auditable.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm_models import (
    NotificationEventRow,
    NotificationStoryMemberRow,
    NotificationWatermarkRow,
)

logger = logging.getLogger(__name__)

# ── Event statuses ────────────────────────────────────────────────────────────
PENDING = "pending"
CLAIMED = "claimed"
SENT = "sent"
FAILED_RETRYABLE = "failed_retryable"
FAILED_FINAL = "failed_final"
UNKNOWN = "unknown"
SUPPRESSED_WATERMARK = "suppressed_watermark"

# ── Plan outcomes ─────────────────────────────────────────────────────────────
CREATED = "created"
ALREADY_NOTIFIED = "already_notified"
NO_WATERMARK = "no_watermark"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class StorySnapshot:
    """What the production feed said about the story AT PLANNING TIME."""

    member_article_ids: Sequence[str]        # every current component member (≥1)
    cluster_id: Optional[str]                # None for an unclustered story
    canonical_article_id: str
    canonical_headline: str
    source: str
    url: str
    tier: str
    decision_provenance: dict = field(default_factory=dict)


@dataclass
class PlanOutcome:
    outcome: str                             # created | already_notified | no_watermark
    event_id: Optional[str] = None           # the governing event (new or existing)
    attached_member_ids: tuple = ()          # members newly added to an existing lineage


# ── Watermark ─────────────────────────────────────────────────────────────────

def get_watermark(session: Session, profile_id: str,
                  policy_version: str) -> Optional[NotificationWatermarkRow]:
    return session.get(NotificationWatermarkRow, (profile_id, policy_version))


def set_watermark(session: Session, profile_id: str, policy_version: str,
                  suppressed_story_count: int = 0) -> NotificationWatermarkRow:
    """Guarded activation initialization calls this ONCE per (profile, policy)."""
    existing = get_watermark(session, profile_id, policy_version)
    if existing is not None:
        return existing
    row = NotificationWatermarkRow(
        profile_id=profile_id, policy_version=policy_version,
        activated_at=_now_iso(), suppressed_story_count=suppressed_story_count,
    )
    session.add(row)
    session.commit()
    return row


# ── The core mechanism ────────────────────────────────────────────────────────

def plan_story(
    session: Session,
    *,
    profile_id: str,
    policy_version: str,
    story: StorySnapshot,
    initial_status: str = PENDING,
) -> PlanOutcome:
    """Create ONE durable notification event for a story — or prove there is one.

    Atomic per story: the event row and ALL member lineage rows commit
    together; any lineage UNIQUE conflict rolls the whole attempt back and
    routes to the already-notified path (attach genuinely new members to the
    existing lineage, never send again).

    ``initial_status=SUPPRESSED_WATERMARK`` is the activation-initialization
    path: it plants the identity WITHOUT a deliverable event.
    """
    if not story.member_article_ids:
        raise ValueError("a story snapshot must carry at least one member article id")

    if get_watermark(session, profile_id, policy_version) is None:
        return PlanOutcome(outcome=NO_WATERMARK)

    event_id = f"notif_{uuid.uuid4().hex[:20]}"
    now = _now_iso()
    try:
        session.add(NotificationEventRow(
            id=event_id, profile_id=profile_id, policy_version=policy_version,
            status=initial_status, created_at=now,
            cluster_id_at_creation=story.cluster_id,
            canonical_article_id=story.canonical_article_id,
            canonical_headline=story.canonical_headline,
            source=story.source, url=story.url, tier=story.tier,
            decision_provenance=story.decision_provenance or None,
        ))
        for aid in dict.fromkeys(story.member_article_ids):   # de-dup, keep order
            session.add(NotificationStoryMemberRow(
                profile_id=profile_id, policy_version=policy_version,
                article_id=aid, event_id=event_id, added_at=now, reason="creation",
            ))
        session.commit()
        return PlanOutcome(outcome=CREATED, event_id=event_id)
    except IntegrityError:
        session.rollback()

    # ── Already notified: attach genuinely new members to the existing lineage ──
    existing = (
        session.query(NotificationStoryMemberRow)
        .filter(
            NotificationStoryMemberRow.profile_id == profile_id,
            NotificationStoryMemberRow.policy_version == policy_version,
            NotificationStoryMemberRow.article_id.in_(list(story.member_article_ids)),
        )
        .all()
    )
    governing_events = sorted({m.event_id for m in existing})
    if not governing_events:                    # pragma: no cover - defensive
        raise RuntimeError("lineage conflict without a governing event")

    # Two previously-notified components merging surface as members belonging
    # to MULTIPLE events. Policy: no message either way; new members attach to
    # the OLDEST event; the merge is auditable on every involved event.
    rows = (
        session.query(NotificationEventRow)
        .filter(NotificationEventRow.id.in_(governing_events))
        .all()
    )
    governing = min(rows, key=lambda r: r.created_at)
    if len(governing_events) > 1:
        note = {
            "at": _now_iso(),
            "kind": "component_merge_observed",
            "events": governing_events,
            "governing": governing.id,
        }
        for r in rows:
            r.lineage_notes = (r.lineage_notes or []) + [note]
        logger.info(
            "notification lineage: components of events %s merged — no new message",
            governing_events,
        )

    known = {m.article_id for m in existing}
    reason = "merge" if len(governing_events) > 1 else "expansion"
    attached = []
    for aid in dict.fromkeys(story.member_article_ids):
        if aid in known:
            continue
        session.add(NotificationStoryMemberRow(
            profile_id=profile_id, policy_version=policy_version,
            article_id=aid, event_id=governing.id, added_at=_now_iso(),
            reason=reason,
        ))
        attached.append(aid)
    session.commit()
    return PlanOutcome(outcome=ALREADY_NOTIFIED, event_id=governing.id,
                       attached_member_ids=tuple(attached))


def already_notified(session: Session, profile_id: str, policy_version: str,
                     member_article_ids: Sequence[str]) -> Optional[str]:
    """Read-only probe: the governing event id if ANY member is in a notified
    lineage. (The WRITE path never relies on this — the UNIQUE constraint is
    the mechanism; this exists for observability and planning diagnostics.)"""
    row = (
        session.query(NotificationStoryMemberRow.event_id)
        .filter(
            NotificationStoryMemberRow.profile_id == profile_id,
            NotificationStoryMemberRow.policy_version == policy_version,
            NotificationStoryMemberRow.article_id.in_(list(member_article_ids)),
        )
        .first()
    )
    return row[0] if row else None
