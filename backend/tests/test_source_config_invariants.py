"""Static sanity checks on the ingestion source registry."""

from urllib.parse import urlparse

from app.ingestion.config import RSS_SOURCES


def test_source_ids_are_unique():
    ids = [c.source_id for c in RSS_SOURCES]
    assert len(ids) == len(set(ids))


def test_source_ids_are_slugs():
    for c in RSS_SOURCES:
        assert c.source_id == c.source_id.lower()
        assert " " not in c.source_id


def test_feed_urls_are_http_with_host():
    for c in RSS_SOURCES:
        u = urlparse(c.feed_url)
        assert u.scheme in ("http", "https"), c.source_id
        assert u.netloc, c.source_id


def test_every_source_has_display_name():
    assert all(c.display_name.strip() for c in RSS_SOURCES)
