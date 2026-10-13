"""Hosted-LLM bake-off harness (#262): scripts/llm_bakeoff.py.

Offline only: a fixture corpus with the real ORM schema and the seed "guy"
profile, fake providers, injected sleep. No network, no real corpus.
"""

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.orm_models import Base

BACKEND = Path(__file__).resolve().parents[1]

# Hebrew titles; the first ones are the LLM-regression headlines the gate sends on.
TITLES = [
    "סיכום בהפועל תל אביב? בירושלים לא שחררו את ג'ארד הארפר",
    "אולימפיאקוס נקצה, ינאקופולוס עצבני אחרי הסערה הגדולה ביוון",
    "ערב היסטורי לברונסון ולניקס: ניו יורק אלופת ה-NBA!",
    "מכבי תל אביב החתימה גארד חדש מהיורוליג",
    "דני אבדיה נפצע במשחק של פורטלנד",
    "מכבי חיפה ניצחה 2:0 בליגת העל בכדורגל",
]
RATINGS = ["feed", "low", "high", "push", "high", "hide"]
VALID = {"sport": "basketball", "league": "EuroLeague", "entities": ["Maccabi Tel Aviv Basketball"],
         "event_type": "news", "importance": "medium", "confidence": 0.9, "reason": "fake"}


@pytest.fixture
def bake():
    spec = importlib.util.spec_from_file_location("llm_bakeoff_under_test", BACKEND / "scripts" / "llm_bakeoff.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def corpus(tmp_path):
    from app.repositories import profile_repository
    from app.seed.seed_profiles import SEED_PROFILES

    db = tmp_path / "corpus.db"
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    profile_repository.insert(session, next(p for p in SEED_PROFILES if p.user_id == "guy"))
    session.close()
    engine.dispose()
    conn = sqlite3.connect(db)
    ids = []
    for i, title in enumerate(TITLES):
        article_id = f"rss_walla_{i:03d}"
        ids.append(article_id)
        conn.execute(
            "INSERT INTO articles (id, source, source_display_name, url, title, language, published_at, "
            "sport, entities, event_type, importance, confidence, tags, classified_by) "
            "VALUES (?, 'walla_sport', 'וואלה', ?, ?, 'he', '2026-10-01T10:00:00+00:00', 'basketball', "
            "'[]', 'news', 'medium', 0.8, '[]', 'llm')",
            (article_id, f"https://sports.walla.co.il/item/{i}", title))
    conn.commit()
    conn.close()
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps({"profiles": {"guy": {"items": [{"id": i, "title": t} for i, t in zip(ids, TITLES)]}}},
                                 ensure_ascii=False), encoding="utf-8")
    ratings = tmp_path / "ratings.json"
    ratings.write_text(json.dumps({"ratings": {"guy": dict(zip(ids, RATINGS))}}), encoding="utf-8")
    return db, sample, ratings


class FakeInner:
    """A provider that answers every title with a valid classification."""

    provider_id = "fake:test"

    def __init__(self, answers=None, statuses=None):
        self.calls = 0
        self.answers = answers
        self.statuses = list(statuses or [])
        self.paused_checks = 0
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms = None
        self.last_raw_content = None
        self.last_usage = None
        self.last_finish_reason = None
        self.last_http_status = None

    def rate_limit_paused(self):
        self.paused_checks += 1
        return self.paused_checks < 2

    def classify_title(self, title, language, subtitle=None):
        from app.classification.validation import parse_and_validate_llm_json

        self.calls += 1
        self.last_http_status = self.statuses.pop(0) if self.statuses else 200
        self.last_call_latency_ms = 120.0
        if self.last_http_status == 429:
            self.last_failure_reason = "http_error"
            self.last_raw_content = None
            return None
        self.last_failure_reason = "none"
        self.last_raw_content = json.dumps(VALID)
        self.last_usage = {"prompt_tokens": 1200, "completion_tokens": 150, "reasoning_tokens": 60,
                           "cached_prompt_tokens": 1000}
        self.last_finish_reason = "stop"
        return parse_and_validate_llm_json(self.last_raw_content)


def _fake_candidate(bake, name="fake-a"):
    return bake.Candidate(name, "fake", "fake-model", "FAKE_KEY", price_in=0.1, price_cached_in=0.05,
                          price_out=0.4, min_interval_s=0.0)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(bake, corpus, tmp_path, **kwargs):
    db, sample, ratings = corpus
    defaults = dict(db_path=db, sample_path=sample, ratings_path=ratings, review_path=None,
                    stage="accuracy", max_calls=30, live=True, cache_dir=tmp_path / "cache",
                    sleep=lambda s: None)
    defaults.update(kwargs)
    return bake.run_bakeoff(**defaults)


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_is_complete_and_honest(bake):
    names = set(bake.CANDIDATES)
    assert {"groq-gpt-oss-20b", "groq-gpt-oss-120b", "gemini-3.1-flash-lite", "openai-gpt-5-nano"} <= names
    for c in bake.CANDIDATES.values():
        assert c.kind in ("openai_compat", "gemini")
        assert c.price_in > 0 and c.price_out > 0 and c.key_env
        if c.kind == "openai_compat":
            assert c.base_url.startswith("https://")
            assert c.response_format == "json_schema"
    nano = bake.CANDIDATES["openai-gpt-5-nano"]
    assert nano.token_limit_param == "max_completion_tokens" and nano.send_temperature is False
    assert bake.CANDIDATES["groq-gpt-oss-20b"].price_in < bake.CANDIDATES["groq-gpt-oss-120b"].price_in


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_metrics_on_a_toy_case(bake):
    truth = {"a": "push", "b": "feed", "c": "hidden", "d": "high_feed"}
    dec = {"a": "push", "b": "hidden", "c": "push", "d": "high_feed"}
    m = bake.metrics(dec, truth, list(truth))
    assert m["exact"] == 2 and m["rated"] == 4
    assert m["shown"] == 3 and m["shown_precision"] == round(2 / 3, 4)
    assert m["wanted"] == 3 and m["feed_plus_recall"] == round(2 / 3, 4)
    assert m["pushes"] == 2 and m["push_precision"] == 0.5 and m["wrong_pushes"] == ["c"]
    assert m["false_hides_of_wanted"] == ["b"]


def test_verdict_rules(bake):
    stats = {"validation_failure_rate": 0.0, "truncated": 0, "latency_ms": {"p95": 900.0}}
    assert bake.verdict("smoke", {}, {}, stats)["passes"]
    assert not bake.verdict("smoke", {}, {}, {**stats, "truncated": 1})["passes"]
    base = {"feed_plus_recall": 0.70, "shown_precision": 0.90, "wrong_pushes": ["x"]}
    good = {"feed_plus_recall": 0.68, "shown_precision": 0.91, "wrong_pushes": ["x"]}
    assert bake.verdict("accuracy", good, base, stats)["passes"]
    assert not bake.verdict("accuracy", {**good, "wrong_pushes": ["x", "y"]}, base, stats)["passes"]
    assert not bake.verdict("accuracy", {**good, "feed_plus_recall": 0.66}, base, stats)["passes"]
    assert not bake.verdict("accuracy", good, base, {**stats, "validation_failure_rate": 0.05})["passes"]


# ── Runs ──────────────────────────────────────────────────────────────────────

def test_dry_run_calls_nothing_and_never_writes(bake, corpus, tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("a dry run must not build a provider")

    monkeypatch.setattr(bake, "build_provider", forbidden)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-should-not-appear")
    before = _sha(corpus[0])
    report = _run(bake, corpus, tmp_path, live=False, candidates=[bake.CANDIDATES["groq-gpt-oss-20b"]])
    assert report["meta"]["mode"] == "dry_run"
    plan = report["candidates"]["groq-gpt-oss-20b"]
    assert plan["key_present"] is True and plan["planned_calls"] == report["meta"]["selected_llm_rows"]
    assert "gsk-should-not-appear" not in json.dumps(report, ensure_ascii=False)
    assert report["baselines"]["stored_facts"]["all_rows"]["rated"] == len(TITLES)
    assert _sha(corpus[0]) == before
    assert not (tmp_path / "cache").exists()


def test_offline_run_scores_against_the_ratings(bake, corpus, tmp_path):
    inner = FakeInner()
    cand = _fake_candidate(bake)
    before = _sha(corpus[0])
    report = _run(bake, corpus, tmp_path, candidates=[cand], provider_factory=lambda c: inner)
    meta = report["meta"]
    assert meta["mode"] == "offline"            # a fake is never reported as live
    assert meta["llm_eligible_rows"] >= 1
    res = report["candidates"]["fake-a"]
    assert inner.calls == meta["selected_llm_rows"] == res["llm"]["live_calls"]
    assert res["llm"]["validation_failure_rate"] == 0.0
    assert res["llm"]["tokens"]["cached_prompt"] == 1000 * inner.calls
    assert res["llm_rows"]["rated"] == meta["selected_llm_rows"]
    assert res["all_rows"]["rated"] == meta["evaluated_rows"]
    assert "passes" in res["verdict"] and "recommended" in report["ranking"]
    assert _sha(corpus[0]) == before


def test_cache_replays_without_calling_again(bake, corpus, tmp_path):
    cand = _fake_candidate(bake)
    first = FakeInner()
    _run(bake, corpus, tmp_path, candidates=[cand], provider_factory=lambda c: first)
    second = FakeInner()
    report = _run(bake, corpus, tmp_path, candidates=[cand], provider_factory=lambda c: second)
    assert first.calls >= 1 and second.calls == 0
    llm = report["candidates"]["fake-a"]["llm"]
    assert llm["live_calls"] == 0 and llm["from_cache"] == first.calls


def test_budget_selects_the_same_first_rows_for_everyone(bake, corpus, tmp_path):
    a, b = FakeInner(), FakeInner()
    inners = {"fake-a": a, "fake-b": b}
    report = _run(bake, corpus, tmp_path, max_calls=1, cache_dir=None,
                  candidates=[_fake_candidate(bake, "fake-a"), _fake_candidate(bake, "fake-b")],
                  provider_factory=lambda c: inners[c.name])
    assert report["meta"]["selected_llm_rows"] == 1
    assert a.calls == 1 and b.calls == 1


def test_a_429_waits_and_retries_once(bake, corpus, tmp_path):
    inner = FakeInner(statuses=[429])
    report = _run(bake, corpus, tmp_path, cache_dir=None, candidates=[_fake_candidate(bake)],
                  provider_factory=lambda c: inner)
    llm = report["candidates"]["fake-a"]["llm"]
    assert llm["rate_limited_retries"] == 1
    assert llm["live_calls"] == inner.calls == report["meta"]["selected_llm_rows"] + 1


def test_persistent_429_stops_the_candidate(bake, corpus, tmp_path):
    inner = FakeInner(statuses=[429, 429])
    report = _run(bake, corpus, tmp_path, cache_dir=None, candidates=[_fake_candidate(bake)],
                  provider_factory=lambda c: inner)
    assert "still rate-limited" in report["candidates"]["fake-a"]["stopped"]


@pytest.mark.parametrize("max_calls,n", [(0, 1), (501, 1), (300, 4)])
def test_call_ceilings(bake, corpus, tmp_path, max_calls, n):
    with pytest.raises(ValueError):
        _run(bake, corpus, tmp_path, max_calls=max_calls,
             candidates=[_fake_candidate(bake, f"f{i}") for i in range(n)])


def test_missing_key_skips_a_live_candidate(bake, corpus, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = _run(bake, corpus, tmp_path, candidates=[bake.CANDIDATES["openai-gpt-5-nano"]])
    assert report["candidates"]["openai-gpt-5-nano"] == {"skipped": "OPENAI_API_KEY is not set"}


def test_cli_lists_and_requires_a_candidate(bake, capsys):
    assert bake.main(["--list-candidates"]) == 0
    assert "groq-gpt-oss-20b" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        bake.main([])
