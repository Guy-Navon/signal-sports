from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class Article(BaseModel):
    id: str
    source: str
    source_display_name: str
    url: str
    title: str
    original_title: Optional[str] = None
    translated_title: Optional[str] = None
    language: str = "he"
    published_at: datetime
    sport: str
    league: Optional[str] = None
    entities: List[str] = []
    event_type: str
    importance: str  # very_low | low | medium | high | very_high
    confidence: float = 0.85
    tags: List[str] = []
    cluster_id: Optional[str] = None
    subtitle: Optional[str] = None
    # LLM classification metadata
    classified_by: str = "rules"
    classification_provider: Optional[str] = None
    classification_reason: Optional[str] = None
    classification_confidence: Optional[float] = None
    # ArticleFacts (issue #28) — evidence-backed competitions, canonical entity IDs,
    # and a compact classification trace. Legacy `league`/`entities` stay populated;
    # `league` == display_en of `primary_competition` when a primary is set.
    primary_competition: Optional[str] = None       # competition id (comp:*), explicit evidence only
    article_competitions: List[str] = []             # additional explicitly-evidenced competition ids
    entity_ids: List[str] = []                       # canonical taxonomy ids (team:* / player:* / coach:*)
    classification_trace: Optional[dict] = None      # evidence hits, gate/LLM decision, conflicts, normalization
    taxonomy_version: Optional[int] = None           # taxonomy registry version that produced these facts
