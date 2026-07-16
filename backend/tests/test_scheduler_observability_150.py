"""M7-4 (#150) + M7-8 (#154) — durable scheduler/notification observability.

Everything reads durable rows (cycles, lease, worker_status, events) so the
API process can explain what the WORKER process did across restarts. Health
axes stay separate: Telegram trouble degrades notifications, never ingestion.
No secret appears in any response.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text


def _now():
    return datetime.now(tz=timezone.utc)


@pytest.fixture
def session(client, monkeypatch):
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        for table in ("scheduler_cycles", "notification_story_members",
                      "notification_events", "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.execute(text("DELETE FROM worker_status"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                       "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        s.commit()
        yield s
        s.rollback()
        for table in ("scheduler_cycles", "notification_story_members",
                      "notification_events", "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.execute(text("DELETE FROM worker_status"))
        s.commit()


def _seed_cycle(session, cid, status, minutes_ago, trigger="scheduled",
                source_results=None):
    from app.db.orm_models import SchedulerCycleRow
    ts = (_now() - timedelta(minutes=minutes_ago)).isoformat()
    session.add(SchedulerCycleRow(
        id=cid, trigger=trigger, requested_at=ts, started_at=ts, finished_at=ts,
        status=status, source_results=source_results,
    ))
    session.commit()


def _seed_worker(session, state="idle", seconds_ago=5):
    session.execute(text(
        "INSERT INTO worker_status (id, last_seen_at, state, owner, interval_seconds) "
        "VALUES (1, :t, :s, 'pid=1 host=t', 300)"),
        {"t": (_now() - timedelta(seconds=seconds_ago)).isoformat(), "s": state})
    session.commit()


def _seed_event(session, eid, status, minutes_ago=1, attempted=True):
    from app.db.orm_models import NotificationEventRow
    ts = (_now() - timedelta(minutes=minutes_ago)).isoformat()
    session.add(NotificationEventRow(
        id=eid, profile_id="guy", policy_version="v1", status=status,
        created_at=ts, canonical_article_id="rss_x", canonical_headline="כותרת",
        source="walla", url="https://example.test/x", tier="push",
        attempt_count=1 if attempted else 0,
        last_attempt_at=ts if attempted else None,
        final_at=ts if status in ("sent", "failed_final") else None,
    ))
    session.commit()


class TestSchedulerHealth:
    def test_healthy_worker_and_fresh_success(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        _seed_worker(session, "idle", seconds_ago=5)
        _seed_cycle(session, "cycle_h1", "succeeded", minutes_ago=2)
        r = admin_client.get("/api/scheduler/health")
        assert r.status_code == 200
        body = r.json()
        assert body["scheduler_enabled"] is True
        assert body["stale"] is False
        assert body["consecutive_failures"] == 0
        assert body["last_successful_cycle"]["id"] == "cycle_h1"
        assert body["next_expected_run_at"] is not None
        assert body["ingestion_degraded"] is False

    def test_dead_worker_is_stale_with_a_reason(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "300")
        monkeypatch.setenv("SCHEDULER_MAX_RUN_SECONDS", "900")
        _seed_worker(session, "idle", seconds_ago=5000)   # > interval+max_run
        _seed_cycle(session, "cycle_h1", "succeeded", minutes_ago=90)
        body = admin_client.get("/api/scheduler/health").json()
        assert body["stale"] is True
        assert "heartbeat" in body["stale_reason"]
        assert body["ingestion_degraded"] is True

    def test_disabled_scheduler_is_never_stale(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        body = admin_client.get("/api/scheduler/health").json()
        assert body["scheduler_enabled"] is False
        assert body["stale"] is False

    def test_consecutive_failures_counted(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        _seed_worker(session)
        _seed_cycle(session, "cycle_ok", "succeeded", minutes_ago=30)
        _seed_cycle(session, "cycle_f1", "failed", minutes_ago=20)
        _seed_cycle(session, "cycle_f2", "failed", minutes_ago=10)
        body = admin_client.get("/api/scheduler/health").json()
        assert body["consecutive_failures"] == 2
        assert body["ingestion_degraded"] is True

    def test_telegram_trouble_degrades_notifications_not_ingestion(
            self, admin_client, session, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
        _seed_worker(session, "idle", seconds_ago=5)
        _seed_cycle(session, "cycle_ok", "succeeded", minutes_ago=1)
        _seed_event(session, "notif_u1", "unknown")
        body = admin_client.get("/api/scheduler/health").json()
        assert body["notifications_degraded"] is True
        assert body["ingestion_degraded"] is False          # the separation
        assert body["stale"] is False

    def test_no_secrets_anywhere(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET_TOKEN_XYZ")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
        _seed_worker(session)
        for path in ("/api/scheduler/health", "/api/scheduler/cycles",
                     "/api/notifications/health", "/api/notifications/events",
                     "/api/ingest/scheduler/status"):
            body = admin_client.get(path).text
            assert "SECRET_TOKEN_XYZ" not in body, path
            assert "987654321" not in body, path


class TestCycleHistoryAndEvents:
    def test_cycles_endpoint_returns_history_with_summaries(self, admin_client, session):
        _seed_cycle(session, "cycle_a", "succeeded", minutes_ago=10,
                    source_results=[{"source_id": "walla_sport", "inserted": 2,
                                     "fetched": 5, "failed": 0,
                                     "skipped_duplicate": 3, "skipped_filtered": 0,
                                     "errors": []}])
        _seed_cycle(session, "cycle_b", "skipped_active_run", minutes_ago=5,
                    trigger="manual")
        r = admin_client.get("/api/scheduler/cycles?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert [c["id"] for c in body] == ["cycle_b", "cycle_a"]
        assert body[1]["source_results"][0]["inserted"] == 2

    def test_notification_events_endpoint(self, admin_client, session):
        _seed_event(session, "notif_s1", "sent", minutes_ago=3)
        _seed_event(session, "notif_p1", "pending", minutes_ago=1, attempted=False)
        r = admin_client.get("/api/notifications/events")
        assert r.status_code == 200
        body = r.json()
        assert {e["id"] for e in body} == {"notif_s1", "notif_p1"}
        assert all("canonical_headline" in e for e in body)

    def test_notifications_health_counts(self, admin_client, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
        _seed_event(session, "notif_s1", "sent")
        _seed_event(session, "notif_p1", "pending", attempted=False, minutes_ago=30)
        _seed_event(session, "notif_u1", "unknown")
        body = admin_client.get("/api/notifications/health").json()
        assert body["sent"] == 1
        assert body["pending"] == 1
        assert body["unknown"] == 1
        assert body["oldest_pending_age_seconds"] > 1000

    def test_legacy_status_endpoint_reads_durable_state(self, admin_client, session,
                                                        monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        _seed_worker(session, "idle", seconds_ago=5)
        _seed_cycle(session, "cycle_leg", "succeeded", minutes_ago=2,
                    source_results=[{"source_id": "walla_sport", "inserted": 1,
                                     "fetched": 2, "failed": 0,
                                     "skipped_duplicate": 1, "skipped_filtered": 0,
                                     "errors": []}])
        body = admin_client.get("/api/ingest/scheduler/status").json()
        assert body["enabled"] is True
        assert body["running"] is True                    # worker alive
        assert body["last_status"] == "ok"
        assert body["last_result_summary"][0]["source_id"] == "walla_sport"
        assert body["next_run_at"] is not None


class TestAdminResetScript:
    def test_dry_run_changes_nothing(self, session, monkeypatch, capsys):
        import scripts.reset_admin_password as script
        monkeypatch.setenv("AUTH_ADMIN_EMAIL", "")
        monkeypatch.setenv("AUTH_ADMIN_PASSWORD", "")
        monkeypatch.setattr("sys.argv", ["reset_admin_password.py"])
        assert script.main() == 1                        # refuses without config