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
from app.seed.seed_profiles import PROFILE_V2_SEEDS, SEED_PROFILES
from app.seed.seed_sources import SEED_SOURCES
from app.seed.seed_calibration import SEED_CALIBRATION_HEADLINES


def seed_all_if_empty(session: Session) -> None:
    if article_repository.count(session) == 0:
        for article in SEED_ARTICLES:
            article_repository.insert(session, article)

    if profile_repository.count(session) == 0:
        for profile in SEED_PROFILES:
            profile_repository.insert(session, profile)
    else:
        # ProfileV2 backfill (issue #32): pre-existing DBs seeded before the
        # v2 column get the seed v2 payload — only when missing, so a user-
        # edited v2 profile is never overwritten.
        for user_id, v2 in PROFILE_V2_SEEDS.items():
            existing = profile_repository.get_by_id(session, user_id)
            if existing is not None and existing.profile_v2 is None:
                profile_repository.set_profile_v2(session, user_id, v2)

    if source_repository.count(session) == 0:
        for source in SEED_SOURCES:
            source_repository.insert(session, source)

    if calibration_repository.count(session) == 0:
        for headline in SEED_CALIBRATION_HEADLINES:
            calibration_repository.insert(session, headline)
