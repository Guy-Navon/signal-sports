from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import List
import uuid
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.feedback import FeedbackEvent, FeedbackRequest
from app.repositories import feedback_repository, article_repository, profile_repository
from app.services.learning_service import build_click_context, with_learned
from app.services.preference_engine import score_article_v2

router = APIRouter()

VALID_ACTIONS = {
    "more_like_this", "less_like_this", "not_interested", "never_show",
    "mute_source", "always_notify",
    # Passive-behavior slot (issue #34): logged, never learning evidence.
    "article_opened",
}


@router.post("/feedback", response_model=FeedbackEvent, status_code=201)
def submit_feedback(request: FeedbackRequest, session: Session = Depends(get_session)):
    if request.action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{request.action}'. Valid: {sorted(VALID_ACTIONS)}",
        )
    profile = profile_repository.get_by_id(session, request.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{request.user_id}' not found")
    article = article_repository.get_by_id(session, request.article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{request.article_id}' not found")

    # Click-time context (issue #34): score with the same effective profile
    # the feed used (learned entries included) and store the decision +
    # attribution — learned adjustments never rebuild attribution later.
    context = None
    if profile.profile_v2 is not None:
        events = feedback_repository.get_active_by_user(session, request.user_id)
        effective = with_learned(profile, events)
        result = score_article_v2(article, effective)
        context = build_click_context(article, result)

    event = FeedbackEvent(
        id=str(uuid.uuid4()),
        user_id=request.user_id,
        article_id=request.article_id,
        action=request.action,
        created_at=datetime.now(timezone.utc),
        context=context,
    )
    feedback_repository.insert(session, event)
    return event


@router.get("/feedback/{user_id}", response_model=List[FeedbackEvent])
def get_feedback_for_user(user_id: str, session: Session = Depends(get_session)):
    if not profile_repository.get_by_id(session, user_id):
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return feedback_repository.get_by_user(session, user_id)
