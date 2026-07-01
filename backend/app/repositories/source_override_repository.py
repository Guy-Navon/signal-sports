"""
Runtime source enabled/disabled overrides (PR 13.1).

config.py holds each source's code default; an override row (set from the
Sources page UI via PATCH /api/ingest/sources/{source_id}) wins over the
default and survives restarts. Used by run-all ingestion, the scheduler,
GET /api/ingest/sources, and source health.
"""

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import SourceOverrideRow


def get_all(session: Session) -> Dict[str, bool]:
    """source_id → enabled for every stored override."""
    rows = session.execute(select(SourceOverrideRow)).scalars().all()
    return {row.source_id: bool(row.enabled) for row in rows}


def get_override(session: Session, source_id: str) -> Optional[bool]:
    row = session.get(SourceOverrideRow, source_id)
    return bool(row.enabled) if row is not None else None


def set_override(session: Session, source_id: str, enabled: bool) -> None:
    row = session.get(SourceOverrideRow, source_id)
    if row is None:
        session.add(SourceOverrideRow(source_id=source_id, enabled=enabled))
    else:
        row.enabled = enabled
    session.commit()


def clear_override(session: Session, source_id: str) -> None:
    """Remove an override so the config.py default applies again (used by tests)."""
    row = session.get(SourceOverrideRow, source_id)
    if row is not None:
        session.delete(row)
        session.commit()
