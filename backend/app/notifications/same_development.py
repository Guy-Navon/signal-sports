"""Repeated reporting of the same development is not a new story (#371).

Notification identity is cluster lineage (#151). Clustering joins same-state reports only
within its 24 h window, so one agreement reported again 52 h later (Lundberg: Israel Hayom
07-20, Sport5 07-22) started a second lineage and a second message.

Before the planner creates a NEW event, it asks whether an earlier event already covers the
same development:

- a **transaction** story (negotiation / signing) on both sides;
- **both** asserting an agreement or completion (the attention evidence's ``development``);
- the **same person** (a canonical player / coach / executive id) and the **same club**;
- published within ``same_development_window()`` of each other (72 h by default).

Anything else still notifies: a different person or club, a different development (talks →
agreement, an injury), or the same agreement after the window expires (72 h of publication).

**Delivery state matters.** Only an earlier event that reached, or can still reach, the user
covers a repeat: pending / claimed / sent / failed_retryable (the dispatcher keeps retrying it;
attaching a repeat never changes its status) / unknown (it may have been delivered) /
suppressed_watermark (deliberately silent at activation). A ``failed_final`` event never
reached the user, so a repeat may notify. The check is per (profile, policy) and compares
**publication** times, never processing time. A row without attention evidence
(rows stored before the 2026-09-11 push-severity gate) is never treated as a repeat. This
module only reads; attaching is the outbox's job.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy.orm import Session

DEFAULT_WINDOW_HOURS = 72.0


def same_development_window() -> timedelta:
    """``NOTIFICATION_SAME_DEVELOPMENT_HOURS`` (default 72; 0 turns the check off). Read at
    call time; an unparsable value falls back to the default."""
    raw = os.getenv("NOTIFICATION_SAME_DEVELOPMENT_HOURS", str(DEFAULT_WINDOW_HOURS))
    try:
        hours = float(raw)
    except ValueError:
        hours = DEFAULT_WINDOW_HOURS
    return timedelta(hours=max(hours, 0.0))
_NOT_COVERING = frozenset({"failed_final"})
_TRANSACTION_EVENTS = frozenset({"negotiation", "signing", "major_signing"})
_SETTLED = "agreement_or_completion"
_PERSON_PREFIXES = ("player:", "coach:", "exec:")


def _published(row) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(row.published_at))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _settled_transaction(row) -> Optional[tuple[frozenset, frozenset, datetime]]:
    """(people, clubs, published) for a row asserting a settled transaction, else None."""
    attention = (row.classification_trace or {}).get("attention")
    if not attention or attention.get("development") != _SETTLED:
        return None
    if row.event_type not in _TRANSACTION_EVENTS:
        return None
    published = _published(row)
    if published is None:
        return None
    ids = set(row.entity_ids or ())
    ids |= {a.get("anchor") for a in (row.story_anchors or ()) if isinstance(a, dict)}
    people = frozenset(i for i in ids if i and i.startswith(_PERSON_PREFIXES))
    clubs = frozenset(i for i in (ids | set(attention.get("subject_entity_ids") or ()))
                      if i and i.startswith("team:"))
    if not people or not clubs:
        return None
    return people, clubs, published


def find_same_development_event(session: Session, profile_id: str, policy_version: str,
                                member_article_ids: Sequence[str]) -> Optional[str]:
    """The id of an earlier event that already covers this story's development, or None."""
    from app.db.orm_models import ArticleRow, NotificationEventRow, NotificationStoryMemberRow

    window = same_development_window()
    if window <= timedelta(0):
        return None
    rows = session.query(ArticleRow).filter(ArticleRow.id.in_(list(member_article_ids))).all()
    mine = [f for f in (_settled_transaction(r) for r in rows) if f is not None]
    if not mine:
        return None
    lo = min(f[2] for f in mine) - window
    hi = max(f[2] for f in mine) + window

    lineage = (
        session.query(NotificationStoryMemberRow.event_id, ArticleRow)
        .join(ArticleRow, ArticleRow.id == NotificationStoryMemberRow.article_id)
        .join(NotificationEventRow, NotificationEventRow.id == NotificationStoryMemberRow.event_id)
        .filter(NotificationStoryMemberRow.profile_id == profile_id,
                NotificationStoryMemberRow.policy_version == policy_version,
                NotificationEventRow.status.notin_(_NOT_COVERING))
        .all()
    )
    for event_id, row in sorted(lineage, key=lambda x: str(x[1].published_at)):
        theirs = _settled_transaction(row)
        if theirs is None or not (lo <= theirs[2] <= hi):
            continue
        for people, clubs, published in mine:
            if (people & theirs[0] and clubs & theirs[1]
                    and abs(published - theirs[2]) <= window):
                return event_id
    return None
