from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import CalibrationHeadlineRow
from app.models.calibration import CalibrationHeadline


def _row_to_headline(row: CalibrationHeadlineRow) -> CalibrationHeadline:
    return CalibrationHeadline(
        id=row.id,
        title=row.title,
        sport=row.sport,
        league=row.league,
        entities=row.entities or [],
        event_type=row.event_type,
        importance=row.importance,
        tags=row.tags or [],
    )


def _headline_to_row(h: CalibrationHeadline) -> CalibrationHeadlineRow:
    return CalibrationHeadlineRow(
        id=h.id,
        title=h.title,
        sport=h.sport,
        league=h.league,
        entities=list(h.entities),
        event_type=h.event_type,
        importance=h.importance,
        tags=list(h.tags),
    )


def get_all(session: Session) -> List[CalibrationHeadline]:
    rows = session.execute(select(CalibrationHeadlineRow)).scalars().all()
    return [_row_to_headline(r) for r in rows]


def count(session: Session) -> int:
    return session.query(CalibrationHeadlineRow).count()


def insert(session: Session, headline: CalibrationHeadline) -> None:
    session.add(_headline_to_row(headline))
    session.commit()
