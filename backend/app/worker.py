"""
The dedicated ingestion scheduler worker (M7-2, #148).

    python -m app.worker

WHY A SEPARATE PROCESS. The previous scheduler (PR 13) lived inside the FastAPI
lifespan, so its lifetime was coupled to request-serving reloads: `uvicorn
--reload` and every additional worker would each have started their own polling
loop. Scheduler lifetime must not be coupled to request serving — so the loop
lives here, the API serves requests, and the two coordinate through the durable
single-flight lease (M7-1). One machine, one worker process, one shared SQLite
file: honest single-node semantics.

The loop is deliberately a plain `while` with an Event-based sleep — no
scheduling library, nothing to configure wrong, SIGINT-responsive. A tick that
fires while another run is active (e.g. a manual run from the API) is recorded
by the orchestration as `skipped_active_run` and simply waits for the next
interval: overlapping ticks are COALESCED, never queued.

STARTUP CATCH-UP. On start, if the last successful cycle is older than one
interval (or none exists), the worker runs ONE `startup_catchup` cycle. Missed
ticks during downtime or machine sleep are never replayed one-by-one — the
next cycle fetches whatever the sources have now, and URL dedup makes that
idempotent.

SHUTDOWN. Ctrl+C / SIGTERM stops the loop after the current step. A cycle
interrupted mid-run leaves a `running` row whose heartbeat goes stale; the
next acquirer (this worker restarted, or a manual run) takes the lease over
and marks that cycle `abandoned` — recovery is the M7-1 contract, not worker
magic.

Tests never start this loop: `SCHEDULER_ENABLED` defaults to false and
`main()` refuses to loop when it is not exactly "true".
"""

from __future__ import annotations

import logging
import os
import pathlib
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("app.worker")


def _load_dotenv() -> None:
    env_file = pathlib.Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:                        # pragma: no cover
        pass


# ── Typed configuration (single source of truth for scheduler cadence) ───────

@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool
    interval_seconds: int          # default 300 — the ~5 minute polling target
    run_on_startup: bool           # force a cycle at startup regardless of staleness
    startup_catchup: bool          # run one cycle at startup IF the last success is stale
    max_run_seconds: int           # a cycle exceeding this is flagged in health (M7-4);
                                   # it is NOT killed — killing mid-transaction is worse
    stale_after_seconds: int       # lease takeover threshold (consumed by orchestration)


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return v if v >= minimum else default
    except ValueError:
        return default


def read_scheduler_config() -> SchedulerConfig:
    return SchedulerConfig(
        enabled=os.getenv("SCHEDULER_ENABLED", "false").strip().lower() == "true",
        interval_seconds=_int_env("SCHEDULER_INTERVAL_SECONDS", 300),
        run_on_startup=os.getenv("SCHEDULER_RUN_ON_STARTUP", "false").strip().lower() == "true",
        startup_catchup=os.getenv("SCHEDULER_STARTUP_CATCHUP", "true").strip().lower() == "true",
        max_run_seconds=_int_env("SCHEDULER_MAX_RUN_SECONDS", 900),
        stale_after_seconds=_int_env("SCHEDULER_STALE_AFTER_SECONDS", 1800),
    )


# ── Worker heartbeat (worker-alive signal, distinct from the run lease) ──────

def beat(session, cfg: SchedulerConfig, state: str) -> None:
    """Record 'this worker process is alive' — including on IDLE ticks, so
    health (M7-4) can distinguish a dead worker from a quiet one."""
    from sqlalchemy import text

    from app.ingestion.orchestration import process_identity
    session.execute(text(
        "INSERT INTO worker_status (id, last_seen_at, state, owner, interval_seconds) "
        "VALUES (1, :now, :state, :owner, :interval) "
        "ON CONFLICT(id) DO UPDATE SET last_seen_at=:now, state=:state, "
        "owner=:owner, interval_seconds=:interval"
    ), {
        "now": datetime.now(tz=timezone.utc).isoformat(),
        "state": state, "owner": process_identity(),
        "interval": cfg.interval_seconds,
    })
    session.commit()


# ── Catch-up decision ─────────────────────────────────────────────────────────

def should_catch_up(session, cfg: SchedulerConfig) -> bool:
    """One catch-up cycle iff the last SUCCESSFUL cycle is older than one
    interval (or none exists). Never a tick-by-tick replay."""
    from sqlalchemy import text
    row = session.execute(text(
        "SELECT finished_at FROM scheduler_cycles "
        "WHERE status IN ('succeeded', 'succeeded_with_warnings') "
        "ORDER BY finished_at DESC LIMIT 1"
    )).fetchone()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0])
    age = datetime.now(tz=timezone.utc) - last
    return age > timedelta(seconds=cfg.interval_seconds)


# ── One tick ─────────────────────────────────────────────────────────────────

def run_tick(cfg: SchedulerConfig, trigger: str) -> "object":
    """Execute one scheduled cycle through the canonical orchestration."""
    from app.ingestion.orchestration import orchestrate_cycle
    outcome = orchestrate_cycle(trigger)
    if outcome.skipped:
        logger.info("tick coalesced — active run %s",
                    (outcome.active_run or {}).get("cycle_id"))
    else:
        dur = ""
        if outcome.started_at and outcome.finished_at:
            secs = (outcome.finished_at - outcome.started_at).total_seconds()
            dur = f" in {secs:.1f}s"
            if secs > cfg.max_run_seconds:
                logger.warning("cycle %s exceeded SCHEDULER_MAX_RUN_SECONDS "
                               "(%.1fs > %ds)", outcome.cycle_id, secs,
                               cfg.max_run_seconds)
        logger.info("cycle %s finished: %s%s", outcome.cycle_id, outcome.status, dur)
    return outcome


# ── The loop ──────────────────────────────────────────────────────────────────

def worker_loop(cfg: SchedulerConfig, stop: threading.Event,
                max_ticks: Optional[int] = None) -> int:
    """The scheduler loop. ``max_ticks`` exists for tests; production is None.

    Returns the number of scheduled ticks executed (skips included).
    """
    from app.db.database import SessionLocal, init_db

    init_db()

    with SessionLocal() as s:
        beat(s, cfg, "starting")

    if cfg.run_on_startup:
        run_tick(cfg, "startup_catchup")
    elif cfg.startup_catchup:
        with SessionLocal() as s:
            needed = should_catch_up(s, cfg)
        if needed:
            logger.info("last successful cycle is stale — running one startup catch-up")
            run_tick(cfg, "startup_catchup")
        else:
            logger.info("last successful cycle is fresh — no startup catch-up needed")

    ticks = 0
    while not stop.is_set():
        # Idle-responsive sleep: wakes immediately on stop; ticks on schedule.
        if stop.wait(timeout=cfg.interval_seconds):
            break
        run_tick(cfg, "scheduled")
        ticks += 1
        with SessionLocal() as s:
            beat(s, cfg, "idle")
        if max_ticks is not None and ticks >= max_ticks:
            break

    with SessionLocal() as s:
        beat(s, cfg, "stopped")
    return ticks


def main() -> int:
    _load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = read_scheduler_config()
    if not cfg.enabled:
        logger.error(
            "SCHEDULER_ENABLED is not 'true' — refusing to start the worker loop. "
            "Set SCHEDULER_ENABLED=true in backend/.env (activation authority: M7-10)."
        )
        return 1

    logger.info("scheduler worker starting: every %ds (catchup=%s, run_on_startup=%s)",
                cfg.interval_seconds, cfg.startup_catchup, cfg.run_on_startup)

    stop = threading.Event()

    def _stop(signum, frame):                  # pragma: no cover - signal path
        logger.info("shutdown signal received — stopping after the current step")
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    worker_loop(cfg, stop)
    logger.info("scheduler worker stopped")
    return 0


if __name__ == "__main__":                     # pragma: no cover - process entry
    raise SystemExit(main())
