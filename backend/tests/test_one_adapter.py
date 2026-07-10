# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
Tests for ONE Sport source onboarding.

Live inspection found no suitable public news RSS feed. ONE's current homepage
uses public api.one.co.il JSON article-list endpoints, where items include
Title.Main, Title.Secondary, Date, ID, URL.PC, IsVideo, and IsLive. Tests use
mocked JSON responses only; no live network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx

from app.api import routes_classify
from app.classification.source_hints import extract_source_sport_hint
from app.ingestion import ingestion_service
from app.ingestion.adapters.factory import build_adapter
from app.ingestion.adapters.one_adapter import OneSportAdapter, _parse_one_datetime
from app.ingestion.config import get_enabled_sources, get_source_config

HTTPX_GET = "app.ingestion.adapters.one_adapter.httpx.get"


def _one_item(
    article_id=527248,
    *,
    title='המספרים המטורפים מאחורי עסקת ים מדר למכבי ת"א',
    subtitle="הרכז יהפוך לישראלי המשתכר הגבוה בתולדות המועדון",
    url=None,
    date="2026-07-05T02:05:00",
    is_video=False,
):
    if url is None:
        url = f"https://www.one.co.il/Article/{article_id}.html"
    return {
        "IsLive": False,
        "LiveID": 0,
        "IsVideo": is_video,
        "Date": date,
        "Title": {
            "Main": title,
            "Secondary": subtitle,
            "External": title,
        },
        "ID": article_id,
        "URL": {
            "PC": url,
            "Mobile": url,
            "API": f"https://api.one.co.il/JSON/v6/Articles/{article_id}",
        },
    }


def _payload(items):
    return {
        "Version": 6,
        "UpdateTime": "2026-07-05T00:48:23Z",
        "DataName": "ArticlesBy_c2_page_1",
        "Data": {
            "Articles": {
                "Title": "כדורסל ישראלי",
                "Items": items,
            }
        },
    }


def _first_page_payload(items):
    return {
        "Version": 6,
        "Data": {
            "Articles": {
                "Categories": [
                    {"ID": 0, "Title": "Top", "Items": items},
                    {"ID": 1172, "Title": "ONE Podcasts", "Items": []},
                ]
            }
        },
    }


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _adapter():
    return OneSportAdapter(
        source_id="one_sport",
        category_urls=("https://api.one.co.il/JSON/v6/Articles/Category/2",),
        base_url="https://www.one.co.il/",
    )


class TestOneSourceConfig:
    def test_one_sport_configured_as_enabled_hebrew_json_source(self):
        cfg = get_source_config("one_sport")
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.language == "he"
        assert cfg.allowed_languages == ("he",)
        assert cfg.source_type == "html_scrape"
        assert cfg.is_pilot is False
        assert cfg.feed_url == "https://www.one.co.il/"
        assert cfg.category_urls

    def test_one_sport_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "one_sport" in ids
        assert "ynet_sport" in ids
        assert "sportando" not in ids
        assert "eurohoops" not in ids

    def test_one_sport_visible_in_sources_api(self, admin_client):
        response = admin_client.get("/api/ingest/sources")
        assert response.status_code == 200
        one = next(s for s in response.json() if s["source_id"] == "one_sport")
        assert one["display_name"] == "ONE ספורט"
        assert one["language"] == "he"
        assert one["enabled"] is True
        assert one["type"] == "html_scrape"
        assert one["is_pilot"] is False


class TestOneAdapter:
    def test_factory_builds_one_adapter(self):
        cfg = get_source_config("one_sport")
        adapter = build_adapter(cfg)
        assert isinstance(adapter, OneSportAdapter)
        assert adapter.category_urls == cfg.category_urls

    def test_parses_title_url_subtitle_and_timestamp(self):
        with patch(HTTPX_GET, return_value=_response(_payload([_one_item()]))):
            items = _adapter().fetch()

        assert len(items) == 1
        item = items[0]
        assert item.source_id == "one_sport"
        assert item.title == 'המספרים המטורפים מאחורי עסקת ים מדר למכבי ת"א'
        assert item.url == "https://www.one.co.il/Article/527248.html"
        assert item.summary == "הרכז יהפוך לישראלי המשתכר הגבוה בתולדות המועדון"
        assert item.published_at == datetime(2026, 7, 4, 23, 5, tzinfo=timezone.utc)

    def test_parses_first_page_categories_shape(self):
        with patch(HTTPX_GET, return_value=_response(_first_page_payload([_one_item()]))):
            items = _adapter().fetch()
        assert len(items) == 1
        assert items[0].url == "https://www.one.co.il/Article/527248.html"

    def test_relative_url_normalized(self):
        item = _one_item(527300, url="/Article/527300.html")
        with patch(HTTPX_GET, return_value=_response(_payload([item]))):
            items = _adapter().fetch()
        assert items[0].url == "https://www.one.co.il/Article/527300.html"

    def test_duplicate_urls_removed_within_fetch(self):
        item = _one_item(527248)
        with patch(HTTPX_GET, return_value=_response(_payload([item, item]))):
            items = _adapter().fetch()
        assert len(items) == 1

    def test_video_only_items_skipped(self):
        video = _one_item(527202, is_video=True)
        article = _one_item(527248)
        with patch(HTTPX_GET, return_value=_response(_payload([video, article]))):
            items = _adapter().fetch()
        assert [i.url for i in items] == ["https://www.one.co.il/Article/527248.html"]

    def test_missing_optional_metadata_keeps_item(self):
        item = _one_item(subtitle=None, date=None)
        with patch(HTTPX_GET, return_value=_response(_payload([item]))):
            items = _adapter().fetch()
        assert len(items) == 1
        assert items[0].summary is None
        assert items[0].published_at is None

    def test_malformed_individual_items_are_isolated(self):
        broken = {"Title": {"Main": "כותרת בלי כתובת"}}
        good = _one_item(527249)
        with patch(HTTPX_GET, return_value=_response(_payload([broken, good]))):
            items = _adapter().fetch()
        assert len(items) == 1
        assert items[0].url == "https://www.one.co.il/Article/527249.html"

    def test_network_failure_returns_empty(self):
        with patch(HTTPX_GET, side_effect=httpx.ConnectError("refused")):
            assert _adapter().fetch() == []

    def test_one_failed_page_does_not_kill_other_pages(self):
        adapter = OneSportAdapter(
            source_id="one_sport",
            category_urls=("https://api.one.co.il/a", "https://api.one.co.il/b"),
            base_url="https://www.one.co.il/",
        )
        responses = [httpx.ConnectError("refused"), _response(_payload([_one_item()]))]

        def side_effect(url, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch(HTTPX_GET, side_effect=side_effect):
            items = adapter.fetch()
        assert len(items) == 1


class TestOneTimestampParsing:
    def test_local_summer_timestamp_converts_to_utc(self):
        assert _parse_one_datetime("2026-07-05T02:05:00") == datetime(
            2026, 7, 4, 23, 5, tzinfo=timezone.utc
        )

    def test_utc_timestamp_converts_to_utc(self):
        assert _parse_one_datetime("2026-07-05T00:48:23Z") == datetime(
            2026, 7, 5, 0, 48, 23, tzinfo=timezone.utc
        )

    def test_invalid_timestamp_returns_none(self):
        assert _parse_one_datetime("not-a-date") is None
        assert _parse_one_datetime(None) is None


class TestOneIngestion:
    def test_ingests_one_article_with_hebrew_fields_and_subtitle(self, admin_client):
        with patch(HTTPX_GET, return_value=_response(_payload([_one_item(527500)]))):
            response = admin_client.post("/api/ingest/run?source_id=one_sport")
        assert response.status_code == 200
        result = response.json()["sources"][0]
        assert result["source_id"] == "one_sport"
        assert result["fetched"] == 1
        assert result["inserted"] == 1
        assert result["skipped_filtered"] == 0
        assert result["failed"] == 0

        article_response = admin_client.get("/api/articles")
        article = next(
            a for a in article_response.json()
            if a["url"] == "https://www.one.co.il/Article/527500.html"
        )
        assert article["source"] == "one_sport"
        assert article["source_display_name"] == "ONE ספורט"
        assert article["language"] == "he"
        assert article["original_title"] is None
        assert article["translated_title"] is None
        assert article["subtitle"] == "הרכז יהפוך לישראלי המשתכר הגבוה בתולדות המועדון"

    def test_dedup_skips_second_one_run(self, admin_client):
        payload = _payload([_one_item(527501)])
        with patch(HTTPX_GET, return_value=_response(payload)):
            admin_client.post("/api/ingest/run?source_id=one_sport")
        with patch(HTTPX_GET, return_value=_response(payload)):
            response = admin_client.post("/api/ingest/run?source_id=one_sport")

        second = response.json()["sources"][0]
        assert second["inserted"] == 0
        assert second["skipped_duplicate"] == second["fetched"]

    def test_one_article_appears_in_debug_feed(self, admin_client):
        with patch(HTTPX_GET, return_value=_response(_payload([_one_item(527502)]))):
            admin_client.post("/api/ingest/run?source_id=one_sport")

        response = admin_client.get("/api/debug/feed/guy")
        urls = [item["article"]["url"] for item in response.json()]
        assert "https://www.one.co.il/Article/527502.html" in urls

    def test_source_failure_isolated_in_run_all(self, admin_client):
        class EmptyAdapter:
            def fetch(self):
                return []

        class FailingAdapter:
            def fetch(self):
                raise RuntimeError("one unavailable")

        def build(cfg):
            return FailingAdapter() if cfg.source_id == "one_sport" else EmptyAdapter()

        with patch("app.ingestion.ingestion_service.build_adapter", side_effect=build):
            response = admin_client.post("/api/ingest/run")

        assert response.status_code == 200
        sources = response.json()["sources"]
        ids = {s["source_id"] for s in sources}
        assert {"walla_sport", "israel_hayom_sport", "ynet_sport", "one_sport"} <= ids
        one = next(s for s in sources if s["source_id"] == "one_sport")
        assert one["errors"] == ["Fetch error for one_sport: one unavailable"]


class TestOneHebrewBroadClassification:
    def test_one_is_in_ingestion_llm_eligible_set(self):
        assert "one_sport" in ingestion_service._HEBREW_BROAD_SOURCES

    def test_one_is_in_backfill_llm_eligible_set(self):
        assert "one_sport" in routes_classify._HEBREW_BROAD_SOURCES

    def test_classify_status_reports_one(self, admin_client):
        response = admin_client.get("/api/classify/status")
        assert response.status_code == 200
        assert "one_sport" in response.json()["hebrew_broad_sources"]


class TestOneSourceHints:
    def test_basketball_category_url_hint(self):
        url = "https://www.one.co.il/Article/26-27/5,100,0,0/527227.html"
        assert extract_source_sport_hint("one_sport", url) == "basketball"

    def test_football_category_url_hint(self):
        url = "https://www.one.co.il/Article/26-27/3,100,0,0/527252.html"
        assert extract_source_sport_hint("one_sport", url) == "football"

    def test_generic_one_article_url_has_no_hint(self):
        url = "https://www.one.co.il/Article/527248.html"
        assert extract_source_sport_hint("one_sport", url) is None
