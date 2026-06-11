from fastapi import APIRouter, HTTPException
from typing import List
from app.db import db
from app.models.article import Article
from app.services.article_service import get_all_articles, get_article_by_id

router = APIRouter()


@router.get("/articles", response_model=List[Article])
def list_articles():
    return get_all_articles(db)


@router.get("/articles/{article_id}", response_model=Article)
def get_article(article_id: str):
    article = get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")
    return article
