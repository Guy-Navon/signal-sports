"""Effective source enabled-state: DB override wins over the config default."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.orm_models import Base
from app.ingestion.config import RSS_SOURCES
from app.ingestion.source_state import (
    get_effective_enabled_map,
    get_effective_enabled_sources,
    is_source_enabled,
)
from app.repositories import source_override_repository as overrides


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def test_no_overrides_uses_config_defaults(session):
    m = get_effective_enabled_map(session)
    assert m == {c.source_id: c.enabled for c in RSS_SOURCES}


def test_override_flips_config_default(session):
    cfg = RSS_SOURCES[0]
    overrides.set_override(session, cfg.source_id, not cfg.enabled)
    session.commit()
    assert is_source_enabled(session, cfg) is (not cfg.enabled)


def test_clear_override_restores_default(session):
    cfg = RSS_SOURCES[0]
    overrides.set_override(session, cfg.source_id, not cfg.enabled)
    session.commit()
    overrides.clear_override(session, cfg.source_id)
    session.commit()
    assert is_source_enabled(session, cfg) is cfg.enabled


def test_enabled_sources_matches_map(session):
    m = get_effective_enabled_map(session)
    assert {c.source_id for c in get_effective_enabled_sources(session)} == {
        k for k, v in m.items() if v
    }
