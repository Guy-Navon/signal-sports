import pathlib
import os


def _load_dotenv() -> None:
    """Load backend/.env if it exists.

    Must be called before any module that reads os.environ at import time
    (e.g. app.core.config).  The function is tolerant of python-dotenv not
    being installed, though it is listed in requirements.txt.

    override=False means already-set shell env vars take precedence over .env.
    """
    env_file = pathlib.Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:
        pass


_load_dotenv()

# ── All remaining imports come AFTER dotenv is loaded ─────────────────────────

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.csrf import CSRFMiddleware
from app.core.config import settings
from app.core.security_deps import validate_auth_startup_config
from app.api import (
    routes_auth,
    routes_health,
    routes_profiles,
    routes_articles,
    routes_feed,
    routes_feedback,
    routes_learning,
    routes_calibration,
    routes_ingest,
    routes_translation,
    routes_classify,
    routes_dev,
)


def _ensure_db_dir(database_url: str) -> None:
    """Create the parent directory of a relative SQLite file path if needed."""
    if database_url.startswith("sqlite:///./"):
        db_path = database_url[len("sqlite:///"):]
        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        from app.db.database import init_db, SessionLocal
        from app.repositories.seed_runner import seed_all_if_empty
        from app.services.auth_service import bootstrap_admin, ensure_users_for_profiles
        from app.ingestion.scheduler import scheduler_state, start_scheduler, stop_scheduler

        validate_auth_startup_config()
        _ensure_db_dir(settings.database_url)
        init_db()

        with SessionLocal() as session:
            seed_all_if_empty(session)
            ensure_users_for_profiles(session)
            bootstrap_admin(
                session,
                email=os.environ.get("AUTH_ADMIN_EMAIL"),
                password=os.environ.get("AUTH_ADMIN_PASSWORD"),
            )

        # Scheduled ingestion (PR 13) — disabled by default; returns None when
        # INGESTION_SCHEDULER_ENABLED != true, leaving behavior identical to before.
        scheduler_task = start_scheduler(scheduler_state)

        yield

        await stop_scheduler(scheduler_state, scheduler_task)

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Signal Sports backend — personalized sports news relevance API",
        lifespan=lifespan,
    )

    # Allow the Vite dev server (any localhost port) to call the API from a browser.
    # In production this should be restricted to the actual frontend domain.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(CSRFMiddleware)

    application.include_router(routes_health.router, tags=["health"])
    application.include_router(routes_auth.router, prefix="/api", tags=["auth"])
    application.include_router(routes_profiles.router, prefix="/api", tags=["profiles"])
    application.include_router(routes_articles.router, prefix="/api", tags=["articles"])
    application.include_router(routes_feed.router, prefix="/api", tags=["feed"])
    application.include_router(routes_feedback.router, prefix="/api", tags=["feedback"])
    application.include_router(routes_learning.router, prefix="/api", tags=["learning"])
    application.include_router(routes_calibration.router, prefix="/api", tags=["calibration"])
    application.include_router(routes_ingest.router, prefix="/api", tags=["ingest"])
    application.include_router(routes_translation.router, prefix="/api", tags=["translation"])
    application.include_router(routes_classify.router, prefix="/api", tags=["classify"])
    application.include_router(routes_dev.router, prefix="/api", tags=["dev"])

    return application


app = create_app()
