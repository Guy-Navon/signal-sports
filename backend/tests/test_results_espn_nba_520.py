"""Saved ESPN NBA payloads; real transports and the live database are forbidden."""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.results import providers


FIXTURES = Path(__file__).parent / "fixtures/results/nba"
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def payload(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def scoreboard():
    return payload("espn_scoreboard_20261113.json")


def event():
    return next(e for e in scoreboard()["events"] if e["id"] == "401909303")


def summary():
    return payload("espn_summary_401909303_POR_SAC.json")


def reply(request):
    if request.url.path.endswith("summary"):
        name = {"401909303": "POR_SAC", "401909976": "TOR_PHI"}[request.url.params["event"]]
        return httpx.Response(200, json=payload(f"espn_summary_{request.url.params['event']}_{name}.json"))
    date = request.url.params["dates"]
    data = payload(f"espn_scoreboard_{date}.json") if date in ("20261112", "20261113") else {"events": []}
    return httpx.Response(200, json=data)


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def make_provider(monkeypatch):
    from app.results.providers.espn_nba import ESPNNBAProvider

    monkeypatch.setenv("RESULTS_ESPN_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_HTTP_MAX_RETRIES", "2")
    monkeypatch.setenv("RESULTS_ESPN_DAYS_BACK", "1")
    monkeypatch.setenv("RESULTS_ESPN_DAYS_AHEAD", "3")

    def no_network(*args, **kwargs):
        raise AssertionError("real network is forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    clients = []

    def make(handler=reply, *, now=NOW, clock=None):
        clock = clock or Clock()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return ESPNNBAProvider(client=client, utcnow=lambda: now, clock=clock, sleep=clock.sleep)

    yield make
    for client in clients:
        client.close()


def final_game(provider):
    return next(g for g in provider.fetch(["comp:nba"]).games if g.external_id == "401909303")


def test_saved_scoreboard_home_away_scores_ids_and_next_israel_date(make_provider):
    game = final_game(make_provider())
    assert (game.provider, game.competition_id, game.sport) == ("espn_nba", "comp:nba", "basketball")
    assert game.season == "2026-2027" and game.status == "final"
    assert (game.home_team_name, game.away_team_name) == ("Sacramento Kings", "Portland Trail Blazers")
    assert (game.home_team_id, game.away_team_id) == ("team:sacramento_kings", "team:portland_blazers")
    assert (game.home_score, game.away_score) == (107, 120)
    assert game.start_time == "2026-11-14T03:00:00+00:00"
    assert datetime.fromisoformat(game.start_time).astimezone(ZoneInfo("Asia/Jerusalem")).date().isoformat() == "2026-11-14"


@pytest.mark.parametrize("now,dates", [
    (datetime(2026, 11, 15, 0, 30, tzinfo=timezone.utc), ["20261113", "20261114", "20261115", "20261116", "20261117"]),
    (datetime(2026, 7, 1, 3, 30, tzinfo=timezone.utc), ["20260629", "20260630", "20260701", "20260702", "20260703"]),
])
def test_window_uses_new_york_calendar_including_dst(make_provider, now, dates):
    sent = []
    def handler(request):
        sent.append(request.url.params["dates"])
        return httpx.Response(200, json={"events": []})
    out = make_provider(handler, now=now).fetch(["comp:nba", "comp:nba", "comp:epl"])
    assert sent == dates
    assert out.fetched_counts == {"comp:nba": 0}
    assert set(out.errors) == {"comp:epl"}


def test_configured_window_and_empty_unsupported_requests(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_ESPN_DAYS_BACK", "2")
    monkeypatch.setenv("RESULTS_ESPN_DAYS_AHEAD", "0")
    sent = []
    def handler(request):
        sent.append(request.url.params["dates"])
        return httpx.Response(200, json={"events": []})
    p = make_provider(handler)
    assert set(p.fetch(["comp:ibl"]).errors) == {"comp:ibl"}
    assert not p.fetch([]).games and not sent
    p.fetch(["comp:nba"])
    assert sent == ["20261112", "20261113", "20261114"]


@pytest.mark.parametrize("state,completed,name,want", [
    ("pre", False, "STATUS_SCHEDULED", "scheduled"),
    ("in", False, "STATUS_IN_PROGRESS", "live"),
    ("post", True, "STATUS_FINAL", "final"),
    ("post", False, "STATUS_FINAL", "unknown"),
    ("pre", False, "STATUS_POSTPONED", "postponed"),
    ("post", False, "STATUS_CANCELED", "cancelled"),
])
def test_status_scores_only_for_final(make_provider, state, completed, name, want):
    raw = event()
    raw["status"]["type"] = {"state": state, "completed": completed, "name": name}
    raw["competitions"][0]["competitors"].reverse()
    out = make_provider(lambda r: httpx.Response(200, json={"events": [raw]})).fetch(["comp:nba"])
    assert len(out.games) == 1 and not out.errors
    g = out.games[0]
    assert g.status == want
    assert (g.home_score, g.away_score) == ((107, 120) if want == "final" else (None, None))


@pytest.mark.parametrize("date,season", [("2026-09-30T23:00Z", "2025-2026"), ("2026-10-01T23:00Z", "2026-2027"), ("2027-01-15T03:00Z", "2026-2027")])
def test_season_rolls_in_october_from_event_time(make_provider, date, season):
    raw = event()
    raw["date"] = date
    g = make_provider(lambda r: httpx.Response(200, json={"events": [raw]})).fetch(["comp:nba"]).games[0]
    assert g.season == season


def test_unknown_team_keeps_source_name_without_taxonomy_alias(make_provider):
    raw = event()
    raw["competitions"][0]["competitors"][0]["team"]["displayName"] = "Unregistered Moon Club"
    g = make_provider(lambda r: httpx.Response(200, json={"events": [raw]})).fetch(["comp:nba"]).games[0]
    assert g.home_team_id is None and g.home_team_name == "Unregistered Moon Club"


def test_summary_preserves_deni_shooting_strings_minutes_and_top_scorers(make_provider):
    p = make_provider()
    g = final_game(p)
    out = p.fetch_details([g])
    assert not out.errors and len(out.details) == 1
    d = out.details[0]
    assert d.game_id == g.id and d.provider == "espn_nba"
    deni = next(l for l in d.players if l.name == "Deni Avdija")
    assert deni.side == "away" and deni.source_player_id == "4683021"
    assert deni.minutes == 35.0 and deni.name_he is None
    assert {k: deni.stats[k] for k in ("PTS", "FG", "FT", "REB", "AST", "+/-", "points")} == {
        "PTS": "34", "FG": "11-13", "FT": "9-9", "REB": "6", "AST": "4", "+/-": "+11", "points": 34}
    assert {(l.side, l.name, l.value) for l in d.leaders if l.stat == "points"} == {
        ("away", "Deni Avdija", 34), ("home", "De'Andre Hunter", 24)}
    sabonis = next(l for l in d.players if l.name == "Domantas Sabonis")
    assert sabonis.stats["PTS"] == "21" and sabonis.stats["REB"] == "12"
    assert d.team_stats["away"]["fieldGoalsMade-fieldGoalsAttempted"] == "37-77"
    assert d.team_stats["away"]["quarters"] == [34, 30, 29, 27]
    assert d.team_stats["home"]["quarters"] == [25, 28, 25, 29]
    assert d.venue == "Golden 1 Center" and d.attendance == 14831


def test_old_game_detail_gets_quarters_from_summary_header_without_scoreboard(make_provider):
    g = final_game(make_provider())
    d = make_provider().fetch_details([g]).details[0]
    assert d.team_stats["away"]["quarters"] == [34, 30, 29, 27]


def test_scoreboard_leaders_and_numeric_quarters_are_normalized(make_provider):
    from app.results.providers.espn_nba import normalize_scoreboard_detail

    g = final_game(make_provider())
    raw = event()
    for c in raw["competitions"][0]["competitors"]:
        for quarter in c["linescores"]:
            quarter.pop("displayValue")
    d = normalize_scoreboard_detail(raw, g)
    assert d.team_stats["away"]["quarters"] == [34, 30, 29, 27]
    assert {(l.side, l.stat, l.name, l.value) for l in d.leaders} == {
        ("home", "points", "De'Andre Hunter", 24),
        ("home", "rebounds", "Domantas Sabonis", 12),
        ("home", "assists", "Darius Acuff Jr.", 6),
        ("away", "points", "Deni Avdija", 34),
        ("away", "rebounds", "Donovan Clingan", 11),
        ("away", "assists", "Damian Lillard", 6),
    }


def test_unfinished_summary_is_not_permanently_cached(make_provider):
    g = final_game(make_provider())
    data = summary()
    data["header"]["competitions"][0]["status"]["type"].update(completed=False, state="in")
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch_details([g])
    assert not out.details and not out.errors


def test_scoreboard_quarters_survive_when_summary_header_omits_them(make_provider):
    data = summary()
    for c in data["header"]["competitions"][0]["competitors"]:
        c.pop("linescores", None)
    def handler(request):
        return httpx.Response(200, json=data) if request.url.path.endswith("summary") else reply(request)
    p = make_provider(handler)
    d = p.fetch_details([final_game(p)]).details[0]
    assert d.team_stats["away"]["quarters"] == [34, 30, 29, 27]


def test_second_real_summary_and_team_matching_not_array_position(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_ESPN_DAYS_BACK", "2")
    p = make_provider()
    g = next(g for g in p.fetch(["comp:nba"]).games if g.external_id == "401909976")
    d = p.fetch_details([g]).details[0]
    assert (g.home_score, g.away_score) == (123, 112)
    assert {(l.side, l.name, l.value) for l in d.leaders if l.stat == "points"} == {
        ("home", "Tyrese Maxey", 27), ("away", "RJ Barrett", 31)}
    barrett = next(l for l in d.players if l.name == "RJ Barrett")
    assert barrett.stats["REB"] == "14" and barrett.side == "away"


def test_dnp_is_skipped_and_clock_minutes_and_label_order_are_parsed(make_provider):
    data = summary()
    block = data["boxscore"]["players"][0]["statistics"][0]
    deni = next(a for a in block["athletes"] if a["athlete"]["displayName"] == "Deni Avdija")
    deni["stats"][0] = "35:30"
    block["athletes"].append({"athlete": {"id": "dnp", "displayName": "Bench Player"}, "didNotPlay": True, "stats": ["DNP"]})
    block["labels"].reverse()
    for a in block["athletes"]:
        a["stats"].reverse()
    g = final_game(make_provider())
    d = make_provider(lambda r: httpx.Response(200, json=data)).fetch_details([g]).details[0]
    assert all(l.source_player_id != "dnp" for l in d.players)
    assert next(l for l in d.players if l.name == "Deni Avdija").minutes == 35.5
    assert next(l for l in d.leaders if l.name == "Deni Avdija" and l.stat == "points").value == 34


def test_malformed_summary_is_per_game_error_and_next_game_survives(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_ESPN_DAYS_BACK", "2")
    p = make_provider()
    games = [g for g in p.fetch(["comp:nba"]).games if g.external_id in ("401909303", "401909976")]
    bad = summary()
    bad["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"] = ["not aligned"]
    def handler(request):
        return httpx.Response(200, json=bad) if request.url.params["event"] == "401909303" else reply(request)
    out = make_provider(handler).fetch_details(games)
    assert set(out.errors) == {next(g.id for g in games if g.external_id == "401909303")}
    assert [d.external_id for d in out.details] == ["401909976"]
    assert "http" not in str(out.errors)


def test_empty_boxscore_stays_pending_and_wrong_identity_is_error(make_provider):
    g = final_game(make_provider())
    empty = make_provider(lambda r: httpx.Response(200, json={"boxscore": {"players": []}})).fetch_details([g])
    assert not empty.details and not empty.errors
    bad = summary()
    bad["header"]["id"] = "999"
    out = make_provider(lambda r: httpx.Response(200, json=bad)).fetch_details([g])
    assert not out.details and set(out.errors) == {g.id}


def test_incomplete_team_lines_are_not_cached_as_complete_detail(make_provider):
    g = final_game(make_provider())
    data = summary()
    data["boxscore"]["players"][0]["statistics"][0]["athletes"] = []
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch_details([g])
    assert not out.details and set(out.errors) == {g.id}


@pytest.mark.parametrize("data", [[], {"wrong": []}, {"events": None}])
def test_malformed_scoreboard_is_safe_competition_error(make_provider, data):
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch(["comp:nba"])
    assert not out.games and set(out.errors) == {"comp:nba"}
    assert "http" not in str(out.errors)


def test_malformed_event_does_not_lose_healthy_games(make_provider):
    raw = event()
    out = make_provider(lambda r: httpx.Response(200, json={"events": [None, {"id": "bad"}, raw, raw]})).fetch(["comp:nba"])
    assert [g.external_id for g in out.games] == ["401909303"]


def test_scoreboard_429_preserves_prior_date_and_propagates_retry_after(make_provider):
    sent = []
    def handler(request):
        sent.append(request.url.params["dates"])
        if len(sent) == 2:
            return httpx.Response(429, headers={"Retry-After": "123"})
        return reply(request)
    out = make_provider(handler).fetch(["comp:nba"])
    assert sent == ["20261113", "20261114"]
    assert len(out.games) == 9 and out.fetched_counts == {"comp:nba": 9}
    assert out.not_checked == ["comp:nba"] and out.retry_after_seconds == 123
    assert not out.errors


def test_summary_429_stops_remaining_games_without_retry(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_ESPN_DAYS_BACK", "2")
    games = [g for g in make_provider().fetch(["comp:nba"]).games if g.external_id in ("401909303", "401909976")]
    sent = []
    def handler(request):
        sent.append(request.url.params["event"])
        return httpx.Response(429, headers={"Retry-After": "bad"})
    out = make_provider(handler).fetch_details(games)
    assert len(sent) == 1 and not out.errors and not out.details
    assert out.not_checked == [g.id for g in games] and out.retry_after_seconds == 60


@pytest.mark.parametrize("failure", [503, "timeout"])
@pytest.mark.parametrize("recovers", [True, False])
def test_bounded_transient_retries(make_provider, failure, recovers):
    g = final_game(make_provider())
    attempts = []
    def handler(request):
        attempts.append(request)
        if recovers and len(attempts) == 3:
            return reply(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("https://example.test/private", request=request)
        return httpx.Response(failure)
    out = make_provider(handler).fetch_details([g])
    assert len(attempts) == 3
    assert bool(out.details) is recovers
    assert bool(out.errors) is not recovers
    assert "http" not in str(out.errors)


@pytest.mark.parametrize("status", [401, 403, 404])
def test_permanent_http_failure_is_not_retried(make_provider, status):
    g = final_game(make_provider())
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(status)
    out = make_provider(handler).fetch_details([g])
    assert len(sent) == 1 and set(out.errors) == {g.id}
    assert str(status) in out.errors[g.id] and "http" not in out.errors[g.id]


def test_pacing_shared_between_scoreboards_summaries_and_retries(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_ESPN_MIN_INTERVAL_SECONDS", "2")
    clock = Clock()
    sent = []
    def handler(request):
        sent.append(clock())
        if len(sent) == 2:
            return httpx.Response(503)
        return reply(request)
    p = make_provider(handler, clock=clock)
    p.fetch_details([final_game(p)])
    assert len(sent) == 7
    assert all(b - a >= 2 for a, b in zip(sent, sent[1:]))


def test_owned_client_accepts_gzip_and_has_timeout_and_honest_user_agent(make_provider, monkeypatch):
    from app.results.providers.espn_nba import ESPNNBAProvider
    original = httpx.Client
    sent = []
    def handler(request):
        sent.append(request)
        assert "gzip" in request.headers["Accept-Encoding"]
        assert request.headers["User-Agent"] == "signal-sports-results/1.0"
        assert request.extensions["timeout"]["read"] == 15
        return httpx.Response(200, content=gzip.compress(b'{"events": []}'), headers={"Content-Encoding": "gzip"})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    out = ESPNNBAProvider(utcnow=lambda: NOW).fetch(["comp:nba"])
    assert not out.errors and len(sent) == 5


def test_registration_routes_nba_only_with_fake_default(make_provider, monkeypatch):
    assert "espn_nba" in providers.REGISTRY
    monkeypatch.setitem(providers.REGISTRY, "espn_nba", lambda: make_provider())
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:nba=espn_nba")
    out = providers.get_provider().fetch(["comp:nba", "comp:euroleague"])
    assert not out.errors
    assert {g.provider for g in out.games} == {"espn_nba", "fake"}
    assert all(g.competition_id == "comp:nba" for g in out.games if g.provider == "espn_nba")


@pytest.mark.parametrize("detail_enabled", [False, True])
def test_sync_in_isolated_db_never_refetches_stored_detail(make_provider, monkeypatch, detail_enabled):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from app.db.orm_models import Base, GameResultRow
    from app.repositories.game_detail_repository import get_details
    from app.results.sync_service import sync_results

    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", str(detail_enabled).lower())
    sent = []
    def handler(request):
        sent.append(request.url.path)
        if request.url.path.endswith("scoreboard"):
            return httpx.Response(200, json={"events": [event()]})
        return reply(request)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            first = sync_results(session, provider=make_provider(handler), competition_ids=["comp:nba"])
            assert first["status"] == "ok"
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 1
            if detail_enabled:
                assert first["detail"]["stored"] == 1
                stored = get_details(session, [final_game(make_provider()).id])
                assert len(stored) == 1
                assert next(l for d in stored.values() for l in d.players if l.name == "Deni Avdija").stats["points"] == 34
            else:
                assert "detail" not in first
            before = len(sent)
            second = sync_results(session, provider=make_provider(handler), competition_ids=["comp:nba"])
            assert second["status"] == "ok" and len(sent) == before + 5
            assert sum(p.endswith("summary") for p in sent) == int(detail_enabled)
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 1
    finally:
        engine.dispose()
