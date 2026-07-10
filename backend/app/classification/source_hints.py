"""
Source-specific sport hint extraction from structured URL paths.

Only sources with reliable, well-maintained URL category schemes are listed here.
The hint is treated as a strong guardrail — it overrides the LLM when sport can be
inferred with high confidence from a known URL category structure.

To add a new source: add a block under the source_id check in extract_source_sport_hint().
Do NOT add generic URL patterns here — all rules must be source-scoped.
"""

import re
from typing import Literal, Optional


# Israel Hayom sport section URL category paths.
# /sport/other-sports/ and /sport/opinions-sport/ intentionally return None.
# Corpus audit (issue #62, 2026-07-10): observed categories israeli-basketball,
# world-basketball, israeli-soccer, world-soccer, other-sports, opinions-sport —
# israeli-soccer had been missing from the map (the golden C3 root enabler).
_IH_BASKETBALL_PATHS = ("/sport/israeli-basketball/", "/sport/world-basketball/")
_IH_FOOTBALL_PATHS = ("/sport/world-soccer/", "/sport/israeli-soccer/")

# Sport5 article URLs embed the CMS folder in the query string
# (articles.aspx?FolderID=274&docID=...). FolderID=274 is the basketball news
# folder — verified against the live basketball category page (PR 13 pilot).
# All other FolderIDs intentionally return None (conservative: broad/unknown
# categories fall through to keyword detection and gated LLM classification).
# Corpus audit (issue #62): folders 11840/405/416 appeared with basketball-
# leaning content (3/1/2 articles) but are NOT mapped — too little evidence
# and no live-page verification; the module contract requires both.
_SPORT5_BASKETBALL_FOLDER_MARKERS = ("folderid=274&", "folderid=274#")
_SPORT5_BASKETBALL_FOLDER_SUFFIX = "folderid=274"

# Ynet sport article paths observed in the official sport RSS feed.
# Generic /sport/article/ paths and livegame URLs intentionally return None:
# they are sport content, but the URL alone does not identify a specific sport.
# Corpus audit (issue #62): /sport/israelisoccer/ (11 articles) had been
# missing — it enabled the golden C2/C2-sibling misclassifications; /sport/
# tennis/ is now mapped as well.
_YNET_BASKETBALL_PATHS = (
    "/sport/israelibasketball/",
    "/sport/worldbasketball/",
)
_YNET_FOOTBALL_PATHS = (
    "/sport/worldsoccer/",
    "/sport/worldcup",
    "/sport/israelisoccer/",
)
_YNET_TENNIS_PATHS = ("/sport/tennis/",)

# Walla (corpus audit, issue #62): article URLs are uniformly
# sports.walla.co.il/item/<id> — they carry NO category signal, so walla can
# never have URL hints. Sport for walla articles comes from keywords,
# entities, and the gated LLM path only. This is a documented finding, not an
# oversight.

# ONE article URLs sometimes include the category id after the season segment:
# /Article/26-27/3,100,0,0/527252.html. Category IDs observed in the public
# article APIs: 1/3/155 football, 2/5 basketball, 7 other sports.
_ONE_CATEGORY_RE = re.compile(r"/article/\d{2}-\d{2}/(\d+),", re.IGNORECASE)
_ONE_FOOTBALL_CATEGORY_IDS = {"1", "3", "155"}
_ONE_BASKETBALL_CATEGORY_IDS = {"2", "5"}


def extract_source_sport_hint(
    source_id: str,
    url: str,
) -> Optional[Literal["basketball", "football", "tennis"]]:
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
    if source_id == "ynet_sport":
        url_lower = url.lower()
        if any(p in url_lower for p in _YNET_BASKETBALL_PATHS):
            return "basketball"
        if any(p in url_lower for p in _YNET_FOOTBALL_PATHS):
            return "football"
        if any(p in url_lower for p in _YNET_TENNIS_PATHS):
            return "tennis"
    if source_id == "one_sport":
        match = _ONE_CATEGORY_RE.search(url)
        if match:
            category_id = match.group(1)
            if category_id in _ONE_BASKETBALL_CATEGORY_IDS:
                return "basketball"
            if category_id in _ONE_FOOTBALL_CATEGORY_IDS:
                return "football"
    return None
