import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.orm_models import Base

# Read DATABASE_URL at import time so tests can set it via os.environ before importing.
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they do not exist. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """FastAPI dependency: yields a SQLAlchemy session, closes on exit."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
