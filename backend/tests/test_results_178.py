"""Personalized results feature — end-to-end coverage (issue #178).

Covers provider payload normalization, stable identity + idempotent upsert,
score/status drift, duplicate prevention, followed-team / followed-league /
followed-player-team relevance, exclusion of unrelated games, profile
isolation, chronological ordering, sync bookkeeping/throttle, and the API
authorization + response contract.
"""
from datetime import datetime, timezone

import pytest

from app.db.database import SessionLocal
from app.repositories import game_result_repository as repo
from app.repositories import profile_repository
from app.results import settings, status as st
from app.results.models import NormalizedGame, game_id
from app.results.normalization import parse_timestamp, parse_int, starts_in_future
from app.results.providers.base import FetchOutcome
from app.results.providers.fake import FakeResultsProvider, FAKE_GAMES
from app.results.providers.thesportsdb import normalize_event
from app.results.relevance import followed_targets, is_relevant, relevance_reason
from app.results.service import personalized_results
from app.results.sync_service import sync_results, should_sync, get_sync_state
from app.results.team_resolver import resolve_team


# ── Fixtures / helpers ────────────────────────────────────────────────────────

@pytest.fixture
def seeded(client):
    """Depend on the app lifespan (seeds guy / casual_deni_fan profiles)."""
    return client


def _sync_fake(session, games=None):
    provider = FakeResultsProvider(games=games)
    return sync_results(session, provider=provider, force=True)


def _clear_games(session):
    """Reset the shared session-scoped corpus so a created-count assertion is
    deterministic regardless of test order."""
    from app.db.orm_models import GameResultRow, ResultsSyncStateRow
    session.query(GameResultRow).delete()
    session.query(ResultsSyncStateRow).delete()
    session.commit()


# ── Provider payload normalization (raw TheSportsDB → NormalizedGame) ──────────

RAW_FINAL = {
    "idEvent": "2483461", "strSport": "Basketball",
    "strLeague": "NBA", "strSeason": "2025-2026",
    "strHomeTeam": "San Antonio Spurs", "strAwayTeam": "New York Knicks",
    "intHomeScore": "90", "intAwayScore": "94",
    "dateEvent": "2026-06-14", "strTime": "00:30:00",
    "strTimestamp": "2026-06-14T00:30:00", "strStatus": "FT",
    "intRound": "0", "strPostponed": "no",
}


class TestNormalization:
    def test_final_event_maps_all_fields(self):
        g = normalize_event(RAW_FINAL, "comp:nba")
        assert g is not None
        assert g.provider == "thesportsdb"
        assert g.external_id == "2483461"
        assert g.competition_id == "comp:nba"
        assert g.sport == "basketball"
        assert g.season == "2025-2026"
        assert g.status == st.FINAL
        assert g.home_score == 90 and g.away_score == 94
        assert g.start_time == "2026-06-14T00:30:00+00:00"
        # Team identity resolved against the taxonomy.
        assert g.home_team_id == "team:san_antonio_spurs"
        assert g.away_team_id == "team:ny_knicks"

    def test_missing_identity_or_teams_is_skipped(self):
        assert normalize_event({"idEvent": "", "strHomeTeam": "A", "strAwayTeam": "B"}, "comp:nba") is None
        assert normalize_event({"idEvent": "1", "strHomeTeam": "", "strAwayTeam": "B"}, "comp:nba") is None

    def test_unknown_team_resolves_to_none_but_game_kept(self):
        raw = {**RAW_FINAL, "strHomeTeam": "New Zealand Breakers", "strAwayTeam": "Utah Jazz"}
        g = normalize_event(raw, "comp:nba")
        assert g.home_team_id is None
        assert g.away_team_id == "team:utah_jazz"

    def test_scheduled_when_future_and_no_score(self):
        raw = {**RAW_FINAL, "intHomeScore": None, "intAwayScore": None,
               "strStatus": "NS", "strTimestamp": "2999-01-01T00:00:00"}
        g = normalize_event(raw, "comp:nba")
        assert g.status == st.SCHEDULED

    def test_postponed_flag_wins(self):
        raw = {**RAW_FINAL, "strPostponed": "yes", "strStatus": "FT"}
        assert normalize_event(raw, "comp:nba").status == st.POSTPONED


class TestStatusAndTime:
    def test_parse_status_structural_fallback(self):
        assert st.parse_status("", has_score=True, starts_in_future=False) == st.FINAL
        assert st.parse_status("", has_score=False, starts_in_future=True) == st.SCHEDULED
        assert st.parse_status("", has_score=False, starts_in_future=False) == st.UNKNOWN

    def test_winner(self):
        assert st.winner(st.FINAL, 90, 80) == "home"
        assert st.winner(st.FINAL, 80, 90) == "away"
        assert st.winner(st.FINAL, 88, 88) == "draw"
        assert st.winner(st.SCHEDULED, None, None) is None
        assert st.winner(st.FINAL, None, 80) is None

    def test_parse_timestamp_variants(self):
        assert parse_timestamp("2026-06-14T00:30:00") == "2026-06-14T00:30:00+00:00"
        assert parse_timestamp("2026-06-14T00:30:00Z") == "2026-06-14T00:30:00+00:00"
        assert parse_timestamp(None, "2026-06-14", "00:30:00") == "2026-06-14T00:30:00+00:00"
        assert parse_timestamp(None, "2026-06-14", "") == "2026-06-14T00:00:00+00:00"
        assert parse_timestamp(None, None, None) is None

    def test_parse_int(self):
        assert parse_int("5") == 5 and parse_int(5) == 5
        assert parse_int("") is None and parse_int(None) is None and parse_int("x") is None

    def test_starts_in_future(self):
        assert starts_in_future("2999-01-01T00:00:00+00:00") is True
        assert starts_in_future("2000-01-01T00:00:00+00:00") is False
        assert starts_in_future(None) is False


class TestTeamResolver:
    def test_resolves_real_provider_names_scoped_to_competition(self):
        assert resolve_team("Real Madrid Baloncesto", "comp:euroleague") == "team:real_madrid_bb"
        assert resolve_team("FC Barcelona Basquet", "comp:acb") == "team:barcelona_bb"
        assert resolve_team("Hapoel Tel Aviv BC", "comp:euroleague") == "team:hapoel_tlv_bb"
        assert resolve_team("Maccabi Tel Aviv BC", "comp:ibl") == "team:maccabi_tlv_bb"

    def test_competition_scopes_sport_for_shared_alias(self):
        # "Maccabi Tel Aviv" is shared by a football and a basketball entity;
        # a basketball competition must pick the basketball club.
        assert resolve_team("Maccabi Tel Aviv", "comp:euroleague") == "team:maccabi_tlv_bb"

    def test_unknown_returns_none(self):
        assert resolve_team("Some Unknown Club", "comp:nba") is None
        assert resolve_team("", "comp:nba") is None


class TestSeasons:
    def test_default_seasons_offseason(self):
        assert settings.default_seasons(datetime(2026, 7, 1, tzinfo=timezone.utc)) == [
            "2025-2026", "2024-2025"]

    def test_default_seasons_in_season(self):
        assert settings.default_seasons(datetime(2025, 11, 1, tzinfo=timezone.utc)) == [
            "2025-2026", "2024-2025"]


# ── Identity + idempotent persistence ─────────────────────────────────────────

class TestIdentityAndUpsert:
    def test_stable_id_from_provider_identity(self):
        a = game_id("thesportsdb", "999")
        b = game_id("thesportsdb", "999")
        c = game_id("thesportsdb", "1000")
        assert a == b and a != c and a.startswith("game_")

    def test_idempotent_upsert_no_duplicates(self, seeded):
        game = FAKE_GAMES[0]
        with SessionLocal() as s:
            repo.upsert(s, game)
            s.commit()
            repo.upsert(s, game)
            s.commit()
            rows = repo.list_games(s)
            matching = [r for r in rows if r.external_id == game.external_id]
            assert len(matching) == 1

    def test_score_and_status_update_between_cycles(self, seeded):
        base = NormalizedGame(
            provider="fake", external_id="drift-1", competition_id="comp:nba",
            sport="basketball", status=st.SCHEDULED, start_time="2026-04-01T00:00:00+00:00",
            home_team_name="Portland Trail Blazers", away_team_name="Los Angeles Lakers",
            home_team_id="team:portland_blazers", away_team_id="team:la_lakers",
        )
        finished = base.model_copy(update={
            "status": st.FINAL, "home_score": 111, "away_score": 100})
        with SessionLocal() as s:
            repo.upsert(s, base)
            s.commit()
            repo.upsert(s, finished)
            s.commit()
            row = repo.get_by_id(s, base.id)
            assert row.status == st.FINAL
            assert row.home_score == 111 and row.away_score == 100
            assert len([r for r in repo.list_games(s) if r.external_id == "drift-1"]) == 1

    def test_repeated_sync_does_not_duplicate(self, seeded):
        with SessionLocal() as s:
            _clear_games(s)
            first = _sync_fake(s)
            total_after_first = repo.count(s)
            second = _sync_fake(s)
            assert first["created"] == len(FAKE_GAMES)
            assert second["created"] == 0
            assert second["updated"] == len(FAKE_GAMES)
            assert repo.count(s) == total_after_first

    def test_list_games_newest_first(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            rows = repo.list_games(s, statuses=[st.FINAL])
            times = [r.start_time for r in rows if r.start_time]
            assert times == sorted(times, reverse=True)


# ── Relevance + isolation ─────────────────────────────────────────────────────

class TestRelevance:
    def test_guy_followed_targets(self, seeded):
        with SessionLocal() as s:
            guy = profile_repository.get_by_id(s, "guy")
            followed = followed_targets(guy)
        assert "comp:nba" in followed.competition_ids
        assert "comp:euroleague" in followed.competition_ids
        assert "comp:acb" not in followed.competition_ids       # level -1, not followed
        assert "team:maccabi_tlv_bb" in followed.team_ids
        # Followed player/coach → their team is in scope.
        assert "team:portland_blazers" in followed.team_ids     # via Deni Avdija

    def test_deni_fan_only_gets_players_team(self, seeded):
        with SessionLocal() as s:
            deni = profile_repository.get_by_id(s, "casual_deni_fan")
            followed = followed_targets(deni)
        assert followed.competition_ids == frozenset()
        assert followed.team_ids == frozenset({"team:portland_blazers"})

    def test_followed_league_relevance(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            guy = profile_repository.get_by_id(s, "guy")
            res = personalized_results(s, guy)
        ids = {g.id for g in res.games}
        # Lakers–Celtics: relevant to Guy ONLY through the followed NBA competition.
        lakers = next(g for g in FAKE_GAMES if g.external_id == "nba-lakers-celtics-1")
        assert lakers.id in ids

    def test_followed_team_and_player_team_relevance(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            deni = profile_repository.get_by_id(s, "casual_deni_fan")
            res = personalized_results(s, deni)
        reasons = {g.relevance_reason for g in res.games}
        assert res.games, "Deni fan should see Portland games"
        assert all("team:portland_blazers" in r for r in reasons)

    def test_unrelated_game_excluded_both_profiles(self, seeded):
        acb = next(g for g in FAKE_GAMES if g.competition_id == "comp:acb")
        with SessionLocal() as s:
            _sync_fake(s)
            for uid in ("guy", "casual_deni_fan"):
                prof = profile_repository.get_by_id(s, uid)
                res = personalized_results(s, prof)
                assert acb.id not in {g.id for g in res.games}

    def test_profile_isolation(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            guy_ids = {g.id for g in personalized_results(
                s, profile_repository.get_by_id(s, "guy")).games}
            deni_ids = {g.id for g in personalized_results(
                s, profile_repository.get_by_id(s, "casual_deni_fan")).games}
        # Guy sees strictly more; every Deni game (Portland) is also in Guy's
        # NBA-followed set; Guy has EuroLeague/IBL games Deni never sees.
        assert deni_ids and guy_ids
        assert deni_ids < guy_ids

    def test_no_preferences_is_signaled(self, seeded):
        # A profile with no follows → has_preferences False, empty games.
        from app.models.profile import UserProfile
        from app.models.profile_v2 import ProfileV2
        empty = UserProfile(
            user_id="empty", display_name="Empty", language="he",
            profile_type="new", topics=[], muted_topics=[], muted_sources=[],
            followed_entities=[], profile_v2=ProfileV2(),
        )
        with SessionLocal() as s:
            _sync_fake(s)
            res = personalized_results(s, empty)
        assert res.has_preferences is False
        assert res.games == []

    def test_relevance_reason_prefers_direct_team(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            guy = profile_repository.get_by_id(s, "guy")
            res = personalized_results(s, guy)
        maccabi_el = next(g for g in FAKE_GAMES if g.external_id == "el-maccabi-realmadrid-1")
        row = next(g for g in res.games if g.id == maccabi_el.id)
        # Guy follows Maccabi as a team directly — direct beats player-derived.
        assert row.relevance_reason == "followed_team:team:maccabi_tlv_bb"


# ── Sync bookkeeping / throttle / errors ──────────────────────────────────────

class _ErrorProvider:
    name = "erroring"

    def fetch(self, competition_ids):
        return FetchOutcome(games=[], errors={"comp:nba": "boom"}, fetched_counts={})


class TestSync:
    def test_summary_shape_ok(self, seeded):
        with SessionLocal() as s:
            summary = _sync_fake(s)
        assert summary["status"] == "ok"
        assert summary["fetched"] == len(FAKE_GAMES)
        assert summary["errors"] == {}

    def test_error_is_captured_not_raised(self, seeded):
        with SessionLocal() as s:
            summary = sync_results(s, provider=_ErrorProvider(), force=True)
            state = get_sync_state(s)
        assert summary["status"] == "error"
        assert "comp:nba" in summary["errors"]
        assert state["last_status"] == "error"

    def test_throttle_blocks_soon_after_success(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            # force=False now respects the throttle.
            assert should_sync(s, min_interval_seconds=3600) is False
            skipped = sync_results(s, provider=FakeResultsProvider(), force=False,
                                   competition_ids=settings.tracked_competitions())
            assert skipped.get("skipped") == "throttled"

    def test_zero_interval_always_allows(self, seeded):
        with SessionLocal() as s:
            _sync_fake(s)
            assert should_sync(s, min_interval_seconds=0) is True


# ── API: authorization + response contract ────────────────────────────────────

def _seed_results_for_api():
    with SessionLocal() as s:
        _sync_fake(s)


class TestResultsApi:
    def test_me_results_requires_auth(self, client):
        assert client.get("/api/me/results").status_code == 401

    def test_admin_route_requires_admin(self, client, user_client, admin_client):
        _seed_results_for_api()
        assert client.get("/api/results/guy").status_code == 401           # anon
        assert user_client.get("/api/results/guy").status_code == 403      # non-admin
        assert admin_client.get("/api/results/guy").status_code == 200     # admin

    def test_sync_endpoint_admin_only(self, client, user_client, admin_client):
        assert client.post("/api/results/sync").status_code == 401
        assert user_client.post("/api/results/sync").status_code == 403
        # Admin sync succeeds (fake provider, no network).
        assert admin_client.post("/api/results/sync").status_code == 200

    def test_admin_view_as_relevance_and_isolation(self, admin_client):
        _seed_results_for_api()
        guy = admin_client.get("/api/results/guy").json()
        deni = admin_client.get("/api/results/casual_deni_fan").json()
        assert guy["has_preferences"] is True
        guy_ids = {g["id"] for g in guy["games"]}
        deni_ids = {g["id"] for g in deni["games"]}
        assert deni_ids and deni_ids < guy_ids

    def test_response_contract(self, admin_client):
        _seed_results_for_api()
        body = admin_client.get("/api/results/guy").json()
        assert set(body) == {"has_preferences", "games"}
        game = body["games"][0]
        for key in ("id", "competition_id", "competition_he", "status",
                    "start_time", "home", "away", "winner"):
            assert key in game
        for key in ("id", "name", "name_provider", "score", "is_winner"):
            assert key in game["home"]

    def test_me_results_no_preferences_then_with_follows(self, user_client):
        _seed_results_for_api()
        # Fresh user: no follows.
        first = user_client.get("/api/me/results").json()
        assert first["has_preferences"] is False
        assert first["games"] == []
        # Declare an interest in the NBA → NBA results appear, others excluded.
        put = user_client.put("/api/me/interests", json={
            "follows": [{"scope": "competition", "target_id": "comp:nba", "starred": False}],
            "event_preferences": {},
        })
        assert put.status_code == 200
        after = user_client.get("/api/me/results").json()
        assert after["has_preferences"] is True
        comps = {g["competition_id"] for g in after["games"]}
        assert comps == {"comp:nba"}      # preference change changed visible results

    def test_isolation_between_two_users(self, _application):
        """Two real user sessions with different follows never see each other's
        preference-driven results."""
        from tests.conftest import _identity_client, _dispose_identity
        _seed_results_for_api()
        alice = _identity_client(_application, "user")
        bob = _identity_client(_application, "user")
        try:
            alice.put("/api/me/interests", json={
                "follows": [{"scope": "competition", "target_id": "comp:euroleague",
                             "starred": False}], "event_preferences": {}})
            bob.put("/api/me/interests", json={
                "follows": [{"scope": "competition", "target_id": "comp:ibl",
                             "starred": False}], "event_preferences": {}})
            a_comps = {g["competition_id"] for g in alice.get("/api/me/results").json()["games"]}
            b_comps = {g["competition_id"] for g in bob.get("/api/me/results").json()["games"]}
            assert a_comps == {"comp:euroleague"}
            assert b_comps == {"comp:ibl"}
        finally:
            _dispose_identity(alice)
            _dispose_identity(bob)
