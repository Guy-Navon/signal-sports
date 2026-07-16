"""M7-6 (#152) — the production PUSH planner for the pilot profile.

Feed eligibility is the source of truth: the planner calls the exact
build_feed path behind GET /api/feed/guy and reads story-level card
decisions. No second ruleset, no importance reconstruction.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.notifications.outbox import SUPPRESSED_WATERMARK, set_watermark
from app.notifications.planner import plan_cycle_notifications

PROFILE = "guy"
POLICY = "v1"


def _now():
    return datetime.now(tz=timezone.utc)


_IDS: list[str] = []


def _add_article(session, _id, *, title, importance="high", event_type="negotiation",
                 entities=("Maccabi Tel Aviv Basketball",), sport="basketball",
                 league="EuroLeague", cluster_id=None, hours_ago=1.0,
                 source="sport5_sport"):
    """A realistic rss_ row shaped like the seeded Maccabi-negotiation push
    (article_001's shape) — scored by the REAL engine, not stubbed."""
    from app.db.orm_models import ArticleRow
    _IDS.append(_id)
    session.add(ArticleRow(
        id=_id, source=source, source_display_name=source,
        url=f"https://example.test/{_id}",
        title=title, language="he",
        published_at=(_now() - timedelta(hours=hours_ago)).isoformat(),
        sport=sport, league=league, entities=list(entities),
        event_type=event_type, event_certainty="confirmed",
        importance=importance, confidence=0.92, tags=[],
        entity_ids=[], cluster_id=cluster_id,
    ))
    return _id


@pytest.fixture
def session(client, monkeypatch):
    # `client` enters the app lifespan: tables created, PROFILES SEEDED — the
    # planner scores through the real engine against the real guy profile.
    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    from app.db.database import SessionLocal, init_db
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        # DETERMINISTIC CORPUS: earlier test files leave rss_ rows (fake feeds)
        # behind in the shared test DB; the planner reads the REAL feed, so
        # leftovers would perturb exact-count assertions. The seeded article_0xx
        # scoring fixtures are untouched.
        s.execute(text("DELETE FROM articles WHERE id LIKE 'rss_%'"))
        s.execute(text("DELETE FROM cluster_edges"))
        s.execute(text("DELETE FROM story_clusters"))
        s.commit()
        yield s
        s.rollback()
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        if _IDS:
            s.execute(text("DELETE FROM story_clusters WHERE id LIKE 'cluster_t152%'"))
            from app.db.orm_models import ArticleRow
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(
                synchronize_session=False)
        s.commit()


def _events(session):
    return session.execute(text(
        "SELECT id, status, canonical_headline, tier FROM notification_events"
    )).fetchall()


class TestGating:
    def test_disabled_telegram_plans_nothing(self, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false")
        _add_article(session, "rss_t152_push1", title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        summary = plan_cycle_notifications(session)
        assert summary == {"skipped": "telegram_disabled"}
        assert _events(session) == []

    def test_no_watermark_plans_nothing(self, session):
        _add_article(session, "rss_t152_push1", title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        summary = plan_cycle_notifications(session)
        assert summary["no_watermark"] is True
        assert summary["created"] == []
        assert _events(session) == []


class TestPlanning:
    def test_push_story_creates_exactly_one_event(self, session):
        set_watermark(session, PROFILE, POLICY)
        _add_article(session, "rss_t152_push1",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()

        summary = plan_cycle_notifications(session)
        assert len(summary["created"]) == 1
        events = _events(session)
        assert len(events) == 1
        assert events[0][1] == "pending"
        assert events[0][3] == "push"
        assert "מכבי" in events[0][2]

    def test_second_cycle_suppresses_not_duplicates(self, session):
        set_watermark(session, PROFILE, POLICY)
        _add_article(session, "rss_t152_push1",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        plan_cycle_notifications(session)
        summary2 = plan_cycle_notifications(session)
        assert summary2["created"] == []
        assert summary2["already_notified"] >= 1
        assert len(_events(session)) == 1

    def test_lower_tiers_create_nothing(self, session):
        set_watermark(session, PROFILE, POLICY)
        # A generic low-importance story — visible at most as feed/low for Guy.
        _add_article(session, "rss_t152_low1",
                     title="סיכום שבוע בליגה הספרדית בכדורגל",
                     importance="low", event_type="news", entities=(),
                     sport="football", league=None)
        session.commit()
        summary = plan_cycle_notifications(session)
        assert summary["created"] == []
        assert _events(session) == []
        assert summary["ignored_non_push"] >= 0   # counted, not planned

    def test_clustered_story_records_full_component_membership(self, session):
        from app.db.orm_models import StoryClusterRow
        set_watermark(session, PROFILE, POLICY)
        cid = "cluster_t152_madar"
        session.add(StoryClusterRow(
            id=cid, anchor_article_id="rss_t152_c1",
            representative_article_id="rss_t152_c1",
            event_state="negotiation", sport="basketball",
            member_count=2, rule_version=1,
            formed_at=_now().isoformat(),
            last_member_added_at=_now().isoformat(),
        ))
        _add_article(session, "rss_t152_c1",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג",
                     cluster_id=cid)
        _add_article(session, "rss_t152_c2",
                     title="מכבי תל אביב מנהלת מגעים עם גארד היורוליג",
                     cluster_id=cid, source="ynet_sport")
        session.commit()

        summary = plan_cycle_notifications(session)
        assert len(summary["created"]) == 1
        members = {m[0] for m in session.execute(text(
            "SELECT article_id FROM notification_story_members")).fetchall()}
        assert members == {"rss_t152_c1", "rss_t152_c2"}
        # Cluster expansion later — a third source joins:
        _add_article(session, "rss_t152_c3",
                     title="גם וואלה: מכבי ת״א קרובה לגארד יורוליג",
                     cluster_id=cid, source="walla_sport")
        session.execute(text(
            "UPDATE story_clusters SET member_count=3 WHERE id=:c"), {"c": cid})
        session.commit()
        summary2 = plan_cycle_notifications(session)
        assert summary2["created"] == []
        assert len(_events(session)) == 1          # no second event

    def test_suppressed_watermark_story_never_notifies(self, session):
        from app.notifications.outbox import StorySnapshot, plan_story
        set_watermark(session, PROFILE, POLICY)
        _add_article(session, "rss_t152_hist",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        # Activation initialization planted the suppression:
        plan_story(session, profile_id=PROFILE, policy_version=POLICY,
                   story=StorySnapshot(
                       member_article_ids=["rss_t152_hist"], cluster_id=None,
                       canonical_article_id="rss_t152_hist",
                       canonical_headline="x", source="s",
                       url="https://example.test/rss_t152_hist", tier="push"),
                   initial_status=SUPPRESSED_WATERMARK)
        summary = plan_cycle_notifications(session)
        assert summary["created"] == []
        statuses = [e[1] for e in _events(session)]
        assert statuses == [SUPPRESSED_WATERMARK]


class TestOrchestrationIntegration:
    def test_cycle_records_notification_summary(self, session, monkeypatch):
        import types

        from app.ingestion.orchestration import orchestrate_cycle
        set_watermark(session, PROFILE, POLICY)
        _add_article(session, "rss_t152_push1",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()

        fake = [types.SimpleNamespace(
            source_id="walla_sport", fetched=0, inserted=0, skipped_duplicate=0,
            skipped_filtered=0, failed=0, errors=[])]
        with patch("app.ingestion.ingestion_service.run_ingestion",
                   return_value=fake):
            out = orchestrate_cycle("manual")
        assert out.status == "succeeded"
        row = session.execute(text(
            "SELECT notification_summary FROM scheduler_cycles WHERE id=:c"
        ), {"c": out.cycle_id}).fetchone()
        import json
        summary = json.loads(row[0])
        assert len(summary["planning"]["created"]) == 1
        # Dispatch ran as its own stage (M7-7); Telegram is unconfigured in
        # tests, so delivery reports unavailable WITHOUT degrading the cycle.
        assert summary["dispatch"] == {"skipped": "not_configured"}

    def test_planner_failure_degrades_cycle_not_ingestion(self, session, monkeypatch):
        import types

        from app.ingestion.orchestration import orchestrate_cycle
        fake = [types.SimpleNamespace(
            source_id="walla_sport", fetched=1, inserted=1, skipped_duplicate=0,
            skipped_filtered=0, failed=0, errors=[])]
        with patch("app.ingestion.ingestion_service.run_ingestion",
                   return_value=fake), \
             patch("app.notifications.planner.plan_cycle_notifications",
                   side_effect=RuntimeError("planner exploded")):
            out = orchestrate_cycle("manual")
        assert out.status == "succeeded_with_warnings"
        assert "planner exploded" in (out.error_summary or "")