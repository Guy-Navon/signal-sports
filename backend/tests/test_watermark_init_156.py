"""M7-10 (#156) — guarded activation watermark initialization.

THE ACTIVATION RULE under test: enabling Telegram must not flood historical
PUSH stories. Initialization plants `suppressed_watermark` events (with full
lineage) for every story already PUSH-eligible — after which the per-cycle
planner creates events ONLY for stories that first become eligible later.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.notifications.outbox import (
    SUPPRESSED_WATERMARK,
    get_watermark,
    plan_story,
    set_watermark,
)
from app.notifications.planner import (
    enumerate_push_stories,
    plan_cycle_notifications,
)

PROFILE = "guy"
POLICY = "v1"


def _now():
    return datetime.now(tz=timezone.utc)


_IDS: list[str] = []


def _add_article(session, _id, *, title, importance="high", event_type="negotiation",
                 entities=("Maccabi Tel Aviv Basketball",), sport="basketball",
                 league="EuroLeague", hours_ago=1.0, source="sport5_sport"):
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
        entity_ids=[], cluster_id=None,
    ))
    return _id


@pytest.fixture
def session(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    from app.db.database import SessionLocal, init_db
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
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
            from app.db.orm_models import ArticleRow
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(
                synchronize_session=False)
        s.commit()


def _events(session):
    return session.execute(text(
        "SELECT id, status FROM notification_events ORDER BY created_at"
    )).fetchall()


def _initialize(session):
    """The exact initialization sequence the script performs."""
    enumerated = enumerate_push_stories(session, PROFILE)
    assert enumerated is not None
    snapshots, _ = enumerated
    set_watermark(session, PROFILE, POLICY)
    planted = 0
    for s in snapshots:
        out = plan_story(session, profile_id=PROFILE, policy_version=POLICY,
                         story=s, initial_status=SUPPRESSED_WATERMARK)
        if out.outcome == "created":
            planted += 1
    row = get_watermark(session, PROFILE, POLICY)
    row.suppressed_story_count = planted
    session.commit()
    return planted


class TestActivationRule:
    def test_historical_push_suppressed_new_push_notifies(self, session):
        """THE ACTIVATION RULE. A story PUSH-eligible BEFORE initialization is
        suppressed forever; a story first eligible AFTER it creates exactly
        one pending event."""
        _add_article(session, "rss_t156_hist",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()

        planted = _initialize(session)
        assert planted == 1
        assert [e[1] for e in _events(session)] == [SUPPRESSED_WATERMARK]

        # Cycles after activation: the historical story never notifies…
        summary = plan_cycle_notifications(session)
        assert summary["created"] == []
        assert summary["already_notified"] == 1

        # …but a genuinely new push story creates exactly one pending event.
        _add_article(session, "rss_t156_new",
                     title="רשמית: מכבי ת״א מחתימה סנטר חדש ל-3 עונות")
        session.commit()
        summary2 = plan_cycle_notifications(session)
        assert len(summary2["created"]) == 1
        assert summary2["already_notified"] == 1        # the suppressed one, again
        statuses = sorted(e[1] for e in _events(session))
        assert statuses == ["pending", SUPPRESSED_WATERMARK]

    def test_initialization_is_idempotent(self, session):
        _add_article(session, "rss_t156_hist",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        first = _initialize(session)
        assert first == 1
        # Re-running plants nothing new and keeps the original watermark row.
        wm_before = get_watermark(session, PROFILE, POLICY).activated_at
        second = _initialize(session)
        assert second == 0
        assert get_watermark(session, PROFILE, POLICY).activated_at == wm_before
        assert len(_events(session)) == 1

    def test_suppressed_events_are_undeliverable(self, session):
        """A suppressed_watermark event must never be claimed by the
        dispatcher — it is identity, not a deliverable."""
        _add_article(session, "rss_t156_hist",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        _initialize(session)

        from app.notifications.dispatcher import dispatch_pending

        class ExplodingSender:
            provider = "fake"
            def configured(self):
                return True
            def send(self, text):
                raise AssertionError("dispatcher tried to SEND a suppressed event")

        summary = dispatch_pending(session, ExplodingSender())
        assert summary["attempted"] == 0
        assert [e[1] for e in _events(session)] == [SUPPRESSED_WATERMARK]

    def test_empty_feed_initialization_sets_watermark_only(self, session):
        planted = _initialize(session)
        assert planted == 0
        assert _events(session) == []
        assert get_watermark(session, PROFILE, POLICY) is not None
        # New push story after an empty-feed activation still notifies.
        _add_article(session, "rss_t156_new",
                     title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג")
        session.commit()
        summary = plan_cycle_notifications(session)
        assert len(summary["created"]) == 1
