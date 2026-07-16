"""
Legacy in-process scheduler shims (PR 13 → retired by M7-2, #148).

The scheduled ingestion LOOP no longer lives here — or anywhere in the API
process. The in-process lifespan scheduler was retired because its lifetime
was coupled to request-serving reloads (`uvicorn --reload` and every extra
worker would each have started their own polling loop). Scheduled ingestion is
the dedicated worker process: ``python -m app.worker`` (see app/worker.py),
coordinating with manual API triggers through the durable single-flight lease
in app/ingestion/orchestration.py (M7-1).

What remains here, deliberately and temporarily:
- ``SchedulerState`` + ``scheduler_state`` — the in-memory mirror behind the
  legacy ``GET /api/ingest/scheduler/status`` endpoint. It reflects THIS API
  process only (a worker-process run is invisible to it); M7-4 replaces the
  endpoint with the durable cycle data and this mirror dies with it.
- ``run_ingestion_guarded`` — a thin shim over the canonical orchestration
  that keeps the mirror coherent.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SchedulerState:
    """In-memory mirror for the LEGACY status endpoint only (see module doc)."""

    enabled: bool = False
    interval_minutes: int = 15
    running: bool = False
    active_run: Optional[dict] = None
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
    """Run ingestion through the canonical orchestration (M7-1, #147).

    Since #147 the guard is the DURABLE database lease in
    ``app.ingestion.orchestration`` — not the process-local lock (which could
    never see a run in another process). This wrapper keeps the in-memory
    ``SchedulerState`` mirror coherent for the legacy status endpoint until
    M7-4 replaces it with the durable cycle data.

    Returns the per-source summary list, or None if another run is active.
    """
    # Imported here (not at module top) so importing scheduler.py never pulls
    # the ingestion stack before .env is loaded.
    from app.ingestion.orchestration import orchestrate_cycle

    outcome = orchestrate_cycle(trigger, source_id=source_id)
    if outcome.skipped:
        if trigger == "scheduled":
            state.last_status = "skipped"
            logger.info("Scheduled ingestion tick skipped — another run is active")
        return None

    state.last_started_at = outcome.started_at
    state.last_finished_at = outcome.finished_at
    summary = _summarize_results(outcome.source_results)
    if outcome.status in ("succeeded", "succeeded_with_warnings"):
        state.last_status = "ok"
        state.last_error = None
        state.last_result_summary = summary
    else:
        state.last_status = "error"
        state.last_error = outcome.error_summary
    return summary


# The asyncio loop machinery (_scheduler_loop / start_scheduler / stop_scheduler)
# and the INGESTION_SCHEDULER_* env vars were REMOVED by M7-2 (#148), not kept as
# dead default-off code: leaving a second loop-starter in the tree is exactly the
# dual-scheduler hazard the retirement exists to prevent. The worker process is
# the only thing that polls.
