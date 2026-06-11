from typing import Optional, List
from pydantic import BaseModel
from app.models.article import Article


class DecisionResult(BaseModel):
    decision: str  # hidden | low_feed | feed | high_feed | push
    matched_topic: Optional[str] = None
    matched_entities: List[str] = []
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []


class ScoredArticle(BaseModel):
    article: Article
    decision: str
    matched_topic: Optional[str] = None
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []
