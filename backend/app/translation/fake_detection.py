"""
Fake/stub translation detection.

The FakeTranslationProvider prefixes stub translations with FAKE_PREFIX.
These are not real Hebrew translations and should be replaceable once a real
provider (e.g. claude) is configured.
"""

from typing import Optional

FAKE_PREFIX = "תרגום בדיקה:"


def is_fake_translation(title: str, translated_title: Optional[str]) -> bool:
    """Return True if the stored translation is a fake/stub from FakeTranslationProvider.

    Checks both translated_title and title because the backfill writes the stub
    to both fields simultaneously.
    """
    if translated_title is not None and translated_title.startswith(FAKE_PREFIX):
        return True
    if title.startswith(FAKE_PREFIX):
        return True
    return False
