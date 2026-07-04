"""
Tests for the RSS source configuration — Hebrew MVP scope.

Verifies:
- Only Hebrew sources are active by default (walla_sport, israel_hayom_sport, ynet_sport)
- Eurohoops and Sportando remain in the codebase but are disabled by default
- ONE is not in the source list at all
"""

import pytest
from app.ingestion.config import get_source_config, get_enabled_sources, RSS_SOURCES


class TestEnabledSourcesMvp:
    def test_only_hebrew_sources_enabled(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert ids == {"walla_sport", "israel_hayom_sport", "ynet_sport"}

    def test_walla_sport_enabled(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "walla_sport" in ids

    def test_israel_hayom_sport_enabled(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "israel_hayom_sport" in ids

    def test_ynet_sport_enabled(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "ynet_sport" in ids

    def test_eurohoops_not_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "eurohoops" not in ids

    def test_sportando_not_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "sportando" not in ids


class TestDisabledSourcesPresent:
    """Eurohoops and Sportando must remain in RSS_SOURCES for post-MVP use."""

    def test_eurohoops_exists_in_rss_sources(self):
        cfg = get_source_config("eurohoops")
        assert cfg is not None
        assert cfg.source_id == "eurohoops"
        assert cfg.language == "en"

    def test_eurohoops_disabled_by_default(self):
        cfg = get_source_config("eurohoops")
        assert cfg.enabled is False

    def test_sportando_exists_in_rss_sources(self):
        cfg = get_source_config("sportando")
        assert cfg is not None
        assert cfg.source_id == "sportando"
        assert cfg.language == "en"

    def test_sportando_disabled_by_default(self):
        cfg = get_source_config("sportando")
        assert cfg.enabled is False


class TestActiveSourceConfig:
    def test_walla_sport_config(self):
        cfg = get_source_config("walla_sport")
        assert cfg is not None
        assert cfg.language == "he"
        assert cfg.enabled is True
        assert "rss.walla.co.il" in cfg.feed_url

    def test_israel_hayom_sport_config(self):
        cfg = get_source_config("israel_hayom_sport")
        assert cfg is not None
        assert cfg.language == "he"
        assert cfg.enabled is True
        assert "/sport/" in cfg.allowed_url_patterns

    def test_ynet_sport_config(self):
        cfg = get_source_config("ynet_sport")
        assert cfg is not None
        assert cfg.language == "he"
        assert cfg.enabled is True
        assert cfg.source_type == "rss"
        assert "StoryRss3.xml" in cfg.feed_url
        assert cfg.allowed_url_patterns == ()

    def test_hebrew_sources_allow_only_hebrew(self):
        for source_id in ("walla_sport", "israel_hayom_sport", "ynet_sport"):
            cfg = get_source_config(source_id)
            assert cfg.allowed_languages == ("he",), (
                f"{source_id} should only allow Hebrew articles"
            )


class TestRejectedSources:
    """ONE is explicitly not added because no public RSS exists."""

    def test_one_sport_not_in_sources(self):
        assert get_source_config("one_sport") is None
        ids = {c.source_id for c in RSS_SOURCES}
        assert "one_sport" not in ids

    def test_ynet_sport_is_now_configured(self):
        assert get_source_config("ynet_sport") is not None
        ids = {c.source_id for c in RSS_SOURCES}
        assert "ynet_sport" in ids
