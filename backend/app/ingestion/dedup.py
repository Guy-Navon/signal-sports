"""
URL-based deduplication.

Rules:
- Two articles with the same URL are considered duplicates.
- The article ID is a deterministic hash of the URL, so ID collision == URL collision.
- Fuzzy title dedup (near-duplicate clustering) is deferred to a future PR.

TODO: Add fuzzy title dedup after ingestion volume justifies it.
"""

import hashlib

from sqlalchemy.orm import Session

from app.db.orm_models import ArticleRow


def article_id_from_url(url: str) -> str:
    """Derive a stable, deterministic article ID from a URL."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return f"rss_{digest[:20]}"


def url_already_exists(session: Session, url: str) -> bool:
    """Return True if any article with this URL exists in the DB."""
    return session.query(ArticleRow).filter_by(url=url).first() is not None
