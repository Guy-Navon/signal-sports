"""
Feed freshness contract (Milestone 8, #171) — THE shared predicate.

The consumer feed is a CURRENT sports-news feed: articles whose normalized
publication time is older than the freshness window must not appear in ranked
feeds and must not become PUSH notifications. This module is the single
implementation of that cutoff. Nothing else — not the feed route, not the
cluster collapse, not the Telegram planner — reimplements an age rule; they
all flow through ``build_feed``, which calls :func:`fresh_only` exactly once.

Clock semantics (docs/FEED_FRESHNESS.md):
  - the clock is the article's normalized ``published_at`` (source publication
    time, UTC), never fetch/ingest time — a late-discovered old article must
    not look new because Signal fetched it recently. Where the source gave no
    timestamp, ``published_at`` already holds the bounded ingest-time fallback
    (fixed at insert, so it ages out normally; provenance recorded in
    ``published_at_meta`` since M8-4, #174);
  - naive datetimes are treated as UTC (matches the repository convention);
  - an article exactly at the cutoff is FRESH (``>= cutoff``);
  - a future-dated article is fresh — ingestion clamps timestamps more than
    :data:`FUTURE_TOLERANCE_MINUTES` ahead (M8-4), so nothing can ride the
    top of the feed indefinitely.

Visibility policy, not deletion: expired articles stay in the database under
the separate ~30-day physical-retention contract (retention.py, M7-3) and
remain visible in the Debug feed, which deliberately shows everything.

ACTIVATION (M8-5, #175): ``FEED_FRESHNESS_ENABLED`` is the guarded production
flip, same pattern as CLUSTERING_ENABLED — code default false so merging the
capability changes nothing until the activation gate flips the production
.env. Rollback is flipping it back; no data is touched either way.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

DEFAULT_FEED_MAX_AGE_HOURS = 36

# Publication timestamps this far ahead of ingest time are clamped at
# ingestion (M8-4). Deliberately a constant, not an env knob: it covers clock
# skew and scheduled-publish quirks (the one live case was +40 min), and a
# per-deployment value would just be config sprawl.
FUTURE_TOLERANCE_MINUTES = 15


def freshness_enabled() -> bool:
    """The M8-5 activation flag. False (code default) = no age filtering,
    byte-identical pre-M8 behavior."""
    return os.getenv("FEED_FRESHNESS_ENABLED", "false").strip().lower() == "true"


def feed_max_age_hours() -> int:
    """The freshness window in hours. Guarded parse: non-numeric or < 1 falls
    back to the documented default rather than silently hiding the feed."""
    raw = os.getenv("FEED_MAX_AGE_HOURS", str(DEFAULT_FEED_MAX_AGE_HOURS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_FEED_MAX_AGE_HOURS
    return value if value >= 1 else DEFAULT_FEED_MAX_AGE_HOURS


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def freshness_cutoff(now: Optional[datetime] = None) -> datetime:
    """Oldest still-fresh publication instant: now − FEED_MAX_AGE_HOURS."""
    now = _as_utc(now) if now is not None else datetime.now(tz=timezone.utc)
    return now - timedelta(hours=feed_max_age_hours())


def is_fresh(published_at: datetime, now: Optional[datetime] = None) -> bool:
    """THE freshness predicate. True when the article's normalized publication
    time is inside the window (or freshness is not enabled)."""
    if not freshness_enabled():
        return True
    return _as_utc(published_at) >= freshness_cutoff(now)


def fresh_only(articles: Iterable, now: Optional[datetime] = None) -> List:
    """Filter to in-window articles. One ``now`` for the whole batch so a
    single feed build cannot straddle the cutoff mid-list."""
    if not freshness_enabled():
        return list(articles)
    cutoff = freshness_cutoff(now)
    return [a for a in articles if _as_utc(a.published_at) >= cutoff]
