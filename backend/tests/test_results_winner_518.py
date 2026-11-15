"""Ligat Winner results provider (issue #518).

Scores come from the league's own season game list (basket.co.il); per-game detail
from Segev Stats' box score. Payloads are real ones saved on 2026-11-15 (trimmed
season list, two full games), so no test touches the network.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.db.database import SessionLocal
from app.db.orm_models import (
    GameDetailRow, GamePlayerLineRow, GameResultRow, ResultsSyncLeaseRow, ResultsSyncStateRow,
)
from app.results import providers as registry
from app.results import status as st
from app.results.providers import get_provider
from app.results.providers.fake import FAKE_GAMES, FakeResultsProvider
from app.results.providers.routing import RoutingProvider
from app.results.providers.winner import CLUB_IDS, WinnerProvider, normalize_game
from app.results.sync_service import sync_results
from app.taxonomy.entities import _ALL_ENTITIES

FIX = Path(__file__).parent / "fixtures" / "results" / "winner"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


SEASON = _load("ws_games_2027_sample.json")
ROWS = {g["ExternalID"]: g for g in SEASON["games"] if g["ExternalID"] != "0"}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


def _provider(handler, clock=None):
    clock = clock or _Clock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WinnerProvider(client=client, sleep=clock.sleep, clock=clock, utcnow=lambda: NOW)


def _is_segev(request):
    return "segevstats" in request.url.host


def _segev(request):
    """Serve the saved Segev payloads for games 440 and 462."""
    gid = request.url.params["game_id"]
    suffix = {"getBoxScore": "boxscore", "getGameInfo": "gameinfo"}[request.url.params["method"]]
    path = FIX / f"segev_{gid}_{suffix}.json"
    if not path.exists():
        return httpx.Response(404)
    return httpx.Response(200, content=path.read_bytes())


def _handler(requests=None, season=SEASON):
    def handle(request):
        if requests is not None:
            requests.append(request)
        if not _is_segev(request):
            return httpx.Response(200, json=season)
        return _segev(request)
    return handle


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setenv("RESULTS_WINNER_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")


def _game(ext, comp="comp:ibl"):
    return normalize_game(ROWS[ext], comp, NOW)


# ── Season-list normalization ─────────────────────────────────────────────────

class TestNormalize:
    def test_league_game_home_away_score_round_and_identity(self):
        g = _game("440")
        assert g.provider == "winner"
        assert g.external_id == "26673"          # the league's id, stable before Segev has one
        assert g.competition_id == "comp:ibl"
        assert g.sport == "basketball"
        assert (g.home_score, g.away_score) == (87, 105)
        assert g.status == st.FINAL
        assert g.stage == "4"
        assert g.season == "2026-2027"
        assert g.home_team_id == "team:maccabi_tlv_bb"
        assert g.away_team_id == "team:hapoel_tlv_bb"
        assert g.home_team_name.startswith("מכבי")

    def test_israel_local_time_becomes_utc(self):
        # 01/11/2026 20:55 Israel (UTC+2 after the 25 Oct change) = 18:55Z
        assert _game("440").start_time == "2026-11-01T18:55:00+00:00"
        # 08/09/2026 19:00 Israel (summer time, UTC+3) = 16:00Z
        assert _game("396", "comp:winner_cup").start_time == "2026-09-08T16:00:00+00:00"

    def test_html_entities_are_decoded_in_names(self):
        raw = {**ROWS["404"], "team2_name": "הפועל ב&quot;ש"}
        g = normalize_game(raw, "comp:winner_cup", NOW)
        assert g.away_team_name == 'הפועל ב"ש'
        assert "&quot;" not in g.home_team_name

    def test_future_game_is_scheduled_without_a_score(self):
        g = _game("452")
        assert g.status == st.SCHEDULED
        assert (g.home_score, g.away_score) == (None, None)

    def test_unscored_game_without_a_time_is_kept_as_scheduled(self):
        raw = SEASON["games"][-1]
        assert raw["TimeOfGame"] == ""
        g = normalize_game(raw, "comp:ibl", NOW)
        assert g.status == st.SCHEDULED and g.start_time is not None
        assert g.home_score is None

    def test_scores_that_are_strings_become_ints(self):
        raw = {**ROWS["440"], "score_team1": " 87 ", "score_team2": "105"}
        g = normalize_game(raw, "comp:ibl", NOW)
        assert (g.home_score, g.away_score) == (87, 105)

    def test_a_half_readable_score_is_no_score(self):
        raw = {**ROWS["440"], "score_team1": "87", "score_team2": "x"}
        g = normalize_game(raw, "comp:ibl", NOW)
        assert (g.home_score, g.away_score) == (None, None) and g.status != st.FINAL

    def test_a_game_missing_identity_is_skipped(self):
        assert normalize_game({**ROWS["440"], "game_id": ""}, "comp:ibl", NOW) is None
        assert normalize_game({**ROWS["440"], "team1_name": ""}, "comp:ibl", NOW) is None
        assert normalize_game({**ROWS["440"], "game_date_txt": "garbage"}, "comp:ibl", NOW) is None

    def test_unresolved_team_keeps_the_provider_name(self):
        raw = {**ROWS["440"], "team1_name": "קבוצה לא ידועה", "team1_name_eng": "Unknown Club"}
        g = normalize_game(raw, "comp:ibl", NOW)
        assert g.home_team_id is None and g.home_team_name == "קבוצה לא ידועה"

    def test_every_mapped_club_exists_in_the_taxonomy(self):
        known = {e.id for e in _ALL_ENTITIES}
        assert set(CLUB_IDS.values()) <= known

    def test_the_full_season_list_resolves_the_clubs_the_taxonomy_has(self):
        """Maccabi/Hapoel Tel Aviv and Jerusalem etc. carry sponsor names in the
        list; they must still resolve (relevance depends on the team id)."""
        for eng, heb in {"Maccabi Rapyd Tel Aviv": "מכבי Rapyd תל אביב",
                         "Hapoel IBI Tel Aviv": "הפועל IBI תל אביב",
                         "Hapoel Midtown Jerusalem": "הפועל מידטאון י-ם"}.items():
            raw = {**ROWS["440"], "team1_name": heb, "team1_name_eng": eng}
            assert normalize_game(raw, "comp:ibl", NOW).home_team_id is not None


class TestFetch:
    def test_one_request_and_games_split_by_competition(self):
        seen = []
        out = _provider(_handler(seen)).fetch(["comp:ibl", "comp:winner_cup", "comp:il_super_cup"])
        assert len(seen) == 1
        assert "cYear=2027" in str(seen[0].url)
        comps = ("comp:ibl", "comp:winner_cup", "comp:il_super_cup")
        by = {c: [g for g in out.games if g.competition_id == c] for c in comps}
        assert len(by["comp:ibl"]) == 4 and len(by["comp:winner_cup"]) == 2
        assert len(by["comp:il_super_cup"]) == 1
        assert out.fetched_counts == {c: len(v) for c, v in by.items()}
        assert out.errors == {}

    def test_only_requested_competitions_are_returned(self):
        out = _provider(_handler()).fetch(["comp:winner_cup"])
        assert {g.competition_id for g in out.games} == {"comp:winner_cup"}

    def test_unsupported_competition_is_an_error_not_a_request(self):
        seen = []
        out = _provider(_handler(seen)).fetch(["comp:nba"])
        assert seen == [] and "comp:nba" in out.errors

    def test_429_marks_everything_not_checked(self):
        p = _provider(lambda r: httpx.Response(429, headers={"Retry-After": "30"}))
        out = p.fetch(["comp:ibl", "comp:winner_cup"])
        assert out.games == [] and out.errors == {}
        assert out.not_checked == ["comp:ibl", "comp:winner_cup"]
        assert out.retry_after_seconds == 30

    def test_malformed_payload_is_a_per_competition_error(self):
        out = _provider(lambda r: httpx.Response(200, json={"nope": 1})).fetch(["comp:ibl"])
        assert out.games == [] and "comp:ibl" in out.errors

    def test_non_json_body_is_an_error(self):
        out = _provider(lambda r: httpx.Response(200, text="<html>")).fetch(["comp:ibl"])
        assert "comp:ibl" in out.errors

    def test_a_bad_row_does_not_lose_the_others(self):
        season = {"games": [{"game_id": "1"}, "junk", *SEASON["games"]]}
        out = _provider(_handler(season=season)).fetch(["comp:ibl"])
        assert len(out.games) == 4

    def test_per_competition_cap_keeps_upcoming_and_newest_finals(self, monkeypatch):
        monkeypatch.setenv("RESULTS_MAX_GAMES_PER_COMPETITION", "2")
        out = _provider(_handler()).fetch(["comp:ibl"])
        assert len(out.games) == 2
        assert {g.status for g in out.games} == {st.FINAL, st.SCHEDULED}
        finals = [g for g in out.games if g.status == st.FINAL]
        assert all(g.external_id == "26700" for g in finals)  # newest of the two finals


# ── Detail ────────────────────────────────────────────────────────────────────

class TestDetail:
    def _detail(self, ext="440", comp="comp:ibl"):
        game = _game(ext, comp)
        out = _provider(_handler()).fetch_details([game])
        assert out.errors == {} and out.not_checked == []
        (detail,) = out.details
        return game, detail

    def test_two_segev_requests_and_one_list_request_per_run(self):
        seen = []
        _provider(_handler(seen)).fetch_details([_game("440")])
        assert sum(1 for r in seen if not _is_segev(r)) == 1
        methods = sorted(r.url.params["method"] for r in seen if _is_segev(r))
        assert methods == ["getBoxScore", "getGameInfo"]
        assert all(r.url.params["game_id"] == "440" for r in seen if _is_segev(r))

    def test_identity_matches_the_game(self):
        game, detail = self._detail()
        assert detail.game_id == game.id

    def test_top_scorer_per_team_with_hebrew_names(self):
        _, detail = self._detail()
        top = {l.side: l for l in detail.leaders if l.stat == "points"}
        assert (top["home"].value, top["home"].name) == (18, "Yam Madar")
        assert (top["away"].value, top["away"].name) == (31, "Vasilije Micic")
        assert top["home"].name_he and top["away"].name_he
        assert top["home"].name_he.startswith("ים")

    def test_player_lines_are_cast_to_ints_and_skip_dnp(self):
        _, detail = self._detail()
        assert detail.players
        for line in detail.players:
            assert line.side in ("home", "away") and line.source_player_id
            assert type(line.stats["points"]) is int
            assert type(line.stats["rebounds"]) is int
            assert line.minutes is None or line.minutes > 0
        assert sum(l.stats["points"] for l in detail.players if l.side == "home") == 87
        assert sum(l.stats["points"] for l in detail.players if l.side == "away") == 105
        madar = next(l for l in detail.players if l.name == "Yam Madar")
        assert type(madar.minutes) is float and 0 < madar.minutes < 48

    def test_team_stats_venue_attendance_and_quarters(self):
        _, detail = self._detail()
        assert detail.team_stats["home"]["pts_in_the_paint"] == 36
        assert detail.team_stats["away"]["bench_points"] == 49
        assert detail.team_stats["home"]["quarter_scores"] == [22, 25, 16, 24]
        assert detail.team_stats["away"]["quarter_scores"] == [26, 33, 24, 22]
        assert detail.attendance == 8314
        assert detail.venue == 'היכל מנורה מבטחים, ת"א'

    def test_second_game_also_resolves(self):
        _, detail = self._detail("462")
        assert {l.side for l in detail.leaders} == {"home", "away"}

    def test_requests_are_paced(self, monkeypatch):
        monkeypatch.setenv("RESULTS_WINNER_MIN_INTERVAL_SECONDS", "2")
        clock, times = _Clock(), []

        def handle(request):
            times.append(clock.now)
            return _handler()(request)

        _provider(handle, clock).fetch_details([_game("440"), _game("462")])
        assert len(times) == 5
        assert min(b - a for a, b in zip(times, times[1:])) >= 2

    def test_429_on_a_segev_call_stops_and_marks_the_rest_not_checked(self):
        def handle(request):
            if _is_segev(request) and request.url.params["game_id"] == "462":
                return httpx.Response(429, headers={"Retry-After": "45"})
            return _handler()(request)

        first, second = _game("440"), _game("462")
        out = _provider(handle).fetch_details([first, second])
        assert [d.game_id for d in out.details] == [first.id]
        assert out.not_checked == [second.id]
        assert out.retry_after_seconds == 45 and out.errors == {}

    def test_429_on_the_list_request_checks_nothing(self):
        games = [_game("440"), _game("462")]
        out = _provider(lambda r: httpx.Response(429)).fetch_details(games)
        assert out.details == [] and sorted(out.not_checked) == sorted(g.id for g in games)
        assert out.retry_after_seconds == 60

    def test_malformed_box_score_is_a_per_game_error_and_others_continue(self):
        def handle(request):
            if _is_segev(request) and request.url.params["game_id"] == "440":
                return httpx.Response(200, json={"result": {"boxscore": "broken"}})
            return _handler()(request)

        bad, good = _game("440"), _game("462")
        out = _provider(handle).fetch_details([bad, good])
        assert [d.game_id for d in out.details] == [good.id]
        assert bad.id in out.errors
        assert "http" not in out.errors[bad.id].lower()   # stored and served: no URLs

    def test_http_error_is_a_per_game_error(self):
        def handle(request):
            if _is_segev(request):
                return httpx.Response(500)
            return _handler()(request)

        game = _game("440")
        out = _provider(handle).fetch_details([game])
        assert out.details == [] and game.id in out.errors

    def test_unfinished_box_score_is_not_a_detail_and_not_an_error(self):
        payload = _load("segev_440_boxscore.json")
        payload["result"]["boxscore"]["gameInfo"]["gameFinished"] = False

        def handle(request):
            if _is_segev(request) and request.url.params["method"] == "getBoxScore":
                return httpx.Response(200, json=payload)
            return _handler()(request)

        out = _provider(handle).fetch_details([_game("440")])
        assert out.details == [] and out.errors == {} and out.not_checked == []

    def test_game_not_in_the_season_list_has_no_detail(self):
        gone = _game("440").model_copy(update={"external_id": "999999"})
        out = _provider(_handler()).fetch_details([gone])
        assert out.details == [] and out.errors == {}

    def test_game_info_failure_is_an_error_so_names_are_retried(self):
        def handle(request):
            if _is_segev(request) and request.url.params["method"] == "getGameInfo":
                return httpx.Response(200, json={"result": {}})
            return _handler()(request)

        game = _game("440")
        out = _provider(handle).fetch_details([game])
        assert out.details == [] and game.id in out.errors


# ── Registry and routing ──────────────────────────────────────────────────────

class TestRouting:
    def test_registered_as_winner(self):
        assert "winner" in registry.REGISTRY
        assert registry.REGISTRY["winner"]().name == "winner"

    def test_route_config_builds_a_router_with_a_detail_capable_winner(self, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER", "fake")
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES",
                           "comp:ibl=winner,comp:winner_cup=winner,comp:il_super_cup=winner")
        router = get_provider()
        assert isinstance(router, RoutingProvider)
        assert router.provider_for("comp:winner_cup") == "winner"
        assert "winner" in router.detail_provider_names()

    def test_ibl_goes_to_winner_and_the_rest_to_the_default(self):
        default = FakeResultsProvider([g for g in FAKE_GAMES if g.competition_id == "comp:nba"])
        default.name = "alpha"
        router = RoutingProvider({"alpha": default, "winner": _provider(_handler())},
                                 {"comp:ibl": "winner", "comp:winner_cup": "winner"}, "alpha")
        out = router.fetch(["comp:nba", "comp:ibl", "comp:winner_cup"])
        assert {g.competition_id for g in out.games if g.provider == "winner"} == {
            "comp:ibl", "comp:winner_cup"}
        assert any(g.competition_id == "comp:nba" and g.provider != "winner" for g in out.games)

    def test_router_asks_winner_only_for_its_own_games_details(self):
        default = FakeResultsProvider([])
        default.name = "alpha"
        router = RoutingProvider({"alpha": default, "winner": _provider(_handler())},
                                 {"comp:ibl": "winner"}, "alpha")
        out = router.fetch_details([_game("440")])
        assert [d.external_id for d in out.details] == ["26673"]


class TestSyncIntegration:
    """The whole path with a fake default provider: scores, then detail, and a
    second sync that asks for nothing already stored."""

    @pytest.fixture
    def clean(self, client, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
        monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "50")

        def wipe():
            with SessionLocal() as s:
                for m in (GamePlayerLineRow, GameDetailRow, GameResultRow,
                          ResultsSyncStateRow, ResultsSyncLeaseRow):
                    s.query(m).delete()
                s.commit()
        wipe()
        yield
        wipe()

    def test_scores_then_detail_then_nothing_refetched(self, clean):
        seen = []
        default = FakeResultsProvider([])
        default.name = "alpha"
        router = RoutingProvider({"alpha": default, "winner": _provider(_handler(seen))},
                                 {"comp:ibl": "winner", "comp:winner_cup": "winner"}, "alpha")
        comps = ["comp:ibl", "comp:winner_cup"]
        with SessionLocal() as s:
            result = sync_results(s, provider=router, competition_ids=comps, force=True)
        assert result["status"] in ("ok", "partial")
        with SessionLocal() as s:
            rows = s.query(GameResultRow).filter_by(provider="winner").all()
            # 4 league + 2 cup games; the two future ones are stored as scheduled
            assert len(rows) == 6
            assert {r.status for r in rows} == {st.FINAL, st.SCHEDULED}
            stored = {r.external_id for r in s.query(GameDetailRow).all()}
        # Only 440 and 462 have saved Segev payloads; the other finals 404 -> errors
        assert {"26673", "26700"} <= stored
        segev_calls = [r for r in seen if _is_segev(r)]
        seen.clear()
        with SessionLocal() as s:
            sync_results(s, provider=router, competition_ids=comps, force=True)
        again = {(r.url.params["game_id"]) for r in seen if _is_segev(r)}
        assert "440" not in again and "462" not in again
        assert segev_calls
