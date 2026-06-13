"""
Tests for app.translation.language_detection.

No network, no external dependencies.
"""

import pytest

from app.translation.language_detection import detect_from_url, detect_from_text, detect_language


class TestDetectFromUrl:
    def test_english_path(self):
        assert detect_from_url("https://eurohoops.net/en/article") == "en"

    def test_italian_path(self):
        assert detect_from_url("https://sportando.basketball/it/notizie") == "it"

    def test_greek_path(self):
        assert detect_from_url("https://example.com/el/news") == "el"

    def test_turkish_path(self):
        assert detect_from_url("https://example.com/tr/haber") == "tr"

    def test_hebrew_path(self):
        assert detect_from_url("https://example.com/he/article") == "he"

    def test_no_language_path_returns_none(self):
        assert detect_from_url("https://www.eurohoops.net/feed/") is None

    def test_case_insensitive(self):
        assert detect_from_url("https://EXAMPLE.COM/IT/ARTICLE") == "it"

    def test_spanish_path(self):
        assert detect_from_url("https://example.com/es/news") == "es"

    def test_french_path(self):
        assert detect_from_url("https://example.com/fr/article") == "fr"


class TestDetectFromText:
    def test_hebrew_title(self):
        assert detect_from_text("מכבי תל אביב חתמה על שחקן חדש") == "he"

    def test_greek_title(self):
        assert detect_from_text("Παναθηναϊκός: Ανοίγει το ΟΑΚΑ") == "el"

    def test_cyrillic_returns_ru(self):
        assert detect_from_text("Российская сборная выиграла") == "ru"

    def test_latin_title_returns_none(self):
        # Pure Latin (English/Italian) — no Unicode script signal
        assert detect_from_text("Paris Basketball tratta Dave Joerger") is None

    def test_empty_string_returns_none(self):
        assert detect_from_text("") is None

    def test_mixed_hebrew_dominant(self):
        # Title with a few English chars but mostly Hebrew
        result = detect_from_text("NBA — מכבי תל אביב")
        assert result == "he"


class TestDetectLanguage:
    def test_url_takes_priority_over_text(self):
        # URL says /it/, title is English
        result = detect_language(
            "https://sportando.basketball/it/article",
            "Paris Basketball signs guard",
            "en",
        )
        assert result == "it"

    def test_text_used_when_url_has_no_hint(self):
        result = detect_language(
            "https://www.eurohoops.net/article/123",
            "מכבי תל אביב חתמה",
            "en",
        )
        assert result == "he"

    def test_greek_detected_from_text(self):
        result = detect_language(
            "https://eurohoops.net/article/pan",
            "Παναθηναϊκός: Ανοίγει το ΟΑΚΑ",
            "en",
        )
        assert result == "el"

    def test_default_used_when_no_hints(self):
        result = detect_language(
            "https://www.eurohoops.net/article/123",
            "Paris Basketball signs Dave Joerger",
            "en",
        )
        assert result == "en"

    def test_eurohoops_english_url(self):
        # Eurohoops English articles have /en/ in the URL
        result = detect_language(
            "https://www.eurohoops.net/en/nba-news/123",
            "Deni Avdija traded to Portland Trail Blazers",
            "en",
        )
        assert result == "en"

    def test_sportando_italian_detected_via_keyword_heuristic(self):
        # Sportando Italian articles have no /it/ in URL — must use keyword heuristic
        result = detect_language(
            "https://www.sportando.basketball/paris-basketball-dave-joerger",
            "Paris Basketball tratta Dave Joerger per la panchina",
            "en",  # source default — should be overridden
        )
        assert result == "it"

    def test_italian_fallback_does_not_trigger_for_english(self):
        result = detect_language(
            "https://www.eurohoops.net/article/123",
            "Deni Avdija signed a new contract",
            "en",
        )
        assert result == "en"


class TestDetectItalianFromText:
    def test_tratta_keyword(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("Paris Basketball tratta Dave Joerger") is True

    def test_panchina_keyword(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("Allenatore sulla panchina del Real Madrid") is True

    def test_stagione_keyword(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("Nuova stagione per la squadra") is True

    def test_english_text_is_not_italian(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("Deni Avdija traded to Portland Trail Blazers") is False

    def test_empty_string_is_not_italian(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("") is False

    def test_case_insensitive(self):
        from app.translation.language_detection import detect_italian_from_text
        assert detect_italian_from_text("TRATTA e ACCORDO") is True

    def test_mixed_italian_english_detected(self):
        from app.translation.language_detection import detect_italian_from_text
        # Real Sportando headline pattern: team name in English, verb in Italian
        assert detect_italian_from_text("Umana Reyer in EuroCup: stagione pluriennale") is True
