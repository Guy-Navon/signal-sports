"""M7-1 (#147) — canonical orchestration + durable DB-backed single-flight.

The guard contract, stated honestly: at most one corpus-mutating cycle at a
time ON THIS MACHINE, across processes sharing this SQLite file — enforced by
one conditional UPDATE on the scheduler_lease row. Dead holders are recovered
by stale-heartbeat takeover; live holders can never be stolen.
"""

import threading
import time
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.ingestion.orchestration import (
    STATUS_ABANDONED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_SUCCEEDED,
    STATUS_WARNINGS,
    TRIGGER_MANUAL,
    TRIGGER_RUN_NOW,
    TRIGGER_SCHEDULED,
    _try_acquire_lease,
    current_lease,
    orchestrate_cycle,
)

RUN_INGESTION = "app.ingestion.ingestion_service.run_ingestion"


def _result(source_id="walla_sport", inserted=3, fetched=5, failed=0, errors=None):
    return types.SimpleNamespace(
        source_id=source_id, fetched=fetched, inserted=inserted,
        skipped_duplicate=2, skipped_filtered=0, failed=failed,
        errors=errors or [],
    )


@pytest.fixture
def session(_application):
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        # Each test starts with a free lease and no cycle rows.
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                       "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        s.commit()
        yield s
        s.rollback()
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                       "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        s.commit()


def _cycles(session, status=None):
    q = "SELECT id, trigger, status, error_summary FROM scheduler_cycles"
    if status:
        q += f" WHERE status = '{status}'"
    return session.execute(text(q)).fetchall()


# ══════════════════════════════════════════════════════════════════════════════
# Lease primitives
# ══════════════════════════════════════════════════════════════════════════════

class TestLease:
    def test_free_lease_is_acquired(self, session):
        acquired, abandoned = _try_acquire_lease(session, "cycle_a")
        assert acquired and abandoned is None
        assert current_lease(session)["cycle_id"] == "cycle_a"

    def test_fresh_holder_is_never_stolen(self, session):
        _try_acquire_lease(session, "cycle_a")
        acquired, _ = _try_acquire_lease(session, "cycle_b")
        assert not acquired
        assert current_lease(session)["cycle_id"] == "cycle_a"

    def test_stale_holder_is_taken_over(self, session):
        _try_acquire_lease(session, "cycle_dead")
        stale = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
        session.execute(text(
            "UPDATE scheduler_lease SET heartbeat_at = :hb WHERE id = 1"), {"hb": stale})
        session.commit()

        acquired, abandoned = _try_acquire_lease(session, "cycle_new")
        assert acquired
        assert abandoned == "cycle_dead"
        assert current_lease(session)["cycle_id"] == "cycle_new"

    def test_release_is_owner_scoped(self, session):
        from app.ingestion.orchestration import _release_lease
        _try_acquire_lease(session, "cycle_a")
        _release_lease(session, "cycle_someone_else")   # must be a no-op
        assert current_lease(session)["cycle_id"] == "cycle_a"
        _release_lease(session, "cycle_a")
        assert current_lease(session) is None


# ══════════════════════════════════════════════════════════════════════════════
# orchestrate_cycle
# ══════════════════════════════════════════════════════════════════════════════

class TestOrchestration:
    def test_success_finalizes_cycle_and_releases(self, session):
        with patch(RUN_INGESTION, return_value=[_result()]):
            out = orchestrate_cycle(TRIGGER_MANUAL)
        assert out.status == STATUS_SUCCEEDED
        assert not out.skipped
        assert current_lease(session) is None
        rows = _cycles(session)
        assert len(rows) == 1
        assert rows[0][2] == STATUS_SUCCEEDED

    def test_source_errors_degrade_to_warnings(self, session):
        results = [_result(), _result(source_id="ynet_sport", inserted=0,
                                      fetched=0, failed=1, errors=["Fetch error: boom"])]
        with patch(RUN_INGESTION, return_value=results):
            out = orchestrate_cycle(TRIGGER_RUN_NOW)
        assert out.status == STATUS_WARNINGS
        assert "boom" in (out.error_summary or "")
        assert current_lease(session) is None

    def test_total_failure_is_reported_honestly_and_releases(self, session):
        with patch(RUN_INGESTION, side_effect=RuntimeError("db exploded")):
            out = orchestrate_cycle(TRIGGER_MANUAL)
        assert out.status == STATUS_FAILED
        assert "db exploded" in out.error_summary
        assert current_lease(session) is None            # release on EVERY exit path
        rows = _cycles(session, STATUS_FAILED)
        assert len(rows) == 1

    def test_skip_records_a_durable_cycle_row(self, session):
        _try_acquire_lease(session, "cycle_other_process")
        with patch(RUN_INGESTION, return_value=[_result()]):
            out = orchestrate_cycle(TRIGGER_SCHEDULED)
        assert out.skipped
        assert out.status == STATUS_SKIPPED
        assert out.active_run["cycle_id"] == "cycle_other_process"
        rows = _cycles(session, STATUS_SKIPPED)
        assert len(rows) == 1
        assert rows[0][1] == TRIGGER_SCHEDULED
        # The holder is untouched.
        assert current_lease(session)["cycle_id"] == "cycle_other_process"

    def test_stale_takeover_marks_previous_cycle_abandoned(self, session):
        # Simulate a crash: a running cycle row + a held lease with a dead heartbeat.
        from app.db.orm_models import SchedulerCycleRow
        session.add(SchedulerCycleRow(
            id="cycle_dead", trigger=TRIGGER_SCHEDULED,
            requested_at=datetime.now(tz=timezone.utc).isoformat(),
            started_at=datetime.now(tz=timezone.utc).isoformat(),
            status=STATUS_RUNNING,
        ))
        session.commit()
        _try_acquire_lease(session, "cycle_dead")
        stale = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
        session.execute(text(
            "UPDATE scheduler_lease SET heartbeat_at = :hb WHERE id = 1"), {"hb": stale})
        session.commit()

        with patch(RUN_INGESTION, return_value=[_result()]):
            out = orchestrate_cycle(TRIGGER_STARTUP := "startup_catchup")
        assert out.status == STATUS_SUCCEEDED

        dead = session.execute(text(
            "SELECT status, error_summary FROM scheduler_cycles WHERE id='cycle_dead'"
        )).fetchone()
        assert dead[0] == STATUS_ABANDONED
        assert "stale" in dead[1]

    def test_concurrent_triggers_exactly_one_runs(self, session):
        """Two triggers race: exactly one mutates, the other records a skip."""
        release_gate = threading.Event()

        def slow_ingestion(sess, source_id=None):
            release_gate.wait(timeout=10)
            return [_result()]

        outcomes = {}

        def call(name):
            with patch(RUN_INGESTION, side_effect=slow_ingestion):
                outcomes[name] = orchestrate_cycle(TRIGGER_MANUAL)

        t1 = threading.Thread(target=call, args=("a",))
        t1.start()
        time.sleep(1.0)          # let t1 acquire and enter the slow pipeline
        t2 = threading.Thread(target=call, args=("b",))
        t2.start()
        t2.join(timeout=15)
        release_gate.set()
        t1.join(timeout=15)

        statuses = sorted(o.status for o in outcomes.values())
        assert statuses == [STATUS_SKIPPED, STATUS_SUCCEEDED], statuses

    def test_rerun_inserts_nothing_new(self, session):
        """Article idempotency across a retried cycle: the second run's URL dedup
        skips everything the first inserted (the existing per-article contract)."""
        from app.ingestion.adapters.base import RawSourceItem
        from app.db.orm_models import ArticleRow

        items = [RawSourceItem(
            source_id="walla_sport",
            url="https://example.test/m7/idempotent-1",
            title="מכבי תל אביב ניצחה את הפועל ירושלים בליגת ווינר",
            published_at=datetime.now(tz=timezone.utc),
        )]
        fake_adapter = types.SimpleNamespace(fetch=lambda: list(items))
        with patch("app.ingestion.ingestion_service.build_adapter",
                   return_value=fake_adapter):
            out1 = orchestrate_cycle(TRIGGER_MANUAL, source_id="walla_sport")
            out2 = orchestrate_cycle(TRIGGER_MANUAL, source_id="walla_sport")

        assert out1.source_results[0].inserted == 1
        assert out2.source_results[0].inserted == 0
        assert out2.source_results[0].skipped_duplicate == 1
        n = session.query(ArticleRow).filter(
            ArticleRow.url == "https://example.test/m7/idempotent-1").count()
        assert n == 1
        # cleanup
        session.query(ArticleRow).filter(
            ArticleRow.url == "https://example.test/m7/idempotent-1").delete(
            synchronize_session=False)
        session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# The endpoints share the guard
# ══════════════════════════════════════════════════════════════════════════════

class TestMigrationCoverage:
    def test_every_orm_column_reaches_a_legacy_database(self):
        """THE CLASS LOCK for the #155 Phase-B finding: tests create fresh
        schemas via create_all, so a missing soft-migration ALTER for a column
        added to an EXISTING table is invisible here and fatal on the live DB
        (ingestion_runs.cycle_id failed exactly that way mid-cycle).

        This test builds a LEGACY-shaped table (without the new columns), runs
        the soft migrations against it, and asserts the ORM's view of the world
        exists on disk afterwards — for every table the migration list touches.
        """
        import sqlite3
        import tempfile
        from pathlib import Path

        from sqlalchemy import create_engine, inspect

        from app.db import database as db_module
        from app.db.orm_models import Base

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy.db"
            # A legacy ingestion_runs WITHOUT the M7 column:
            conn = sqlite3.connect(path)
            conn.execute(
                "CREATE TABLE ingestion_runs (id TEXT PRIMARY KEY, source_id TEXT, "
                "started_at TEXT, finished_at TEXT, status TEXT, fetched_count INT, "
                "inserted_count INT, skipped_duplicate_count INT, failed_count INT, "
                "error_message TEXT)")
            conn.commit()
            conn.close()

            eng = create_engine(f"sqlite:///{path.as_posix()}")
            Base.metadata.create_all(bind=eng)      # creates only MISSING tables
            db_module._apply_migrations(eng)

            on_disk = {c["name"] for c in inspect(eng).get_columns("ingestion_runs")}
            orm = {c.name for c in Base.metadata.tables["ingestion_runs"].columns}
            missing = orm - on_disk
            assert missing == set(), (
                f"ORM columns missing from a legacy database after migrations: "
                f"{missing} — add them to _apply_migrations")
            eng.dispose()


class TestEndpointsShareTheGuard:
    def test_manual_endpoint_409_when_lease_held_elsewhere(self, admin_client, session):
        _try_acquire_lease(session, "cycle_worker_process")
        r = admin_client.post("/api/ingest/run")
        assert r.status_code == 409
        body = r.json()["detail"]
        assert body["error"] == "ingestion_already_running"
        assert body["active_run"]["cycle_id"] == "cycle_worker_process"

    def test_run_now_endpoint_409_when_lease_held_elsewhere(self, admin_client, session):
        _try_acquire_lease(session, "cycle_worker_process")
        r = admin_client.post("/api/ingest/scheduler/run-now")
        assert r.status_code == 409

    def test_manual_endpoint_runs_and_records_cycle(self, admin_client, session):
        from app.ingestion.ingestion_service import SourceIngestResult
        real = SourceIngestResult(
            source_id="walla_sport", fetched=5, inserted=3,
            skipped_filtered=0, skipped_duplicate=2, failed=0,
        )
        with patch(RUN_INGESTION, return_value=[real]):
            r = admin_client.post("/api/ingest/run")
        assert r.status_code == 200
        rows = _cycles(session, STATUS_SUCCEEDED)
        assert len(rows) == 1
        assert rows[0][1] == TRIGGER_MANUAL
