from sqlalchemy import Column, String, Text, Float, Boolean, JSON, Integer
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ArticleRow(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    source_display_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    original_title = Column(String, nullable=True)
    translated_title = Column(String, nullable=True)
    language = Column(String, nullable=False, default="he")
    # Stored as ISO-8601 string for reliable round-trip with timezone info
    published_at = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    league = Column(String, nullable=True)
    entities = Column(JSON, nullable=False)
    event_type = Column(String, nullable=False)
    importance = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=0.85)
    tags = Column(JSON, nullable=False)
    cluster_id = Column(String, nullable=True)
    # Subtitle/description from RSS feed — added via soft migration; nullable for existing rows
    subtitle = Column(Text, nullable=True)
    # LLM classification metadata — added via soft migration; nullable for existing rows
    classified_by = Column(String, nullable=True, default="rules")
    classification_provider = Column(String, nullable=True)
    classification_reason = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    # ArticleFacts (issue #28) — added via soft migration; nullable for existing rows
    primary_competition = Column(String, nullable=True)
    article_competitions = Column(JSON, nullable=True)
    entity_ids = Column(JSON, nullable=True)
    classification_trace = Column(JSON, nullable=True)
    taxonomy_version = Column(Integer, nullable=True)


class ProfileRow(Base):
    __tablename__ = "profiles"

    user_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    language = Column(String, nullable=False, default="he")
    profile_type = Column(String, nullable=False)
    # Topics stored as JSON list of dicts; avoids over-normalizing a deeply nested structure
    topics = Column(JSON, nullable=False)
    muted_topics = Column(JSON, nullable=False)
    muted_sources = Column(JSON, nullable=False)
    followed_entities = Column(JSON, nullable=False)


class SourceRow(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    language = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    trust_level = Column(String, nullable=False)


class SourceOverrideRow(Base):
    """Runtime enabled/disabled override for ingestion sources (PR 13.1).

    config.py holds the code default; a row here (set via
    PATCH /api/ingest/sources/{source_id}) wins over it and survives restarts.
    Distinct from the legacy `sources` demo table — keyed by ingestion
    source_id (e.g. "sport5_sport").
    """
    __tablename__ = "source_overrides"

    source_id = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False)


class FeedbackRow(Base):
    __tablename__ = "feedback_events"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    article_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    # Stored as ISO-8601 string
    created_at = Column(String, nullable=False)


class CalibrationHeadlineRow(Base):
    __tablename__ = "calibration_headlines"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    league = Column(String, nullable=True)
    entities = Column(JSON, nullable=False)
    event_type = Column(String, nullable=False)
    importance = Column(String, nullable=False)
    tags = Column(JSON, nullable=False)


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    # Stored as ISO-8601 strings (same pattern as other datetime fields)
    started_at = Column(String, nullable=False)
    finished_at = Column(String, nullable=True)
    status = Column(String, nullable=False)           # ok | error
    fetched_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    skipped_duplicate_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(String, nullable=True)
