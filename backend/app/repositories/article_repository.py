from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import ArticleRow, ProtectedArticleRow
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
        published_at_meta=row.published_at_meta,
        sport=row.sport,
        league=row.league,
        entities=row.entities or [],
        event_type=row.event_type,
        event_certainty=row.event_certainty or "confirmed",
        importance=row.importance,
        confidence=row.confidence,
        tags=row.tags or [],
        cluster_id=row.cluster_id,
        subtitle=row.subtitle,
        classified_by=row.classified_by or "rules",
        classification_provider=row.classification_provider,
        classification_reason=row.classification_reason,
        classification_confidence=row.classification_confidence,
        primary_competition=row.primary_competition,
        article_competitions=row.article_competitions or [],
        entity_ids=row.entity_ids or [],
        classification_trace=row.classification_trace,
        taxonomy_version=row.taxonomy_version,
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
        published_at_meta=article.published_at_meta,
        sport=article.sport,
        league=article.league,
        entities=list(article.entities),
        event_type=article.event_type,
        event_certainty=article.event_certainty,
        importance=article.importance,
        confidence=article.confidence,
        tags=list(article.tags),
        cluster_id=article.cluster_id,
        subtitle=article.subtitle,
        classified_by=article.classified_by,
        classification_provider=article.classification_provider,
        classification_reason=article.classification_reason,
        classification_confidence=article.classification_confidence,
        primary_competition=article.primary_competition,
        article_competitions=list(article.article_competitions),
        entity_ids=list(article.entity_ids),
        classification_trace=article.classification_trace,
        taxonomy_version=article.taxonomy_version,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_all(session: Session) -> List[Article]:
    rows = session.execute(select(ArticleRow)).scalars().all()
    return [_row_to_article(r) for r in rows]


def get_by_id(session: Session, article_id: str) -> Optional[Article]:
    row = session.get(ArticleRow, article_id)
    return _row_to_article(row) if row else None


def get_rss_articles(session: Session, *, published_at_floor: Optional[str] = None) -> List[Article]:
    """Return all articles ingested via RSS (id prefix 'rss_').

    ``published_at_floor``, when given, keeps rows whose stored ``published_at``
    text sorts at or above it. It is a text comparison, not a time one: see
    ``freshness.published_at_query_floor``, the only intended source of a floor.
    """
    query = session.query(ArticleRow).filter(ArticleRow.id.startswith("rss_", autoescape=True))
    if published_at_floor is not None:
        query = query.filter(ArticleRow.published_at >= published_at_floor)
    return [_row_to_article(r) for r in query.all()]


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
    event_certainty: str = "confirmed",
) -> None:
    row = session.get(ArticleRow, article_id)
    if row is None:
        return
    row.sport = sport
    row.league = league
    row.entities = entities
    row.event_type = event_type
    row.event_certainty = event_certainty
    row.importance = importance
    row.confidence = confidence
    row.tags = tags
    session.commit()


def update_full_classification(
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
    classified_by: str,
    classification_provider: Optional[str],
    classification_reason: Optional[str],
    classification_confidence: Optional[float],
    event_certainty: str = "confirmed",
    primary_competition: Optional[str] = None,
    article_competitions: Optional[List[str]] = None,
    entity_ids: Optional[List[str]] = None,
    classification_trace: Optional[dict] = None,
    taxonomy_version: Optional[int] = None,
) -> None:
    """Update all classification fields including LLM metadata and ArticleFacts. Used by backfill."""
    row = session.get(ArticleRow, article_id)
    if row is None:
        return
    row.sport = sport
    row.league = league
    row.entities = entities
    row.event_type = event_type
    row.event_certainty = event_certainty
    row.importance = importance
    row.confidence = confidence
    row.tags = tags
    row.classified_by = classified_by
    row.classification_provider = classification_provider
    row.classification_reason = classification_reason
    row.classification_confidence = classification_confidence
    row.primary_competition = primary_competition
    row.article_competitions = list(article_competitions or [])
    row.entity_ids = list(entity_ids or [])
    row.classification_trace = classification_trace
    row.taxonomy_version = taxonomy_version
    session.commit()


def is_protected(session: Session, article_id: str) -> bool:
    """True when the row is human-rated ground truth (#255) and must never change."""
    return session.get(ProtectedArticleRow, article_id) is not None


def refresh_from_source(
    session: Session,
    article_id: str,
    article: Article,
    *,
    reason: str,
    refreshed_at: Optional[datetime] = None,
) -> bool:
    """Overwrite a stored row with a fresh normalisation of the same URL (#579).

    Used when a source rewrote a live blog into the final report at the same URL.
    Keeps id, url and source (the row's identity, which ratings and clusters point
    at). Replaces the title fields and every classification/facts field, the same
    set ``update_full_classification`` writes. ``published_at`` moves forward only,
    so the final report sorts by its real time but a source clock never drags a row
    back. Story anchors are cleared so the anchor stage recomputes them for the new
    title. The previous title, event type and time are kept in
    ``classification_trace["refreshed_from"]``. One commit.

    Returns False when the row no longer exists.
    """
    row = session.get(ArticleRow, article_id)
    if row is None:
        return False
    now = refreshed_at or datetime.now(tz=timezone.utc)
    previous = {
        "previous_title": row.original_title or row.title,
        "previous_event_type": row.event_type,
        "previous_published_at": row.published_at,
        "refreshed_at": now.isoformat(),
        "reason": reason,
    }

    row.title = article.title
    row.original_title = article.original_title
    row.translated_title = article.translated_title
    row.language = article.language
    row.subtitle = article.subtitle

    stored_published = datetime.fromisoformat(row.published_at)
    if stored_published.tzinfo is None:
        stored_published = stored_published.replace(tzinfo=timezone.utc)
    if article.published_at > stored_published:
        row.published_at = article.published_at.isoformat()
        row.published_at_meta = article.published_at_meta

    row.sport = article.sport
    row.league = article.league
    row.entities = list(article.entities)
    row.event_type = article.event_type
    row.event_certainty = article.event_certainty
    row.importance = article.importance
    row.confidence = article.confidence
    row.tags = list(article.tags)
    row.classified_by = article.classified_by
    row.classification_provider = article.classification_provider
    row.classification_reason = article.classification_reason
    row.classification_confidence = article.classification_confidence
    row.primary_competition = article.primary_competition
    row.article_competitions = list(article.article_competitions)
    row.entity_ids = list(article.entity_ids)
    row.taxonomy_version = article.taxonomy_version
    trace = dict(article.classification_trace or {})
    trace["refreshed_from"] = previous
    row.classification_trace = trace

    row.story_anchors = None
    row.anchor_validator_version = None
    session.commit()
    return True


def get_articles_for_classification_backfill(
    session: Session,
    *,
    source_ids: List[str],
    force: bool = False,
    limit: Optional[int] = None,
) -> List[Article]:
    """Return RSS articles from the given sources that are eligible for LLM reclassification.

    When force=False: only returns articles where classified_by is NOT already 'llm'
    or 'llm+rules_guardrail' (i.e., articles not yet successfully classified by LLM).
    When force=True: returns all articles from the given sources regardless of classified_by.
    """
    _already_llm = {"llm", "llm+rules_guardrail"}
    query = (
        session.query(ArticleRow)
        .filter(ArticleRow.id.startswith("rss_", autoescape=True))
        .filter(ArticleRow.source.in_(source_ids))
    )
    if not force:
        query = query.filter(
            ~ArticleRow.classified_by.in_(list(_already_llm))
        )
    if limit:
        query = query.limit(limit)
    return [_row_to_article(r) for r in query.all()]
