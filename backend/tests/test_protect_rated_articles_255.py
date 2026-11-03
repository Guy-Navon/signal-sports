"""#255 backfill: every human-rated or sampled article id in docs/qa is protected
from retention, whatever the rating document is called.

The 2026-10-30 triage found the first version's file list had silently missed
three newer rating sets (week sample, focused #345, people #259). The coverage
test below reads the real docs/qa so the next new rating file fails CI instead.

Scope of that guard: it recognises the two formats the rating tooling writes
(a ratings store and a sample, see `_names_rated_or_sampled_articles`), anywhere
under docs/qa. The third recognised format, applied correction logs
({"rows": [{"id": ...}]}), is an explicit list (owner decision 2026-11-02),
guarded by its own tests below. Score and analysis output are not checked.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

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
    # *_sample.json (or <name>.json beside <name>_ratings.json) and keep it at
    # the top level of docs/qa to be covered; a subdirectory is not read.
    covered = set(tool.documents(REPO_QA))
    shaped = {p for p in REPO_QA.rglob("*.json")
              if _names_rated_or_sampled_articles(json.loads(p.read_text(encoding="utf-8")))}
    assert shaped, "docs/qa holds no rating documents: the test is looking in the wrong place"
    assert sorted(str(p.relative_to(REPO_QA)) for p in shaped - covered) == []


def test_every_covered_document_is_readable():
    # A covered file whose shape the reader does not understand would protect nothing.
    for path in tool.documents(REPO_QA):
        assert not tool.unreadable(json.loads(path.read_text(encoding="utf-8"))), path.name


@pytest.mark.parametrize("doc, unreadable", [
    ({"ratings": {"guy": {"rss_x": "feed"}}}, False),
    ({"meta": {}, "profiles": {"guy": {"items": [{"id": "rss_x"}]}}}, False),
    # A ratings store committed before the first keypress protects nothing yet, legitimately.
    ({"generated": "x", "seed": 1, "ratings": {"guy": {}}}, False),
    ({"ratings": {}}, False),
    # A sample with no items, or a shape article_ids() cannot read, is a broken file.
    ({"meta": {}, "profiles": {"guy": {"strata": {}, "items": []}}}, True),
    ({"rows": [{"id": "rss_x"}]}, True),
    ([{"id": "rss_x"}], True),
    ({"profiles": ["guy"]}, True),
])
def test_unreadable_flags_documents_that_would_protect_nothing(doc, unreadable):
    assert tool.unreadable(doc) is unreadable


def test_documents_order_numbers_naturally(tmp_path):
    for name in ("census10_ratings.json", "census2_ratings.json", "census_ratings.json",
                 "census10_sample.json", "census2_sample.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [p.name for p in tool.documents(tmp_path)] == [
        "census_ratings.json", "census2_ratings.json", "census10_ratings.json",
        "census2_sample.json", "census10_sample.json"]


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
    (tmp_path / "n191_event_corrections.json").write_text(   # a listed correction log
        json.dumps({"applied": True, "rows": [{"id": f"{_PREFIX}a"}, {"id": f"{_PREFIX}f"}]}),
        encoding="utf-8")
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
        for suffix in "abcdefz":
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
        f"{_PREFIX}f": "n191_event_corrections",   # corrected by hand, never rated
    }


def test_dry_run_writes_nothing_and_apply_is_idempotent(session, qa_dir, capsys):
    assert tool.main(["--qa-dir", str(qa_dir)]) == 0
    assert "would add 6 protection rows" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}

    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 0
    assert "added 6 protection rows" in capsys.readouterr().out
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 0
    assert "added 0 protection rows" in capsys.readouterr().out


def test_report_shows_retention_would_keep_every_rated_id(session, qa_dir, capsys):
    tool.main(["--qa-dir", str(qa_dir)])
    before = capsys.readouterr().out
    assert "6 rated, sampled or corrected ids in the corpus are NOT protected" in before

    tool.main(["--qa-dir", str(qa_dir), "--apply"])
    after = capsys.readouterr().out
    assert "0 rated, sampled or corrected ids in the corpus are NOT protected" in after
    from app.ingestion.retention import cleanup_articles
    summary = cleanup_articles(session, dry_run=True)
    assert summary["protected_rated"] >= 6                          # a..f, all 40 days old
    assert f"protected_rated={summary['protected_rated']}" in after
    protected = set(_reasons(session))
    assert f"{_PREFIX}z" not in protected and f"{_PREFIX}unrated" not in protected
    session.expire_all()
    assert session.execute(text(                                    # a dry run deletes nothing
        f"SELECT COUNT(*) FROM articles WHERE id LIKE '{_PREFIX}%'")).scalar_one() == 8


def test_apply_on_the_live_corpus_needs_the_backup_acknowledgement(session, qa_dir, monkeypatch, capsys):
    monkeypatch.setattr("app.db.corpus_protection.is_protected_corpus_db", lambda url=None: True)
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 2
    assert "backup_db.py" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}

    assert tool.main(["--qa-dir", str(qa_dir), "--apply", "--i-know-this-is-the-live-corpus"]) == 0
    session.expire_all()
    assert len(_reasons(session)) == 6


def test_an_unreadable_covered_document_stops_the_apply_before_any_write(session, qa_dir, capsys):
    (qa_dir / "broken_sample.json").write_text(json.dumps({"rows": [{"id": f"{_PREFIX}a"}]}),
                                               encoding="utf-8")
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 2
    assert "broken_sample.json" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}


# ── correction logs: the third recognised format, an explicit list ────────────

def test_every_listed_correction_log_exists_and_names_articles():
    for name in tool.CORRECTION_LOGS:
        doc = json.loads((REPO_QA / name).read_text(encoding="utf-8"))
        assert tool.correction_log_ids(doc), name


def test_every_correction_log_in_docs_qa_is_listed():
    # A new n<issue>_*_corrections.json or *_log.json must be listed (with its reason)
    # or deliberately left out here, so it is never forgotten silently.
    found = {p.name for p in REPO_QA.rglob("*.json")
             if p.name.endswith(("_corrections.json", "_log.json"))}
    assert found == set(tool.CORRECTION_LOGS)


@pytest.mark.parametrize("doc, ids", [
    ({"applied": True, "rows": [{"id": "rss_x", "input": {"id": "rss_x"}}, {"id": "rss_y"}]},
     {"rss_x", "rss_y"}),
    ({"applied": True, "rows": []}, set()),
    ({"ratings": {"guy": {"rss_x": "feed"}}}, set()),
])
def test_correction_log_ids_reads_rows(doc, ids):
    assert tool.correction_log_ids(doc) == ids


def test_an_empty_listed_correction_log_stops_the_apply(session, qa_dir, capsys):
    (qa_dir / "n191_event_corrections.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    assert tool.main(["--qa-dir", str(qa_dir), "--apply"]) == 2
    assert "n191_event_corrections.json" in capsys.readouterr().out
    session.expire_all()
    assert _reasons(session) == {}
