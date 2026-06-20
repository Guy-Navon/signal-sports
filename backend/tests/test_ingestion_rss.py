"""
Tests for RSS adapter normalisation, dedup, and the ingestion service.

All network / RSS parsing is mocked — tests never make real HTTP requests.
"""

import hashlib
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.dedup import article_id_from_url, url_already_exists
from app.ingestion.ingestion_service import _normalise
from app.ingestion.config import RSSSourceConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entry(title: str, link: str, published_parsed=None, summary=None):
    """Build a fake feedparser entry object."""
    entry = types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=published_parsed,
        updated_parsed=None,
        summary=summary,
    )
    return entry


def _make_feed(entries):
    return types.SimpleNamespace(entries=entries, bozo=False)


# ── Article ID ────────────────────────────────────────────────────────────────

class TestArticleIdFromUrl:
    def test_deterministic(self):
        url = "https://www.eurohoops.net/article/123"
        assert article_id_from_url(url) == article_id_from_url(url)

    def test_prefixed_rss(self):
        url = "https://www.eurohoops.net/article/123"
        assert article_id_from_url(url).startswith("rss_")

    def test_different_urls_produce_different_ids(self):
        url1 = "https://www.eurohoops.net/article/123"
        url2 = "https://www.eurohoops.net/article/456"
        assert article_id_from_url(url1) != article_id_from_url(url2)

    def test_id_length(self):
        # "rss_" + 20 hex chars = 24 chars total
        url = "https://example.com/article"
        assert len(article_id_from_url(url)) == 24


# ── RSS adapter fetch ─────────────────────────────────────────────────────────

class TestRSSAdapterFetch:
    def _adapter(self, source_id="eurohoops"):
        return RSSSourceAdapter(
            source_id=source_id,
            feed_url="https://fake.feed/rss",
            source_display_name="Test",
            language="en",
        )

    def test_happy_path_returns_items(self):
        entries = [
            _make_entry("Deni Avdija injured", "https://site.com/1"),
            _make_entry("Maccabi Tel Aviv signs guard", "https://site.com/2"),
        ]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            items = self._adapter().fetch()
        assert len(items) == 2
        assert items[0].title == "Deni Avdija injured"
        assert items[0].url == "https://site.com/1"
        assert items[0].source_id == "eurohoops"

    def test_skips_entries_without_link(self):
        bad = types.SimpleNamespace(title="No URL entry", link=None, published_parsed=None, updated_parsed=None, summary=None)
        good = _make_entry("Good entry", "https://site.com/good")
        with patch("feedparser.parse", return_value=_make_feed([bad, good])):
            items = self._adapter().fetch()
        assert len(items) == 1
        assert items[0].url == "https://site.com/good"

    def test_skips_entries_without_title(self):
        bad = types.SimpleNamespace(title="", link="https://site.com/notitle", published_parsed=None, updated_parsed=None, summary=None)
        with patch("feedparser.parse", return_value=_make_feed([bad])):
            items = self._adapter().fetch()
        assert items == []

    def test_network_error_returns_empty(self):
        with patch("feedparser.parse", side_effect=Exception("timeout")):
            items = self._adapter().fetch()
        assert items == []

    def test_published_at_parsed_from_struct_time(self):
        import time
        # Use a fixed time struct
        dt = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
        struct = time.strptime("2026-06-10 12:00:00", "%Y-%m-%d %H:%M:%S")
        entry = _make_entry("Title", "https://site.com/1", published_parsed=struct)
        with patch("feedparser.parse", return_value=_make_feed([entry])):
            items = self._adapter().fetch()
        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026


# ── Normalisation ─────────────────────────────────────────────────────────────

class TestNormalisation:
    def _english_cfg(self):
        return RSSSourceConfig(
            source_id="eurohoops",
            display_name="Eurohoops",
            feed_url="https://www.eurohoops.net/feed/",
            language="en",
        )

    def _hebrew_cfg(self):
        return RSSSourceConfig(
            source_id="walla",
            display_name="וואלה ספורט",
            feed_url="https://walla.co.il/rss",
            language="he",
        )

    @patch("app.ingestion.ingestion_service.translate_title", return_value=None)
    def test_english_source_sets_original_title(self, _mock_tr):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/1",
            title="Deni Avdija injured",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        article, _ = _normalise(item, self._english_cfg())
        assert article.original_title == "Deni Avdija injured"
        assert article.translated_title is None
        assert article.language == "en"

    def test_hebrew_source_leaves_original_title_none(self):
        item = RawSourceItem(
            source_id="walla",
            url="https://walla.co.il/1",
            title="מכבי ת״א בודקת שחקן",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        article, _ = _normalise(item, self._hebrew_cfg())
        assert article.original_title is None
        assert article.translated_title is None
        assert article.language == "he"
        assert article.title == "מכבי ת״א בודקת שחקן"

    def test_stable_id_from_url(self):
        url = "https://eurohoops.net/article/999"
        item = RawSourceItem(
            source_id="eurohoops",
            url=url,
            title="Some article",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        article, _ = _normalise(item, self._english_cfg())
        assert article.id == article_id_from_url(url)

    def test_missing_published_at_uses_now(self):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/no-date",
            title="Article without date",
            published_at=None,
        )
        before = datetime.now(tz=timezone.utc)
        article, _ = _normalise(item, self._english_cfg())
        after = datetime.now(tz=timezone.utc)
        assert before <= article.published_at <= after

    @patch("app.ingestion.ingestion_service.translate_title", return_value=None)
    def test_classification_flows_through(self, _mock_tr):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/deni-trade",
            title="Deni Avdija traded to new NBA team",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        article, _ = _normalise(item, self._english_cfg())
        assert article.sport == "basketball"
        assert article.league == "NBA"
        assert "Deni Avdija" in article.entities
        assert article.event_type == "major_trade"

    def test_subtitle_stored_from_raw_item_summary(self):
        """_normalise() must copy item.summary to article.subtitle."""
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/subtitle-test",
            title="Maccabi Tel Aviv signs guard",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            summary="The club completed a deal with a EuroLeague point guard.",
        )
        article, _ = _normalise(item, self._english_cfg())
        assert article.subtitle == "The club completed a deal with a EuroLeague point guard."

    def test_subtitle_is_none_when_item_has_no_summary(self):
        """_normalise() must set article.subtitle=None when item.summary is None."""
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/no-subtitle",
            title="Maccabi Tel Aviv news",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            summary=None,
        )
        article, _ = _normalise(item, self._english_cfg())
        assert article.subtitle is None


# ── Dedup ─────────────────────────────────────────────────────────────────────

class TestDedup:
    def test_url_exists_returns_true_when_article_present(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = object()
        assert url_already_exists(mock_session, "https://site.com/1") is True

    def test_url_exists_returns_false_when_absent(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        assert url_already_exists(mock_session, "https://site.com/new") is False
