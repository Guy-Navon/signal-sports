# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
PR 13 — Sport5 / ערוץ הספורט scraping pilot tests.

All tests are fixture-driven: httpx.get is patched, no test touches the live site.

Coverage:
- Fixture parsing: item count, titles, junk anchors skipped
- Relative → absolute URL normalization
- In-fetch dedup (image anchor + title anchor to the same article)
- Missing/short titles skipped
- Network failure → [] (never raises)
- End-to-end: POST /api/ingest/run?source_id=sport5_sport inserts items,
  persists a run record, and skips duplicates on a second run
- Source hint: folderid=274 → basketball
- GET /api/ingest/sources exposes sport5 as html_scrape pilot, disabled
"""

import pathlib
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.classification.source_hints import extract_source_sport_hint
from app.ingestion.adapters.factory import build_adapter
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.adapters.sport5_adapter import Sport5ScrapeAdapter
from app.ingestion.config import get_source_config

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "sport5_category.html"
FIXTURE_HTML = FIXTURE_PATH.read_text(encoding="utf-8")

BASE_URL = "https://www.sport5.co.il/"
CATEGORY_URL = "https://www.sport5.co.il/liga.aspx?FolderID=273"


def make_adapter() -> Sport5ScrapeAdapter:
    return Sport5ScrapeAdapter(
        source_id="sport5_sport",
        category_urls=(CATEGORY_URL,),
        base_url=BASE_URL,
    )


def mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


HTTPX_GET = "app.ingestion.adapters.sport5_adapter.httpx.get"


# ── Fixture parsing ───────────────────────────────────────────────────────────

class TestFixtureParsing:
    def _fetch(self):
        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            return make_adapter().fetch()

    def test_expected_item_count(self):
        items = self._fetch()
        # Cards 1, 2, 3 (deduped), 6, 8 — nav/ads/empty/short/no-docID skipped.
        assert len(items) == 5

    def test_all_urls_absolute(self):
        for item in self._fetch():
            assert item.url.startswith("https://www.sport5.co.il/")

    def test_relative_url_normalized(self):
        urls = [i.url for i in self._fetch()]
        assert "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=550760" in urls

    def test_titles_extracted(self):
        titles = [i.title for i in self._fetch()]
        assert any("ים מדר" in t for t in titles)
        assert any("מקס היידיגר" in t for t in titles)

    def test_duplicate_anchor_deduplicated(self):
        urls = [i.url for i in self._fetch()]
        assert len(urls) == len(set(urls))
        dup_url = "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=550741"
        assert urls.count(dup_url) == 1

    def test_image_only_anchor_does_not_block_title_anchor(self):
        # Card 3: the empty image anchor comes first; the title anchor must win.
        items = self._fetch()
        item = next(i for i in items if "docID=550741" in i.url)
        assert "מקס היידיגר" in item.title

    def test_nav_and_ad_anchors_skipped(self):
        urls = [i.url for i in self._fetch()]
        assert not any("liga.aspx" in u for u in urls)
        assert not any("ads.example.com" in u for u in urls)
        assert not any("dayevents.aspx" in u for u in urls)

    def test_empty_and_short_titles_skipped(self):
        urls = [i.url for i in self._fetch()]
        assert not any("docID=550999" in u for u in urls)  # empty title
        assert not any("docID=550998" in u for u in urls)  # "עוד..." too short

    def test_source_id_set_on_all_items(self):
        for item in self._fetch():
            assert item.source_id == "sport5_sport"


# ── Card subtitle extraction ──────────────────────────────────────────────────

class TestSubtitleExtraction:
    def _fetch(self):
        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            return make_adapter().fetch()

    def _item(self, doc_id):
        return next(i for i in self._fetch() if f"docID={doc_id}" in i.url)

    def test_card_subtitle_extracted(self):
        item = self._item(550765)
        assert item.summary == "הגארד הישראלי ממשיך לרכז עניין רב"

    def test_second_card_subtitle_extracted(self):
        item = self._item(550736)
        assert item.summary == "הסנטר האמריקאי צפוי לעבור לקבוצה אירופית בקיץ הקרוב"

    def test_timestamp_span_not_used_as_subtitle(self):
        # Card 1 has a "01.07.26 - 21:40" span before the subtitle paragraph.
        item = self._item(550765)
        assert "01.07.26" not in (item.summary or "")

    def test_card_without_subtitle_returns_none(self):
        # Card 2 has only the headline anchor — and must NOT steal the
        # subtitle of a neighbouring card via a shared ancestor container.
        item = self._item(550760)
        assert item.summary is None

    def test_kicker_inside_anchor_not_used_as_subtitle(self):
        # Card 6's <span class="kicker"> lives inside the headline anchor.
        item = self._item(550553)
        assert item.summary is None

    def test_published_at_flows_into_article(self, admin_client):
        from app.db.database import SessionLocal
        from app.repositories.article_repository import get_by_id
        from app.ingestion.dedup import article_id_from_url

        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            admin_client.post("/api/ingest/run?source_id=sport5_sport")

        url = "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=550765"
        with SessionLocal() as session:
            article = get_by_id(session, article_id_from_url(url))
        assert article is not None
        # Card shows 01.07.26 - 21:40 Israel time (IDT, UTC+3) → 18:40 UTC.
        assert article.published_at.strftime("%Y-%m-%d %H:%M") == "2026-07-01 18:40"

    def test_subtitle_flows_into_article(self, admin_client):
        from app.db.database import SessionLocal
        from app.repositories.article_repository import get_by_id
        from app.ingestion.dedup import article_id_from_url

        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            admin_client.post("/api/ingest/run?source_id=sport5_sport")

        url = "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=550765"
        with SessionLocal() as session:
            article = get_by_id(session, article_id_from_url(url))
        assert article is not None
        assert article.subtitle == "הגארד הישראלי ממשיך לרכז עניין רב"


# ── Failure handling ──────────────────────────────────────────────────────────

class TestFailureHandling:
    def test_connect_error_returns_empty(self):
        with patch(HTTPX_GET, side_effect=httpx.ConnectError("refused")):
            assert make_adapter().fetch() == []

    def test_timeout_returns_empty(self):
        with patch(HTTPX_GET, side_effect=httpx.ReadTimeout("timed out")):
            assert make_adapter().fetch() == []

    def test_http_error_returns_empty(self):
        resp = mock_response("")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )
        with patch(HTTPX_GET, return_value=resp):
            assert make_adapter().fetch() == []

    def test_malformed_html_does_not_raise(self):
        with patch(HTTPX_GET, return_value=mock_response("<html><a href='x")):
            assert make_adapter().fetch() == []

    def test_one_failed_page_does_not_kill_other_pages(self):
        adapter = Sport5ScrapeAdapter(
            source_id="sport5_sport",
            category_urls=("https://a.example/1", "https://a.example/2"),
            base_url=BASE_URL,
        )
        responses = [httpx.ConnectError("refused"), mock_response(FIXTURE_HTML)]

        def side_effect(url, **kwargs):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch(HTTPX_GET, side_effect=side_effect):
            items = adapter.fetch()
        assert len(items) == 5


# ── Adapter factory ───────────────────────────────────────────────────────────

class TestAdapterFactory:
    def test_sport5_config_builds_scrape_adapter(self):
        cfg = get_source_config("sport5_sport")
        adapter = build_adapter(cfg)
        assert isinstance(adapter, Sport5ScrapeAdapter)
        assert adapter.category_urls == cfg.category_urls

    def test_rss_config_builds_rss_adapter(self):
        cfg = get_source_config("walla_sport")
        adapter = build_adapter(cfg)
        assert isinstance(adapter, RSSSourceAdapter)


# ── Config entry ──────────────────────────────────────────────────────────────

class TestSport5Config:
    def test_sport5_is_disabled_pilot_html_scrape(self):
        cfg = get_source_config("sport5_sport")
        assert cfg is not None
        assert cfg.enabled is False
        assert cfg.is_pilot is True
        assert cfg.source_type == "html_scrape"
        assert cfg.language == "he"
        assert cfg.category_urls  # non-empty

    def test_existing_sources_defaults_unchanged(self):
        for source_id in ("walla_sport", "israel_hayom_sport", "eurohoops", "sportando"):
            cfg = get_source_config(source_id)
            assert cfg.source_type == "rss"
            assert cfg.is_pilot is False
            assert cfg.category_urls == ()


# ── Source hint ───────────────────────────────────────────────────────────────

class TestSport5SourceHint:
    def test_basketball_folder_hint(self):
        url = "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=550765"
        assert extract_source_sport_hint("sport5_sport", url) == "basketball"

    def test_basketball_folder_hint_at_end_of_url(self):
        url = "https://www.sport5.co.il/articles.aspx?docID=1&FolderID=274"
        assert extract_source_sport_hint("sport5_sport", url) == "basketball"

    def test_other_folder_no_hint(self):
        url = "https://www.sport5.co.il/articles.aspx?FolderID=252&docID=550759"
        assert extract_source_sport_hint("sport5_sport", url) is None

    def test_folder_prefix_collision_no_hint(self):
        # folderid=2740 must NOT match the folderid=274 basketball hint.
        url = "https://www.sport5.co.il/articles.aspx?FolderID=2740&docID=1"
        assert extract_source_sport_hint("sport5_sport", url) is None

    def test_other_source_no_hint(self):
        url = "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=1"
        assert extract_source_sport_hint("walla_sport", url) is None


# ── End-to-end ingestion via API ──────────────────────────────────────────────

class TestSport5Ingestion:
    def test_manual_run_inserts_and_dedups(self, admin_client):
        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            first = admin_client.post("/api/ingest/run?source_id=sport5_sport")
            second = admin_client.post("/api/ingest/run?source_id=sport5_sport")

        assert first.status_code == 200
        result = first.json()["sources"][0]
        assert result["source_id"] == "sport5_sport"
        assert result["fetched"] == 5
        assert result["failed"] == 0
        # Other tests in the shared session may have ingested the fixture
        # already — every fetched item is either newly inserted or deduped.
        assert result["inserted"] + result["skipped_duplicate"] == 5

        result2 = second.json()["sources"][0]
        assert result2["inserted"] == 0
        assert result2["skipped_duplicate"] == 5

    def test_run_record_persisted(self, admin_client):
        runs = admin_client.get("/api/ingest/runs?limit=50").json()
        assert any(r["source_id"] == "sport5_sport" for r in runs)

    def test_network_failure_run_does_not_crash(self, admin_client):
        with patch(HTTPX_GET, side_effect=httpx.ConnectError("refused")):
            resp = admin_client.post("/api/ingest/run?source_id=sport5_sport")
        assert resp.status_code == 200
        result = resp.json()["sources"][0]
        assert result["fetched"] == 0
        assert result["failed"] == 0

    def test_sources_endpoint_exposes_sport5_pilot(self, admin_client):
        sources = admin_client.get("/api/ingest/sources").json()
        sport5 = next(s for s in sources if s["source_id"] == "sport5_sport")
        assert sport5["type"] == "html_scrape"
        assert sport5["is_pilot"] is True
        assert sport5["enabled"] is False
        assert sport5["display_name"] == "ערוץ הספורט"

    def test_sport5_excluded_from_run_all(self, admin_client):
        # enabled=False → not part of POST /api/ingest/run without source_id.
        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)), \
             patch("feedparser.parse", return_value=MagicMock(entries=[], bozo=False)):
            resp = admin_client.post("/api/ingest/run")
        source_ids = [s["source_id"] for s in resp.json()["sources"]]
        assert "sport5_sport" not in source_ids


# ── Card timestamp → published_at (PR 13.3) ───────────────────────────────────

from datetime import datetime, timezone as _tz

from app.ingestion.adapters.sport5_adapter import _parse_card_timestamp


class TestParseCardTimestamp:
    def test_summer_timestamp_converts_idt_to_utc(self):
        # July = Israel Daylight Time (UTC+3)
        dt = _parse_card_timestamp("01.07.26 - 21:40")
        assert dt == datetime(2026, 7, 1, 18, 40, tzinfo=_tz.utc)

    def test_winter_timestamp_converts_ist_to_utc(self):
        # January = Israel Standard Time (UTC+2)
        dt = _parse_card_timestamp("15.01.26 - 09:15")
        assert dt == datetime(2026, 1, 15, 7, 15, tzinfo=_tz.utc)

    def test_four_digit_year(self):
        dt = _parse_card_timestamp("01.07.2026 - 21:40")
        assert dt == datetime(2026, 7, 1, 18, 40, tzinfo=_tz.utc)

    def test_timestamp_embedded_in_longer_text(self):
        dt = _parse_card_timestamp("עודכן: 01.07.26 - 21:40 | מערכת")
        assert dt is not None

    def test_no_timestamp_returns_none(self):
        assert _parse_card_timestamp("הגארד הישראלי ממשיך לרכז עניין") is None
        assert _parse_card_timestamp("") is None

    def test_impossible_date_returns_none(self):
        assert _parse_card_timestamp("32.01.26 - 10:00") is None
        assert _parse_card_timestamp("01.13.26 - 10:00") is None
        assert _parse_card_timestamp("01.07.26 - 25:00") is None


class TestPublishedAtExtraction:
    def _fetch(self):
        with patch(HTTPX_GET, return_value=mock_response(FIXTURE_HTML)):
            return make_adapter().fetch()

    def _item(self, doc_id):
        return next(i for i in self._fetch() if f"docID={doc_id}" in i.url)

    def test_card_with_timestamp_gets_published_at(self):
        item = self._item(550765)
        assert item.published_at == datetime(2026, 7, 1, 18, 40, tzinfo=_tz.utc)

    def test_winter_card_timestamp(self):
        item = self._item(550736)
        assert item.published_at == datetime(2026, 1, 15, 7, 15, tzinfo=_tz.utc)

    def test_card_without_timestamp_returns_none(self):
        # Card 2 has only the headline anchor — falls back to ingest time
        # downstream, and must not steal a neighbouring card timestamp.
        item = self._item(550760)
        assert item.published_at is None

    def test_subtitle_still_extracted_alongside_timestamp(self):
        item = self._item(550736)
        assert item.summary == "הסנטר האמריקאי צפוי לעבור לקבוצה אירופית בקיץ הקרוב"
