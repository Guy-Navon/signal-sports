import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Set an isolated SQLite DB path BEFORE any app module is imported.
# This must run at module level so that when app.db.database is first imported
# (inside the fixture below), it picks up the test URL.
_tmp_dir = tempfile.mkdtemp(prefix="signal_sports_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"


@pytest.fixture(scope="session")
def client():
    # Import app modules AFTER the DATABASE_URL env var is set above.
    from app.main import create_app
    application = create_app()
    # TestClient enters the lifespan: creates tables and seeds the test DB.
    with TestClient(application) as c:
        yield c


# IDs of seed articles used by feed/scoring tests (must survive the rss-only filter).
_RSS_SEEDED_IDS = {
    "article_001",   # Maccabi negotiation → push for Guy
    "article_006",   # Hornets/Wizards → visible for Guy, hidden for Deni
    "article_007",   # Deni trade → push for both profiles
    "article_010",   # Lakers/Suns major_trade → high_feed, tests importance cap
    "article_012",   # Tennis early_round_result → hidden for Guy
    "article_014",   # Real Madrid EuroLeague → high_feed via euroleague topic
}


@pytest.fixture(scope="session")
def rss_seeded(client):
    """Insert rss_-prefixed copies of key seed articles so the rss-only feed filter works.

    The feed and /api/articles endpoints now only return articles whose id starts with
    'rss_'. Seed articles (id='article_NNN') are excluded from those endpoints but remain
    in the DB for the single-article lookup tests and persistence checks.
    """
    from app.db.database import SessionLocal
    from app.repositories.article_repository import insert, get_by_id
    from app.seed.seed_articles import SEED_ARTICLES
    from app.models.article import Article

    seed_map = {a.id: a for a in SEED_ARTICLES if a.id in _RSS_SEEDED_IDS}

    with SessionLocal() as session:
        for orig_id, article in seed_map.items():
            rss_id = f"rss_{orig_id}"
            if get_by_id(session, rss_id) is not None:
                continue
            data = article.model_dump()
            data["id"] = rss_id
            data["url"] = f"https://rss.test.local/{orig_id}"
            insert(session, Article(**data))

    return client
