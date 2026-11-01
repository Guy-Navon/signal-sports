"""Smoke test for scripts/census_calibration_fit.py (#237) on a tiny fixture.

Runs the script in a subprocess (it pins its own environment before importing
the app) against a temp corpus, and proves the file is not modified.
"""

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "census_calibration_fit.py"

TITLES = [
    "מכבי תל אביב החתימה גארד חדש מהיורוליג",
    "הפועל ירושלים ניצחה את מכבי תל אביב בליגת העל בכדורסל",
    "דני אבדיה נפצע במשחק של פורטלנד",
    "אלקראס זכה בווימבלדון",
    "מכבי תל אביב במגעים עם פורוורד אמריקאי",
    "היורוליג: ריאל מדריד ניצחה את פנאתינייקוס",
]


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    db = tmp_path / "corpus.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE articles (id TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, subtitle TEXT)")
    ids = [f"rss_walla_{i:03d}" for i in range(len(TITLES))]
    for i, (article_id, title) in enumerate(zip(ids, TITLES)):
        conn.execute("INSERT INTO articles VALUES (?, 'walla_sport', ?, ?, NULL)",
                     (article_id, f"https://sports.walla.co.il/item/{i}", title))
    conn.commit()
    conn.close()
    ratings = tmp_path / "ratings.json"
    ratings.write_text(json.dumps({"ratings": {"guy": dict(zip(ids, ["push", "feed", "high", "hide", "feed", "feed"]))}}),
                       encoding="utf-8")
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps({"profiles": {"guy": {"items": [{"id": i, "title": t} for i, t in zip(ids, TITLES)]}}},
                                 ensure_ascii=False), encoding="utf-8")
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps([{"kind": "event", "scope_ref": "comp:euroleague", "event_type": "news", "delta": 1}]),
                         encoding="utf-8")
    return db, ratings, sample, candidate


def test_runs_read_only_on_a_fixture(tmp_path):
    db, ratings, sample, candidate = _fixture(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--ratings", str(ratings), "--sample", str(sample),
         "--candidate", str(candidate), "--show"],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    assert "articles replayed: 6 (fit 3, hold-out 3)" in out
    for marker in ("BASE  fit:", "BASE hold:", "CAND  fit:", "CAND hold:", "flips:", "closer"):
        assert marker in out
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["candidate.json", "corpus.db", "ratings.json", "sample.json"]


def test_missing_database_is_an_error(tmp_path):
    _, ratings, sample, _ = _fixture(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(tmp_path / "absent.db"), "--ratings", str(ratings),
         "--sample", str(sample)],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )
    assert proc.returncode == 1
    assert not (tmp_path / "absent.db").exists()


def test_a_sealed_held_out_half_is_excluded_unless_final_evaluation(tmp_path):
    # Census #3 (#241): calibration never sees the held-out labels, even passed via --review.
    db, ratings, sample, _ = _fixture(tmp_path)
    doc = json.loads(sample.read_text(encoding="utf-8"))
    held = [doc["profiles"]["guy"]["items"][i]["id"] for i in (1, 4)]
    doc["meta"] = {"sealed_heldout": {"ids": "held.json", "ratings": "held_ratings.json"}}
    sample.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "held.json").write_text(json.dumps(held), encoding="utf-8")
    review = tmp_path / "held_ratings.json"
    review.write_text(json.dumps({"ratings": {"guy": {k: "push" for k in held}}}), encoding="utf-8")

    def run(*extra):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(db), "--ratings", str(ratings), "--sample", str(sample),
             "--review", str(review), *extra],
            cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        return proc.stdout

    assert "sealed held-out half: 2 ratings excluded" in run()
    assert "excluded" not in run("--final-heldout-eval")
