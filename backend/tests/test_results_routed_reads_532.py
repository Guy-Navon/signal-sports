"""#532: reads show only the provider each competition is currently routed to."""
from __future__ import annotations

import pytest

from app.db.database import SessionLocal
from app.repositories import game_detail_repository, game_result_repository as repo
from app.results import service, status as st
from app.results.models import NormalizedGame, NormalizedGameDetail
from app.results.providers import active_provider_for, active_provider_map
from app.results.relevance import FollowedTargets


@pytest.fixture(autouse=True)
def _follow_two_comps(client, monkeypatch):
    monkeypatch.setattr(service, "followed_targets", lambda p: FollowedTargets(
        competition_ids=frozenset({"comp:euroleague", "comp:nba"})))
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.delenv("RESULTS_PROVIDER_ROUTES", raising=False)


def _game(provider, ext, comp):
    return NormalizedGame(
        provider=provider, external_id=ext, competition_id=comp, sport="basketball",
        status=st.FINAL, start_time="2999-01-01T00:00:00+00:00",
        home_team_name="A", away_team_name="B", home_score=80, away_score=70)


def _seed(s):
    games = [_game("fake", "old-el", "comp:euroleague"),
             _game("euroleague", "new-el", "comp:euroleague"),
             _game("fake", "nba-1", "comp:nba"),
             _game("thesportsdb", "legacy", "comp:nba")]
    for g in games:
        repo.upsert(s, g)
    s.commit()
    return {g.external_id: g for g in games}


def _read(s):
    """Ids of this file's rows (start 2999) that the read path returns; the DB is
    shared with other tests, which use real dates."""
    res = service.personalized_results(s, object())
    return sorted(g.id for g in res.games if (g.start_time or "").startswith("2999"))


def _ids(games, *exts):
    return sorted(games[e].id for e in exts)


def test_no_routes_reads_default_provider_rows_only_like_today(monkeypatch):
    with SessionLocal() as s:
        games = _seed(s)
        # Default is "fake"; the rows stored under the other providers are not it.
        assert _read(s) == _ids(games, "old-el", "nba-1")


def test_no_routes_default_thesportsdb_is_identical_to_unfiltered(monkeypatch):
    monkeypatch.delenv("RESULTS_PROVIDER")
    with SessionLocal() as s:
        for ext, comp in [("a", "comp:nba"), ("b", "comp:euroleague")]:
            repo.upsert(s, _game("thesportsdb", ext, comp))
        repo.upsert(s, _game("fake", "ignored-by-default", "comp:ignored"))
        s.commit()
        unfiltered = sorted(r.id for r in repo.list_games(s)
                            if r.provider == "thesportsdb" and r.start_time.startswith("2999"))
        assert _read(s) == unfiltered and len(unfiltered) >= 2


def test_routed_competition_reads_only_routed_provider(monkeypatch):
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:euroleague=euroleague")
    with SessionLocal() as s:
        games = _seed(s)
        # euroleague -> routed provider's row; nba unrouted -> default "fake" row
        assert _read(s) == _ids(games, "new-el", "nba-1")


def test_switching_route_back_restores_old_rows(monkeypatch):
    with SessionLocal() as s:
        games = _seed(s)
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:euroleague=euroleague")
        assert "old-el" not in [g.external_id for g in _rows(s)]
        monkeypatch.delenv("RESULTS_PROVIDER_ROUTES")
        assert _read(s) == _ids(games, "old-el", "nba-1")
        assert len([r for r in repo.list_games(s) if r.start_time.startswith("2999")]) >= 4  # nothing deleted


def _rows(s):
    return repo.list_games(s, active_providers=active_provider_map())


def test_detail_follows_the_filter(monkeypatch):
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:euroleague=euroleague")
    with SessionLocal() as s:
        games = _seed(s)
        for k in ("old-el", "new-el"):
            g = games[k]
            game_detail_repository.upsert(s, NormalizedGameDetail(
                game_id=g.id, provider=g.provider, external_id=g.external_id))
        s.commit()
        shown = [r.id for r in _rows(s)]
        details = game_detail_repository.get_details(s, shown)
        assert set(details) == {games["new-el"].id}


@pytest.mark.parametrize("bad", ["garbage", "comp:nope=euroleague", "comp:nba=nosuch"])
def test_bad_route_config_falls_back_to_default_without_crashing(monkeypatch, caplog, bad):
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", bad)
    with SessionLocal() as s:
        games = _seed(s)
        assert _read(s) == _ids(games, "old-el", "nba-1")
    assert active_provider_for("comp:euroleague") == "fake"
    assert "invalid RESULTS_PROVIDER_ROUTES" in caplog.text


def test_active_provider_for(monkeypatch):
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:euroleague=euroleague")
    assert active_provider_for("comp:euroleague") == "euroleague"
    assert active_provider_for("comp:nba") == "fake"
