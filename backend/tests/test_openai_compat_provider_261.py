"""OpenAI-compatible classification provider (#261). Mocked HTTP only.

Every response here is a hand-built httpx.Response; no test reaches a network.
"""

import json
import logging
from datetime import datetime, timezone

import httpx
import pytest

from app.classification import providers
from app.classification.providers import (
    DisabledLLMProvider,
    OpenAICompatibleProvider,
    classification_json_schema,
)
from app.classification.validation import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_IMPORTANCES,
    ALLOWED_LEAGUES,
    ALLOWED_SPORTS,
    LLM_MIN_CONFIDENCE,
)

BASE = "https://llm.example.test/openai/v1"
KEY = "sk-test-SECRET-never-logged"
MODEL = "openai/gpt-oss-20b"
VALID = {
    "sport": "basketball", "league": "EuroLeague",
    "entities": ["Maccabi Tel Aviv Basketball"], "event_type": "signing",
    "importance": "high", "confidence": 0.93, "reason": "Maccabi signing.",
}


def _provider(**kwargs) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(base_url=BASE, api_key=KEY, model=MODEL, timeout=15.0, **kwargs)


def _response(status=200, body=None, headers=None, text=None) -> httpx.Response:
    request = httpx.Request("POST", f"{BASE}/chat/completions")
    if text is not None:
        return httpx.Response(status, text=text, headers=headers, request=request)
    return httpx.Response(status, json=body, headers=headers, request=request)


def _completion(content, usage=True, finish_reason="stop") -> dict:
    body = {"choices": [{"index": 0, "finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 1180, "completion_tokens": 140, "total_tokens": 1320,
                         "completion_tokens_details": {"reasoning_tokens": 64}}
    return body


class _Recorder:
    """Stands in for httpx.post; returns queued responses or raises."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def post(monkeypatch):
    def install(*outcomes):
        recorder = _Recorder(*outcomes)
        monkeypatch.setattr(httpx, "post", recorder)
        return recorder
    return install


# ── Success and request shape ────────────────────────────────────────────────

def test_success_parses_and_records_usage(post):
    rec = post(_response(body=_completion(json.dumps(VALID))))
    p = _provider()
    result = p.classify_title("מכבי חתמה על גארד", "he", subtitle="יורוליג")

    assert result is not None
    assert (result.sport, result.league, result.event_type) == ("basketball", "EuroLeague", "signing")
    assert p.last_failure_reason == "none"
    assert p.last_usage == {"prompt_tokens": 1180, "completion_tokens": 140, "reasoning_tokens": 64,
                            "cached_prompt_tokens": None}
    assert p.last_finish_reason == "stop"
    assert p.last_call_latency_ms is not None
    assert p.provider_id == f"openai_compat:{MODEL}"

    call = rec.calls[0]
    assert call["url"] == f"{BASE}/chat/completions"
    assert call["headers"] == {"Authorization": f"Bearer {KEY}"}
    payload = call["json"]
    assert payload["model"] == MODEL
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 1000
    assert payload["stream"] is False
    assert payload["reasoning_effort"] == "low"
    assert payload["messages"][1]["content"] == "Headline: מכבי חתמה על גארד\nSubtitle: יורוליג"
    fmt = payload["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == classification_json_schema()


def test_trailing_slash_in_base_url(post):
    rec = post(_response(body=_completion(json.dumps(VALID))))
    OpenAICompatibleProvider(base_url=BASE + "/", api_key=KEY, model=MODEL, timeout=5).classify_title("x", "he")
    assert rec.calls[0]["url"] == f"{BASE}/chat/completions"


def test_json_object_mode_and_omitted_effort():
    payload = _provider(response_format="json_object", reasoning_effort="").build_payload("x")
    assert payload["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in payload


def test_no_response_format_mode():
    assert "response_format" not in _provider(response_format="none").build_payload("x")


def test_unknown_response_format_is_rejected():
    with pytest.raises(ValueError):
        _provider(response_format="yaml")


def test_schema_matches_validation_enums():
    schema = classification_json_schema()
    props = schema["properties"]
    assert set(props["sport"]["enum"]) == ALLOWED_SPORTS
    assert set(props["league"]["enum"]) == ALLOWED_LEAGUES | {None}
    assert set(props["event_type"]["enum"]) == ALLOWED_EVENT_TYPES
    assert set(props["importance"]["enum"]) == ALLOWED_IMPORTANCES
    assert set(schema["required"]) == set(props)
    assert schema["additionalProperties"] is False


def test_missing_usage_is_none(post):
    post(_response(body=_completion(json.dumps(VALID), usage=False)))
    p = _provider()
    assert p.classify_title("x", "he") is not None
    assert p.last_usage is None


# ── Content failures ─────────────────────────────────────────────────────────

def test_malformed_json_is_unparseable(post):
    post(_response(body=_completion('{"sport": "basketball", "league": ', finish_reason="length")))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "unparseable_json"
    assert p.last_finish_reason == "length"


def test_schema_mismatch_degrades_to_low_confidence(post):
    # Valid JSON that ignores the schema: validation substitutes safe defaults,
    # and the zero confidence routes the article to the low-confidence fallback.
    post(_response(body=_completion(json.dumps({"sport": "cricket", "event_type": "scandal"}))))
    p = _provider()
    result = p.classify_title("x", "he")
    assert result is not None
    assert (result.sport, result.event_type, result.league) == ("unknown", "news", None)
    assert result.confidence < LLM_MIN_CONFIDENCE


@pytest.mark.parametrize("body", [
    {"choices": []},
    {"no_choices": True},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": "not-a-dict"}]},
])
def test_unexpected_body_is_bad_response_shape(post, body):
    post(_response(body=body))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "bad_response_shape"


def test_non_json_body_is_bad_response_shape(post):
    post(_response(text="<html>gateway</html>"))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "bad_response_shape"


# ── Transport failures ───────────────────────────────────────────────────────

def test_timeout(post):
    post(httpx.ReadTimeout("slow"))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "timeout"
    assert p.last_failure_was_connect_error is False
    assert p.last_call_latency_ms is not None


def test_connect_error_opens_the_run_circuit(post):
    post(httpx.ConnectError("refused"))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "connect_error"
    assert p.last_failure_was_connect_error is True


@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
def test_http_errors(post, status):
    post(_response(status=status, body={"error": {"message": f"echo {KEY}"}}))
    p = _provider()
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "http_error"
    assert p.last_http_status == status


# ── 429: one fallback, then a bounded pause with no requests ────────────────

def test_429_pauses_without_retrying(post, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["now"])
    rec = post(_response(status=429, body={}, headers={"retry-after": "7"}),
               _response(body=_completion(json.dumps(VALID))))
    p = _provider()

    assert p.classify_title("a", "he") is None
    assert p.last_failure_reason == "http_error" and p.last_http_status == 429
    assert len(rec.calls) == 1                      # no retry inside the call

    for _ in range(5):                              # the rest of the cycle
        assert p.classify_title("b", "he") is None
        assert p.last_failure_reason == "http_error"
    assert len(rec.calls) == 1                      # paused: no request sent

    clock["now"] += 7.5
    assert p.classify_title("c", "he") is not None  # pause over
    assert len(rec.calls) == 2


@pytest.mark.parametrize("header,expected", [
    ("100000", providers.MAX_RATE_LIMIT_PAUSE_SECONDS),
    ("Wed, 21 Oct 2026 07:28:00 GMT", providers.DEFAULT_RATE_LIMIT_PAUSE_SECONDS),
    (None, providers.DEFAULT_RATE_LIMIT_PAUSE_SECONDS),
])
def test_429_pause_is_bounded(post, monkeypatch, header, expected):
    monkeypatch.setattr(providers.time, "monotonic", lambda: 0.0)
    post(_response(status=429, body={}, headers={"retry-after": header} if header else None))
    p = _provider()
    p.classify_title("a", "he")
    assert p._paused_until == pytest.approx(expected)


# ── Secret hygiene ───────────────────────────────────────────────────────────

def test_key_never_logged_or_repr(post, caplog):
    caplog.set_level(logging.DEBUG)
    post(_response(status=401, body={"error": f"bad key {KEY}"}),
         httpx.ConnectError(f"refused {BASE}"),
         _response(text=f"<html>{KEY}</html>"),
         _response(status=429, body={}, headers={"retry-after": "1"}))
    p = _provider()
    for _ in range(4):
        p.classify_title("x", "he")
    assert KEY not in caplog.text
    assert KEY not in repr(p)


# ── Wiring (service.get_llm_provider) ────────────────────────────────────────

@pytest.fixture
def compat_env(monkeypatch):
    for name in ("CLASSIFICATION_RESPONSE_FORMAT", "CLASSIFICATION_REASONING_EFFORT",
                 "CLASSIFICATION_TOKEN_LIMIT_PARAM", "CLASSIFICATION_SEND_TEMPERATURE",
                 "CLASSIFICATION_MAX_OUTPUT_TOKENS", "CLASSIFICATION_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLASSIFICATION_PROVIDER", "openai_compat")
    monkeypatch.setenv("CLASSIFICATION_BASE_URL", BASE)
    monkeypatch.setenv("CLASSIFICATION_API_KEY", KEY)
    monkeypatch.setenv("CLASSIFICATION_MODEL", MODEL)
    return monkeypatch


def test_wiring_builds_the_provider(compat_env):
    from app.classification.service import get_llm_provider

    compat_env.setenv("CLASSIFICATION_MAX_OUTPUT_TOKENS", "600")
    compat_env.setenv("CLASSIFICATION_REASONING_EFFORT", "none")
    p = get_llm_provider()
    assert isinstance(p, OpenAICompatibleProvider)
    payload = p.build_payload("x")
    assert payload["max_tokens"] == 600
    assert "reasoning_effort" not in payload


@pytest.mark.parametrize("missing", ["CLASSIFICATION_BASE_URL", "CLASSIFICATION_API_KEY", "CLASSIFICATION_MODEL"])
def test_wiring_missing_setting_disables(compat_env, caplog, missing):
    from app.classification.service import get_llm_provider

    compat_env.delenv(missing)
    caplog.set_level(logging.WARNING)
    assert isinstance(get_llm_provider(), DisabledLLMProvider)
    assert missing in caplog.text
    assert KEY not in caplog.text


@pytest.mark.parametrize("name,value", [
    ("CLASSIFICATION_BASE_URL", "http://llm.example.test/v1"),   # plain http, not local
    ("CLASSIFICATION_RESPONSE_FORMAT", "yaml"),
])
def test_wiring_invalid_setting_disables(compat_env, name, value):
    from app.classification.service import get_llm_provider

    compat_env.setenv(name, value)
    assert isinstance(get_llm_provider(), DisabledLLMProvider)


# ── End to end through _normalise, and run metrics ───────────────────────────

def test_end_to_end_through_normalise(post, monkeypatch):
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config

    post(_response(body=_completion(json.dumps(VALID))))
    provider = _provider()
    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", provider)
    item = RawSourceItem(
        source_id="walla_sport",
        url="https://sports.walla.co.il/item/261261",
        title="מכבי תל אביב החתימה גארד חדש",
        published_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
    )
    article, llm_ms, _gate = ingestion_service._normalise(
        item, get_source_config("walla_sport"), llm_gating_enabled_override=False,
    )
    assert llm_ms is not None
    assert article.classified_by in ("llm", "llm+rules_guardrail")
    assert article.classification_provider == f"openai_compat:{MODEL}"


def test_usage_totals_reach_run_metrics():
    from app.ingestion.ingestion_service import _accumulate_usage
    from app.ingestion.run_metrics import ArticleQualityCounters, compute_run_metrics

    totals: dict = {}
    _accumulate_usage(totals, {"prompt_tokens": 1000, "completion_tokens": 100, "reasoning_tokens": None})
    _accumulate_usage(totals, {"prompt_tokens": 1100, "completion_tokens": 90, "reasoning_tokens": 40})
    _accumulate_usage(totals, None)  # a provider that reports nothing
    assert totals == {"calls_with_usage": 2, "prompt_tokens": 2100,
                      "completion_tokens": 190, "reasoning_tokens": 40}

    common = dict(
        counters=ArticleQualityCounters(), llm_attempts=2, llm_successes=2,
        llm_fallback_connect_error=0, llm_fallback_timeout=0, llm_fallback_http_error=0,
        llm_fallback_bad_response_shape=0, llm_fallback_unparseable_json=0,
        llm_fallback_low_confidence=0, llm_failure_latencies={}, llm_skipped=0,
        llm_skip_reasons={}, llm_call_reasons={}, llm_avg_ms=None, llm_p95_ms=None, total_ms=1.0,
    )
    assert compute_run_metrics(**common, llm_usage=totals)["llm_tokens"] == totals
    assert compute_run_metrics(**common)["llm_tokens"] is None


# ── Gemini: evaluation-facing metadata (#261/#262), behaviour unchanged ──────

def _gemini(monkeypatch, **kwargs):
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.classification.providers import GeminiLLMProvider

    mock_genai = MagicMock()
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=mock_genai))
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", mock_genai.types)
    return GeminiLLMProvider(api_key="test-key", model="gemini-3.1-flash-lite", **kwargs), mock_genai


def _gemini_response(text, finish="STOP", thoughts=300):
    from types import SimpleNamespace

    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=1150, candidates_token_count=80,
                                       thoughts_token_count=thoughts),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
    )


def test_gemini_records_usage_including_thinking(monkeypatch):
    p, genai = _gemini(monkeypatch)
    p._client.models.generate_content.return_value = _gemini_response(json.dumps(VALID))
    assert p.classify_title("x", "he") is not None
    assert p.last_usage == {"prompt_tokens": 1150, "completion_tokens": 80, "reasoning_tokens": 300}
    assert p.last_finish_reason == "STOP"
    assert p.last_failure_reason == "none"
    assert genai.types.GenerateContentConfig.call_args.kwargs["max_output_tokens"] == 500


def test_gemini_truncation_is_visible(monkeypatch):
    p, _ = _gemini(monkeypatch, max_output_tokens=200)
    p._client.models.generate_content.return_value = _gemini_response('{"sport": "bask', finish="MAX_TOKENS")
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "unparseable_json"
    assert p.last_finish_reason == "MAX_TOKENS"


def test_gemini_api_error_is_typed(monkeypatch):
    p, _ = _gemini(monkeypatch)
    p._client.models.generate_content.side_effect = RuntimeError("500 INTERNAL")
    assert p.classify_title("x", "he") is None
    assert p.last_failure_reason == "http_error"


def test_gemini_max_output_tokens_env(monkeypatch):
    import sys
    from unittest.mock import MagicMock

    from app.classification.service import get_llm_provider

    mock_genai = MagicMock()
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setenv("CLASSIFICATION_PROVIDER", "gemini")
    monkeypatch.setenv("CLASSIFICATION_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFICATION_MAX_OUTPUT_TOKENS", "900")
    assert get_llm_provider()._max_output_tokens == 900
    monkeypatch.delenv("CLASSIFICATION_MAX_OUTPUT_TOKENS")
    assert get_llm_provider()._max_output_tokens == 500


# ── OpenAI reasoning models and prompt-cache accounting (#262 bake-off) ──────

def test_reasoning_model_options_shape_the_payload():
    payload = _provider(token_limit_param="max_completion_tokens", send_temperature=False,
                        reasoning_effort="minimal").build_payload("x")
    assert payload["max_completion_tokens"] == 1000
    assert "max_tokens" not in payload and "temperature" not in payload
    assert payload["reasoning_effort"] == "minimal"


def test_defaults_keep_the_groq_shape():
    payload = _provider().build_payload("x")
    assert payload["max_tokens"] == 1000 and payload["temperature"] == 0
    assert "max_completion_tokens" not in payload


def test_unknown_token_param_is_rejected():
    with pytest.raises(ValueError):
        _provider(token_limit_param="max_output")


def test_cached_prompt_tokens_are_recorded(post):
    body = _completion(json.dumps(VALID))
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": 1024}
    post(_response(body=body))
    p = _provider()
    p.classify_title("x", "he")
    assert p.last_usage["cached_prompt_tokens"] == 1024


def test_wiring_reasoning_model_env(compat_env):
    from app.classification.service import get_llm_provider

    compat_env.setenv("CLASSIFICATION_TOKEN_LIMIT_PARAM", "max_completion_tokens")
    compat_env.setenv("CLASSIFICATION_SEND_TEMPERATURE", "false")
    payload = get_llm_provider().build_payload("x")
    assert "max_completion_tokens" in payload and "temperature" not in payload
    compat_env.setenv("CLASSIFICATION_TOKEN_LIMIT_PARAM", "bogus")
    assert isinstance(get_llm_provider(), DisabledLLMProvider)
