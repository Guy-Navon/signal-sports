from fastapi import APIRouter, HTTPException
from typing import List
from app.db import db
from app.models.scoring import ScoredArticle
from app.services.profile_service import get_profile_by_id
from app.services.article_service import get_all_articles
from app.services.feed_service import build_feed

router = APIRouter()


@router.get("/feed/{user_id}", response_model=List[ScoredArticle])
def get_feed(user_id: str):
    profile = get_profile_by_id(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = get_all_articles(db)
    return build_feed(articles, profile, include_hidden=False)


@router.get("/debug/feed/{user_id}", response_model=List[ScoredArticle])
def get_debug_feed(user_id: str):
    profile = get_profile_by_id(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    articles = get_all_articles(db)
    return build_feed(articles, profile, include_hidden=True)
