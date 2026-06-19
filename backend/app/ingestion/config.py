"""
RSS source configuration.

Add entries here to register a new RSS source.
The feed_url is the only thing that needs to change per-source.
Ingestion logic (adapter, classifier, dedup) does not need to be touched.
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
]


def get_source_config(source_id: str) -> RSSSourceConfig | None:
    for cfg in RSS_SOURCES:
        if cfg.source_id == source_id:
            return cfg
    return None


def get_enabled_sources() -> list[RSSSourceConfig]:
    return [cfg for cfg in RSS_SOURCES if cfg.enabled]
