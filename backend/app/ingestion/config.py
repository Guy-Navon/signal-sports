"""
RSS source configuration.

Add entries here to register a new RSS source.
The feed_url is the only thing that needs to change per-source.
Ingestion logic (adapter, classifier, dedup) does not need to be touched.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RSSSourceConfig:
    source_id: str
    display_name: str
    feed_url: str
    language: str   # "en" | "he"
    enabled: bool = True


# ── Configured RSS sources ────────────────────────────────────────────────────
# Start with Eurohoops: basketball-only English source with a clean RSS feed.
# Add Sportando as a second source; same sport, different editorial angle.
# Hebrew sources (Walla, Sport5) require scraping adapters — deferred to PR 8.

RSS_SOURCES: list[RSSSourceConfig] = [
    RSSSourceConfig(
        source_id="eurohoops",
        display_name="Eurohoops",
        feed_url="https://www.eurohoops.net/feed/",
        language="en",
    ),
    RSSSourceConfig(
        source_id="sportando",
        display_name="Sportando",
        feed_url="https://sportando.basketball/feed/",
        language="en",
    ),
]


def get_source_config(source_id: str) -> RSSSourceConfig | None:
    for cfg in RSS_SOURCES:
        if cfg.source_id == source_id:
            return cfg
    return None


def get_enabled_sources() -> list[RSSSourceConfig]:
    return [cfg for cfg in RSS_SOURCES if cfg.enabled]
