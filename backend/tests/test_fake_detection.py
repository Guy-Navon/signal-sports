"""
Tests for app.translation.fake_detection.

No external dependencies.
"""

from app.translation.fake_detection import is_fake_translation, FAKE_PREFIX


class TestIsFakeTranslation:

    def test_fake_by_translated_title_prefix(self):
        assert is_fake_translation(
            title="תרגום בדיקה: Boston Celtics sign guard",
            translated_title="תרגום בדיקה: Boston Celtics sign guard",
        ) is True

    def test_fake_by_title_prefix_no_translated_title(self):
        assert is_fake_translation(
            title="תרגום בדיקה: Some article",
            translated_title=None,
        ) is True

    def test_fake_by_title_prefix_translated_title_is_none(self):
        # translated_title may not be stored even if title has the prefix
        assert is_fake_translation(
            title="תרגום בדיקה: Deni Avdija news",
            translated_title=None,
        ) is True

    def test_real_hebrew_translation_is_not_fake(self):
        assert is_fake_translation(
            title="בוסטון סלטיקס חתמו על גארד חדש",
            translated_title="בוסטון סלטיקס חתמו על גארד חדש",
        ) is False

    def test_real_translation_with_none_translated_title(self):
        # A Hebrew title that is NOT a stub
        assert is_fake_translation(
            title="מכבי תל אביב במשא ומתן",
            translated_title=None,
        ) is False

    def test_english_original_title_not_fake(self):
        # Articles not yet translated — original RSS title in English
        assert is_fake_translation(
            title="Boston Celtics sign new guard",
            translated_title=None,
        ) is False

    def test_partial_prefix_not_fake(self):
        # Only the exact prefix counts
        assert is_fake_translation(
            title="תרגום בדיקה",  # missing colon
            translated_title=None,
        ) is False

    def test_prefix_in_translated_title_but_not_title(self):
        # Translated title has stub prefix; title might differ
        assert is_fake_translation(
            title="Some English title",
            translated_title="תרגום בדיקה: Some English title",
        ) is True

    def test_known_fake_translation_from_provider(self):
        stub = f"{FAKE_PREFIX} Paris Basketball tratta Dave Joerger"
        assert is_fake_translation(title=stub, translated_title=stub) is True

    def test_empty_strings_not_fake(self):
        assert is_fake_translation(title="", translated_title=None) is False
        assert is_fake_translation(title="", translated_title="") is False
