"""
Tests for app.translation.translation_service and providers.

Translation providers are always mocked — no external API calls.
"""

import pytest
from unittest.mock import MagicMock

from app.translation.providers import NoopTranslationProvider, TranslationProvider
from app.translation.translation_service import translate_title, set_provider, reset_provider


@pytest.fixture(autouse=True)
def reset_after_test():
    """Reset the module-level cached provider after every test."""
    yield
    reset_provider()


class TestNoopProvider:
    def test_returns_none(self):
        noop = NoopTranslationProvider()
        assert noop.translate_title_to_hebrew("Hello world", "en") is None

    def test_any_language_returns_none(self):
        noop = NoopTranslationProvider()
        assert noop.translate_title_to_hebrew("Ciao mondo", "it") is None


class MockProvider(TranslationProvider):
    def __init__(self, response: str):
        self._response = response
        self.call_count = 0

    def translate_title_to_hebrew(self, text: str, source_language: str):
        self.call_count += 1
        return self._response


class FailingProvider(TranslationProvider):
    def translate_title_to_hebrew(self, text: str, source_language: str):
        raise RuntimeError("API unavailable")


class TestTranslateTitle:
    def test_hebrew_source_is_not_translated(self):
        mock = MockProvider("should not appear")
        set_provider(mock)
        result = translate_title("מכבי תל אביב", "he")
        assert result is None
        assert mock.call_count == 0

    def test_non_hebrew_calls_provider(self):
        mock = MockProvider("פריז באסקטבול מנהלת מגעים")
        set_provider(mock)
        result = translate_title("Paris Basketball tratta Dave Joerger", "it")
        assert result == "פריז באסקטבול מנהלת מגעים"
        assert mock.call_count == 1

    def test_provider_failure_returns_none(self):
        set_provider(FailingProvider())
        result = translate_title("Some title", "en")
        assert result is None

    def test_inline_provider_override(self):
        mock = MockProvider("תרגום")
        result = translate_title("Title", "en", provider=mock)
        assert result == "תרגום"

    def test_noop_provider_returns_none_for_english(self):
        set_provider(NoopTranslationProvider())
        result = translate_title("Deni Avdija signs with Portland", "en")
        assert result is None

    def test_title_and_language_forwarded_to_provider(self):
        recorded = {}

        class CapturingProvider(TranslationProvider):
            def translate_title_to_hebrew(self, text, source_language):
                recorded["text"] = text
                recorded["lang"] = source_language
                return "כותרת"

        set_provider(CapturingProvider())
        translate_title("Paris Basketball news", "it")
        assert recorded["text"] == "Paris Basketball news"
        assert recorded["lang"] == "it"
