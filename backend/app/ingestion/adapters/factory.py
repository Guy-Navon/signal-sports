"""
Adapter factory — maps a source config to the adapter that fetches it.

The ingestion service constructs adapters only through build_adapter(), so new
source types (e.g. html_scrape) plug in here without touching _run_source().
"""

from app.ingestion.adapters.base import SourceAdapter
from app.ingestion.adapters.one_adapter import OneSportAdapter
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.adapters.sport5_adapter import Sport5ScrapeAdapter
from app.ingestion.config import RSSSourceConfig


def build_adapter(cfg: RSSSourceConfig) -> SourceAdapter:
    if cfg.source_type == "html_scrape":
        if cfg.source_id == "one_sport":
            return OneSportAdapter(
                source_id=cfg.source_id,
                category_urls=cfg.category_urls,
                base_url=cfg.feed_url,
            )
        return Sport5ScrapeAdapter(
            source_id=cfg.source_id,
            category_urls=cfg.category_urls,
            base_url=cfg.feed_url,
        )
    return RSSSourceAdapter(
        source_id=cfg.source_id,
        feed_url=cfg.feed_url,
        source_display_name=cfg.display_name,
        language=cfg.language,
    )
