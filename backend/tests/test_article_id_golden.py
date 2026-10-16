"""Article ids are persisted and referenced everywhere; the scheme must never drift."""

import hashlib

from app.ingestion.dedup import article_id_from_url


def test_id_is_sha1_prefix_of_url():
    url = "https://example.com/a?b=1"
    expected = "rss_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    assert article_id_from_url(url) == expected


def test_unicode_url_is_supported():
    assert article_id_from_url("https://example.com/כדורסל").startswith("rss_")
