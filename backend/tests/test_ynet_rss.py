# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
Tests for Ynet Sport RSS onboarding.

The real feed inspected during implementation is RSS 2.0 at
https://www.ynet.co.il/Integration/StoryRss3.xml. Items contain title, link,
description with a thumbnail HTML block plus teaser text, pubDate, guid, and a
non-standard tags element. Tests mock feedparser output; no live network.
"""

import time
import types
from datetime import datetime, timezone
from unittest.mock import patch

from app.api import routes_classify
from app.ingestion import ingestion_service
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.config import get_enabled_sources, get_source_config


def _make_entry(
    title: str,
    link: str,
    *,
    summary: str | None = None,
    published_parsed=None,
):
    return types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=published_parsed,
        updated_parsed=None,
        summary=summary,
    )


def _make_feed(entries, bozo=False):
    return types.SimpleNamespace(entries=entries, bozo=bozo)


def _ynet_entry(url_suffix: str = "3odplmxzz"):
    return _make_entry(
        'המו"מ בין מכבי ת"א לים מדר חודש, הצהובים מנסים לסגור את העסקה',
        f"https://www.ynet.co.il/sport/israelibasketball/article/{url_suffix}",
        summary=(
            "<div><a href='https://www.ynet.co.il/sport/israelibasketball/article/"
            f"{url_suffix}'><img src='https://ynet-pic1.yit.co.il/picserver6/img.jpg'"
            " alt='' title='ים מדר' border='0' width='100' height='56'></a></div>"
            'הגארד הגיע לארץ לאחר המשחק נגד גרמניה לכמה שעות, '
            'ובאלופה מנסים לסגור איתו: "עושים הכל כדי שזה יקרה".'
        ),
        published_parsed=time.strptime(
            "Sat, 04 Jul 2026 17:58:14 +0300",
            "%a, %d %b %Y %H:%M:%S %z",
        ),
    )


class TestYnetSourceConfig:
    def test_ynet_sport_configured_as_enabled_hebrew_rss(self):
        cfg = get_source_config("ynet_sport")
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.language == "he"
        assert cfg.allowed_languages == ("he",)
        assert cfg.source_type == "rss"
        assert cfg.is_pilot is False
        assert cfg.feed_url == "https://www.ynet.co.il/Integration/StoryRss3.xml"

    def test_ynet_sport_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "ynet_sport" in ids
        assert "sportando" not in ids
        assert "eurohoops" not in ids

    def test_ynet_sport_visible_in_sources_api(self, admin_client):
        response = admin_client.get("/api/ingest/sources")
        assert response.status_code == 200
        ynet = next(s for s in response.json() if s["source_id"] == "ynet_sport")
        assert ynet["display_name"] == "ynet ספורט"
        assert ynet["language"] == "he"
        assert ynet["enabled"] is True
        assert ynet["type"] == "rss"
        assert ynet["is_pilot"] is False


class TestYnetRssAdapter:
    def _adapter(self):
        return RSSSourceAdapter(
            source_id="ynet_sport",
            feed_url="https://www.ynet.co.il/Integration/StoryRss3.xml",
            source_display_name="ynet ספורט",
            language="he",
        )

    def test_parses_title_url_subtitle_and_timestamp(self):
        with patch("feedparser.parse", return_value=_make_feed([_ynet_entry()])):
            items = self._adapter().fetch()

        assert len(items) == 1
        item = items[0]
        assert item.source_id == "ynet_sport"
        assert item.title == 'המו"מ בין מכבי ת"א לים מדר חודש, הצהובים מנסים לסגור את העסקה'
        assert item.url == "https://www.ynet.co.il/sport/israelibasketball/article/3odplmxzz"
        assert item.published_at is not None
        assert item.published_at.tzinfo == timezone.utc
        assert item.published_at.year == 2026
        assert item.published_at.month == 7
        assert "הגארד הגיע לארץ" in item.summary
        assert "<img" not in item.summary
        assert "ynet-pic" not in item.summary

    def test_skips_malformed_optional_fields_but_keeps_item(self):
        entry = _make_entry(
            "סנסציית ענק בווימבלדון",
            "https://www.ynet.co.il/sport/article/s1dbqoumfx",
            summary=None,
            published_parsed=None,
        )
        with patch("feedparser.parse", return_value=_make_feed([entry])):
            items = self._adapter().fetch()
        assert len(items) == 1
        assert items[0].summary is None
        assert items[0].published_at is None


class TestYnetIngestion:
    def test_ingests_ynet_article_with_hebrew_fields_and_subtitle(self, admin_client):
        with patch("feedparser.parse", return_value=_make_feed([_ynet_entry("ynet-insert-1")])):
            response = admin_client.post("/api/ingest/run?source_id=ynet_sport")
        assert response.status_code == 200
        result = response.json()["sources"][0]
        assert result["source_id"] == "ynet_sport"
        assert result["fetched"] == 1
        assert result["inserted"] == 1
        assert result["skipped_filtered"] == 0
        assert result["failed"] == 0

        article_response = admin_client.get("/api/articles")
        article = next(
            a for a in article_response.json()
            if a["url"] == "https://www.ynet.co.il/sport/israelibasketball/article/ynet-insert-1"
        )
        assert article["source"] == "ynet_sport"
        assert article["source_display_name"] == "ynet ספורט"
        assert article["language"] == "he"
        assert article["original_title"] is None
        assert article["translated_title"] is None
        assert article["subtitle"] is not None
        assert "הגארד הגיע לארץ" in article["subtitle"]
        assert article["sport"] == "basketball"

    def test_dedup_skips_second_ynet_run(self, admin_client):
        entry = _ynet_entry("ynet-dedup-1")
        with patch("feedparser.parse", return_value=_make_feed([entry])):
            admin_client.post("/api/ingest/run?source_id=ynet_sport")
        with patch("feedparser.parse", return_value=_make_feed([entry])):
            response = admin_client.post("/api/ingest/run?source_id=ynet_sport")

        second = response.json()["sources"][0]
        assert second["inserted"] == 0
        assert second["skipped_duplicate"] == second["fetched"]

    def test_ynet_article_appears_in_debug_feed(self, admin_client):
        entry = _ynet_entry("ynet-debug-1")
        with patch("feedparser.parse", return_value=_make_feed([entry])):
            admin_client.post("/api/ingest/run?source_id=ynet_sport")

        response = admin_client.get("/api/debug/feed/guy")
        urls = [item["article"]["url"] for item in response.json()]
        assert "https://www.ynet.co.il/sport/israelibasketball/article/ynet-debug-1" in urls

    def test_source_failure_isolated_in_run_all(self, admin_client):
        class EmptyAdapter:
            def fetch(self):
                return []

        class FailingAdapter:
            def fetch(self):
                raise RuntimeError("ynet unavailable")

        def build(cfg):
            return FailingAdapter() if cfg.source_id == "ynet_sport" else EmptyAdapter()

        with patch("app.ingestion.ingestion_service.build_adapter", side_effect=build):
            response = admin_client.post("/api/ingest/run")

        assert response.status_code == 200
        sources = response.json()["sources"]
        ids = {s["source_id"] for s in sources}
        assert {"walla_sport", "israel_hayom_sport", "ynet_sport"} <= ids
        ynet = next(s for s in sources if s["source_id"] == "ynet_sport")
        assert ynet["errors"] == ["Fetch error for ynet_sport: ynet unavailable"]


class TestYnetHebrewBroadClassification:
    def test_ynet_is_in_ingestion_llm_eligible_set(self):
        assert "ynet_sport" in ingestion_service._HEBREW_BROAD_SOURCES

    def test_ynet_is_in_backfill_llm_eligible_set(self):
        assert "ynet_sport" in routes_classify._HEBREW_BROAD_SOURCES

    def test_classify_status_reports_ynet(self, admin_client):
        response = admin_client.get("/api/classify/status")
        assert response.status_code == 200
        assert "ynet_sport" in response.json()["hebrew_broad_sources"]
