"""
Translation provider interface and implementations.

- TranslationProvider: abstract base
- NoopTranslationProvider: returns None (translation disabled)
- ClaudeTranslationProvider: uses the Anthropic API

Configuration via environment variables:
  TRANSLATION_PROVIDER=disabled|claude   (default: disabled)
  TRANSLATION_API_KEY=<anthropic key>    (required for claude provider)
  TRANSLATION_MODEL=<model id>           (default: claude-haiku-4-5-20251001)
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a sports news headline translator. Translate the given headline into natural, fluent Hebrew.

Rules:
- Return ONLY the translated headline. No explanation, no quotes unless in the original.
- Preserve team names in their common Hebrew sports form when well-known
  (EuroLeague → יורוליג, EuroCup → יורוקאפ, NBA → NBA, Maccabi Tel Aviv → מכבי תל אביב,
  Hapoel Tel Aviv → הפועל תל אביב, Deni Avdija → דני אבדיה, Paris Basketball → פריז באסקטבול).
- Preserve numbers, scores, years, and competition names.
- Do not add facts not present in the original headline.
- Do not summarise beyond the headline.
"""


class TranslationProvider:
    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        raise NotImplementedError


class NoopTranslationProvider(TranslationProvider):
    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        return None


class ClaudeTranslationProvider(TranslationProvider):
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # guarded import — only required when provider is active
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            result = response.content[0].text.strip()
            if not result:
                return None
            return result
        except Exception as exc:
            logger.warning("ClaudeTranslationProvider error: %s", exc)
            raise
