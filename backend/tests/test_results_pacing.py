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


def test_a_retry_after_429_is_also_spaced(monkeypatch):
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "2.5")
    monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")
    clock = _Clock()
    sent_at: list[float] = []

    def handler(request):
        sent_at.append(clock.now)
        if len(sent_at) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"events": []})

    outcome = _provider(handler, clock).fetch(["comp:epl"])

    assert outcome.errors == {}
    assert len(sent_at) == 3  # 429, its retry, then the season request
    assert sent_at[1] - sent_at[0] >= 2.5
