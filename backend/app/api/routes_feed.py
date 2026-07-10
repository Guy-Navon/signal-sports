from fastapi import APIRouter, Depends, HTTPException
from app.core.security_deps import require_admin, require_session
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.scoring import ScoredArticle
from app.repositories import article_repository, feedback_repository, profile_repository
from app.services.feed_service import active_engine, build_feed
from app.services.learning_service import dismissed_article_ids, with_learned
from app.services.shadow_service import ShadowReport, build_shadow_report

router = APIRouter()


@router.get("/feed/{user_id}", response_model=List[ScoredArticle], dependencies=[Depends(require_admin)])
def get_feed(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = article_repository.get_rss_articles(session)
    # Feedback learning (issue #34): score with derived learned entries and
    # drop articles the user explicitly dismissed (feed only — debug shows all).
    events = feedback_repository.get_active_by_user(session, user_id)
    dismissed = dismissed_article_ids(events)
    articles = [a for a in articles if a.id not in dismissed]
    return build_feed(articles, with_learned(profile, events), include_hidden=False)


@router.get("/debug/feed/{user_id}", response_model=List[ScoredArticle], dependencies=[Depends(require_admin)])
def get_debug_feed(user_id: str, session: Session = Depends(get_session)):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = article_repository.get_rss_articles(session)
    events = feedback_repository.get_active_by_user(session, user_id)
    return build_feed(articles, with_learned(profile, events), include_hidden=True)


@router.get("/debug/shadow/{user_id}", response_model=ShadowReport, dependencies=[Depends(require_admin)])
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


@router.get("/feed-engine", dependencies=[Depends(require_session)])
def get_feed_engine():
    """Which preference engine currently serves GET /api/feed (issue #32)."""
    return {"engine": active_engine()}
