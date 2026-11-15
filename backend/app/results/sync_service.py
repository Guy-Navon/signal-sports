"""Results synchronization (issue #178).

Fetches the tracked competitions through the configured provider and upserts
them idempotently. Bookkeeping lives in ``results_sync_state`` (one row) which
both throttles the scheduler stage (so opening the page never triggers provider
calls and cycles don't hammer the API) and records the last outcome for ops.
``results_sync_lease`` keeps the worker and a manual sync from overlapping (#197).
With ``RESULTS_DETAIL_ENABLED`` on, the per-game detail stage (``detail_sync``,
#517) runs after the scores are committed, under the same lease. Per-provider
health (#522, ``app.results.health``) is recorded after the scores are committed,
in its own commit, so it can never fail the sync.
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
from app.results import health, settings
from app.results.detail_sync import sync_details
from app.results.providers import ResultsProvider, configured_provider_names, get_provider
from app.results.providers.base import FetchOutcome, ProviderRun

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


def _active_blocks(session: Session) -> dict[str, datetime]:
    """Unexpired provider blocks, name -> until. The key ``"*"`` is a block from a
    summary written before per-provider limits (#529): it covers every provider."""
    summary = _state(session).last_summary
    if not isinstance(summary, dict):
        return {}
    raw: dict = {}
    by_provider = summary.get("rate_limited_until_by_provider")
    if isinstance(by_provider, dict):
        raw.update(by_provider)
    elif summary.get("rate_limited_until"):
        raw["*"] = summary["rate_limited_until"]
    now = _now()
    blocks: dict[str, datetime] = {}
    for name, value in raw.items():
        try:
            until = datetime.fromisoformat(value) if value else None
        except (ValueError, TypeError):
            until = None
        if until is not None and now < until:
            blocks[str(name)] = until
    return blocks


def _blocked_names(blocks: dict[str, datetime], names: list[str]) -> set[str]:
    return set(names) if "*" in blocks else {n for n in names if n in blocks}


def _provider_names(provider: Optional[ResultsProvider]) -> list[str]:
    if provider is None:
        try:
            return configured_provider_names()
        except ValueError:
            # A bad RESULTS_PROVIDER_ROUTES: get_provider() raises the same error
            # below, inside the try, so the sync records it instead of raising.
            return []
    names = getattr(provider, "provider_names", None)
    return list(names) if names else [getattr(provider, "name", "unknown")]


def _limited_providers(outcome: FetchOutcome, plain_name: str, routed: bool) -> dict:
    """Providers that rate-limited this fetch, name -> Retry-After (or None)."""
    if routed:
        return dict(outcome.provider_retry_after)
    if outcome.retry_after_seconds is not None or outcome.not_checked:
        return {plain_name: outcome.retry_after_seconds}
    return {}


def _provider_runs(provider: ResultsProvider, outcome: FetchOutcome, comps: list[str],
                   raised: Optional[str]) -> dict[str, ProviderRun]:
    """Per-provider runs for health. The routing provider reports its own; a
    plain provider was asked for every competition (unless it was blocked, in
    which case the sync was skipped before getting here)."""
    if getattr(provider, "provider_names", None):
        return dict(outcome.provider_runs)
    name = getattr(provider, "name", "unknown")
    if raised is not None:
        return {name: ProviderRun(list(comps), raised=raised)}
    return {name: ProviderRun(list(comps), outcome)}


def _backup_comps(provider: ResultsProvider, comps: list[str]) -> list[str]:
    """Competitions the default provider fetched as backup (#522), in order."""
    default = getattr(provider, "default_name", None)
    provider_for = getattr(provider, "provider_for", None)
    if not default or not callable(provider_for):
        return []
    return [c for c in comps if provider_for(c) != default]


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
    # The block is per provider (#529): the sync is skipped only when every
    # provider it would call is blocked; otherwise the blocked ones are skipped.
    blocks = _active_blocks(session)
    names = _provider_names(provider)
    blocked = _blocked_names(blocks, names)
    if blocked and len(blocked) == len(names):
        until = max(blocks.values())
        return {"skipped": "rate_limited", "rate_limited_until": until.isoformat()}

    comps = competition_ids or settings.tracked_competitions()
    now_iso = _now().isoformat()

    # Recorded before anyone is called, so a crash still leaves a trace.
    _state(session).last_attempt_at = now_iso
    session.commit()

    fetch_raised: Optional[str] = None
    try:
        provider = provider or get_provider()
        set_blocked = getattr(provider, "set_blocked", None)
        if callable(set_blocked):
            set_blocked(blocked)
        outcome = provider.fetch(comps)
    except Exception as exc:
        # The summary is stored and served, and a message can carry a URL with
        # the API key: it gets the class name, the details go to the log.
        logger.exception("results sync: provider failed unexpectedly")
        outcome = FetchOutcome(errors={"provider": type(exc).__name__})
        fetch_raised = type(exc).__name__
    counts = game_result_repository.upsert_many(session, outcome.games)

    # Per-provider health (#522), after the scores are committed. Its own commit:
    # a failure here rolls back only the health rows, never the scores sync.
    health_error: Optional[str] = None
    if provider is not None:
        try:
            health.record_fetch_health(
                session, _provider_runs(provider, outcome, comps, fetch_raised), now_iso)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("results sync: recording provider health failed")
            health_error = type(exc).__name__

    if outcome.errors and not outcome.games:
        status = "error"
    elif outcome.not_checked and not outcome.games:
        status = "rate_limited"
    elif outcome.errors or outcome.not_checked:
        status = "partial"
    else:
        status = "ok"

    # Per-game detail (#517): never changes the scores status above. Skipped
    # while the provider is rate-limiting us, so a 429 stops every request.
    detail_summary: Optional[dict] = None
    routed = bool(getattr(provider, "provider_names", None))
    plain_name = getattr(provider, "name", "unknown")
    limited = _limited_providers(outcome, plain_name, routed)
    new_retry: dict[str, float] = {n: r for n, r in limited.items() if r is not None}
    if settings.detail_enabled() and provider is not None:
        skip = frozenset(limited) | frozenset(blocked)
        if not routed and skip:
            detail_summary = {"status": "skipped_rate_limited"}
        else:
            try:
                stage = sync_details(session, provider, skip)
                detail_summary = stage.summary
                if stage.provider_retry_after is not None:
                    new_retry.update({n: r for n, r in stage.provider_retry_after.items()
                                      if r is not None})
                elif stage.retry_after_seconds is not None:
                    new_retry[plain_name] = stage.retry_after_seconds
            except Exception as exc:
                # Last line of defence: the scores summary below must still be
                # written whatever a provider's detail payload looks like.
                session.rollback()
                logger.exception("results sync: detail stage failed unexpectedly")
                detail_summary = {"status": "error", "errors": {"detail_stage": type(exc).__name__}}

    # Per-provider blocks: keep those still running (a skipped provider was not
    # called, so it earned no new Retry-After), add this run's.
    until_by_provider = {n: u.isoformat() for n, u in blocks.items()
                         if n != "*" and n in names}
    for n, seconds in new_retry.items():
        until_by_provider[n] = (_now() + timedelta(seconds=seconds)).isoformat()
    # The single field stays for ops readers: the latest block of any provider.
    rate_limited_until = max(until_by_provider.values()) if until_by_provider else None

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
        "rate_limited_until_by_provider": until_by_provider,
        "synced_at": now_iso,
    }
    if outcome.backup is not None:
        summary["backup"] = {
            "provider": getattr(provider, "default_name", None) or "unknown",
            "competitions": _backup_comps(provider, comps),
            "fetched_counts": outcome.backup.fetched_counts,
            "errors": outcome.backup.errors,
            "not_checked": outcome.backup.not_checked,
        }
    if detail_summary is not None:
        summary["detail"] = detail_summary
    if health_error is not None:
        summary["health_error"] = health_error

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
