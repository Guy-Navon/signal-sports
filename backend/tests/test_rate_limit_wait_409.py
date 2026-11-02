"""#409 — wait out a short provider rate limit instead of falling back to rules.

Census #3 found 10.8% of the fresh cohort classified rules-only after an LLM
failure. On the current provider (Groq, openai_compat) every failure but one was
a 429 burst on a backlog cycle: one 429 paused the provider for Retry-After
seconds (2-11 s observed), and every article in that window fell back at once,
without a request. Most of those rows end with sport=unknown and are hidden.

The opt-in fix (CLASSIFICATION_RATE_LIMIT_MAX_WAIT_SECONDS, default 0 = the old
behavior): when the pause is short enough and the per-run wait budget allows,
sleep through it and send (a 429 response is retried once). Mocked HTTP and a
fake clock only; nothing reaches a network.
"""
import json
import time
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import text

from app.classification import providers
from app.classification.providers import OpenAICompatibleProvider

BASE = "https://llm.example.test/openai/v1"
KEY = "sk-test-SECRET-never-logged"
MODEL = "openai/gpt-oss-20b"
VALID = {
    "sport": "basketball", "league": "EuroLeague",
    "entities": ["Maccabi Tel Aviv Basketball"], "event_type": "signing",
    "importance": "high", "confidence": 0.93, "reason": "Maccabi signing.",
}


def _response(status=200, body=None, headers=None) -> httpx.Response:
    request = httpx.Request("POST", f"{BASE}/chat/completions")
    return httpx.Response(status, json=body, headers=headers, request=request)


def _ok():
    return _response(body={"choices": [{"index": 0, "finish_reason": "stop",
                                        "message": {"role": "assistant", "content": json.dumps(VALID)}}]})


def _429(retry_after):
    return _response(status=429, body={}, headers={"retry-after": str(retry_after)})


class _Post:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        return self.outcomes.pop(0)


@pytest.fixture
def clock(monkeypatch):
    """A fake monotonic clock; time.sleep advances it and records each sleep."""
    state = {"now": 1000.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(providers.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(providers.time, "sleep", sleep)
    return state


def _provider(**kwargs):
    return OpenAICompatibleProvider(base_url=BASE, api_key=KEY, model=MODEL, timeout=15.0, **kwargs)


# ── Default: exactly the old behavior ────────────────────────────────────────

def test_default_never_waits(monkeypatch, clock):
    post = _Post(_429(2), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = _provider()

    assert p.classify_title("a", "he") is None          # the 429 article falls back
    assert p.classify_title("b", "he") is None          # paused: falls back without a request
    assert post.calls == 1
    assert clock["sleeps"] == []
    assert p.last_rate_limit_wait_ms == 0.0


# ── Opt-in wait ──────────────────────────────────────────────────────────────

def test_429_response_is_waited_out_and_retried_once(monkeypatch, clock):
    post = _Post(_429(9), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = _provider(rate_limit_max_wait_seconds=15)

    result = p.classify_title("a", "he")

    assert result is not None and result.sport == "basketball"
    assert post.calls == 2
    assert clock["sleeps"] == [pytest.approx(9.0)]
    assert p.last_rate_limit_wait_ms == pytest.approx(9000.0)
    assert p.last_failure_reason == "none"


def test_paused_call_waits_then_sends(monkeypatch, clock):
    # The retry of article a is rate-limited again: a falls back, the pause stands.
    post = _Post(_429(2), _429(5), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = _provider(rate_limit_max_wait_seconds=15)

    assert p.classify_title("a", "he") is None
    assert p.last_failure_reason == "http_error" and p.last_http_status == 429
    assert post.calls == 2                              # one retry, never a third request

    assert p.classify_title("b", "he") is not None      # waits out the 5 s pause, then sends
    assert post.calls == 3
    assert clock["sleeps"] == [pytest.approx(2.0), pytest.approx(5.0)]
    assert p.last_rate_limit_wait_ms == pytest.approx(5000.0)


def test_pause_longer_than_the_cap_fails_fast(monkeypatch, clock):
    post = _Post(_429(60), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = _provider(rate_limit_max_wait_seconds=15)

    assert p.classify_title("a", "he") is None          # no wait for a 60 s pause
    assert p.classify_title("b", "he") is None          # still paused: no request
    assert post.calls == 1
    assert clock["sleeps"] == []


def test_wait_budget_bounds_the_run_and_reset_restores_it(monkeypatch, clock):
    post = _Post(_429(8), _ok(), _429(8), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = _provider(rate_limit_max_wait_seconds=15, rate_limit_wait_budget_seconds=10)

    assert p.classify_title("a", "he") is not None      # waits 8 of the 10 s budget
    clock["now"] += 100                                 # pause long over
    assert p.classify_title("b", "he") is None          # 429 again: 8 s > 2 s left
    assert post.calls == 3

    p.reset_rate_limit_wait_budget()                    # the next ingestion run
    assert p.classify_title("c", "he") is not None      # waits out the rest of the pause
    assert post.calls == 4
    assert sum(clock["sleeps"]) == pytest.approx(16.0)


# ── Wiring ───────────────────────────────────────────────────────────────────

@pytest.fixture
def compat_env(monkeypatch):
    for name in ("CLASSIFICATION_RATE_LIMIT_MAX_WAIT_SECONDS",
                 "CLASSIFICATION_RATE_LIMIT_WAIT_BUDGET_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLASSIFICATION_PROVIDER", "openai_compat")
    monkeypatch.setenv("CLASSIFICATION_BASE_URL", BASE)
    monkeypatch.setenv("CLASSIFICATION_API_KEY", KEY)
    monkeypatch.setenv("CLASSIFICATION_MODEL", MODEL)
    return monkeypatch


def test_wiring_default_is_off(compat_env, monkeypatch, clock):
    from app.classification.service import get_llm_provider

    post = _Post(_429(2), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = get_llm_provider()
    assert p.classify_title("a", "he") is None
    assert clock["sleeps"] == []


def test_wiring_reads_the_settings(compat_env, monkeypatch, clock):
    from app.classification.service import get_llm_provider

    compat_env.setenv("CLASSIFICATION_RATE_LIMIT_MAX_WAIT_SECONDS", "15")
    compat_env.setenv("CLASSIFICATION_RATE_LIMIT_WAIT_BUDGET_SECONDS", "4")
    post = _Post(_429(3), _ok(), _429(3), _ok())
    monkeypatch.setattr(httpx, "post", post)
    p = get_llm_provider()
    assert p.classify_title("a", "he") is not None      # 3 s wait, within the cap and budget
    clock["now"] += 100
    assert p.classify_title("b", "he") is None          # 3 s > the 1 s of budget left
    assert clock["sleeps"] == [pytest.approx(3.0)]


# ── Through a real ingestion run ─────────────────────────────────────────────

WALLA = "walla_sport"
URLS = ["https://sports.walla.co.il/item/40900001", "https://sports.walla.co.il/item/40900002"]
TITLES = ["מכבי תל אביב החתימה גארד חדש", "מכבי תל אביב בדרך להחתמת פורוורד"]


class _FakeAdapter:
    def __init__(self, items):
        self._items = items

    def fetch(self):
        return list(self._items)


@pytest.fixture
def db(_application):
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import ArticleRow

    init_db()

    def cleanup(s):
        s.query(ArticleRow).filter(ArticleRow.url.in_(URLS)).delete(synchronize_session=False)
        s.execute(text("DELETE FROM ingestion_runs WHERE source_id = :w"), {"w": WALLA})
        s.commit()

    with SessionLocal() as s:
        cleanup(s)
    yield SessionLocal
    with SessionLocal() as s:
        cleanup(s)


def test_run_ingestion_recovers_a_rate_limited_article(db, monkeypatch):
    """A real (short) sleep: the run resets the budget, the 429 article is classified
    by the LLM instead of falling back, the wait is counted in the run metrics, and
    LLM latency does not include the time spent waiting."""
    from app.ingestion import ingestion_service
    from app.ingestion.config import get_source_config

    post = _Post(_429(0.3), _ok(), _ok())
    monkeypatch.setattr(httpx, "post", post)
    provider = _provider(rate_limit_max_wait_seconds=15, rate_limit_wait_budget_seconds=1)
    provider._wait_budget_left = 0.0                    # spent by an earlier run
    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", provider)

    from app.ingestion.adapters.base import RawSourceItem

    items = [RawSourceItem(WALLA, u, t, datetime.now(tz=timezone.utc), "")
             for u, t in zip(URLS, TITLES)]
    with patch("app.ingestion.ingestion_service.build_adapter",
               side_effect=lambda cfg: _FakeAdapter(items)), \
         patch("app.ingestion.ingestion_service.get_effective_enabled_sources",
               return_value=[get_source_config(WALLA)]), \
         db() as session:
        started = time.perf_counter()
        [result] = ingestion_service.run_ingestion(session, llm_gating_enabled_override=False)
        elapsed = time.perf_counter() - started
        stored = session.execute(text(
            "SELECT classified_by FROM articles WHERE url IN (:a, :b)"),
            {"a": URLS[0], "b": URLS[1]}).scalars().all()

    assert post.calls == 3
    assert elapsed >= 0.3
    assert len(stored) == 2 and all(cb in ("llm", "llm+rules_guardrail") for cb in stored)
    assert result.llm_fallback_http_error == 0
    assert result.metrics["rate_limit_waits"] == 1
    assert result.metrics["rate_limit_wait_ms"] == pytest.approx(300, abs=50)
    assert result.metrics["llm_p95_ms"] < 250            # the 300 ms wait is not latency
