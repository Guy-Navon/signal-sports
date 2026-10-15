"""url_already_exists against a real (in-memory) SQLite session, not a mock."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.orm_models import ArticleRow, Base
from app.ingestion.dedup import article_id_from_url, url_already_exists


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _row(url: str) -> ArticleRow:
    return ArticleRow(
        id=article_id_from_url(url),
        source="test",
        source_display_name="Test",
        url=url,
        title="t",
        published_at="2026-01-01T00:00:00+00:00",
        sport="basketball",
        entities=[],
        event_type="other",
        importance="low",
        tags=[],
    )


def test_absent_url_is_not_a_duplicate(session):
    assert url_already_exists(session, "https://site.com/new") is False


def test_stored_url_is_a_duplicate(session):
    session.add(_row("https://site.com/1"))
    session.commit()
    assert url_already_exists(session, "https://site.com/1") is True


def test_only_exact_url_matches(session):
    session.add(_row("https://site.com/1"))
    session.commit()
    assert url_already_exists(session, "https://site.com/2") is False
