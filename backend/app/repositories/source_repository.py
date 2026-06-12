from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import SourceRow
from app.models.source import Source


def _row_to_source(row: SourceRow) -> Source:
    return Source(
        id=row.id,
        display_name=row.display_name,
        language=row.language,
        source_type=row.source_type,
        enabled=row.enabled,
        trust_level=row.trust_level,
    )


def _source_to_row(source: Source) -> SourceRow:
    return SourceRow(
        id=source.id,
        display_name=source.display_name,
        language=source.language,
        source_type=source.source_type,
        enabled=source.enabled,
        trust_level=source.trust_level,
    )


def get_all(session: Session) -> List[Source]:
    rows = session.execute(select(SourceRow)).scalars().all()
    return [_row_to_source(r) for r in rows]


def get_by_id(session: Session, source_id: str) -> Optional[Source]:
    row = session.get(SourceRow, source_id)
    return _row_to_source(row) if row else None


def count(session: Session) -> int:
    return session.query(SourceRow).count()


def insert(session: Session, source: Source) -> None:
    session.add(_source_to_row(source))
    session.commit()
