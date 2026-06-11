from typing import Optional, List
from app.models.profile import UserProfile


def get_all_profiles(db) -> List[UserProfile]:
    return list(db.profiles.values())


def get_profile_by_id(db, user_id: str) -> Optional[UserProfile]:
    return db.profiles.get(user_id)
