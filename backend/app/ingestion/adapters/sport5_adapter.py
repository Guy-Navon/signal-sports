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
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.ingestion.adapters.base import RawSourceItem, SourceAdapter

logger = logging.getLogger(__name__)

# Anchors whose href contains both markers are article links
# (e.g. /articles.aspx?FolderID=274&docID=550732). Case-insensitive.
_ARTICLE_URL_MARKERS = ("articles.aspx", "docid=")

# Titles shorter than this are navigation labels / "read more" links, not headlines.
_MIN_TITLE_LENGTH = 15

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
                    published_at=None,  # ingestion falls back to now(UTC)
                    summary=None,
                )
            )

        return items
