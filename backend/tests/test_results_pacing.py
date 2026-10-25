"""TheSportsDB request pacing.

The free key allows 30 requests a minute. One sync makes 1 + one per season
requests per competition, back to back. On 2026-10-25, 20 requests in about 7 s
earned 429s for five competitions. The provider must space its requests,
including retries.
"""
import httpx

from app.results.providers.thesportsdb import TheSportsDBProvider


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def _provider(handler, clock):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TheSportsDBProvider(client=client, sleep=clock.sleep, clock=clock)


def test_requests_are_spaced_by_the_minimum_interval(monkeypatch):
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "2.5")
    monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")
    clock = _Clock()
    sent_at: list[float] = []

    def handler(request):
        sent_at.append(clock.now)
        return httpx.Response(200, json={"events": []})

    outcome = _provider(handler, clock).fetch(["comp:epl", "comp:ibl", "comp:nba"])

    assert outcome.errors == {}
    assert len(sent_at) == 6  # 3 competitions x (past + one season)
    gaps = [b - a for a, b in zip(sent_at, sent_at[1:])]
    assert min(gaps) >= 2.5


def test_a_429_stops_the_sync_and_marks_the_rest_not_checked(monkeypatch):
    """Retrying into a block extends it (2026-10-25: every football league
    429'd for a whole sync). After a 429, nothing more is sent this sync."""
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")
    clock = _Clock()
    sent: list[str] = []

    def handler(request):
        sent.append(request.url.params["id"])
        if len(sent) == 3:  # the second competition's first request
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(200, json={"events": []})

    outcome = _provider(handler, clock).fetch(["comp:epl", "comp:ibl", "comp:nba"])

    assert len(sent) == 3
    assert outcome.not_checked == ["comp:ibl", "comp:nba"]
    assert outcome.errors == {}
    assert outcome.retry_after_seconds == 60


def test_a_429_without_retry_after_waits_a_minute(monkeypatch):
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "0")
    clock = _Clock()
    outcome = _provider(lambda request: httpx.Response(429), clock).fetch(["comp:epl"])
    assert outcome.not_checked == ["comp:epl"]
    assert outcome.retry_after_seconds == 60


# ── The block is honored across syncs and processes (it lives in the DB) ────

class _CountingProvider:
    name = "counting"

    def __init__(self, outcome):
        self.calls = 0
        self._outcome = outcome

    def fetch(self, competition_ids):
        self.calls += 1
        return self._outcome


def test_no_provider_call_until_retry_after_has_passed(client, monkeypatch):
    from datetime import timedelta

    from app.db.database import SessionLocal
    from app.db.orm_models import ResultsSyncStateRow
    from app.results import sync_service
    from app.results.providers.base import FetchOutcome

    t0 = sync_service._now()
    monkeypatch.setattr(sync_service, "_now", lambda: t0)
    with SessionLocal() as s:
        s.query(ResultsSyncStateRow).delete()
        s.commit()
        blocked = _CountingProvider(FetchOutcome(not_checked=["comp:epl"], retry_after_seconds=60))
        first = sync_service.sync_results(s, provider=blocked, competition_ids=["comp:epl"])
        assert first["status"] == "rate_limited"
        assert first["not_checked"] == ["comp:epl"]

        # 30 s later, even a forced (admin) sync must not call the provider.
        monkeypatch.setattr(sync_service, "_now", lambda: t0 + timedelta(seconds=30))
        waiting = _CountingProvider(FetchOutcome())
        second = sync_service.sync_results(s, provider=waiting, force=True,
                                           competition_ids=["comp:epl"])
        assert waiting.calls == 0
        assert second["skipped"] == "rate_limited"

        # Once the wait is over, the provider is called again.
        monkeypatch.setattr(sync_service, "_now", lambda: t0 + timedelta(seconds=61))
        sync_service.sync_results(s, provider=waiting, force=True, competition_ids=["comp:epl"])
        assert waiting.calls == 1
