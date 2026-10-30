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


@pytest.fixture
def fake_one(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        category = url.rsplit("/", 1)[-1]
        if category == "7":
            return _FakeResponse({"error": "down"}, status=503)
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
    assert down.http_status == 503 and down.parsed_items == 0


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
    assert report["hebrew_sources_last_7d"] == {
        "new_articles": 10, "llm_attempts": 4, "llm_call_rate": 0.4, "llm_avg_ms": 1500}


def test_save_raw_then_replay_needs_no_network(probe, fake_one, tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    assert probe.main(["--save-raw", str(raw), "--json"]) == 1   # category 7 is down
    capsys.readouterr()
    (raw / "one_category_7.json").write_text(json.dumps(_payload()), encoding="utf-8")

    def no_network(*a, **k):
        raise AssertionError("replay must not fetch")

    monkeypatch.setattr(httpx, "get", no_network)
    assert probe.main(["--replay", str(raw), "--now", NOW.isoformat(), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["fetch"]["items"] == 7 and report["probed_at"] == NOW.isoformat()


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
