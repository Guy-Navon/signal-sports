"""
Source configuration (RSS + HTML-scraping sources).

Add entries here to register a new source.
For RSS sources, the feed_url is the only thing that needs to change per-source.
For html_scrape sources, set source_type="html_scrape" and list category_urls.
Ingestion logic (adapter factory, classifier, dedup) does not need to be touched.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RSSSourceConfig:
    source_id: str
    display_name: str
    feed_url: str
    language: str               # primary language of this source's content
    enabled: bool = True
    # URL sub-strings that cause an item to be skipped (case-insensitive).
    # Use this to block non-English path prefixes, category pages you don't want, etc.
    blocked_url_patterns: tuple[str, ...] = ()
    # If non-empty, only these languages are accepted; items whose inferred language
    # does not match are counted as skipped_filtered.
    allowed_languages: tuple[str, ...] = ()
    # If non-empty, only items whose URL contains at least one of these substrings
    # are accepted; other items are counted as skipped_filtered.
    # Use this as a category allowlist when the feed mixes sport and non-sport content.
    allowed_url_patterns: tuple[str, ...] = ()
    # ── PR 13: source type + scraping pilot fields ────────────────────────────
    # "rss" (default, feedparser) | "html_scrape" (category-page scraping).
    source_type: str = "rss"
    # html_scrape only: category pages to fetch and parse for article cards.
    # For RSS sources this stays empty; feed_url is used instead.
    category_urls: tuple[str, ...] = ()
    # Marks experimental scraping pilots in the API/UI (badge + docs).
    is_pilot: bool = False


# Conceptual alias — the config now covers non-RSS sources too.
SourceConfig = RSSSourceConfig


# ── Configured RSS sources ────────────────────────────────────────────────────

RSS_SOURCES: list[RSSSourceConfig] = [
    # ── Post-MVP / experimental sources (disabled by default) ─────────────────
    #
    # Eurohoops and Sportando are English-language basketball sources.
    # They work well but are out of scope for the Hebrew-only MVP.
    # Set enabled=True here to re-activate them for testing or post-MVP work.

    # Eurohoops: basketball-only English source.
    # Their feed includes multilingual paths (/tr/, /es/, /el/, etc.).
    # We block all non-English paths so we only store English articles.
    RSSSourceConfig(
        source_id="eurohoops",
        display_name="Eurohoops",
        feed_url="https://www.eurohoops.net/feed/",
        language="en",
        enabled=False,  # post-MVP: English source; disabled for Hebrew MVP
        allowed_languages=("en",),
        blocked_url_patterns=(
            "/tr/", "/es/", "/it/", "/el/", "/de/",
            "/fr/", "/ru/", "/sr/", "/pl/", "/cs/",
        ),
    ),
    # Sportando: basketball news site, primarily English content.
    # Unlike Eurohoops, Sportando does not mix languages via URL paths.
    # Content is in English; no URL-based filtering needed.
    RSSSourceConfig(
        source_id="sportando",
        display_name="Sportando",
        feed_url="https://sportando.basketball/feed/",
        language="en",
        enabled=False,  # post-MVP: English/Italian source; disabled for Hebrew MVP
        allowed_languages=("en",),
    ),

    # ── Active MVP sources ────────────────────────────────────────────────────

    # Walla Sport: Hebrew general sports feed (ספורט וואלה).
    # Feed ID 7 serves the Walla sport section (sports.walla.co.il).
    # Content is Hebrew-only; no language-path mixing or URL blocking needed.
    # Covers Israeli basketball (Maccabi, Israeli League, EuroCup), football,
    # tennis, and international sports including NBA and EuroLeague news.
    RSSSourceConfig(
        source_id="walla_sport",
        display_name="וואלה ספורט",
        feed_url="https://rss.walla.co.il/feed/7",
        language="he",
        allowed_languages=("he",),
    ),
    # Israel Hayom Sport: Hebrew general news site with a sport section.
    # The main RSS feed (rss.xml) mixes sport and non-sport content (politics,
    # opinions, culture). Sport articles always contain /sport/ in their URL.
    # allowed_url_patterns filters out all non-sport articles before dedup/insert.
    # Covers Israeli basketball (israeli-basketball), Israeli football, world
    # basketball (NBA/EuroLeague), world football, and other sports.
    RSSSourceConfig(
        source_id="israel_hayom_sport",
        display_name="ישראל היום ספורט",
        feed_url="https://www.israelhayom.co.il/rss.xml",
        language="he",
        allowed_languages=("he",),
        allowed_url_patterns=("/sport/",),
    ),
    # Ynet Sport: official Hebrew sport RSS feed. The feed is sport-specific
    # and currently returns title, link, description, pubDate, guid, and tags.
    # The generic RSS adapter handles the required fields; descriptions are
    # cleaned into subtitles by the shared subtitle pipeline.
    RSSSourceConfig(
        source_id="ynet_sport",
        display_name="ynet ספורט",
        feed_url="https://www.ynet.co.il/Integration/StoryRss3.xml",
        language="he",
        allowed_languages=("he",),
    ),
    # ONE Sport: no suitable public news RSS feed was found. The ONE homepage
    # uses public api.one.co.il JSON article-list endpoints, so this source
    # reuses the scraping adapter path while parsing stable JSON fields rather
    # than brittle presentation markup. Video-only feed/items are skipped.
    RSSSourceConfig(
        source_id="one_sport",
        display_name="ONE ספורט",
        feed_url="https://www.one.co.il/",   # base URL + Referer for API requests
        language="he",
        allowed_languages=("he",),
        source_type="html_scrape",
        category_urls=(
            "https://api.one.co.il/JSON/v6/Articles/Category/1",    # football Israel
            "https://api.one.co.il/JSON/v6/Articles/Category/2",    # basketball Israel
            "https://api.one.co.il/JSON/v6/Articles/Category/3",    # football world
            "https://api.one.co.il/JSON/v6/Articles/Category/5",    # basketball world
            "https://api.one.co.il/JSON/v6/Articles/Category/7",    # other sports
            "https://api.one.co.il/JSON/v6/Articles/Category/155",  # lower leagues
        ),
    ),

    # ── Scraping pilot (PR 13, disabled by default) ───────────────────────────

    # Sport5 / ערוץ הספורט: Hebrew sports site with NO public RSS (confirmed in
    # PR 8 + PR 10 research). Ingested via category-page HTML scraping — a pilot.
    # Disabled by default because scraping is structurally fragile (site markup
    # can change without notice) and the ingestion scheduler would hit it every
    # interval. Run manually with POST /api/ingest/run?source_id=sport5_sport,
    # or set enabled=True here to include it in scheduled/all-source runs.
    # Pilot scope: the basketball category page only (verified server-rendered
    # static HTML; article anchors /articles.aspx?FolderID=274&docID=...).
    RSSSourceConfig(
        source_id="sport5_sport",
        display_name="ערוץ הספורט",
        feed_url="https://www.sport5.co.il/",   # base URL (used for relative-URL resolution)
        language="he",
        enabled=False,  # pilot: enable manually after validating scrape quality
        allowed_languages=("he",),
        source_type="html_scrape",
        category_urls=(
            "https://www.sport5.co.il/liga.aspx?FolderID=273",  # basketball category
        ),
        is_pilot=True,
    ),
]


def get_source_config(source_id: str) -> RSSSourceConfig | None:
    for cfg in RSS_SOURCES:
        if cfg.source_id == source_id:
            return cfg
    return None


def get_enabled_sources() -> list[RSSSourceConfig]:
    return [cfg for cfg in RSS_SOURCES if cfg.enabled]
