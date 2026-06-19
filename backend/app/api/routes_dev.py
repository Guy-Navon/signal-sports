"""
Development-only endpoints. All routes are guarded by ALLOW_DEV_RESET=true.
Set ALLOW_DEV_RESET=true in backend/.env to enable.

Do NOT enable in production. These endpoints are intentionally destructive.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.db.orm_models import ArticleRow, IngestionRunRow

logger = logging.getLogger(__name__)

router = APIRouter()


def _dev_reset_enabled() -> bool:
    return os.environ.get("ALLOW_DEV_RESET", "false").lower() == "true"


class ResetRssDataResult(BaseModel):
    status: str
    deleted_articles: int
    deleted_ingestion_runs: int


@router.post("/dev/reset-rss-data", response_model=ResetRssDataResult)
def reset_rss_data(session: Session = Depends(get_session)) -> ResetRssDataResult:
    """Delete all RSS articles (id starts with rss_) and all ingestion run logs.

    Keeps profiles, sources, calibration headlines, feedback events,
    and non-RSS seed articles (id starts with article_).

    Guarded by ALLOW_DEV_RESET=true — returns 403 otherwise.
    """
    if not _dev_reset_enabled():
        raise HTTPException(
            status_code=403,
            detail="Dev reset is disabled. Set ALLOW_DEV_RESET=true in backend/.env to enable.",
        )

    deleted_articles = (
        session.query(ArticleRow)
        .filter(ArticleRow.id.like("rss_%"))
        .delete(synchronize_session=False)
    )

    deleted_runs = session.query(IngestionRunRow).delete(synchronize_session=False)

    session.commit()

    logger.warning(
        "Dev reset executed: deleted %d RSS articles, %d ingestion runs",
        deleted_articles,
        deleted_runs,
    )

    return ResetRssDataResult(
        status="ok",
        deleted_articles=deleted_articles,
        deleted_ingestion_runs=deleted_runs,
    )
