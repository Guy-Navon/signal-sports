from datetime import datetime
from pydantic import BaseModel


class FeedbackEvent(BaseModel):
    id: str
    user_id: str
    article_id: str
    # more_like_this | not_interested | never_show | mute_source | always_notify
    action: str
    created_at: datetime


class FeedbackRequest(BaseModel):
    user_id: str
    article_id: str
    action: str
