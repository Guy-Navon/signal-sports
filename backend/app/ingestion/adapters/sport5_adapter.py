"""
Sport5 / ערוץ הספורט category-page scraping adapter (PR 13 pilot).

Sport5 has no public RSS feed (confirmed in PR 8 + PR 10 research), so this
adapter fetches category pages (server-rendered static HTML) and extracts
article cards. It is intentionally conservative:

- Static HTML only — httpx GET + BeautifulSoup (stdlib html.parser backend).
  No browser automation, no article-body scraping.
- Article anchors are identified by URL shape (articles.aspx + docID query),
  not by CSS class names, so cosmetic markup changes don't break parsing.
- Any network/parse failure is logged and skipped — fetch() never raises and
  returns [] in the worst case, so ingestion cannot crash on Sport5 problems.
- published_at is None; the ingestion service falls back to ingest time.
  (The category page shows timestamps, but sibling-text parsing is fragile —
  deferred until the pilot proves itself.)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.ingestion.adapters.base import RawSourceItem, SourceAdapter
from app.ingestion.subtitle import clean_subtitle

logger = logging.getLogger(__name__)

# Sport5 card timestamps are Israel local time. Prefer the IANA zone (DST-aware,
# via the tzdata package); fall back to a fixed UTC+2 if it is unavailable —
# an hour of DST drift is better than crashing or silently using UTC.
try:
    from zoneinfo import ZoneInfo
    _ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover — tzdata missing on this machine
    _ISRAEL_TZ = timezone(timedelta(hours=2))
    logger.warning("Asia/Jerusalem zone unavailable — Sport5 timestamps use fixed UTC+2")

# Anchors whose href contains both markers are article links
# (e.g. /articles.aspx?FolderID=274&docID=550732). Case-insensitive.
_ARTICLE_URL_MARKERS = ("articles.aspx", "docid=")

# Titles shorter than this are navigation labels / "read more" links, not headlines.
_MIN_TITLE_LENGTH = 15

# Subtitle candidates shorter than this are bylines/labels, not real subtitles.
_MIN_SUBTITLE_LENGTH = 10

# Card text that is a timestamp/byline, not a subtitle (e.g. "01.07.26 - 21:40").
_TIMESTAMP_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}")

# Full card timestamp: "01.07.26 - 21:40" (DD.MM.YY or DD.MM.YYYY, Israel local time).
_CARD_TIMESTAMP_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*-\s*(\d{1,2}):(\d{2})"
)


def _parse_card_timestamp(text: str) -> Optional[datetime]:
    """Parse a Sport5 card timestamp to a UTC datetime, or None if not one.

    "01.07.26 - 21:40" → 2026-07-01 21:40 Asia/Jerusalem → UTC (DST-aware).
    Returns None for text without a timestamp or with impossible field values.
    """
    match = _CARD_TIMESTAMP_RE.search(text)
    if match is None:
        return None
    day, month, year, hour, minute = (int(g) for g in match.groups())
    if year < 100:
        year += 2000
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=_ISRAEL_TZ)
    except ValueError:
        return None
    if not (2000 <= year <= 2100):
        return None
    return local.astimezone(timezone.utc)

_FETCH_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "SignalSports/0.1 (+https://github.com/signal-sports; ingestion pilot)"


def _is_article_href(href: str) -> bool:
    href_lower = href.lower()
    return all(marker in href_lower for marker in _ARTICLE_URL_MARKERS)


class Sport5ScrapeAdapter(SourceAdapter):
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

        for page_url in self.category_urls:
            html = self._fetch_page(page_url)
            if html is None:
                continue
            try:
                items.extend(self._parse_page(html, seen_urls))
            except Exception as exc:  # defensive: parsing must never crash ingestion
                logger.error(
                    "Sport5 parse failed for %s (%s): %s", self.source_id, page_url, exc
                )

        logger.info("Fetched %d items from %s (scrape)", len(items), self.source_id)
        return items

    # ── helpers ───────────────────────────────────────────────────────────────

    def _fetch_page(self, page_url: str) -> Optional[str]:
        try:
            response = httpx.get(
                page_url,
                timeout=_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
            return response.text
        except Exception as exc:
            logger.error(
                "Sport5 fetch failed for %s (%s): %s", self.source_id, page_url, exc
            )
            return None

    def _parse_page(self, html: str, seen_urls: set[str]) -> list[RawSourceItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[RawSourceItem] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or not _is_article_href(href):
                continue

            url = urljoin(self.base_url, href)
            if url in seen_urls:
                continue

            title = anchor.get_text(separator=" ", strip=True)
            if len(title) < _MIN_TITLE_LENGTH:
                continue

            seen_urls.add(url)
            items.append(
                RawSourceItem(
                    source_id=self.source_id,
                    url=url,
                    title=title,
                    # None when the card shows no timestamp → ingestion falls
                    # back to now(UTC), same as RSS entries without a date.
                    published_at=self._extract_card_published_at(anchor),
                    summary=self._extract_card_subtitle(anchor, title),
                )
            )

        return items

    @staticmethod
    def _card_containers(anchor):
        """Yield up to two ancestor containers that belong to this card only.

        Stops climbing once a container spans other articles (a card list,
        not this card) — otherwise card-level extraction would steal a
        neighbouring card's subtitle or timestamp.
        """
        own_href = anchor["href"].strip()
        container = anchor.parent
        for _ in range(2):
            if container is None:
                return
            hrefs = {
                a["href"].strip()
                for a in container.find_all("a", href=True)
                if _is_article_href(a["href"])
            }
            if hrefs - {own_href}:
                return
            yield container
            container = container.parent

    @classmethod
    def _extract_card_subtitle(cls, anchor, title: str) -> Optional[str]:
        """Best-effort subtitle from the article card surrounding the anchor.

        Sport5 category cards usually place a descriptive paragraph right under
        the headline anchor. Take the first paragraph-like text that is not the
        title itself, not a timestamp/byline, and long enough to be a real
        subtitle. Returns None when nothing qualifies — subtitle is optional,
        same as RSS entries without a <description>.
        """
        for container in cls._card_containers(anchor):
            for candidate in container.find_all(["p", "h4", "span"]):
                # Skip text that lives inside the headline anchor itself.
                if candidate.find_parent("a") is not None:
                    continue
                text = clean_subtitle(candidate.get_text(" ", strip=True) or "")
                if (
                    text
                    and text != title
                    and len(text) >= _MIN_SUBTITLE_LENGTH
                    and not _TIMESTAMP_RE.match(text)
                ):
                    return text
        return None

    @classmethod
    def _extract_card_published_at(cls, anchor) -> Optional[datetime]:
        """Publish time from the card's timestamp text ("01.07.26 - 21:40").

        Sport5 cards show the publish time as Israel local time next to the
        headline. Returns a UTC datetime, or None when the card has no
        parseable timestamp (the ingestion service then falls back to now).
        """
        for container in cls._card_containers(anchor):
            for candidate in container.find_all(["span", "p", "time", "div"]):
                if candidate.find_parent("a") is not None:
                    continue
                published = _parse_card_timestamp(
                    candidate.get_text(" ", strip=True) or ""
                )
                if published is not None:
                    return published
        return None
