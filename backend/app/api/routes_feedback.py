from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import List
import uuid
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.feedback import FeedbackEvent, FeedbackRequest
from app.repositories import feedback_repository, article_repository, profile_repository

router = APIRouter()

VALID_ACTIONS = {"more_like_this", "not_interested", "never_show", "mute_source", "always_notify"}


@router.post("/feedback", response_model=FeedbackEvent, status_code=201)
def submit_feedback(request: FeedbackRequest, session: Session = Depends(get_session)):
    if request.action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{request.action}'. Valid: {sorted(VALID_ACTIONS)}",
        )
    if not profile_repository.get_by_id(session, request.user_id):
        raise HTTPException(status_code=404, detail=f"Profile '{request.user_id}' not found")
    if not article_repository.get_by_id(session, request.article_id):
        raise HTTPException(status_code=404, detail=f"Article '{request.article_id}' not found")

    event = FeedbackEvent(
        id=str(uuid.uuid4()),
        user_id=request.user_id,
        article_id=request.article_id,
        action=request.action,
        created_at=datetime.now(timezone.utc),
    )
    feedback_repository.insert(session, event)
    return event


@router.get("/feedback/{user_id}", response_model=List[FeedbackEvent])
def get_feedback_for_user(user_id: str, session: Session = Depends(get_session)):
    if not profile_repository.get_by_id(session, user_id):
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return feedback_repository.get_by_user(session, user_id)
