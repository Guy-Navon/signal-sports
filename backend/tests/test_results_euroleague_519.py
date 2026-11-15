"""Official EuroLeague/EuroCup payloads; every HTTP request uses MockTransport."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.results import providers
from app.results.providers.base import supports_details
from app.results.providers.fake import FakeResultsProvider


FIXTURES = Path(__file__).parent / "fixtures/results/euroleague"
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def payload(filename):
    return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def reply(request):
    if request.url.path.endswith("basicstandings"):
        name = ("v3_standings_U2026_round7.json" if "/competitions/U/" in request.url.path
                else "v3_standings_E2026_round11.json")
        return httpx.Response(200, json=payload(name))
    if request.url.path.endswith("Boxscore"):
        code = request.url.params.get("seasoncode", "E")[0]
        return httpx.Response(200, json=payload(f"live_boxscore_{code}2026_103.json"))
    code = "U" if "/competitions/U/" in request.url.path else "E"
    return httpx.Response(200, json=payload(f"v2_games_{code}2026.json"))


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def make_provider(monkeypatch):
    from app.results.providers.euroleague import EuroLeagueProvider

    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_HTTP_MAX_RETRIES", "2")
    # Fail loudly if any test accidentally constructs a real HTTP transport.
    def no_network(*args, **kwargs):
        raise AssertionError("real network is forbidden")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    clients = []

    def make(handler=reply, *, now=NOW, clock=None):
        clock = clock or Clock()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return EuroLeagueProvider(client=client, sleep=clock.sleep, clock=clock,
                                  utcnow=lambda: now)
    yield make
    for client in clients:
        client.close()


def final_game(provider):
    return next(g for g in provider.fetch(["comp:euroleague"]).games
                if g.external_id == "E2026_103")


def test_saved_season_normalizes_identity_teams_score_round_and_utc(make_provider):
    game = final_game(make_provider())
    assert game.provider == "euroleague"
    assert game.competition_id == "comp:euroleague"
    assert game.sport == "basketball"
    assert game.season == "2026-2027"
    assert game.stage == "11"
    assert game.status == "final"
    assert game.start_time == "2026-11-12T19:05:00+00:00"
    assert (game.home_team_name, game.away_team_name) == (
        "Maccabi Rapyd Tel Aviv", "Hapoel IBI Tel Aviv")
    assert (game.home_team_id, game.away_team_id) == (
        "team:maccabi_tlv_bb", "team:hapoel_tlv_bb")
    assert (game.home_score, game.away_score) == (80, 73)


def test_upcoming_is_scheduled_without_zero_scores(make_provider):
    games = make_provider().fetch(["comp:euroleague"]).games
    upcoming = next(g for g in games if g.external_id == "E2026_379")
    assert upcoming.status == "scheduled"
    assert upcoming.home_score is None and upcoming.away_score is None
    assert upcoming.start_time == "2027-04-16T18:30:00+00:00"


def test_local_date_offset_is_used_when_utc_date_is_missing(make_provider):
    data = payload("v2_games_E2026.json")
    data["data"][0].pop("utcDate")
    p = make_provider(lambda r: httpx.Response(200, json=data))
    assert final_game(p).start_time == "2026-11-12T19:05:00+00:00"


@pytest.mark.parametrize("now,season", [
    (datetime(2027, 1, 1, tzinfo=timezone.utc), "2026"),
    (datetime(2027, 6, 30, tzinfo=timezone.utc), "2026"),
    (datetime(2027, 7, 1, tzinfo=timezone.utc), "2027"),
    (NOW, "2026"),
])
def test_one_current_season_request_per_competition(make_provider, now, season):
    sent = []
    def handler(request):
        sent.append(request.url.path)
        return httpx.Response(200, json={"data": []})
    out = make_provider(handler, now=now).fetch([
        "comp:euroleague", "comp:eurocup", "comp:euroleague"])
    assert sent == [f"/v2/competitions/E/seasons/E{season}/games",
                    f"/v2/competitions/U/seasons/U{season}/games"]
    assert out.errors == {}
    assert out.fetched_counts == {"comp:euroleague": 0, "comp:eurocup": 0}


def test_eurocup_uses_its_own_season_and_game_identity(make_provider):
    out = make_provider().fetch(["comp:eurocup"])
    assert not out.errors
    assert len(out.games) == 2
    assert {g.status for g in out.games} == {"final", "scheduled"}
    assert all(g.external_id.startswith("U2026_") and
               g.competition_id == "comp:eurocup" for g in out.games)


def test_saved_eurocup_boxscore_and_group_standings(make_provider):
    p = make_provider()
    g = next(g for g in p.fetch(["comp:eurocup"]).games if g.status == "final")
    out = p.fetch_details([g])
    assert not out.errors and len(out.details) == 1
    d = out.details[0]
    assert d.external_id == "U2026_103" and d.game_id == g.id
    assert (d.team_stats["home"]["Points"], d.team_stats["away"]["Points"]) == (89, 113)
    standings = payload("v3_standings_U2026_round7.json")["teams"]
    for side, name in (("home", g.home_team_name), ("away", g.away_team_name)):
        rank = next(t["position"] for t in standings if t["club"]["name"] == name)
        assert d.team_stats[side]["rank"] == rank
        assert d.team_stats[side]["standings_round"] == 7
    assert d.attendance == 1666
    assert {(l.side, l.name, l.value) for l in d.leaders} == {
        ("home", "MINTZ, JUDAH", 23), ("away", "MOON, XAVIER", 19)}


def test_eurocup_jerusalem_sponsored_name_resolves_via_taxonomy(make_provider):
    data = payload("v2_games_U2026.json")
    jerusalem = next(t["club"] for t in payload("v3_standings_U2026_round7.json")["teams"]
                     if t["club"]["code"] == "JER")
    data["data"][0]["local"]["club"] = jerusalem
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch(["comp:eurocup"])
    assert out.games[0].home_team_id == "team:hapoel_jlm_bb"


def test_malformed_optional_standings_still_preserve_boxscore(make_provider):
    def handler(request):
        if request.url.path.endswith("basicstandings"):
            return httpx.Response(200, json={"teams": [None, {"club": "bad"}]})
        return reply(request)
    p = make_provider(handler)
    out = p.fetch_details([final_game(p)])
    assert len(out.details) == 1 and not out.errors
    assert "rank" not in out.details[0].team_stats["home"]


def test_full_season_is_not_truncated_at_thesportsdb_cap(make_provider, monkeypatch):
    data = payload("v2_games_E2026.json")
    data["data"] = [dict(data["data"][0], gameCode=n) for n in range(1, 381)]
    monkeypatch.setenv("RESULTS_MAX_GAMES_PER_COMPETITION", "80")
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch(["comp:euroleague"])
    assert len(out.games) == 380
    assert out.fetched_counts == {"comp:euroleague": 380}


def test_bad_rows_are_skipped_and_duplicate_games_deduplicated(make_provider):
    data = payload("v2_games_E2026.json")
    data["data"].extend([None, {}, {"gameCode": 999}, copy.deepcopy(data["data"][0])])
    out = make_provider(lambda r: httpx.Response(200, json=data)).fetch(["comp:euroleague"])
    assert not out.errors
    assert len(out.games) == 3


def test_unsupported_competition_is_an_error_without_request(make_provider):
    def handler(request):
        pytest.fail("unsupported competition must not make a request")
    out = make_provider(handler).fetch(["comp:nba"])
    assert "comp:nba" in out.errors


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_unavailable_without_retry_and_other_competition_survives(
        make_provider, status):
    sent = []
    def handler(request):
        sent.append(request)
        if "/competitions/E/" in request.url.path:
            return httpx.Response(status)
        return reply(request)
    out = make_provider(handler).fetch(["comp:euroleague", "comp:eurocup"])
    assert len(sent) == 2
    assert out.errors == {"comp:euroleague": f"source unavailable (HTTP {status})"}
    assert {g.competition_id for g in out.games} == {"comp:eurocup"}


@pytest.mark.parametrize("retry_after,expected", [("90", 90), (None, 60), ("bad", 60)])
def test_scores_429_stops_and_marks_remaining_competitions(make_provider, retry_after, expected):
    sent = []
    def handler(request):
        sent.append(request)
        headers = {"Retry-After": retry_after} if retry_after else {}
        return httpx.Response(429, headers=headers)
    out = make_provider(handler).fetch(["comp:euroleague", "comp:eurocup"])
    assert len(sent) == 1
    assert not out.errors
    assert out.not_checked == ["comp:euroleague", "comp:eurocup"]
    assert out.retry_after_seconds == expected


@pytest.mark.parametrize("failure", ["timeout", "503", "json"])
def test_transient_failures_retry_with_a_bound_and_recover(make_provider, failure):
    sent = []
    def handler(request):
        sent.append(request)
        if len(sent) < 3:
            if failure == "timeout":
                raise httpx.ReadTimeout("timed out", request=request)
            if failure == "json":
                return httpx.Response(200, text="not json")
            return httpx.Response(503)
        return reply(request)
    out = make_provider(handler).fetch(["comp:euroleague"])
    assert len(sent) == 3
    assert not out.errors and len(out.games) == 3


def test_exhausted_retries_report_safe_error_and_continue(make_provider):
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(503) if "/competitions/E/" in request.url.path else reply(request)
    out = make_provider(handler).fetch(["comp:euroleague", "comp:eurocup"])
    assert len(sent) == 4
    assert "comp:euroleague" in out.errors
    assert "https://" not in out.errors["comp:euroleague"]
    assert len(out.games) == 2


def test_saved_boxscore_tied_leaders_minutes_stats_attendance_and_referees(make_provider):
    p = make_provider()
    game = final_game(p)
    out = p.fetch_details([game])
    assert not out.errors and len(out.details) == 1
    detail = out.details[0]
    assert detail.game_id == game.id
    assert {(l.side, l.name, l.value) for l in detail.leaders} == {
        ("home", "CLARK III, JIMMY", 14), ("home", "COLSON, BONZIE", 14),
        ("away", "MICIC, VASILIJE", 14)}
    assert all(l.stat == "points" and l.name_he is None for l in detail.leaders)
    assert len(detail.players) == 24
    clark = next(p for p in detail.players if p.name == "CLARK III, JIMMY")
    assert clark.source_player_id == "P013699"
    assert clark.minutes == pytest.approx(29 + 1 / 60)
    assert clark.stats["points"] == 14 and clark.stats["Assistances"] == 4
    assert next(p for p in detail.players if p.name == "BACOT JR., ARMANDO").minutes is None
    assert detail.attendance == 1212
    assert detail.venue == "SPYROS KYPRIANOU ATHLETIC CENTER"
    assert detail.team_stats["home"]["Points"] == 80
    assert detail.team_stats["away"]["TotalRebounds"] == 37
    assert detail.team_stats["home"]["quarters"]["Quarter4"] == 24
    assert detail.team_stats["home"]["referees"] == (
        "PERUGA, CARLOS, BELOSEVIC, ILIJA, ALIAGA, JORDI")
    assert detail.team_stats["home"]["rank"] == 17
    assert detail.team_stats["away"]["rank"] == 10
    assert detail.team_stats["home"]["standings_round"] == 11


def test_reversed_boxscore_teams_still_match_home_and_away(make_provider):
    def handler(request):
        if request.url.path.endswith("Boxscore"):
            data = payload("live_boxscore_E2026_103.json")
            data["Stats"].reverse()
            return httpx.Response(200, json=data)
        return reply(request)
    p = make_provider(handler)
    detail = p.fetch_details([final_game(p)]).details[0]
    assert detail.team_stats["home"]["Points"] == 80
    assert {(l.name, l.side) for l in detail.leaders if l.side == "away"} == {
        ("MICIC, VASILIJE", "away")}


def test_details_can_be_fetched_by_a_fresh_provider_and_old_season(make_provider):
    game = final_game(make_provider()).model_copy(update={"external_id": "E2025_103"})
    sent = []
    def handler(request):
        sent.append(request)
        return reply(request)
    out = make_provider(handler).fetch_details([game])
    assert not out.errors and len(out.details) == 1
    box = next(r for r in sent if r.url.path.endswith("Boxscore"))
    assert dict(box.url.params) == {"gamecode": "103", "seasoncode": "E2025"}
    assert any("/seasons/E2025/rounds/11/" in r.url.path for r in sent)


def test_standings_once_per_round_and_one_boxscore_per_unique_finished_game(make_provider):
    sent = []
    def handler(request):
        sent.append(request)
        return reply(request)
    p = make_provider(handler)
    g = final_game(p)
    other = g.model_copy(update={"external_id": "E2026_104"})
    out = p.fetch_details([g, g, other])
    p.fetch_details([other])
    assert len(out.details) == 2
    assert sum(r.url.path.endswith("basicstandings") for r in sent) == 1
    assert sum(r.url.path.endswith("Boxscore") for r in sent) == 3


@pytest.mark.parametrize("status", [401, 403, 404, 503])
def test_unavailable_standings_do_not_lose_boxscore_or_repeat_request(make_provider, status):
    sent = []
    def handler(request):
        if request.url.path.endswith("basicstandings"):
            sent.append(request)
            return httpx.Response(status)
        return reply(request)
    p = make_provider(handler)
    g = final_game(p)
    out = p.fetch_details([g, g.model_copy(update={"external_id": "E2026_104"})])
    assert len(out.details) == 2 and not out.errors
    assert "rank" not in out.details[0].team_stats["home"]
    assert len(sent) == (3 if status == 503 else 1)


@pytest.mark.parametrize("status", [401, 403])
def test_boxscore_auth_failure_is_per_game_error(make_provider, status):
    g = final_game(make_provider())
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(status)
    out = make_provider(handler).fetch_details([g])
    assert len(sent) == 1 and not out.details
    assert out.errors == {g.id: f"source unavailable (HTTP {status})"}


@pytest.mark.parametrize("where", ["boxscore", "standings"])
def test_detail_429_preserves_finished_details_and_stops_all_requests(make_provider, where):
    g = final_game(make_provider())
    other = g.model_copy(update={"external_id": "E2026_104"})
    sent = []
    def handler(request):
        sent.append(request)
        limited = (request.url.path.endswith("Boxscore") if where == "boxscore"
                   else request.url.path.endswith("basicstandings"))
        return httpx.Response(429, headers={"Retry-After": "120"}) if limited else reply(request)
    out = make_provider(handler).fetch_details([g, other])
    assert out.retry_after_seconds == 120 and not out.errors
    if where == "boxscore":
        assert len(sent) == 1 and not out.details
        assert out.not_checked == [g.id, other.id]
    else:
        assert len(sent) == 2 and len(out.details) == 1
        assert out.not_checked == [other.id]
        assert "rank" not in out.details[0].team_stats["home"]


@pytest.mark.parametrize("body", [{}, {"Stats": []}, {"Live": True, "Stats": []}])
def test_unpublished_or_live_boxscore_stays_pending(make_provider, body):
    g = final_game(make_provider())
    out = make_provider(lambda r: httpx.Response(200, json=body)).fetch_details([g])
    assert not out.details and not out.errors


def test_malformed_boxscore_isolated_from_next_game(make_provider):
    g = final_game(make_provider())
    other = g.model_copy(update={"external_id": "E2026_104"})
    def handler(request):
        if request.url.path.endswith("Boxscore") and request.url.params["gamecode"] == "103":
            return httpx.Response(200, json={"Stats": "broken"})
        return reply(request)
    out = make_provider(handler).fetch_details([g, other])
    assert g.id in out.errors
    assert [d.game_id for d in out.details] == [other.id]


def test_details_ignore_nonfinal_foreign_and_invalid_identity_games(make_provider):
    g = final_game(make_provider())
    def handler(request):
        pytest.fail("invalid candidate must not make a request")
    out = make_provider(handler).fetch_details([
        g.model_copy(update={"status": "scheduled"}),
        g.model_copy(update={"provider": "fake"}),
        g.model_copy(update={"external_id": "E2026_103?bad=1"}),
        g.model_copy(update={"competition_id": "comp:eurocup"}),
    ])
    assert not out.details


def test_scores_details_standings_and_retries_are_paced_together(make_provider, monkeypatch):
    clock = Clock()
    sent = []
    def handler(request):
        sent.append(clock())
        return httpx.Response(503) if len(sent) == 1 else reply(request)
    p = make_provider(handler, clock=clock)
    monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "2.5")
    p.fetch_details([final_game(p)])
    assert len(sent) == 4
    assert all(b - a >= 2.5 for a, b in zip(sent, sent[1:]))


def test_registered_routing_with_fake_default_and_isolated_429(make_provider, monkeypatch):
    assert "euroleague" in providers.REGISTRY
    p = make_provider()
    monkeypatch.setitem(providers.REGISTRY, "euroleague", lambda: p)
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES",
                       "comp:euroleague=euroleague,comp:eurocup=euroleague")
    router = providers.get_provider()
    out = router.fetch(["comp:euroleague", "comp:eurocup", "comp:nba"])
    assert not out.errors
    assert {g.provider for g in out.games} == {"euroleague", "fake"}
    assert {g.competition_id for g in out.games if g.provider == "euroleague"} == {
        "comp:euroleague", "comp:eurocup"}
    detail = router.fetch_details([g for g in out.games if g.external_id == "E2026_103"])
    assert len(detail.details) == 1
    monkeypatch.setitem(providers.REGISTRY, "euroleague",
                        lambda: make_provider(lambda r: httpx.Response(429)))
    limited = providers.get_provider().fetch(["comp:euroleague", "comp:nba"])
    assert limited.not_checked == ["comp:euroleague"]
    assert limited.provider_retry_after == {"euroleague": 60}
    assert {g.provider for g in limited.games} == {"fake"}


def test_defaults_unchanged_and_detail_capability_registered(make_provider, monkeypatch):
    p = make_provider()
    assert supports_details(p)
    monkeypatch.delenv("RESULTS_PROVIDER", raising=False)
    monkeypatch.delenv("RESULTS_PROVIDER_ROUTES", raising=False)
    assert providers.get_provider().name == "thesportsdb"
    from app.results import settings
    assert settings.detail_enabled() is False
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    assert isinstance(providers.get_provider(), FakeResultsProvider)


@pytest.mark.parametrize("detail_enabled", [False, True])
def test_sync_persists_official_details_and_never_refetches_stored_games(
        make_provider, monkeypatch, detail_enabled):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from app.db.orm_models import Base, GamePlayerLineRow, GameResultRow
    from app.repositories.game_detail_repository import get_details
    from app.results.sync_service import sync_results

    # A separate in-memory database; no app DB or existing corpus is opened.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", str(detail_enabled).lower())
    sent = []
    def handler(request):
        sent.append(request)
        if request.url.path.endswith("/games"):
            data = payload("v2_games_E2026.json")
            data["data"] = [data["data"][0], data["data"][2]]
            return httpx.Response(200, json=data)
        return reply(request)
    try:
        with Session(engine) as session:
            first = sync_results(session, provider=make_provider(handler),
                                 competition_ids=["comp:euroleague"])
            assert first["status"] == "ok"
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 2
            if detail_enabled:
                assert first["detail"]["stored"] == 1
                game = final_game(make_provider())
                stored = get_details(session, [game.id])[game.id]
                assert stored.team_stats["home"]["rank"] == 17
                assert stored.team_stats["away"]["rank"] == 10
                assert stored.attendance == 1212 and len(stored.leaders) == 3
                assert session.scalar(select(func.count()).select_from(GamePlayerLineRow)) == 24
            else:
                assert "detail" not in first
            before = len(sent)
            second = sync_results(session, provider=make_provider(handler),
                                  competition_ids=["comp:euroleague"])
            assert second["status"] == "ok"
            assert len(sent) == before + 1  # only the season; persisted detail is never fetched again
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 2
    finally:
        engine.dispose()
