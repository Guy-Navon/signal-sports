"""
Translation provider interface and implementations.

- TranslationProvider:        abstract base
- NoopTranslationProvider:    returns None (translation disabled)
- FakeTranslationProvider:    dev-only; returns realistic stub translations
- ClaudeTranslationProvider:  uses the Anthropic API

Configuration via environment variables:
  TRANSLATION_PROVIDER=disabled|fake|claude   (default: disabled)
  TRANSLATION_API_KEY=<anthropic key>         (required for claude provider)
  TRANSLATION_MODEL=<model id>               (default: claude-haiku-4-5-20251001)
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

# A small dictionary of sample translations used by FakeTranslationProvider.
# Add entries here to test specific titles without an API key.
_FAKE_KNOWN: dict[str, str] = {
    "Paris Basketball tratta Dave Joerger per la panchina":
        "פריז באסקטבול מנהלת מגעים עם דייב ייגר לתפקיד המאמן",
    "Umana Reyer in EuroCup: 12° anno di fila in Europa e licenza pluriennale":
        "אומנה רייר ביורוקאפ: שנה 12 ברציפות באירופה ורישיון רב-שנתי",
    "Παναθηναϊκός: Ανοίγει το ΟΑΚΑ για τον 5ο τελικό!":
        "פנאתינייקוס פותחת את ה-OAKA למשחק הגמר החמישי",
    "Maccabi Tel Aviv signs a new EuroLeague guard":
        "מכבי תל אביב חתמה על גארד יורוליג חדש",
    "Deni Avdija traded to Portland Trail Blazers":
        "דני אבדיה נסחר לפורטלנד טריל בלייזרס",
}


class TranslationProvider:
    can_translate: bool = False

    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        raise NotImplementedError


class NoopTranslationProvider(TranslationProvider):
    can_translate = False

    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        return None


class FakeTranslationProvider(TranslationProvider):
    """Dev-only provider for local UI testing without a real API key.

    Known titles return realistic Hebrew translations from a small built-in map.
    Unknown titles return the original prefixed with 'תרגום בדיקה: ' so it is
    visually obvious in the UI that fake translation occurred.

    Activate with: TRANSLATION_PROVIDER=fake
    """
    can_translate = True

    def translate_title_to_hebrew(self, text: str, source_language: str) -> Optional[str]:
        known = _FAKE_KNOWN.get(text)
        if known:
            return known
        return f"תרגום בדיקה: {text}"


class ClaudeTranslationProvider(TranslationProvider):
    can_translate = True

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
