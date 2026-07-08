from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ProfileRow
from app.models.profile import UserProfile, TopicPreference
from app.models.profile_v2 import ProfileV2


# ── Conversion helpers ────────────────────────────────────────────────────────

def _row_to_profile(row: ProfileRow) -> UserProfile:
    topics = [TopicPreference.model_validate(t) for t in (row.topics or [])]
    return UserProfile(
        user_id=row.user_id,
        display_name=row.display_name,
        language=row.language,
        profile_type=row.profile_type,
        topics=topics,
        muted_topics=row.muted_topics or [],
        muted_sources=row.muted_sources or [],
        followed_entities=row.followed_entities or [],
        profile_v2=ProfileV2.model_validate(row.profile_v2) if row.profile_v2 else None,
    )


def _profile_to_row(profile: UserProfile) -> ProfileRow:
    return ProfileRow(
        user_id=profile.user_id,
        display_name=profile.display_name,
        language=profile.language,
        profile_type=profile.profile_type,
        topics=[t.model_dump() for t in profile.topics],
        muted_topics=list(profile.muted_topics),
        muted_sources=list(profile.muted_sources),
        followed_entities=list(profile.followed_entities),
        profile_v2=profile.profile_v2.model_dump(mode="json") if profile.profile_v2 else None,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_all(session: Session) -> List[UserProfile]:
    rows = session.execute(select(ProfileRow)).scalars().all()
    return [_row_to_profile(r) for r in rows]


def get_by_id(session: Session, user_id: str) -> Optional[UserProfile]:
    row = session.get(ProfileRow, user_id)
    return _row_to_profile(row) if row else None


def count(session: Session) -> int:
    return session.query(ProfileRow).count()


def insert(session: Session, profile: UserProfile) -> None:
    session.add(_profile_to_row(profile))
    session.commit()


def update(session: Session, profile: UserProfile) -> None:
    """Full-row update for an existing profile (PUT /api/profiles/{user_id})."""
    row = session.get(ProfileRow, profile.user_id)
    if row is None:
        raise ValueError(f"profile {profile.user_id!r} does not exist")
    new_row = _profile_to_row(profile)
    row.display_name = new_row.display_name
    row.language = new_row.language
    row.profile_type = new_row.profile_type
    row.topics = new_row.topics
    row.muted_topics = new_row.muted_topics
    row.muted_sources = new_row.muted_sources
    row.followed_entities = new_row.followed_entities
    row.profile_v2 = new_row.profile_v2
    session.commit()


def set_profile_v2(session: Session, user_id: str, profile_v2: ProfileV2) -> None:
    """Write only the v2 payload (seed backfill for pre-existing rows)."""
    row = session.get(ProfileRow, user_id)
    if row is None:
        raise ValueError(f"profile {user_id!r} does not exist")
    row.profile_v2 = profile_v2.model_dump(mode="json")
    session.commit()
