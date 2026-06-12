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


# ── Configured RSS sources ────────────────────────────────────────────────────

RSS_SOURCES: list[RSSSourceConfig] = [
    # Eurohoops: basketball-only English source.
    # Their feed includes multilingual paths (/tr/, /es/, /el/, etc.).
    # We block all non-English paths so we only store English articles.
    RSSSourceConfig(
        source_id="eurohoops",
        display_name="Eurohoops",
        feed_url="https://www.eurohoops.net/feed/",
        language="en",
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
        allowed_languages=("en",),
    ),
]


def get_source_config(source_id: str) -> RSSSourceConfig | None:
    for cfg in RSS_SOURCES:
        if cfg.source_id == source_id:
            return cfg
    return None


def get_enabled_sources() -> list[RSSSourceConfig]:
    return [cfg for cfg in RSS_SOURCES if cfg.enabled]
