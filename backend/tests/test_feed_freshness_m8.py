"""
Milestone 8 (#170) — feed freshness window.

THE product bug this locks against: the ranked feed showing 3-6 day old
articles. One shared predicate (app/services/freshness.py, M8-1 #171) applied
once in build_feed (M8-2 #172); the Telegram planner consumes build_feed and
therefore inherits the window with zero planner code (M8-3 #173); ingestion
guards the publication-timestamp clock (M8-4 #174).

Freshness is pinned OFF in conftest for hermeticity — every test here that
exercises the window enables it explicitly.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.db.orm_models import ArticleRow, ClusterEdgeRow, StoryClusterRow
from app.services.freshness import (
    DEFAULT_FEED_MAX_AGE_HOURS,
    feed_max_age_hours,
    freshness_cutoff,
    fresh_only,
    is_fresh,
)

FRESH_ON = {"FEED_FRESHNESS_ENABLED": "true"}


def _now():
    return datetime.now(tz=timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# M8-1 — the predicate itself
# ══════════════════════════════════════════════════════════════════════════════

class TestPredicate:
    def test_disabled_means_everything_is_fresh(self):
        with patch.dict(os.environ, {"FEED_FRESHNESS_ENABLED": "false"}):
            assert is_fresh(_now() - timedelta(days=100)) is True

    def test_disabled_is_the_code_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEED_FRESHNESS_ENABLED", None)
            assert is_fresh(_now() - timedelta(days=100)) is True

    def test_window_boundary(self):
        with patch.dict(os.environ, FRESH_ON):
            assert is_fresh(_now() - timedelta(hours=35)) is True
            assert is_fresh(_now() - timedelta(hours=37)) is False

    def test_exactly_at_cutoff_is_fresh(self):
        """The documented boundary rule: published_at >= cutoff is IN."""
        with patch.dict(os.environ, FRESH_ON):
            now = _now()
            assert is_fresh(freshness_cutoff(now), now=now) is True

    def test_naive_datetime_treated_as_utc(self):
        with patch.dict(os.environ, FRESH_ON):
            naive_fresh = (_now() - timedelta(hours=1)).replace(tzinfo=None)
            naive_old = (_now() - timedelta(hours=48)).replace(tzinfo=None)
            assert is_fresh(naive_fresh) is True
            assert is_fresh(naive_old) is False

    def test_future_dated_article_is_fresh(self):
        """Future timestamps are clamped at INGESTION (M8-4); the predicate
        itself never expires a future-dated article."""
        with patch.dict(os.environ, FRESH_ON):
            assert is_fresh(_now() + timedelta(minutes=40)) is True

    def test_window_is_configurable(self):
        with patch.dict(os.environ, {**FRESH_ON, "FEED_MAX_AGE_HOURS": "12"}):
            assert is_fresh(_now() - timedelta(hours=11)) is True
            assert is_fresh(_now() - timedelta(hours=13)) is False

    def test_guarded_parse_falls_back_to_default(self):
        for bad in ("abc", "", "0", "-5", "3.5"):
            with patch.dict(os.environ, {"FEED_MAX_AGE_HOURS": bad}):
                assert feed_max_age_hours() == DEFAULT_FEED_MAX_AGE_HOURS

    def test_fresh_only_uses_one_clock_for_the_batch(self):
        class A:
            def __init__(self, dt):
                self.published_at = dt
        with patch.dict(os.environ, FRESH_ON):
            fresh = A(_now() - timedelta(hours=1))
            expired = A(_now() - timedelta(hours=40))
            out = fresh_only([fresh, expired])
            assert out == [fresh]


# ══════════════════════════════════════════════════════════════════════════════
# Shared DB harness for feed / cluster / planner tests
# ══════════════════════════════════════════════════════════════════════════════

_IDS: list[str] = []


@pytest.fixture
def session(client):
    """App lifespan entered (tables + seeded guy/casual_deni_fan profiles);
    deterministic rss_ corpus (planner reads the REAL feed, so leftovers from
    other test files would perturb exact assertions)."""
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
        s.query(ClusterEdgeRow).delete(synchronize_session=False)
        s.query(StoryClusterRow).delete(synchronize_session=False)
        if _IDS:
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(
                synchronize_session=False)
        s.commit()


def _add_article(session, _id, *, title="דיווח: מכבי ת״א במו״מ עם גארד יורוליג",
                 hours_ago=1.0, cluster_id=None, importance="high",
                 event_type="negotiation",
                 entities=("Maccabi Tel Aviv Basketball",),
                 sport="basketball", league="EuroLeague",
                 source="sport5_sport"):
    """Default shape scores PUSH for guy (the seeded Maccabi-negotiation
    shape) through the REAL engine — nothing is stubbed."""
    _IDS.append(_id)
    session.add(ArticleRow(
        id=_id, source=source, source_display_name=source,
        url=f"https://example.test/{_id}", title=title, language="he",
        published_at=(_now() - timedelta(hours=hours_ago)).isoformat(),
        sport=sport, league=league, entities=list(entities),
        event_type=event_type, event_certainty="confirmed",
        importance=importance, confidence=0.92, tags=[],
        entity_ids=[], cluster_id=cluster_id,
    ))
    return _id


def _cluster(session, cid, *, rep, members):
    session.add(StoryClusterRow(
        id=cid, anchor_article_id=members[0], representative_article_id=rep,
        event_state="negotiation", sport="basketball",
        formed_at=_now().isoformat(), last_member_added_at=_now().isoformat(),
        method="deterministic", rule_version=1, member_count=len(members),
    ))


def _build(session, profile_id="guy", include_hidden=False):
    from app.repositories import article_repository, profile_repository
    from app.services.feed_service import build_feed
    profile = profile_repository.get_by_id(session, profile_id)
    articles = article_repository.get_rss_articles(session)
    return build_feed(articles, profile, include_hidden=include_hidden,
                      session=session)


def _ids(feed):
    return [s.article.id for s in feed]


# ══════════════════════════════════════════════════════════════════════════════
# M8-2 — consumer feed and debug behavior
# ══════════════════════════════════════════════════════════════════════════════

class TestConsumerFeed:
    def test_expired_articles_leave_the_consumer_feed(self, session):
        _add_article(session, "rss_m8_fresh", hours_ago=2)
        _add_article(session, "rss_m8_old", hours_ago=40)
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            feed = _build(session)
        assert "rss_m8_fresh" in _ids(feed)
        assert "rss_m8_old" not in _ids(feed)

    def test_debug_feed_keeps_showing_expired(self, session):
        """Debug is the everything-view by contract — expired articles stay
        inspectable there, exactly like hidden ones."""
        _add_article(session, "rss_m8_old", hours_ago=40)
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            debug = _build(session, include_hidden=True)
        assert "rss_m8_old" in _ids(debug)

    def test_flag_off_is_byte_identical_prem8_behavior(self, session):
        _add_article(session, "rss_m8_old", hours_ago=40)
        session.commit()
        with patch.dict(os.environ, {"FEED_FRESHNESS_ENABLED": "false"}):
            feed = _build(session)
        assert "rss_m8_old" in _ids(feed)

    def test_zero_decision_drift_for_fresh_articles(self, session):
        """THE no-drift lock: enabling freshness only REMOVES expired items —
        every still-fresh article keeps the identical decision and relative
        order."""
        _add_article(session, "rss_m8_push", hours_ago=1)
        _add_article(session, "rss_m8_nba",
                     title="דני אבדיה קלע 30 נקודות בניצחון פורטלנד",
                     hours_ago=3, importance="medium",
                     event_type="match_result",
                     entities=("Deni Avdija",), league="NBA")
        _add_article(session, "rss_m8_old", hours_ago=40)
        session.commit()

        with patch.dict(os.environ, {"FEED_FRESHNESS_ENABLED": "false"}):
            before = {s.article.id: s.decision for s in _build(session)}
            order_before = [i for i in _ids(_build(session)) if i != "rss_m8_old"]
        with patch.dict(os.environ, FRESH_ON):
            after = {s.article.id: s.decision for s in _build(session)}
            order_after = _ids(_build(session))

        assert "rss_m8_old" not in after
        for aid, decision in after.items():
            assert before[aid] == decision
        assert [i for i in order_before if i.startswith("rss_m8")] == \
               [i for i in order_after if i.startswith("rss_m8")]

    def test_consumer_api_route_applies_the_window(self, session, admin_client):
        _add_article(session, "rss_m8_fresh", hours_ago=2)
        _add_article(session, "rss_m8_old", hours_ago=40)
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            feed_ids = [s["article"]["id"]
                        for s in admin_client.get("/api/feed/guy").json()]
            debug_ids = [s["article"]["id"]
                         for s in admin_client.get("/api/debug/feed/guy").json()]
        assert "rss_m8_fresh" in feed_ids
        assert "rss_m8_old" not in feed_ids
        assert "rss_m8_old" in debug_ids

    def test_same_policy_for_both_permanent_profiles(self, session):
        _add_article(session, "rss_m8_deni_old",
                     title="דני אבדיה הוחלף לקבוצה אחרת ב-NBA",
                     hours_ago=40, importance="very_high", event_type="major_trade",
                     entities=("Deni Avdija",), league="NBA")
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            assert "rss_m8_deni_old" not in _ids(_build(session, "guy"))
            assert "rss_m8_deni_old" not in _ids(_build(session, "casual_deni_fan"))


# ══════════════════════════════════════════════════════════════════════════════
# M8-2 — cluster canonical behavior on mixed-age components
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def clustering_on():
    with patch.dict(os.environ, {"CLUSTERING_ENABLED": "true"}):
        yield


class TestClusterCanonical:
    def test_expired_representative_yields_inwindow_canonical(
            self, session, clustering_on):
        """A cluster with an expired corpus representative and a fresh member
        must display the fresh member — the expired former canonical loses
        control of the headline/link."""
        _add_article(session, "rss_m8_c_old", hours_ago=40, cluster_id="cl_m8")
        _add_article(session, "rss_m8_c_new", hours_ago=2, cluster_id="cl_m8")
        _cluster(session, "cl_m8", rep="rss_m8_c_old",
                 members=["rss_m8_c_old", "rss_m8_c_new"])
        session.commit()

        with patch.dict(os.environ, FRESH_ON):
            feed = _build(session)
        cards = [s for s in feed if s.cluster is not None
                 and s.cluster.cluster_id == "cl_m8"]
        assert len(cards) == 1
        card = cards[0].cluster
        assert cards[0].article.id == "rss_m8_c_new"
        assert card.displayed_article_id == "rss_m8_c_new"
        assert card.displayed_reason == "representative_hidden_fallback"
        member_ids = [m.article_id for m in card.members]
        assert member_ids == ["rss_m8_c_new"]          # expired member folded out
        assert card.sort_at == max(
            s.article.published_at for s in cards)      # newest FRESH member

    def test_all_expired_cluster_disappears(self, session, clustering_on):
        _add_article(session, "rss_m8_c1", hours_ago=40, cluster_id="cl_m8")
        _add_article(session, "rss_m8_c2", hours_ago=50, cluster_id="cl_m8")
        _cluster(session, "cl_m8", rep="rss_m8_c1",
                 members=["rss_m8_c1", "rss_m8_c2"])
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            feed = _build(session)
        assert "rss_m8_c1" not in _ids(feed)
        assert "rss_m8_c2" not in _ids(feed)
        assert all(s.cluster is None or s.cluster.cluster_id != "cl_m8"
                   for s in feed)


# ══════════════════════════════════════════════════════════════════════════════
# M8-3 — the Telegram planner inherits the exact same predicate
# ══════════════════════════════════════════════════════════════════════════════

class TestPlannerFreshness:
    @pytest.fixture(autouse=True)
    def _telegram_on(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")

    def _events(self, session):
        return session.execute(text(
            "SELECT id, status FROM notification_events")).fetchall()

    def test_expired_push_story_creates_no_event(self, session):
        from app.notifications.outbox import set_watermark
        from app.notifications.planner import plan_cycle_notifications
        set_watermark(session, "guy", "v1")
        _add_article(session, "rss_m8_p_old", hours_ago=40)   # push shape, expired
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            summary = plan_cycle_notifications(session)
        assert summary["created"] == []
        assert summary["push_stories"] == 0
        assert self._events(session) == []

    def test_fresh_push_story_remains_eligible(self, session):
        from app.notifications.outbox import set_watermark
        from app.notifications.planner import plan_cycle_notifications
        set_watermark(session, "guy", "v1")
        _add_article(session, "rss_m8_p_new", hours_ago=1)
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            summary = plan_cycle_notifications(session)
        assert len(summary["created"]) == 1

    def test_canonical_replacement_does_not_resend(self, session):
        """A notified story whose canonical expires and is replaced by a fresh
        duplicate must stay already-notified: lineage is keyed on article ids
        of the FULL component, including expired members."""
        from app.notifications.outbox import set_watermark
        from app.notifications.planner import plan_cycle_notifications
        set_watermark(session, "guy", "v1")
        _add_article(session, "rss_m8_p_a", hours_ago=1)
        session.commit()
        with patch.dict(os.environ, FRESH_ON):
            first = plan_cycle_notifications(session)
        assert len(first["created"]) == 1

        # Time passes: the notified article leaves the window; a fresh source
        # joins the same story and becomes the displayed canonical.
        session.execute(text(
            "UPDATE articles SET published_at = :p, cluster_id = 'cl_m8p' "
            "WHERE id = 'rss_m8_p_a'"),
            {"p": (_now() - timedelta(hours=40)).isoformat()})
        _add_article(session, "rss_m8_p_b", hours_ago=1, cluster_id="cl_m8p")
        _cluster(session, "cl_m8p", rep="rss_m8_p_a",
                 members=["rss_m8_p_a", "rss_m8_p_b"])
        session.commit()

        with patch.dict(os.environ, {**FRESH_ON, "CLUSTERING_ENABLED": "true"}):
            second = plan_cycle_notifications(session)
        assert second["created"] == []
        assert second["already_notified"] >= 1
        assert len(self._events(session)) == 1

    def test_no_telegram_specific_age_rule_exists(self):
        """Contract guard: the planner module must not read the freshness env
        or implement its own cutoff — it inherits build_feed's."""
        import inspect
        from app.notifications import planner
        source = inspect.getsource(planner)
        assert "FEED_MAX_AGE" not in source
        assert "freshness" not in source


# ══════════════════════════════════════════════════════════════════════════════
# M8-4 — timestamp quality at ingestion
# ══════════════════════════════════════════════════════════════════════════════

class TestTimestampQuality:
    def test_missing_timestamp_gets_bounded_fallback_with_provenance(self):
        from app.ingestion.ingestion_service import _normalise_published_at
        published, meta = _normalise_published_at(None)
        assert abs((published - _now()).total_seconds()) < 5
        assert meta == {"provenance": "ingest_fallback"}

    def test_source_timestamp_passes_through_unmarked(self):
        from app.ingestion.ingestion_service import _normalise_published_at
        src = _now() - timedelta(hours=5)
        published, meta = _normalise_published_at(src)
        assert published == src
        assert meta is None

    def test_small_future_skew_is_tolerated(self):
        from app.ingestion.ingestion_service import _normalise_published_at
        src = _now() + timedelta(minutes=10)
        published, meta = _normalise_published_at(src)
        assert published == src
        assert meta is None

    def test_far_future_timestamp_is_clamped_with_audit_trail(self):
        from app.ingestion.ingestion_service import _normalise_published_at
        src = _now() + timedelta(hours=6)
        published, meta = _normalise_published_at(src)
        assert abs((published - _now()).total_seconds()) < 5
        assert meta["provenance"] == "clamped_future"
        assert meta["raw"] == src.isoformat()

    def test_naive_source_timestamp_normalized_to_utc(self):
        from app.ingestion.ingestion_service import _normalise_published_at
        naive = (_now() - timedelta(hours=3)).replace(tzinfo=None)
        published, meta = _normalise_published_at(naive)
        assert published.tzinfo == timezone.utc
        assert meta is None

    def test_published_at_meta_round_trips_through_the_repository(self, session):
        from app.models.article import Article
        from app.repositories.article_repository import get_by_id, insert
        _IDS.append("rss_m8_meta")
        insert(session, Article(
            id="rss_m8_meta", source="sport5_sport",
            source_display_name="ספורט 5",
            url="https://example.test/rss_m8_meta", title="בדיקה",
            published_at=_now(),
            published_at_meta={"provenance": "ingest_fallback"},
            sport="basketball", event_type="news", importance="low",
        ))
        got = get_by_id(session, "rss_m8_meta")
        assert got.published_at_meta == {"provenance": "ingest_fallback"}
