"""Per-competition provider routing (issue #529).

Each competition goes to the provider its route names; the default (no routes) is
the plain provider, so requests are exactly what they were. Rate limits are per
provider: a 429 from one provider never stops another in the same sync.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import SessionLocal
from app.db.orm_models import (
    GameDetailRow, GamePlayerLineRow, GameResultRow, ResultsSyncLeaseRow, ResultsSyncStateRow,
)
from app.results import providers as registry
from app.results import status as st
from app.results.providers import get_provider
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.providers.fake import FAKE_GAMES, FakeResultsProvider
from app.results.providers.routing import RoutingProvider, parse_routes
from app.results.sync_service import sync_results

NBA = [g.model_copy(update={"provider": "alpha"}) for g in FAKE_GAMES
       if g.competition_id == "comp:nba" and g.status == st.FINAL]
IBL = [g.model_copy(update={"provider": "beta"}) for g in FAKE_GAMES if g.competition_id == "comp:ibl"]
ROUTES = {"comp:nba": "alpha", "comp:ibl": "beta"}


class _Fake(FakeResultsProvider):
    def __init__(self, name, games, *, retry_after=None, boom=False, details=True):
        super().__init__(games)
        self.name = name
        self.calls: list[list[str]] = []
        self._retry, self._boom = retry_after, boom
        if not details:
            self.fetch_details = None  # supports_details() is False

    def fetch(self, competition_ids):
        self.calls.append(list(competition_ids))
        if self._boom:
            raise RuntimeError("secret-key-in-url")
        out = super().fetch(competition_ids)
        if self._retry is not None:
            return FetchOutcome(not_checked=list(competition_ids), retry_after_seconds=self._retry)
        return out


def _router(alpha, beta, default="alpha"):
    return RoutingProvider({"alpha": alpha, "beta": beta}, ROUTES, default)


@pytest.fixture
def clean(client, monkeypatch):
    def wipe():
        with SessionLocal() as s:
            for m in (GamePlayerLineRow, GameDetailRow, GameResultRow,
                      ResultsSyncStateRow, ResultsSyncLeaseRow):
                s.query(m).delete()
            s.commit()
    wipe()
    yield
    wipe()


def _sync(provider, comps=("comp:nba", "comp:ibl")):
    with SessionLocal() as s:
        return sync_results(s, provider=provider, competition_ids=list(comps), force=True)


class TestRoutingProvider:
    def test_games_from_both_providers_are_merged(self):
        out = _router(_Fake("alpha", NBA), _Fake("beta", IBL)).fetch(["comp:nba", "comp:ibl"])
        assert {g.provider for g in out.games} == {"alpha", "beta"}
        assert out.fetched_counts == {"comp:nba": len(NBA), "comp:ibl": len(IBL)}

    def test_each_provider_only_gets_its_competitions(self):
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        _router(a, b).fetch(["comp:ibl", "comp:nba", "comp:acb"])  # acb -> default alpha
        assert a.calls == [["comp:nba", "comp:acb"]]
        assert b.calls == [["comp:ibl"]]

    def test_an_error_in_one_keeps_the_others_games(self):
        out = _router(_Fake("alpha", NBA), _Fake("beta", IBL, boom=True)).fetch(
            ["comp:nba", "comp:ibl"])
        assert {g.provider for g in out.games} == {"alpha"}
        assert out.errors == {"comp:ibl": "RuntimeError"}  # class name only

    def test_a_429_marks_only_its_own_competitions_not_checked(self):
        out = _router(_Fake("alpha", NBA), _Fake("beta", IBL, retry_after=60)).fetch(
            ["comp:nba", "comp:ibl"])
        assert {g.provider for g in out.games} == {"alpha"}
        assert out.not_checked == ["comp:ibl"]
        assert out.provider_retry_after == {"beta": 60}
        assert out.retry_after_seconds == 60

    def test_fetch_details_dispatches_by_game_provider(self):
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        beta_final = [g for g in IBL if g.status == st.FINAL]
        out = _router(a, b).fetch_details(NBA + beta_final)
        assert a.detail_calls == [[g.external_id for g in NBA]]
        assert b.detail_calls == [[g.external_id for g in beta_final]]
        assert {d.provider for d in out.details} == {"alpha", "beta"}

    def test_fetch_details_skips_providers_without_details(self):
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL, details=False)
        out = _router(a, b).fetch_details(NBA + [g for g in IBL if g.status == st.FINAL])
        assert a.detail_calls and {d.provider for d in out.details} == {"alpha"}
        assert out.errors == {} and out.not_checked == []

    def test_blocked_provider_is_not_called(self):
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        r = _router(a, b)
        r.set_blocked({"beta"})
        out = r.fetch(["comp:nba", "comp:ibl"])
        assert b.calls == [] and out.not_checked == ["comp:ibl"] and len(out.games) == len(NBA)


class TestRouteConfig:
    KW = dict(known_providers={"alpha", "beta"}, known_competitions={"comp:nba", "comp:ibl"})

    def test_parses_and_normalizes(self):
        assert parse_routes(" comp:nba = Alpha ,comp:ibl=beta,", **self.KW) == ROUTES

    def test_empty_is_no_routes(self):
        assert parse_routes("", **self.KW) == {} and parse_routes(None, **self.KW) == {}

    @pytest.mark.parametrize("raw", [
        "comp:nba", "comp:nba=", "=alpha", "comp:nba=gamma", "comp:zzz=alpha",
        "comp:nba=alpha,comp:nba=beta",
    ])
    def test_invalid_config_is_rejected(self, raw):
        with pytest.raises(ValueError):
            parse_routes(raw, **self.KW)

    def test_get_provider_rejects_a_bad_env(self, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:nba=nosuch")
        with pytest.raises(ValueError):
            get_provider()


class TestRegistry:
    def test_default_is_the_plain_provider(self, monkeypatch):
        monkeypatch.delenv("RESULTS_PROVIDER_ROUTES", raising=False)
        assert type(get_provider()) is FakeResultsProvider  # conftest: RESULTS_PROVIDER=fake

    def test_routes_give_a_router_and_a_provider_is_one_registry_line(self, monkeypatch):
        monkeypatch.setitem(registry.REGISTRY, "alpha", lambda: _Fake("alpha", NBA))
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:ibl=alpha")
        p = get_provider()
        assert isinstance(p, RoutingProvider) and p.provider_names == ["alpha", "fake"]
        assert p.provider_for("comp:ibl") == "alpha" and p.provider_for("comp:nba") == "fake"

    def test_default_config_sends_the_same_calls_as_before(self, clean, monkeypatch):
        monkeypatch.delenv("RESULTS_PROVIDER_ROUTES", raising=False)
        plain = _Fake("fake", FAKE_GAMES)
        _sync(plain, ("comp:nba", "comp:ibl"))
        assert plain.calls == [["comp:nba", "comp:ibl"]]  # one call, all competitions


class TestSyncRateLimits:
    def test_a_429_in_one_provider_still_syncs_the_other(self, clean):
        summary = _sync(_router(_Fake("alpha", NBA), _Fake("beta", IBL, retry_after=60)))
        assert summary["status"] == "partial"
        assert summary["not_checked"] == ["comp:ibl"]
        assert set(summary["rate_limited_until_by_provider"]) == {"beta"}
        assert summary["rate_limited_until"] == summary["rate_limited_until_by_provider"]["beta"]
        with SessionLocal() as s:
            assert {r.provider for r in s.query(GameResultRow)} == {"alpha"}

    def test_next_sync_skips_only_the_blocked_provider_until_it_passes(self, clean):
        _sync(_router(_Fake("alpha", NBA), _Fake("beta", IBL, retry_after=60)))
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        second = _sync(_router(a, b))
        assert second["status"] == "partial" and second["not_checked"] == ["comp:ibl"]
        assert a.calls and b.calls == []
        # The block expires: move the stored per-provider time into the past.
        with SessionLocal() as s:
            row = s.get(ResultsSyncStateRow, 1)
            past = (datetime.now(tz=timezone.utc) - timedelta(seconds=5)).isoformat()
            row.last_summary = {**row.last_summary,
                                "rate_limited_until_by_provider": {"beta": past}}
            s.commit()
        a2, b2 = _Fake("alpha", NBA), _Fake("beta", IBL)
        third = _sync(_router(a2, b2))
        assert third["status"] == "ok" and b2.calls == [["comp:ibl"]]
        assert third["rate_limited_until_by_provider"] == {}

    def test_all_providers_blocked_skips_the_sync(self, clean):
        _sync(_router(_Fake("alpha", NBA, retry_after=60), _Fake("beta", IBL, retry_after=60)))
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        assert _sync(_router(a, b))["skipped"] == "rate_limited"
        assert a.calls == [] and b.calls == []

    def test_legacy_summary_blocks_every_provider(self, clean):
        until = (datetime.now(tz=timezone.utc) + timedelta(minutes=5)).isoformat()
        with SessionLocal() as s:
            s.add(ResultsSyncStateRow(id=1, last_summary={"rate_limited_until": until}))
            s.commit()
        assert _sync(_Fake("fake", FAKE_GAMES))["skipped"] == "rate_limited"

    def test_detail_stage_skips_only_the_limited_provider(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
        monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "50")
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL, retry_after=60)
        summary = _sync(_router(a, b))
        assert a.detail_calls and b.detail_calls == []
        assert summary["detail"]["status"] == "ok"
        assert summary["detail"]["requested"] == len(NBA)

    def test_detail_429_blocks_only_that_provider(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
        monkeypatch.setenv("RESULTS_DETAIL_MAX_PER_RUN", "50")

        class _DetailLimited(_Fake):
            def fetch_details(self, games):
                return DetailOutcome(not_checked=[g.id for g in games], retry_after_seconds=90)

        summary = _sync(_router(_Fake("alpha", NBA), _DetailLimited("beta", IBL)))
        assert set(summary["rate_limited_until_by_provider"]) == {"beta"}
        a, b = _Fake("alpha", NBA), _Fake("beta", IBL)
        second = _sync(_router(a, b))
        assert a.calls and b.calls == []
        assert second["status"] == "partial"


def test_a_bad_route_config_is_recorded_not_raised_by_the_sync(clean, monkeypatch):
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "comp:nba=nosuch")
    with SessionLocal() as s:
        summary = sync_results(s, force=True, competition_ids=["comp:nba"])
    assert summary["status"] == "error"
    assert summary["errors"] == {"provider": "ValueError"}
