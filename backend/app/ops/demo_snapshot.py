"""Static snapshot of one profile's consumer feed for the public demo (#458).

The demo on Firebase Hosting serves only static files. This module builds the
feed of the demo profile through the SAME handler GET /api/me/feed delegates to
(``routes_feed.get_feed``: candidates, dismissed filter, learned entries,
``build_feed(include_hidden=False)`` with cluster collapse), then keeps only the
fields the Orbit feed renders.

Safety properties (locked by tests/test_demo_snapshot_458.py):
- The database is opened read-only (``mode=ro`` URI, ``PRAGMA query_only``) on
  its own engine, inside one read transaction, so the snapshot is consistent
  while the worker keeps writing and no code path can write.
- No usage is recorded (``record_feed_view`` belongs to the /me route, not here).
- Output fields are an explicit allowlist: no engine trace, no classification
  internals, no user, account or email data.
- Both files are written to temp files first and only then renamed into place;
  any failure leaves the previous snapshot untouched.

The engine and clustering settings come from the process environment, exactly
as in the API process; scripts/export_demo_snapshot.py loads backend/.env the
same way app.main does before importing this module.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.api.routes_feed import get_feed
from app.ingestion.orchestration import last_successful_cycle
from app.repositories import profile_repository

SCHEMA_VERSION = 1
DEMO_USER_ID = "guy"
FEED_FILE = "feed.json"
META_FILE = "meta.json"

# What the Orbit feed reads (src/components/feed + api/normalizers.js), in the
# backend's snake_case wire shape so the demo reuses normalizeScoredArticleFromApi.
# An allowlist on purpose: a field added to the models later stays out of the
# public file until someone decides it belongs there.
ARTICLE_FIELDS = (
    "id", "source", "source_display_name", "url", "title", "original_title",
    "translated_title", "language", "published_at", "sport", "league", "entities",
    "event_type", "importance", "tags", "cluster_id", "subtitle",
)
SCORED_FIELDS = ("decision", "reason_he")
CLUSTER_FIELDS = (
    "cluster_id", "decision", "representative_article_id", "displayed_article_id",
    "priority_article_id", "displayed_reason", "source_count", "sort_at",
    "rule_version", "event_state",
)
MEMBER_FIELDS = (
    "article_id", "source", "source_display_name", "title", "url",
    "published_at", "decision",
)


class ExportError(RuntimeError):
    """The snapshot could not be built; nothing was written."""


class EmptyFeedError(ExportError):
    """The feed is empty, which on the live corpus means the pipeline stopped
    (nothing left inside the freshness window). Nothing was written, so the
    demo keeps its last real snapshot, whose banner shows its age."""


def readonly_engine(db_path: Path) -> Engine:
    """A SQLAlchemy engine that can only read ``db_path``.

    ``mode=ro`` makes SQLite refuse every write (and refuse to create a missing
    file); ``query_only`` is a second lock. The driver runs in autocommit mode
    and the engine emits an explicit BEGIN, so a session reads one consistent
    snapshot (the SQLAlchemy-documented pysqlite transaction recipe).
    """
    path = Path(db_path).resolve()
    if not path.is_file():
        raise ExportError(f"database not found: {path}")
    uri = f"{path.as_uri()}?mode=ro"

    def connect():
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=30)
        conn.isolation_level = None
        conn.execute("PRAGMA query_only=ON")
        return conn

    engine = create_engine("sqlite://", creator=connect)

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


def _pick(data: dict, fields: tuple) -> dict:
    return {name: data.get(name) for name in fields}


def public_item(scored: dict) -> dict:
    """Reduce one serialized ScoredArticle to the public demo shape."""
    item = _pick(scored, SCORED_FIELDS)
    item["article"] = _pick(scored["article"], ARTICLE_FIELDS)
    cluster = scored.get("cluster")
    if cluster:
        public_cluster = _pick(cluster, CLUSTER_FIELDS)
        public_cluster["members"] = [_pick(m, MEMBER_FIELDS) for m in cluster.get("members") or []]
        item["cluster"] = public_cluster
    else:
        item["cluster"] = None
    return item


def build_snapshot(db_path: Path, user_id: str = DEMO_USER_ID,
                   now: Optional[datetime] = None) -> tuple[list, dict]:
    """Build (feed, meta) for ``user_id`` from a read-only view of ``db_path``."""
    now = now or datetime.now(timezone.utc)
    engine = readonly_engine(db_path)
    try:
        with sessionmaker(bind=engine, autoflush=False)() as session:
            if profile_repository.get_by_id(session, user_id) is None:
                raise ExportError(f"profile {user_id!r} not found in {db_path}")
            scored = get_feed(user_id=user_id, session=session)
            last = last_successful_cycle(session)
            session.rollback()
    finally:
        engine.dispose()

    feed = [public_item(sa.model_dump(mode="json")) for sa in scored]
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "last_successful_cycle_at": last[3] if last else None,
        "item_count": len(feed),
    }
    return feed, meta


def _dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def write_snapshot(out_dir: Path, feed: list, meta: dict) -> None:
    """Write feed.json and meta.json so readers only ever see complete files.

    Both payloads are serialized before anything touches the disk, written to
    temp files in ``out_dir``, then renamed into place (feed first, meta last,
    so meta never describes a feed that is not there yet).
    """
    out_dir = Path(out_dir)
    texts = {FEED_FILE: _dumps(feed), META_FILE: _dumps(meta)}
    out_dir.mkdir(parents=True, exist_ok=True)
    temps: dict[str, str] = {}
    try:
        for name, body in texts.items():
            fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=out_dir)
            temps[name] = tmp
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
        for name in (FEED_FILE, META_FILE):
            os.replace(temps.pop(name), out_dir / name)
    finally:
        for tmp in temps.values():
            try:
                os.unlink(tmp)
            except OSError:
                pass


def export_snapshot(db_path: Path, out_dir: Path, user_id: str = DEMO_USER_ID,
                    now: Optional[datetime] = None, allow_empty: bool = False) -> dict:
    """Build and write the snapshot; returns meta. Raises on any failure, and on
    an empty feed unless ``allow_empty``."""
    feed, meta = build_snapshot(db_path, user_id=user_id, now=now)
    if not feed and not allow_empty:
        raise EmptyFeedError(
            f"the feed of {user_id!r} is empty (last successful cycle: "
            f"{meta['last_successful_cycle_at']}); keeping the previous snapshot")
    write_snapshot(out_dir, feed, meta)
    return meta
