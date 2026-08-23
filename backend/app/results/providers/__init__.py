"""Results provider adapters (issue #178)."""
from __future__ import annotations

from app.results import settings
from app.results.providers.base import ResultsProvider


def get_provider() -> ResultsProvider:
    """Construct the configured provider. ``RESULTS_PROVIDER=fake`` selects the
    offline/test provider; anything else defaults to TheSportsDB."""
    name = settings.provider_name()
    if name == "fake":
        from app.results.providers.fake import FakeResultsProvider
        return FakeResultsProvider()
    from app.results.providers.thesportsdb import TheSportsDBProvider
    return TheSportsDBProvider()


__all__ = ["ResultsProvider", "get_provider"]
