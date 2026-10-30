"""The read-only ONE Sport probe (scripts/one_sport_probe.py, #258).

Fake HTTP and a throwaway SQLite file only: no test fetches ONE, and the probe
must never write to the database it reads.
"""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 30, 4, 0, tzinfo=timezone.utc)
API = "https://api.one.co.il/JSON/v6/Articles/Category/"


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("one_sport_probe_under_test",
                                                  BACKEND / "scripts" / "one_sport_probe.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _item(article_id, title, *, local_date="2026-10-30T05:00:00", video=False, url=None, subtitle="תקציר"):
    url = url or f"https://www.one.co.il/Article/{article_id}.html"
    return {"IsVideo": video, "Date": local_date, "ID": article_id,
            "Title": {"Main": title, "Secondary": subtitle, "External": title},
            "URL": {"PC": url, "Mobile": url}}


def _payload(*items):
    return {"Version": 6, "Data": {"Articles": {"Title": "x", "Items": list(items)}}}


# Category 2 (Israeli basketball) and 5 (world basketball) share one story, as the
# real lists do; category 1 holds a video and an item with an unparseable date.
PAYLOADS = {
    "1": _payload(_item(101, "בית\"ר ניצחה בדרבי"), _item(102, "וידאו", video=True),
                  _item(103, "ללא תאריך", local_date="not a date")),
    "2": _payload(_item(201, "הפועל העמק בדרך למינוי מאמן"), _item(200, "קטש: לא מספיק טובים")),
    "3": _payload(_item(301, "ברצלונה יוצאת למבצע", url="https://www.one.co.il/Article/26-27/3,10,135,0/301.html")),
    "5": _payload(_item(200, "קטש: לא מספיק טובים"), _item(501, "שארפ ללא נקודות")),
    "7": _payload(),
    "155": _payload(_item(1551, "ליגה א'", local_date="2026-10-28T06:00:00")),
}


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.headers = {"content-type": "application/json; charset=utf-8"}
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class _Calls(list):
    """The requests made, plus per-category overrides: category -> (payload, status)."""

    def __init__(self):
        super().__init__()
        self.overrides = {}


@pytest.fixture
def fake_one(monkeypatch):
    calls = _Calls()

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        category = url.rsplit("/", 1)[-1]
        if category in calls.overrides:
            payload, status = calls.overrides[category]
            return _FakeResponse(payload, status=status)
        if category == "7":
            # An error body that still carries an item: fetch() discards it, so must the report.
            return _FakeResponse(_payload(_item(701, "גוף של שגיאה")), status=503)
        return _FakeResponse(PAYLOADS[category])

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


def test_recorded_fetch_uses_the_real_adapter_once_per_endpoint(probe, fake_one):
    cfg = probe.get_source_config("one_sport")
    items, exchanges = probe.recorded_fetch(cfg)

    assert [url for url, _ in fake_one] == list(cfg.category_urls)
    assert all(k["headers"]["User-Agent"].startswith("SignalSports/") for _, k in fake_one)
    assert [e.http_status for e in exchanges] == [200, 200, 200, 200, 503, 200]
    # The adapter's own dedup and video skip: 101, 103, 201, 200, 301, 501, 1551.
    assert len(items) == 7 and len({i.url for i in items}) == 7


def test_endpoint_report_counts_what_the_parser_drops(probe, fake_one):
    _, exchanges = probe.recorded_fetch(probe.get_source_config("one_sport"))
    cat1 = probe.endpoint_report(exchanges[0], NOW)
    assert (cat1.raw_items, cat1.parsed_items, cat1.skipped_video, cat1.missing_date) == (3, 2, 1, 1)
    assert cat1.hebrew_titles == 2 and cat1.samples[0]["title"] == "בית\"ר ניצחה בדרבי"
    cat155 = probe.endpoint_report(exchanges[5], NOW)
    # 2026-10-28 06:00 Israel time is UTC+2 (DST ended 10-25): 48 h before NOW, one item.
    assert cat155.oldest_age_hours == 48.0 and cat155.per_day_rate == 0.5
    down = probe.endpoint_report(exchanges[4], NOW)
    assert down.http_status == 503
    assert (down.raw_items, down.parsed_items, down.samples) == (0, 0, [])


def test_error_bodies_never_reach_the_fetch_numbers(probe, fake_one):
    cfg = probe.get_source_config("one_sport")
    items, exchanges = probe.recorded_fetch(cfg)
    assert "https://www.one.co.il/Article/701.html" not in {i.url for i in items}
    assert "https://www.one.co.il/Article/701.html" not in probe.first_endpoint_by_url(exchanges)
    assert probe.build_report(cfg, items, exchanges, NOW)["fetch"]["cross_endpoint_duplicates"] == 1


@pytest.mark.parametrize("payload", [{"Data": None}, {"Data": {"Articles": []}}, ["not", "a", "dict"]])
def test_a_changed_json_shape_is_reported_not_raised(probe, fake_one, payload):
    fake_one.overrides["1"] = (payload, 200)
    cfg = probe.get_source_config("one_sport")
    items, exchanges = probe.recorded_fetch(cfg)
    report = probe.build_report(cfg, items, exchanges, NOW)
    cat1 = report["endpoints"][0]
    assert cat1["http_status"] == 200 and cat1["parsed_items"] == 0
    assert cat1["error"] and ("shape" in cat1["error"] or "parse" in cat1["error"])
    assert probe.healthy(report) is False
    assert report["fetch"]["items"] == 5   # the other endpoints still count: 201 200 301 501 1551


def test_build_report_basketball_share_hints_and_health(probe, fake_one):
    cfg = probe.get_source_config("one_sport")
    items, exchanges = probe.recorded_fetch(cfg)
    report = probe.build_report(cfg, items, exchanges, NOW)
    fetch = report["fetch"]
    assert fetch["basketball_by_endpoint"] == 3          # 201, 200 (first seen in cat 2), 501
    assert fetch["cross_endpoint_duplicates"] == 1
    assert fetch["url_shapes"] == {"article_generic": 7 - 1, "article_with_category": 1}
    assert fetch["url_sport_hint"] == {"none": 6, "football": 1}
    assert report["gate"]["items"] == 7
    assert sum(report["gate"]["gate_reasons"].values()) == 7
    assert probe.healthy(report) is False                 # category 7 answered 503


def _corpus(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE articles (id TEXT, source TEXT, url TEXT, title TEXT, published_at TEXT);
        CREATE TABLE source_overrides (source_id TEXT, enabled BOOLEAN);
        CREATE TABLE ingestion_runs (source_id TEXT, started_at TEXT, metrics TEXT);
    """)
    conn.execute("INSERT INTO source_overrides VALUES ('one_sport', 0)")
    conn.execute("INSERT INTO articles VALUES ('a', 'walla_sport', ?, ?, ?)",
                 ("https://www.one.co.il/Article/101.html", "x", NOW.isoformat()))
    conn.execute("INSERT INTO articles VALUES ('b', 'walla_sport', 'https://w/1', ?, ?)",
                 ("הפועל העמק בדרך למינוי של מאמן חדש", (NOW - timedelta(hours=3)).isoformat()))
    conn.execute("INSERT INTO ingestion_runs VALUES ('walla_sport', ?, ?)",
                 ((NOW - timedelta(hours=1)).isoformat(),
                  json.dumps({"new_articles": 10, "llm_attempts": 4, "llm_avg_ms": 1500})))
    conn.commit()
    conn.close()


def test_corpus_report_reads_a_copy_without_writing(probe, fake_one, tmp_path):
    db = tmp_path / "copy.db"
    _corpus(db)
    before = db.read_bytes()
    cfg = probe.get_source_config("one_sport")
    items, exchanges = probe.recorded_fetch(cfg)

    conn = probe.open_readonly(db)
    try:
        report = probe.build_report(cfg, items, exchanges, NOW, conn)["corpus"]
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM source_overrides")
    finally:
        conn.close()

    assert db.read_bytes() == before
    assert report["already_in_corpus_by_url"] == 1 and report["would_be_new"] == 6
    assert report["source_overrides"] == {"one_sport": False}
    assert report["last_one_ingestion_run"] is None
    overlap = report["cross_source_overlap"]
    # Only items published before the corpus's last run are comparable; the Emek story matches.
    assert overlap["with_likely_match"] == 1 and overlap["best_match_source"] == {"walla_sport": 1}
    # The window ends at the copy's last run (NOW - 1 h), not at NOW.
    assert report["hebrew_sources_last_7d"] == {
        "new_articles": 10, "window_days": 6.96, "new_articles_per_day": 1,
        "llm_attempts": 4, "llm_call_rate": 0.4, "llm_avg_ms": 1500}


def _no_network(monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("replay must not fetch")

    monkeypatch.setattr(httpx, "get", no_network)


def _run_main(probe, capsys, argv):
    code = probe.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_save_raw_then_replay_needs_no_network(probe, fake_one, tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    fake_one.overrides["7"] = (_payload(), 200)
    code, live = _run_main(probe, capsys, ["--save-raw", str(raw), "--json"])
    assert code == 0
    _no_network(monkeypatch)
    code, replay = _run_main(probe, capsys, ["--replay", str(raw), "--now", NOW.isoformat(), "--json"])
    assert code == 0
    assert replay["probed_at"] == NOW.isoformat()
    assert replay["fetch"]["items"] == live["fetch"]["items"] == 7


def test_a_failed_endpoint_stays_failed_on_replay(probe, fake_one, tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    code, live = _run_main(probe, capsys, ["--save-raw", str(raw), "--json"])
    assert code == 1                                      # category 7 answered 503
    assert not (raw / "one_category_7.json").exists()     # its error body was not saved
    _no_network(monkeypatch)
    code, replay = _run_main(probe, capsys, ["--replay", str(raw), "--now", NOW.isoformat(), "--json"])
    assert code == 1
    cat7 = replay["endpoints"][4]
    assert cat7["http_status"] is None and "no saved response" in cat7["error"]


def test_a_saved_non_object_replays_as_an_error(probe, tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    for category, payload in PAYLOADS.items():
        (raw / f"one_category_{category}.json").write_text(json.dumps(payload), encoding="utf-8")
    (raw / "one_category_7.json").write_text("null", encoding="utf-8")
    _no_network(monkeypatch)
    code, replay = _run_main(probe, capsys, ["--replay", str(raw), "--now", NOW.isoformat(), "--json"])
    assert code == 1 and replay["endpoints"][4]["error"]


@pytest.mark.parametrize("mode", [["--json"], []])
def test_piped_output_is_utf8_even_when_the_console_codec_is_not(tmp_path, mode):
    """The docstring's `--json > file` on Windows: a redirected stdout gets the ANSI
    codepage (cp1252), which cannot encode Hebrew. The probe must write UTF-8 anyway."""
    raw = tmp_path / "raw"
    raw.mkdir()
    for category, payload in PAYLOADS.items():
        (raw / f"one_category_{category}.json").write_text(json.dumps(payload), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp1252"
    proc = subprocess.run(
        [sys.executable, "scripts/one_sport_probe.py", "--replay", str(raw), "--now", NOW.isoformat(), *mode],
        cwd=BACKEND, env=env, capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    assert "בית\"ר ניצחה בדרבי" in out or "בית\\\"ר ניצחה בדרבי" in out


def test_missing_db_is_refused(probe, tmp_path):
    with pytest.raises(SystemExit):
        probe.open_readonly(tmp_path / "absent.db")
    assert not (tmp_path / "absent.db").exists()


def test_probe_never_imports_the_database_module():
    code = ("import importlib.util, sys; "
            "spec = importlib.util.spec_from_file_location('p', 'scripts/one_sport_probe.py'); "
            "m = importlib.util.module_from_spec(spec); sys.modules['p'] = m; spec.loader.exec_module(m); "
            "print('app.db.database' in sys.modules, 'sqlalchemy' in sys.modules)")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False False"
