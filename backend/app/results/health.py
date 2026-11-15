"""Results provider health and the read-time serving decision (issue #522).

Every sync records, per provider and per competition it asked that provider for,
the outcome of the scores fetch (``results_provider_health``). Two readers:

- the read path: ``serving_routes`` drops a route whose provider is disabled or
  has not succeeded for that competition within ``RESULTS_PROVIDER_STALE_HOURS``,
  so the competition is served by the default provider (whose backup sync keeps
  its rows fresh). One provider per competition, never a mix.
- ops: ``ops_view`` for the admin ``GET /api/results/sync/state``.

Classification of one competition in one provider run:

- the provider raised: ``error`` (exception class name only);
- in ``not_checked``: ``rate_limited`` (a 429 stopped the provider; not a source
  failure, so the failure count is unchanged);
- in ``errors``: ``error``; a parse/shape error also counts in ``shape_failures``;
- otherwise: ``ok`` (the provider answered for it, even with zero games).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ResultsProviderHealthRow
from app.results import settings
from app.results.providers.base import FetchOutcome, ProviderRun  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

PROVIDER_ROW = "*"
_MAX_ERROR_LEN = 200

# Error strings (or their leading "Name:" part) that mean the source answered
# with something we could not read: a format change, not an outage. Providers
# report errors as short class names (``_error``) or "Class: message".
SHAPE_ERRORS = frozenset({
    "MalformedResponse", "ValueError", "TypeError", "KeyError", "AttributeError",
    "IndexError", "JSONDecodeError", "ValidationError",
})

OK, PARTIAL, ERROR, RATE_LIMITED = "ok", "partial", "error", "rate_limited"


def is_shape_error(text: Optional[str]) -> bool:
    if not text:
        return False
    return text.split(":", 1)[0].strip() in SHAPE_ERRORS


def _classify(run: ProviderRun) -> dict[str, tuple[str, Optional[str]]]:
    """competition -> (status, error text) for one provider run."""
    result: dict[str, tuple[str, Optional[str]]] = {}
    out = run.outcome
    for comp in dict.fromkeys(run.competitions):
        if out is None:
            result[comp] = (ERROR, run.raised or "error")
        elif comp in out.not_checked:
            result[comp] = (RATE_LIMITED, "rate limited (429)")
        elif comp in out.errors:
            result[comp] = (ERROR, str(out.errors[comp])[:_MAX_ERROR_LEN])
        else:
            result[comp] = (OK, None)
    return result


def _row(session: Session, provider: str, comp: str) -> ResultsProviderHealthRow:
    row = session.get(ResultsProviderHealthRow, (provider, comp))
    if row is None:
        row = ResultsProviderHealthRow(provider=provider, competition_id=comp,
                                       consecutive_failures=0, shape_failures=0)
        session.add(row)
    return row


def _apply(row: ResultsProviderHealthRow, status: str, error: Optional[str],
           shape: bool, now_iso: str) -> None:
    row.last_attempt_at = now_iso
    row.last_status = status
    if status in (OK, PARTIAL):
        row.last_success_at = now_iso
        row.consecutive_failures = 0
    elif status == ERROR:
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
    if error:
        row.last_error = error
        row.last_error_at = now_iso
    if shape:
        row.shape_failures = (row.shape_failures or 0) + 1


def record_fetch_health(session: Session, runs: dict[str, ProviderRun], now_iso: str) -> None:
    """Write this sync's per-provider health. Adds to the session; the caller
    commits (and rolls back on failure, so health never fails the sync)."""
    for provider, run in runs.items():
        per_comp = _classify(run)
        if not per_comp:
            continue
        for comp, (status, error) in per_comp.items():
            _apply(_row(session, provider, comp), status, error,
                   status == ERROR and is_shape_error(error), now_iso)
        statuses = {s for s, _ in per_comp.values()}
        if OK in statuses:
            overall = PARTIAL if statuses - {OK} else OK
        elif ERROR in statuses:
            overall = ERROR
        else:
            overall = RATE_LIMITED
        errors = [e for s, e in per_comp.values() if e]
        shape = any(s == ERROR and is_shape_error(e) for s, e in per_comp.values())
        _apply(_row(session, provider, PROVIDER_ROW), overall, errors[0] if errors else None,
               shape, now_iso)


def last_success_by(session: Session, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], Optional[str]]:
    """(provider, competition) -> last_success_at, for the requested pairs."""
    pairs = set(pairs)
    if not pairs:
        return {}
    providers = {p for p, _ in pairs}
    rows = session.execute(
        select(ResultsProviderHealthRow.provider, ResultsProviderHealthRow.competition_id,
               ResultsProviderHealthRow.last_success_at)
        .where(ResultsProviderHealthRow.provider.in_(providers))
    ).all()
    found = {(p, c): s for p, c, s in rows if (p, c) in pairs}
    return {pair: found.get(pair) for pair in pairs}


def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
    if moment is not None and moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _age_hours(value: Optional[str], now: datetime) -> Optional[float]:
    moment = _parse(value)
    return None if moment is None else round((now - moment).total_seconds() / 3600, 2)


def decide(routes: dict[str, str], default: str, disabled: frozenset[str],
           last_success: Optional[dict[tuple[str, str], Optional[str]]],
           now: datetime, stale_hours: int) -> dict[str, tuple[str, str]]:
    """The serving decision for every routed competition: comp -> (provider,
    reason). Pure; ``last_success`` maps (provider, competition) -> ISO time.

    - route to the default itself: the default (``routed``);
    - provider disabled: the default (``disabled``);
    - ``last_success`` None (no health consulted) or ``stale_hours`` 0: the route;
    - routed provider succeeded for this competition within ``stale_hours``: the
      route (``routed``);
    - it never succeeded for it: the default (``never_succeeded``);
    - it is stale: the default (``stale``) if the default succeeded for this
      competition more recently, else the route (``stale_no_fallback``), so a
      competition the default cannot serve keeps stale rows, not an empty list.
    """
    decisions: dict[str, tuple[str, str]] = {}
    for comp, provider in routes.items():
        if provider == default:
            decisions[comp] = (default, "routed")
        elif provider in disabled:
            decisions[comp] = (default, "disabled")
        elif last_success is None or stale_hours <= 0:
            decisions[comp] = (provider, "routed")
        else:
            moment = _parse(last_success.get((provider, comp)))
            if moment is None:
                decisions[comp] = (default, "never_succeeded")
            elif (now - moment).total_seconds() > stale_hours * 3600:
                fallback = _parse(last_success.get((default, comp)))
                decisions[comp] = ((default, "stale") if fallback is not None and fallback > moment
                                   else (provider, "stale_no_fallback"))
            else:
                decisions[comp] = (provider, "routed")
    return decisions


def serving_routes(session: Session, routes: dict[str, str], default: str,
                   disabled: frozenset[str], now: Optional[datetime] = None) -> dict[str, str]:
    """The routes the read path should apply now: only competitions still served
    by their routed provider. Everything else reads the default provider."""
    if not routes:
        return {}
    now = now or datetime.now(tz=timezone.utc)
    stale = settings.provider_stale_hours()
    pairs = [pair for c, p in routes.items() for pair in ((p, c), (default, c))]
    last = last_success_by(session, pairs) if stale > 0 else None
    decisions = decide(routes, default, disabled, last, now, stale)
    return {c: p for c, (p, _) in decisions.items() if p != default}


# ── Ops view ──────────────────────────────────────────────────────────────────

def _blocks(session: Session) -> dict[str, str]:
    from app.db.orm_models import ResultsSyncStateRow
    row = session.get(ResultsSyncStateRow, 1)
    summary = row.last_summary if row is not None else None
    if not isinstance(summary, dict):
        return {}
    by_provider = summary.get("rate_limited_until_by_provider")
    if isinstance(by_provider, dict):
        return {str(k): v for k, v in by_provider.items() if v}
    if summary.get("rate_limited_until"):
        return {"*": summary["rate_limited_until"]}
    return {}


def ops_view(session: Session, now: Optional[datetime] = None) -> dict:
    """Admin-only, read-only: each provider's health and each competition's
    serving provider and freshness. Never raises on a bad route config."""
    from app.results import providers as registry

    now = now or datetime.now(tz=timezone.utc)
    default = registry.default_provider_name()
    config_error = None
    try:
        routes = registry.configured_routes()
        disabled = registry.configured_disabled()
    except ValueError as exc:
        routes, disabled, config_error = {}, frozenset(), str(exc)[:_MAX_ERROR_LEN]
    stale = settings.provider_stale_hours()

    rows = session.execute(select(ResultsProviderHealthRow)).scalars().all()
    by_key = {(r.provider, r.competition_id): r for r in rows}
    blocks = _blocks(session)

    names = sorted({default, *routes.values(), *(r.provider for r in rows)})
    providers = []
    for name in names:
        row = by_key.get((name, PROVIDER_ROW))
        until = blocks.get(name) or blocks.get("*")
        if until and (_parse(until) is None or _parse(until) <= now):
            until = None
        providers.append({
            "provider": name,
            "is_default": name == default,
            "enabled": name == default or name not in disabled,
            "rate_limited_until": until,
            "last_attempt_at": row.last_attempt_at if row else None,
            "last_success_at": row.last_success_at if row else None,
            "last_status": row.last_status if row else None,
            "last_error": row.last_error if row else None,
            "last_error_at": row.last_error_at if row else None,
            "consecutive_failures": row.consecutive_failures if row else 0,
            "shape_failures": row.shape_failures if row else 0,
        })

    last = {k: r.last_success_at for k, r in by_key.items()}
    decisions = decide(routes, default, disabled, last, now, stale)
    competitions = []
    for comp in dict.fromkeys([*settings.tracked_competitions(), *routes]):
        routed_to = routes.get(comp)
        serving, reason = decisions.get(comp, (default, "default"))
        freshness = {}
        for name in dict.fromkeys([p for p in (routed_to, default) if p]):
            row = by_key.get((name, comp))
            freshness[name] = {
                "last_success_at": row.last_success_at if row else None,
                "age_hours": _age_hours(row.last_success_at, now) if row else None,
                "last_status": row.last_status if row else None,
                "consecutive_failures": row.consecutive_failures if row else 0,
            }
        competitions.append({"competition_id": comp, "routed_to": routed_to,
                             "serving": serving, "reason": reason, "freshness": freshness})

    return {
        "default_provider": default,
        "stale_hours": stale,
        "backup_sync": settings.provider_backup_sync_enabled(),
        "config_error": config_error,
        "providers": providers,
        "competitions": competitions,
    }
