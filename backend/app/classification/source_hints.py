"""
Source-specific sport hint extraction from structured URL paths.

Only sources with reliable, well-maintained URL category schemes are listed here.
The hint is treated as a strong guardrail — it overrides the LLM when sport can be
inferred with high confidence from a known URL category structure.

To add a new source: add a block under the source_id check in extract_source_sport_hint().
Do NOT add generic URL patterns here — all rules must be source-scoped.
"""

from typing import Literal, Optional


# Israel Hayom sport section URL category paths.
# /sport/other-sports/ and /sport/opinions-sport/ intentionally return None.
_IH_BASKETBALL_PATHS = ("/sport/israeli-basketball/", "/sport/world-basketball/")
_IH_FOOTBALL_PATHS = ("/sport/world-soccer/",)


def extract_source_sport_hint(
    source_id: str,
    url: str,
) -> Optional[Literal["basketball", "football"]]:
    """Return a sport hint derived from the article URL for known sources, or None.

    None means no override — callers should treat None as "no information".
    """
    if source_id == "israel_hayom_sport":
        url_lower = url.lower()
        if any(p in url_lower for p in _IH_BASKETBALL_PATHS):
            return "basketball"
        if any(p in url_lower for p in _IH_FOOTBALL_PATHS):
            return "football"
    return None
