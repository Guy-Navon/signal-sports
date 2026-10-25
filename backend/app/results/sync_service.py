"""Results synchronization (issue #178).

Fetches the tracked competitions through the configured provider and upserts
them idempotently. Bookkeeping lives in ``results_sync_state`` (one row) which
both throttles the scheduler stage (so opening the page never triggers provider
calls and cycles don't hammer the API) and records the last outcome for ops.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import ResultsSyncStateRow
from app.repositories import game_result_repository
from app.results import settings
from app.results.providers import ResultsProvider, get_provider

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _state(session: Session) -> ResultsSyncStateRow:
    row = session.get(ResultsSyncStateRow, 1)
    if row is None:
        row = ResultsSyncStateRow(id=1)
        session.add(row)
        session.commit()
    return row


def _rate_limited_until(session: Session) -> Optional[datetime]:
    summary = _state(session).last_summary or {}
    value = summary.get("rate_limited_until") if isinstance(summary, dict) else None
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def get_sync_state(session: Session) -> dict:
    row = _state(session)
    return {
        "last_attempt_at": row.last_attempt_at,
        "last_success_at": row.last_success_at,
        "last_status": row.last_status,
        "last_summary": row.last_summary,
    }


def should_sync(session: Session, *, min_interval_seconds: Optional[int] = None) -> bool:
    """True when enough time has passed since the last attempt (throttle)."""
    interval = (
        min_interval_seconds
        if min_interval_seconds is not None
        else settings.sync_min_interval_seconds()
    )
    if interval <= 0:
        return True
    row = _state(session)
    if not row.last_attempt_at:
        return True
    try:
        last = datetime.fromisoformat(row.last_attempt_at)
    except ValueError:
        return True
    return (_now() - last).total_seconds() >= interval


def sync_results(
    session: Session,
    *,
    provider: Optional[ResultsProvider] = None,
    competition_ids: Optional[list[str]] = None,
    force: bool = True,
) -> dict:
    """Run one sync. ``force=False`` respects the throttle (used by the
    scheduler); the manual endpoint forces. Never raises for provider errors —
    they are captured in the summary."""
    if not force and not should_sync(session):
        state = get_sync_state(session)
        return {"skipped": "throttled", **state}
    # A provider block applies to every caller, the worker and the admin
    # endpoint alike; it lives in the DB so separate processes share it.
    blocked_until = _rate_limited_until(session)
    if blocked_until is not None and _now() < blocked_until:
        return {"skipped": "rate_limited", "rate_limited_until": blocked_until.isoformat()}

    provider = provider or get_provider()
    comps = competition_ids or settings.tracked_competitions()
    now_iso = _now().isoformat()

    outcome = provider.fetch(comps)
    counts = game_result_repository.upsert_many(session, outcome.games)

    if outcome.errors and not outcome.games:
        status = "error"
    elif outcome.not_checked and not outcome.games:
        status = "rate_limited"
    elif outcome.errors or outcome.not_checked:
        status = "partial"
    else:
        status = "ok"
    rate_limited_until = (
        (_now() + timedelta(seconds=outcome.retry_after_seconds)).isoformat()
        if outcome.retry_after_seconds is not None else None
    )

    summary = {
        "status": status,
        "provider": getattr(provider, "name", "unknown"),
        "competitions": comps,
        "fetched": len(outcome.games),
        "created": counts["created"],
        "updated": counts["updated"],
        "fetched_counts": outcome.fetched_counts,
        "errors": outcome.errors,
        "not_checked": outcome.not_checked,
        "rate_limited_until": rate_limited_until,
        "synced_at": now_iso,
    }

    row = _state(session)
    row.last_attempt_at = now_iso
    row.last_status = status
    row.last_summary = summary
    if status in {"ok", "partial"}:
        row.last_success_at = now_iso
    session.commit()

    logger.info(
        "results sync %s: fetched=%d created=%d updated=%d errors=%s not_checked=%s",
        status, summary["fetched"], counts["created"], counts["updated"],
        list(outcome.errors) or "none", outcome.not_checked or "none",
    )
    return summary
