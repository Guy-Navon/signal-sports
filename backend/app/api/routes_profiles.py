from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.profile import UserProfile
from app.repositories import profile_repository

router = APIRouter()


@router.get("/profiles", response_model=List[UserProfile])
def list_profiles(session: Session = Depends(get_session)):
    return profile_repository.get_all(session)


@router.get("/profiles/{user_id}", response_model=UserProfile)
def get_profile(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return profile
