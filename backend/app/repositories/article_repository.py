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


def get_by_url(session: Session, url: str) -> Optional[Article]:
    row = session.query(ArticleRow).filter_by(url=url).first()
    return _row_to_article(row) if row else None


def get_rss_articles(session: Session) -> List[Article]:
    """Return all articles ingested via RSS (id prefix 'rss_')."""
    rows = session.query(ArticleRow).filter(ArticleRow.id.like("rss_%")).all()
    return [_row_to_article(r) for r in rows]


def count(session: Session) -> int:
    return session.query(ArticleRow).count()


def insert(session: Session, article: Article) -> None:
    session.add(_article_to_row(article))
    session.commit()


def update_translation_fields(
    session: Session,
    article_id: str,
    *,
    title: str,
    original_title: Optional[str],
    translated_title: Optional[str],
    language: str,
) -> None:
    row = session.get(ArticleRow, article_id)
    if row is None:
        return
    row.title = title
    row.original_title = original_title
    row.translated_title = translated_title
    row.language = language
    session.commit()


def update_classification_fields(
    session: Session,
    article_id: str,
    *,
    sport: str,
    league: Optional[str],
    entities: List[str],
    event_type: str,
    importance: str,
    confidence: float,
    tags: List[str],
) -> None:
    row = session.get(ArticleRow, article_id)
    if row is None:
        return
    row.sport = sport
    row.league = league
    row.entities = entities
    row.event_type = event_type
    row.importance = importance
    row.confidence = confidence
    row.tags = tags
    session.commit()


def get_untranslated_rss_articles(
    session: Session,
    *,
    limit: Optional[int] = None,
    source_id: Optional[str] = None,
) -> List[Article]:
    """Return RSS articles that need translation.

    Candidates: language != 'he' AND translated_title IS NULL.
    """
    query = (
        session.query(ArticleRow)
        .filter(ArticleRow.id.like("rss_%"))
        .filter(ArticleRow.language != "he")
        .filter(ArticleRow.translated_title.is_(None))
    )
    if source_id:
        query = query.filter(ArticleRow.source == source_id)
    if limit:
        query = query.limit(limit)
    return [_row_to_article(r) for r in query.all()]
