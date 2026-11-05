"""Results sync leaves a trace before it calls anyone, and never overlaps (#197).

Manual (admin) and worker syncs run in different processes. Overlap spends the
provider's rate limit twice, and a crash inside the provider used to leave no
record of the attempt at all.
"""
import threading
from datetime import timedelta

import pytest

from app.db.database import SessionLocal
from app.db.orm_models import ResultsSyncLeaseRow, ResultsSyncStateRow
from app.repositories import game_result_repository
from app.results import sync_service
from app.results.providers.base import FetchOutcome
from app.results.sync_service import get_sync_state, sync_results


class _Provider:
    name = "test"

    def __init__(self, on_fetch=None):
        self.calls = 0
        self.on_fetch = on_fetch

    def fetch(self, competition_ids):
        self.calls += 1
        if self.on_fetch:
            self.on_fetch()
        return FetchOutcome()


@pytest.fixture
def clean_state(client):
    def wipe():
        with SessionLocal() as s:
            s.query(ResultsSyncStateRow).delete()
            s.query(ResultsSyncLeaseRow).delete()
            s.commit()

    wipe()
    yield
    wipe()


def _sync(session, provider, force=True):
    return sync_results(session, provider=provider, force=force, competition_ids=["comp:nba"])


def _raise():
    raise RuntimeError("boom")


def test_unexpected_provider_exception_is_recorded_not_raised(clean_state):
    with SessionLocal() as s:
        summary = _sync(s, _Provider(on_fetch=_raise))
        state = get_sync_state(s)
    assert summary["status"] == "error"
    assert summary["errors"] == {"provider": "RuntimeError"}
    assert state["last_attempt_at"] is not None
    assert state["last_status"] == "error"
    assert state["last_success_at"] is None


def test_attempt_is_visible_to_other_sessions_before_the_provider_runs(clean_state):
    seen = []

    def read_state():
        with SessionLocal() as other:
            seen.append(get_sync_state(other)["last_attempt_at"])

    with SessionLocal() as s:
        _sync(s, _Provider(on_fetch=read_state))
    assert seen[0] is not None


def test_failing_provider_constructor_still_records_the_attempt(clean_state, monkeypatch):
    def no_provider():
        raise RuntimeError("unknown provider")

    monkeypatch.setattr(sync_service, "get_provider", no_provider)
    with SessionLocal() as s:
        summary = sync_results(s, force=True, competition_ids=["comp:nba"])
        state = get_sync_state(s)
    assert summary["status"] == "error"
    assert summary["provider"] == "unknown"
    assert state["last_attempt_at"] is not None


@pytest.mark.parametrize("force", [True, False])
def test_a_second_sync_does_not_call_the_provider_while_one_runs(clean_state, force):
    second = _Provider()
    results = []

    def overlap():
        with SessionLocal() as other:
            results.append(_sync(other, second, force=force))

    with SessionLocal() as s:
        first = _sync(s, _Provider(on_fetch=overlap))
    assert second.calls == 0
    assert results[0]["skipped"] == "in_progress"
    assert first["status"] == "ok"


def test_only_one_of_many_concurrent_syncs_reaches_the_provider(clean_state):
    count = 6
    barrier = threading.Barrier(count)
    others_done = threading.Event()
    outcomes = []
    lock = threading.Lock()
    finished = []

    provider = _Provider(on_fetch=lambda: others_done.wait(timeout=30))

    def run():
        barrier.wait(timeout=30)
        with SessionLocal() as s:
            result = _sync(s, provider)
        with lock:
            outcomes.append(result)
            finished.append(1)
            if len(finished) == count - 1:
                others_done.set()

    threads = [threading.Thread(target=run) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert provider.calls == 1
    assert sum(1 for o in outcomes if o.get("skipped") == "in_progress") == count - 1
    assert sum(1 for o in outcomes if o.get("status") == "ok") == 1


def test_the_lease_is_free_after_a_failed_sync(clean_state):
    with SessionLocal() as s:
        _sync(s, _Provider(on_fetch=_raise))
        next_provider = _Provider()
        assert _sync(s, next_provider)["status"] == "ok"
    assert next_provider.calls == 1


def test_a_database_failure_keeps_the_attempt_and_frees_the_lease(clean_state, monkeypatch):
    def broken(session, games):
        raise RuntimeError("disk full")

    monkeypatch.setattr(game_result_repository, "upsert_many", broken)
    with SessionLocal() as s:
        with pytest.raises(RuntimeError):
            _sync(s, _Provider())
    monkeypatch.undo()

    with SessionLocal() as s:
        assert get_sync_state(s)["last_attempt_at"] is not None
        next_provider = _Provider()
        assert _sync(s, next_provider)["status"] == "ok"
    assert next_provider.calls == 1


def test_a_dead_holder_blocks_until_stale_and_is_then_taken_over(clean_state, monkeypatch):
    t0 = sync_service._now()
    monkeypatch.setattr(sync_service, "_now", lambda: t0)
    with SessionLocal() as s:
        assert sync_service._try_acquire_lease(s, "dead-process")

        # Just inside the stale window: still held.
        monkeypatch.setattr(
            sync_service, "_now",
            lambda: t0 + timedelta(seconds=sync_service.LEASE_STALE_AFTER_SECONDS - 1),
        )
        waiting = _Provider()
        assert _sync(s, waiting)["skipped"] == "in_progress"
        assert waiting.calls == 0

        # Past it: the crashed process cannot block results forever.
        monkeypatch.setattr(
            sync_service, "_now",
            lambda: t0 + timedelta(seconds=sync_service.LEASE_STALE_AFTER_SECONDS + 1),
        )
        taker = _Provider()
        assert _sync(s, taker)["status"] == "ok"
    assert taker.calls == 1


def test_an_old_holder_cannot_release_a_lease_taken_over_from_it(clean_state, monkeypatch):
    t0 = sync_service._now()
    monkeypatch.setattr(sync_service, "_now", lambda: t0)
    with SessionLocal() as s:
        assert sync_service._try_acquire_lease(s, "slow-process")
        monkeypatch.setattr(
            sync_service, "_now",
            lambda: t0 + timedelta(seconds=sync_service.LEASE_STALE_AFTER_SECONDS + 1),
        )
        assert sync_service._try_acquire_lease(s, "new-holder")

        sync_service._release_lease(s, "slow-process")

        assert not sync_service._try_acquire_lease(s, "third")
