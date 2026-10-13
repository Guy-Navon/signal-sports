"""
LLM classification provider interface and implementations.

- LLMClassificationProvider:  abstract base
- DisabledLLMProvider:        no-op; classification disabled
- FakeLLMProvider:            dev-only; returns pre-set results for known headlines
- GeminiLLMProvider:          Google Gemini API (recommended free cloud option)
- OllamaProvider:             calls a locally running Ollama instance
- OpenAICompatibleProvider:   any OpenAI Chat Completions endpoint (Groq, Cerebras,
                              OpenRouter, ...) — issue #261

Configuration via environment variables:
  CLASSIFICATION_PROVIDER=disabled|fake|gemini|ollama|openai_compat  (default: disabled)
  CLASSIFICATION_MODEL=<model name>                    (default varies by provider)
  CLASSIFICATION_API_KEY=<key>                         (required for gemini, openai_compat)
  CLASSIFICATION_OLLAMA_BASE_URL=<url>                 (default: http://localhost:11434)
  CLASSIFICATION_BASE_URL=<url>                        (openai_compat, e.g. .../openai/v1)
  CLASSIFICATION_TIMEOUT_SECONDS=<number>              (default: 15; ollama, openai_compat)
  The openai_compat tuning variables are documented in app/classification/service.py.
"""

import json
import logging
import time
from typing import Optional

import httpx

from app.classification.llm_result import LLMClassificationResult
from app.classification.prompt import CLASSIFICATION_SYSTEM_PROMPT, build_user_message
from app.classification.validation import parse_and_validate_llm_json

logger = logging.getLogger(__name__)


class LLMClassificationProvider:
    can_classify: bool = False
    last_failure_was_connect_error: bool = False
    last_failure_reason: str = "none"
    last_call_latency_ms: Optional[float] = None
    last_raw_content: Optional[str] = None
    # Token usage of the last call, when the provider reports it (#261):
    # {"prompt_tokens", "completion_tokens", "reasoning_tokens"}; counts only.
    last_usage: Optional[dict] = None

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        raise NotImplementedError

    @property
    def provider_id(self) -> str:
        return "disabled"


class DisabledLLMProvider(LLMClassificationProvider):
    can_classify = False

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        return None

    @property
    def provider_id(self) -> str:
        return "disabled"


# Pre-set results for the 4 regression headlines and common test cases.
# FakeProvider is deterministic: same input → same output every time.
_FAKE_KNOWN: dict[str, LLMClassificationResult] = {
    "ג'יילן ברונסון ה-MVP של סדרת הגמר: \"בכל פעם, פשוט לקחנו את זה\"": LLMClassificationResult(
        sport="basketball", league="NBA",
        entities=["Jalen Brunson", "New York Knicks"],
        event_type="finals_result", importance="very_high",
        confidence=0.92,
        reason="Brunson is the Knicks NBA Finals MVP — basketball finals result.",
    ),
    "ערב היסטורי לברונסון ולניקס: ניו יורק אלופת ה-NBA!": LLMClassificationResult(
        sport="basketball", league="NBA",
        entities=["Jalen Brunson", "New York Knicks"],
        event_type="title_win", importance="very_high",
        confidence=0.97,
        reason="New York Knicks win the NBA championship — basketball title win.",
    ),
    "סיכום בהפועל תל אביב? בירושלים לא שחררו את ג'ארד הארפר": LLMClassificationResult(
        sport="basketball", league="Israeli Basketball League",
        entities=["הפועל תל אביב", "הפועל ירושלים"],
        event_type="negotiation", importance="medium",
        confidence=0.82,
        reason="Harper transfer negotiation between Hapoel TLV and Hapoel Jerusalem — Israeli basketball.",
    ),
    "אולימפיאקוס נקצה, ינאקופולוס עצבני אחרי הסערה הגדולה ביוון": LLMClassificationResult(
        sport="basketball", league="Greek Basket League",
        entities=["Olympiacos Basketball", "Panathinaikos Basketball"],
        event_type="news", importance="medium",
        confidence=0.72,
        reason="Yannakopoulos (Panathinaikos owner) and Olympiacos are rivals in Greek basketball; controversy context.",
    ),
}


class FakeLLMProvider(LLMClassificationProvider):
    """
    Returns pre-set results for known test headlines.
    Unknown headlines return None (simulates no classification).
    For dev testing without Ollama installed.
    """
    can_classify = True

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        return _FAKE_KNOWN.get(title)

    @property
    def provider_id(self) -> str:
        return "fake"


class GeminiLLMProvider(LLMClassificationProvider):
    """
    Calls the Google Gemini API for article classification.
    Requires: google-genai package and CLASSIFICATION_API_KEY.
    Recommended free cloud option: gemini-2.5-flash-lite

    Failure modes:
      - Any API error → logs warning, returns None → rules fallback in ingestion_service
      - No circuit breaker needed: cloud API failures are transient
    """
    can_classify = True

    def __init__(self, api_key: str, model: str, max_output_tokens: int = 500) -> None:
        import google.genai as genai  # guarded import — only when provider is active
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._max_output_tokens = max_output_tokens
        self.last_usage: Optional[dict] = None
        self.last_finish_reason: Optional[str] = None

    @property
    def provider_id(self) -> str:
        return f"gemini:{self._model}"

    def _record_response(self, response) -> None:
        """Usage (incl. thinking tokens) and finish reason, for evaluation (#262).

        A thinking model can spend the max_output_tokens budget before the
        JSON ends; a MAX_TOKENS finish reason with unparseable JSON shows that.
        """
        def _count(value) -> Optional[int]:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            self.last_usage = {
                "prompt_tokens": _count(getattr(meta, "prompt_token_count", None)),
                "completion_tokens": _count(getattr(meta, "candidates_token_count", None)),
                "reasoning_tokens": _count(getattr(meta, "thoughts_token_count", None)),
            }
        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list) and candidates:
            reason = getattr(candidates[0], "finish_reason", None)
            name = getattr(reason, "name", reason)
            self.last_finish_reason = name if isinstance(name, str) else None

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        self.last_failure_reason = "none"
        self.last_usage = None
        self.last_finish_reason = None
        self.last_raw_content = None
        # Two attempts: first try, then one retry after a rate-limit sleep.
        for attempt in range(2):
            try:
                from google.genai import types
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=build_user_message(title, subtitle),
                    config=types.GenerateContentConfig(
                        system_instruction=CLASSIFICATION_SYSTEM_PROMPT,
                        temperature=0.0,
                        max_output_tokens=self._max_output_tokens,
                        response_mime_type="application/json",
                    ),
                )
                self._record_response(response)
                self.last_raw_content = response.text
                result = parse_and_validate_llm_json(response.text or "")
                if result is None:
                    self.last_failure_reason = "unparseable_json"
                return result
            except Exception as exc:
                exc_str = str(exc)
                if attempt == 0 and ("429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str):
                    import re
                    import time
                    # API embeds the retry delay: "retryDelay": "2.8s" or "910ms"
                    m = re.search(r"retryDelay.*?['\"](\d+(?:\.\d+)?)(ms|s)['\"]", exc_str)
                    if m:
                        value, unit = float(m.group(1)), m.group(2)
                        delay = value / 1000.0 if unit == "ms" else value
                    else:
                        delay = 6.0
                    delay = max(0.5, min(delay, 65.0))
                    logger.info(
                        "Gemini rate limit — sleeping %.1fs then retrying %r",
                        delay, title[:40],
                    )
                    time.sleep(delay)
                    continue
                self.last_failure_reason = "http_error"
                logger.warning("Gemini classify failed for %r: %s", title[:60], exc)
                return None
        self.last_failure_reason = "http_error"
        return None


class OllamaProvider(LLMClassificationProvider):
    """
    Calls a locally running Ollama instance for article classification.
    Requires: Ollama installed and running, target model pulled.
    No GPU required (CPU inference works; slower but functional).

    Failure modes:
      - ConnectError (Ollama not running) → sets last_failure_was_connect_error=True, returns None
      - ReadTimeout (model slow) → last_failure_was_connect_error=False, returns None
      - HTTP error / parse error → last_failure_was_connect_error=False, returns None
      - Valid JSON but low confidence → returns result (caller handles it)
    """
    can_classify = True

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(connect=2.0, read=timeout, write=5.0, pool=5.0)
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms: Optional[float] = None
        self.last_raw_content: Optional[str] = None

    @property
    def provider_id(self) -> str:
        return f"ollama:{self._model}"

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms = None
        self.last_raw_content = None
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(title, subtitle)},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 500},
        }
        started_at = time.perf_counter()
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["message"]["content"]
            if not isinstance(raw_content, str):
                raise TypeError("Ollama message content is not a string")
            self.last_raw_content = raw_content
            result = parse_and_validate_llm_json(raw_content)
            if result is None:
                self.last_failure_reason = "unparseable_json"
                stripped = raw_content.rstrip()
                logger.warning(
                    "Ollama returned unparseable JSON for %r: length=%d "
                    "ends_mid_token=%s raw=%r",
                    title[:60],
                    len(raw_content),
                    bool(stripped) and not stripped.endswith(("}", "]")),
                    raw_content[:200],
                )
            return result
        except httpx.ConnectError as exc:
            self.last_failure_was_connect_error = True
            self.last_failure_reason = "connect_error"
            logger.warning("Ollama not reachable for %r: %s", title[:60], exc)
            return None
        except httpx.TimeoutException as exc:
            self.last_failure_reason = "timeout"
            logger.warning("Ollama timed out for %r: %s", title[:60], exc)
            return None
        except httpx.HTTPStatusError as exc:
            self.last_failure_reason = "http_error"
            logger.warning("Ollama HTTP error for %r: %s", title[:60], exc)
            return None
        except httpx.RequestError as exc:
            self.last_failure_reason = "http_error"
            logger.warning("Ollama request failed for %r: %s", title[:60], exc)
            return None
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self.last_failure_reason = "bad_response_shape"
            logger.warning("Ollama response shape invalid for %r: %s", title[:60], exc)
            return None
        finally:
            self.last_call_latency_ms = (time.perf_counter() - started_at) * 1000


# ── OpenAI-compatible endpoints (#261) ────────────────────────────────────────

def classification_json_schema() -> dict:
    """The classification output as a strict JSON Schema.

    Built from the same allowed values ``parse_and_validate_llm_json`` enforces,
    so the two cannot drift. Strict mode needs every property required and no
    extra properties; ``league`` is nullable through ``["string", "null"]`` with
    ``None`` in its enum.
    """
    from app.classification.validation import (
        ALLOWED_EVENT_TYPES,
        ALLOWED_IMPORTANCES,
        ALLOWED_LEAGUES,
        ALLOWED_SPORTS,
    )

    properties = {
        "sport": {"type": "string", "enum": sorted(ALLOWED_SPORTS)},
        "league": {"type": ["string", "null"], "enum": sorted(ALLOWED_LEAGUES) + [None]},
        "entities": {"type": "array", "items": {"type": "string"}},
        "event_type": {"type": "string", "enum": sorted(ALLOWED_EVENT_TYPES)},
        "importance": {"type": "string", "enum": sorted(ALLOWED_IMPORTANCES)},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


RESPONSE_FORMATS = ("json_schema", "json_object", "none")
TOKEN_LIMIT_PARAMS = ("max_tokens", "max_completion_tokens")

# A 429 pauses the provider for Retry-After seconds, capped here, so one cycle
# can never hammer a rate-limited endpoint. No request is sent while paused.
MAX_RATE_LIMIT_PAUSE_SECONDS = 300.0
DEFAULT_RATE_LIMIT_PAUSE_SECONDS = 60.0


def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # an HTTP-date: use the default pause


class OpenAICompatibleProvider(LLMClassificationProvider):
    """
    Classifies through any OpenAI Chat Completions endpoint (Groq, Cerebras,
    OpenRouter, Cloudflare's OpenAI-compatible API, OpenAI itself).

    Same contract as OllamaProvider: the same prompt and user message,
    ``temperature 0``, ``parse_and_validate_llm_json``, the typed failure
    taxonomy (#217) and per-call latency. It never retries.

    - ``response_format``: ``json_schema`` (strict, the classification schema;
      Groq's gpt-oss models support it), ``json_object`` (JSON mode), or
      ``none`` for endpoints that support neither.
    - ``reasoning_effort``: sent when set (gpt-oss, Qwen3), so hidden reasoning
      does not eat the output budget. Empty omits it for endpoints that reject
      the parameter.
    - 429: that article falls back as ``http_error``, then the provider pauses
      for ``Retry-After`` (default 60 s, capped at 300 s). Calls during the
      pause return None at once, also as ``http_error``, without a request.
    - ``last_usage`` holds the reported token counts (never content).
    - The key travels only in the Authorization header. It is never logged, and
      error logs carry the status code, not the response body.
    """
    can_classify = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_output_tokens: int = 1000,
        response_format: str = "json_schema",
        reasoning_effort: str = "low",
        token_limit_param: str = "max_tokens",
        send_temperature: bool = True,
    ) -> None:
        if response_format not in RESPONSE_FORMATS:
            raise ValueError(f"response_format must be one of {RESPONSE_FORMATS}")
        if token_limit_param not in TOKEN_LIMIT_PARAMS:
            raise ValueError(f"token_limit_param must be one of {TOKEN_LIMIT_PARAMS}")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = httpx.Timeout(connect=5.0, read=timeout, write=10.0, pool=5.0)
        self._max_output_tokens = max_output_tokens
        self._response_format = response_format
        self._reasoning_effort = reasoning_effort.strip()
        # OpenAI's reasoning models reject max_tokens and any temperature other
        # than the default; Groq accepts both spellings and temperature 0.
        self._token_limit_param = token_limit_param
        self._send_temperature = send_temperature
        self._paused_until = 0.0
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms: Optional[float] = None
        self.last_raw_content: Optional[str] = None
        self.last_usage: Optional[dict] = None
        self.last_http_status: Optional[int] = None
        self.last_finish_reason: Optional[str] = None

    @property
    def provider_id(self) -> str:
        return f"openai_compat:{self._model}"

    def __repr__(self) -> str:  # never include the key
        return f"OpenAICompatibleProvider(url={self._url!r}, model={self._model!r})"

    def rate_limit_paused(self) -> bool:
        return time.monotonic() < self._paused_until

    def build_payload(self, title: str, subtitle: Optional[str] = None) -> dict:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(title, subtitle)},
            ],
            self._token_limit_param: self._max_output_tokens,
            "stream": False,
        }
        if self._send_temperature:
            payload["temperature"] = 0
        if self._response_format == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "article_classification",
                    "strict": True,
                    "schema": classification_json_schema(),
                },
            }
        elif self._response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        return payload

    @staticmethod
    def _usage(data: dict) -> Optional[dict]:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None

        def _count(value) -> Optional[int]:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        details = usage.get("completion_tokens_details")
        reasoning = _count(details.get("reasoning_tokens")) if isinstance(details, dict) else None
        prompt_details = usage.get("prompt_tokens_details")
        cached = _count(prompt_details.get("cached_tokens")) if isinstance(prompt_details, dict) else None
        return {
            "prompt_tokens": _count(usage.get("prompt_tokens")),
            "completion_tokens": _count(usage.get("completion_tokens")),
            "reasoning_tokens": reasoning,
            # Part of prompt_tokens served from the provider's prompt cache
            # (billed at a discount by Groq and OpenAI).
            "cached_prompt_tokens": cached,
        }

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms = None
        self.last_raw_content = None
        self.last_usage = None
        self.last_http_status = None
        self.last_finish_reason = None

        if self.rate_limit_paused():
            self.last_failure_reason = "http_error"
            self.last_http_status = 429
            self.last_call_latency_ms = 0.0
            return None

        started_at = time.perf_counter()
        try:
            response = httpx.post(
                self._url,
                json=self.build_payload(title, subtitle),
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            self.last_http_status = response.status_code
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                pause = min(
                    DEFAULT_RATE_LIMIT_PAUSE_SECONDS if retry_after is None else retry_after,
                    MAX_RATE_LIMIT_PAUSE_SECONDS,
                )
                self._paused_until = time.monotonic() + pause
                self.last_failure_reason = "http_error"
                logger.warning(
                    "%s rate-limited (429, retry-after=%s): no LLM calls for %.0fs",
                    self.provider_id, response.headers.get("retry-after"), pause,
                )
                return None
            response.raise_for_status()
            data = response.json()
            self.last_usage = self._usage(data)
            choice = data["choices"][0]
            self.last_finish_reason = choice.get("finish_reason")
            raw_content = choice["message"]["content"]
            if not isinstance(raw_content, str):
                raise TypeError("message content is not a string")
            self.last_raw_content = raw_content
            result = parse_and_validate_llm_json(raw_content)
            if result is None:
                self.last_failure_reason = "unparseable_json"
                logger.warning(
                    "%s returned unparseable JSON for %r: length=%d finish_reason=%s",
                    self.provider_id, title[:60], len(raw_content), self.last_finish_reason,
                )
            return result
        except httpx.ConnectError as exc:
            self.last_failure_was_connect_error = True
            self.last_failure_reason = "connect_error"
            logger.warning("%s not reachable for %r: %s", self.provider_id, title[:60], type(exc).__name__)
            return None
        except httpx.TimeoutException as exc:
            self.last_failure_reason = "timeout"
            logger.warning("%s timed out for %r: %s", self.provider_id, title[:60], type(exc).__name__)
            return None
        except httpx.HTTPStatusError:
            self.last_failure_reason = "http_error"
            logger.warning("%s HTTP %s for %r", self.provider_id, self.last_http_status, title[:60])
            return None
        except httpx.RequestError as exc:
            self.last_failure_reason = "http_error"
            logger.warning("%s request failed for %r: %s", self.provider_id, title[:60], type(exc).__name__)
            return None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            # ValueError covers a non-JSON body (json.JSONDecodeError subclasses it).
            self.last_failure_reason = "bad_response_shape"
            logger.warning("%s response shape invalid for %r: %s", self.provider_id, title[:60], type(exc).__name__)
            return None
        finally:
            if self.last_call_latency_ms is None:
                self.last_call_latency_ms = (time.perf_counter() - started_at) * 1000
