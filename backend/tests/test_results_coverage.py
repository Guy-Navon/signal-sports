"""Recent-results coverage on TheSportsDB's free key.

With key "123", ``eventspastleague`` returns 1 event per league and
``eventsseason`` the season's first 15, so most finished games of the last week
never reached ``game_results`` (2026-10-25: one game per competition in the
week of 19-25 October, except the IBL). The documented free ``eventsday.php``
returns up to 3 events per day, filtered by league id, so the provider also asks
for today and the previous days (UTC), a fixed number of requests per league.

No test here touches the network: every request goes to an httpx.MockTransport.
"""
from datetime import datetime, timezone

import httpx

from app.results.providers.thesportsdb import TheSportsDBProvider

IBL_LEAGUE_ID = "4474"


def _event(event_id: str, date: str, home: str = "Maccabi Tel Aviv BC",
           away: str = "Hapoel Holon", score=("90", "80")) -> dict:
    return {
        "idEvent": event_id,
        "strHomeTeam": home,
        "strAwayTeam": away,
        "intHomeScore": score[0],
        "intAwayScore": score[1],
        "strStatus": "FT",
        "strTimestamp": f"{date}T18:00:00",
        "dateEvent": date,
        "strSeason": "2026-2027",
    }


def _provider(handler, now: datetime) -> TheSportsDBProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TheSportsDBProvider(
        client=client, sleep=lambda s: None, clock=lambda: 0.0, utcnow=lambda: now
    )


def _quiet(monkeypatch, days: str) -> None:
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")
    monkeypatch.setenv("RESULTS_RECENT_DAYS", days)


def test_asks_for_today_and_yesterday_in_utc_per_league(monkeypatch):
    _quiet(monkeypatch, "2")
    days_asked: list[tuple[str, str]] = []

    def handler(request):
        if request.url.path.endswith("/eventsday.php"):
            days_asked.append((request.url.params["d"], request.url.params["l"]))
        return httpx.Response(200, json={"events": None})

    # 00:30 UTC on the 25th is still the 25th in UTC, whatever the local zone.
    now = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    outcome = _provider(handler, now).fetch(["comp:ibl"])

    assert outcome.errors == {}
    assert days_asked == [("2026-10-25", IBL_LEAGUE_ID), ("2026-10-24", IBL_LEAGUE_ID)]


def test_games_from_recent_days_are_stored_alongside_the_league_slices(monkeypatch):
    """The finished games of the last two days reach the outcome, deduplicated
    with the same game returned by eventspastleague."""
    _quiet(monkeypatch, "2")
    by_endpoint = {
        "eventspastleague.php": [_event("100", "2026-10-24")],
        "eventsseason.php": [_event("1", "2026-10-10")],
        "eventsday.php?2026-10-25": [_event("101", "2026-10-25")],
        "eventsday.php?2026-10-24": [_event("100", "2026-10-24"), _event("102", "2026-10-24")],
    }

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "eventsday.php":
            name = f"{name}?{request.url.params['d']}"
        return httpx.Response(200, json={"events": by_endpoint[name]})

    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    outcome = _provider(handler, now).fetch(["comp:ibl"])

    assert sorted(g.external_id for g in outcome.games) == ["1", "100", "101", "102"]
    assert outcome.fetched_counts == {"comp:ibl": 4}


def test_request_count_is_fixed_per_competition(monkeypatch):
    """Bounded: past (1) + seasons + recent days, per competition, every sync."""
    _quiet(monkeypatch, "2")
    sent: list[str] = []

    def handler(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"events": []})

    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    _provider(handler, now).fetch(["comp:ibl", "comp:nba"])

    assert len(sent) == 2 * (1 + 1 + 2)
    assert sent.count("eventsday.php") == 4


def test_recent_days_is_capped_at_a_week(monkeypatch):
    """A config typo (30, 100) must not turn one sync into hundreds of requests."""
    _quiet(monkeypatch, "30")
    sent: list[str] = []

    def handler(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"events": []})

    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    _provider(handler, now).fetch(["comp:ibl"])

    assert sent.count("eventsday.php") == 7


def test_zero_recent_days_sends_no_day_requests(monkeypatch):
    _quiet(monkeypatch, "0")
    sent: list[str] = []

    def handler(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"events": []})

    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    _provider(handler, now).fetch(["comp:ibl"])

    assert sent == ["eventspastleague.php", "eventsseason.php"]


def test_a_day_event_from_another_league_is_not_stored_under_this_competition(monkeypatch):
    """If the league filter were ignored, a day would return other leagues'
    games; storing them under comp:ibl would put foreign games on IBL followers'
    results page."""
    _quiet(monkeypatch, "1")
    other_league = {**_event("900", "2026-10-25", home="Boston Red Sox", away="New York Yankees"),
                    "idLeague": "4424"}
    same_league = {**_event("901", "2026-10-25"), "idLeague": IBL_LEAGUE_ID}

    def handler(request):
        if request.url.path.endswith("/eventsday.php"):
            return httpx.Response(200, json={"events": [other_league, same_league]})
        return httpx.Response(200, json={"events": []})

    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    outcome = _provider(handler, now).fetch(["comp:ibl"])

    assert [g.external_id for g in outcome.games] == ["901"]
