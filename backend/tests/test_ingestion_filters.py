"""
Tests for PR 7.1 RSS quality guardrails:
- URL pattern blocking
- Language inference from URL
- skipped_filtered tracking
- Israeli Basketball League context inference
- EuroCup vs EuroLeague classification
- Generic news importance downgrade

All tests are offline — no network calls.
"""

import types
from unittest.mock import patch

import pytest

from app.ingestion.classifier import classify
from app.ingestion.config import RSSSourceConfig
from app.ingestion.ingestion_service import _should_filter
from app.translation.language_detection import detect_language


# ── Language inference from URL ───────────────────────────────────────────────

class TestInferLanguageFromUrl:
    """Tests for URL-based language inference (now in language_detection module)."""

    def test_english_path_returns_en(self):
        assert detect_language("https://eurohoops.net/en/article", "", "en") == "en"

    def test_turkish_path_returns_tr(self):
        assert detect_language("https://eurohoops.net/tr/haber", "", "en") == "tr"

    def test_spanish_path_returns_es(self):
        assert detect_language("https://eurohoops.net/es/noticia", "", "en") == "es"

    def test_greek_path_returns_el(self):
        assert detect_language("https://eurohoops.net/el/arthro", "", "en") == "el"

    def test_no_lang_path_returns_default(self):
        assert detect_language("https://eurohoops.net/2026/06/some-article", "", "en") == "en"

    def test_default_used_when_no_known_segment(self):
        assert detect_language("https://sportando.basketball/nba/article", "", "en") == "en"

    def test_case_insensitive(self):
        assert detect_language("https://example.com/TR/article", "", "en") == "tr"


# ── URL filter logic ──────────────────────────────────────────────────────────

class TestShouldFilter:
    def _cfg(self, blocked=(), allowed=()):
        return RSSSourceConfig(
            source_id="eurohoops",
            display_name="Eurohoops",
            feed_url="https://eurohoops.net/feed/",
            language="en",
            blocked_url_patterns=blocked,
            allowed_languages=allowed,
        )

    def test_no_filters_never_blocks(self):
        cfg = self._cfg()
        assert _should_filter("https://eurohoops.net/tr/article", cfg) is False

    def test_blocked_pattern_match(self):
        cfg = self._cfg(blocked=("/tr/",))
        assert _should_filter("https://eurohoops.net/tr/article", cfg) is True

    def test_blocked_pattern_no_match(self):
        cfg = self._cfg(blocked=("/tr/",))
        assert _should_filter("https://eurohoops.net/en/article", cfg) is False

    def test_multiple_blocked_patterns(self):
        cfg = self._cfg(blocked=("/tr/", "/es/", "/el/"))
        assert _should_filter("https://eurohoops.net/es/noticia", cfg) is True
        assert _should_filter("https://eurohoops.net/en/article", cfg) is False

    def test_allowed_languages_blocks_non_allowed(self):
        cfg = self._cfg(allowed=("en",))
        assert _should_filter("https://eurohoops.net/tr/article", cfg) is True

    def test_allowed_languages_passes_allowed(self):
        cfg = self._cfg(allowed=("en",))
        assert _should_filter("https://eurohoops.net/en/article", cfg) is False

    def test_allowed_languages_uses_default_when_no_path(self):
        cfg = self._cfg(allowed=("en",))
        # URL has no language path segment → default "en" → allowed
        assert _should_filter("https://eurohoops.net/article/123", cfg) is False

    def test_blocked_pattern_takes_precedence_over_allowed(self):
        # If the URL is both blocked by pattern AND the inferred lang is allowed,
        # the blocked_url_patterns check runs first and wins.
        cfg = self._cfg(blocked=("/tr/",), allowed=("en", "tr"))
        assert _should_filter("https://eurohoops.net/tr/article", cfg) is True


# ── Classifier: EuroCup ───────────────────────────────────────────────────────

class TestEuroCupClassification:
    def test_eurocup_in_title_is_eurocup_not_euroleague(self):
        r = classify("EuroCup: Monaco beats UNICS Kazan to advance", source_id="eurohoops", language="en")
        assert r.league == "EuroCup"
        assert r.sport == "basketball"

    def test_eurocup_in_url_is_eurocup(self):
        r = classify("Basketball: Monaco beats UNICS", source_id="eurohoops", language="en",
                     url="https://eurohoops.net/eurocup/2026/monaco-beats-unics")
        assert r.league == "EuroCup"

    def test_euroleague_title_without_eurocup_is_euroleague(self):
        r = classify("EuroLeague: Real Madrid top the standings", source_id="eurohoops", language="en")
        assert r.league == "EuroLeague"

    def test_eurocup_beats_euroleague_when_both_in_title(self):
        # Edge case: title mentions both — EuroCup should win
        r = classify(
            "Euroleague teams watch closely as EuroCup play-in results are released",
            source_id="eurohoops",
            language="en",
        )
        assert r.league == "EuroCup"

    def test_euro_cup_two_words(self):
        r = classify("Euro Cup preview: which teams advance to EuroLeague?", source_id="eurohoops", language="en")
        assert r.league == "EuroCup"


# ── Classifier: Israeli Basketball League context inference ───────────────────

class TestIsraeliLeagueContextInference:
    def test_maccabi_holon_infers_israeli_league(self):
        r = classify("Maccabi Tel Aviv beats Holon 92-88 in tight game", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_maccabi_hapoel_holon_infers_israeli_league(self):
        r = classify("Maccabi Tel Aviv defeats Hapoel Holon in overtime", source_id="eurohoops", language="en")
        assert r.league == "Israeli Basketball League"

    def test_maccabi_no_context_kw_league_remains_none(self):
        # Maccabi alone without any Israeli context keyword — league should not be inferred
        r = classify("Maccabi Tel Aviv roster preview for the season", source_id="eurohoops", language="en")
        # League may be None or EuroLeague depending on other keywords — just not Israeli
        assert r.league != "Israeli Basketball League"

    def test_maccabi_euroleague_kw_overrides_context(self):
        # EuroLeague keyword is detected first (ordered detection), so EuroLeague wins
        r = classify("Maccabi Tel Aviv in EuroLeague playoffs — game summary", source_id="eurohoops", language="en")
        assert r.league == "EuroLeague"

    def test_israeli_basketball_direct_kw(self):
        r = classify("Israeli Basketball League: winner league semi-finals tonight", source_id="eurohoops", language="en")
        assert r.league == "Israeli Basketball League"

    def test_maccabi_israeli_basketball_context(self):
        r = classify("Maccabi Tel Aviv wins Israeli Basketball game over Eilat", source_id="eurohoops", language="en")
        assert r.league == "Israeli Basketball League"


# ── Classifier: generic news importance downgrade ─────────────────────────────

class TestGenericNewsImportance:
    def test_news_without_entity_is_low(self):
        r = classify("NBA weekly roundup and general context", source_id="eurohoops", language="en")
        assert r.event_type == "news"
        assert r.importance == "low"

    def test_news_with_tracked_entity_is_not_low(self):
        # Deni Avdija mention without any event keyword still has a tracked entity
        r = classify("Deni Avdija in the spotlight this NBA season", source_id="eurohoops", language="en")
        # importance should not be low — entity is tracked
        assert r.importance != "low"

    def test_news_with_maccabi_entity_is_not_low(self):
        r = classify("Maccabi Tel Aviv season outlook and analysis", source_id="eurohoops", language="en")
        assert r.importance != "low"

    def test_signing_medium_or_above_regardless_of_entity(self):
        # Event type is signing → importance should be medium or higher
        r = classify("Panathinaikos sign American guard for next season", source_id="eurohoops", language="en")
        assert r.event_type == "signing"
        assert r.importance in ("medium", "high", "very_high")


# ── Skipped_filtered in API response ─────────────────────────────────────────

def _make_entry(title: str, link: str):
    return types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=None,
        updated_parsed=None,
        summary=None,
    )


def _make_feed(entries, bozo=False):
    return types.SimpleNamespace(entries=entries, bozo=bozo)


class TestSkippedFilteredInResponse:
    def test_skipped_filtered_field_present(self, client):
        entries = [_make_entry("Some article", "https://eurohoops.net/fake/filter-field-test")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=eurohoops")
        result = r.json()["sources"][0]
        assert "skipped_filtered" in result

    def test_skipped_filtered_is_zero_for_passing_url(self, client):
        entries = [_make_entry("EuroLeague: Barca wins", "https://eurohoops.net/en/euroleague/barca-wins-test")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=eurohoops")
        result = r.json()["sources"][0]
        # The URL passes through — skipped_filtered must be 0
        assert result["skipped_filtered"] == 0

    def test_blocked_url_pattern_counts_as_filtered(self, client):
        # Inject a Turkish-path URL; Eurohoops config blocks /tr/
        entries = [
            _make_entry("Turkish article", "https://eurohoops.net/tr/haber/baska-makale"),
            _make_entry("English article", "https://eurohoops.net/fake/filter-passing-en-test"),
        ]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=eurohoops")
        result = r.json()["sources"][0]
        # Turkish article should be filtered out
        assert result["skipped_filtered"] >= 1
        assert result["fetched"] == 2
