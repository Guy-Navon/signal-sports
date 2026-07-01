"""
Effective source enabled-state: config.py default + DB override (PR 13.1).

config.py stays a pure, static registry. This module answers "is this source
enabled right now?" by consulting the source_overrides table first and falling
back to the config default. All runtime consumers (run-all ingestion, the
scheduler, the sources endpoint, source health) go through here.
"""

from sqlalchemy.orm import Session

from app.ingestion.config import RSS_SOURCES, RSSSourceConfig
from app.repositories import source_override_repository


def get_effective_enabled_map(session: Session) -> dict[str, bool]:
    """source_id → effective enabled for every configured source."""
    overrides = source_override_repository.get_all(session)
    return {
        cfg.source_id: overrides.get(cfg.source_id, cfg.enabled)
        for cfg in RSS_SOURCES
    }


def is_source_enabled(session: Session, cfg: RSSSourceConfig) -> bool:
    override = source_override_repository.get_override(session, cfg.source_id)
    return cfg.enabled if override is None else override


def get_effective_enabled_sources(session: Session) -> list[RSSSourceConfig]:
    enabled_map = get_effective_enabled_map(session)
    return [cfg for cfg in RSS_SOURCES if enabled_map[cfg.source_id]]
