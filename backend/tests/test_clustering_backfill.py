"""
Cluster backfill + corpus QA (#102) — docs/CLUSTERING.md.

Everything here runs on THROWAWAY sqlite files in tmp_path. The real corpus is never
opened for write; the protected-corpus refusal is asserted directly.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "backfill_clusters.py"
BASE = datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)


def _seed_db(path: Path, rows: list[tuple]) -> None:
    """Build a minimal DB with the schema the backfill needs.

    Uses its OWN throwaway engine. It must NOT touch ``DATABASE_URL`` or reload
    ``app.db.database`` — doing so repoints the whole suite's global engine at this temp
    file and cascades failures into unrelated tests. (It did, once.) The backfill script
    itself runs in a subprocess and sets its own DATABASE_URL, so it stays isolated.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.orm_models import ArticleRow, Base

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        for aid, source, title, hours, sport, event_type, ents in rows:
            s.add(ArticleRow(
                id=aid, source=source, source_display_name=source,
                url=f"https://example.test/{aid}", title=title, language="he",
                published_at=(BASE + timedelta(hours=hours)).isoformat(),
                sport=sport, entities=[], event_type=event_type,
                event_certainty="confirmed", importance="medium", tags=[],
                entity_ids=ents,
            ))
        s.commit()
    engine.dispose()


_STORY = [
    ("rss_a", "walla_sport", "גרג לי חתם בהפועל חולון", 0, "basketball", "signing",
     ["team:hapoel_holon"]),
    ("rss_b", "ynet_sport", "גרג לי חתם רשמית בהפועל חולון", 1, "basketball", "signing",
     ["team:hapoel_holon"]),
    ("rss_c", "sport5_sport", "רשמית: גרג לי חתם בהפועל חולון", 2, "basketball", "signing",
     ["team:hapoel_holon"]),
    ("rss_z", "walla_sport", "משהו אחר לגמרי בנושא אחר", 5, "football", "news", []),
]


def _run(db: Path, *args, expect_ok: bool = True):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), *args],
        capture_output=True, text=True, cwd=str(BACKEND),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if expect_ok:
        assert proc.returncode == 0, proc.stderr[-2000:]
    return proc


def _clusters(db: Path) -> list[tuple]:
    c = sqlite3.connect(db)
    rows = c.execute(
        "select id, anchor_article_id, rule_version from story_clusters order by id"
    ).fetchall()
    c.close()
    return rows


def _membership(db: Path) -> dict:
    c = sqlite3.connect(db)
    rows = c.execute(
        "select id, cluster_id from articles where cluster_id is not null"
    ).fetchall()
    c.close()
    return dict(rows)


@pytest.fixture
def db(tmp_path) -> Path:
    p = tmp_path / "corpus.db"
    _seed_db(p, _STORY)
    return p


# ── Safety ───────────────────────────────────────────────────────────────────

class TestSafety:
    def test_apply_refuses_the_protected_live_corpus(self):
        from app.db.corpus_protection import CANONICAL_CORPUS_PATH

        if not CANONICAL_CORPUS_PATH.exists():
            pytest.skip("no local corpus present")
        proc = _run(CANONICAL_CORPUS_PATH, "--apply", expect_ok=False)
        assert proc.returncode != 0
        assert "REFUSED" in proc.stdout + proc.stderr
        assert "COPY" in proc.stdout + proc.stderr

    def test_dry_run_is_the_default_and_writes_nothing(self, db):
        before = db.read_bytes()

        proc = _run(db)                       # no --apply

        assert "DRY-RUN" in proc.stdout
        assert db.read_bytes() == before, "dry-run modified the target database"
        assert _clusters(db) == []
        assert _membership(db) == {}

    def test_dry_run_still_reports_what_apply_would_do(self, db):
        out = db.parent / "r.json"
        _run(db, "--out", str(out))
        report = json.loads(out.read_text(encoding="utf-8"))

        # It ran the REAL backfill (on a scratch copy) — so the numbers are exact.
        assert report["mode"] == "DRY-RUN"
        assert report["clusters"]["proposed_count"] == 1
        assert db.read_bytes() and _clusters(db) == []      # target still untouched


# ── Apply ────────────────────────────────────────────────────────────────────

class TestApply:
    def test_apply_persists_clusters(self, db):
        _run(db, "--apply")

        clusters = _clusters(db)
        assert len(clusters) == 1
        members = _membership(db)
        assert set(members) == {"rss_a", "rss_b", "rss_c"}
        assert len(set(members.values())) == 1
        assert "rss_z" not in members          # unrelated article untouched

    def test_repeated_apply_is_idempotent_and_preserves_ids(self, db):
        _run(db, "--apply")
        first_clusters, first_members = _clusters(db), _membership(db)

        _run(db, "--apply")
        _run(db, "--apply")

        assert _clusters(db) == first_clusters, "cluster ids churned across runs"
        assert _membership(db) == first_members
        c = sqlite3.connect(db)
        assert c.execute("select count(*) from story_clusters").fetchone()[0] == 1
        c.close()

    def test_rule_version_is_recorded_and_updatable_without_id_churn(self, db):
        _run(db, "--apply", "--rule-version", "1")
        before = _clusters(db)
        assert before[0][2] == 1

        _run(db, "--apply", "--rule-version", "2")
        after = _clusters(db)

        assert after[0][0] == before[0][0]     # same id
        assert after[0][2] == 2                # new rule_version

    def test_no_dangling_edges(self, db):
        _run(db, "--apply")
        c = sqlite3.connect(db)
        article_ids = {r[0] for r in c.execute("select id from articles")}
        cluster_ids = {r[0] for r in c.execute("select id from story_clusters")}
        for a, b, cid in c.execute("select article_a, article_b, cluster_id from cluster_edges"):
            assert a in article_ids and b in article_ids
            assert cid in cluster_ids
        c.close()

    def test_only_accepted_evidence_is_stored(self, db):
        _run(db, "--apply")
        c = sqlite3.connect(db)
        rows = c.execute("select rare_tokens, tier from cluster_edges").fetchall()
        c.close()
        assert rows
        for rare_tokens, tier in rows:
            assert json.loads(rare_tokens), "an edge must carry its discriminative evidence"
            assert tier in ("A", "B", "C")


# ── Snapshot report ──────────────────────────────────────────────────────────

class TestSnapshotReport:
    def test_report_contains_every_required_field(self, db):
        out = db.parent / "report.json"
        _run(db, "--apply", "--out", str(out))
        r = json.loads(out.read_text(encoding="utf-8"))

        assert r["snapshot_timestamp"] and r["rule_version"] and r["matcher_config"]
        for k in ("path", "size_bytes", "mtime"):
            assert k in r["database"]                       # db identity/fingerprint
        c = r["corpus"]
        for k in ("total_articles", "rss_articles", "per_source", "sport_distribution",
                  "event_state_distribution", "time_range"):
            assert k in c
        cl = r["clusters"]
        for k in ("proposed_count", "member_count", "size_distribution", "created",
                  "retained", "changed", "removed", "ids_preserved"):
            assert k in cl
        assert "before" in r["cards"] and "after" in r["cards"]
        assert "newly_clustered" in r["articles"] and "newly_unclustered" in r["articles"]
        assert "near_miss_reasons" in r
        assert r["detail"][0]["members"] and r["detail"][0]["edges"]

    def test_cards_before_after_is_computed(self, db):
        out = db.parent / "r2.json"
        _run(db, "--apply", "--out", str(out))
        r = json.loads(out.read_text(encoding="utf-8"))
        # 4 articles: 3 collapse into 1 card, 1 stands alone → 4 → 2
        assert r["cards"]["before"] == 4
        assert r["cards"]["after"] == 2

    def test_near_miss_reasons_are_bounded_and_named(self, db):
        from app.clustering.intra_source import IntraRejection
        from app.clustering.matcher import Rejection
        out = db.parent / "r3.json"
        _run(db, "--apply", "--out", str(out))
        r = json.loads(out.read_text(encoding="utf-8"))
        allowed = {v for k, v in vars(Rejection).items() if not k.startswith("_")}
        allowed |= {v for k, v in vars(IntraRejection).items() if not k.startswith("_")}
        assert set(r["near_miss_reasons"]) <= allowed

    def test_second_run_reports_ids_preserved_not_recreated(self, db):
        _run(db, "--apply")
        out = db.parent / "r4.json"
        _run(db, "--apply", "--out", str(out))
        r = json.loads(out.read_text(encoding="utf-8"))
        assert r["clusters"]["created"] == []
        assert r["clusters"]["ids_preserved"] == 1
        assert r["clusters"]["removed"] == []


# ── Same matcher as live ─────────────────────────────────────────────────────

class TestSameMatcherAsLive:
    def test_backfill_replays_the_live_ingestion_stage(self):
        """Backfill must NOT have its own matching semantics — it calls the live stage."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "run_clustering_stage" in src
        assert "cluster_articles" in src
        # and must not reimplement matching
        assert "def match_pair" not in src and "def validate_coherence" not in src
