"""
Tests for the translation backfill endpoint.

All translation calls are mocked — no external API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.models.article import Article
from app.models.translation import BackfillResult


def _make_article(
    article_id: str,
    title: str,
    language: str = "en",
    original_title: str = None,
    translated_title: str = None,
    source: str = "eurohoops",
) -> Article:
    return Article(
        id=f"rss_{article_id}",
        source=source,
        source_display_name="Eurohoops",
        url=f"https://eurohoops.net/{article_id}",
        title=title,
        original_title=original_title,
        translated_title=translated_title,
        language=language,
        published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        sport="basketball",
        league="EuroLeague",
        entities=[],
        event_type="news",
        importance="medium",
        confidence=0.70,
        tags=[],
    )


class TestBackfillLogic:
    """Unit tests that exercise the backfill endpoint logic through the FastAPI test client."""

    def _get_client(self):
        # Import here to use conftest DB isolation
        from app.main import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_backfill_dry_run_returns_summary(self):
        """Dry run must not write to DB but must return accurate candidate count."""
        italian = _make_article("it1", "Paris Basketball tratta Dave Joerger", language="en")
        hebrew = _make_article("he1", "מכבי תל אביב", language="he")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[italian, hebrew]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="פריז באסקטבול") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd:

            from app.api.routes_translation import backfill_translations
            from unittest.mock import MagicMock
            mock_session = MagicMock()

            result = backfill_translations(
                limit=None,
                source_id=None,
                dry_run=True,
                reclassify=False,
                session=mock_session,
            )

        assert isinstance(result, BackfillResult)
        assert result.dry_run is True
        assert result.skipped_hebrew == 1
        assert result.candidates == 1
        assert result.translated == 1
        mock_upd.assert_not_called()

    def test_backfill_skips_already_translated(self):
        already = _make_article(
            "en1", "פריז באסקטבול", language="en",
            original_title="Paris Basketball", translated_title="פריז באסקטבול"
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[already]):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.skipped_already_translated == 1
        assert result.candidates == 0
        assert result.translated == 0

    def test_backfill_skips_hebrew_articles(self):
        he1 = _make_article("he1", "מכבי תל אביב", language="he")
        he2 = _make_article("he2", "כדורסל", language="he")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[he1, he2]):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.skipped_hebrew == 2
        assert result.candidates == 0
        assert result.translated == 0

    def test_backfill_noop_provider_counts_as_skipped(self):
        item = _make_article("en1", "Some English title", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title", return_value=None):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.candidates == 1
        assert result.translated == 0
        # When provider returns None (noop), it increments skipped_already_translated
        assert result.skipped_already_translated >= 1

    def test_backfill_updates_db_for_candidate(self):
        item = _make_article("en1", "Paris Basketball news", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="פריז באסקטבול") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.article_repository.update_classification_fields"):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=True,
                session=MagicMock(),
            )

        assert result.translated == 1
        mock_upd.assert_called_once()
        call_kwargs = mock_upd.call_args[1]
        assert call_kwargs["title"] == "פריז באסקטבול"
        assert call_kwargs["translated_title"] == "פריז באסקטבול"
        assert call_kwargs["original_title"] == "Paris Basketball news"

    def test_backfill_handles_translation_error(self):
        item = _make_article("en1", "Some title", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   side_effect=RuntimeError("API error")):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.failed == 1
        assert result.status == "partial"
        assert len(result.errors) == 1
        assert "API error" in result.errors[0].error

    def test_backfill_respects_limit(self):
        items = [_make_article(f"en{i}", f"Title {i}", language="en") for i in range(10)]

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=items), \
             patch("app.api.routes_translation.translate_title", return_value="כותרת"), \
             patch("app.api.routes_translation.article_repository.update_translation_fields"), \
             patch("app.api.routes_translation.article_repository.update_classification_fields"):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=3, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.candidates == 3
        assert result.translated == 3

    def test_backfill_running_twice_skips_translated(self):
        """Second backfill run skips articles already translated in the first run."""
        # Simulate an article that has already been translated (first run updated it)
        already_done = _make_article(
            "en1", "כותרת עברית", language="en",
            original_title="English title", translated_title="כותרת עברית"
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[already_done]):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                session=MagicMock(),
            )

        assert result.candidates == 0
        assert result.translated == 0
        assert result.skipped_already_translated == 1
