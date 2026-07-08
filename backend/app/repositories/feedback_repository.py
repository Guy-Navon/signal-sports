from datetime import datetime, timezone
from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import FeedbackRow
from app.models.feedback import FeedbackEvent


def _row_to_event(row: FeedbackRow) -> FeedbackEvent:
    created = datetime.fromisoformat(row.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return FeedbackEvent(
        id=row.id,
        user_id=row.user_id,
        article_id=row.article_id,
        action=row.action,
        created_at=created,
        context=row.context,
        retracted=bool(row.retracted),
    )


def _event_to_row(event: FeedbackEvent) -> FeedbackRow:
    return FeedbackRow(
        id=event.id,
        user_id=event.user_id,
        article_id=event.article_id,
        action=event.action,
        created_at=event.created_at.isoformat(),
        context=event.context,
        retracted=1 if event.retracted else 0,
    )


def get_all(session: Session) -> List[FeedbackEvent]:
    rows = session.execute(select(FeedbackRow)).scalars().all()
    return [_row_to_event(r) for r in rows]


def get_by_user(session: Session, user_id: str) -> List[FeedbackEvent]:
    rows = (
        session.execute(select(FeedbackRow).where(FeedbackRow.user_id == user_id))
        .scalars()
        .all()
    )
    return [_row_to_event(r) for r in rows]


def get_active_by_user(session: Session, user_id: str) -> List[FeedbackEvent]:
    """Non-retracted events only — the derivation input (issue #34)."""
    rows = (
        session.execute(
            select(FeedbackRow)
            .where(FeedbackRow.user_id == user_id)
            .where(FeedbackRow.retracted == 0)
        )
        .scalars()
        .all()
    )
    return [_row_to_event(r) for r in rows]


def insert(session: Session, event: FeedbackEvent) -> None:
    session.add(_event_to_row(event))
    session.commit()


def retract(session: Session, user_id: str, event_ids: List[str]) -> int:
    """Tombstone the given events (issue #34) — the log stays append-only;
    derivation simply stops seeing them. Returns the number retracted."""
    rows = (
        session.execute(
            select(FeedbackRow)
            .where(FeedbackRow.user_id == user_id)
            .where(FeedbackRow.id.in_(event_ids))
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.retracted = 1
    session.commit()
    return len(rows)
