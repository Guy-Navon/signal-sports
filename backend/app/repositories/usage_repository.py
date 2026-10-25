"""Feed-view counting per user and day (#250). Read by the pilot report (#252)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.db.orm_models import UsageDayRow

_DAY_ZONE = ZoneInfo("Asia/Jerusalem")


def record_feed_view(session: Session, user_id: str, *, day: Optional[date] = None,
                     now: Optional[datetime] = None) -> None:
    """Count one feed view for ``user_id`` on ``day`` (default: today in Israel).
    A single atomic upsert, so concurrent requests cannot create two rows."""
    now = now or datetime.now(tz=timezone.utc)
    day_key = (day or now.astimezone(_DAY_ZONE).date()).isoformat()
    stamp = now.isoformat()
    stmt = insert(UsageDayRow).values(
        user_id=user_id, day=day_key, feed_views=1, first_view_at=stamp, last_view_at=stamp,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UsageDayRow.user_id, UsageDayRow.day],
        set_={"feed_views": UsageDayRow.feed_views + 1, "last_view_at": stamp},
    )
    session.execute(stmt)
    session.commit()
