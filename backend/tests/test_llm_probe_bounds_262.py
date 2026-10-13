"""Bounded evaluation tooling (#262): scripts/llm_failure_probe.py.

A temp SQLite corpus and a stub provider only. The script is loaded with
load_dotenv stubbed, so no developer .env can leak into the test process.
"""

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from app.classification.llm_result import LLMClassificationResult

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "llm_failure_probe.py"
IDS = [f"rss_walla_{i:03d}" for i in range(5)]


@pytest.fixture
def probe(monkeypatch):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location("llm_failure_probe_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "corpus.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE articles (id TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, "
                 "translated_title TEXT, subtitle TEXT)")
    for i, article_id in enumerate(IDS):
        conn.execute("INSERT INTO articles VALUES (?, 'walla_sport', ?, ?, NULL, NULL)",
                     (article_id, f"https://sports.walla.co.il/item/{i}", f"כותרת ספורט מספר {i}"))
    conn.execute("INSERT INTO articles VALUES ('rss_eurohoops_1', 'eurohoops', 'https://e/1', "
                 "'Not eligible', NULL, NULL)")
    conn.commit()
    conn.close()
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _StubProvider:
    can_classify = True
    provider_id = "stub:test"
    last_failure_reason = "none"
    last_raw_content = None

    def __init__(self):
        self.calls = 0
        self.last_call_latency_ms = None
        self.last_usage = None

    def classify_title(self, title, language, subtitle=None):
        self.calls += 1
        self.last_call_latency_ms = 12.0
        self.last_usage = {"prompt_tokens": 1000, "completion_tokens": 100, "reasoning_tokens": 30}
        return LLMClassificationResult(
            sport="basketball", league=None, entities=[], event_type="news",
            importance="medium", confidence=0.9, reason="stub",
        )


def test_dry_run_builds_no_provider_and_sends_nothing(probe, corpus, monkeypatch):
    def _forbidden():
        raise AssertionError("dry run must not build a provider")

    monkeypatch.setattr(probe, "get_llm_provider", _forbidden)
    monkeypatch.setenv("CLASSIFICATION_API_KEY", "sk-should-not-appear")
    before = _digest(corpus)
    report = probe.run_probe(corpus, limit=60, max_calls=3, dry_run=True,
                             price_in_per_m=0.075, price_out_per_m=0.30)
    assert report["mode"] == "dry_run"
    assert report["requests_sent"] == 0
    assert report["bounds"] == {"max_calls": 3, "calls_planned": 3, "cut_by_max_calls": True,
                                "ids_requested": None, "ids_found_eligible": None}
    assert report["sample_ids"] == IDS[:3]
    est = report["estimate"]
    assert est["input_tokens"] == 3 * probe.ASSUMED_PROMPT_TOKENS
    assert est["estimated_cost_usd"] == pytest.approx(3 * 1200 / 1e6 * 0.075 + 3 * 150 / 1e6 * 0.30)
    assert report["provider_settings"]["api_key_set"] is True
    assert "sk-should-not-appear" not in json.dumps(report)
    assert _digest(corpus) == before


def test_max_calls_is_a_hard_ceiling(probe, corpus, monkeypatch):
    stub = _StubProvider()
    monkeypatch.setattr(probe, "get_llm_provider", lambda: stub)
    before = _digest(corpus)
    report = probe.run_probe(corpus, limit=60, max_calls=2,
                             price_in_per_m=0.10, price_out_per_m=0.40)
    assert stub.calls == 2
    assert report["requests_sent"] == 2
    assert report["bounds"]["cut_by_max_calls"] is True
    assert report["mode"] == "offline"          # a stub is never reported as live
    assert report["usage"]["prompt_tokens"] == 2000
    assert report["usage"]["completion_tokens"] == 200
    assert report["usage"]["measured_cost_usd"] == pytest.approx(2000 / 1e6 * 0.10 + 200 / 1e6 * 0.40)
    assert _digest(corpus) == before


def test_networked_provider_is_reported_live(probe, corpus, monkeypatch):
    stub = _StubProvider()
    stub.provider_id = "openai_compat:some-model"
    monkeypatch.setattr(probe, "get_llm_provider", lambda: stub)
    assert probe.run_probe(corpus, limit=1, max_calls=1)["mode"] == "live"


def test_ids_file_restricts_the_sample(probe, corpus, monkeypatch, tmp_path):
    census = {"meta": {}, "profiles": {"guy": {"items": [{"id": IDS[4]}, {"id": IDS[1]}, {"id": "rss_missing"}]}}}
    ids_path = tmp_path / "ids.json"
    ids_path.write_text(json.dumps(census), encoding="utf-8")
    ids = probe.load_ids(ids_path)
    assert ids == [IDS[4], IDS[1], "rss_missing"]
    stub = _StubProvider()
    monkeypatch.setattr(probe, "get_llm_provider", lambda: stub)
    report = probe.run_probe(corpus, limit=60, max_calls=30, ids=ids)
    assert report["sample_ids"] == [IDS[1], IDS[4]]          # id order, eligible only
    assert report["bounds"]["ids_requested"] == 3
    assert report["bounds"]["ids_found_eligible"] == 2
    assert report["bounds"]["cut_by_max_calls"] is False


def test_plain_id_list_format(probe, tmp_path):
    path = tmp_path / "ids.json"
    path.write_text(json.dumps([IDS[0], {"id": IDS[2]}, IDS[0]]), encoding="utf-8")
    assert probe.load_ids(path) == [IDS[0], IDS[2]]


@pytest.mark.parametrize("bad", [0, -1, 501])
def test_max_calls_bounds(probe, corpus, bad):
    with pytest.raises(ValueError):
        probe.run_probe(corpus, limit=10, max_calls=bad, dry_run=True)
