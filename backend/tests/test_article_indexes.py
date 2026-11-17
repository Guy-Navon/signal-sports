"""articles(published_at) and articles(cluster_id) are indexed (AUDIT_REPORT M3).

Both a fresh schema (create_all) and a legacy database that predates the
indexes (soft migrations) must end up with them, and migrating twice is a no-op.
"""
from sqlalchemy import create_engine, inspect, text

from app.db import database as db_module
from app.db.orm_models import Base

EXPECTED = {
    "ix_articles_published_at": ["published_at"],
    "ix_articles_cluster_id": ["cluster_id"],
}


def _article_indexes(eng):
    return {ix["name"]: ix["column_names"] for ix in inspect(eng).get_indexes("articles")}


def test_fresh_schema_has_the_indexes(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    Base.metadata.create_all(bind=eng)
    db_module._apply_migrations(eng)
    indexes = _article_indexes(eng)
    for name, cols in EXPECTED.items():
        assert indexes.get(name) == cols
    eng.dispose()


def test_legacy_database_gains_the_indexes_without_losing_rows(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        for name in EXPECTED:
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
        conn.execute(text(
            "INSERT INTO articles (id, source, source_display_name, url, title, language,"
            " published_at, sport, entities, event_type, importance, confidence, tags)"
            " VALUES ('a1', 's', 'S', 'https://x/1', 't', 'he', '2026-11-17T00:00:00+00:00',"
            " 'basketball', '[]', 'news', 'normal', 0.9, '[]')"))
    assert not set(EXPECTED) & set(_article_indexes(eng))

    db_module._apply_migrations(eng)
    db_module._apply_migrations(eng)  # idempotent

    indexes = _article_indexes(eng)
    for name, cols in EXPECTED.items():
        assert indexes.get(name) == cols
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM articles")).scalar() == 1
    eng.dispose()
