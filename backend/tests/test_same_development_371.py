"""#371: one agreement reported again more than 24 h later must not send a second message.

The Lundberg agreement was pushed by Israel Hayom (07-20) and again by Sport5 (07-22), 52 h
apart: beyond the clustering window, so the second report started a new lineage. The planner
now checks for an earlier event covering the SAME development before creating a new one:
the same person and club, a transaction story (negotiation/signing), and both reports
asserting an agreement or completion (attention evidence), within 72 h of publication.

New developments must still notify: a different person, a different development (an
imminent renewal before the agreement), the same person's injury, or the same agreement much
later. Rows without attention evidence keep today's behavior. Runs through the real engine and
the real seeded Guy profile, like the #152 planner tests.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.notifications.outbox import set_watermark
from app.notifications.planner import plan_cycle_notifications

PROFILE = "guy"
POLICY = "v1"
MACCABI = "team:maccabi_tlv_bb"
LUNDBERG = "player:iffe_lundberg"
MADAR = "player:yam_madar"
_IDS: list[str] = []


def _now():
    return datetime.now(tz=timezone.utc)


def _add(session, _id, title, hours_ago, *, people=(LUNDBERG,), development="agreement_or_completion",
         event_type="negotiation", attention=True):
    from app.db.orm_models import ArticleRow
    _IDS.append(_id)
    trace = {"attention": {"development": development, "subject_entity_ids": [MACCABI]}} if attention else {}
    session.add(ArticleRow(
        id=_id, source="sport5_sport", source_display_name="sport5", url=f"https://example.test/{_id}",
        title=title, language="he", published_at=(_now() - timedelta(hours=hours_ago)).isoformat(),
        sport="basketball", league="EuroLeague", entities=["Maccabi Tel Aviv Basketball"],
        event_type=event_type, event_certainty="probable", importance="high", confidence=0.9,
        tags=[], entity_ids=[MACCABI], cluster_id=None, classification_trace=trace,
        story_anchors=[{"anchor": p, "role": "unknown", "source": "title", "validator_id": "taxonomy",
                        "reason_code": "canonical"} for p in people],
    ))
    session.commit()
    return _id


@pytest.fixture
def session(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    from app.db.database import SessionLocal, init_db
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        for table in ("notification_story_members", "notification_events", "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.execute(text("DELETE FROM articles WHERE id LIKE 'rss_%'"))
        s.execute(text("DELETE FROM cluster_edges"))
        s.execute(text("DELETE FROM story_clusters"))
        s.commit()
        set_watermark(s, PROFILE, POLICY)
        yield s
        s.rollback()
        for table in ("notification_story_members", "notification_events", "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        if _IDS:
            from app.db.orm_models import ArticleRow
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(synchronize_session=False)
        s.commit()


def _event_count(s):
    return s.execute(text("SELECT count(*) FROM notification_events")).scalar()


def _member_reason(s, article_id):
    return s.execute(text("SELECT reason FROM notification_story_members WHERE article_id=:a"),
                     {"a": article_id}).scalar()


def test_the_same_agreement_52h_later_sends_no_second_message(session):
    _add(session, "rss_t371_ih", "בשורה אדירה למכבי תל אביב: איפה לונדברג סיכם על חוזה חדש", 60)
    assert len(plan_cycle_notifications(session)["created"]) == 1
    _add(session, "rss_t371_s5", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 8)
    summary = plan_cycle_notifications(session)
    assert summary["created"] == []
    assert summary["same_development"] == 1
    assert _event_count(session) == 1
    assert _member_reason(session, "rss_t371_s5") == "same_development"


def test_two_reports_in_one_cycle_send_one_message(session):
    _add(session, "rss_t371_a", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 30)
    _add(session, "rss_t371_b", "נשאר צהוב: איפה לונדברג סיכם לשנתיים נוספות", 2)
    plan_cycle_notifications(session)
    assert _event_count(session) == 1


def test_a_new_development_still_notifies(session):
    _add(session, "rss_t371_near", "מכבי קרובה להארכה עם לונדברג", 40, development="imminent_renewal")
    plan_cycle_notifications(session)
    _add(session, "rss_t371_done", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 5)
    assert len(plan_cycle_notifications(session)["created"]) == 1
    assert _event_count(session) == 2


def test_a_different_person_at_the_same_club_still_notifies(session):
    _add(session, "rss_t371_l", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 30)
    plan_cycle_notifications(session)
    _add(session, "rss_t371_m", "ים מדר סיכם במכבי תל אביב", 4, people=(MADAR,))
    assert len(plan_cycle_notifications(session)["created"]) == 1


def test_the_same_persons_injury_still_notifies(session):
    _add(session, "rss_t371_deal", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 30)
    plan_cycle_notifications(session)
    _add(session, "rss_t371_inj", "לונדברג נפצע באימון של מכבי", 3, event_type="injury",
         development="current_injury")
    assert len(plan_cycle_notifications(session)["created"]) == 1


def test_the_same_agreement_much_later_still_notifies(session):
    _add(session, "rss_t371_old", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 100)
    plan_cycle_notifications(session)
    _add(session, "rss_t371_new", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 2)
    assert len(plan_cycle_notifications(session)["created"]) == 1


def test_without_attention_evidence_behavior_is_unchanged(session):
    _add(session, "rss_t371_x", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 50, attention=False)
    plan_cycle_notifications(session)
    _add(session, "rss_t371_y", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 4, attention=False)
    assert len(plan_cycle_notifications(session)["created"]) == 1
