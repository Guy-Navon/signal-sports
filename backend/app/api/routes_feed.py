from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.scoring import ScoredArticle
from app.repositories import article_repository, profile_repository
from app.services.feed_service import build_feed

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
