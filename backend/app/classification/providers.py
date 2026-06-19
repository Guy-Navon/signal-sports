"""
LLM classification provider interface and implementations.

- LLMClassificationProvider:  abstract base
- DisabledLLMProvider:        no-op; classification disabled
- FakeLLMProvider:            dev-only; returns pre-set results for known headlines
- GeminiLLMProvider:          Google Gemini API (recommended free cloud option)
- OllamaProvider:             calls a locally running Ollama instance

Configuration via environment variables:
  CLASSIFICATION_PROVIDER=disabled|fake|gemini|ollama  (default: disabled)
  CLASSIFICATION_MODEL=<model name>                    (default varies by provider)
  CLASSIFICATION_API_KEY=<gemini key>                  (required for gemini)
  CLASSIFICATION_OLLAMA_BASE_URL=<url>                 (default: http://localhost:11434)
  CLASSIFICATION_TIMEOUT_SECONDS=<number>              (default: 15, ollama only)
"""

import logging
from typing import Optional

import httpx

from app.classification.llm_result import LLMClassificationResult
from app.classification.prompt import CLASSIFICATION_SYSTEM_PROMPT, build_user_message
from app.classification.validation import parse_and_validate_llm_json

logger = logging.getLogger(__name__)


class LLMClassificationProvider:
    can_classify: bool = False
    last_failure_was_connect_error: bool = False

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

    def __init__(self, api_key: str, model: str) -> None:
        import google.genai as genai  # guarded import — only when provider is active
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @property
    def provider_id(self) -> str:
        return f"gemini:{self._model}"

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
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
                        max_output_tokens=500,
                        response_mime_type="application/json",
                    ),
                )
                return parse_and_validate_llm_json(response.text)
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
                logger.warning("Gemini classify failed for %r: %s", title[:60], exc)
                return None
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

    @property
    def provider_id(self) -> str:
        return f"ollama:{self._model}"

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None) -> Optional[LLMClassificationResult]:
        self.last_failure_was_connect_error = False
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
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["message"]["content"]
            return parse_and_validate_llm_json(raw_content)
        except httpx.ConnectError as exc:
            self.last_failure_was_connect_error = True
            logger.warning("Ollama not reachable for %r: %s", title[:60], exc)
            return None
        except Exception as exc:
            logger.warning("Ollama classify failed for %r: %s", title[:60], exc)
            return None
