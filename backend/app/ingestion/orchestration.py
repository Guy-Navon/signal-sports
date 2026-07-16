"""
Canonical ingestion-cycle orchestration + durable single-flight guard (M7-1, #147).

EVERY trigger runs through ``orchestrate_cycle`` — the scheduled worker tick,
``POST /api/ingest/run``, ``POST /api/ingest/scheduler/run-now`` and the worker's
startup catch-up. A scheduler tick is not a second implementation of ingestion:
this module owns the guard, the durable cycle record and the stage ordering, and
delegates the actual pipeline to the same ``run_ingestion()`` every path has
always used.

THE GUARD — honest single-node semantics
----------------------------------------
The previous guard was a process-local ``threading.Lock`` (PR 13). It was
correct within one process and INVISIBLE across processes — the M7 topology
(one API process + one worker process) makes that insufficient. The guard here
is one durable row (``scheduler_lease``) updated with a single conditional
UPDATE. SQLite serializes writers on the database file, so exactly one process
can win that UPDATE. That is the entire guarantee: at most one corpus-mutating
cycle at a time ON THIS MACHINE, across processes sharing this database file.
It is not a distributed lock and is never described as one.

Dead-process recovery: the holder refreshes ``heartbeat_at`` while it runs. An
acquirer that finds the lease held but the heartbeat older than
``SCHEDULER_STALE_AFTER_SECONDS`` takes the lease over and marks the previous
cycle ``abandoned`` — a crash can therefore never wedge ingestion forever,
and a live run can never be stolen (its heartbeat is fresh).

STAGE ORDERING (later issues fill the placeholders; the order is contract):
    acquire → cycle row → run_ingestion (fetch/classify/insert/anchor/cluster,
    per source, source-isolated) → notification planning (M7-6) → notification
    dispatch (M7-7, never inside the ingestion transaction) → retention cleanup
    (M7-3, AFTER planning so the planner always sees the full window) →
    finalize cycle → release.
Failures in planning/dispatch/cleanup degrade the cycle to
``succeeded_with_warnings`` — they never invalidate successful ingestion.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Trigger vocabulary ─────────────────────────────────────────────────────────
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_STARTUP_CATCHUP = "startup_catchup"
TRIGGER_MANUAL = "manual"
TRIGGER_RUN_NOW = "run_now"

# ── Cycle statuses ─────────────────────────────────────────────────────────────
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_WARNINGS = "succeeded_with_warnings"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped_active_run"
STATUS_ABANDONED = "abandoned"

_DEFAULT_STALE_AFTER_SECONDS = 1800  # 30 min ≫ any observed cycle duration
_HEARTBEAT_EVERY_SECONDS = 10


def stale_after_seconds() -> int:
    try:
        v = int(os.getenv("SCHEDULER_STALE_AFTER_SECONDS",
                          str(_DEFAULT_STALE_AFTER_SECONDS)))
        return v if v > 0 else _DEFAULT_STALE_AFTER_SECONDS
    except ValueError:
        return _DEFAULT_STALE_AFTER_SECONDS


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def process_identity() -> str:
    return f"pid={os.getpid()} host={socket.gethostname()}"


@dataclass
class CycleResult:
    """What a trigger got back: either a completed cycle or a recorded skip."""

    cycle_id: str
    status: str
    skipped: bool = False
    active_run: Optional[dict] = None          # who held the lease, when skipped
    source_results: list = field(default_factory=list)   # SourceIngestResult list
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ── Lease primitives ──────────────────────────────────────────────────────────

def _ensure_lease_row(session) -> None:
    session.execute(text(
        "INSERT OR IGNORE INTO scheduler_lease (id, active_cycle_id, heartbeat_at, owner) "
        "VALUES (1, NULL, NULL, NULL)"
    ))
    session.commit()


def _try_acquire_lease(session, cycle_id: str) -> tuple[bool, Optional[str]]:
    """One atomic conditional UPDATE. Returns (acquired, abandoned_cycle_id).

    Succeeds when the lease is free OR the current holder's heartbeat is stale
    (dead-process takeover). SQLite's writer serialization makes the UPDATE
    atomic across processes; rowcount tells us who won.
    """
    _ensure_lease_row(session)
    cutoff = _iso(_now() - timedelta(seconds=stale_after_seconds()))

    holder = session.execute(text(
        "SELECT active_cycle_id, heartbeat_at FROM scheduler_lease WHERE id = 1"
    )).fetchone()
    previous_cycle = holder[0] if holder else None

    result = session.execute(
        text(
            "UPDATE scheduler_lease SET active_cycle_id = :cid, heartbeat_at = :hb, "
            "owner = :owner WHERE id = 1 AND (active_cycle_id IS NULL "
            "OR heartbeat_at IS NULL OR heartbeat_at < :cutoff)"
        ),
        {"cid": cycle_id, "hb": _iso(_now()), "owner": process_identity(),
         "cutoff": cutoff},
    )
    session.commit()
    if result.rowcount != 1:
        return False, None
    # We acquired. If somebody held it before us, their heartbeat was stale —
    # their cycle is abandoned (the process died without releasing).
    abandoned = previous_cycle if previous_cycle and previous_cycle != cycle_id else None
    return True, abandoned


def _heartbeat(session, cycle_id: str) -> None:
    session.execute(
        text("UPDATE scheduler_lease SET heartbeat_at = :hb "
             "WHERE id = 1 AND active_cycle_id = :cid"),
        {"hb": _iso(_now()), "cid": cycle_id},
    )
    session.commit()


def _release_lease(session, cycle_id: str) -> None:
    """Release only OUR lease — a stale takeover must not be clobbered later."""
    session.execute(
        text("UPDATE scheduler_lease SET active_cycle_id = NULL, heartbeat_at = NULL, "
             "owner = NULL WHERE id = 1 AND active_cycle_id = :cid"),
        {"cid": cycle_id},
    )
    session.commit()


def current_lease(session) -> Optional[dict]:
    row = session.execute(text(
        "SELECT active_cycle_id, heartbeat_at, owner FROM scheduler_lease WHERE id = 1"
    )).fetchone()
    if not row or not row[0]:
        return None
    return {"cycle_id": row[0], "heartbeat_at": row[1], "owner": row[2]}


def _max_run_seconds() -> int:
    try:
        v = int(os.getenv("SCHEDULER_MAX_RUN_SECONDS", "900"))
        return v if v > 0 else 900
    except ValueError:
        return 900


def worker_liveness(session) -> dict:
    """Is the DEDICATED WORKER process alive and ticking?

    Derived purely from the durable ``worker_status`` heartbeat the worker
    writes on every tick (including idle ticks) — NOT from any process's
    ``SCHEDULER_ENABLED`` env. In the two-process topology (API + worker) the
    API's own env flag says nothing about whether the worker is running, so
    this durable signal is the authoritative "automatic ingestion is actually
    happening" answer that every status surface must use instead of the
    serving process's config intent.

    ``running`` is true only when the worker claims an active loop state
    (``starting``/``idle``, never ``stopped``) AND its last heartbeat is within
    one interval + one max-run allowance — a crashed worker leaves a stale
    ``idle`` row, which must read as NOT running.
    """
    row = session.execute(text(
        "SELECT state, last_seen_at, interval_seconds FROM worker_status WHERE id = 1"
    )).fetchone()
    if not row:
        return {"present": False, "running": False, "state": None,
                "last_seen_at": None, "heartbeat_age_seconds": None,
                "interval_seconds": None, "allowance_seconds": None}
    state, last_seen, interval = row[0], row[1], row[2]
    age = None
    if last_seen:
        try:
            age = (_now() - datetime.fromisoformat(last_seen)).total_seconds()
        except ValueError:
            age = None
    interval = interval or 300
    allowance = interval + _max_run_seconds()
    running = (state in ("starting", "idle")
               and age is not None and age <= allowance)
    return {"present": True, "running": running, "state": state,
            "last_seen_at": last_seen, "heartbeat_age_seconds": age,
            "interval_seconds": interval, "allowance_seconds": allowance}


# ── Heartbeat thread ──────────────────────────────────────────────────────────

class _HeartbeatThread(threading.Thread):
    """Refreshes the lease heartbeat while a cycle runs, on its OWN session —
    the run's session is busy in the pipeline and must not be shared across
    threads. Daemon so a crashed run can never be kept alive by its own pulse."""

    def __init__(self, cycle_id: str):
        super().__init__(daemon=True, name=f"heartbeat-{cycle_id[:14]}")
        self.cycle_id = cycle_id
        self._stop = threading.Event()

    def run(self) -> None:
        from app.db.database import SessionLocal
        while not self._stop.wait(_HEARTBEAT_EVERY_SECONDS):
            try:
                with SessionLocal() as s:
                    _heartbeat(s, self.cycle_id)
            except Exception:                      # pragma: no cover - defensive
                logger.warning("heartbeat refresh failed", exc_info=True)

    def stop(self) -> None:
        self._stop.set()


# ── Cycle records ─────────────────────────────────────────────────────────────

def _config_snapshot() -> dict:
    return {
        "clustering_enabled": os.getenv("CLUSTERING_ENABLED", "false"),
        "scheduler_interval_seconds": os.getenv("SCHEDULER_INTERVAL_SECONDS"),
        "stale_after_seconds": stale_after_seconds(),
    }


def _insert_cycle(session, cycle_id: str, trigger: str, requested_at: datetime,
                  status: str, started_at: Optional[datetime] = None) -> None:
    from app.db.orm_models import SchedulerCycleRow
    session.add(SchedulerCycleRow(
        id=cycle_id, trigger=trigger, requested_at=_iso(requested_at),
        started_at=_iso(started_at), status=status,
        process_identity=process_identity(), config_snapshot=_config_snapshot(),
    ))
    session.commit()


def _summarize(results) -> list[dict[str, Any]]:
    return [
        {
            "source_id": r.source_id,
            "fetched": r.fetched,
            "inserted": r.inserted,
            "skipped_duplicate": r.skipped_duplicate,
            "skipped_filtered": r.skipped_filtered,
            "failed": r.failed,
            "errors": [e[:300] for e in (r.errors or [])[:3]],
        }
        for r in results
    ]


def _mark_abandoned(session, cycle_id: str) -> None:
    from app.db.orm_models import SchedulerCycleRow
    row = session.get(SchedulerCycleRow, cycle_id)
    if row is not None and row.status == STATUS_RUNNING:
        row.status = STATUS_ABANDONED
        row.finished_at = _iso(_now())
        row.error_summary = ("abandoned: holder process died without releasing "
                             "the lease (stale heartbeat takeover)")
        session.commit()


# ── The orchestration ─────────────────────────────────────────────────────────

def orchestrate_cycle(trigger: str, source_id: Optional[str] = None) -> CycleResult:
    """Run one full ingestion cycle under the durable single-flight guard.

    Owns its sessions (callable from any process/thread — endpoints, the worker
    loop, tests). Always leaves a durable cycle row explaining what happened,
    including for triggers that were skipped because another run was active.
    """
    from app.db.database import SessionLocal
    from app.ingestion.ingestion_service import run_ingestion

    requested_at = _now()
    cycle_id = f"cycle_{uuid.uuid4().hex[:20]}"

    with SessionLocal() as session:
        acquired, abandoned_cycle = _try_acquire_lease(session, cycle_id)
        if not acquired:
            active = current_lease(session)
            _insert_cycle(session, cycle_id, trigger, requested_at, STATUS_SKIPPED)
            logger.info("Cycle %s (%s) skipped — active run %s",
                        cycle_id, trigger, active and active.get("cycle_id"))
            return CycleResult(cycle_id=cycle_id, status=STATUS_SKIPPED,
                               skipped=True, active_run=active)
        if abandoned_cycle:
            _mark_abandoned(session, abandoned_cycle)

    started_at = _now()
    heartbeat = _HeartbeatThread(cycle_id)
    heartbeat.start()

    status = STATUS_FAILED
    error_summary: Optional[str] = None
    results: list = []
    notification_summary: Optional[dict] = None
    cleanup_summary: Optional[dict] = None
    stage_warnings: list[str] = []
    try:
        with SessionLocal() as session:
            _insert_cycle(session, cycle_id, trigger, requested_at,
                          STATUS_RUNNING, started_at=started_at)

        with SessionLocal() as session:
            results = run_ingestion(session, source_id=source_id)
            # Link the per-source child rows created by this cycle.
            session.execute(
                text("UPDATE ingestion_runs SET cycle_id = :cid "
                     "WHERE cycle_id IS NULL AND started_at >= :t0"),
                {"cid": cycle_id, "t0": _iso(started_at)},
            )
            session.commit()

        # ── Notification planning (M7-6, #152) ────────────────────────────────
        # AFTER clustering (must see today's components), BEFORE cleanup (M7-3;
        # planning must observe the full window before anything is deleted).
        # A planner failure degrades the cycle — it never rolls back ingestion.
        planning_summary: Optional[dict] = None
        dispatch_summary: Optional[dict] = None
        try:
            from app.notifications.planner import plan_cycle_notifications
            with SessionLocal() as session:
                planning_summary = plan_cycle_notifications(session)
        except Exception as exc:
            planning_summary = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            stage_warnings.append(f"notification planning failed: {exc}")
            logger.exception("Cycle %s: notification planning failed", cycle_id)

        # ── Notification dispatch (M7-7, #153) ────────────────────────────────
        # Delivery NEVER participates in the ingestion transaction: its own
        # sessions, its own failure class. A Telegram outage degrades the cycle
        # at most to succeeded_with_warnings and never blocks ingestion.
        try:
            from app.notifications.dispatcher import dispatch_pending
            with SessionLocal() as session:
                dispatch_summary = dispatch_pending(session)
            if dispatch_summary.get("unknown") or dispatch_summary.get("failed_final"):
                stage_warnings.append(
                    f"notification delivery degraded: {dispatch_summary}")
        except Exception as exc:
            dispatch_summary = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            stage_warnings.append(f"notification dispatch failed: {exc}")
            logger.exception("Cycle %s: notification dispatch failed", cycle_id)

        notification_summary = {"planning": planning_summary,
                                "dispatch": dispatch_summary}

        # ── Retention cleanup (M7-3, #149) — LAST, after planning saw the full
        # window. Guarded by RETENTION_CLEANUP_ENABLED; a cleanup failure
        # degrades the cycle, never invalidating successful ingestion.
        try:
            from app.ingestion.retention import cleanup_articles, cleanup_enabled
            if cleanup_enabled():
                with SessionLocal() as session:
                    cleanup_summary = cleanup_articles(session)
            else:
                cleanup_summary = {"skipped": "disabled"}
        except Exception as exc:
            cleanup_summary = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            stage_warnings.append(f"retention cleanup failed: {exc}")
            logger.exception("Cycle %s: retention cleanup failed", cycle_id)

        any_errors = any(r.errors for r in results)
        any_inserted = any(r.inserted for r in results)
        if any_errors and not any_inserted and all(r.fetched == 0 for r in results):
            status = STATUS_FAILED
            error_summary = next(
                (e[:300] for r in results for e in r.errors), None)
        elif any_errors or stage_warnings:
            status = STATUS_WARNINGS
            error_summary = next(
                (e[:300] for r in results for e in r.errors),
                stage_warnings[0][:300] if stage_warnings else None)
        else:
            status = STATUS_SUCCEEDED
    except Exception as exc:
        status = STATUS_FAILED
        error_summary = f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.exception("Cycle %s (%s) failed", cycle_id, trigger)
    finally:
        heartbeat.stop()
        finished_at = _now()
        try:
            with SessionLocal() as session:
                from app.db.orm_models import SchedulerCycleRow
                row = session.get(SchedulerCycleRow, cycle_id)
                if row is not None:
                    row.status = status
                    row.finished_at = _iso(finished_at)
                    row.error_summary = error_summary
                    row.source_results = _summarize(results)
                    row.notification_summary = notification_summary
                    row.cleanup_summary = cleanup_summary
                    session.commit()
        except Exception:                          # pragma: no cover - defensive
            logger.exception("Cycle %s: failed to finalize the cycle row", cycle_id)
        try:
            with SessionLocal() as session:
                _release_lease(session, cycle_id)
        except Exception:                          # pragma: no cover - defensive
            logger.exception("Cycle %s: failed to release the lease", cycle_id)

    return CycleResult(
        cycle_id=cycle_id, status=status, source_results=results,
        error_summary=error_summary, started_at=started_at, finished_at=finished_at,
    )
