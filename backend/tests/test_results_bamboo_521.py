"""Bamboo's saved football payloads, with real transports forbidden."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.results import providers


FIXTURES = Path(__file__).parent / "fixtures/results/ligat_haal"
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
COMP = "comp:ligat_haal"


def payload(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def reply(request):
    endpoint = request.url.path.rsplit("/", 1)[-1]
    assert request.url.host == "cdnapi.bamboo-cloud.com"
    assert request.url.params["format"] == "json"
    assert request.url.params["iid"] == "573881b7181f46ae4c8b4567"
    if endpoint == "player":
        pid = json.loads(request.url.params["filter"])["id"]
        assert pid != -1, "-1 is not a person"
        file = FIXTURES / f"player_{pid}.json"
        return httpx.Response(200, json=payload(file.name) if file.exists() else {"data": []})
    if endpoint == "stats":
        assert json.loads(request.url.params["filter"]) == {"gameId": 310793}
        return httpx.Response(200, json=payload("stats_game_310793.json"))
    return httpx.Response(200, json=payload({
        "game": "game_2627.json", "team": "team.json", "standings": "standings.json",
    }[endpoint]))


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def make_provider(monkeypatch):
    from app.results.providers.bamboo import BambooFootballProvider

    monkeypatch.setenv("RESULTS_BAMBOO_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_HTTP_MAX_RETRIES", "2")
    monkeypatch.setenv("RESULTS_MAX_GAMES_PER_COMPETITION", "80")

    def no_network(*args, **kwargs):
        raise AssertionError("real network is forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    clients = []

    def make(handler=reply, *, clock=None):
        clock = clock or Clock()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return BambooFootballProvider(client=client, sleep=clock.sleep, clock=clock,
                                      utcnow=lambda: NOW)

    yield make
    for client in clients:
        client.close()


def final_game(provider):
    return next(g for g in provider.fetch([COMP]).games if g.external_id == "310793")


def test_saved_game_identity_score_hebrew_names_season_round_and_utc(make_provider):
    game = final_game(make_provider())
    assert (game.provider, game.competition_id, game.sport) == ("bamboo", COMP, "football")
    assert (game.season, game.stage, game.status) == ("2026-2027", "10", "final")
    assert game.start_time == "2026-11-06T12:00:00+00:00"
    assert (game.home_team_name, game.away_team_name) == ('מכבי ת"א', 'מכבי פ"ת')
    assert (game.home_team_id, game.away_team_id) == (
        "team:maccabi_tlv_fc", "team:maccabi_petah_tikva_fc")
    assert (game.home_score, game.away_score) == (2, 2)


@pytest.mark.parametrize("source_status,want", [(3, "final"), (2, "live"), (4, "postponed")])
def test_source_status_is_authoritative_including_scoreless_or_zero_draw(
        make_provider, source_status, want):
    def handler(request):
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            row = data["data"]["310793"]
            row.update(status=source_status, homeScore=0, awayScore=0)
            return httpx.Response(200, json=data)
        return reply(request)

    game = final_game(make_provider(handler))
    assert game.status == want
    assert (game.home_score, game.away_score) == ((0, 0) if want != "postponed" else (None, None))


def test_date_range_without_hour_uses_epoch_and_is_scheduled_without_scores(make_provider):
    game = next(g for g in make_provider().fetch([COMP]).games if g.external_id == "310803")
    assert game.status == "scheduled"
    assert game.start_time == "2026-11-27T12:00:00+00:00"
    assert game.home_score is None and game.away_score is None


def test_one_season_request_and_cached_teams_per_instance(make_provider):
    sent = []

    def handler(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        return reply(request)

    p = make_provider(handler)
    first = p.fetch([COMP, COMP, "comp:nba"])
    second = p.fetch([COMP])
    assert len(first.games) == len(second.games) == 9
    assert first.errors == {"comp:nba": "not a Bamboo competition"}
    assert first.fetched_counts == {COMP: 9}
    assert sent.count("game") == 2 and sent.count("team") == 1


def test_all_14_clubs_keep_hebrew_names_and_only_existing_taxonomy_ids(make_provider):
    games = make_provider().fetch([COMP]).games
    clubs = {name: tid for g in games for name, tid in (
        (g.home_team_name, g.home_team_id), (g.away_team_name, g.away_team_id))}
    assert clubs == {
        "מכבי חיפה": "team:maccabi_haifa_fc", 'הפועל ת"א': "team:hapoel_tlv_fc",
        'מכבי ת"א': "team:maccabi_tlv_fc", 'מכבי פ"ת': "team:maccabi_petah_tikva_fc",
        'בית"ר ירושלים': "team:beitar_jlm_fc", 'הפועל ב"ש': "team:hapoel_beer_sheva_fc",
        "הפועל חיפה": "team:hapoel_haifa_fc", 'הפועל ק"ש': None, "בני סכנין": None,
        "מכבי נתניה": "team:maccabi_netanya_fc", 'הפועל ר"ג': None, 'הפועל פ"ת': None,
        "הפועל ירושלים": "team:hapoel_jlm_fc", "עירוני טבריה": None,
    }


def test_unsupported_competition_does_not_request_source(make_provider):
    p = make_provider(lambda r: pytest.fail("unsupported competition sent a request"))
    out = p.fetch(["comp:nba"])
    assert "comp:nba" in out.errors and not out.games


def test_cap_keeps_nearest_upcoming_and_newest_results(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_MAX_GAMES_PER_COMPETITION", "4")
    out = make_provider().fetch([COMP])
    assert len(out.games) == 4
    assert {g.external_id for g in out.games} >= {"310793", "310803"}
    assert sum(g.status == "scheduled" for g in out.games) == 1


@pytest.mark.parametrize("endpoint", ["game", "team"])
def test_scores_429_never_retried_and_reports_retry_after(make_provider, endpoint):
    sent = []

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        sent.append(name)
        return httpx.Response(429, headers={"Retry-After": "123"}) if name == endpoint else reply(request)

    out = make_provider(handler).fetch([COMP])
    assert not out.errors and not out.games
    assert out.not_checked == [COMP] and out.retry_after_seconds == 123
    assert sent.count(endpoint) == 1 and sent[-1] == endpoint


@pytest.mark.parametrize("kind", ["5xx", "timeout"])
def test_transient_failure_retried_then_success(make_provider, kind):
    attempts = []

    def handler(request):
        if request.url.path.endswith("/game"):
            attempts.append(request)
            if len(attempts) < 3:
                if kind == "timeout":
                    raise httpx.ReadTimeout("private request URL", request=request)
                return httpx.Response(503)
        return reply(request)

    out = make_provider(handler).fetch([COMP])
    assert not out.errors and len(out.games) == 9
    assert len(attempts) == 3


@pytest.mark.parametrize("code,attempts", [(401, 1), (403, 1), (404, 1), (503, 3)])
def test_failed_source_stops_at_retry_bound_and_uses_safe_error(make_provider, code, attempts):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(code)

    out = make_provider(handler).fetch([COMP])
    assert len(sent) == attempts
    assert COMP in out.errors and "://" not in out.errors[COMP]
    assert not out.games


def test_malformed_season_container_is_error(make_provider):
    out = make_provider(lambda r: httpx.Response(200, json={"data": "broken"})).fetch([COMP])
    assert COMP in out.errors and not out.games


def test_bad_season_row_does_not_lose_other_games(make_provider):
    def handler(request):
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            data["data"]["310793"]["date"] = {"sec": "bad"}
            return httpx.Response(200, json=data)
        return reply(request)

    out = make_provider(handler).fetch([COMP])
    assert len(out.games) == 8 and not out.errors


@pytest.mark.parametrize("field,value", [("status", {}), ("date", []), ("homeTeamId", None)])
def test_malformed_field_isolated_to_one_season_row(make_provider, field, value):
    def handler(request):
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            data["data"]["310793"][field] = value
            return httpx.Response(200, json=data)
        return reply(request)

    out = make_provider(handler).fetch([COMP])
    assert len(out.games) == 8 and not out.errors


def test_auth_error_names_http_status_without_url_or_response_text(make_provider):
    out = make_provider(lambda r: httpx.Response(403, text="private source URL")).fetch([COMP])
    assert out.errors == {COMP: "source unavailable (HTTP 403)"}


def test_named_scorers_assist_minutes_xg_and_side_from_stats_key(make_provider):
    def handler(request):
        response = reply(request)
        if request.url.path.endswith("/player") and json.loads(request.url.params["filter"])["id"] == 13251:
            data = response.json()
            data["data"]["13251"]["teamId"] = {"id": 4536}  # a later transfer
            return httpx.Response(200, json=data)
        return response

    p = make_provider(handler)
    out = p.fetch_details([final_game(p)])
    assert not out.errors and len(out.details) == 1
    detail = out.details[0]
    lines = {line.source_player_id: line for line in detail.players if line.source_player_id}
    assert (lines["13251"].side, lines["13251"].name_he) == ("away", "איתן טיבי")
    assert (lines["331446"].side, lines["331446"].name_he) == ("away", "גיא חדידה")
    sokler = lines["565113"]
    assert (sokler.name, sokler.name_he, sokler.minutes) == ("Ester Sokler", "אסטר סוקלר", 34)
    assert sokler.stats["goals"] == 1 and sokler.stats["xg"] == pytest.approx(0.7433)
    assert lines["246438"].name_he == "קייל ספנס"
    assert lines["246438"].stats["assists"] == 1
    assert lines["286044"].stats["yellow_cards"] == 1
    assert lines["286044"].stats["own_goals"] == 0
    assert all("goal_minute" not in line.stats for line in detail.players)
    assert detail.venue == "בלומפילד"
    assert (detail.team_stats["home"]["rank"], detail.team_stats["away"]["rank"]) == (2, 9)


def test_all_scorers_are_leaders_even_when_one_scores_more(make_provider):
    def handler(request):
        if request.url.path.endswith("/stats"):
            data = payload("stats_game_310793.json")
            data["data"]["902_26/27_RegularSeason_10_310793_15006_13251"]["Goal"] = 2
            return httpx.Response(200, json=data)
        return reply(request)

    p = make_provider(handler)
    detail = p.fetch_details([final_game(p)]).details[0]
    assert {(l.name_he, l.value) for l in detail.leaders if l.side == "away" and l.name_he} == {
        ("איתן טיבי", 2), ("גיא חדידה", 1)}


def test_minus_one_is_team_totals_without_duplicate_goals_cards_or_xg(make_provider):
    p = make_provider()
    detail = p.fetch_details([final_game(p)]).details[0]
    assert sum(l.value for l in detail.leaders if l.side == "home") == 2
    assert sum(l.value for l in detail.leaders if l.side == "away") == 2
    assert len(detail.leaders) == 4
    assert {(l.name_he, l.side) for l in detail.leaders} == {
        ("אסטר סוקלר", "home"), ("שגיב יחזקאל", "home"),
        ("איתן טיבי", "away"), ("גיא חדידה", "away"),
    }
    assert detail.team_stats["home"]["goals"] == 2
    assert detail.team_stats["home"]["yellow_cards"] == 2
    assert detail.team_stats["home"]["xg"] == pytest.approx(2.9229)
    assert detail.team_stats["away"]["xg"] == pytest.approx(1.9271)
    assert not any(l.source_player_id == "-1" for l in detail.players)


def test_unnamed_goal_gap_is_preserved_and_never_calls_player_minus_one(make_provider):
    def handler(request):
        if request.url.path.endswith("/stats"):
            data = payload("stats_game_310793.json")
            del data["data"]["902_26/27_RegularSeason_10_310793_4536_286044"]
            return httpx.Response(200, json=data)
        return reply(request)

    p = make_provider(handler)
    detail = p.fetch_details([final_game(p)]).details[0]
    unnamed = next(l for l in detail.leaders if l.side == "home" and l.name is None)
    assert unnamed.name_he is None and unnamed.source_player_id is None and unnamed.value == 1
    assert sum(l.value for l in detail.leaders if l.side == "home") == 2
    line = next(l for l in detail.players if l.side == "home" and l.source_player_id is None)
    assert line.stats["goals"] == 1 and line.stats["yellow_cards"] == 1


def test_red_cards_use_team_total_once_and_keep_player_cards(make_provider):
    def handler(request):
        if request.url.path.endswith("/stats"):
            data = payload("stats_game_310793.json")
            data["data"]["902_26/27_RegularSeason_10_310793_15006_13251"]["RedCard"] = 1
            data["data"]["902_26/27_RegularSeason_10_310793_15006_-1"]["RedCard"] = 1
            return httpx.Response(200, json=data)
        return reply(request)

    p = make_provider(handler)
    detail = p.fetch_details([final_game(p)]).details[0]
    assert detail.team_stats["away"]["red_cards"] == 1
    assert detail.team_stats["home"]["red_cards"] == 0
    tibi = next(l for l in detail.players if l.source_player_id == "13251")
    assert tibi.stats["red_cards"] == 1


def test_player_failure_keeps_unnamed_line_and_stores_detail(make_provider):
    def handler(request):
        if request.url.path.endswith("/player"):
            return httpx.Response(503)
        return reply(request)

    p = make_provider(handler)
    out = p.fetch_details([final_game(p)])
    assert not out.errors and len(out.details) == 1
    tibi = next(l for l in out.details[0].players if l.source_player_id == "13251")
    assert tibi.name is None and tibi.name_he is None and tibi.stats["goals"] == 1


def test_names_and_standings_cached_including_missing_names(make_provider):
    sent = []

    def handler(request):
        sent.append(request)
        return reply(request)

    p = make_provider(handler)
    game = final_game(p)
    p.fetch_details([game, game])
    before = len(sent)
    p.fetch_details([game])
    assert len(sent) == before + 1  # stats only; stored detail is the sync stage's cache
    assert sum(r.url.path.endswith("/standings") for r in sent) == 1
    ids = [json.loads(r.url.params["filter"])["id"] for r in sent if r.url.path.endswith("/player")]
    assert len(ids) == len(set(ids)) and -1 not in ids


@pytest.mark.parametrize("body", [{}, {"data": "broken"}, {"data": {"bad_key": {}}}])
def test_malformed_stats_is_per_game_error(make_provider, body):
    p = make_provider()
    game = final_game(p)
    bad = make_provider(lambda r: httpx.Response(200, json=body) if r.url.path.endswith("/stats") else reply(r))
    out = bad.fetch_details([game])
    assert game.id in out.errors and not out.details


def test_one_malformed_game_does_not_lose_next_game_detail(make_provider):
    game = final_game(make_provider())
    other = game.model_copy(update={"external_id": "310794"})

    def handler(request):
        if request.url.path.endswith("/stats"):
            gid = json.loads(request.url.params["filter"])["gameId"]
            if gid == 310793:
                return httpx.Response(200, json={"data": "broken"})
            data = payload("stats_game_310793.json")
            data["data"] = {k.replace("_310793_", "_310794_"): v for k, v in data["data"].items()}
            return httpx.Response(200, json=data)
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            data["data"]["310794"] = {**data["data"]["310793"], "id": 310794}
            return httpx.Response(200, json=data)
        return reply(request)

    out = make_provider(handler).fetch_details([game, other])
    assert set(out.errors) == {game.id}
    assert [d.game_id for d in out.details] == [other.id]


def test_malformed_game_metadata_becomes_per_game_error(make_provider):
    game = final_game(make_provider())

    def handler(request):
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            del data["data"]["310793"]["homeTeamId"]
            return httpx.Response(200, json=data)
        return reply(request)

    out = make_provider(handler).fetch_details([game])
    assert set(out.errors) == {game.id} and not out.details


@pytest.mark.parametrize("body", [{"data": {}}, {"data": []}])
def test_empty_stats_stay_pending(make_provider, body):
    game = final_game(make_provider())
    out = make_provider(lambda r: httpx.Response(200, json=body)).fetch_details([game])
    assert not out.details and not out.errors


@pytest.mark.parametrize("status", [2, 4])
def test_fresh_detail_provider_does_not_cache_game_no_longer_final(make_provider, status):
    game = final_game(make_provider())

    def handler(request):
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            data["data"]["310793"]["status"] = status
            return httpx.Response(200, json=data)
        return reply(request)

    out = make_provider(handler).fetch_details([game])
    assert not out.details and not out.errors


@pytest.mark.parametrize("body", [{"data": "broken"}, {"data": {}}, None])
def test_optional_standings_failure_preserves_detail_and_is_cached(make_provider, body):
    sent = []

    def handler(request):
        if request.url.path.endswith("/standings"):
            sent.append(request)
            return httpx.Response(403) if body is None else httpx.Response(200, json=body)
        return reply(request)

    p = make_provider(handler)
    game = final_game(p)
    first = p.fetch_details([game])
    second = p.fetch_details([game])
    assert len(first.details) == len(second.details) == 1
    assert not first.errors and "rank" not in first.details[0].team_stats["home"]
    assert len(sent) == 1


def test_foreign_nonfinal_or_invalid_games_send_no_requests(make_provider):
    game = final_game(make_provider())
    p = make_provider(lambda r: pytest.fail("invalid game sent a request"))
    bad = game.model_copy(update={"external_id": "310793?url=private"})
    out = p.fetch_details([
        game.model_copy(update={"status": "scheduled"}),
        game.model_copy(update={"provider": "fake"}), bad,
    ])
    assert not out.details and set(out.errors) == {bad.id}


@pytest.mark.parametrize("endpoint", ["stats", "player", "standings"])
def test_detail_429_stops_requests_and_propagates_retry_after(make_provider, endpoint):
    game = final_game(make_provider())
    other = game.model_copy(update={"external_id": "310794"})
    sent = []

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        sent.append(name)
        return httpx.Response(429, headers={"Retry-After": "90"}) if name == endpoint else reply(request)

    out = make_provider(handler).fetch_details([game, other])
    assert out.retry_after_seconds == 90 and not out.errors
    assert sent.count(endpoint) == 1 and sent[-1] == endpoint
    if endpoint == "standings":
        assert len(out.details) == 1 and out.not_checked == [other.id]
    else:
        assert not out.details and out.not_checked == [game.id, other.id]


def test_scores_details_names_standings_and_retries_share_pacing(make_provider, monkeypatch):
    clock = Clock()
    sent = []

    def handler(request):
        sent.append(clock())
        return httpx.Response(503) if len(sent) == 1 else reply(request)

    p = make_provider(handler, clock=clock)
    monkeypatch.delenv("RESULTS_BAMBOO_MIN_INTERVAL_SECONDS")  # default 2 s
    p.fetch_details([final_game(p)])
    assert len(sent) > 5
    assert all(b - a >= 2 for a, b in zip(sent, sent[1:]))


def test_routing_uses_bamboo_only_for_ligat_haal_with_fake_default(make_provider, monkeypatch):
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ligat_haal=bamboo")
    assert providers.configured_routes() == {COMP: "bamboo"}
    monkeypatch.setitem(providers.REGISTRY, "bamboo", lambda: make_provider())
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ligat_haal=bamboo")
    router = providers.get_provider()
    out = router.fetch([COMP, "comp:nba"])
    assert not out.errors
    assert {g.provider for g in out.games if g.competition_id == COMP} == {"bamboo"}
    assert {g.provider for g in out.games if g.competition_id == "comp:nba"} == {"fake"}
    game = next(g for g in out.games if g.external_id == "310793")
    assert len(router.fetch_details([game]).details) == 1


def test_registered_provider_owns_client_timeout_and_user_agent(make_provider, monkeypatch):
    original_client = httpx.Client
    clients = []
    sent = []

    def handler(request):
        sent.append(request)
        return reply(request)

    def client(**kwargs):
        instance = original_client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(instance)
        return instance

    monkeypatch.setattr(httpx, "Client", client)
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ligat_haal=bamboo")
    monkeypatch.setenv("RESULTS_HTTP_TIMEOUT_SECONDS", "9")
    router = providers.get_provider()  # real registry constructor
    out = router.fetch([COMP])
    game = next(g for g in out.games if g.external_id == "310793")
    assert len(router.fetch_details([game]).details) == 1
    assert len(clients) == 2 and all(c.is_closed for c in clients)
    assert all(r.headers["User-Agent"] == "signal-sports-results/1.0" for r in sent)
    assert all(r.extensions["timeout"]["read"] == 9 for r in sent)


def test_routed_bamboo_rate_limit_leaves_fake_default_working(make_provider, monkeypatch):
    monkeypatch.setitem(providers.REGISTRY, "bamboo", lambda: make_provider(
        lambda r: httpx.Response(429, headers={"Retry-After": "120"})))
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ligat_haal=bamboo")
    out = providers.get_provider().fetch([COMP, "comp:nba"])
    assert out.not_checked == [COMP] and out.provider_retry_after == {"bamboo": 120}
    assert {g.provider for g in out.games} == {"fake"}


@pytest.mark.parametrize("enabled", [False, True])
def test_full_sync_isolated_db_persists_detail_and_never_refetches_it(
        make_provider, monkeypatch, enabled):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from app.db.orm_models import Base, GamePlayerLineRow, GameResultRow
    from app.repositories.game_detail_repository import get_details
    from app.results.sync_service import sync_results

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", str(enabled).lower())
    sent = []

    def handler(request):
        sent.append(request)
        if request.url.path.endswith("/game"):
            data = payload("game_2627.json")
            data["data"] = {k: v for k, v in data["data"].items() if k in {"310793", "310803"}}
            return httpx.Response(200, json=data)
        return reply(request)

    monkeypatch.setitem(providers.REGISTRY, "bamboo", lambda: make_provider(handler))
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ligat_haal=bamboo")
    try:
        with Session(engine) as session:
            first = sync_results(session, provider=providers.get_provider(), competition_ids=[COMP])
            assert first["status"] == "ok"
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 2
            if enabled:
                assert first["detail"]["stored"] == 1
                game = final_game(make_provider())
                detail = get_details(session, [game.id])[game.id]
                assert detail.team_stats["home"]["rank"] == 2
                assert any(l.name_he == "איתן טיבי" and l.side == "away" for l in detail.leaders)
                assert session.scalar(select(func.count()).select_from(GamePlayerLineRow)) > 0
            else:
                assert "detail" not in first
            before = len(sent)
            second = sync_results(session, provider=providers.get_provider(), competition_ids=[COMP])
            assert second["status"] == "ok"
            assert all(r.url.path.endswith(("/game", "/team")) for r in sent[before:])
            assert len(sent) == before + 2  # fresh instance, season + teams only
            assert session.scalar(select(func.count()).select_from(GameResultRow)) == 2
    finally:
        engine.dispose()
