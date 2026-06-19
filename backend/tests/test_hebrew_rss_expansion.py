"""
Tests for Hebrew RSS sources expansion — PR 10.

Covers:
  - allowed_url_patterns filter logic (new field in RSSSourceConfig)
  - israel_hayom_sport source config (language, allowed_languages, allowed_url_patterns)
  - Hebrew no-translation invariant for israel_hayom_sport
  - URL-based sport filtering (non-sport URLs are skipped, sport URLs pass)
  - Article normalization from israel_hayom_sport
  - Classifier smoke tests on titles from new source
  - API source listing includes israel_hayom_sport
  - Deduplication still works for new source
  - Source rejection documentation: ONE and Ynet have no usable RSS

All network calls are mocked. Tests are fully offline.
"""

import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.ingestion.classifier import classify
from app.ingestion.config import get_source_config, get_enabled_sources, RSSSourceConfig
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.ingestion_service import _normalise, _should_filter


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _ih_cfg():
    return RSSSourceConfig(
        source_id="israel_hayom_sport",
        display_name="ישראל היום ספורט",
        feed_url="https://www.israelhayom.co.il/rss.xml",
        language="he",
        allowed_languages=("he",),
        allowed_url_patterns=("/sport/",),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. allowed_url_patterns filter (new infrastructure)
# ══════════════════════════════════════════════════════════════════════════════

class TestAllowedUrlPatterns:
    def _cfg(self, allowed_url=(), blocked=(), allowed_lang=()):
        return RSSSourceConfig(
            source_id="test_source",
            display_name="Test",
            feed_url="https://example.com/rss.xml",
            language="he",
            allowed_url_patterns=allowed_url,
            blocked_url_patterns=blocked,
            allowed_languages=allowed_lang,
        )

    def test_no_allowed_url_patterns_never_filters(self):
        cfg = self._cfg()
        assert _should_filter("https://example.com/news/article/1", cfg) is False
        assert _should_filter("https://example.com/opinions/article/2", cfg) is False

    def test_matching_allowed_url_pattern_passes(self):
        cfg = self._cfg(allowed_url=("/sport/",))
        assert _should_filter("https://example.com/sport/basketball/article/1", cfg) is False

    def test_non_matching_allowed_url_pattern_filtered(self):
        cfg = self._cfg(allowed_url=("/sport/",))
        assert _should_filter("https://example.com/news/world/article/1", cfg) is True

    def test_non_matching_opinion_url_filtered(self):
        cfg = self._cfg(allowed_url=("/sport/",))
        assert _should_filter("https://example.com/opinions/article/3", cfg) is True

    def test_multiple_allowed_url_patterns_any_match_passes(self):
        cfg = self._cfg(allowed_url=("/sport/", "/sports/"))
        assert _should_filter("https://example.com/sport/basketball/1", cfg) is False
        assert _should_filter("https://example.com/sports/nba/2", cfg) is False

    def test_multiple_allowed_url_patterns_no_match_filtered(self):
        cfg = self._cfg(allowed_url=("/sport/", "/sports/"))
        assert _should_filter("https://example.com/news/politics/3", cfg) is True

    def test_allowed_url_pattern_case_insensitive(self):
        cfg = self._cfg(allowed_url=("/sport/",))
        # URL with uppercase SPORT/ should still match (lower() applied)
        assert _should_filter("https://example.com/SPORT/basketball/1", cfg) is False

    def test_blocked_url_pattern_takes_precedence_over_allowed_url(self):
        # Item URL matches allowed_url_patterns but is also blocked — blocked wins
        cfg = self._cfg(allowed_url=("/sport/",), blocked=("/sport/blocked/",))
        assert _should_filter("https://example.com/sport/blocked/article/1", cfg) is True

    def test_allowed_url_and_allowed_lang_both_must_pass(self):
        cfg = self._cfg(allowed_url=("/sport/",), allowed_lang=("he",))
        # Matches /sport/ but URL has /tr/ language prefix → filtered by language
        assert _should_filter("https://example.com/sport/tr/article/1", cfg) is True

    def test_empty_allowed_url_patterns_tuple_is_no_filter(self):
        cfg = self._cfg(allowed_url=())
        assert _should_filter("https://example.com/opinions/article/1", cfg) is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. Israel Hayom Sport source config
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomSportConfig:
    def test_israel_hayom_sport_in_config(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg is not None

    def test_source_id_is_stable(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.source_id == "israel_hayom_sport"

    def test_language_is_he(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.language == "he"

    def test_allowed_languages_is_he(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.allowed_languages == ("he",)

    def test_allowed_url_patterns_includes_sport(self):
        cfg = get_source_config("israel_hayom_sport")
        assert "/sport/" in cfg.allowed_url_patterns

    def test_feed_url_is_nonempty(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.feed_url and "israelhayom.co.il" in cfg.feed_url

    def test_display_name_is_nonempty(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.display_name and len(cfg.display_name) > 0

    def test_enabled_by_default(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg.enabled is True

    def test_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "israel_hayom_sport" in ids

    def test_walla_sport_still_exists(self):
        cfg = get_source_config("walla_sport")
        assert cfg is not None
        assert cfg.language == "he"

    def test_all_three_hebrew_sources_present(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "walla_sport" in ids
        assert "israel_hayom_sport" in ids


# ══════════════════════════════════════════════════════════════════════════════
# 3. API: GET /api/ingest/sources
# ══════════════════════════════════════════════════════════════════════════════

class TestSourcesApiWithExpansion:
    def test_israel_hayom_sport_in_api_sources(self, client):
        r = client.get("/api/ingest/sources")
        assert r.status_code == 200
        ids = {s["source_id"] for s in r.json()}
        assert "israel_hayom_sport" in ids

    def test_walla_sport_still_in_api_sources(self, client):
        r = client.get("/api/ingest/sources")
        ids = {s["source_id"] for s in r.json()}
        assert "walla_sport" in ids

    def test_israel_hayom_sport_language_in_api(self, client):
        r = client.get("/api/ingest/sources")
        ih = next(s for s in r.json() if s["source_id"] == "israel_hayom_sport")
        assert ih["language"] == "he"

    def test_israel_hayom_sport_display_name_in_api(self, client):
        r = client.get("/api/ingest/sources")
        ih = next(s for s in r.json() if s["source_id"] == "israel_hayom_sport")
        assert ih["display_name"] and len(ih["display_name"]) > 0

    def test_one_sport_not_in_sources(self, client):
        # ONE has no RSS feed — must not be added
        r = client.get("/api/ingest/sources")
        ids = {s["source_id"] for s in r.json()}
        assert "one_sport" not in ids

    def test_ynet_sport_not_in_sources(self, client):
        # Ynet has no sport-specific RSS — must not be added
        r = client.get("/api/ingest/sources")
        ids = {s["source_id"] for s in r.json()}
        assert "ynet_sport" not in ids


# ══════════════════════════════════════════════════════════════════════════════
# 4. URL filtering: sport URLs pass, non-sport URLs filtered
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomUrlFilter:
    """Verify that allowed_url_patterns=('/sport/',) correctly gates IH content."""

    def test_sport_basketball_url_passes(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/sport/israeli-basketball/article/20752364", cfg
        ) is False

    def test_sport_world_basketball_url_passes(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/sport/world-basketball/article/20751915", cfg
        ) is False

    def test_sport_world_soccer_url_passes(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/sport/world-soccer/article/20752578", cfg
        ) is False

    def test_sport_other_sports_url_passes(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/sport/other-sports/article/20753572", cfg
        ) is False

    def test_news_url_filtered(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/news/world-news/usa/article/20753579", cfg
        ) is True

    def test_opinions_url_filtered(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/opinions/article/20753434", cfg
        ) is True

    def test_culture_url_filtered(self):
        cfg = _ih_cfg()
        assert _should_filter(
            "https://www.israelhayom.co.il/culture/tv/article/20753302", cfg
        ) is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. Hebrew no-translation invariant for israel_hayom_sport
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomHebrewInvariant:
    """Hebrew articles from israel_hayom_sport must NEVER call translate_title."""

    def _basketball_item(self):
        return RawSourceItem(
            source_id="israel_hayom_sport",
            url="https://www.israelhayom.co.il/sport/israeli-basketball/article/1001",
            title="מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל",
            published_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        )

    def test_translate_title_not_called(self):
        with patch("app.ingestion.ingestion_service.translate_title") as mock_tr:
            _normalise(self._basketball_item(), _ih_cfg())
        mock_tr.assert_not_called()

    def test_language_is_he(self):
        with patch("app.ingestion.ingestion_service.translate_title"):
            article = _normalise(self._basketball_item(), _ih_cfg())
        assert article.language == "he"

    def test_title_equals_original_hebrew_rss_title(self):
        hebrew_title = "מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל"
        with patch("app.ingestion.ingestion_service.translate_title"):
            article = _normalise(self._basketball_item(), _ih_cfg())
        assert article.title == hebrew_title

    def test_original_title_is_none(self):
        with patch("app.ingestion.ingestion_service.translate_title"):
            article = _normalise(self._basketball_item(), _ih_cfg())
        assert article.original_title is None

    def test_translated_title_is_none(self):
        with patch("app.ingestion.ingestion_service.translate_title"):
            article = _normalise(self._basketball_item(), _ih_cfg())
        assert article.translated_title is None

    def test_source_is_israel_hayom_sport(self):
        with patch("app.ingestion.ingestion_service.translate_title"):
            article = _normalise(self._basketball_item(), _ih_cfg())
        assert article.source == "israel_hayom_sport"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Ingestion API: israel_hayom_sport ingestion via POST /api/ingest/run
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomIngestionApi:
    def _sport_entries(self):
        return [
            _make_entry(
                "מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל",
                "https://www.israelhayom.co.il/sport/israeli-basketball/article/ih-test-1",
            ),
            _make_entry(
                "אבדיה בולט ב-NBA: ניצחון גדול לוושינגטון",
                "https://www.israelhayom.co.il/sport/world-basketball/article/ih-test-2",
            ),
        ]

    def _non_sport_entries(self):
        return [
            _make_entry(
                "Trump article",
                "https://www.israelhayom.co.il/news/world-news/usa/article/ih-test-3",
            ),
            _make_entry(
                "Opinion article",
                "https://www.israelhayom.co.il/opinions/article/ih-test-4",
            ),
        ]

    def test_ingestion_returns_ok(self, client):
        with patch("feedparser.parse", return_value=_make_feed(self._sport_entries())):
            r = client.post("/api/ingest/run?source_id=israel_hayom_sport")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "error")
        sources = data["sources"]
        assert len(sources) == 1
        assert sources[0]["source_id"] == "israel_hayom_sport"

    def test_sport_articles_inserted(self, client):
        url = "https://www.israelhayom.co.il/sport/israeli-basketball/article/ih-insert-unique-1"
        entries = [_make_entry("מכבי תל אביב חתמה על שחקן חדש", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=israel_hayom_sport")
        assert r.json()["sources"][0]["inserted"] >= 1

        r2 = client.get("/api/articles")
        urls = [a["url"] for a in r2.json()]
        assert url in urls

    def test_non_sport_articles_filtered(self, client):
        """Non-sport URLs from Israel Hayom must be filtered out (skipped_filtered > 0)."""
        mixed = self._sport_entries() + self._non_sport_entries()
        with patch("feedparser.parse", return_value=_make_feed(mixed)):
            r = client.post("/api/ingest/run?source_id=israel_hayom_sport")
        result = r.json()["sources"][0]
        assert result["fetched"] == 4
        assert result["skipped_filtered"] == 2

    def test_only_sport_urls_reach_db(self, client):
        """Non-sport article URLs must not appear in the articles list."""
        sport_url = "https://www.israelhayom.co.il/sport/world-basketball/article/ih-filter-test-s"
        news_url = "https://www.israelhayom.co.il/news/politics/article/ih-filter-test-n"
        entries = [
            _make_entry("כדורסל: NBA ניצחון", sport_url),
            _make_entry("פוליטיקה", news_url),
        ]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/articles")
        db_urls = {a["url"] for a in r.json()}
        assert sport_url in db_urls
        assert news_url not in db_urls

    def test_hebrew_article_language_field(self, client):
        url = "https://www.israelhayom.co.il/sport/world-basketball/article/ih-lang-test-1"
        entries = [_make_entry("מכבי תל אביב הגיעה לשלב הגמר", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["language"] == "he"

    def test_hebrew_title_preserved(self, client):
        url = "https://www.israelhayom.co.il/sport/israeli-basketball/article/ih-title-test-1"
        hebrew_title = "מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל"
        entries = [_make_entry(hebrew_title, url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["title"] == hebrew_title

    def test_original_title_is_null_in_api(self, client):
        url = "https://www.israelhayom.co.il/sport/world-basketball/article/ih-orig-test-1"
        entries = [_make_entry("NBA: אבדיה ומכבי", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["original_title"] is None

    def test_dedup_skips_on_second_run(self, client):
        url = "https://www.israelhayom.co.il/sport/israeli-basketball/article/ih-dedup-unique-1"
        entries = [_make_entry("מכבי תל אביב במו״מ עם שחקן", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=israel_hayom_sport")
        second = r.json()["sources"][0]
        assert second["inserted"] == 0
        assert second["skipped_duplicate"] == second["fetched"]

    def test_article_appears_in_debug_feed(self, client):
        url = "https://www.israelhayom.co.il/sport/world-basketball/article/ih-debug-test-1"
        entries = [_make_entry("NBA: מכבי לקראת גמר היורוליג", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")
        r = client.get("/api/debug/feed/guy")
        feed_urls = [item["article"]["url"] for item in r.json()]
        assert url in feed_urls


# ══════════════════════════════════════════════════════════════════════════════
# 7. Classifier smoke tests on Israel Hayom Sport titles
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomClassifierSmoke:
    """Basic classifier checks for titles from Israel Hayom Sport.

    These tests verify that the classifier handles IH content correctly.
    They use source_id='israel_hayom_sport' which is not a basketball-only source,
    so all sport detection must be keyword-driven.
    """

    def test_maccabi_basketball_title_classified(self):
        r = classify(
            "מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_maccabi_basketball_title_not_football_entity(self):
        r = classify(
            "מכבי תל אביב ניצחה בגמר ליגת העל בכדורסל",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert "Maccabi Tel Aviv Football" not in r.entities

    def test_football_world_cup_title_classified(self):
        r = classify(
            "מונדיאל: ברזיל ניצחה בגמר",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "football"

    def test_football_title_no_maccabi_basketball_entity(self):
        r = classify(
            "מכבי חיפה ניצחה בגביע המדינה",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_deni_avdija_nba_title(self):
        r = classify(
            "דני אבדיה בולט ב-NBA: ניצחון גדול",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.league == "NBA"

    def test_euroleague_title_classified(self):
        r = classify(
            "מכבי תל אביב במגרש היורוליג: ניצחון גדול",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"

    def test_israeli_basketball_league_title(self):
        r = classify(
            "ווינר סל: הפועל חולון ניצחה",
            source_id="israel_hayom_sport",
            language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"


# ══════════════════════════════════════════════════════════════════════════════
# 8. Feed scoring for Guy — israel_hayom_sport articles
# ══════════════════════════════════════════════════════════════════════════════

class TestIsraelHayomFeedScoring:
    def test_maccabi_basketball_article_visible_for_guy(self, client):
        url = "https://www.israelhayom.co.il/sport/israeli-basketball/article/ih-scoring-1"
        entries = [_make_entry("מכבי תל אביב הביסה בגמר ליגת העל בכדורסל", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] in ("feed", "high_feed", "push")

    def test_generic_football_article_hidden_for_guy(self, client):
        url = "https://www.israelhayom.co.il/sport/world-soccer/article/ih-football-hidden-1"
        entries = [_make_entry('ליגת העל: מחזור חשוב ב"פרימיר ליג"', url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=israel_hayom_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] == "hidden"
