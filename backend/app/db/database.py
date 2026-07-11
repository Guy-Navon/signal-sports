import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from app.db.orm_models import Base

# Read DATABASE_URL at import time so tests can set it via os.environ before importing.
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _apply_migrations(eng) -> None:
    """Add new nullable columns to existing tables without recreating them."""
    migrations = [
        ("articles", "subtitle",                  "TEXT"),
        ("articles", "classified_by",            "TEXT DEFAULT 'rules'"),
        ("articles", "classification_provider",   "TEXT"),
        ("articles", "classification_reason",     "TEXT"),
        ("articles", "classification_confidence", "REAL"),
        ("articles", "event_certainty",           "TEXT DEFAULT 'confirmed'"),
        # ArticleFacts (issue #28) — same soft-migration pattern as PR 11.
        ("articles", "primary_competition",       "TEXT"),
        ("articles", "article_competitions",      "JSON"),
        ("articles", "entity_ids",                "JSON"),
        ("articles", "classification_trace",      "JSON"),
        ("articles", "taxonomy_version",          "INTEGER"),
        # LLM dependency metrics (issue #31) — same soft-migration pattern.
        ("ingestion_runs", "metrics",             "JSON"),
        # ProfileV2 affinity model (issue #32).
        ("profiles", "profile_v2",                "JSON"),
        # Feedback learning (issue #34).
        ("feedback_events", "context",            "JSON"),
        ("feedback_events", "retracted",          "INTEGER DEFAULT 0"),
        # Explicit interests stage (issue #77).
        ("users", "interests_completed_at",       "TEXT"),
    ]
    with eng.connect() as conn:
        for table, col, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore


def init_db() -> None:
    """Create all tables if they do not exist, then apply soft migrations."""
    Base.metadata.create_all(bind=engine)
    _apply_migrations(engine)


def get_session():
    """FastAPI dependency: yields a SQLAlchemy session, closes on exit."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
