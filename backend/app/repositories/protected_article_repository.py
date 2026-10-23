"""
Articles that retention cleanup must never delete (#255).

Filled by scripts/protect_rated_articles.py (existing N05 and census ratings)
and by `rate_census.py build` (each new census), read by
app/ingestion/retention.py.
"""

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ProtectedArticleRow


def protected_ids(session: Session) -> set[str]:
    return set(session.execute(select(ProtectedArticleRow.article_id)).scalars())


def protect(session: Session, article_ids: Iterable[str], *, reason: str) -> int:
    """Add protection rows; existing rows keep their first reason. Returns the
    number added. The caller commits."""
    new = set(article_ids) - protected_ids(session)
    now = datetime.now(timezone.utc).isoformat()
    session.add_all(
        ProtectedArticleRow(article_id=article_id, reason=reason, created_at=now)
        for article_id in sorted(new)
    )
    session.flush()
    return len(new)
