"""
Durable scheduler + notification observability (M7-4 #150, M7-8 #154).

Everything here reads the DURABLE state (scheduler_cycles, scheduler_lease,
worker_status, notification_events) — never process memory, so the API
process can explain what the WORKER process did, across restarts.

Health separation is contract: a Telegram outage degrades
``notifications`` — it never marks the scheduler or ingestion dead.
No secret (bot token, chat id) ever appears in any response.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security_deps import require_admin
from app.db.database import get_session
from app.ingestion.orchestration import current_lease, stale_after_seconds

router = APIRouter()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _age_seconds(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        return (_now() - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return None


def _scheduler_config() -> dict:
    from app.worker import read_scheduler_config
    cfg = read_scheduler_config()
    return {
        "enabled": cfg.enabled,
        "interval_seconds": cfg.interval_seconds,
        "max_run_seconds": cfg.max_run_seconds,
        "stale_after_seconds": stale_after_seconds(),
    }


# ── Scheduler health ──────────────────────────────────────────────────────────

class SchedulerHealthResponse(BaseModel):
    scheduler_enabled: bool
    interval_seconds: int
    worker_state: Optional[str] = None           # starting | idle | stopped | None
    worker_last_seen_at: Optional[str] = None
    worker_heartbeat_age_seconds: Optional[float] = None
    currently_running: bool
    active_cycle_id: Optional[str] = None
    last_attempted_cycle: Optional[dict] = None   # id, trigger, status, finished_at
    last_successful_cycle: Optional[dict] = None
    age_of_last_success_seconds: Optional[float] = None
    next_expected_run_at: Optional[str] = None
    consecutive_failures: int
    stale: bool
    stale_reason: Optional[str] = None
    last_source_failures: List[dict] = []
    notifications: dict = {}                      # the M7-8 summary block
    ingestion_degraded: bool
    notifications_degraded: bool


def _cycle_brief(row) -> Optional[dict]:
    if row is None:
        return None
    return {"id": row[0], "trigger": row[1], "status": row[2],
            "finished_at": row[3]}


def _notification_block(session: Session) -> dict:
    """The M7-8 summary — embedded in scheduler health but a separate axis."""
    import os

    counts = dict(session.execute(text(
        "SELECT status, COUNT(*) FROM notification_events GROUP BY status"
    )).fetchall())
    oldest_pending = session.execute(text(
        "SELECT MIN(created_at) FROM notification_events WHERE status = 'pending'"
    )).fetchone()[0]
    last_sent = session.execute(text(
        "SELECT MAX(final_at) FROM notification_events WHERE status = 'sent'"
    )).fetchone()[0]
    # Consecutive delivery failures: walk recent attempts backwards.
    recent = session.execute(text(
        "SELECT status FROM notification_events WHERE last_attempt_at IS NOT NULL "
        "ORDER BY last_attempt_at DESC LIMIT 20"
    )).fetchall()
    consecutive_failures = 0
    for (status,) in recent:
        if status in ("failed_retryable", "failed_final", "unknown"):
            consecutive_failures += 1
        else:
            break

    return {
        "enabled": os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false").lower() == "true",
        "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
                           and os.getenv("TELEGRAM_CHAT_ID", "").strip()),
        "pending": counts.get("pending", 0),
        "oldest_pending_age_seconds": _age_seconds(oldest_pending),
        "sent": counts.get("sent", 0),
        "failed_final": counts.get("failed_final", 0),
        "failed_retryable": counts.get("failed_retryable", 0),
        "unknown": counts.get("unknown", 0),
        "claimed_in_flight": counts.get("claimed", 0),
        "suppressed_watermark": counts.get("suppressed_watermark", 0),
        "last_confirmed_delivery_at": last_sent,
        "consecutive_delivery_failures": consecutive_failures,
    }


@router.get("/scheduler/health", response_model=SchedulerHealthResponse,
            dependencies=[Depends(require_admin)])
def scheduler_health(session: Session = Depends(get_session)):
    cfg = _scheduler_config()

    worker = session.execute(text(
        "SELECT state, last_seen_at FROM worker_status WHERE id = 1"
    )).fetchone()
    worker_state = worker[0] if worker else None
    worker_seen = worker[1] if worker else None
    heartbeat_age = _age_seconds(worker_seen)

    lease = current_lease(session)

    last_attempted = session.execute(text(
        "SELECT id, trigger, status, finished_at FROM scheduler_cycles "
        "WHERE status != 'skipped_active_run' ORDER BY requested_at DESC LIMIT 1"
    )).fetchone()
    last_success = session.execute(text(
        "SELECT id, trigger, status, finished_at FROM scheduler_cycles "
        "WHERE status IN ('succeeded','succeeded_with_warnings') "
        "ORDER BY finished_at DESC LIMIT 1"
    )).fetchone()
    success_age = _age_seconds(last_success[3]) if last_success else None

    # Consecutive failures: walk real (non-skip) cycles backwards.
    recent = session.execute(text(
        "SELECT status FROM scheduler_cycles WHERE status NOT IN "
        "('skipped_active_run','running') ORDER BY requested_at DESC LIMIT 20"
    )).fetchall()
    consecutive_failures = 0
    for (status,) in recent:
        if status in ("failed", "abandoned"):
            consecutive_failures += 1
        else:
            break

    # Stale: defined relative to cadence + max run duration, never a magic
    # constant. The scheduler is stale when it is ENABLED and either the worker
    # heartbeat or the last success is older than one interval + one max run.
    allowance = cfg["interval_seconds"] + cfg["max_run_seconds"]
    stale = False
    stale_reason = None
    if cfg["enabled"]:
        if heartbeat_age is None:
            stale, stale_reason = True, "worker has never reported a heartbeat"
        elif heartbeat_age > allowance:
            stale, stale_reason = True, (
                f"worker heartbeat is {heartbeat_age:.0f}s old "
                f"(> interval+max_run = {allowance}s)")
        elif success_age is not None and success_age > 3 * allowance:
            stale, stale_reason = True, (
                f"last successful cycle is {success_age:.0f}s old")

    next_expected = None
    if cfg["enabled"] and worker_seen and worker_state not in (None, "stopped"):
        next_expected = (datetime.fromisoformat(worker_seen)
                         + timedelta(seconds=cfg["interval_seconds"])).isoformat()

    failures = []
    if last_attempted:
        srcs = session.execute(text(
            "SELECT source_results FROM scheduler_cycles WHERE id = :i"
        ), {"i": last_attempted[0]}).fetchone()
        if srcs and srcs[0]:
            import json
            parsed = json.loads(srcs[0]) if isinstance(srcs[0], str) else srcs[0]
            failures = [s for s in (parsed or [])
                        if s.get("failed") or s.get("errors")]

    notifications = _notification_block(session)

    return SchedulerHealthResponse(
        scheduler_enabled=cfg["enabled"],
        interval_seconds=cfg["interval_seconds"],
        worker_state=worker_state,
        worker_last_seen_at=worker_seen,
        worker_heartbeat_age_seconds=heartbeat_age,
        currently_running=lease is not None,
        active_cycle_id=lease["cycle_id"] if lease else None,
        last_attempted_cycle=_cycle_brief(last_attempted),
        last_successful_cycle=_cycle_brief(last_success),
        age_of_last_success_seconds=success_age,
        next_expected_run_at=next_expected,
        consecutive_failures=consecutive_failures,
        stale=stale,
        stale_reason=stale_reason,
        last_source_failures=failures,
        notifications=notifications,
        ingestion_degraded=consecutive_failures > 0 or stale,
        notifications_degraded=(
            notifications["enabled"] and (
                notifications["consecutive_delivery_failures"] > 0
                or notifications["unknown"] > 0
                or (notifications["oldest_pending_age_seconds"] or 0) > allowance
            )
        ),
    )


# ── Cycle history ─────────────────────────────────────────────────────────────

class CycleRecord(BaseModel):
    id: str
    trigger: str
    requested_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str
    error_summary: Optional[str] = None
    source_results: Optional[Any] = None
    notification_summary: Optional[Any] = None
    cleanup_summary: Optional[Any] = None
    process_identity: Optional[str] = None


@router.get("/scheduler/cycles", response_model=List[CycleRecord],
            dependencies=[Depends(require_admin)])
def scheduler_cycles(
    limit: int = Query(default=25, ge=1, le=200),
    session: Session = Depends(get_session),
):
    from app.db.orm_models import SchedulerCycleRow
    rows = (session.query(SchedulerCycleRow)
            .order_by(SchedulerCycleRow.requested_at.desc())
            .limit(limit).all())
    return [CycleRecord(
        id=r.id, trigger=r.trigger, requested_at=r.requested_at,
        started_at=r.started_at, finished_at=r.finished_at, status=r.status,
        error_summary=r.error_summary, source_results=r.source_results,
        notification_summary=r.notification_summary,
        cleanup_summary=r.cleanup_summary, process_identity=r.process_identity,
    ) for r in rows]


# ── Notification observability (M7-8) ─────────────────────────────────────────

@router.get("/notifications/health", dependencies=[Depends(require_admin)])
def notifications_health(session: Session = Depends(get_session)):
    return _notification_block(session)


class NotificationEventRecord(BaseModel):
    id: str
    profile_id: str
    policy_version: str
    status: str
    created_at: str
    canonical_headline: str
    source: str
    url: str
    tier: str
    attempt_count: int
    last_attempt_at: Optional[str] = None
    claimed_at: Optional[str] = None
    provider_message_id: Optional[str] = None
    last_error_class: Optional[str] = None
    cluster_id_at_creation: Optional[str] = None


@router.get("/notifications/events", response_model=List[NotificationEventRecord],
            dependencies=[Depends(require_admin)])
def notification_events(
    limit: int = Query(default=25, ge=1, le=200),
    session: Session = Depends(get_session),
):
    from app.db.orm_models import NotificationEventRow
    rows = (session.query(NotificationEventRow)
            .order_by(NotificationEventRow.created_at.desc())
            .limit(limit).all())
    return [NotificationEventRecord(
        id=r.id, profile_id=r.profile_id, policy_version=r.policy_version,
        status=r.status, created_at=r.created_at,
        canonical_headline=r.canonical_headline, source=r.source, url=r.url,
        tier=r.tier, attempt_count=r.attempt_count,
        last_attempt_at=r.last_attempt_at, claimed_at=r.claimed_at,
        provider_message_id=r.provider_message_id,
        last_error_class=r.last_error_class,
        cluster_id_at_creation=r.cluster_id_at_creation,
    ) for r in rows]
