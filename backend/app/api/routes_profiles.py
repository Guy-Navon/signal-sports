from fastapi import APIRouter, HTTPException
from typing import List
from app.db import db
from app.models.profile import UserProfile
from app.services.profile_service import get_all_profiles, get_profile_by_id

router = APIRouter()


@router.get("/profiles", response_model=List[UserProfile])
def list_profiles():
    return get_all_profiles(db)


@router.get("/profiles/{user_id}", response_model=UserProfile)
def get_profile(user_id: str):
    profile = get_profile_by_id(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return profile
