"""Results provider adapters (issue #178, routing #529)."""
from __future__ import annotations

import logging
from typing import Callable

from app.results import settings
from app.results.providers.base import ResultsProvider
from app.results.providers.routing import RoutingProvider, parse_routes

log = logging.getLogger(__name__)


def _fake():
    from app.results.providers.fake import FakeResultsProvider
    return FakeResultsProvider()


def _thesportsdb():
    from app.results.providers.thesportsdb import TheSportsDBProvider
    return TheSportsDBProvider()


def _winner():
    from app.results.providers.winner import WinnerProvider
    return WinnerProvider()


def _euroleague():
    from app.results.providers.euroleague import EuroLeagueProvider
    return EuroLeagueProvider()


def _espn_nba():
    from app.results.providers.espn_nba import ESPNNBAProvider
    return ESPNNBAProvider()


def _bamboo():
    from app.results.providers.bamboo import BambooFootballProvider
    return BambooFootballProvider()


# Provider name -> constructor. Adding a provider is one line here.
REGISTRY: dict[str, Callable[[], ResultsProvider]] = {
    "fake": _fake,
    "thesportsdb": _thesportsdb,
    "winner": _winner,
    "euroleague": _euroleague,
    "espn_nba": _espn_nba,
    "bamboo": _bamboo,
}


def default_provider_name() -> str:
    """``RESULTS_PROVIDER``; an unknown value keeps the historical fallback to
    TheSportsDB."""
    name = settings.provider_name()
    return name if name in REGISTRY else "thesportsdb"


def configured_routes() -> dict[str, str]:
    """The validated ``RESULTS_PROVIDER_ROUTES`` map (empty by default). Raises
    ``ValueError`` for a bad entry, an unknown provider or competition."""
    from app.taxonomy.competitions import COMPETITIONS
    return parse_routes(settings.provider_routes_raw(),
                        known_providers=REGISTRY, known_competitions=COMPETITIONS)


def configured_disabled() -> frozenset[str]:
    """The validated ``RESULTS_PROVIDER_DISABLED`` set (#522; empty by default).
    Raises ``ValueError`` for an unknown name (a typo must not leave a broken
    source switched on) or for the default provider, which is the fallback for
    everything and cannot be switched off this way."""
    names = frozenset(n.strip().lower() for n in settings.provider_disabled_raw().split(",")
                      if n.strip())
    unknown = names - set(REGISTRY)
    if unknown:
        raise ValueError(f"RESULTS_PROVIDER_DISABLED: unknown provider(s) {sorted(unknown)} "
                         f"(known: {sorted(REGISTRY)})")
    if default_provider_name() in names:
        raise ValueError("RESULTS_PROVIDER_DISABLED: the default provider "
                         f"{default_provider_name()!r} cannot be disabled")
    return names


def effective_routes() -> dict[str, str]:
    """The routes the SYNC uses: configured routes minus disabled providers, whose
    competitions fall back to the default. Raises ``ValueError`` like its parts."""
    disabled = configured_disabled()
    return {c: p for c, p in configured_routes().items() if p not in disabled}


def active_provider_map(session=None, *, now=None) -> tuple[dict[str, str], str]:
    """``(routes, default)`` for the READ path: per competition, the one provider
    whose rows are served.

    A route is dropped (the competition reads the default provider) when its
    provider is disabled or, given a ``session``, when the provider has not
    succeeded for that competition within ``RESULTS_PROVIDER_STALE_HOURS`` at
    ``now`` (#522). Without a session only the switch applies (the #532 rule).
    A bad config must not break reads: fall back to no routes and log."""
    default = default_provider_name()
    try:
        routes = configured_routes()
        disabled = configured_disabled()
    except ValueError as exc:
        log.warning("invalid RESULTS_PROVIDER_ROUTES/RESULTS_PROVIDER_DISABLED, "
                    "reading default provider only: %s", exc)
        return {}, default
    if session is None:
        return {c: p for c, p in routes.items() if p not in disabled}, default
    from app.results import health
    try:
        return health.serving_routes(session, routes, default, disabled, now), default
    except Exception:
        # Health unreadable: the default provider always has a row set to serve.
        log.exception("results health unreadable, reading default provider only")
        session.rollback()
        return {}, default


def active_provider_for(competition_id: str, session=None, *, now=None) -> str:
    """The provider whose rows are served for this competition (#532, #522): the
    serving route, else the default."""
    routes, default = active_provider_map(session, now=now)
    return routes.get(competition_id, default)


def configured_provider_names() -> list[str]:
    """Provider names the sync calls, without constructing anything."""
    return sorted({default_provider_name(), *effective_routes().values()})


def get_provider() -> ResultsProvider:
    """Construct the configured provider. With no (enabled) routes this is the
    plain default provider (exactly the single-provider behaviour); with routes it
    is a ``RoutingProvider`` over the providers in use, with the default's backup
    sync on unless ``RESULTS_PROVIDER_BACKUP_SYNC=false`` (#522)."""
    default = default_provider_name()
    routes = effective_routes()
    if not routes:
        return REGISTRY[default]()
    names = {default, *routes.values()}
    return RoutingProvider({n: REGISTRY[n]() for n in names}, routes, default,
                           backup=settings.provider_backup_sync_enabled())


__all__ = ["ResultsProvider", "RoutingProvider", "REGISTRY", "get_provider",
           "configured_provider_names", "configured_routes", "configured_disabled",
           "effective_routes", "active_provider_map", "active_provider_for"]
