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

# Sport5 article URLs embed the CMS folder in the query string
# (articles.aspx?FolderID=274&docID=...). FolderID=274 is the basketball news
# folder — verified against the live basketball category page (PR 13 pilot).
# All other FolderIDs intentionally return None (conservative: broad/unknown
# categories fall through to keyword detection and gated LLM classification).
_SPORT5_BASKETBALL_FOLDER_MARKERS = ("folderid=274&", "folderid=274#")
_SPORT5_BASKETBALL_FOLDER_SUFFIX = "folderid=274"


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
    if source_id == "sport5_sport":
        url_lower = url.lower()
        # Exact-value match: "folderid=274" must not match e.g. folderid=2740.
        if (
            any(m in url_lower for m in _SPORT5_BASKETBALL_FOLDER_MARKERS)
            or url_lower.endswith(_SPORT5_BASKETBALL_FOLDER_SUFFIX)
        ):
            return "basketball"
    return None
