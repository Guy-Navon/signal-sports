"""
Seed-on-empty: populate all tables from static seed data when they are empty.
Idempotent — skips each table when it already has rows.
"""
from sqlalchemy.orm import Session

from app.repositories import (
    article_repository,
    profile_repository,
    source_repository,
    feedback_repository,
    calibration_repository,
)
from app.seed.seed_articles import SEED_ARTICLES
from app.seed.seed_profiles import SEED_PROFILES
from app.seed.seed_sources import SEED_SOURCES
from app.seed.seed_calibration import SEED_CALIBRATION_HEADLINES


def seed_all_if_empty(session: Session) -> None:
    if article_repository.count(session) == 0:
        for article in SEED_ARTICLES:
            article_repository.insert(session, article)

    if profile_repository.count(session) == 0:
        for profile in SEED_PROFILES:
            profile_repository.insert(session, profile)

    if source_repository.count(session) == 0:
        for source in SEED_SOURCES:
            source_repository.insert(session, source)

    if calibration_repository.count(session) == 0:
        for headline in SEED_CALIBRATION_HEADLINES:
            calibration_repository.insert(session, headline)
