"""#522: per-provider health, the per-provider switch, read-time fallback and
backup sync.

The clock is injected everywhere (``sync_service._now`` for the sync, ``now=``
for reads), so freshness decisions are deterministic. No network: providers are
scripted fakes, and the one TheSportsDB test uses ``httpx.MockTransport``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.db.database import SessionLocal
from app.db.orm_models import (
    GameDetailRow, GamePlayerLineRow, GameResultRow, ResultsProviderHealthRow,
    ResultsSyncLeaseRow, ResultsSyncStateRow,
)
from app.repositories import game_detail_repository, game_result_repository as repo
from app.results import health, providers as registry, service, status as st, sync_service
from app.results.models import NormalizedGame, NormalizedGameDetail
from app.results.providers import active_provider_map, get_provider
from app.results.providers.base import FetchOutcome
from app.results.providers.fake import FakeResultsProvider
from app.results.providers.routing import RoutingProvider
from app.results.providers.thesportsdb import TheSportsDBProvider
from app.results.relevance import FollowedTargets

NOW = datetime(2030, 3, 1, 12, 0, tzinfo=timezone.utc)
EL, NBA, IBL = "comp:euroleague", "comp:nba", "comp:ibl"


def _game(provider, ext, comp, start="2999-01-01T00:00:00+00:00"):
    return NormalizedGame(
        provider=provider, external_id=ext, competition_id=comp, sport="basketball",
        status=st.FINAL, start_time=start, home_team_name="A", away_team_name="B",
        home_score=80, away_score=70)


class _Scripted:
    """A provider whose answer per competition is scripted: games, an error
    string, a 429 (``limited``) or raising for the whole call."""

    def __init__(self, name, *, games=None, errors=None, limited=(), retry=60.0, boom=None):
        self.name = name
        self._games = games if games is not None else {}
        self._errors = dict(errors or {})
        self._limited, self._retry, self._boom = set(limited), retry, boom
        self.calls: list[list[str]] = []

    def fetch(self, competition_ids):
        self.calls.append(list(competition_ids))
        if self._boom is not None:
            raise self._boom
        out = FetchOutcome()
        for index, comp in enumerate(competition_ids):
            if comp in self._limited:
                out.not_checked = list(competition_ids[index:])
                out.retry_after_seconds = self._retry
                break
            if comp in self._errors:
                out.errors[comp] = self._errors[comp]
                continue
            games = [_game(self.name, f"{self.name}-{comp}-{i}", comp) for i in
                     range(self._games.get(comp, 1))]
            out.games.extend(games)
            out.fetched_counts[comp] = len(games)
        return out


@pytest.fixture
def clean(client, monkeypatch):
    def wipe():
        with SessionLocal() as s:
            for m in (GamePlayerLineRow, GameDetailRow, GameResultRow, ResultsSyncStateRow,
                      ResultsSyncLeaseRow, ResultsProviderHealthRow):
                s.query(m).delete()
            s.commit()
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    for name in ("RESULTS_PROVIDER_ROUTES", "RESULTS_PROVIDER_DISABLED",
                 "RESULTS_PROVIDER_STALE_HOURS", "RESULTS_PROVIDER_BACKUP_SYNC"):
        monkeypatch.delenv(name, raising=False)
    wipe()
    yield
    wipe()


def _at(monkeypatch, moment):
    monkeypatch.setattr(sync_service, "_now", lambda: moment)


def _sync(provider, comps):
    with SessionLocal() as s:
        return sync_service.sync_results(s, provider=provider, competition_ids=list(comps),
                                         force=True)


def _health(provider, comp="*"):
    with SessionLocal() as s:
        row = s.get(ResultsProviderHealthRow, (provider, comp))
        if row is None:
            return None
        s.expunge(row)
        return row


# ── 1. Health is recorded per provider and per competition ──────────────────────

class TestHealthRecording:
    def test_success_is_recorded_for_the_provider_and_each_competition(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha"), [NBA, EL])
        for comp in ("*", NBA, EL):
            row = _health("alpha", comp)
            assert row.last_attempt_at == NOW.isoformat()
            assert row.last_success_at == NOW.isoformat()
            assert row.last_status == "ok"
            assert row.consecutive_failures == 0 and row.last_error is None

    def test_a_competition_error_is_recorded_without_failing_the_others(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha", errors={EL: "HTTP 500"}), [NBA, EL])
        el, nba, prov = _health("alpha", EL), _health("alpha", NBA), _health("alpha")
        assert el.last_status == "error" and el.last_error == "HTTP 500"
        assert el.consecutive_failures == 1 and el.last_success_at is None
        assert el.last_error_at == NOW.isoformat() and el.shape_failures == 0
        assert nba.last_status == "ok" and nba.consecutive_failures == 0
        # The provider answered for one competition: it is up, partially.
        assert prov.last_status == "partial" and prov.consecutive_failures == 0
        assert prov.last_success_at == NOW.isoformat() and prov.last_error == "HTTP 500"

    @pytest.mark.parametrize("err", ["MalformedResponse", "ValueError",
                                     "JSONDecodeError: Expecting value"])
    def test_a_shape_failure_is_counted(self, clean, monkeypatch, err):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha", errors={EL: err}), [EL])
        assert _health("alpha", EL).shape_failures == 1
        prov = _health("alpha")
        assert prov.shape_failures == 1 and prov.last_status == "error"
        assert prov.consecutive_failures == 1

    def test_a_transport_error_is_not_a_shape_failure(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha", errors={EL: "ConnectTimeout: timed out"}), [EL])
        assert _health("alpha", EL).shape_failures == 0

    def test_a_provider_that_raises_fails_every_competition(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        summary = _sync(_Scripted("alpha", boom=RuntimeError("https://x?key=secret")), [NBA, EL])
        assert summary["status"] == "error"
        for comp in ("*", NBA, EL):
            row = _health("alpha", comp)
            assert row.last_status == "error" and row.consecutive_failures == 1
            assert row.last_error == "RuntimeError"  # class name only, never the URL

    def test_a_429_is_recorded_but_is_not_a_source_failure(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha"), [NBA, EL])
        _at(monkeypatch, NOW + timedelta(hours=1))
        _sync(_Scripted("alpha", limited={NBA}), [NBA, EL])
        for comp in ("*", NBA, EL):
            row = _health("alpha", comp)
            assert row.last_status == "rate_limited"
            assert row.consecutive_failures == 0
            assert row.last_success_at == NOW.isoformat()  # unchanged
            assert row.last_attempt_at == (NOW + timedelta(hours=1)).isoformat()

    def test_consecutive_failures_accumulate_and_reset_on_success(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("alpha"), [EL])
        for hour in (1, 2):
            _at(monkeypatch, NOW + timedelta(hours=hour))
            _sync(_Scripted("alpha", errors={EL: "HTTP 503"}), [EL])
        row = _health("alpha", EL)
        assert row.consecutive_failures == 2 and row.last_success_at == NOW.isoformat()
        assert _health("alpha").consecutive_failures == 2
        _at(monkeypatch, NOW + timedelta(hours=3))
        _sync(_Scripted("alpha"), [EL])
        row = _health("alpha", EL)
        assert row.consecutive_failures == 0
        assert row.last_success_at == (NOW + timedelta(hours=3)).isoformat()
        assert row.last_error == "HTTP 503"  # the last error stays visible
        assert _health("alpha").consecutive_failures == 0

    def test_routed_providers_get_separate_health(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        router = RoutingProvider(
            {"alpha": _Scripted("alpha"), "beta": _Scripted("beta", errors={IBL: "HTTP 404"})},
            {IBL: "beta"}, "alpha")
        _sync(router, [NBA, IBL])
        assert _health("alpha", NBA).last_status == "ok"
        assert _health("beta", IBL).last_status == "error"
        assert _health("beta").consecutive_failures == 1
        assert _health("alpha", IBL) is None  # backup off on a hand-built router

    def test_a_blocked_provider_is_not_recorded_as_attempted(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        router = RoutingProvider({"alpha": _Scripted("alpha"),
                                  "beta": _Scripted("beta", limited={IBL})}, {IBL: "beta"}, "alpha")
        _sync(router, [NBA, IBL])
        _at(monkeypatch, NOW + timedelta(seconds=10))  # beta's block still runs
        router2 = RoutingProvider({"alpha": _Scripted("alpha"), "beta": _Scripted("beta")},
                                  {IBL: "beta"}, "alpha")
        _sync(router2, [NBA, IBL])
        assert _health("beta", IBL).last_attempt_at == NOW.isoformat()

    def test_a_health_recording_failure_never_breaks_the_scores_sync(self, clean, monkeypatch):
        _at(monkeypatch, NOW)

        def boom(*a, **k):
            raise RuntimeError("health table broke")
        monkeypatch.setattr(sync_service.health, "record_fetch_health", boom)
        summary = _sync(_Scripted("alpha"), [NBA, EL])
        assert summary["status"] == "ok" and summary["created"] == 2
        assert summary["health_error"] == "RuntimeError"
        with SessionLocal() as s:
            assert s.query(GameResultRow).count() == 2
            assert s.get(ResultsSyncStateRow, 1).last_status == "ok"


# ── 2/3. The per-provider switch ────────────────────────────────────────────────

class TestDisabledProvider:
    def test_disabled_provider_is_not_constructed_or_called(self, clean, monkeypatch):
        built = []

        def euroleague():
            built.append("euroleague")
            return _Scripted("euroleague")
        default = FakeResultsProvider()
        monkeypatch.setitem(registry.REGISTRY, "euroleague", euroleague)
        monkeypatch.setitem(registry.REGISTRY, "fake", lambda: default)
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "euroleague")
        provider = get_provider()
        assert provider is default and built == []  # no routes left: the plain default
        assert registry.configured_provider_names() == ["fake"]

    def test_disabled_provider_competitions_are_synced_by_the_default(self, clean, monkeypatch):
        el = _Scripted("euroleague")
        nba = _Scripted("espn_nba")
        default = _Scripted("fake")
        monkeypatch.setitem(registry.REGISTRY, "euroleague", lambda: el)
        monkeypatch.setitem(registry.REGISTRY, "espn_nba", lambda: nba)
        monkeypatch.setitem(registry.REGISTRY, "fake", lambda: default)
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague,{NBA}=espn_nba")
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", " Euroleague ")
        monkeypatch.setenv("RESULTS_PROVIDER_BACKUP_SYNC", "false")
        _at(monkeypatch, NOW)
        with SessionLocal() as s:
            summary = sync_service.sync_results(s, competition_ids=[EL, NBA, IBL], force=True)
        assert el.calls == []
        assert default.calls == [[EL, IBL]]
        assert nba.calls == [[NBA]]
        assert summary["fetched_counts"] == {EL: 1, IBL: 1, NBA: 1}

    def test_disabled_provider_competitions_are_read_from_the_default(self, clean, follows,
                                                                      monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", EL, NOW)  # healthy, but switched off
            monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "euroleague")
            assert _served(s) == {EL: {"fake"}}

    def test_unknown_disabled_name_is_rejected_by_config_and_reads_fall_back(
            self, clean, follows, monkeypatch, caplog):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "eurolaegue")
        with pytest.raises(ValueError):
            registry.configured_disabled()
        with pytest.raises(ValueError):
            get_provider()
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", EL, NOW)
            assert _served(s) == {EL: {"fake"}}
        assert "RESULTS_PROVIDER_DISABLED" in caplog.text

    def test_disabling_the_default_provider_is_rejected(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "fake")
        with pytest.raises(ValueError):
            registry.configured_disabled()


# ── 4. Read-time fallback ───────────────────────────────────────────────────────

def _seed_both(s):
    """One EuroLeague game from each provider (the same real game, two identities)
    plus an unrouted NBA game of the default."""
    rows = [_game("fake", "fb-el", EL), _game("euroleague", "rt-el", EL), _game("fake", "nba", NBA)]
    for g in rows:
        repo.upsert(s, g)
    s.commit()
    return {g.external_id: g for g in rows}


def _record_success(s, provider, comp, at):
    health.record_fetch_health(
        s, {provider: health.ProviderRun([comp], FetchOutcome(fetched_counts={comp: 1}))},
        at.isoformat())
    s.commit()


def _served(s, now=NOW):
    """competition -> set of providers whose rows the read path returned."""
    out: dict[str, set] = {}
    for g in service.personalized_results(s, object(), now=now).games:
        if (g.start_time or "").startswith("2999"):
            row = repo.get_by_id(s, g.id)
            out.setdefault(g.competition_id, set()).add(row.provider)
    return {k: v for k, v in out.items() if k == EL}


@pytest.fixture
def follows(monkeypatch):
    monkeypatch.setattr(service, "followed_targets", lambda p: FollowedTargets(
        competition_ids=frozenset({EL, NBA})))


class TestReadFallback:
    @pytest.fixture(autouse=True)
    def _routed(self, clean, follows, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")

    def test_fresh_routed_provider_is_served(self):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=5, minutes=59))
            assert _served(s) == {EL: {"euroleague"}}

    def test_stale_routed_provider_falls_back_and_returns_when_fresh(self):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "fake", EL, NOW - timedelta(minutes=10))  # the backup sync
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=6, seconds=1))
            assert _served(s) == {EL: {"fake"}}
            _record_success(s, "euroleague", EL, NOW - timedelta(minutes=30))
            assert _served(s) == {EL: {"euroleague"}}

    def test_threshold_is_configurable(self, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_STALE_HOURS", "12")
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=8))
            assert _served(s) == {EL: {"euroleague"}}

    def test_failures_after_a_fresh_success_do_not_switch_early(self, monkeypatch):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=2))
            health.record_fetch_health(s, {"euroleague": health.ProviderRun(
                [EL], FetchOutcome(errors={EL: "HTTP 500"}))}, (NOW - timedelta(hours=1)).isoformat())
            s.commit()
            assert _served(s) == {EL: {"euroleague"}}

    def test_stale_routed_without_a_fresher_default_keeps_routed(self):
        """A competition the default cannot serve (no backup success, e.g. a cup
        TheSportsDB has no league id for) keeps its stale routed rows rather
        than an empty list."""
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "fake", EL, NOW - timedelta(hours=9))
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=8))
            assert _served(s) == {EL: {"euroleague"}}
            assert health.decide({EL: "euroleague"}, "fake", frozenset(),
                                 health.last_success_by(s, [("euroleague", EL), ("fake", EL)]),
                                 NOW, 6) == {EL: ("euroleague", "stale_no_fallback")}

    def test_never_synced_routed_provider_falls_back(self):
        with SessionLocal() as s:
            _seed_both(s)
            assert _served(s) == {EL: {"fake"}}

    def test_a_success_for_another_competition_does_not_count(self):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "euroleague", "comp:eurocup", NOW)
            assert _served(s) == {EL: {"fake"}}

    def test_stale_hours_zero_turns_the_fallback_off(self, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_STALE_HOURS", "0")
        with SessionLocal() as s:
            _seed_both(s)
            assert _served(s) == {EL: {"euroleague"}}  # the #532 rule alone

    @pytest.mark.parametrize("hours_ago", [None, 1, 7])
    def test_never_two_providers_for_one_competition(self, hours_ago):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "fake", EL, NOW)
            if hours_ago is not None:
                _record_success(s, "euroleague", EL, NOW - timedelta(hours=hours_ago))
            served = _served(s)
            assert len(served[EL]) == 1

    def test_active_provider_map_and_reads_agree(self):
        with SessionLocal() as s:
            _seed_both(s)
            _record_success(s, "fake", EL, NOW - timedelta(minutes=10))
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=7))
            assert active_provider_map(s, now=NOW) == ({}, "fake")
            assert registry.active_provider_for(EL, s, now=NOW) == "fake"
            _record_success(s, "euroleague", EL, NOW)
            assert active_provider_map(s, now=NOW) == ({EL: "euroleague"}, "fake")
            assert registry.active_provider_for(EL, s, now=NOW) == "euroleague"

    def test_detail_follows_the_decision(self):
        with SessionLocal() as s:
            games = _seed_both(s)
            for key in ("fb-el", "rt-el"):
                g = games[key]
                game_detail_repository.upsert(s, NormalizedGameDetail(
                    game_id=g.id, provider=g.provider, external_id=g.external_id))
            s.commit()
            both = [games["fb-el"].id, games["rt-el"].id]
            assert set(service.visible_details(s, both, now=NOW)) == {games["fb-el"].id}
            _record_success(s, "euroleague", EL, NOW)
            assert set(service.visible_details(s, both, now=NOW)) == {games["rt-el"].id}

    def test_consumer_and_admin_view_as_agree(self, admin_client, user_client):
        real_now = datetime.now(tz=timezone.utc)
        with SessionLocal() as s:
            games = _seed_both(s)
            _record_success(s, "fake", EL, real_now - timedelta(minutes=10))
            _record_success(s, "euroleague", EL, real_now - timedelta(hours=7))

        def el_ids(body):
            return {g["id"] for g in body["games"] if g["competition_id"] == EL
                    and g["start_time"].startswith("2999")}
        stale_admin = el_ids(admin_client.get("/api/results/guy").json())
        stale_me = el_ids(user_client.get("/api/me/results").json())
        assert stale_admin == stale_me == {games["fb-el"].id}
        with SessionLocal() as s:
            _record_success(s, "euroleague", EL, real_now)
        fresh_admin = el_ids(admin_client.get("/api/results/guy").json())
        fresh_me = el_ids(user_client.get("/api/me/results").json())
        assert fresh_admin == fresh_me == {games["rt-el"].id}


# ── 5. Backup sync ──────────────────────────────────────────────────────────────

class TestBackupSync:
    def _router(self, default, routed, backup=True):
        return RoutingProvider({"fake": default, "euroleague": routed}, {EL: "euroleague"},
                               "fake", backup=backup)

    def test_default_also_fetches_routed_competitions_after_its_own(self):
        default, routed = _Scripted("fake"), _Scripted("euroleague")
        out = self._router(default, routed).fetch([EL, NBA, IBL])
        assert default.calls == [[NBA, IBL, EL]]  # its own first, then the backup
        assert routed.calls == [[EL]]
        assert {(g.provider, g.competition_id) for g in out.games} == {
            ("fake", NBA), ("fake", IBL), ("fake", EL), ("euroleague", EL)}
        # The primary view is the routed one; the backup is reported apart.
        assert out.fetched_counts == {NBA: 1, IBL: 1, EL: 1}
        assert out.backup.fetched_counts == {EL: 1}

    def test_backup_errors_and_429_stay_out_of_the_primary_view(self):
        default = _Scripted("fake", limited={EL})
        routed = _Scripted("euroleague")
        out = self._router(default, routed).fetch([EL, NBA])
        assert out.not_checked == [] and out.errors == {}
        assert out.backup.not_checked == [EL]
        assert out.provider_retry_after == {"fake": 60.0}  # the default is still blocked

    def test_backup_error_is_reported_under_backup(self):
        out = self._router(_Scripted("fake", errors={EL: "HTTP 500"}),
                           _Scripted("euroleague")).fetch([EL, NBA])
        assert out.errors == {} and out.backup.errors == {EL: "HTTP 500"}

    def test_a_blocked_default_sends_no_backup_requests(self):
        default = _Scripted("fake")
        router = self._router(default, _Scripted("euroleague"))
        router.set_blocked({"fake"})
        out = router.fetch([EL, NBA])
        assert default.calls == [] and out.not_checked == [NBA]
        assert out.backup.not_checked == [EL]

    def test_backup_rows_are_fresh_but_hidden_while_routed_is_healthy(
            self, clean, follows, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")
        _at(monkeypatch, NOW)
        summary = _sync(self._router(_Scripted("fake"), _Scripted("euroleague")), [EL, NBA])
        assert summary["backup"] == {"provider": "fake", "competitions": [EL],
                                     "fetched_counts": {EL: 1}, "errors": {},
                                     "not_checked": []}
        assert _health("fake", EL).last_success_at == NOW.isoformat()
        with SessionLocal() as s:
            assert {r.provider for r in s.query(GameResultRow).filter_by(competition_id=EL)} == {
                "fake", "euroleague"}
            assert _served(s, now=NOW) == {EL: {"euroleague"}}
            # The routed provider then breaks: after the threshold the backup shows.
        for hour in range(1, 8):
            _at(monkeypatch, NOW + timedelta(hours=hour))
            _sync(self._router(_Scripted("fake"),
                               _Scripted("euroleague", errors={EL: "HTTP 500"})), [EL, NBA])
        with SessionLocal() as s:
            assert _served(s, now=NOW + timedelta(hours=7)) == {EL: {"fake"}}

    def test_get_provider_turns_backup_on_by_default_and_the_flag_turns_it_off(
            self, clean, monkeypatch):
        default, routed = _Scripted("fake"), _Scripted("euroleague")
        monkeypatch.setitem(registry.REGISTRY, "fake", lambda: default)
        monkeypatch.setitem(registry.REGISTRY, "euroleague", lambda: routed)
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague")
        get_provider().fetch([EL, NBA])
        assert default.calls == [[NBA, EL]]
        monkeypatch.setenv("RESULTS_PROVIDER_BACKUP_SYNC", "false")
        get_provider().fetch([EL, NBA])
        assert default.calls[-1] == [NBA]

    def test_thesportsdb_backup_keeps_its_pacing_and_stops_on_a_429(self, monkeypatch):
        """The backup goes through the same TheSportsDB fetch call, so its spacing
        and its 429 stop cover the backup requests too."""
        monkeypatch.setenv("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "7")
        monkeypatch.setenv("RESULTS_SEASONS", "2026-2027")
        monkeypatch.setenv("RESULTS_RECENT_DAYS", "0")
        clock = {"t": 0.0}
        sent: list[tuple[float, str]] = []

        def handler(request):
            sent.append((clock["t"], request.url.params["id"]))
            if len(sent) == 5:  # the backup competition's first request
                return httpx.Response(429, headers={"Retry-After": "120"})
            return httpx.Response(200, json={"events": []})

        tsdb = TheSportsDBProvider(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda sec: clock.__setitem__("t", clock["t"] + max(0.0, sec)),
            clock=lambda: clock["t"])
        router = RoutingProvider({"thesportsdb": tsdb, "euroleague": _Scripted("euroleague")},
                                 {EL: "euroleague", "comp:eurocup": "euroleague"},
                                 "thesportsdb", backup=True)
        out = router.fetch([EL, "comp:eurocup", NBA, IBL])
        # NBA and IBL (2 requests each), then EuroLeague's first backup request 429s.
        assert len(sent) == 5
        gaps = [b[0] - a[0] for a, b in zip(sent, sent[1:])]
        assert min(gaps) >= 7
        assert out.not_checked == [] and out.fetched_counts[NBA] == 0
        assert out.backup.not_checked == [EL, "comp:eurocup"]
        assert out.provider_retry_after == {"thesportsdb": 120.0}


# ── No routes: exactly today's behaviour ────────────────────────────────────────

class TestNoRoutesUnchanged:
    def test_requests_and_summary_are_identical(self, clean, monkeypatch):
        default = _Scripted("fake")
        monkeypatch.setitem(registry.REGISTRY, "fake", lambda: default)
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "euroleague")  # unrelated switch
        provider = get_provider()
        assert provider is default
        _at(monkeypatch, NOW)
        with SessionLocal() as s:
            summary = sync_service.sync_results(s, competition_ids=[EL, NBA], force=True)
        assert default.calls == [[EL, NBA]]
        assert set(summary) == {
            "status", "provider", "competitions", "fetched", "created", "updated",
            "fetched_counts", "errors", "not_checked", "rate_limited_until",
            "rate_limited_until_by_provider", "synced_at"}
        assert summary["provider"] == "fake" and summary["status"] == "ok"

    def test_reads_ignore_health_without_routes(self, clean, follows):
        with SessionLocal() as s:
            games = _seed_both(s)
            # Even a long-dead default provider is served: there is nothing to fall back to.
            _record_success(s, "fake", EL, NOW - timedelta(days=30))
            ids = {g.id for g in service.personalized_results(s, object(), now=NOW).games
                   if g.start_time.startswith("2999")}
            assert ids == {games["fb-el"].id, games["nba"].id}
            assert active_provider_map(s, now=NOW) == ({}, "fake")


# ── Ops visibility ──────────────────────────────────────────────────────────────

class TestOpsView:
    def test_view_shows_health_and_per_competition_serving_provider(self, clean, monkeypatch):
        monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", f"{EL}=euroleague,{IBL}=winner")
        monkeypatch.setenv("RESULTS_PROVIDER_DISABLED", "winner")
        monkeypatch.setenv("RESULTS_COMPETITIONS", f"{EL},{IBL},{NBA}")
        with SessionLocal() as s:
            _record_success(s, "fake", EL, NOW - timedelta(minutes=30))
            _record_success(s, "euroleague", EL, NOW - timedelta(hours=8))
            view = health.ops_view(s, now=NOW)
        assert view["default_provider"] == "fake" and view["stale_hours"] == 6
        assert view["backup_sync"] is True
        provs = {p["provider"]: p for p in view["providers"]}
        assert provs["winner"]["enabled"] is False and provs["euroleague"]["enabled"] is True
        assert provs["euroleague"]["last_success_at"] == (NOW - timedelta(hours=8)).isoformat()
        comps = {c["competition_id"]: c for c in view["competitions"]}
        assert comps[EL]["routed_to"] == "euroleague"
        assert comps[EL]["serving"] == "fake" and comps[EL]["reason"] == "stale"
        assert comps[EL]["freshness"]["euroleague"]["age_hours"] == 8.0
        assert comps[EL]["freshness"]["fake"]["age_hours"] == 0.5
        assert comps[IBL]["serving"] == "fake" and comps[IBL]["reason"] == "disabled"
        assert comps[NBA]["routed_to"] is None and comps[NBA]["reason"] == "default"

    def test_view_shows_the_current_block(self, clean, monkeypatch):
        _at(monkeypatch, NOW)
        _sync(_Scripted("fake", limited={NBA}, retry=600), [NBA])
        with SessionLocal() as s:
            view = health.ops_view(s, now=NOW)
        provs = {p["provider"]: p for p in view["providers"]}
        assert provs["fake"]["rate_limited_until"] == (NOW + timedelta(seconds=600)).isoformat()

    def test_admin_endpoint_shows_health_and_is_admin_only(
            self, clean, client, user_client, admin_client):
        assert client.get("/api/results/sync/state").status_code == 401
        assert user_client.get("/api/results/sync/state").status_code == 403
        body = admin_client.get("/api/results/sync/state").json()
        assert {"last_attempt_at", "last_status", "last_summary"} <= set(body)
        assert body["health"]["default_provider"] == "fake"
        assert isinstance(body["health"]["providers"], list)
        assert {c["competition_id"] for c in body["health"]["competitions"]} >= {NBA, EL}
