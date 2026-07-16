from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SourceIngestResult(BaseModel):
    source_id: str
    fetched: int
    inserted: int
    skipped_filtered: int = 0   # items dropped by source-level URL/language filters
    skipped_duplicate: int
    failed: int
    errors: List[str] = Field(default_factory=list)
    # Timing fields (live response only — not persisted to DB)
    fetch_ms: Optional[float] = None
    total_ms: Optional[float] = None
    llm_attempts: int = 0
    llm_successes: int = 0
    llm_fallback_connect_error: int = 0
    llm_fallback_timeout_or_parse: int = 0
    llm_fallback_low_confidence: int = 0
    llm_avg_ms: Optional[float] = None
    llm_p95_ms: Optional[float] = None
    # Gating fields: how many eligible articles were skipped by the gate and why.
    # "Eligible" means Hebrew broad source + provider active + circuit not open.
    # These are live response only — not persisted to DB.
    llm_skipped: int = 0
    llm_skip_reasons: Dict[str, int] = Field(default_factory=dict)
    llm_call_reasons: Dict[str, int] = Field(default_factory=dict)
    # Per-run LLM dependency / quality metrics (issue #31) — also persisted on
    # the ingestion_runs row. Computed only in the normal gated ingestion path.
    metrics: Optional[Dict] = None
    # Story-clustering stage (issue #101). Live response only — NOT persisted, matching
    # the skipped_filtered precedent (no DB migration). Deliberately separate counters:
    # clustering must never be conflated with URL dedup, which is a different mechanism.
    clustering_ran: bool = False
    clusters_created: int = 0
    articles_appended_to_clusters: int = 0
    articles_left_unclustered: int = 0
    clusters_removed: int = 0
    clustering_failed: bool = False
    clustering_error: Optional[str] = None


class IngestRunResponse(BaseModel):
    status: str
    sources: List[SourceIngestResult]


class IngestSourceInfo(BaseModel):
    source_id: str
    display_name: str
    type: str = "rss"           # "rss" | "html_scrape"
    enabled: bool
    feed_url: str
    language: str = "en"
    is_pilot: bool = False      # experimental scraping pilot (PR 13)


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
    # LLM dependency / quality metrics (issue #31). None on rows that predate
    # the metrics column — old runs stay readable unchanged.
    metrics: Optional[Dict] = None


class SchedulerStatusResponse(BaseModel):
    """Live scheduler + ingestion-lock state (PR 13; M7-4 durable rewrite).

    Three distinct signals — ``enabled`` is the SCHEDULER_ENABLED config INTENT
    as seen by the API process (NOT proof of ticking; false during the
    controlled soak); ``worker_running``/``automatic_ingestion_active`` are the
    durable runtime truth from the dedicated worker's heartbeat. UIs must show
    ``automatic_ingestion_active`` as the headline, never ``enabled``.
    """
    enabled: bool                                   # config intent (API process env)
    running: bool                                   # legacy: worker state != stopped (not freshness-checked)
    worker_running: bool = False                    # dedicated worker alive + fresh heartbeat
    automatic_ingestion_active: bool = False        # the true "auto ingestion is happening" signal
    interval_minutes: int
    next_run_at: Optional[datetime] = None
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    last_status: str = "never_run"                  # ok | error | skipped | never_run
    last_error: Optional[str] = None
    active_run: Optional[Dict[str, str]] = None     # {"trigger", "started_at"}
    last_result_summary: Optional[List[Dict[str, object]]] = None


class RunNowResponse(BaseModel):
    """POST /api/ingest/scheduler/run-now result (PR 13)."""
    trigger: str = "run_now"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str                                     # ok | error
    sources: List[Dict[str, object]] = Field(default_factory=list)


class SourceHealthInfo(BaseModel):
    """Per-source ingestion health, computed on request from ingestion_runs (PR 13)."""
    source_id: str
    display_name: str
    enabled: bool
    source_type: str = "rss"
    is_pilot: bool = False
    freshness: str                                  # healthy | stale | never_run | disabled | error
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None               # ok | error
    last_fetched_count: Optional[int] = None
    last_inserted_count: Optional[int] = None
    last_failed_count: Optional[int] = None
    last_skipped_duplicate_count: Optional[int] = None
    consecutive_failures: int = 0
    last_error_message: Optional[str] = None


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
    # LLM dependency trend (issue #31): recent ingestion runs, newest first,
    # each carrying its persisted per-run metrics dict (None for runs that
    # predate the metrics column). Normal gated ingestion runs only — the
    # forced classification backfill never writes run records by design.
    llm_dependency_runs: List[IngestionRunRecord] = Field(default_factory=list)
