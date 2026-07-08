from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel


class FeedbackEvent(BaseModel):
    id: str
    user_id: str
    article_id: str
    # more_like_this | less_like_this | not_interested | never_show |
    # mute_source | always_notify | article_opened (passive slot, no learning)
    action: str
    created_at: datetime
    # Click-time context (issue #34): the decision + attribution captured
    # server-side when the event was submitted - the source for learned
    # adjustments (attribution is never rebuilt from titles).
    context: Optional[Dict] = None
    # Tombstone (issue #34): retracted events keep the log append-only while
    # excluding the event from derivation - undo restores prior state exactly.
    retracted: bool = False


class FeedbackRequest(BaseModel):
    user_id: str
    article_id: str
    action: str
