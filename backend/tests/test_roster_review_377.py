"""scripts/roster_review.py (#377): the read-only roster review aid."""

import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "roster_review", Path(__file__).resolve().parents[1] / "scripts" / "roster_review.py"
)
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)


def _copy(tmp_path: Path, name: str = "copy.db") -> Path:
    db = tmp_path / name
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE articles (id TEXT, published_at TEXT, source TEXT, "
                "title TEXT, subtitle TEXT)")
    con.executemany("INSERT INTO articles VALUES (?, ?, ?, ?, ?)", [
        ("a1", "2026-10-01T10:00:00", "walla_sport", "פגישה על הפרק: מו\"מ הפועל וג`ייקוב טופין", None),
        ("a2", "2026-10-02T10:00:00", "ynet_sport", "הפועל ניצחה", "ג'ייקוב טופין קלע 20"),
        ("held", "2026-10-03T10:00:00", "one_sport", "ג'ייקוב טופין חתם", ""),
        ("a3", "2026-10-04T10:00:00", "ynet_sport", "ריאל מדריד ניצחה", ""),
        ("a4", "2026-10-05T10:00:00", "walla_sport", "המדריך של העונה", "ים מדר קלע 20"),
        ("a5", "2026-10-06T10:00:00", "walla_sport", "שבחים למדר אחרי הניצחון", ""),
        ("a6", "2026-10-07T10:00:00", "ynet_sport", "טי-ג'יי ליף חזר לסגל", ""),
    ])
    con.commit()
    con.close()
    return db


def _titles(rows):
    return [r[2] for r in rows]


def test_mentions_match_every_geresh_spelling_and_skip_the_holdout(tmp_path):
    rows, raw = rr.find_mentions(_copy(tmp_path), "ג'ייקוב טופין", skip_ids={"held"})
    assert _titles(rows) == ['פגישה על הפרק: מו"מ הפועל וג`ייקוב טופין', "הפועל ניצחה"]
    assert raw == 2


def test_a_hit_inside_a_longer_word_is_not_a_mention(tmp_path):
    # The resolver matches club-people aliases only as standalone words (#229/#259):
    # "מדריד" and "המדריך" are not the surname "מדר"; "ים מדר" and "למדר" are.
    rows, raw = rr.find_mentions(_copy(tmp_path), "מדר", skip_ids=set())
    assert _titles(rows) == ["המדריך של העונה", "שבחים למדר אחרי הניצחון"]  # a4 via its subtitle
    assert raw == 3  # a3 (מדריד) counts only as a raw substring


def test_hyphenated_text_matches_a_spaced_name(tmp_path):
    rows, _raw = rr.find_mentions(_copy(tmp_path), "טי ג'יי ליף", skip_ids=set())
    assert _titles(rows) == ["טי-ג'יי ליף חזר לסגל"]


def test_holdout_ids_are_the_week_sample_test_split():
    assert len(rr.holdout_ids()) == 35


def test_a_missing_week_sample_means_no_holdout(tmp_path):
    assert rr.holdout_ids(tmp_path / "retired.json") == set()


def test_refuses_the_live_corpus_file(monkeypatch, tmp_path, capsys):
    live = _copy(tmp_path)
    monkeypatch.setattr(rr, "LIVE_DB", live)
    assert rr.main(["--db", str(live), "טופין"]) == 2
    assert "refusing" in capsys.readouterr().out


def test_refuses_the_live_file_name_from_another_checkout(tmp_path, capsys):
    other = _copy(tmp_path, "signal_sports.db")
    assert rr.main(["--db", str(other), "טופין"]) == 2
    assert "refusing" in capsys.readouterr().out


def test_refuses_a_database_with_wal_sidecars(tmp_path, capsys):
    db = _copy(tmp_path, "renamed.db")
    (tmp_path / "renamed.db-wal").write_bytes(b"")
    assert rr.main(["--db", str(db), "טופין"]) == 2
    assert "refusing" in capsys.readouterr().out


def test_a_search_leaves_the_copy_unchanged(tmp_path, capsys):
    db = _copy(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    assert rr.main(["--db", str(db), "מדר"]) == 0
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["copy.db"]
    assert "מדר: 2 mention(s)" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["טופין"], ["--db", "x.db"]], ids=["names_without_db", "db_without_names"])
def test_argument_errors(argv):
    with pytest.raises(SystemExit) as exc:
        rr.main(argv)
    assert exc.value.code == 2


def test_listing_covers_every_implies_team_person(capsys):
    assert rr.main([]) == 0
    out = capsys.readouterr().out
    assert "player:jacob_toppin" in out and "coach:dimitris_itoudis" in out
    assert rr.ROSTER_PAGES["team:maccabi_tlv_bb"] in out
