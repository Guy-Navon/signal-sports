"""#250 — real usage leaves a minimal trace.

One row per (user, Israel day) counts feed views; opening an article's source emits
``article_opened``, which stays a passive event: no learning, no dismissal.
"""

from datetime import date

from app.db.database import SessionLocal
from app.db.orm_models import UsageDayRow
from app.repositories import usage_repository


def _usage_rows(user_id: str) -> list[UsageDayRow]:
    with SessionLocal() as s:
        return s.query(UsageDayRow).filter(UsageDayRow.user_id == user_id).all()


class TestFeedViews:
    def test_two_views_on_one_day_are_one_row(self, user_client):
        assert user_client.get("/api/me/feed").status_code == 200
        assert user_client.get("/api/me/feed").status_code == 200
        rows = _usage_rows(user_client.identity_user_id)
        assert len(rows) == 1
        assert rows[0].feed_views == 2

    def test_each_day_gets_its_own_row(self, client):
        with SessionLocal() as s:
            usage_repository.record_feed_view(s, "usage-test-user", day=date(2026, 10, 25))
            usage_repository.record_feed_view(s, "usage-test-user", day=date(2026, 10, 26))
            usage_repository.record_feed_view(s, "usage-test-user", day=date(2026, 10, 26))
        rows = {r.day: r.feed_views for r in _usage_rows("usage-test-user")}
        assert rows == {"2026-10-25": 1, "2026-10-26": 2}

    def test_a_recording_failure_never_breaks_the_feed(self, user_client, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("usage table unavailable")
        monkeypatch.setattr(usage_repository, "record_feed_view", boom)
        assert user_client.get("/api/me/feed").status_code == 200


class TestArticleOpenedStaysPassive:
    def test_open_is_recorded_once_and_changes_nothing_learned(self, user_client):
        from app.repositories import feedback_repository
        from app.services.learning_service import dismissed_article_ids

        article_id = "article_006"  # a seeded corpus article
        learning_before = user_client.get("/api/me/learning").json()

        r = user_client.post("/api/me/feedback", json={"article_id": article_id, "action": "article_opened"})
        assert r.status_code == 201

        events = user_client.get("/api/me/feedback").json()
        assert [e["action"] for e in events if e["article_id"] == article_id] == ["article_opened"]
        assert user_client.get("/api/me/learning").json() == learning_before
        with SessionLocal() as s:
            stored = feedback_repository.get_by_user(s, user_client.identity_user_id)
        assert article_id not in dismissed_article_ids(stored), "an open is not a dismissal"
