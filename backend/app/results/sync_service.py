"""Results synchronization (issue #178).

Fetches the tracked competitions through the configured provider and upserts
them idempotently. Bookkeeping lives in ``results_sync_state`` (one row) which
both throttles the scheduler stage (so opening the page never triggers provider
calls and cycles don't hammer the API) and records the last outcome for ops.
``results_sync_lease`` keeps the worker and a manual sync from overlapping (#197).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.orm_models import ResultsSyncStateRow
from app.repositories import game_result_repository
from app.results import settings
from app.results.providers import ResultsProvider, get_provider
from app.results.providers.base import FetchOutcome

logger = logging.getLogger(__name__)

# The lease has no heartbeat, so this must outlast the longest real sync: about
# 10 requests per competition, 7 s apart by default, plus slow responses. A
# crashed holder therefore blocks syncs for up to this long; syncs are throttled
# and idempotent, so that delay is cheap.
LEASE_STALE_AFTER_SECONDS = 3600


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


def _lease_time(moment: datetime) -> str:
    # One fixed format: the stale check compares these as strings.
    return moment.isoformat(timespec="seconds")


def _try_acquire_lease(session: Session, holder: str) -> bool:
    """One atomic conditional UPDATE, free or stale only; rowcount says who won."""
    session.execute(text(
        "INSERT OR IGNORE INTO results_sync_lease (id, holder, acquired_at) "
        "VALUES (1, NULL, NULL)"
    ))
    now = _now()
    result = session.execute(
        text(
            "UPDATE results_sync_lease SET holder = :holder, acquired_at = :now "
            "WHERE id = 1 AND (holder IS NULL OR acquired_at IS NULL OR acquired_at < :cutoff)"
        ),
        {
            "holder": holder,
            "now": _lease_time(now),
            "cutoff": _lease_time(now - timedelta(seconds=LEASE_STALE_AFTER_SECONDS)),
        },
    )
    session.commit()
    return result.rowcount == 1


def _release_lease(session: Session, holder: str) -> None:
    """Release only OUR lease: a stale takeover must not be clobbered later."""
    session.execute(
        text("UPDATE results_sync_lease SET holder = NULL, acquired_at = NULL "
             "WHERE id = 1 AND holder = :holder"),
        {"holder": holder},
    )
    session.commit()


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
    they are captured in the summary. Returns ``{"skipped": "in_progress"}``
    while another process or session holds the lease."""
    holder = uuid.uuid4().hex
    if not _try_acquire_lease(session, holder):
        return {"skipped": "in_progress"}
    try:
        return _sync_holding_lease(session, provider, competition_ids, force)
    finally:
        # A database failure below leaves the session needing a rollback.
        session.rollback()
        _release_lease(session, holder)


def _sync_holding_lease(
    session: Session,
    provider: Optional[ResultsProvider],
    competition_ids: Optional[list[str]],
    force: bool,
) -> dict:
    if not force and not should_sync(session):
        state = get_sync_state(session)
        return {"skipped": "throttled", **state}
    # A provider block applies to every caller, the worker and the admin
    # endpoint alike; it lives in the DB so separate processes share it.
    blocked_until = _rate_limited_until(session)
    if blocked_until is not None and _now() < blocked_until:
        return {"skipped": "rate_limited", "rate_limited_until": blocked_until.isoformat()}

    comps = competition_ids or settings.tracked_competitions()
    now_iso = _now().isoformat()

    # Recorded before anyone is called, so a crash still leaves a trace.
    _state(session).last_attempt_at = now_iso
    session.commit()

    try:
        provider = provider or get_provider()
        outcome = provider.fetch(comps)
    except Exception as exc:
        # The summary is stored and served, and a message can carry a URL with
        # the API key: it gets the class name, the details go to the log.
        logger.exception("results sync: provider failed unexpectedly")
        outcome = FetchOutcome(errors={"provider": type(exc).__name__})
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
