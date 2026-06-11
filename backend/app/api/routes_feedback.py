from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid
from app.db import db
from app.models.feedback import FeedbackEvent, FeedbackRequest

router = APIRouter()

VALID_ACTIONS = {"more_like_this", "not_interested", "never_show", "mute_source", "always_notify"}


@router.post("/feedback", response_model=FeedbackEvent, status_code=201)
def submit_feedback(request: FeedbackRequest):
    if request.action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{request.action}'. Valid: {sorted(VALID_ACTIONS)}",
        )
    if request.user_id not in db.profiles:
        raise HTTPException(status_code=404, detail=f"Profile '{request.user_id}' not found")
    if request.article_id not in db.articles:
        raise HTTPException(status_code=404, detail=f"Article '{request.article_id}' not found")

    event = FeedbackEvent(
        id=str(uuid.uuid4()),
        user_id=request.user_id,
        article_id=request.article_id,
        action=request.action,
        created_at=datetime.now(timezone.utc),
    )
    db.feedback.append(event)
    return event
