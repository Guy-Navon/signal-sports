import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional

import feedparser

from app.ingestion.adapters.base import RawSourceItem, SourceAdapter
from app.ingestion.subtitle import extract_subtitle

logger = logging.getLogger(__name__)


class RSSSourceAdapter(SourceAdapter):
    def __init__(
        self,
        source_id: str,
        feed_url: str,
        source_display_name: str,
        language: str,
    ) -> None:
        self.source_id = source_id
        self.feed_url = feed_url
        self.source_display_name = source_display_name
        self.language = language

    def fetch(self) -> list[RawSourceItem]:
        try:
            feed = feedparser.parse(self.feed_url)
        except Exception as exc:
            logger.error("RSS fetch failed for %s (%s): %s", self.source_id, self.feed_url, exc)
            return []

        if getattr(feed, "bozo", False) and not feed.entries:
            logger.warning(
                "RSS parse warning for %s: %s",
                self.source_id,
                getattr(feed, "bozo_exception", "unknown parse error"),
            )

        items: list[RawSourceItem] = []
        for entry in feed.entries:
            url = getattr(entry, "link", None)
            if not url:
                continue
            title = (getattr(entry, "title", "") or "").strip()
            if not title:
                continue

            items.append(
                RawSourceItem(
                    source_id=self.source_id,
                    url=url,
                    title=title,
                    published_at=self._parse_date(entry),
                    summary=extract_subtitle(entry),
                )
            )

        logger.info("Fetched %d items from %s", len(items), self.source_id)
        return items

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date(entry) -> Optional[datetime]:
        for attr in ("published_parsed", "updated_parsed"):
            value = getattr(entry, attr, None)
            if value:
                try:
                    ts = _time.mktime(value)
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                except (OverflowError, OSError):
                    pass
        return None
