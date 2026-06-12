from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel


class SourceIngestResult(BaseModel):
    source_id: str
    fetched: int
    inserted: int
    skipped_filtered: int = 0   # items dropped by source-level URL/language filters
    skipped_duplicate: int
    failed: int
    errors: List[str] = []


class IngestRunResponse(BaseModel):
    status: str
    sources: List[SourceIngestResult]


class IngestSourceInfo(BaseModel):
    source_id: str
    display_name: str
    type: str = "rss"
    enabled: bool
    feed_url: str
    language: str = "en"


class IngestionRunRecord(BaseModel):
    id: str
    source_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str                       # ok | error
    fetched_count: int
    inserted_count: int
    skipped_duplicate_count: int
    failed_count: int
    error_message: Optional[str] = None


class QuestionableArticle(BaseModel):
    id: str
    title: str
    source: str
    sport: str
    league: Optional[str] = None
    event_type: str
    importance: str
    confidence: float
    reasons: List[str]


class IngestQualityResponse(BaseModel):
    total_rss_articles: int
    sport_breakdown: Dict[str, int]
    league_breakdown: Dict[str, int]
    event_type_breakdown: Dict[str, int]
    importance_breakdown: Dict[str, int]
    low_confidence_count: int
    questionable_articles: List[QuestionableArticle]
