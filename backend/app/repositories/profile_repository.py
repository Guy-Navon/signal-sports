from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ProfileRow
from app.models.profile import UserProfile, TopicPreference


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
