"""M7-3 (#149) — article retention cleanup under the CLUSTERING.md §14 constraints.

Feed visibility ≠ physical deletion: the window is weeks, and the protections
(live-cluster cohesion, feedback provenance, notification-lineage survival)
are each locked here with a positive and a negative case.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.ingestion.retention import cleanup_articles, cleanup_enabled, retention_days


def _now():
    return datetime.now(tz=timezone.utc)


_IDS: list[str] = []


def _add(session, _id, *, days_ago, cluster_id=None):
    from app.db.orm_models import ArticleRow
    _IDS.append(_id)
    session.add(ArticleRow(
        id=_id, source="walla_sport", source_display_name="walla",
        url=f"https://example.test/{_id}", title=f"כתבה {_id}", language="he",
        published_at=(_now() - timedelta(days=days_ago)).isoformat(),
        sport="basketball", entities=[], event_type="news",
        event_certainty="confirmed", importance="low", tags=[],
        entity_ids=[], cluster_id=cluster_id,
    ))


@pytest.fixture
def session(_application, monkeypatch):
    monkeypatch.setenv("ARTICLE_RETENTION_DAYS", "30")
    from app.db.database import SessionLocal, init_db
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM articles WHERE id LIKE 'rss_t149%'"))
        s.execute(text("DELETE FROM story_clusters WHERE id LIKE 'cluster_t149%'"))
        s.execute(text("DELETE FROM feedback_events WHERE article_id LIKE 'rss_t149%'"))
        s.commit()
        yield s
        s.rollback()
        s.execute(text("DELETE FROM articles WHERE id LIKE 'rss_t149%'"))
        s.execute(text("DELETE FROM story_clusters WHERE id LIKE 'cluster_t149%'"))
        s.execute(text("DELETE FROM feedback_events WHERE article_id LIKE 'rss_t149%'"))
        s.commit()


def _exists(session, _id):
    return session.execute(text(
        "SELECT COUNT(*) FROM articles WHERE id=:i"), {"i": _id}).fetchone()[0] == 1


class TestConfig:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("RETENTION_CLEANUP_ENABLED", raising=False)
        assert cleanup_enabled() is False

    def test_window_never_below_a_week(self, monkeypatch):
        monkeypatch.setenv("ARTICLE_RETENTION_DAYS", "2")
        assert retention_days() == 30      # cluster span + margin must fit


class TestDeletion:
    def test_only_out_of_window_rss_articles_are_deleted(self, session):
        _add(session, "rss_t149_old", days_ago=40)
        _add(session, "rss_t149_fresh", days_ago=2)
        session.commit()
        summary = cleanup_articles(session)
        assert summary["deleted"] == 1
        assert not _exists(session, "rss_t149_old")
        assert _exists(session, "rss_t149_fresh")

    def test_seeded_demo_articles_are_never_candidates(self, session):
        # article_0xx scoring fixtures are older than any window but not rss_.
        summary = cleanup_articles(session, dry_run=True)
        before = session.execute(text(
            "SELECT COUNT(*) FROM articles WHERE id LIKE 'article_%'")).fetchone()[0]
        cleanup_articles(session)
        after = session.execute(text(
            "SELECT COUNT(*) FROM articles WHERE id LIKE 'article_%'")).fetchone()[0]
        assert before == after

    def test_dry_run_writes_nothing(self, session):
        _add(session, "rss_t149_old", days_ago=40)
        session.commit()
        summary = cleanup_articles(session, dry_run=True)
        assert summary["deleted"] == 1 and summary["dry_run"] is True
        assert _exists(session, "rss_t149_old")


class TestProtections:
    def test_live_cluster_protects_its_old_members(self, session):
        from app.db.orm_models import StoryClusterRow
        cid = "cluster_t149_live"
        session.add(StoryClusterRow(
            id=cid, anchor_article_id="rss_t149_old_member",
            representative_article_id="rss_t149_fresh_member",
            event_state="signing", sport="basketball", member_count=2,
            rule_version=1, formed_at=_now().isoformat(),
            last_member_added_at=_now().isoformat()))
        _add(session, "rss_t149_old_member", days_ago=40, cluster_id=cid)
        _add(session, "rss_t149_fresh_member", days_ago=1, cluster_id=cid)
        session.commit()

        summary = cleanup_articles(session)
        assert _exists(session, "rss_t149_old_member")       # protected
        assert summary["protected_cluster"] == 1
        # The cluster survives intact with a correct count:
        count = session.execute(text(
            "SELECT member_count FROM story_clusters WHERE id=:c"), {"c": cid}
        ).fetchone()[0]
        assert count == 2

    def test_fully_aged_cluster_is_removed_with_its_edges(self, session):
        from app.db.orm_models import ClusterEdgeRow, StoryClusterRow
        cid = "cluster_t149_dead"
        session.add(StoryClusterRow(
            id=cid, anchor_article_id="rss_t149_a",
            representative_article_id="rss_t149_a",
            event_state="signing", sport="basketball", member_count=2,
            rule_version=1, formed_at=_now().isoformat(),
            last_member_added_at=_now().isoformat()))
        session.add(ClusterEdgeRow(
            id="edge_t149", cluster_id=cid, article_a="rss_t149_a",
            article_b="rss_t149_b", jaccard=0.5, hours_apart=1.0,
            rare_tokens=[], entity_overlap=[], competition_overlap=[], tier="A"))
        _add(session, "rss_t149_a", days_ago=40, cluster_id=cid)
        _add(session, "rss_t149_b", days_ago=41, cluster_id=cid)
        session.commit()

        summary = cleanup_articles(session)
        assert summary["deleted"] == 2
        assert summary["clusters_removed"] == 1
        assert session.execute(text(
            "SELECT COUNT(*) FROM story_clusters WHERE id=:c"), {"c": cid}
        ).fetchone()[0] == 0
        assert session.execute(text(
            "SELECT COUNT(*) FROM cluster_edges WHERE cluster_id=:c"), {"c": cid}
        ).fetchone()[0] == 0

    def test_feedback_referenced_articles_survive(self, session):
        from app.db.orm_models import FeedbackRow
        _add(session, "rss_t149_feedback", days_ago=40)
        session.add(FeedbackRow(
            id="fb_t149", user_id="guy", article_id="rss_t149_feedback",
            action="more_like_this", created_at=_now().isoformat()))
        session.commit()

        summary = cleanup_articles(session)
        assert _exists(session, "rss_t149_feedback")
        assert summary["protected_feedback"] == 1

    def test_notification_lineage_survives_member_deletion(self, session):
        from app.notifications.outbox import StorySnapshot, plan_story, set_watermark
        set_watermark(session, "guy", "v1")
        _add(session, "rss_t149_notified", days_ago=40)
        session.commit()
        plan_story(session, profile_id="guy", policy_version="v1",
                   story=StorySnapshot(
                       member_article_ids=["rss_t149_notified"], cluster_id=None,
                       canonical_article_id="rss_t149_notified",
                       canonical_headline="x", source="s",
                       url="https://example.test/n", tier="push"))
        cleanup_articles(session)
        assert not _exists(session, "rss_t149_notified")     # article gone
        lineage = session.execute(text(
            "SELECT COUNT(*) FROM notification_story_members "
            "WHERE article_id='rss_t149_notified'")).fetchone()[0]
        assert lineage == 1                                   # memory intact
        # cleanup of notification test rows
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()


class TestOrchestrationIntegration:
    def test_cleanup_failure_degrades_cycle_not_ingestion(self, session, monkeypatch):
        import types
        from unittest.mock import patch

        from app.ingestion.orchestration import orchestrate_cycle
        monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "true")
        fake = [types.SimpleNamespace(
            source_id="walla_sport", fetched=1, inserted=1, skipped_duplicate=0,
            skipped_filtered=0, failed=0, errors=[])]
        with patch("app.ingestion.ingestion_service.run_ingestion",
                   return_value=fake), \
             patch("app.ingestion.retention.cleanup_articles",
                   side_effect=RuntimeError("cleanup exploded")):
            out = orchestrate_cycle("manual")
        assert out.status == "succeeded_with_warnings"
        assert "cleanup exploded" in (out.error_summary or "")

    def test_disabled_cleanup_is_a_recorded_noop(self, session, monkeypatch):
        import json
        import types
        from unittest.mock import patch

        from app.ingestion.orchestration import orchestrate_cycle
        monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "false")
        fake = [types.SimpleNamespace(
            source_id="walla_sport", fetched=0, inserted=0, skipped_duplicate=0,
            skipped_filtered=0, failed=0, errors=[])]
        with patch("app.ingestion.ingestion_service.run_ingestion",
                   return_value=fake):
            out = orchestrate_cycle("manual")
        assert out.status == "succeeded"
        row = session.execute(text(
            "SELECT cleanup_summary FROM scheduler_cycles WHERE id=:c"
        ), {"c": out.cycle_id}).fetchone()
        assert json.loads(row[0]) == {"skipped": "disabled"}