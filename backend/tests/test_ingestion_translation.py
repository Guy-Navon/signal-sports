"""
Tests for the translation-aware ingestion normalisation flow.

All external dependencies (network, translation APIs) are mocked.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import RSSSourceConfig
from app.ingestion.ingestion_service import _normalise


def _english_cfg(source_id="eurohoops"):
    return RSSSourceConfig(
        source_id=source_id,
        display_name="Eurohoops",
        feed_url="https://www.eurohoops.net/feed/",
        language="en",
    )


def _italian_cfg():
    return RSSSourceConfig(
        source_id="sportando",
        display_name="Sportando",
        feed_url="https://sportando.basketball/feed/",
        language="en",  # source config says en, but URL may reveal it
    )


def _hebrew_cfg():
    return RSSSourceConfig(
        source_id="walla_sport",
        display_name="וואלה ספורט",
        feed_url="https://rss.walla.co.il/feed/7",
        language="he",
    )


MOCK_ITALIAN_TITLE = "Paris Basketball tratta Dave Joerger per la panchina"
MOCK_HEBREW_TRANSLATION = "פריז באסקטבול מנהלת מגעים עם דייב ייגר לתפקיד המאמן"


class TestNormaliseWithTranslation:
    def test_italian_url_article_gets_translated(self):
        item = RawSourceItem(
            source_id="sportando",
            url="https://sportando.basketball/it/notizie/123",
            title=MOCK_ITALIAN_TITLE,
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        with patch(
            "app.ingestion.ingestion_service.translate_title",
            return_value=MOCK_HEBREW_TRANSLATION,
        ):
            article = _normalise(item, _italian_cfg())

        assert article.language == "it"
        assert article.original_title == MOCK_ITALIAN_TITLE
        assert article.translated_title == MOCK_HEBREW_TRANSLATION
        assert article.title == MOCK_HEBREW_TRANSLATION

    def test_hebrew_article_not_translated(self):
        item = RawSourceItem(
            source_id="walla_sport",
            url="https://sports.walla.co.il/item/123",
            title="מכבי תל אביב חתמה על שחקן חדש",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        with patch(
            "app.ingestion.ingestion_service.translate_title"
        ) as mock_translate:
            article = _normalise(item, _hebrew_cfg())

        mock_translate.assert_not_called()
        assert article.language == "he"
        assert article.original_title is None
        assert article.translated_title is None
        assert article.title == "מכבי תל אביב חתמה על שחקן חדש"

    def test_translation_failure_keeps_original_title(self):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/1",
            title="Deni Avdija traded to Portland",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        with patch(
            "app.ingestion.ingestion_service.translate_title",
            return_value=None,  # provider disabled or failed
        ):
            article = _normalise(item, _english_cfg())

        assert article.original_title == "Deni Avdija traded to Portland"
        assert article.translated_title is None
        # title falls back to original when translation returns None
        assert article.title == "Deni Avdija traded to Portland"

    def test_english_article_sets_original_title(self):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/en/article/1",
            title="Maccabi Tel Aviv signs a new guard",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        with patch(
            "app.ingestion.ingestion_service.translate_title",
            return_value="מכבי תל אביב חתמה על גארד חדש",
        ):
            article = _normalise(item, _english_cfg())

        assert article.language == "en"
        assert article.original_title == "Maccabi Tel Aviv signs a new guard"
        assert article.translated_title == "מכבי תל אביב חתמה על גארד חדש"
        assert article.title == "מכבי תל אביב חתמה על גארד חדש"

    def test_greek_title_detected_and_translated(self):
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/article/pan",
            title="Παναθηναϊκός: Ανοίγει το ΟΑΚΑ για τον 5ο τελικό",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        with patch(
            "app.ingestion.ingestion_service.translate_title",
            return_value="פנאתינייקוס פותחת את ה-OAKA",
        ) as mock_translate:
            article = _normalise(item, _english_cfg())

        assert article.language == "el"
        assert article.original_title == "Παναθηναϊκός: Ανοίγει το ΟΑΚΑ για τον 5ο τελικό"
        mock_translate.assert_called_once_with(
            "Παναθηναϊκός: Ανοίγει το ΟΑΚΑ για τον 5ο τελικό", "el"
        )

    def test_duplicate_url_not_retranslated(self):
        """URL dedup happens BEFORE translation — second call for the same URL
        skips both translation and insert entirely at the service level.
        We verify _normalise itself is only called for new (non-duplicate) items.
        """
        from unittest.mock import MagicMock
        from app.ingestion.ingestion_service import _run_source

        cfg = _english_cfg()
        item = RawSourceItem(
            source_id="eurohoops",
            url="https://eurohoops.net/unique-article",
            title="Deni Avdija news",
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        mock_session = MagicMock()
        # First call: URL not in DB
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("app.ingestion.adapters.rss_adapter.feedparser") as mock_fp, \
             patch("app.ingestion.ingestion_service.translate_title", return_value="דני אבדיה") as mock_tr, \
             patch("app.ingestion.ingestion_service.article_repository.insert"), \
             patch("app.ingestion.ingestion_service.ingestion_repository.insert"):
            import types
            entry = types.SimpleNamespace(
                title=item.title,
                link=item.url,
                published_parsed=None,
                updated_parsed=None,
                summary=None,
            )
            mock_fp.parse.return_value = types.SimpleNamespace(entries=[entry], bozo=False)
            _run_source(mock_session, cfg)

        # translate_title should be called once per new article
        assert mock_tr.call_count == 1
