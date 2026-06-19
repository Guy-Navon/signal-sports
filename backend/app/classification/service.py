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
            return GeminiLLMProvider(api_key=api_key, model=model)
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

    if provider_name == "fake":
        logger.info("LLM classification provider: fake (dev mode)")
        return FakeLLMProvider()

    if provider_name != "disabled":
        logger.warning("Unknown CLASSIFICATION_PROVIDER=%r; using disabled", provider_name)

    return DisabledLLMProvider()
