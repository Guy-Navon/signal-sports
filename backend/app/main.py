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
from dataclasses import dataclass, field
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.csrf import CSRFMiddleware
from app.core.config import settings
from app.core.security_deps import require_admin, validate_auth_startup_config
from app.api import (
    routes_auth,
    routes_me,
    routes_health,
    routes_profiles,
    routes_articles,
    routes_feed,
    routes_results,
    routes_feedback,
    routes_learning,
    routes_calibration,
    routes_taxonomy,
    routes_ingest,
    routes_scheduler,
    routes_translation,
    routes_classify,
    routes_dev,
)


@dataclass(frozen=True)
class RouterInclude:
    """One ``include_router`` call, recorded so it can be inspected publicly.

    ``create_app`` registers routers ONLY through ``router_includes()``, and
    stores the list on ``app.state.router_includes``. The authorization
    inventory (tests/test_authz_inventory.py) walks this registry instead of
    FastAPI's internal route table, whose shape changed in FastAPI 0.141
    (audit L9). The test cross-checks the registry against the app's OpenAPI
    schema, so a router registered any other way fails the suite.
    """

    router: APIRouter
    prefix: str = ""
    tags: tuple[str, ...] = ()
    dependencies: tuple = field(default_factory=tuple)


def router_includes() -> list[RouterInclude]:
    # Results (issue #178): per-route auth like the feed router — the read
    # routes self-gate (require_admin / require_user via /me), the sync route
    # is admin-only. Registered without a router-level dependency.
    #
    # Ops surface (User Platform PR 5, #53): admin-gated at the router level,
    # fail-closed by default; ALLOW_INSECURE_AUTH_BYPASS restores the open
    # behavior for local development. /api/dev/* keeps its ALLOW_DEV_RESET env
    # gate INSIDE the routes — a deliberate double gate.
    admin = (Depends(require_admin),)
    return [
        RouterInclude(routes_health.router, tags=("health",)),
        RouterInclude(routes_auth.router, "/api", ("auth",)),
        RouterInclude(routes_me.router, "/api", ("me",)),
        RouterInclude(routes_profiles.router, "/api", ("profiles",)),
        RouterInclude(routes_articles.router, "/api", ("articles",)),
        RouterInclude(routes_feed.router, "/api", ("feed",)),
        RouterInclude(routes_results.router, "/api", ("results",)),
        RouterInclude(routes_feedback.router, "/api", ("feedback",)),
        RouterInclude(routes_learning.router, "/api", ("learning",)),
        RouterInclude(routes_calibration.router, "/api", ("calibration",)),
        RouterInclude(routes_taxonomy.router, "/api", ("taxonomy",)),
        RouterInclude(routes_ingest.router, "/api", ("ingest",), admin),
        RouterInclude(routes_scheduler.router, "/api", ("scheduler",), admin),
        RouterInclude(routes_translation.router, "/api", ("translation",), admin),
        RouterInclude(routes_classify.router, "/api", ("classify",), admin),
        RouterInclude(routes_dev.router, "/api", ("dev",), admin),
    ]


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

        from app.core.deploy_mode import validate_deploy_startup_config

        validate_deploy_startup_config()
        validate_auth_startup_config()
        from app.results.providers import configured_disabled, configured_routes
        configured_routes()  # RESULTS_PROVIDER_ROUTES typo: fail at startup (#529)
        configured_disabled()  # RESULTS_PROVIDER_DISABLED typo: fail at startup (#522)
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

        # NO scheduler here — deliberately (M7-2, #148). The in-process lifespan
        # scheduler (PR 13) was retired because its lifetime was coupled to
        # request-serving reloads: `uvicorn --reload` and every extra worker
        # would each start their own polling loop. Scheduled ingestion lives in
        # the DEDICATED worker process (`python -m app.worker`), which shares
        # the durable single-flight lease (M7-1) with the manual API triggers.
        # A second polling loop is now impossible by construction.

        yield

    # Verification tokens never belong in access logs (app/core/log_redaction.py).
    from app.core.log_redaction import install_access_log_redaction

    install_access_log_redaction()

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Signal Sports backend — personalized sports news relevance API",
        lifespan=lifespan,
    )

    # CORS and CSRF share one origin list (CSRF_ALLOWED_ORIGINS, N07 / #196):
    # an origin allowed to mutate must also be allowed to read the response.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.csrf_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(CSRFMiddleware)

    includes = router_includes()
    for inc in includes:
        application.include_router(
            inc.router,
            prefix=inc.prefix,
            tags=list(inc.tags),
            dependencies=list(inc.dependencies),
        )
    application.state.router_includes = tuple(includes)

    return application


app = create_app()
