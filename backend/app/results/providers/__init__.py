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


def active_provider_map() -> tuple[dict[str, str], str]:
    """``(routes, default)`` for the READ path. A bad route config must not break
    reads: fall back to no routes (everything on the default provider) and log."""
    default = default_provider_name()
    try:
        return configured_routes(), default
    except ValueError as exc:
        log.warning("invalid RESULTS_PROVIDER_ROUTES, reading default provider only: %s", exc)
        return {}, default


def active_provider_for(competition_id: str) -> str:
    """The provider this competition is currently routed to (#532): the route,
    else the default. Reads show only that provider's rows."""
    routes, default = active_provider_map()
    return routes.get(competition_id, default)


def configured_provider_names() -> list[str]:
    """Provider names the configuration uses, without constructing anything."""
    return sorted({default_provider_name(), *configured_routes().values()})


def get_provider() -> ResultsProvider:
    """Construct the configured provider. With no routes this is the plain
    default provider (exactly the single-provider behaviour); with routes it is a
    ``RoutingProvider`` over the providers in use."""
    default = default_provider_name()
    routes = configured_routes()
    if not routes:
        return REGISTRY[default]()
    names = {default, *routes.values()}
    return RoutingProvider({n: REGISTRY[n]() for n in names}, routes, default)


__all__ = ["ResultsProvider", "RoutingProvider", "REGISTRY", "get_provider",
           "configured_provider_names", "configured_routes", "active_provider_map",
           "active_provider_for"]
