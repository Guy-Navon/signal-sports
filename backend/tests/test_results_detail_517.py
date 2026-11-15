"""Per-game results detail: storage, provider contract and sync (issue #517).

Detail (per-team leaders, optional box-score lines, team stats, venue,
attendance) is stored next to ``game_results`` and keyed by the same game id.
The sync asks a provider that offers ``fetch_details`` for its finished games
that have no stored detail yet, at most ``RESULTS_DETAIL_MAX_PER_RUN`` per run,
and never asks again once a detail is stored. Detail failures never touch the
scores sync. With ``RESULTS_DETAIL_ENABLED`` off nothing changes at all.
"""
import pytest

from app.db.database import SessionLocal
from app.db.orm_models import (
    GameDetailRow, GamePlayerLineRow, GameResultRow, ResultsSyncLeaseRow, ResultsSyncStateRow,
)
from app.repositories import game_detail_repository as detail_repo
from app.repositories import game_result_repository as game_repo
from app.results import status as st
from app.results.models import (
    NormalizedGame, NormalizedGameDetail, PlayerLine, TeamLeader, leaders_from_lines,
)
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.providers.fake import FAKE_GAMES, FakeResultsProvider
from app.results.sync_service import sync_results

FINAL_FAKE = [g for g in FAKE_GAMES if g.status == st.FINAL]


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _wipe():
    with SessionLocal() as s:
        for model in (GamePlayerLineRow, GameDetailRow, GameResultRow,
                      ResultsSyncStateRow, ResultsSyncLeaseRow):
            s.query(model).delete()
        s.commit()


@pytest.fixture
def clean(client, monkeypatch):
    """App lifespan up, results tables empty, detail on with a roomy cap."""
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
    monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "50")
    _wipe()
    yield
    _wipe()


def _sync(provider):
    with SessionLocal() as s:
        return sync_results(s, provider=provider, force=True)


def _stored_ids():
    with SessionLocal() as s:
        return {r.game_id for r in s.query(GameDetailRow).all()}


def _detail(game: NormalizedGame, *, home_pts=20, players=None, venue="Arena") -> NormalizedGameDetail:
    return NormalizedGameDetail(
        provider=game.provider, external_id=game.external_id,
        leaders=[
            TeamLeader(side="home", stat="points", value=home_pts,
                       source_player_id="p1", name="Home Star", name_he="כוכב בית"),
            TeamLeader(side="away", stat="points", value=18,
                       source_player_id="p2", name="Away Star"),
        ],
        players=players if players is not None else [
            PlayerLine(side="home", source_player_id="p1", name="Home Star",
                       name_he="כוכב בית", minutes=31.5, stats={"points": home_pts, "rebounds": 7}),
            PlayerLine(side="away", source_player_id="p2", name="Away Star",
                       minutes=29.0, stats={"points": 18}),
        ],
        team_stats={"home": {"rebounds": 40}, "away": {"rebounds": 35}},
        venue=venue, attendance=10500,
    )


class _ScoresOnlyProvider:
    """A provider with no detail capability (TheSportsDB today)."""
    name = "fake"

    def fetch(self, competition_ids):
        return FakeResultsProvider().fetch(competition_ids)


class _RaisingDetailProvider(FakeResultsProvider):
    def fetch_details(self, games):
        self.detail_calls.append([g.external_id for g in games])
        raise RuntimeError("detail endpoint exploded")


# ── Storage: idempotent upsert + read path ────────────────────────────────────

class TestStorage:
    def test_same_detail_twice_is_one_row_set(self, clean):
        game = FINAL_FAKE[0]
        with SessionLocal() as s:
            game_repo.upsert(s, game)
            detail_repo.upsert(s, _detail(game))
            s.commit()
            detail_repo.upsert(s, _detail(game))
            s.commit()
            assert s.query(GameDetailRow).count() == 1
            assert s.query(GamePlayerLineRow).filter_by(game_id=game.id).count() == 2

    def test_upsert_updates_instead_of_duplicating(self, clean):
        game = FINAL_FAKE[0]
        fewer_lines = [PlayerLine(side="home", source_player_id="p1", name="Home Star",
                                  stats={"points": 33})]
        with SessionLocal() as s:
            detail_repo.upsert(s, _detail(game))
            s.commit()
            detail_repo.upsert(s, _detail(game, home_pts=33, players=fewer_lines, venue="New Arena"))
            s.commit()
            stored = detail_repo.get_details(s, [game.id])[game.id]
            assert stored.venue == "New Arena"
            assert [ld.value for ld in stored.leaders if ld.side == "home"] == [33]
            assert [p.stats for p in stored.players] == [{"points": 33}]
            assert s.query(GamePlayerLineRow).filter_by(game_id=game.id).count() == 1

    def test_read_returns_what_was_stored(self, clean):
        game = FINAL_FAKE[0]
        with SessionLocal() as s:
            detail_repo.upsert(s, _detail(game))
            s.commit()
            got = detail_repo.get_details(s, [game.id, "game_missing"])
        assert set(got) == {game.id}
        d = got[game.id]
        assert (d.provider, d.external_id) == (game.provider, game.external_id)
        assert d.venue == "Arena" and d.attendance == 10500
        assert d.team_stats == {"home": {"rebounds": 40}, "away": {"rebounds": 35}}
        home = [ld for ld in d.leaders if ld.side == "home"][0]
        assert (home.name, home.name_he, home.stat, home.value, home.source_player_id) == (
            "Home Star", "כוכב בית", "points", 20, "p1")
        lines = {p.source_player_id: p for p in d.players}
        assert lines["p1"].minutes == 31.5 and lines["p1"].stats == {"points": 20, "rebounds": 7}
        assert lines["p2"].name_he is None
        assert d.fetched_at

    def test_read_with_no_ids_is_empty(self, clean):
        with SessionLocal() as s:
            assert detail_repo.get_details(s, []) == {}


class TestLeadersFromLines:
    def test_top_scorer_per_side_with_ties(self):
        lines = [
            PlayerLine(side="home", source_player_id="a", name="A", stats={"points": 22}),
            PlayerLine(side="home", source_player_id="b", name="B", stats={"points": 22}),
            PlayerLine(side="home", source_player_id="c", name="C", stats={"points": 9}),
            PlayerLine(side="away", source_player_id="d", name="D", stats={"points": 30}),
        ]
        leaders = leaders_from_lines(lines, "points")
        assert sorted((ld.side, ld.source_player_id, ld.value) for ld in leaders) == [
            ("away", "d", 30), ("home", "a", 22), ("home", "b", 22)]

    def test_side_without_a_positive_value_has_no_leader(self):
        # A football team that did not score has no top scorer.
        lines = [
            PlayerLine(side="home", source_player_id="a", name="A", stats={"goals": 2}),
            PlayerLine(side="away", source_player_id="b", name="B", stats={"goals": 0}),
            PlayerLine(side="away", source_player_id="c", name=None, stats={}),
        ]
        leaders = leaders_from_lines(lines, "goals")
        assert [(ld.side, ld.value) for ld in leaders] == [("home", 2)]


# ── Sync behaviour ────────────────────────────────────────────────────────────

class TestDetailSync:
    def test_flag_off_makes_no_detail_calls(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "false")
        provider = FakeResultsProvider()
        summary = _sync(provider)
        assert provider.detail_calls == []
        assert "detail" not in summary
        assert _stored_ids() == set()

    def test_flag_defaults_off(self, clean, monkeypatch):
        monkeypatch.delenv("RESULTS_DETAIL_ENABLED", raising=False)
        provider = FakeResultsProvider()
        _sync(provider)
        assert provider.detail_calls == []

    def test_only_final_games_are_requested_and_stored(self, clean):
        provider = FakeResultsProvider()
        summary = _sync(provider)
        requested = {ext for call in provider.detail_calls for ext in call}
        assert requested == {g.external_id for g in FINAL_FAKE}
        assert _stored_ids() == {g.id for g in FINAL_FAKE}
        assert summary["status"] == "ok"
        assert summary["detail"]["status"] == "ok"
        assert summary["detail"]["stored"] == len(FINAL_FAKE)
        assert summary["detail"]["pending"] == 0

    def test_stored_detail_is_never_refetched(self, clean):
        first = FakeResultsProvider()
        _sync(first)
        second = FakeResultsProvider()
        summary = _sync(second)
        assert second.detail_calls == []
        assert summary["detail"]["requested"] == 0
        with SessionLocal() as s:
            assert s.query(GameDetailRow).count() == len(FINAL_FAKE)

    def test_game_that_becomes_final_is_fetched_once(self, clean):
        sched = [g for g in FAKE_GAMES if g.status == st.SCHEDULED][0]
        provider = FakeResultsProvider(games=[sched])
        _sync(provider)
        assert provider.detail_calls == []
        finished = sched.model_copy(update={"status": st.FINAL, "home_score": 99, "away_score": 90})
        provider = FakeResultsProvider(games=[finished])
        _sync(provider)
        assert provider.detail_calls == [[sched.external_id]]
        assert _stored_ids() == {sched.id}

    def test_per_run_cap_newest_first(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "3")
        newest_first = sorted(FINAL_FAKE, key=lambda g: g.start_time, reverse=True)
        provider = FakeResultsProvider()
        summary = _sync(provider)
        assert provider.detail_calls == [[g.external_id for g in newest_first[:3]]]
        assert summary["detail"]["pending"] == len(FINAL_FAKE) - 3
        provider = FakeResultsProvider()
        _sync(provider)
        assert provider.detail_calls == [[g.external_id for g in newest_first[3:6]]]

    def test_cap_zero_sends_no_detail_requests(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "0")
        provider = FakeResultsProvider()
        summary = _sync(provider)
        assert provider.detail_calls == []
        assert summary["detail"]["requested"] == 0

    def test_provider_without_detail_is_skipped_cleanly(self, clean):
        summary = _sync(_ScoresOnlyProvider())
        assert summary["status"] == "ok"
        assert summary["detail"]["status"] == "unsupported"
        assert _stored_ids() == set()

    def test_one_game_error_does_not_lose_the_others(self, clean):
        bad = FINAL_FAKE[0]
        provider = FakeResultsProvider(detail_errors={bad.external_id})
        summary = _sync(provider)
        assert summary["status"] == "ok"                         # scores untouched
        assert summary["created"] == len(FAKE_GAMES)
        assert summary["detail"]["status"] == "partial"
        assert set(summary["detail"]["errors"]) == {bad.id}
        assert _stored_ids() == {g.id for g in FINAL_FAKE[1:]}
        # The failed game is a candidate again next run, and only it.
        retry = FakeResultsProvider()
        _sync(retry)
        assert retry.detail_calls == [[bad.external_id]]
        assert _stored_ids() == {g.id for g in FINAL_FAKE}

    def test_detail_exception_does_not_affect_scores(self, clean):
        summary = _sync(_RaisingDetailProvider())
        assert summary["status"] == "ok"
        assert summary["created"] == len(FAKE_GAMES)
        assert summary["detail"]["status"] == "error"
        assert summary["detail"]["errors"] == {"provider": "RuntimeError"}
        with SessionLocal() as s:
            assert game_repo.count(s) == len(FAKE_GAMES)
            assert s.query(ResultsSyncStateRow).one().last_status == "ok"
        assert _stored_ids() == set()

    def test_malformed_detail_payload_does_not_affect_scores(self, clean):
        class _Garbage(FakeResultsProvider):
            def fetch_details(self, games):
                return DetailOutcome(details=["not a detail"])

        summary = _sync(_Garbage())
        assert summary["status"] == "ok"
        assert summary["detail"]["status"] == "error"
        with SessionLocal() as s:
            state = s.query(ResultsSyncStateRow).one()
            assert state.last_status == "ok"
            assert state.last_summary["detail"]["status"] == "error"
        assert _stored_ids() == set()

    def test_only_this_providers_games_are_requested(self, clean):
        other = FINAL_FAKE[0].model_copy(update={"provider": "thesportsdb"})
        with SessionLocal() as s:
            game_repo.upsert_many(s, [other])
        provider = FakeResultsProvider(games=[])
        _sync(provider)
        assert provider.detail_calls == []

    def test_detail_for_an_unrequested_game_is_ignored(self, clean):
        stranger = NormalizedGame(
            provider="fake", external_id="never-synced", competition_id="comp:nba",
            sport="basketball", status=st.FINAL, home_team_name="A", away_team_name="B")

        class _Chatty(FakeResultsProvider):
            def fetch_details(self, games):
                outcome = super().fetch_details(games)
                outcome.details.append(_detail(stranger))
                return outcome

        summary = _sync(_Chatty(games=FINAL_FAKE[:1]))
        assert _stored_ids() == {FINAL_FAKE[0].id}
        assert summary["detail"]["ignored"] == 1

    def test_scores_rate_limit_sends_no_detail_requests(self, clean):
        class _Limited(FakeResultsProvider):
            def fetch(self, competition_ids):
                outcome = super().fetch(competition_ids)
                outcome.not_checked = ["comp:acb"]
                outcome.retry_after_seconds = 60
                return outcome

        provider = _Limited()
        summary = _sync(provider)
        assert provider.detail_calls == []
        assert summary["detail"]["status"] == "skipped_rate_limited"

    def test_detail_rate_limit_blocks_later_syncs(self, clean):
        class _DetailLimited(FakeResultsProvider):
            def fetch_details(self, games):
                self.detail_calls.append([g.external_id for g in games])
                return DetailOutcome(details=[], not_checked=[g.id for g in games],
                                     retry_after_seconds=120)

        summary = _sync(_DetailLimited())
        assert summary["status"] == "ok"
        assert summary["detail"]["status"] == "rate_limited"
        assert summary["rate_limited_until"] is not None
        blocked = _sync(FakeResultsProvider())
        assert blocked["skipped"] == "rate_limited"

    def test_configured_fake_provider_end_to_end(self, clean):
        # No provider injected: RESULTS_PROVIDER=fake (conftest) is used.
        with SessionLocal() as s:
            summary = sync_results(s, force=True)
            details = detail_repo.get_details(s, [g.id for g in FINAL_FAKE])
        assert summary["detail"]["status"] == "ok"
        assert set(details) == {g.id for g in FINAL_FAKE}
        portland = details[FINAL_FAKE[0].id]
        assert {ld.side for ld in portland.leaders} == {"home", "away"}
        football = [g for g in FINAL_FAKE if g.sport == "football"]
        for g in football:
            assert all(ld.stat == "goals" for ld in details[g.id].leaders)


def test_scores_only_providers_still_satisfy_the_fetch_contract():
    # The detail capability is optional: the base contract is unchanged.
    outcome = _ScoresOnlyProvider().fetch(["comp:nba"])
    assert isinstance(outcome, FetchOutcome) and outcome.games
