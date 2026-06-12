from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ArticleRow
from app.models.article import Article


# ── Conversion helpers ────────────────────────────────────────────────────────

def _row_to_article(row: ArticleRow) -> Article:
    published = datetime.fromisoformat(row.published_at)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return Article(
        id=row.id,
        source=row.source,
        source_display_name=row.source_display_name,
        url=row.url,
        title=row.title,
        original_title=row.original_title,
        translated_title=row.translated_title,
        language=row.language,
        published_at=published,
        sport=row.sport,
        league=row.league,
        entities=row.entities or [],
        event_type=row.event_type,
        importance=row.importance,
        confidence=row.confidence,
        tags=row.tags or [],
        cluster_id=row.cluster_id,
    )


def _article_to_row(article: Article) -> ArticleRow:
    return ArticleRow(
        id=article.id,
        source=article.source,
        source_display_name=article.source_display_name,
        url=article.url,
        title=article.title,
        original_title=article.original_title,
        translated_title=article.translated_title,
        language=article.language,
        published_at=article.published_at.isoformat(),
        sport=article.sport,
        league=article.league,
        entities=list(article.entities),
        event_type=article.event_type,
        importance=article.importance,
        confidence=article.confidence,
        tags=list(article.tags),
        cluster_id=article.cluster_id,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_all(session: Session) -> List[Article]:
    rows = session.execute(select(ArticleRow)).scalars().all()
    return [_row_to_article(r) for r in rows]


def get_by_id(session: Session, article_id: str) -> Optional[Article]:
    row = session.get(ArticleRow, article_id)
    return _row_to_article(row) if row else None


def count(session: Session) -> int:
    return session.query(ArticleRow).count()


def insert(session: Session, article: Article) -> None:
    session.add(_article_to_row(article))
    session.commit()
