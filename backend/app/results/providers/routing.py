"""Per-competition provider routing (issue #529).

``RoutingProvider`` implements the same protocol as a single provider and sends
each competition to the provider the route map names. The default map sends every
competition to ``RESULTS_PROVIDER``, so with no ``RESULTS_PROVIDER_ROUTES`` the
requests are exactly what the single provider sent before (``get_provider`` then
returns the plain provider, not a router).

Rate limits are per provider: a 429 from one provider puts only its own
competitions (or games) in ``not_checked``; the others proceed.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from app.results.models import NormalizedGame
from app.results.providers.base import DetailOutcome, FetchOutcome, supports_details

logger = logging.getLogger(__name__)


def parse_routes(raw: Optional[str], *, known_providers: Iterable[str],
                 known_competitions: Iterable[str]) -> dict[str, str]:
    """Parse ``"comp:ibl=winner,comp:euroleague=euroleague"``. Raises ``ValueError``
    on a bad entry, an unknown provider or competition, or a competition routed
    twice: a typo must never silently send a competition to the wrong place."""
    providers, comps = set(known_providers), set(known_competitions)
    routes: dict[str, str] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        comp, sep, name = (part.strip() for part in entry.partition("="))
        name = name.lower()
        if not sep or not comp or not name:
            raise ValueError(f"RESULTS_PROVIDER_ROUTES entry {entry!r} is not 'competition=provider'")
        if comp not in comps:
            raise ValueError(f"RESULTS_PROVIDER_ROUTES: unknown competition {comp!r}")
        if name not in providers:
            raise ValueError(
                f"RESULTS_PROVIDER_ROUTES: unknown provider {name!r} (known: {sorted(providers)})")
        if comp in routes:
            raise ValueError(f"RESULTS_PROVIDER_ROUTES: competition {comp!r} is routed twice")
        routes[comp] = name
    return routes


class RoutingProvider:
    name = "routing"

    def __init__(self, providers: dict[str, object], routes: dict[str, str], default: str):
        missing = ({default} | set(routes.values())) - set(providers)
        if missing:
            raise ValueError(f"routing refers to providers not constructed: {sorted(missing)}")
        self._providers = providers
        self._routes = dict(routes)
        self._default = default
        # Provider names the caller wants skipped this run (rate-limited earlier).
        self._blocked: set[str] = set()

    @property
    def provider_names(self) -> list[str]:
        return sorted({self._default, *self._routes.values()})

    def provider_for(self, competition_id: str) -> str:
        return self._routes.get(competition_id, self._default)

    def set_blocked(self, names: Iterable[str]) -> None:
        self._blocked = set(names)

    def detail_provider_names(self) -> list[str]:
        return [n for n in self.provider_names if supports_details(self._providers[n])]

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        by_provider: dict[str, list[str]] = {}
        for comp in competition_ids:
            by_provider.setdefault(self.provider_for(comp), []).append(comp)
        merged = FetchOutcome()
        for name in sorted(by_provider):
            comps = by_provider[name]
            if name in self._blocked:
                merged.not_checked.extend(comps)
                merged.provider_retry_after.setdefault(name, None)
                continue
            try:
                out = self._providers[name].fetch(comps)  # type: ignore[attr-defined]
            except Exception as exc:
                # One provider raising must not lose the others. Class name only:
                # the message is stored and served and can carry a URL with a key.
                logger.exception("results routing: provider %s failed unexpectedly", name)
                for comp in comps:
                    merged.errors[comp] = type(exc).__name__
                continue
            merged.games.extend(out.games)
            merged.errors.update(out.errors)
            merged.fetched_counts.update(out.fetched_counts)
            merged.not_checked.extend(out.not_checked)
            if out.retry_after_seconds is not None or out.not_checked:
                merged.provider_retry_after[name] = out.retry_after_seconds
        retries = [v for v in merged.provider_retry_after.values() if v is not None]
        merged.retry_after_seconds = max(retries) if retries else None
        return merged

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        by_provider: dict[str, list[NormalizedGame]] = {}
        for game in games:
            by_provider.setdefault(game.provider, []).append(game)
        merged = DetailOutcome()
        for name in sorted(by_provider):
            provider = self._providers.get(name)
            if provider is None or not supports_details(provider) or name in self._blocked:
                continue  # stays a candidate; never asked of a provider that cannot answer
            try:
                out = provider.fetch_details(by_provider[name])  # type: ignore[attr-defined]
            except Exception as exc:
                logger.exception("results routing: %s detail failed unexpectedly", name)
                for game in by_provider[name]:
                    merged.errors[game.id] = type(exc).__name__
                continue
            merged.details.extend(out.details)
            merged.errors.update(out.errors)
            merged.not_checked.extend(out.not_checked)
            if out.retry_after_seconds is not None or out.not_checked:
                merged.provider_retry_after[name] = out.retry_after_seconds
        retries = [v for v in merged.provider_retry_after.values() if v is not None]
        merged.retry_after_seconds = max(retries) if retries else None
        return merged
