from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.article import Article
from app.repositories import article_repository

router = APIRouter()


@router.get("/articles", response_model=List[Article])
def list_articles(session: Session = Depends(get_session)):
    return article_repository.get_rss_articles(session)


@router.get("/articles/{article_id}", response_model=Article)
def get_article(article_id: str, session: Session = Depends(get_session)):
    article = article_repository.get_by_id(session, article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")
    return article
