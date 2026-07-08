from typing import Dict, Optional, List
from pydantic import BaseModel
from app.models.article import Article


class DecisionResult(BaseModel):
    decision: str  # hidden | low_feed | feed | high_feed | push
    matched_topic: Optional[str] = None
    matched_entities: List[str] = []
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []
    # Structured contribution trace (Preference V2, issue #32):
    # [{step, scope, effect, detail}]. None on legacy-engine results.
    contributions: Optional[List[Dict]] = None


class ScoredArticle(BaseModel):
    article: Article
    decision: str
    matched_topic: Optional[str] = None
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []
    contributions: Optional[List[Dict]] = None
    # Which engine produced this trace (issue #35): "v2" | "legacy".
    engine: Optional[str] = None
