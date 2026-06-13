"""
Translation service — orchestrates provider selection and per-title translation.

Provider is selected from environment variables at first use and cached.
Tests can inject a custom provider via set_provider().
"""

import logging
import os
from typing import Optional

from app.translation.providers import TranslationProvider, NoopTranslationProvider

logger = logging.getLogger(__name__)

_provider: Optional[TranslationProvider] = None


def _build_provider() -> TranslationProvider:
    name = os.environ.get("TRANSLATION_PROVIDER", "disabled").lower().strip()
    if name in ("disabled", "", "noop"):
        return NoopTranslationProvider()

    if name == "claude":
        api_key = os.environ.get("TRANSLATION_API_KEY", "")
        if not api_key:
            logger.warning(
                "TRANSLATION_PROVIDER=claude but TRANSLATION_API_KEY is not set — "
                "falling back to noop"
            )
            return NoopTranslationProvider()
        model = os.environ.get("TRANSLATION_MODEL", "claude-haiku-4-5-20251001")
        try:
            from app.translation.providers import ClaudeTranslationProvider
            logger.info("Translation provider: Claude model=%s", model)
            return ClaudeTranslationProvider(api_key=api_key, model=model)
        except ImportError:
            logger.warning("anthropic package not installed — falling back to noop")
            return NoopTranslationProvider()

    logger.warning("Unknown TRANSLATION_PROVIDER=%r — falling back to noop", name)
    return NoopTranslationProvider()


def get_provider() -> TranslationProvider:
    """Return the active translation provider (built once from env, then cached)."""
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def set_provider(provider: TranslationProvider) -> None:
    """Override the active provider. Intended for tests only."""
    global _provider
    _provider = provider


def reset_provider() -> None:
    """Clear the cached provider so it is rebuilt on next use. Intended for tests."""
    global _provider
    _provider = None


def translate_title(
    title: str,
    source_language: str,
    *,
    provider: Optional[TranslationProvider] = None,
) -> Optional[str]:
    """Translate a title to Hebrew.

    Args:
        title:           The raw headline to translate.
        source_language: ISO 639-1 code of the source language.
        provider:        Optional override (useful in tests). If None, uses
                         the module-level cached provider.

    Returns:
        Hebrew title string, or None if translation is disabled or fails.
        Never raises.
    """
    if source_language == "he":
        return None

    active = provider if provider is not None else get_provider()
    try:
        return active.translate_title_to_hebrew(title, source_language)
    except Exception as exc:
        logger.warning("translate_title failed for %r (%s): %s", title, source_language, exc)
        return None
