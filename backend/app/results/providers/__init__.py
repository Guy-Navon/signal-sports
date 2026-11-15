"""Results provider adapters (issue #178, routing #529)."""
from __future__ import annotations

from typing import Callable

from app.results import settings
from app.results.providers.base import ResultsProvider
from app.results.providers.routing import RoutingProvider, parse_routes


def _fake():
    from app.results.providers.fake import FakeResultsProvider
    return FakeResultsProvider()


def _thesportsdb():
    from app.results.providers.thesportsdb import TheSportsDBProvider
    return TheSportsDBProvider()


# Provider name -> constructor. Adding a provider is one line here.
REGISTRY: dict[str, Callable[[], ResultsProvider]] = {
    "fake": _fake,
    "thesportsdb": _thesportsdb,
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
           "configured_provider_names", "configured_routes"]
