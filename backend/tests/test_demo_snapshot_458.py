"""Public demo snapshot exporter (#458).

The demo is a static copy of the real feed of profile ``guy``. These tests lock
what makes it safe to publish: the exporter reads the database read-only, builds
the same feed GET /api/me/feed serves, strips internal fields, carries no user
data, and never replaces a good snapshot with a broken one.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db.orm_models import ArticleRow, Base, FeedbackRow, SchedulerCycleRow, UserRow
from app.ops import demo_snapshot
from app.repositories import profile_repository
from app.seed.seed_profiles import SEED_PROFILES

GUY_EMAIL = "guy-private@example.test"
BASE = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def _article(_id, *, title, event_type, sport="basketball", entities=None,
             league="Israeli Basketball League", hours=0):
    return ArticleRow(
        id=_id, source="sport5", source_display_name="ספורט 5",
        url=f"https://example.test/{_id}", title=title, language="he",
        published_at=(BASE + timedelta(hours=hours)).isoformat(),
        sport=sport, league=league, entities=entities or [],
        event_type=event_type, event_certainty="confirmed", importance="high",
        tags=[], entity_ids=[],
        classified_by="llm", classification_provider="groq",
        classification_reason="internal LLM rationale",
        classification_trace={"internal": "evidence hits"},
    )


@pytest.fixture
def fixture_db(tmp_path):
    """A small, self-contained corpus on disk (never the test-suite DB)."""
    path = tmp_path / "corpus.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        for profile in SEED_PROFILES:
            profile_repository.insert(s, profile)
        s.add(UserRow(id="guy", email=GUY_EMAIL, role="demo",
                      password_hash="secret-hash", created_at=BASE.isoformat()))
        s.add_all([
            _article("rss_maccabi_sign", title="מכבי ת״א החתימה גארד",
                     event_type="signing", entities=["Maccabi Tel Aviv Basketball"]),
            _article("rss_maccabi_dismissed", title="מכבי ת״א בשיחות עם סנטר",
                     event_type="negotiation", entities=["Maccabi Tel Aviv Basketball"],
                     hours=1),
            _article("rss_tennis_r1", title="Early round tennis", event_type="match_result",
                     sport="tennis", league=None, entities=[], hours=2),
        ])
        s.add(FeedbackRow(id="fb1", user_id="guy", article_id="rss_maccabi_dismissed",
                          action="not_interested", created_at=BASE.isoformat(), retracted=0))
        s.add(SchedulerCycleRow(id="cycle_1", trigger="scheduled",
                                requested_at=BASE.isoformat(), started_at=BASE.isoformat(),
                                finished_at="2026-11-10T09:05:00+00:00", status="succeeded"))
        s.commit()
    engine.dispose()
    return path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export(db, out):
    return demo_snapshot.export_snapshot(
        db, out, now=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc))


def test_snapshot_is_guys_consumer_feed(fixture_db, tmp_path):
    out = tmp_path / "out"
    meta = _export(fixture_db, out)

    feed = json.loads((out / "feed.json").read_text(encoding="utf-8"))
    ids = [item["article"]["id"] for item in feed]
    assert "rss_maccabi_sign" in ids
    assert "rss_tennis_r1" not in ids            # hidden for guy
    assert "rss_maccabi_dismissed" not in ids    # guy dismissed it
    sign = next(i for i in feed if i["article"]["id"] == "rss_maccabi_sign")
    assert sign["decision"] != "hidden"
    assert sign["reason_he"]
    assert sign["article"]["url"] == "https://example.test/rss_maccabi_sign"

    on_disk = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert on_disk == meta
    assert on_disk["item_count"] == len(feed)
    assert on_disk["last_successful_cycle_at"] == "2026-11-10T09:05:00+00:00"
    assert on_disk["generated_at"].startswith("2026-11-10T10:00:00")


def test_snapshot_matches_the_feed_route(fixture_db, tmp_path):
    """Same code path as GET /api/me/feed: same items, same order, same decisions."""
    from app.api.routes_feed import get_feed

    _export(fixture_db, tmp_path / "out")
    exported = json.loads((tmp_path / "out" / "feed.json").read_text(encoding="utf-8"))

    engine = create_engine(f"sqlite:///{fixture_db}")
    with sessionmaker(bind=engine)() as s:
        served = get_feed(user_id="guy", session=s)
    engine.dispose()
    assert [(i["article"]["id"], i["decision"], i["reason_he"]) for i in exported] == [
        (sa.article.id, sa.decision, sa.reason_he) for sa in served
    ]


def test_snapshot_strips_internal_fields_and_user_data(fixture_db, tmp_path):
    out = tmp_path / "out"
    _export(fixture_db, out)
    raw = (out / "feed.json").read_text(encoding="utf-8") + (out / "meta.json").read_text(encoding="utf-8")

    for forbidden in ("classification_trace", "classification_reason", "internal LLM rationale",
                      "contributions", "reasoning", "matched_event_rule", "entity_ids",
                      "suppressed_members", GUY_EMAIL, "secret-hash", "password", "email"):
        assert forbidden not in raw, forbidden


def test_database_is_opened_read_only_and_left_unchanged(fixture_db, tmp_path):
    before = _digest(fixture_db)
    engine = demo_snapshot.readonly_engine(fixture_db)
    with engine.connect() as conn:
        with pytest.raises(OperationalError, match="readonly"):
            conn.execute(text("DELETE FROM articles"))
    engine.dispose()

    _export(fixture_db, tmp_path / "out")
    assert _digest(fixture_db) == before
    assert not fixture_db.with_name(fixture_db.name + "-wal").exists()


def test_failed_export_keeps_the_previous_snapshot(fixture_db, tmp_path):
    out = tmp_path / "out"
    _export(fixture_db, out)
    good_feed = (out / "feed.json").read_bytes()
    good_meta = (out / "meta.json").read_bytes()

    with pytest.raises(demo_snapshot.ExportError):
        demo_snapshot.export_snapshot(fixture_db, out, user_id="nobody")

    assert (out / "feed.json").read_bytes() == good_feed
    assert (out / "meta.json").read_bytes() == good_meta
    assert sorted(p.name for p in out.iterdir()) == ["feed.json", "meta.json"]


def test_empty_feed_is_not_written_unless_allowed(fixture_db, tmp_path):
    """A stopped worker empties the feed once the freshness window passes. The
    demo then keeps its last real snapshot (whose banner already says how old it
    is) instead of publishing an empty page."""
    out = tmp_path / "out"
    _export(fixture_db, out)
    good = (out / "feed.json").read_bytes()
    engine = create_engine(f"sqlite:///{fixture_db}")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM articles"))
    engine.dispose()

    with pytest.raises(demo_snapshot.EmptyFeedError):
        _export(fixture_db, out)
    assert (out / "feed.json").read_bytes() == good

    meta = demo_snapshot.export_snapshot(fixture_db, out, allow_empty=True)
    assert meta["item_count"] == 0
    assert json.loads((out / "feed.json").read_text(encoding="utf-8")) == []


def test_write_failure_mid_way_keeps_both_previous_files(tmp_path):
    out = tmp_path / "out"
    demo_snapshot.write_snapshot(out, [{"a": 1}], {"item_count": 1})
    good = {p.name: p.read_bytes() for p in out.iterdir()}

    with pytest.raises(TypeError):
        demo_snapshot.write_snapshot(out, [{"a": 2}], {"bad": object()})

    assert {p.name: p.read_bytes() for p in out.iterdir()} == good


def test_missing_database_fails_instead_of_creating_one(tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(demo_snapshot.ExportError):
        demo_snapshot.export_snapshot(missing, tmp_path / "out")
    assert not missing.exists()


def _run_cli(*args):
    backend = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(backend / "scripts" / "export_demo_snapshot.py"), *args],
        capture_output=True, text=True, encoding="utf-8", env=dict(os.environ), timeout=120,
    )


def test_cli_exports_and_exits_zero(fixture_db, tmp_path):
    out = tmp_path / "cli-out"
    before = _digest(fixture_db)
    result = _run_cli("--db", str(fixture_db), "--out", str(out),
                      "--env-file", str(tmp_path / "no.env"))
    assert result.returncode == 0, result.stderr
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["item_count"] >= 1
    assert _digest(fixture_db) == before


def test_cli_fails_non_zero_without_writing(tmp_path):
    out = tmp_path / "cli-out"
    result = _run_cli("--db", str(tmp_path / "missing.db"), "--out", str(out),
                      "--env-file", str(tmp_path / "no.env"))
    assert result.returncode == 1
    assert "EXPORT FAILED" in result.stderr
    assert not out.exists()
