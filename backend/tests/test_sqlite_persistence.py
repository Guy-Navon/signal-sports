"""
SQLite persistence tests.

Verifies that:
- Tables are created on startup
- Seed data loads when the DB is empty
- Seeding is idempotent (no duplicate rows on repeated calls)
- All entity types (articles, profiles, sources, calibration) are persisted
- Feed scoring still works correctly end-to-end via SQLite
- Feedback events are persisted and readable
- Feedback survives an app restart (same SQLite file, new app instance)

All tests share the session-scoped `client` fixture from conftest.py, which
creates a temp SQLite DB and seeds it via the app lifespan.
"""
import pytest
from fastapi.testclient import TestClient


# ── Tables and seed data ─────────────────────────────────────────────────────

def test_tables_exist(client):
    """Sanity: the seeded DB has rows in all core tables."""
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow, ProfileRow, SourceRow, CalibrationHeadlineRow

    with SessionLocal() as session:
        assert session.query(ArticleRow).count() > 0
        assert session.query(ProfileRow).count() > 0
        assert session.query(SourceRow).count() > 0
        assert session.query(CalibrationHeadlineRow).count() > 0


def test_seed_loads_expected_article_count(client):
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.seed.seed_articles import SEED_ARTICLES

    with SessionLocal() as session:
        assert session.query(ArticleRow).count() == len(SEED_ARTICLES)


def test_seed_loads_expected_profile_count(client):
    from app.db.database import SessionLocal
    from app.db.orm_models import ProfileRow
    from app.seed.seed_profiles import SEED_PROFILES

    with SessionLocal() as session:
        assert session.query(ProfileRow).count() == len(SEED_PROFILES)


def test_seeding_is_idempotent(client):
    """Calling seed_all_if_empty a second time must not add rows."""
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow, ProfileRow
    from app.repositories.seed_runner import seed_all_if_empty

    with SessionLocal() as session:
        articles_before = session.query(ArticleRow).count()
        profiles_before = session.query(ProfileRow).count()

    with SessionLocal() as session:
        seed_all_if_empty(session)

    with SessionLocal() as session:
        assert session.query(ArticleRow).count() == articles_before
        assert session.query(ProfileRow).count() == profiles_before


# ── Articles via API ──────────────────────────────────────────────────────────

def test_articles_api_returns_seeded_articles(client):
    r = client.get("/api/articles")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0
    ids = {a["id"] for a in data}
    assert "article_001" in ids  # Maccabi negotiation
    assert "article_014" in ids  # Real Madrid EuroLeague


def test_article_response_shape_stable(client):
    """API response shape must include all expected fields."""
    r = client.get("/api/articles/article_001")
    assert r.status_code == 200
    a = r.json()
    assert a["id"] == "article_001"
    assert a["source"] == "sport5"
    assert a["source_display_name"] == "ספורט 5"
    assert "published_at" in a
    assert a["sport"] == "basketball"
    assert a["league"] == "EuroLeague"
    assert "Maccabi Tel Aviv Basketball" in a["entities"]
    assert a["event_type"] == "negotiation"
    assert a["importance"] == "high"
    assert isinstance(a["tags"], list)
    assert isinstance(a["confidence"], float)


# ── Profiles via API ──────────────────────────────────────────────────────────

def test_profiles_api_returns_seeded_profiles(client):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    data = r.json()
    user_ids = {p["user_id"] for p in data}
    assert "guy" in user_ids
    assert "casual_deni_fan" in user_ids


def test_profile_topics_survive_json_round_trip(client):
    """Topics stored as JSON must deserialize back with all nested fields intact."""
    r = client.get("/api/profiles/guy")
    assert r.status_code == 200
    profile = r.json()
    assert len(profile["topics"]) > 0
    maccabi_topic = next(
        (t for t in profile["topics"] if t["topic_id"] == "maccabi_tel_aviv_basketball"),
        None,
    )
    assert maccabi_topic is not None
    assert maccabi_topic["scope"] == "entity"
    assert maccabi_topic["mode"] == "all"
    assert "negotiation" in maccabi_topic["event_rules"]
    assert maccabi_topic["event_rules"]["negotiation"] == "push"


# ── Feed scoring via SQLite data ──────────────────────────────────────────────

def test_feed_for_guy_not_empty(client):
    r = client.get("/api/feed/guy")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_maccabi_negotiation_is_push_from_sqlite(client):
    r = client.get("/api/feed/guy")
    feed = r.json()
    article = next((a for a in feed if a["article"]["id"] == "article_001"), None)
    assert article is not None, "Maccabi negotiation not in Guy's feed"
    assert article["decision"] == "push"


def test_euroleague_real_madrid_is_high_feed_not_push(client):
    """article_014 (Real Madrid EuroLeague): high_feed via euroleague topic, not push via maccabi."""
    r = client.get("/api/debug/feed/guy")
    debug = r.json()
    article = next((a for a in debug if a["article"]["id"] == "article_014"), None)
    assert article is not None, "article_014 not in debug feed"
    assert article["decision"] == "high_feed", f"Expected high_feed, got {article['decision']}"
    assert article["matched_topic"] == "euroleague", (
        f"Expected matched_topic=euroleague, got {article['matched_topic']}"
    )


def test_debug_feed_includes_hidden_articles(client):
    r = client.get("/api/debug/feed/guy")
    debug = r.json()
    decisions = {a["decision"] for a in debug}
    assert "hidden" in decisions


def test_feed_has_fewer_items_than_debug(client):
    feed = client.get("/api/feed/guy").json()
    debug = client.get("/api/debug/feed/guy").json()
    assert len(feed) < len(debug)


# ── Feedback persistence ──────────────────────────────────────────────────────

def test_feedback_persisted_to_sqlite(client):
    """POST feedback → readable back via GET /api/feedback/{user_id}."""
    r = client.post("/api/feedback", json={
        "user_id": "guy",
        "article_id": "article_001",
        "action": "more_like_this",
    })
    assert r.status_code == 201
    feedback_id = r.json()["id"]

    r2 = client.get("/api/feedback/guy")
    assert r2.status_code == 200
    events = r2.json()
    assert any(e["id"] == feedback_id for e in events)


def test_feedback_readable_via_repository(client):
    """Feedback written via API is accessible directly through the repository."""
    r = client.post("/api/feedback", json={
        "user_id": "casual_deni_fan",
        "article_id": "article_007",
        "action": "always_notify",
    })
    assert r.status_code == 201
    feedback_id = r.json()["id"]

    from app.db.database import SessionLocal
    from app.repositories.feedback_repository import get_by_user

    with SessionLocal() as session:
        events = get_by_user(session, "casual_deni_fan")
    ids = [e.id for e in events]
    assert feedback_id in ids


def test_feedback_persists_across_app_restart(client):
    """
    Simulate a backend restart: create a second app instance using the same
    SQLite file (same DATABASE_URL env var). Feedback written by the first
    instance must be visible to the second instance.
    """
    # Write feedback via the session-scoped client
    r = client.post("/api/feedback", json={
        "user_id": "guy",
        "article_id": "article_002",
        "action": "never_show",
    })
    assert r.status_code == 201
    feedback_id = r.json()["id"]

    # Simulate restart: fresh app instance (same DB file via env var)
    from app.main import create_app
    fresh_app = create_app()
    with TestClient(fresh_app) as fresh_client:
        r2 = fresh_client.get("/api/feedback/guy")
        assert r2.status_code == 200
        events = r2.json()
        assert any(e["id"] == feedback_id for e in events), (
            "Feedback written before restart was not found after restart"
        )


# ── Response shape stability ──────────────────────────────────────────────────

def test_scored_article_response_shape(client):
    """ScoredArticle response must include article, decision, reasoning fields."""
    r = client.get("/api/feed/guy")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    item = items[0]
    assert "article" in item
    assert "decision" in item
    assert "reasoning" in item
    assert isinstance(item["reasoning"], list)
    assert "matched_topic" in item
    # Article sub-object must have all expected fields
    a = item["article"]
    assert "id" in a
    assert "source_display_name" in a
    assert "published_at" in a
    assert "event_type" in a


def test_calibration_headlines_returned_from_sqlite(client):
    r = client.get("/api/calibration/headlines")
    assert r.status_code == 200
    headlines = r.json()
    assert len(headlines) > 0
    h = headlines[0]
    assert "id" in h
    assert "title" in h
    assert "event_type" in h
    assert "sport" in h
