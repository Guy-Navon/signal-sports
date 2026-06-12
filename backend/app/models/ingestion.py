from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class SourceIngestResult(BaseModel):
    source_id: str
    fetched: int
    inserted: int
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
