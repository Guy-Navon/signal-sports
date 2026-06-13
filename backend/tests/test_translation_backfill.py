"""
Tests for the translation backfill endpoint.

All translation calls are mocked — no external API calls.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone

from app.models.article import Article
from app.models.translation import BackfillResult
from app.translation.fake_detection import FAKE_PREFIX


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

    def test_backfill_dry_run_returns_summary(self):
        italian = _make_article("it1", "Paris Basketball tratta Dave Joerger", language="en")
        hebrew = _make_article("he1", "מכבי תל אביב", language="he")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[italian, hebrew]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="פריז באסקטבול") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):

            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=True, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert isinstance(result, BackfillResult)
        assert result.dry_run is True
        assert result.provider_ready is True
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
                   return_value=[already]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.skipped_already_translated == 1
        assert result.candidates == 0
        assert result.translated == 0

    def test_backfill_skips_hebrew_articles(self):
        he1 = _make_article("he1", "מכבי תל אביב", language="he")
        he2 = _make_article("he2", "כדורסל", language="he")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[he1, he2]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.skipped_hebrew == 2
        assert result.candidates == 0
        assert result.translated == 0

    def test_backfill_disabled_provider_returns_skipped_status(self):
        """When provider is not ready, backfill returns status='skipped', not 'ok'."""
        item = _make_article("en1", "Some English title", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={
                       "can_translate": False,
                       "reason": "TRANSLATION_PROVIDER is disabled",
                   }):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.status == "skipped"
        assert result.provider_ready is False
        assert result.translated == 0
        assert result.skipped_provider_not_ready == 1
        assert "disabled" in (result.reason or "")

    def test_backfill_updates_db_for_candidate(self):
        item = _make_article("en1", "Paris Basketball news", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="פריז באסקטבול") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.article_repository.update_classification_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=True,
                include_fake=False, force=False, session=MagicMock(),
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
                   side_effect=RuntimeError("API error")), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
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
             patch("app.api.routes_translation.article_repository.update_classification_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=3, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.candidates == 3
        assert result.translated == 3

    def test_backfill_running_twice_skips_translated(self):
        already_done = _make_article(
            "en1", "כותרת עברית", language="en",
            original_title="English title", translated_title="כותרת עברית"
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[already_done]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.candidates == 0
        assert result.translated == 0
        assert result.skipped_already_translated == 1

    def test_backfill_corrects_language_for_italian_title(self):
        """Backfill should detect Italian and correct article.language from 'en' to 'it'."""
        item = _make_article(
            "sp1",
            "Paris Basketball tratta Dave Joerger per la panchina",
            language="en",  # wrong — should be "it"
            source="sportando",
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="פריז באסקטבול") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.article_repository.update_classification_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.translated == 1
        assert result.language_corrected == 1
        # Language passed to translate_title should be "it" (detected), not "en"
        mock_tr.assert_called_once()
        lang_arg = mock_tr.call_args[0][1]  # second positional arg
        assert lang_arg == "it"
        # DB update should store corrected language
        call_kwargs = mock_upd.call_args[1]
        assert call_kwargs["language"] == "it"


class TestBackfillIncludeFake:

    def _fake_article(self, article_id, original="Boston Celtics sign guard"):
        stub = f"{FAKE_PREFIX} {original}"
        return _make_article(
            article_id,
            title=stub,
            language="en",
            original_title=original,
            translated_title=stub,
        )

    def test_include_fake_false_skips_stub_articles(self):
        """Default: stub-translated articles are counted as already-translated."""
        item = self._fake_article("en1")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=False, session=MagicMock(),
            )

        assert result.skipped_already_translated == 1
        assert result.candidates == 0
        assert result.translated == 0
        assert result.retranslated_fake == 0

    def test_include_fake_true_reprocesses_stub_articles(self):
        """include_fake=True makes stub-translated articles candidates."""
        item = self._fake_article("en1")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="בוסטון סלטיקס חתמו") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=True, force=False, session=MagicMock(),
            )

        assert result.candidates == 1
        assert result.translated == 1
        assert result.retranslated_fake == 1
        assert result.skipped_already_translated == 0

    def test_include_fake_uses_original_title_as_source(self):
        """Retranslation uses original_title, not the stub title."""
        item = self._fake_article("en1", original="Boston Celtics sign guard")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="בוסטון סלטיקס") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=True, force=False, session=MagicMock(),
            )

        mock_tr.assert_called_once()
        text_arg = mock_tr.call_args[0][0]
        assert text_arg == "Boston Celtics sign guard"
        assert FAKE_PREFIX not in text_arg

    def test_include_fake_writes_real_title_to_db(self):
        """DB update stores real Hebrew translation, not the stub."""
        item = self._fake_article("en1")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="בוסטון סלטיקס חתמו על שחקן"), \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=True, force=False, session=MagicMock(),
            )

        call_kwargs = mock_upd.call_args[1]
        assert call_kwargs["title"] == "בוסטון סלטיקס חתמו על שחקן"
        assert call_kwargs["translated_title"] == "בוסטון סלטיקס חתמו על שחקן"
        assert FAKE_PREFIX not in call_kwargs["title"]

    def test_include_fake_dry_run_does_not_write_db(self):
        item = self._fake_article("en1")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title", return_value="בוסטון"), \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=True, reclassify=False,
                include_fake=True, force=False, session=MagicMock(),
            )

        assert result.translated == 1
        assert result.retranslated_fake == 1
        mock_upd.assert_not_called()

    def test_include_fake_disabled_provider_returns_skipped(self):
        """Provider not ready + include_fake → skipped, not ok."""
        item = self._fake_article("en1")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": False, "reason": "disabled"}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=True, force=False, session=MagicMock(),
            )

        assert result.status == "skipped"
        assert result.provider_ready is False
        assert result.candidates == 1
        assert result.translated == 0


class TestBackfillForce:

    def test_force_retranslates_already_translated_article(self):
        """force=True re-translates articles that have a real translation."""
        item = _make_article(
            "en1", "מכבי תל אביב חתמה",
            language="en",
            original_title="Maccabi Tel Aviv sign guard",
            translated_title="מכבי תל אביב חתמה",
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title",
                   return_value="מכבי חתמה על גארד") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields") as mock_upd, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=True, session=MagicMock(),
            )

        assert result.candidates == 1
        assert result.translated == 1
        assert result.forced_retranslated == 1
        assert result.retranslated_fake == 0
        mock_tr.assert_called_once()
        text_arg = mock_tr.call_args[0][0]
        assert text_arg == "Maccabi Tel Aviv sign guard"

    def test_force_uses_original_title_as_source(self):
        item = _make_article(
            "en1", "מכבי תל אביב",
            language="en",
            original_title="Maccabi Tel Aviv news",
            translated_title="מכבי תל אביב",
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title", return_value="מכבי") as mock_tr, \
             patch("app.api.routes_translation.article_repository.update_translation_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=True, session=MagicMock(),
            )

        text_arg = mock_tr.call_args[0][0]
        assert text_arg == "Maccabi Tel Aviv news"

    def test_force_skips_stub_when_original_title_missing(self):
        """force=True but original_title is None and title is a stub → skip."""
        stub = f"{FAKE_PREFIX} Some title"
        item = _make_article(
            "en1", stub,
            language="en",
            original_title=None,
            translated_title=stub,
        )

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title") as mock_tr, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=True, session=MagicMock(),
            )

        mock_tr.assert_not_called()
        assert result.translated == 0
        assert result.skipped_provider_not_ready == 1

    def test_force_does_not_touch_hebrew_articles(self):
        """Hebrew articles are never retranslated even with force=True."""
        he = _make_article("he1", "מכבי תל אביב", language="he",
                           original_title="מכבי תל אביב", translated_title="מכבי תל אביב")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[he]), \
             patch("app.api.routes_translation.translate_title") as mock_tr, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=False, force=True, session=MagicMock(),
            )

        mock_tr.assert_not_called()
        assert result.skipped_hebrew == 1
        assert result.translated == 0

    def test_force_and_include_fake_together(self):
        """force=True takes priority over include_fake — all non-Hebrew are candidates."""
        real = _make_article("en1", "מכבי", language="en",
                             original_title="Maccabi news", translated_title="מכבי")
        stub = f"{FAKE_PREFIX} Some"
        fake = _make_article("en2", stub, language="en",
                             original_title="Some title", translated_title=stub)
        untranslated = _make_article("en3", "Deni Avdija news", language="en")

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[real, fake, untranslated]), \
             patch("app.api.routes_translation.translate_title", return_value="כותרת"), \
             patch("app.api.routes_translation.article_repository.update_translation_fields"), \
             patch("app.api.routes_translation.article_repository.update_classification_fields"), \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            result = backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=False,
                include_fake=True, force=True, session=MagicMock(),
            )

        assert result.candidates == 3
        assert result.translated == 3
        assert result.forced_retranslated == 2  # real + fake go through "forced" mode
        assert result.skipped_already_translated == 0

    def test_reclassify_after_retranslation(self):
        """reclassify=True still works after retranslation via include_fake."""
        stub = f"{FAKE_PREFIX} Boston Celtics"
        item = _make_article("en1", stub, language="en",
                             original_title="Boston Celtics news", translated_title=stub)

        with patch("app.api.routes_translation.article_repository.get_rss_articles",
                   return_value=[item]), \
             patch("app.api.routes_translation.translate_title", return_value="בוסטון סלטיקס"), \
             patch("app.api.routes_translation.article_repository.update_translation_fields"), \
             patch("app.api.routes_translation.article_repository.update_classification_fields") as mock_cl, \
             patch("app.api.routes_translation.classify") as mock_classify, \
             patch("app.api.routes_translation.get_provider_status",
                   return_value={"can_translate": True, "reason": None}):
            from app.api.routes_translation import backfill_translations
            backfill_translations(
                limit=None, source_id=None, dry_run=False, reclassify=True,
                include_fake=True, force=False, session=MagicMock(),
            )

        mock_classify.assert_called_once()
        classify_text = mock_classify.call_args[0][0]
        assert classify_text == "בוסטון סלטיקס"
        mock_cl.assert_called_once()
