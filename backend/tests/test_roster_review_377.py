"""scripts/roster_review.py (#377): the read-only roster review aid."""

import importlib.util
import sqlite3
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "roster_review", Path(__file__).resolve().parents[1] / "scripts" / "roster_review.py"
)
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)


def _copy(tmp_path: Path) -> Path:
    db = tmp_path / "copy.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE articles (id TEXT, published_at TEXT, source TEXT, "
                "title TEXT, subtitle TEXT)")
    con.executemany("INSERT INTO articles VALUES (?, ?, ?, ?, ?)", [
        ("a1", "2026-10-01T10:00:00", "walla_sport", "פגישה על הפרק: מו\"מ הפועל וג`ייקוב טופין", None),
        ("a2", "2026-10-02T10:00:00", "ynet_sport", "הפועל ניצחה", "ג'ייקוב טופין קלע 20"),
        ("held", "2026-10-03T10:00:00", "one_sport", "ג'ייקוב טופין חתם", ""),
        ("a3", "2026-10-04T10:00:00", "ynet_sport", "ריאל מדריד ניצחה", ""),
    ])
    con.commit()
    con.close()
    return db


def test_mentions_match_every_geresh_spelling_and_skip_the_holdout(tmp_path):
    rows = rr.find_mentions(_copy(tmp_path), "ג'ייקוב טופין", skip_ids={"held"})
    assert [r[2] for r in rows] == ['פגישה על הפרק: מו"מ הפועל וג`ייקוב טופין', "הפועל ניצחה"]


def test_holdout_ids_are_the_week_sample_test_split():
    ids = rr.holdout_ids()
    assert len(ids) == 35


def test_refuses_the_live_corpus_file(monkeypatch, tmp_path, capsys):
    live = _copy(tmp_path)
    monkeypatch.setattr(rr, "LIVE_DB", live)
    assert rr.main(["--db", str(live), "טופין"]) == 2
    assert "refusing the live corpus" in capsys.readouterr().out


def test_listing_covers_every_implies_team_person(capsys):
    assert rr.main([]) == 0
    out = capsys.readouterr().out
    assert "player:jacob_toppin" in out and "coach:dimitris_itoudis" in out
    assert rr.ROSTER_PAGES["team:maccabi_tlv_bb"] in out
