from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.orm_models import IngestionRunRow
from app.models.ingestion import IngestionRunRecord


def _row_to_record(row: IngestionRunRow) -> IngestionRunRecord:
    started = datetime.fromisoformat(row.started_at)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    finished: Optional[datetime] = None
    if row.finished_at:
        finished = datetime.fromisoformat(row.finished_at)
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)

    return IngestionRunRecord(
        id=row.id,
        source_id=row.source_id,
        started_at=started,
        finished_at=finished,
        status=row.status,
        fetched_count=row.fetched_count,
        inserted_count=row.inserted_count,
        skipped_duplicate_count=row.skipped_duplicate_count,
        failed_count=row.failed_count,
        error_message=row.error_message,
        metrics=row.metrics,
    )


def insert(session: Session, record: IngestionRunRecord) -> None:
    row = IngestionRunRow(
        id=record.id,
        source_id=record.source_id,
        started_at=record.started_at.isoformat(),
        finished_at=record.finished_at.isoformat() if record.finished_at else None,
        status=record.status,
        fetched_count=record.fetched_count,
        inserted_count=record.inserted_count,
        skipped_duplicate_count=record.skipped_duplicate_count,
        failed_count=record.failed_count,
        error_message=record.error_message,
        metrics=record.metrics,
    )
    session.add(row)
    session.commit()


def get_recent(session: Session, limit: int = 50) -> List[IngestionRunRecord]:
    rows = (
        session.execute(
            select(IngestionRunRow)
            .order_by(IngestionRunRow.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [_row_to_record(r) for r in rows]


def get_recent_for_source(
    session: Session, source_id: str, limit: int = 20
) -> List[IngestionRunRecord]:
    """Most recent runs for one source, newest first (source-health, PR 13)."""
    rows = (
        session.execute(
            select(IngestionRunRow)
            .where(IngestionRunRow.source_id == source_id)
            .order_by(IngestionRunRow.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [_row_to_record(r) for r in rows]
