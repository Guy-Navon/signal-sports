from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_health, routes_profiles, routes_articles, routes_feed, routes_feedback, routes_calibration
from app.db import db
from app.seed.seed_articles import seed_articles
from app.seed.seed_profiles import seed_profiles
from app.seed.seed_sources import seed_sources
from app.seed.seed_calibration import seed_calibration_headlines


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        seed_profiles(db)
        seed_articles(db)
        seed_sources(db)
        seed_calibration_headlines(db)
        yield

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Signal Sports backend — personalized sports news relevance API",
        lifespan=lifespan,
    )

    application.include_router(routes_health.router, tags=["health"])
    application.include_router(routes_profiles.router, prefix="/api", tags=["profiles"])
    application.include_router(routes_articles.router, prefix="/api", tags=["articles"])
    application.include_router(routes_feed.router, prefix="/api", tags=["feed"])
    application.include_router(routes_feedback.router, prefix="/api", tags=["feedback"])
    application.include_router(routes_calibration.router, prefix="/api", tags=["calibration"])

    return application


app = create_app()
