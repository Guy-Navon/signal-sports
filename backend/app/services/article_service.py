from typing import Optional, List
from app.models.article import Article


def get_all_articles(db) -> List[Article]:
    return list(db.articles.values())


def get_article_by_id(db, article_id: str) -> Optional[Article]:
    return db.articles.get(article_id)
