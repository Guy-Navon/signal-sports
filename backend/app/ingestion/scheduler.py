"""
Scheduled ingestion loop + process-level ingestion lock (PR 13).

Design:
- A plain asyncio.Task started in the FastAPI lifespan (no APScheduler).
  The blocking sync ingestion runs in a worker thread via anyio.to_thread so
  the event loop is never blocked.
- Disabled by default (INGESTION_SCHEDULER_ENABLED=false). When disabled,
  start_scheduler() returns None and the app behaves exactly as before PR 13.
- scheduler_state.lock is THE process-level ingestion lock, shared by:
    1. the scheduled loop
    2. POST /api/ingest/run (manual)
    3. POST /api/ingest/scheduler/run-now
  A busy lock produces a structured 409 for the endpoints and a "skipped"
  status for a scheduled tick. No two ingestion runs can overlap in-process.
- Deployment note: the lock and the loop are process-local. In a multi-replica
  deployment only one worker should run the scheduler, or a distributed lock /
  external scheduler is required.

Env vars (read at call time so tests can monkeypatch):
    INGESTION_SCHEDULER_ENABLED=false
    INGESTION_SCHEDULER_INTERVAL_MINUTES=15
    INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS=30
"""

import asyncio
import contextlib
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_MINUTES = 15
_DEFAULT_INITIAL_DELAY_SECONDS = 30


def _read_scheduler_env() -> tuple[bool, int, int]:
    """Read scheduler env vars. Called at start time (not import) for testability."""
    enabled = os.getenv("INGESTION_SCHEDULER_ENABLED", "false").lower() == "true"
    try:
        interval = int(os.getenv("INGESTION_SCHEDULER_INTERVAL_MINUTES",
                                 str(_DEFAULT_INTERVAL_MINUTES)))
    except ValueError:
        interval = _DEFAULT_INTERVAL_MINUTES
    try:
        initial_delay = int(os.getenv("INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS",
                                      str(_DEFAULT_INITIAL_DELAY_SECONDS)))
    except ValueError:
        initial_delay = _DEFAULT_INITIAL_DELAY_SECONDS
    if interval < 1:
        interval = _DEFAULT_INTERVAL_MINUTES
    if initial_delay < 0:
        initial_delay = _DEFAULT_INITIAL_DELAY_SECONDS
    return enabled, interval, initial_delay


@dataclass
class SchedulerState:
    """Mutable scheduler + ingestion-lock state (module singleton)."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    enabled: bool = False
    interval_minutes: int = _DEFAULT_INTERVAL_MINUTES
    running: bool = False                       # scheduler loop alive
    active_run: Optional[dict] = None           # {"trigger": ..., "started_at": iso}
    next_run_at: Optional[datetime] = None
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    last_status: str = "never_run"              # ok | error | skipped | never_run
    last_error: Optional[str] = None
    last_result_summary: Optional[list[dict[str, Any]]] = None


scheduler_state = SchedulerState()


def _summarize_results(results) -> list[dict[str, Any]]:
    return [
        {
            "source_id": r.source_id,
            "fetched": r.fetched,
            "inserted": r.inserted,
            "skipped_duplicate": r.skipped_duplicate,
            "skipped_filtered": r.skipped_filtered,
            "failed": r.failed,
        }
        for r in results
    ]


def run_ingestion_guarded(
    state: SchedulerState,
    trigger: str,
    source_id: Optional[str] = None,
) -> Optional[list[dict[str, Any]]]:
    """Run ingestion under the process-level lock.

    Returns the per-source summary list, or None if another run is active
    (lock busy). Sync by design — callable from endpoints and from the
    scheduler loop's worker thread alike. The lock is always released.
    """
    if not state.lock.acquire(blocking=False):
        if trigger == "scheduled":
            state.last_status = "skipped"
            logger.info("Scheduled ingestion tick skipped — another run is active")
        return None

    # Imported here (not at module top) so importing scheduler.py never pulls
    # the LLM provider/ingestion stack before .env is loaded.
    from app.db.database import SessionLocal
    from app.ingestion.ingestion_service import run_ingestion

    started = datetime.now(tz=timezone.utc)
    state.active_run = {"trigger": trigger, "started_at": started.isoformat()}
    state.last_started_at = started
    try:
        with SessionLocal() as session:
            results = run_ingestion(session, source_id=source_id)
        summary = _summarize_results(results)
        state.last_status = "ok"
        state.last_error = None
        state.last_result_summary = summary
        return summary
    except Exception as exc:
        logger.exception("Ingestion run (%s) failed", trigger)
        state.last_status = "error"
        state.last_error = str(exc)
        return []
    finally:
        state.last_finished_at = datetime.now(tz=timezone.utc)
        state.active_run = None
        state.lock.release()


async def _scheduler_loop(state: SchedulerState, interval_minutes: int,
                          initial_delay_seconds: int) -> None:
    import anyio

    state.next_run_at = datetime.now(tz=timezone.utc) + timedelta(
        seconds=initial_delay_seconds
    )
    await asyncio.sleep(initial_delay_seconds)
    while True:
        state.next_run_at = datetime.now(tz=timezone.utc) + timedelta(
            minutes=interval_minutes
        )
        await anyio.to_thread.run_sync(run_ingestion_guarded, state, "scheduled")
        await asyncio.sleep(interval_minutes * 60)


def start_scheduler(state: SchedulerState) -> Optional[asyncio.Task]:
    """Start the scheduled ingestion loop if enabled. Returns None when disabled."""
    enabled, interval, initial_delay = _read_scheduler_env()
    state.enabled = enabled
    state.interval_minutes = interval
    if not enabled:
        state.running = False
        return None

    state.running = True
    logger.info(
        "Ingestion scheduler enabled: every %d min (initial delay %ds)",
        interval, initial_delay,
    )
    # Called from the FastAPI lifespan, where an event loop is running.
    return asyncio.create_task(_scheduler_loop(state, interval, initial_delay))


async def stop_scheduler(state: SchedulerState, task: Optional[asyncio.Task]) -> None:
    """Cancel the scheduler task on app shutdown. Safe to call with None."""
    state.running = False
    state.next_run_at = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
