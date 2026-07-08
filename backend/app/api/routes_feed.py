from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.scoring import ScoredArticle
from app.repositories import article_repository, profile_repository
from app.services.feed_service import active_engine, build_feed
from app.services.shadow_service import ShadowReport, build_shadow_report

router = APIRouter()


@router.get("/feed/{user_id}", response_model=List[ScoredArticle])
def get_feed(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = article_repository.get_rss_articles(session)
    return build_feed(articles, profile, include_hidden=False)


@router.get("/debug/feed/{user_id}", response_model=List[ScoredArticle])
def get_debug_feed(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = article_repository.get_rss_articles(session)
    return build_feed(articles, profile, include_hidden=True)


@router.get("/debug/shadow/{user_id}", response_model=ShadowReport)
def get_shadow_report(user_id: str, session: Session = Depends(get_session)):
    """Shadow-mode comparison (issue #32): every article scored by BOTH the
    legacy topic engine and the Preference V2 affinity scorer; returns the
    agreement summary plus per-article traces for each disagreement."""
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    if profile.profile_v2 is None:
        raise HTTPException(
            status_code=409,
            detail=f"Profile '{user_id}' has no profile_v2 — nothing to shadow-compare",
        )
    articles = article_repository.get_rss_articles(session)
    return build_shadow_report(articles, profile)


@router.get("/feed-engine")
def get_feed_engine():
    """Which preference engine currently serves GET /api/feed (issue #32)."""
    return {"engine": active_engine()}
