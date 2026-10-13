"""
Module-level provider singleton loaded from environment variables at import time.
Mirrors the pattern used by app.translation.translation_service.
"""

import logging
import os

from app.classification.providers import (
    DisabledLLMProvider,
    FakeLLMProvider,
    LLMClassificationProvider,
    OllamaProvider,
)

logger = logging.getLogger(__name__)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
        return value if value > 0 else default
    except ValueError:
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        return default


def _openai_compat_from_env() -> LLMClassificationProvider:
    """CLASSIFICATION_PROVIDER=openai_compat (#261).

    Required: CLASSIFICATION_BASE_URL (e.g. https://api.groq.com/openai/v1),
    CLASSIFICATION_API_KEY and CLASSIFICATION_MODEL (no default: a hosted model
    is an owner decision, #262). Optional:
      CLASSIFICATION_TIMEOUT_SECONDS          read timeout, default 15
      CLASSIFICATION_MAX_OUTPUT_TOKENS        default 1000 (includes reasoning)
      CLASSIFICATION_RESPONSE_FORMAT          json_schema (default) | json_object | none
      CLASSIFICATION_REASONING_EFFORT         default low; empty or "none" omits it
    Anything missing or invalid falls back to disabled, with a warning that
    names the variable and never its value.
    """
    from app.classification.providers import RESPONSE_FORMATS, OpenAICompatibleProvider

    base_url = os.environ.get("CLASSIFICATION_BASE_URL", "").strip()
    api_key = os.environ.get("CLASSIFICATION_API_KEY", "").strip()
    model = os.environ.get("CLASSIFICATION_MODEL", "").strip()
    missing = [name for name, value in (
        ("CLASSIFICATION_BASE_URL", base_url),
        ("CLASSIFICATION_API_KEY", api_key),
        ("CLASSIFICATION_MODEL", model),
    ) if not value]
    if missing:
        logger.warning(
            "CLASSIFICATION_PROVIDER=openai_compat but %s not set — using disabled",
            ", ".join(missing),
        )
        return DisabledLLMProvider()
    if not base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        logger.warning(
            "CLASSIFICATION_BASE_URL must be https (or local http) — using disabled"
        )
        return DisabledLLMProvider()

    response_format = os.environ.get("CLASSIFICATION_RESPONSE_FORMAT", "json_schema").strip().lower()
    if response_format not in RESPONSE_FORMATS:
        logger.warning("Invalid CLASSIFICATION_RESPONSE_FORMAT=%r — using disabled", response_format)
        return DisabledLLMProvider()
    effort = os.environ.get("CLASSIFICATION_REASONING_EFFORT", "low").strip().lower()
    if effort == "none":
        effort = ""
    max_tokens = int(_float_env("CLASSIFICATION_MAX_OUTPUT_TOKENS", 1000))

    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=_float_env("CLASSIFICATION_TIMEOUT_SECONDS", 15.0),
        max_output_tokens=max_tokens,
        response_format=response_format,
        reasoning_effort=effort,
    )
    logger.info(
        "LLM classification provider: openai_compat (model=%s, format=%s, reasoning=%s)",
        model, response_format, effort or "omitted",
    )
    return provider


def get_llm_provider() -> LLMClassificationProvider:
    provider_name = os.environ.get("CLASSIFICATION_PROVIDER", "disabled").lower().strip()

    if provider_name == "gemini":
        api_key = os.environ.get("CLASSIFICATION_API_KEY", "")
        if not api_key:
            logger.warning(
                "CLASSIFICATION_PROVIDER=gemini but CLASSIFICATION_API_KEY is not set — using disabled"
            )
            return DisabledLLMProvider()
        model = os.environ.get("CLASSIFICATION_MODEL", "gemini-2.5-flash-lite")
        try:
            from app.classification.providers import GeminiLLMProvider
            logger.info("LLM classification provider: gemini (model=%s)", model)
            return GeminiLLMProvider(
                api_key=api_key,
                model=model,
                # Default 500 = the behaviour before #261. Raise it when a
                # thinking model truncates the JSON (finish_reason MAX_TOKENS).
                max_output_tokens=int(_float_env("CLASSIFICATION_MAX_OUTPUT_TOKENS", 500)),
            )
        except ImportError:
            logger.warning("google-genai package not installed — using disabled")
            return DisabledLLMProvider()

    if provider_name == "ollama":
        base_url = os.environ.get("CLASSIFICATION_OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.environ.get("CLASSIFICATION_MODEL", "llama3.2:3b")
        timeout_str = os.environ.get("CLASSIFICATION_TIMEOUT_SECONDS", "15")
        try:
            timeout = float(timeout_str)
        except ValueError:
            logger.warning("Invalid CLASSIFICATION_TIMEOUT_SECONDS=%r; using 15", timeout_str)
            timeout = 15.0
        logger.info("LLM classification provider: ollama (model=%s, url=%s)", model, base_url)
        return OllamaProvider(base_url=base_url, model=model, timeout=timeout)

    if provider_name == "openai_compat":
        return _openai_compat_from_env()

    if provider_name == "fake":
        logger.info("LLM classification provider: fake (dev mode)")
        return FakeLLMProvider()

    if provider_name != "disabled":
        logger.warning("Unknown CLASSIFICATION_PROVIDER=%r; using disabled", provider_name)

    return DisabledLLMProvider()
