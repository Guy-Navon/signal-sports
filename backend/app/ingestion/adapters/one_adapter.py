"""
ONE.co.il public JSON article adapter.

ONE does not expose a suitable public news RSS feed, but the public homepage
uses api.one.co.il JSON endpoints for article lists. This adapter consumes
those list endpoints and normalizes them into RawSourceItem objects so the
regular ingestion service handles filtering, deduplication, classification,
persistence, and observability.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from app.ingestion.adapters.base import RawSourceItem, SourceAdapter
from app.ingestion.subtitle import clean_subtitle

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    _ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover - tzdata missing on this machine
    _ISRAEL_TZ = timezone(timedelta(hours=2))
    logger.warning("Asia/Jerusalem zone unavailable - ONE timestamps use fixed UTC+2")

_FETCH_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "SignalSports/0.1 (+https://github.com/signal-sports; ONE source)"


def _parse_one_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_ISRAEL_TZ)
    return parsed.astimezone(timezone.utc)


def _article_url(item: dict[str, Any], base_url: str) -> Optional[str]:
    raw_url = item.get("URL")
    if isinstance(raw_url, dict):
        url = raw_url.get("PC") or raw_url.get("Mobile")
    else:
        url = raw_url

    if not isinstance(url, str) or not url.strip():
        return None

    normalized = urljoin(base_url, url.strip())
    if "/Article/" not in normalized and "vole.one.co.il/item/" not in normalized:
        return None
    return normalized


def _article_title(item: dict[str, Any]) -> str:
    title = item.get("Title")
    if isinstance(title, dict):
        value = title.get("Main") or title.get("External")
    else:
        value = title
    return value.strip() if isinstance(value, str) else ""


def _article_subtitle(item: dict[str, Any]) -> Optional[str]:
    title = item.get("Title")
    if not isinstance(title, dict):
        return None
    summary = title.get("Secondary")
    if not isinstance(summary, str):
        return None
    return clean_subtitle(summary)


class OneSportAdapter(SourceAdapter):
    def __init__(
        self,
        source_id: str,
        category_urls: tuple[str, ...],
        base_url: str,
    ) -> None:
        self.source_id = source_id
        self.category_urls = category_urls
        self.base_url = base_url

    def fetch(self) -> list[RawSourceItem]:
        items: list[RawSourceItem] = []
        seen_urls: set[str] = set()

        for api_url in self.category_urls:
            payload = self._fetch_payload(api_url)
            if payload is None:
                continue
            try:
                items.extend(self._parse_payload(payload, seen_urls))
            except Exception as exc:  # defensive: parsing must not crash ingestion
                logger.error(
                    "ONE parse failed for %s (%s): %s", self.source_id, api_url, exc
                )

        logger.info("Fetched %d items from %s (ONE JSON)", len(items), self.source_id)
        return items

    def _fetch_payload(self, api_url: str) -> Optional[dict[str, Any]]:
        try:
            response = httpx.get(
                api_url,
                timeout=_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": self.base_url,
                    "User-Agent": _USER_AGENT,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.error("ONE fetch failed for %s (%s): %s", self.source_id, api_url, exc)
            return None

    def _parse_payload(
        self,
        payload: dict[str, Any],
        seen_urls: set[str],
    ) -> list[RawSourceItem]:
        items: list[RawSourceItem] = []
        for raw_item in self._iter_article_items(payload):
            try:
                item = self._parse_item(raw_item, seen_urls)
            except Exception as exc:
                logger.warning("ONE item skipped for %s: %s", self.source_id, exc)
                continue
            if item is not None:
                items.append(item)
        return items

    @staticmethod
    def _iter_article_items(payload: dict[str, Any]):
        articles = payload.get("Data", {}).get("Articles", {})
        direct_items = articles.get("Items")
        if isinstance(direct_items, list):
            yield from direct_items

        categories = articles.get("Categories")
        if isinstance(categories, list):
            for category in categories:
                items = category.get("Items") if isinstance(category, dict) else None
                if isinstance(items, list):
                    yield from items

    def _parse_item(
        self,
        item: Any,
        seen_urls: set[str],
    ) -> Optional[RawSourceItem]:
        if not isinstance(item, dict):
            return None
        if item.get("IsVideo") is True:
            return None

        url = _article_url(item, self.base_url)
        if url is None or url in seen_urls:
            return None

        title = _article_title(item)
        if not title:
            return None

        seen_urls.add(url)
        return RawSourceItem(
            source_id=self.source_id,
            url=url,
            title=title,
            published_at=_parse_one_datetime(item.get("Date")),
            summary=_article_subtitle(item),
        )
