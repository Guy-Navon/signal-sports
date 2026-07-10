from fastapi import APIRouter, Depends, HTTPException
from app.core.security_deps import require_admin
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.profile import UserProfile
from app.repositories import profile_repository

router = APIRouter()


@router.get("/profiles", response_model=List[UserProfile], dependencies=[Depends(require_admin)])
def list_profiles(session: Session = Depends(get_session)):
    return profile_repository.get_all(session)


@router.get("/profiles/{user_id}", response_model=UserProfile, dependencies=[Depends(require_admin)])
def get_profile(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return profile


@router.put("/profiles/{user_id}", response_model=UserProfile, dependencies=[Depends(require_admin)])
def put_profile(user_id: str, payload: UserProfile, session: Session = Depends(get_session)):
    """Profile mutation API (issue #32). Full-profile PUT; the pydantic
    models (incl. ProfileV2 affinity levels/targets/overrides) are the
    validation layer. The path user_id is authoritative — a mismatched
    payload user_id is rejected rather than silently renaming."""
    if payload.user_id != user_id:
        raise HTTPException(
            status_code=422,
            detail=f"payload user_id {payload.user_id!r} does not match path {user_id!r}",
        )
    existing = profile_repository.get_by_id(session, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    profile_repository.update(session, payload)
    return profile_repository.get_by_id(session, user_id)
