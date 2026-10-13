"""
Outbound health pings for an external monitor (healthchecks.io-style), #13 of
docs/HOSTING_PLAN.md and docs/DEPLOYMENT.md "Monitoring".

Four independent signals, each its own check URL (all optional):

  MONITOR_CYCLE_URL    a scheduled cycle COMPLETED (succeeded, or succeeded with
                       warnings); ``<url>/fail`` when it ended ``failed``.
                       Silence = dead worker, down host or a stuck cycle.
  MONITOR_SOURCES_URL  at least one source returned items this cycle, new or
                       not (feeds always list their latest items, so a quiet
                       night still pings); ``/fail`` when no source returned
                       anything.
  MONITOR_FRESH_URL    at least one NEW article was stored. Never ``/fail``:
                       quiet periods are natural, the monitor's long grace
                       decides when silence is a problem.
  MONITOR_BACKUP_URL   used by the backup job, only after an off-host upload
                       succeeded (deploy/backup.sh).

Rules:
- Unset URL = that signal is off. Nothing is configured by default.
- A ping never raises and never fails a cycle: one short POST
  (MONITOR_TIMEOUT_SECONDS, default 5, at most 10) and every error is logged
  by check NAME only — the URL is a credential and is never logged.
- The body is a short summary of counts and source ids; never article text,
  never settings, never secrets.
- DEPLOY_ENV=dev never pings (a dev copy must not feed production's monitor);
  the dev startup check also refuses MONITOR_* URLs.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

CHECK_ENV = {
    "cycle": "MONITOR_CYCLE_URL",
    "sources": "MONITOR_SOURCES_URL",
    "fresh": "MONITOR_FRESH_URL",
    "backup": "MONITOR_BACKUP_URL",
}

_COMPLETED = ("succeeded", "succeeded_with_warnings")


def _timeout() -> float:
    try:
        value = float(os.environ.get("MONITOR_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5.0
    return min(max(value, 0.5), 10.0)


def check_url(check: str) -> Optional[str]:
    url = os.environ.get(CHECK_ENV[check], "").strip()
    return url or None


def ping(check: str, *, fail: bool = False, body: str = "") -> bool:
    """POST one ping. Returns True only on a 2xx answer. Never raises."""
    try:
        from app.core.deploy_mode import deploy_env

        if deploy_env() == "dev":
            return False
        url = check_url(check)
        if url is None:
            return False
        import httpx

        target = url.rstrip("/") + ("/fail" if fail else "")
        response = httpx.post(target, content=body.encode("utf-8")[:10_000], timeout=_timeout())
        if 200 <= response.status_code < 300:
            return True
        logger.warning("monitor ping %s%s answered HTTP %s", check, " (fail)" if fail else "",
                       response.status_code)
        return False
    except Exception as exc:  # noqa: BLE001 - monitoring must never break a cycle
        logger.warning("monitor ping %s failed: %s", check, type(exc).__name__)
        return False


def _source_lines(source_results: Iterable) -> list[str]:
    lines = []
    for r in source_results:
        lines.append(
            f"{getattr(r, 'source_id', '?')}: fetched={getattr(r, 'fetched', 0)} "
            f"inserted={getattr(r, 'inserted', 0)} errors={len(getattr(r, 'errors', None) or [])}"
        )
    return lines


def report_cycle(outcome) -> dict[str, Optional[bool]]:
    """Send the cycle, sources and freshness signals for one finished cycle.

    ``outcome`` is the orchestration CycleResult. A coalesced (skipped) tick
    sends nothing: another run held the lease, and the next tick reports.
    Returns what was sent per check (None = not sent), for tests and logs.
    """
    sent: dict[str, Optional[bool]] = {"cycle": None, "sources": None, "fresh": None}
    if getattr(outcome, "skipped", False):
        return sent
    status = getattr(outcome, "status", None)
    results = list(getattr(outcome, "source_results", None) or [])
    summary_lines = [f"cycle {getattr(outcome, 'cycle_id', '?')} {status}"] + _source_lines(results)
    summary = "\n".join(summary_lines)

    if check_url("cycle"):
        if status in _COMPLETED:
            sent["cycle"] = ping("cycle", body=summary)
        elif status == "failed":
            error = (getattr(outcome, "error_summary", None) or "")[:200]
            sent["cycle"] = ping("cycle", fail=True, body=summary + ("\n" + error if error else ""))

    if check_url("sources") and status in _COMPLETED + ("failed",):
        any_items = any((getattr(r, "fetched", 0) or 0) > 0 for r in results)
        sent["sources"] = ping("sources", fail=not any_items, body=summary)

    if check_url("fresh"):
        if any((getattr(r, "inserted", 0) or 0) > 0 for r in results):
            sent["fresh"] = ping("fresh", body=summary)
    return sent
