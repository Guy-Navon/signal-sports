"""#255 backfill: every human-rated or sampled article id in docs/qa is protected
from retention, whatever the rating document is called.

The 2026-10-30 triage found the first version's file list had silently missed
three newer rating sets (week sample, focused #345, people #259). The coverage
test below reads the real docs/qa so the next new rating file fails CI instead.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.qa import census_rating as cr
from scripts import protect_rated_articles as tool

REPO_QA = Path(__file__).resolve().parents[2] / "docs" / "qa"


def _names_rated_or_sampled_articles(doc) -> bool:
    """Shape test, independent of file names: a ratings store ({"ratings": {profile: {id: label}}})
    or a sample ({"profiles": {profile: {"items": [{"id": ...}]}}})."""
    if not isinstance(doc, dict):
        return False
    if isinstance(doc.get("ratings"), dict):
        return True
    profiles = doc.get("profiles")
    return isinstance(profiles, dict) and any(
        isinstance(block, dict) and block.get("items") for block in profiles.values())


def test_every_rating_or_sample_document_in_docs_qa_is_covered():
    # A new census3_ratings.json, a re-rate, a focused sample: if it names rated
    # articles, the backfill must read it. Rename it to *_ratings.json /
    # *_sample.json (or <name>.json beside <name>_ratings.json) to be covered.
    covered = set(tool.documents(REPO_QA))
    shaped = {p for p in REPO_QA.glob("*.json")
              if _names_rated_or_sampled_articles(json.loads(p.read_text(encoding="utf-8")))}
    assert shaped, "docs/qa holds no rating documents: the test is looking in the wrong place"
    assert sorted(p.name for p in shaped - covered) == []


def test_every_covered_document_names_articles():
    # A covered file whose shape the reader does not understand would protect nothing.
    for path in tool.documents(REPO_QA):
        assert cr.article_ids(json.loads(path.read_text(encoding="utf-8"))), path.name


# ── the script against the test database ──────────────────────────────────────

_PREFIX = "rss_t255_"


def _ratings(path: Path, ids):
    path.write_text(json.dumps({"generated": "x", "seed": 1,
                                "ratings": {"guy": {f"{_PREFIX}{i}": "feed" for i in ids}}}),
                    encoding="utf-8")


def _sample(path: Path, ids):
    path.write_text(json.dumps({"meta": {}, "profiles": {"guy": {
        "strata": {}, "items": [{"id": f"{_PREFIX}{i}"} for i in ids]}}}), encoding="utf-8")


@pytest.fixture
def qa_dir(tmp_path):
    _ratings(tmp_path / "census_ratings.json", ["a"])
    _ratings(tmp_path / "census2_ratings.json", ["a", "b"])
    _sample(tmp_path / "census2_sample.json", ["a", "b", "c"])
    _ratings(tmp_path / "week_x_ratings.json", ["d"])
    _sample(tmp_path / "week_x.json", ["d", "e"])           # bare sample beside its ratings
    (tmp_path / "week_x_dev_analysis.json").write_text(      # analysis output: not ground truth
        json.dumps({"rows": [{"id": f"{_PREFIX}z"}]}), encoding="utf-8")
    return tmp_path


def _add_article(session, suffix, *, days_ago):
    from app.db.orm_models import ArticleRow
    _id = f"{_PREFIX}{suffix}"
    session.add(ArticleRow(
        id=_id, source="walla_sport", source_display_name="walla",
        url=f"https://example.test/{_id}", title=f"כתבה {_id}", language="he",
        published_at=(datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).isoformat(),
        sport="basketball", entities=[], event_type="news", event_certainty="confirmed",
        importance="low", tags=[], entity_ids=[],
    ))


def _clean(session):
    session.execute(text(f"DELETE FROM articles WHERE id LIKE '{_PREFIX}%'"))
    session.execute(text(f"DELETE FROM protected_articles WHERE article_id LIKE '{_PREFIX}%'"))
    session.commit()


@pytest.fixture
def session(_application, monkeypatch):
    monkeypatch.setenv("ARTICLE_RETENTION_DAYS", "30")
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        _clean(s)
        for suffix in "abcdez":
            _add_article(s, suffix, days_ago=40)        # all older than the window
        _add_article(s, "unrated", days_ago=40)
        s.commit()
        yield s
        s.rollback()
        _clean(s)


def _reasons(session):
    return dict(session.execute(text(
        f"SELECT article_id, reason FROM protected_articles WHERE article_id LIKE '{_PREFIX}%'")).all())


def test_apply_records_the_first_document_that_rated_each_id(session, qa_dir):
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 0
    session.expire_all()
    assert _reasons(session) == {
        f"{_PREFIX}a": "census_ratings",       # census #1 rated it before census #2 re-used it
        f"{_PREFIX}b": "census2_ratings",
        f"{_PREFIX}c": "census2_sample",       # sampled, not (yet) rated
        f"{_PREFIX}d": "week_x_ratings",
        f"{_PREFIX}e": "week_x",
    }


def test_dry_run_writes_nothing_and_apply_is_idempotent(session, qa_dir, capsys):
    assert tool.main(["--qa-dir", str(qa_dir)]) == 0
    assert "would add 5 protection rows" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}

    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 0
    assert "added 5 protection rows" in capsys.readouterr().out
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 0
    assert "added 0 protection rows" in capsys.readouterr().out


def test_report_shows_retention_would_keep_every_rated_id(session, qa_dir, capsys):
    tool.main(["--qa-dir", str(qa_dir)])
    before = capsys.readouterr().out
    assert "5 rated or sampled ids in the corpus are NOT protected" in before

    tool.main(["--qa-dir", str(qa_dir), "--apply"])
    after = capsys.readouterr().out
    assert "0 rated or sampled ids in the corpus are NOT protected" in after
    from app.ingestion.retention import cleanup_articles
    summary = cleanup_articles(session, dry_run=True)
    assert f"protected_rated={summary['protected_rated']}" in after
    session.expire_all()
    assert session.execute(text(                                    # a dry run deletes nothing
        f"SELECT COUNT(*) FROM articles WHERE id LIKE '{_PREFIX}%'")).scalar_one() == 7


def test_apply_on_the_live_corpus_needs_the_backup_acknowledgement(session, qa_dir, monkeypatch, capsys):
    monkeypatch.setattr("app.db.corpus_protection.is_protected_corpus_db", lambda url=None: True)
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 2
    assert "backup_db.py" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}

    assert tool.main(["--qa-dir", str(qa_dir), "--apply", "--i-know-this-is-the-live-corpus"]) == 0
    session.expire_all()
    assert len(_reasons(session)) == 5
